"""Runtime: the bar-by-bar engine that both backtest and live use.

The runtime owns ALL strategy state. The strategy itself is pure. Pending
setups, active trades, locks, counters -- all live here so the same code
path drives backtest and live.

CRITICAL CONTRACT: the runtime processes bars in chronological order and
calls strategy methods with ONLY bars[0:current+1]. It is impossible for
the strategy to see future data because the runtime physically slices
history before passing it in.

PUBLIC API:
    rt = Runtime(strategy, fill_model, risk_engine, account_state,
                 strategy_params={"TARGET_PTS": 12})
    for ts, bar, history in feed:
        ctx = build_market_context(history, ts)
        closed_trade = rt.on_bar(bar, history, ts, ctx)
        if closed_trade:
            persist(closed_trade)
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, List, Optional

import pandas as pd

from engine.fills.base import FillModel
from engine.market_context import MarketContext
from engine.risk.engine import RiskEngine
from engine.risk.gates import AccountState
from engine.strategies.base import Strategy
from engine.types import (
    ActiveTrade, ClosedTrade, ExitReason, Fill, LimitOrder, Setup, Side,
    StopOrder, setup_to_orders,
)

logger = logging.getLogger("engine.runtime")

# Strategy timing constants -- override per-strategy if needed
MAX_WAIT_SECS = 300         # cancel pending setups after this long
MAX_HOLD_SECS = 600         # force exit after this long in a trade
MIN_TARGET_HOLD_SECS = 10   # Lucid microscalp safety


@dataclass
class PendingOrder:
    """A LIMIT entry order awaiting fill. Wraps the LimitOrder with the
    Setup that created it so we can build the ActiveTrade on fill."""
    setup: Setup
    order: LimitOrder
    submitted_at: datetime
    expires_at: datetime
    qty: int
    # For analytics: how many bars touched the limit before / without filling
    touch_count: int = 0


@dataclass
class RuntimeState:
    """Mutable state owned by the runtime."""
    pending: List[PendingOrder] = field(default_factory=list)
    active: Optional[ActiveTrade] = None
    last_trade_close_ts: Optional[datetime] = None
    # Dedup: a (side, round(level, 1), minute) key for setups we've already
    # acted on, so the strategy firing the same setup every tick doesn't
    # stack 20 pending orders.
    recent_used_keys: set = field(default_factory=set)


class Runtime:
    def __init__(self, strategy: Strategy, fill_model: FillModel,
                 risk_engine: RiskEngine, account: AccountState,
                 strategy_params: Optional[dict] = None,
                 default_qty: int = 2,
                 dollars_per_pt: float = 2.0,
                 commission_rt: float = 0.74):
        self.strategy = strategy
        self.fill = fill_model
        self.risk = risk_engine
        self.account = account
        self.params = strategy_params or {}
        self.default_qty = default_qty
        self.dollars_per_pt = dollars_per_pt
        self.commission_rt = commission_rt
        self.state = RuntimeState()
        # Audit log -- every decision the runtime made this bar. Bounded
        # deque so a long-running shadow engine doesn't leak memory; the
        # bundle download still gets the last N which is what matters.
        self.decisions: Deque[dict] = deque(maxlen=500)
        # Closed trades emitted from this runtime. Bounded for the same
        # reason -- after N trades the oldest get evicted. Stats /
        # snapshots that need totals over the full lifetime track sums
        # incrementally on the AccountState instead of recomputing from
        # the trade list.
        self.closed_trades: Deque[ClosedTrade] = deque(maxlen=1000)

    # -----------------------------------------------------------------
    # Per-bar entry point
    # -----------------------------------------------------------------
    def on_bar(self, bar: pd.Series, history: pd.DataFrame,
               now: datetime, ctx: MarketContext) -> Optional[ClosedTrade]:
        """Process ONE 1-min bar. Returns a ClosedTrade if one closed
        on this bar, else None.

        Order of operations matches the live bot's bot/pullback_strategy.py
        flow exactly so backtest == live:
          1. Update MAE/MFE on any active trade
          2. Check active trade for exits
          3. Detect a new setup and add to pending (still respecting risk
             engine + dedup) -- pending setups can accumulate across bars,
             one per minute, up to MAX_WAIT_SECS expiry
          4. Drop expired pending setups
          5. Try filling pending setups against this bar's OHLC. First
             fill wins; remaining pendings continue waiting next bar.

        Same-bar fill IS possible (step 3 adds, step 5 fills) -- matches
        the bot's actual is_filled check on the same bar that detected
        the setup.
        """
        # 1. Update excursions on active trade
        if self.state.active is not None:
            self.state.active.update_excursions(
                bar_high=float(bar["high"]),
                bar_low=float(bar["low"]),
            )

        # 2. Exit check
        if self.state.active is not None:
            closed = self._check_exit(bar, now, ctx)
            if closed is not None:
                return closed

        # 3. Detect new setup (only if no active trade)
        if self.state.active is None:
            new_setup = self.strategy.detect_setup(history, now, self.params)
            if new_setup is not None:
                self._consider_setup(new_setup, now, ctx)

        # 4. Drop expired pending setups
        self.state.pending = [
            p for p in self.state.pending if now < p.expires_at
        ]

        # 5. Try filling each pending setup against this bar
        if self.state.active is None and self.state.pending:
            for p in list(self.state.pending):
                if self._try_fill(p, bar, now, ctx):
                    self.state.pending = []  # one position at a time
                    break

        return None

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------
    def _setup_key(self, s: Setup) -> tuple:
        # Same dedup convention as bot/pullback_strategy
        return (s.side.value, round(s.entry_price, 1),
                int(s.detected_at.timestamp() // 60))

    def _consider_setup(self, setup: Setup, now: datetime,
                         ctx: MarketContext) -> None:
        key = self._setup_key(setup)
        # Dedup against recent-used AND existing pending (matches
        # bot/pullback_strategy.py)
        if key in self.state.recent_used_keys:
            return
        if any(self._setup_key(p.setup) == key for p in self.state.pending):
            return

        # Risk engine gate
        decision = self.risk.evaluate(setup, self.account, ctx)
        if not decision.allow:
            self._log_decision(now, f"risk_deny:{decision.reason}",
                                setup=setup, detail=decision.detail)
            return

        qty = decision.suggested_qty or self.default_qty
        entry_order, _stop, _target = setup_to_orders(setup, qty, now)
        pending = PendingOrder(
            setup=setup,
            order=entry_order,
            submitted_at=now,
            expires_at=now + timedelta(seconds=MAX_WAIT_SECS),
            qty=qty,
        )
        self.state.pending.append(pending)
        self._log_decision(now, "setup_submitted", setup=setup, qty=qty)

    def _try_fill(self, p: PendingOrder, bar: pd.Series,
                  now: datetime, ctx: MarketContext) -> bool:
        """Returns True if the order filled this bar."""
        fill = self.fill.check_limit_fill(p.order, bar, ctx)
        if fill is None:
            # Track touch-without-fill for analytics
            bar_low = float(bar["low"])
            bar_high = float(bar["high"])
            if (p.order.side is Side.LONG and bar_low <= p.order.price) or \
               (p.order.side is Side.SHORT and bar_high >= p.order.price):
                p.touch_count += 1
            return False

        # FILLED -- create the active trade
        active = ActiveTrade(
            setup=p.setup,
            entry_fill=fill,
            qty=p.qty,
            stop_price=p.setup.stop_price,
            target_price=p.setup.target_price,
            opened_at=fill.ts,
        )
        self.state.active = active
        self.state.recent_used_keys.add(self._setup_key(p.setup))
        # Trim recent_used set so it doesn't grow forever
        if len(self.state.recent_used_keys) > 500:
            self.state.recent_used_keys = set(list(self.state.recent_used_keys)[-300:])
        self.account.is_in_trade = True
        self._log_decision(now, "trade_opened", setup=p.setup,
                            fill_price=fill.fill_price,
                            latency_ms=fill.latency_ms,
                            touch_count=p.touch_count)
        return True

    def _check_exit(self, bar: pd.Series, now: datetime,
                     ctx: MarketContext) -> Optional[ClosedTrade]:
        t = self.state.active
        assert t is not None

        bar_high = float(bar["high"])
        bar_low  = float(bar["low"])
        bar_close = float(bar["close"])
        side = t.setup.side
        hold_s = t.hold_seconds(now)

        # Both stop and target may be hit on the same bar. Conservative:
        # assume STOP hit first (real markets are usually directional in
        # a bar that swept both extremes).
        if side is Side.LONG:
            hit_stop = bar_low  <= t.stop_price
            hit_tgt  = bar_high >= t.target_price
        else:
            hit_stop = bar_high >= t.stop_price
            hit_tgt  = bar_low  <= t.target_price

        if hit_stop and hit_tgt:
            # Bar swept both ways. Stop is conservative.
            return self._close_via_stop(bar, now, ctx)
        if hit_stop:
            return self._close_via_stop(bar, now, ctx)
        if hit_tgt:
            if hold_s < MIN_TARGET_HOLD_SECS:
                # Microscalp safety: target before 10s isn't booked yet.
                return None
            return self._close_via_target(bar, now, ctx)
        if hold_s >= MAX_HOLD_SECS:
            # Timeout exit at close
            close_fill = self.fill.fill_market(
                Side.SHORT if side is Side.LONG else Side.LONG,
                t.qty, bar, ctx)
            return self._finalize_close(close_fill, ExitReason.TIMEOUT, now)
        return None

    def _close_via_stop(self, bar, now, ctx) -> ClosedTrade:
        t = self.state.active
        exit_side = Side.SHORT if t.setup.side is Side.LONG else Side.LONG
        stop_order = StopOrder(side=exit_side, trigger_price=t.stop_price,
                                qty=t.qty)
        fill = self.fill.fill_stop(stop_order, bar, ctx)
        if fill is None:
            # Should never happen if _check_exit said hit_stop; conservative
            # fallback to market.
            fill = self.fill.fill_market(exit_side, t.qty, bar, ctx)
        return self._finalize_close(fill, ExitReason.STOP, now)

    def _close_via_target(self, bar, now, ctx) -> ClosedTrade:
        t = self.state.active
        exit_side = Side.SHORT if t.setup.side is Side.LONG else Side.LONG
        # Targets are LIMIT orders -- subject to touched-not-filled too!
        # This is the symmetric realism the old sim missed.
        target_order = LimitOrder(
            side=exit_side, price=t.target_price, qty=t.qty,
            setup_id="exit-target", submitted_at=t.opened_at)
        fill = self.fill.check_limit_fill(target_order, bar, ctx)
        if fill is None:
            # Touched but didn't fill -- stay in trade
            return None
        return self._finalize_close(fill, ExitReason.TARGET, now)

    def _finalize_close(self, exit_fill: Fill, reason: ExitReason,
                         now: datetime) -> ClosedTrade:
        t = self.state.active
        assert t is not None
        closed = ClosedTrade(
            setup=t.setup,
            entry_fill=t.entry_fill,
            exit_fill=exit_fill,
            exit_reason=reason,
            qty=t.qty,
            opened_at=t.opened_at,
            closed_at=exit_fill.ts,
            mae_pts=t.mae_pts,
            mfe_pts=t.mfe_pts,
        )
        self.closed_trades.append(closed)

        # Update account state
        pnl_usd = closed.pnl_usd(self.dollars_per_pt, self.commission_rt)
        self.account.balance += pnl_usd
        self.account.today_pnl += pnl_usd
        self.account.today_trades += 1
        self.account.lifetime_trades += 1
        self.account.lifetime_pnl += pnl_usd
        if pnl_usd > 0:
            self.account.lifetime_wins += 1
        self.account.last_trade_close_ts = exit_fill.ts
        self.account.is_in_trade = False
        if pnl_usd < 0:
            self.account.consecutive_losses += 1
        else:
            self.account.consecutive_losses = 0

        self.state.active = None
        self._log_decision(now, f"trade_closed:{reason.value}",
                            pnl_usd=round(pnl_usd, 2),
                            mae=round(t.mae_pts, 2), mfe=round(t.mfe_pts, 2))
        return closed

    # -----------------------------------------------------------------
    # Audit log
    # -----------------------------------------------------------------
    def _log_decision(self, now, event, **kwargs):
        self.decisions.append({"ts": now.isoformat(), "event": event, **kwargs})

    def roll_ny_day(self, now: datetime) -> None:
        """Called by the driver when NY date changes. Resets daily counters."""
        self.account.today_pnl = 0.0
        self.account.today_trades = 0

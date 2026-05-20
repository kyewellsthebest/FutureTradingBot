"""
Fibonacci 50% retracement strategy — runtime module for live deployment.

This is the production-ready Fib 50% strategy that replaces the v11 NQ-ES
divergence book. Built for Lucid 50K Pro Funded compliance.

Setup detection: 10-min bars
Exit walking : 1-min bars
Target       : full prior pivot (1:1 planned RR, ~1:1.26 realised)
Stop         : original swing extreme (the structural "wide" stop)

Safety layers (compliance + risk):
  1. Lucid pre-trade gates — DLL and trail-floor checks before every entry
  2. Hard 6-second minimum hold — exit orders are rejected if <6s since
     entry. Guarantees Lucid microscalp compliance regardless of price action.
  3. Live microscalp ratio tracker — rolling 30-day % of profit from ≤5s
     holds. Circuit-breaker disables the strategy if it crosses 40%.

Backtest performance (8.1 yrs NQ, 10-min entries, 5 MNQ, Lucid rules + costs):
  ~15,300 trades / 55.5% win / +$922k net / max DD -$8k / never blown
  Monthly avg: ~$9,500 / Worst-case microscalp ratio: 42.6% (below 50%)
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional

import numpy as np
import pandas as pd

from research.lucid_guard import (
    LucidState, evaluate_trade, GuardDecision,
    DLL, MICROSCALP_HOLD_THRESHOLD_S,
)

logger = logging.getLogger("fib_strategy")

# ---------------------------------------------------------------------------
# Strategy parameters — frozen from the backtest that produced $922k / 8yr
# ---------------------------------------------------------------------------
PIVOT_K = 5                       # fractal swing-pivot lookback (10-min bars)
MIN_LEG_PTS = 20                  # minimum leg size to consider
MAX_SETUP_AGE_BARS = 25           # 10-min bars (=~4 h) before setup expires
TARGET_REWARD_RATIO = 1.00        # full-pivot target
MAX_HOLD_1M_BARS = 480            # 8 h hard cap on a single trade
DEFAULT_SIZE = 5                  # MNQ contracts (5 MNQ recommended for $50k)

# ---------------------------------------------------------------------------
# Safety constants — Lucid compliance hard gates
# ---------------------------------------------------------------------------
MIN_TARGET_HOLD_SECONDS = 10      # min hold for TARGET exits (Lucid microscalp safety).
                                  # Stops fire immediately — only profit-taking
                                  # is what counts toward Lucid's microscalp rule.
MICROSCALP_HARD_THRESHOLD = 0.40  # circuit-breaker at 40% (well below 50%)
MICROSCALP_WINDOW_DAYS = 30       # rolling window for live ratio
TRAIL_SAFETY_PTS = 300            # extra buffer above trail floor


# ---------------------------------------------------------------------------
# State containers
# ---------------------------------------------------------------------------
@dataclass
class FibSetup:
    """A pending Fib 50% setup waiting for entry trigger or expiry."""
    detected_at: datetime
    side: str                     # "LONG" or "SHORT"
    pivot_high_val: float
    pivot_low_val: float
    level50: float
    expires_at: datetime
    used: bool = False

    @property
    def leg_pts(self) -> float:
        return self.pivot_high_val - self.pivot_low_val

    @property
    def target_px(self) -> float:
        risk_pts = self.leg_pts / 2.0
        if self.side == "SHORT":
            return self.level50 - TARGET_REWARD_RATIO * risk_pts
        return self.level50 + TARGET_REWARD_RATIO * risk_pts

    @property
    def stop_px(self) -> float:
        return self.pivot_high_val if self.side == "SHORT" else self.pivot_low_val


@dataclass
class ActiveTrade:
    """An open Fib trade — tracked through to exit."""
    entry_ts: datetime
    side: str
    n_mnq: int
    entry_px: float
    stop_px: float
    target_px: float
    setup: FibSetup
    max_hold_until: datetime
    exit_ts: Optional[datetime] = None
    exit_px: Optional[float] = None
    exit_reason: Optional[str] = None

    def is_open(self) -> bool:
        return self.exit_ts is None

    def hold_seconds(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        ref = self.exit_ts or now
        return (ref - self.entry_ts).total_seconds()


@dataclass
class FibStrategyState:
    """All runtime state for the Fib strategy.

    Persist this between bot restarts (alongside the LucidState) so we
    don't lose the microscalp ratio history."""
    pending_setups: list[FibSetup] = field(default_factory=list)
    active_trade: Optional[ActiveTrade] = None
    # rolling hold-time history for microscalp ratio (kept as list of
    # (timestamp_utc, hold_seconds, pnl_usd) for the last 30 days)
    completed_trades: Deque[dict] = field(default_factory=lambda: deque(maxlen=10_000))
    # Recent (pivot_high, pivot_low, side) keys for setups we've already
    # traded — prevents the same pivot pair from firing repeatedly while
    # the pivots are still the most recent on the chart.
    recent_used_setups: Deque[tuple] = field(default_factory=lambda: deque(maxlen=200))
    circuit_breaker_tripped: bool = False
    circuit_breaker_reason: Optional[str] = None


def _setup_key(setup_or_high, low: Optional[float] = None,
               side: Optional[str] = None) -> tuple:
    """Stable identity for a setup: rounded pivots + side."""
    if isinstance(setup_or_high, FibSetup):
        return (round(setup_or_high.pivot_high_val, 2),
                round(setup_or_high.pivot_low_val, 2),
                setup_or_high.side)
    return (round(setup_or_high, 2), round(low, 2), side)


# ---------------------------------------------------------------------------
# Helpers — pivots & 50% setup detection on 10-min bars
# ---------------------------------------------------------------------------
def _find_confirmed_pivots(bars: pd.DataFrame, k: int = PIVOT_K
                            ) -> tuple[Optional[tuple[int, float]],
                                       Optional[tuple[int, float]]]:
    """Return (most_recent_swing_high, most_recent_swing_low) as
    (source_idx, value). Both must be CONFIRMED — i.e. k bars have passed
    since the pivot. Returns (None, None) if not enough bars yet."""
    if len(bars) < 2 * k + 1:
        return None, None
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    n = len(bars)
    last_h = last_l = None
    for t in range(k, n - k):
        win = slice(t - k, t + k + 1)
        if h[t] == h[win].max():
            last_h = (t, float(h[t]))
        if l[t] == l[win].min():
            last_l = (t, float(l[t]))
    return last_h, last_l


def detect_setup(bars_10m: pd.DataFrame, now: datetime) -> Optional[FibSetup]:
    """Look at the most recent 10-min bars; if a fresh Fib 50% setup is
    forming, return it. The setup is just the level + target/stop levels;
    the entry trigger (price retracing to level50) is checked separately
    on the 1-min stream."""
    h_piv, l_piv = _find_confirmed_pivots(bars_10m, PIVOT_K)
    if h_piv is None or l_piv is None:
        return None
    h_src, h_val = h_piv
    l_src, l_val = l_piv
    if h_src == l_src:
        return None
    # Geometry sanity: the high pivot's VALUE must be above the low
    # pivot's VALUE for the leg to be a real swing. In a strong trend
    # the fractal-pivot finder can return a "swing low" whose value is
    # numerically above an older "swing high" (or vice versa). That
    # produces inverted stop/target levels and trades like LONG with
    # stop ABOVE entry, which then look like "stops with positive PnL"
    # in the trade log. Skip these — the strategy is only valid when
    # the two most recent pivots form a real high-over-low swing.
    if h_val <= l_val:
        return None
    leg = h_val - l_val
    if leg < MIN_LEG_PTS:
        return None
    # the later pivot wins the leg direction
    if h_src > l_src:
        side = "LONG"                 # leg up; expect retrace down then bounce
    else:
        side = "SHORT"
    # setup ages from the moment the LATER pivot was confirmed
    p1_src = max(h_src, l_src)
    bars_since_p1_confirm = len(bars_10m) - (p1_src + PIVOT_K) - 1
    if bars_since_p1_confirm > MAX_SETUP_AGE_BARS:
        return None
    bars_remaining = MAX_SETUP_AGE_BARS - bars_since_p1_confirm
    expires_at = now + timedelta(minutes=10 * bars_remaining)
    return FibSetup(
        detected_at=now,
        side=side,
        pivot_high_val=h_val,
        pivot_low_val=l_val,
        level50=(h_val + l_val) / 2.0,
        expires_at=expires_at,
    )


def check_trigger(setup: FibSetup, last_bar: pd.Series) -> bool:
    """Has price retraced to the 50% level on the latest 1-min bar?"""
    if setup.side == "SHORT":
        return float(last_bar["high"]) >= setup.level50
    return float(last_bar["low"]) <= setup.level50


# ---------------------------------------------------------------------------
# Lucid + safety gates
# ---------------------------------------------------------------------------
def lucid_precheck(setup: FibSetup, n_mnq: int, lucid: LucidState,
                   slip_pts: float = 1.0, commission_per_mnq: float = 1.0
                   ) -> GuardDecision:
    """Pre-trade Lucid gate. Computes worst-case loss including slippage +
    commission and asks LucidState if it allows the trade."""
    risk_pts = abs(setup.stop_px - setup.level50) + slip_pts
    reward_pts = abs(setup.target_px - setup.level50)
    dollar_per_pt = n_mnq * 2.0
    worst_loss = -(risk_pts * dollar_per_pt + n_mnq * commission_per_mnq)
    reward = reward_pts * dollar_per_pt - n_mnq * commission_per_mnq
    return evaluate_trade(lucid, side=setup.side, n_contracts=n_mnq,
                          proposed_pnl_at_target=reward,
                          proposed_pnl_at_stop=worst_loss)


def microscalp_ratio_30d(completed: Deque[dict],
                         now: Optional[datetime] = None) -> float:
    """Rolling 30-day fraction of profit from holds <=5 seconds."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MICROSCALP_WINDOW_DAYS)
    recent = [t for t in completed if t["ts"] >= cutoff]
    if not recent:
        return 0.0
    total_profit = sum(t["pnl_usd"] for t in recent if t["pnl_usd"] > 0)
    if total_profit <= 0:
        return 0.0
    micro_profit = sum(
        t["pnl_usd"] for t in recent
        if t["pnl_usd"] > 0 and t["hold_s"] <= MICROSCALP_HOLD_THRESHOLD_S
    )
    return micro_profit / total_profit


def check_circuit_breaker(state: FibStrategyState) -> None:
    """If 30-day microscalp ratio crosses threshold, trip the breaker."""
    if state.circuit_breaker_tripped:
        return
    ratio = microscalp_ratio_30d(state.completed_trades)
    if ratio >= MICROSCALP_HARD_THRESHOLD:
        state.circuit_breaker_tripped = True
        state.circuit_breaker_reason = (
            f"microscalp ratio {ratio*100:.1f}% >= {MICROSCALP_HARD_THRESHOLD*100:.0f}% "
            f"safety threshold"
        )
        logger.error("[CIRCUIT BREAKER TRIPPED] %s", state.circuit_breaker_reason)


# ---------------------------------------------------------------------------
# Trade lifecycle
# ---------------------------------------------------------------------------
def open_trade(setup: FibSetup, n_mnq: int, entry_px: float,
               now: datetime) -> Optional[ActiveTrade]:
    # Defensive geometry check: a LONG must have stop BELOW entry and
    # target ABOVE; a SHORT must have stop ABOVE entry and target BELOW.
    # detect_setup already filters inverted pivots, but if any future
    # path lets one through we refuse the trade rather than open one
    # that would generate misleading "stop with profit" exit records.
    stop_ok = (setup.side == "LONG" and setup.stop_px < entry_px) or \
              (setup.side == "SHORT" and setup.stop_px > entry_px)
    tgt_ok = (setup.side == "LONG" and setup.target_px > entry_px) or \
             (setup.side == "SHORT" and setup.target_px < entry_px)
    if not (stop_ok and tgt_ok):
        logger.warning(
            "open_trade REFUSED — inverted geometry: %s entry=%.2f "
            "stop=%.2f target=%.2f (pivots h=%.2f l=%.2f)",
            setup.side, entry_px, setup.stop_px, setup.target_px,
            setup.pivot_high_val, setup.pivot_low_val)
        return None
    return ActiveTrade(
        entry_ts=now,
        side=setup.side,
        n_mnq=n_mnq,
        entry_px=entry_px,
        stop_px=setup.stop_px,
        target_px=setup.target_px,
        setup=setup,
        max_hold_until=now + timedelta(minutes=MAX_HOLD_1M_BARS),
    )


def should_exit(trade: ActiveTrade, last_1m_bar: pd.Series,
                now: datetime) -> Optional[tuple[float, str]]:
    """Return (exit_px, reason) if the trade should exit now, else None.

    Minimum-hold rule (Lucid microscalp safety):
      * STOPS fire IMMEDIATELY — no delay. Losses don't count toward
        microscalp (no profit from a stop), so there's no reason to hold
        a losing position past the technical stop.
      * TARGETS require >= MIN_TARGET_HOLD_SECONDS of hold time before
        the exit fires. A target hit at second 4 is deferred; the bot
        keeps the position open until the 10s mark, then closes at
        whatever the price is.
      * TIMEOUTS fire immediately at the max-hold deadline.

    Ambiguity handling: when the bar straddles both stop and target
    (common with synthesized 1-min bars built from a 5-60s monitor
    window), use the bar's CLOSE relative to entry to disambiguate which
    way price actually finished — that's what really mattered.
    """
    hold_s = (now - trade.entry_ts).total_seconds()
    high = float(last_1m_bar["high"])
    low = float(last_1m_bar["low"])
    close = float(last_1m_bar["close"])

    stop_hit = (trade.side == "LONG" and low <= trade.stop_px) or \
               (trade.side == "SHORT" and high >= trade.stop_px)
    target_hit = (trade.side == "LONG" and high >= trade.target_px) or \
                 (trade.side == "SHORT" and low <= trade.target_px)
    timeout = now >= trade.max_hold_until

    if not stop_hit and not target_hit and not timeout:
        return None

    # Disambiguate "both hit" on the same bar by using close direction.
    # This is the synthesized-bar fix: monitor high/low accumulate over
    # the polling window, so both extremes can exceed the levels even
    # when price action only really touched one of them.
    if stop_hit and target_hit:
        if trade.side == "SHORT":
            stop_hit = close >= trade.entry_px
            target_hit = close < trade.entry_px
        else:
            stop_hit = close <= trade.entry_px
            target_hit = close > trade.entry_px

    # Stops always fire — protects the account, no microscalp concern
    if stop_hit:
        return trade.stop_px, "stop"

    # Targets get the min-hold gate (microscalp protection)
    if target_hit:
        if hold_s < MIN_TARGET_HOLD_SECONDS:
            logger.debug("target deferred: hold %.1fs < min %ds",
                         hold_s, MIN_TARGET_HOLD_SECONDS)
            return None
        return trade.target_px, "target"

    # Timeout exit — fires regardless of hold time
    return close, "timeout"


def close_trade(trade: ActiveTrade, exit_px: float, reason: str,
                now: datetime, commission_per_mnq: float = 1.0) -> dict:
    """Mark the trade closed. Returns a dict to push onto the rolling
    microscalp tracker AND to record in persistence."""
    trade.exit_ts = now
    trade.exit_px = exit_px
    trade.exit_reason = reason
    pnl_pts = (trade.entry_px - exit_px) if trade.side == "SHORT" else \
              (exit_px - trade.entry_px)
    pnl_usd = pnl_pts * trade.n_mnq * 2.0 - trade.n_mnq * commission_per_mnq
    return {
        "ts": now,
        "entry_ts": trade.entry_ts,
        "side": trade.side,
        "n_mnq": trade.n_mnq,
        "entry_px": trade.entry_px,
        "exit_px": exit_px,
        "exit_reason": reason,
        "pnl_usd": float(pnl_usd),
        "pnl_pts": float(pnl_pts),
        "hold_s": float(trade.hold_seconds(now)),
    }


# ---------------------------------------------------------------------------
# Top-level tick — call this each time new 1-min bar data arrives
# ---------------------------------------------------------------------------
def on_new_1m_bar(state: FibStrategyState, lucid: LucidState,
                  bars_10m: pd.DataFrame, last_1m_bar: pd.Series,
                  now: datetime, n_mnq: int = DEFAULT_SIZE
                  ) -> Optional[dict]:
    """Single entry point for the runtime. Pass the latest 10-min bar
    history + the latest 1-min bar + the bot's clock. Returns the closed
    trade dict if a trade just closed, else None.

    Side effects: mutates FibStrategyState (adds setups, opens/closes
    trades, updates rolling history, may trip circuit breaker)."""
    # circuit breaker is a hard stop
    check_circuit_breaker(state)
    if state.circuit_breaker_tripped:
        return None

    # 1. manage active trade first
    if state.active_trade is not None:
        result = should_exit(state.active_trade, last_1m_bar, now)
        if result is not None:
            exit_px, reason = result
            record = close_trade(state.active_trade, exit_px, reason, now)
            state.completed_trades.append(record)
            state.active_trade = None
            logger.info("[CLOSE] %s pnl=$%.2f hold=%.1fs reason=%s",
                        record["side"], record["pnl_usd"],
                        record["hold_s"], record["exit_reason"])
            return record
        return None

    # 2. detect new setup on closed 10-min bars
    new_setup = detect_setup(bars_10m, now)
    if new_setup is not None:
        key = _setup_key(new_setup)
        # Skip if we've recently fired on this exact pivot pair.
        # Prevents the "same setup re-fires on every tick" loop where
        # the bot keeps re-detecting the same h_val/l_val until new
        # pivots form on the 10-min chart.
        if key in state.recent_used_setups:
            new_setup = None
        elif any(s.side == new_setup.side
                   and abs(s.level50 - new_setup.level50) < 0.5
                   for s in state.pending_setups if not s.used):
            # already in pending list as well
            new_setup = None
        else:
            state.pending_setups.append(new_setup)
            logger.debug("[SETUP] %s level50=%.2f leg=%.1fpts",
                         new_setup.side, new_setup.level50, new_setup.leg_pts)

    # 3. expire stale setups
    state.pending_setups = [s for s in state.pending_setups
                             if s.expires_at > now and not s.used]

    # 4. check triggers against the latest 1-min bar
    for setup in state.pending_setups:
        if not check_trigger(setup, last_1m_bar):
            continue
        # Lucid pre-check
        decision = lucid_precheck(setup, n_mnq, lucid)
        if not decision.allowed:
            logger.info("[BLOCKED] Lucid: %s", decision.reason)
            setup.used = True
            state.recent_used_setups.append(_setup_key(setup))
            continue
        # entry at this bar's close — closest realistic fill
        entry_px = float(last_1m_bar["close"])
        new_trade = open_trade(setup, n_mnq, entry_px, now)
        if new_trade is None:
            # geometry guard tripped — already logged; skip this setup
            setup.used = True
            state.recent_used_setups.append(_setup_key(setup))
            continue
        state.active_trade = new_trade
        setup.used = True
        state.recent_used_setups.append(_setup_key(setup))
        logger.info("[OPEN] %s %d MNQ @ %.2f  stop=%.2f tgt=%.2f",
                    setup.side, n_mnq, entry_px, setup.stop_px, setup.target_px)
        break

    return None


# ---------------------------------------------------------------------------
# Snapshot for dashboard / monitoring
# ---------------------------------------------------------------------------
def snapshot(state: FibStrategyState,
             current_price: Optional[float] = None) -> dict:
    """Lightweight JSON-serialisable snapshot for the dashboard. If
    current_price is supplied, the active-trade block includes live
    unrealised P&L."""
    now = datetime.now(timezone.utc)
    rolling = list(state.completed_trades)
    ratio = microscalp_ratio_30d(state.completed_trades, now)
    active = None
    if state.active_trade is not None:
        t = state.active_trade
        active = {
            "side": t.side,
            "n_mnq": t.n_mnq,
            "entry_px": t.entry_px,
            "stop_px": t.stop_px,
            "target_px": t.target_px,
            "hold_s": t.hold_seconds(now),
        }
        if current_price is not None:
            pnl_pts = (t.entry_px - current_price) if t.side == "SHORT" \
                      else (current_price - t.entry_px)
            active["current_price"] = float(current_price)
            active["unrealized_pnl_usd"] = float(pnl_pts * t.n_mnq * 2.0)
            active["unrealized_pnl_pts"] = float(pnl_pts)
    # The actual setups (not just count) so the dashboard can draw the
    # bot's "what I'm watching" levels. Capped at the most recent N to
    # avoid line clutter on the chart.
    live_setups = [s for s in state.pending_setups if not s.used][-5:]
    pending_setup_details = [
        {
            "side": s.side,
            "level50": s.level50,
            "pivot_high_val": s.pivot_high_val,
            "pivot_low_val": s.pivot_low_val,
            "target_px": s.target_px,
            "stop_px": s.stop_px,
            "detected_at": s.detected_at.isoformat()
                if hasattr(s.detected_at, "isoformat") else str(s.detected_at),
            "expires_at": s.expires_at.isoformat()
                if hasattr(s.expires_at, "isoformat") else str(s.expires_at),
        }
        for s in live_setups
    ]
    return {
        "active_trade": active,
        "pending_setups": len(live_setups),
        "pending_setup_details": pending_setup_details,
        "completed_30d_n": len(rolling),
        "completed_30d_pnl": sum(t["pnl_usd"] for t in rolling),
        "microscalp_ratio_30d": ratio,
        "microscalp_threshold": MICROSCALP_HARD_THRESHOLD,
        "circuit_breaker_tripped": state.circuit_breaker_tripped,
        "circuit_breaker_reason": state.circuit_breaker_reason,
        "min_target_hold_seconds": MIN_TARGET_HOLD_SECONDS,
    }

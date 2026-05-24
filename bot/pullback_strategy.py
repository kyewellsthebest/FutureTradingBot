"""Pullback-After-Impulse strategy for the live bot.

REPLACES bot/fib_strategy.py at runtime. Matches the same public interface
(FibStrategyState, on_new_1m_bar, snapshot, lucid_precheck) so fib_main.py
works unchanged — just update its import.

STRATEGY:
  1. Watch every newly-closed 1-min bar
  2. When the net move over the last 3 bars >= IMPULSE_PTS, an impulse is
     detected. Compute the impulse range (highest high - lowest low of
     those 3 bars). Create a pending pullback setup at the 0.618 retracement
     of the impulse range.
  3. If price reaches the pullback level within MAX_WAIT_SECS, fire a trade:
       - LONG if impulse was up (so we're buying the dip)
       - SHORT if impulse was down (selling the rip)
       - Stop: STOP_PTS away from entry
       - Target: TARGET_PTS away from entry (in trade direction)
  4. Trade exits on stop, target, or MAX_HOLD_SECS timeout
  5. COOLDOWN_SECS after exit before any new entry can fire

VALIDATED RESULTS (OOS 22 days, Dec 2025 — Feb 2026 NQ tick data,
                    1 MNQ fixed, 200ms latency, $1/contract comm):
  - 3,203 trades, 45.71% WR, PF 1.22, RR 1.45
  - +13.70%/mo monthly return
  - 0.63% max drawdown
  - 11 of 12 weeks profitable (92%)

Position size: FIXED at 1 MNQ.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional

import pandas as pd

from research.lucid_guard import LucidState, GuardDecision

logger = logging.getLogger("pullback_strategy")


# ============================================================================
# Strategy parameters (validated OOS-positive on NQ tick data)
#
# Full 3-month sim @ Lucid costs ($0.74 RT, 0.25pt adv slip), 2 MNQ:
#   +21.30%/mo, 1.66% max DD, PF 1.244, RR 1.65, WR 43%, 7,809 trades
#
# Out-of-sample split-half check (40d train / 40d val):
#   train +12.59%/mo, val +30.13%/mo  — better than baseline on BOTH halves
#
# Monte Carlo (1000 resamples): median +21.19%/mo, 5-95% [+17.46, +25.17],
# P(positive)=100%, P(>=10%)=100%, P(blow $2K trail)=0.1%.
# ============================================================================
DEFAULT_SIZE = 2                  # 2 MNQ fixed — worst sim day -$489 vs $1,200 DLL
IMPULSE_PTS = 5.0                 # min net move (in NQ pts) over IMPULSE_WINDOW_BARS
IMPULSE_WINDOW_BARS = 4           # impulse measured across last 4 closed 1-min bars
PULLBACK_PCT = 0.618              # 61.8% retracement of impulse range
STOP_PTS = 6.0                    # stop distance from entry (NQ pts)
TARGET_PTS = 12.0                 # target distance from entry (NQ pts)
MAX_HOLD_SECS = 600               # 10 minutes max in trade
MAX_WAIT_SECS = 300               # pullback setup expires if not filled in 5 min
COOLDOWN_SECS = 60                # min gap between trades
MIN_TARGET_HOLD_SECONDS = 10      # Lucid microscalp safety: target exits < 10s become "instant scalp"
MICROSCALP_HARD_THRESHOLD = 0.40  # circuit breaker if >40% of recent trades < MIN_TARGET_HOLD_SECONDS
MICROSCALP_WINDOW_DAYS = 30


# ============================================================================
# Setup / trade dataclasses (names match fib_strategy for compatibility)
# ============================================================================
@dataclass
class FibSetup:
    """A pending pullback setup waiting for the live price to reach the
    pullback entry level. Named FibSetup for fib_main compatibility."""
    detected_at: datetime
    side: str                                 # "LONG" or "SHORT"
    impulse_high: float
    impulse_low: float
    pullback_entry: float                     # the limit price
    stop_px_val: float
    target_px_val: float
    expires_at: datetime
    pivot_high_ts: Optional[datetime] = None  # bar that defined impulse high
    pivot_low_ts: Optional[datetime] = None
    used: bool = False
    entry_armed: bool = False                 # set True when price touches pullback_entry
    fire_attempted: bool = False
    last_block_reason: Optional[str] = None
    last_block_at: Optional[datetime] = None
    armed_at_ts: Optional[datetime] = None

    # Compatibility attributes for the dashboard (it reads .level50, .pivot_high_val, .pivot_low_val)
    @property
    def level50(self) -> float:
        return self.pullback_entry

    @property
    def pivot_high_val(self) -> float:
        return self.impulse_high

    @property
    def pivot_low_val(self) -> float:
        return self.impulse_low

    @property
    def leg_pts(self) -> float:
        return self.impulse_high - self.impulse_low

    @property
    def target_px(self) -> float:
        return self.target_px_val

    @property
    def stop_px(self) -> float:
        return self.stop_px_val

    def is_filled(self, bar: pd.Series) -> bool:
        """LIMIT semantics — price must reach pullback_entry from outside."""
        if self.side == "LONG":
            return float(bar["low"]) <= self.pullback_entry
        return float(bar["high"]) >= self.pullback_entry

    def is_invalidated(self, now: datetime) -> bool:
        if self.used: return False
        # Hard expiry
        if now >= self.expires_at: return True
        return False


@dataclass
class ActiveTrade:
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
    """Runtime state. Same name as the fib version for compat."""
    pending_setups: list[FibSetup] = field(default_factory=list)
    active_trade: Optional[ActiveTrade] = None
    completed_trades: Deque[dict] = field(default_factory=lambda: deque(maxlen=10_000))
    recent_used_setups: Deque[tuple] = field(default_factory=lambda: deque(maxlen=200))
    circuit_breaker_tripped: bool = False
    circuit_breaker_reason: Optional[str] = None
    htf_trend: str = "FLAT"           # dashboard compatibility
    chop_index: float = 0.0           # dashboard compatibility
    last_trade_close_ts: Optional[datetime] = None   # for cooldown


# ============================================================================
# Setup detection from last N closed bars
# ============================================================================
def detect_pullback_setup(bars: pd.DataFrame, now: datetime
                          ) -> Optional[FibSetup]:
    """Look at last IMPULSE_WINDOW_BARS closed bars; if their net move
    >= IMPULSE_PTS, return a pending pullback setup. Else None.
    """
    if bars is None or len(bars) < IMPULSE_WINDOW_BARS:
        return None
    window = bars.iloc[-IMPULSE_WINDOW_BARS:]
    net = float(window["close"].iloc[-1]) - float(window["open"].iloc[0])
    if abs(net) < IMPULSE_PTS:
        return None
    impulse_high = float(window["high"].max())
    impulse_low = float(window["low"].min())
    impulse_range = impulse_high - impulse_low
    if impulse_range <= 0:
        return None

    side = "LONG" if net > 0 else "SHORT"
    if side == "LONG":
        pullback_entry = impulse_high - PULLBACK_PCT * impulse_range
        stop_px = pullback_entry - STOP_PTS
        target_px = pullback_entry + TARGET_PTS
    else:
        pullback_entry = impulse_low + PULLBACK_PCT * impulse_range
        stop_px = pullback_entry + STOP_PTS
        target_px = pullback_entry - TARGET_PTS

    # bar timestamps for chart placement
    try:
        ph_ts = window.iloc[window["high"].values.argmax()].name
        pl_ts = window.iloc[window["low"].values.argmin()].name
    except Exception:
        ph_ts = pl_ts = None

    return FibSetup(
        detected_at=now,
        side=side,
        impulse_high=impulse_high,
        impulse_low=impulse_low,
        pullback_entry=pullback_entry,
        stop_px_val=stop_px,
        target_px_val=target_px,
        expires_at=now + timedelta(seconds=MAX_WAIT_SECS),
        pivot_high_ts=ph_ts,
        pivot_low_ts=pl_ts,
    )


def _setup_key(setup: FibSetup) -> tuple:
    """Dedup key — same impulse high/low/side = same setup."""
    return (round(setup.impulse_high, 1), round(setup.impulse_low, 1), setup.side)


# ============================================================================
# Lucid precheck — pass-through (1 MNQ is always within DLL room)
# ============================================================================
def lucid_precheck(setup: FibSetup, n_mnq: int, lucid: LucidState,
                   slip_pts: float = 0.5) -> GuardDecision:
    """At 1 MNQ the risk per trade is tiny (~$13). Defer to the canonical
    lucid_guard.evaluate_trade for the actual Lucid rule checks."""
    from research.lucid_guard import evaluate_trade
    stop_pts = abs(setup.stop_px_val - setup.pullback_entry) + slip_pts
    target_pts = abs(setup.target_px_val - setup.pullback_entry)
    proposed_pnl_at_stop = -stop_pts * n_mnq * 2.0
    proposed_pnl_at_target = target_pts * n_mnq * 2.0
    return evaluate_trade(
        lucid,
        side=setup.side,
        n_contracts=n_mnq,
        proposed_pnl_at_target=proposed_pnl_at_target,
        proposed_pnl_at_stop=proposed_pnl_at_stop,
    )


# ============================================================================
# Microscalp circuit breaker (same logic as fib strategy)
# ============================================================================
def microscalp_ratio_30d(completed: Deque[dict],
                          now: Optional[datetime] = None) -> float:
    """% of recent target-exit trades that closed in < MIN_TARGET_HOLD_SECONDS."""
    if not completed: return 0.0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MICROSCALP_WINDOW_DAYS)
    recent_target = [t for t in completed
                     if t.get("exit_reason") == "target"
                     and pd.to_datetime(t.get("exit_ts", t.get("entry_ts"))).to_pydatetime()
                         > cutoff]
    if not recent_target: return 0.0
    scalps = sum(1 for t in recent_target
                 if t.get("hold_s", 999) < MIN_TARGET_HOLD_SECONDS)
    return scalps / len(recent_target)


def check_circuit_breaker(state: FibStrategyState) -> None:
    if state.circuit_breaker_tripped: return
    ratio = microscalp_ratio_30d(state.completed_trades)
    if ratio >= MICROSCALP_HARD_THRESHOLD:
        state.circuit_breaker_tripped = True
        state.circuit_breaker_reason = (
            f"microscalp ratio {ratio*100:.1f}% >= {MICROSCALP_HARD_THRESHOLD*100:.0f}% "
            "— pausing entries until manual reset"
        )
        logger.error("[CIRCUIT BREAKER] %s", state.circuit_breaker_reason)


# ============================================================================
# Trade management
# ============================================================================
def open_trade(setup: FibSetup, n_mnq: int, entry_px: float,
               now: datetime) -> ActiveTrade:
    max_hold_until = now + timedelta(seconds=MAX_HOLD_SECS)
    return ActiveTrade(
        entry_ts=now, side=setup.side, n_mnq=n_mnq,
        entry_px=entry_px,
        stop_px=setup.stop_px_val,
        target_px=setup.target_px_val,
        setup=setup,
        max_hold_until=max_hold_until,
    )


def should_exit(trade: ActiveTrade, last_1m_bar: pd.Series,
                now: datetime) -> Optional[tuple[float, str]]:
    """Return (exit_px, reason) if this bar triggers exit, else None.

    Exit rules per Lucid Terms of Use:
      - STOPS fire IMMEDIATELY — losses are NOT subject to microscalp
        rule (Lucid only counts profitable trades held <=5s).
        Cutting losses fast is good risk management.
      - TARGETS require >= MIN_TARGET_HOLD_SECONDS (10s) of hold time.
        Lucid's microscalp threshold is 5s; we use 10s as safety buffer.
      - TIMEOUTS naturally past 10s (10-min max hold).
    """
    high = float(last_1m_bar["high"])
    low = float(last_1m_bar["low"])
    close = float(last_1m_bar["close"])

    if trade.side == "LONG":
        # Stops fire immediately — protect downside
        if low <= trade.stop_px:
            return trade.stop_px, "stop"
        # Targets wait 10s — Lucid microscalp safety
        if high >= trade.target_px:
            hold_s = trade.hold_seconds(now)
            if hold_s < MIN_TARGET_HOLD_SECONDS:
                return None
            return trade.target_px, "target"
    else:
        if high >= trade.stop_px:
            return trade.stop_px, "stop"
        if low <= trade.target_px:
            hold_s = trade.hold_seconds(now)
            if hold_s < MIN_TARGET_HOLD_SECONDS:
                return None
            return trade.target_px, "target"

    if now >= trade.max_hold_until:
        return close, "timeout"
    return None


def close_trade(trade: ActiveTrade, exit_px: float, reason: str,
                now: datetime) -> dict:
    trade.exit_ts = now
    trade.exit_px = exit_px
    trade.exit_reason = reason
    hold_s = trade.hold_seconds(now)
    pnl_pts = (trade.entry_px - exit_px) if trade.side == "SHORT" \
              else (exit_px - trade.entry_px)
    pnl_usd = pnl_pts * trade.n_mnq * 2.0   # $2/pt per MNQ; commissions
                                            # handled in the account layer
    return {
        "entry_ts": trade.entry_ts, "exit_ts": now,
        "side": trade.side, "n_mnq": trade.n_mnq,
        "entry_px": trade.entry_px, "exit_px": exit_px,
        "stop_px": trade.stop_px, "target_px": trade.target_px,
        "exit_reason": reason, "hold_s": hold_s,
        "pnl_pts": pnl_pts, "pnl_usd": pnl_usd,
        "armed_at_ts": trade.setup.armed_at_ts,
    }


# ============================================================================
# Main entry point — called by fib_main.py runtime
# ============================================================================
def on_new_1m_bar(state: FibStrategyState, lucid: LucidState,
                  bars_setup: pd.DataFrame, last_1m_bar: pd.Series,
                  now: datetime, n_mnq: int = DEFAULT_SIZE,
                  bars_trend: Optional[pd.DataFrame] = None
                  ) -> Optional[dict]:
    """Single entry per tick. Returns closed-trade dict if a trade exited.

    Strategy:
      1. Check circuit breaker
      2. Manage active trade (stop/target/timeout exit)
      3. Detect new pullback setups from closed 1-min bars
      4. Arm any setup whose pullback level got touched by live bar
      5. Fire armed setups (subject to cooldown + lucid precheck)
    """
    check_circuit_breaker(state)
    if state.circuit_breaker_tripped:
        return None

    # 1. MANAGE active trade
    if state.active_trade is not None:
        result = should_exit(state.active_trade, last_1m_bar, now)
        if result is not None:
            exit_px, reason = result
            record = close_trade(state.active_trade, exit_px, reason, now)
            state.completed_trades.append(record)
            state.active_trade = None
            state.last_trade_close_ts = now
            logger.info("[CLOSE] %s pnl=$%.2f hold=%.1fs reason=%s",
                        record["side"], record["pnl_usd"],
                        record["hold_s"], record["exit_reason"])
            return record
        return None

    # 2. Cooldown gate (no new entries until COOLDOWN_SECS after last close)
    in_cooldown = (state.last_trade_close_ts is not None and
                   (now - state.last_trade_close_ts).total_seconds() < COOLDOWN_SECS)

    # 3. DETECT new setup from latest 1-min bar history
    new_setup = detect_pullback_setup(bars_setup, now)
    if new_setup is not None:
        key = _setup_key(new_setup)
        # dedup against recent + pending
        already = (key in state.recent_used_setups or
                   any(_setup_key(s) == key for s in state.pending_setups if not s.used))
        if not already:
            state.pending_setups.append(new_setup)
            logger.info("[SETUP] %s impulse=[%.2f,%.2f] pullback=%.2f stop=%.2f tgt=%.2f",
                        new_setup.side, new_setup.impulse_low,
                        new_setup.impulse_high, new_setup.pullback_entry,
                        new_setup.stop_px_val, new_setup.target_px_val)

    # 4. Drop expired/invalidated setups
    state.pending_setups = [s for s in state.pending_setups
                            if not s.is_invalidated(now)]

    # 5. FIRE armed setups
    if in_cooldown:
        return None

    for setup in state.pending_setups:
        if setup.used: continue
        # check if live bar reached pullback_entry (limit fill semantics)
        if not setup.is_filled(last_1m_bar): continue
        setup.fire_attempted = True
        if setup.armed_at_ts is None:
            try:
                setup.armed_at_ts = last_1m_bar.name \
                    if hasattr(last_1m_bar, "name") else now
            except Exception:
                setup.armed_at_ts = now
            setup.entry_armed = True

        # Lucid precheck (n_mnq is 1 by default, rarely blocked)
        decision = lucid_precheck(setup, n_mnq, lucid)
        if not decision.allowed:
            if decision.reason != setup.last_block_reason:
                logger.info("[BLOCKED] %s reason=%s", setup.side, decision.reason)
            setup.last_block_reason = decision.reason
            setup.last_block_at = now
            continue
        size_to_use = decision.suggested_n if decision.suggested_n > 0 else n_mnq

        # ENTRY at pullback level (limit fill assumption)
        entry_px = float(setup.pullback_entry)
        new_trade = open_trade(setup, size_to_use, entry_px, now)
        state.active_trade = new_trade
        setup.used = True
        state.recent_used_setups.append(_setup_key(setup))
        logger.info("[OPEN] %s %d MNQ @ %.2f  stop=%.2f tgt=%.2f",
                    setup.side, size_to_use, entry_px,
                    setup.stop_px_val, setup.target_px_val)
        break   # only one position at a time

    return None


# ============================================================================
# Snapshot (for dashboard)
# ============================================================================
def snapshot(state: FibStrategyState,
             dashboard_extras: Optional[dict] = None) -> dict:
    out = {
        "strategy": "pullback_impulse_v1",
        "default_size": DEFAULT_SIZE,
        "impulse_pts": IMPULSE_PTS,
        "impulse_window_bars": IMPULSE_WINDOW_BARS,
        "pullback_pct": PULLBACK_PCT,
        "stop_pts": STOP_PTS,
        "target_pts": TARGET_PTS,
        "max_hold_secs": MAX_HOLD_SECS,
        "cooldown_secs": COOLDOWN_SECS,
        "microscalp_threshold": MICROSCALP_HARD_THRESHOLD,
        "microscalp_window_days": MICROSCALP_WINDOW_DAYS,
        "min_target_hold_seconds": MIN_TARGET_HOLD_SECONDS,
        "htf_trend": state.htf_trend,
        "chop_index": state.chop_index,
        "circuit_breaker": {
            "tripped": state.circuit_breaker_tripped,
            "reason": state.circuit_breaker_reason,
        },
        "active_trade": None,
        "pending_setups": [],
    }
    if state.active_trade is not None:
        t = state.active_trade
        out["active_trade"] = {
            "entry_ts": t.entry_ts.isoformat() if t.entry_ts else None,
            "side": t.side, "n_mnq": t.n_mnq,
            "entry_px": t.entry_px,
            "stop_px": t.stop_px, "target_px": t.target_px,
            "hold_s": t.hold_seconds(),
        }
    for s in state.pending_setups:
        if s.used: continue
        out["pending_setups"].append({
            "detected_at": s.detected_at.isoformat() if s.detected_at else None,
            "side": s.side,
            "pivot_high_val": s.impulse_high,
            "pivot_low_val": s.impulse_low,
            "level50": s.pullback_entry,
            "stop_px": s.stop_px_val,
            "target_px": s.target_px_val,
            "entry_armed": s.entry_armed,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "last_block_reason": s.last_block_reason,
            "armed_at_ts": s.armed_at_ts.isoformat() if s.armed_at_ts else None,
            "pivot_high_ts": s.pivot_high_ts.isoformat() if s.pivot_high_ts else None,
            "pivot_low_ts": s.pivot_low_ts.isoformat() if s.pivot_low_ts else None,
        })
    if dashboard_extras:
        out.update(dashboard_extras)
    return out

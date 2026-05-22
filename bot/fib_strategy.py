"""
Fibonacci 50% retracement strategy — runtime module for live deployment.

This is the production-ready Fib 50% strategy that replaces the v11 NQ-ES
divergence book. Built for Lucid 50K Pro Funded compliance.

Setup detection: 1-min bars (real Polygon 1-min, or synthesized from 5-min)
Exit walking : 1-min bars (real-time via PriceMonitor)
HTF filter   : 1-min trend state at k=30 (only trade WITH the trend)
Target       : full prior pivot (1:1 planned RR)
Stop         : original swing extreme (the structural "wide" stop)
Sizing       : 5 MNQ default with Lucid `suggested_n` auto-downscale

Safety layers (compliance + risk):
  1. Lucid pre-trade gates — DLL and trail-floor checks before every entry,
     with auto-downscale via the precheck's suggested_n.
  2. 1-min HTF trend filter (k=5) — longs only fire when the 1-min
     trend is UP, shorts only when DOWN. Same-timeframe trend at k=5
     reacts in ~5 min, catches reversals fast enough to allow new
     trend-following setups without lagging.
  3. Hard 10-second min hold on TARGET exits — keeps trades out of Lucid's
     microscalp bucket. Stops always fire immediately (no profit to track).
  4. Live microscalp ratio tracker — rolling 30-day % of profit from ≤5s
     holds. Circuit-breaker disables the strategy if it crosses 40%.

Backtest performance (5 MNQ, 2 yrs REAL 1-min NQ from Polygon, Lucid rules,
1-min trend filter HTF_K=5, PIVOT_K=3, MIN_LEG=5, entry-sanity gate):
  ~16.0k trades / 68.2% win rate / +$622k net / max DD -$3.5k
  Monthly avg: ~$25.9k / Trades/mo: ~669 / PF: 1.98
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
# Strategy parameters — tuned from the 1-min + 5-min-trend backtest
# ---------------------------------------------------------------------------
PIVOT_K = 3                       # fractal swing-pivot lookback (1-min bars)
MIN_LEG_PTS = 15                  # minimum leg size for a tradeable swing
MAX_SETUP_AGE_BARS = 120          # 1-min bars (=~2 h) before setup expires
TARGET_REWARD_RATIO = 1.00        # full-pivot target (1:1 RR)
MAX_HOLD_1M_BARS = 480            # 8 h hard cap on a single trade
DEFAULT_SIZE = 5                  # MNQ contracts (5 MNQ for Lucid 50K Pro)
MIN_DYNAMIC_MNQ = 1               # floor for Lucid's suggested_n downscale

# Entry-sanity gate: when the trigger condition fires, the bot enters at
# the LATEST 1-min bar's CLOSE — but that close can be far past level50
# if price ripped through it inside the bar (a fast retrace + continuation).
# Without this gate, the bot fires SHORTs where entry is 1 pt away from
# the stop, which then takes 1 bar to stop out (the live -$15 / 6-sec
# trade the user flagged). We require the actual entry-to-stop distance
# to be at least MIN_ENTRY_RISK_FRAC of the swing leg — if not, this
# tick is skipped and the setup keeps watching for a better fill on a
# subsequent bar where price comes back into the valid retrace zone.
MIN_ENTRY_RISK_FRAC = 0.25        # entry must leave >= 25% of leg as risk-room

# HTF trend filter — same-timeframe (1-min) trend gate. The trend is
# defined by the most recent two major (k=HTF_PIVOT_K) pivots on the
# SAME 1-min bars used for setup detection, so the filter reacts at the
# same timescale as the setups. Backtest on real 1-min showed this
# variant (htf_k=30, no MSS) gives PF 1.43 vs PF 1.26 with the older
# 5-min trend + MSS layer, and avoids the "stale trend after V-bottom"
# case (a real example: bot took SHORT @ 29258 30 min into a recovery
# rally because the 5-min trend still showed DOWN; the new 1-min trend
# at k=30 catches the reversal in ~30 min and flips to UP first).
HTF_PIVOT_K = 5                   # major-pivot fractal on 1-min trend bars

# Chop filter — when the market is wiggling in a range with no
# directional progress, even the HTF trend filter passes (because the
# most recent pivots can still form an UP or DOWN pattern even in
# choppy conditions). The chop index measures net directional progress
# over the lookback window:
#     chop_index = |close[t] - close[t-N]| / (highest_high - lowest_low)
# Result is 0.0 (pure chop) to 1.0 (clean linear trend). Setups whose
# chop reading falls below the threshold are blocked. Backtested at
# CHOP_LOOKBACK_BARS=15 / CHOP_THRESHOLD=0.30 lifts PF 1.83 → 2.06 and
# reduces max drawdown by 23%, at the cost of ~30% fewer trades.
CHOP_LOOKBACK_BARS = 15
CHOP_THRESHOLD = 0.30

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
    # Timestamps of the bars where the pivot extremes were FORMED (not
    # the detection timestamp). The dashboard uses these to anchor the
    # historical stop/target line segments back to their source candles.
    pivot_high_ts: Optional[datetime] = None
    pivot_low_ts: Optional[datetime] = None
    used: bool = False
    # Sticky trigger / lifecycle tracking. The entry condition (price
    # touching level50) is evaluated on EVERY tick, including while another
    # trade is open, so a 50% touch that happens during another trade's
    # lifetime isn't lost. Once armed, the setup fires on the next tick
    # active_trade is None.
    entry_armed: bool = False
    fire_attempted: bool = False  # set True after first trigger-loop pass
    peak_high: float = -1e18      # max bar.high seen since detection
    peak_low: float = 1e18        # min bar.low seen since detection
    last_block_reason: Optional[str] = None
    last_block_at: Optional[datetime] = None

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

    def update_from_bar(self, bar: pd.Series) -> None:
        """Update peak high/low and arm the entry trigger if level50 was
        touched. Safe to call on every tick — including while another
        trade is open."""
        self.peak_high = max(self.peak_high, float(bar["high"]))
        self.peak_low = min(self.peak_low, float(bar["low"]))
        if not self.entry_armed:
            if self.side == "SHORT" and self.peak_high >= self.level50:
                self.entry_armed = True
            elif self.side == "LONG" and self.peak_low <= self.level50:
                self.entry_armed = True

    def target_reached(self) -> bool:
        if self.side == "LONG":
            return self.peak_high >= self.target_px
        return self.peak_low <= self.target_px

    def stop_reached(self) -> bool:
        if self.side == "LONG":
            return self.peak_low <= self.stop_px
        return self.peak_high >= self.stop_px

    def is_invalidated(self) -> bool:
        """Drop the setup from the watch list when its thesis is moot.

        Pre-arm (price never touched level50): invalidate as soon as
        target or stop is reached — the swing happened without us.

        Post-arm (level50 was touched but we haven't fired yet, e.g.
        because another trade was open or Lucid was blocking): give the
        setup at least one trigger-loop pass before allowing
        invalidation. Otherwise a wide bar that spans both level50 AND
        the target on the SAME tick would arm the setup and immediately
        invalidate it — we'd never get a fire attempt."""
        if self.used:
            return False
        if not self.fire_attempted:
            # Pre-arm: only invalidate if target/stop reached without a
            # 50% touch ever happening.
            if not self.entry_armed:
                return self.target_reached() or self.stop_reached()
            # Armed but not yet attempted (active_trade was open this
            # tick) — keep alive so next tick can fire.
            return False
        # We've had at least one fire attempt. Invalidate if price has
        # moved past target or stop in the meantime.
        return self.target_reached() or self.stop_reached()


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
    # Current 5-min HTF trend state: "UP", "DOWN", or "FLAT" (during a
    # transitional period between major pivots). Updated each tick from
    # the bars_5m series. Setups whose side disagrees with the trend are
    # filtered out at detection time.
    htf_trend: str = "FLAT"
    # Latest chop index reading (0.0 = pure chop, 1.0 = clean trend).
    # Recomputed each tick from the same 1-min bars used for trend.
    # Surfaced on the dashboard so you can see WHY a setup got blocked.
    chop_index: float = 0.0


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
    # Capture the timestamps of the pivot bars so we can later render
    # historical stop/target line segments anchored to those candles.
    try:
        pivot_high_ts = bars_10m.index[h_src].to_pydatetime() \
                         if hasattr(bars_10m.index[h_src], "to_pydatetime") \
                         else bars_10m.index[h_src]
        pivot_low_ts = bars_10m.index[l_src].to_pydatetime() \
                        if hasattr(bars_10m.index[l_src], "to_pydatetime") \
                        else bars_10m.index[l_src]
    except Exception:
        pivot_high_ts = pivot_low_ts = None
    return FibSetup(
        detected_at=now,
        side=side,
        pivot_high_val=h_val,
        pivot_low_val=l_val,
        pivot_high_ts=pivot_high_ts,
        pivot_low_ts=pivot_low_ts,
        level50=(h_val + l_val) / 2.0,
        expires_at=expires_at,
    )


def check_trigger(setup: FibSetup, last_bar: pd.Series) -> bool:
    """Has price retraced to the 50% level on the latest 1-min bar?"""
    if setup.side == "SHORT":
        return float(last_bar["high"]) >= setup.level50
    return float(last_bar["low"]) <= setup.level50


def compute_chop_index(bars: pd.DataFrame, lookback: int = CHOP_LOOKBACK_BARS
                        ) -> float:
    """Net directional progress vs total range over the last `lookback`
    bars. Returns 0.0 (pure chop, lots of range with no net move) to
    1.0 (clean linear trend). Used to gate setups: if the reading is
    below CHOP_THRESHOLD, the market is too choppy and the setup is
    blocked even when the HTF trend technically agrees with the side."""
    if len(bars) < lookback:
        return 0.0
    sub = bars.iloc[-lookback:]
    net = abs(float(sub["close"].iloc[-1]) - float(sub["close"].iloc[0]))
    rng = float(sub["high"].max()) - float(sub["low"].min())
    return net / rng if rng > 0 else 0.0


def compute_htf_trend(bars: pd.DataFrame) -> str:
    """Compute the current trend state from major (k=HTF_PIVOT_K) pivots
    on the SAME 1-min bars used for setup detection. Returns
    "UP" / "DOWN" / "FLAT".

    The last two confirmed major pivots set the leg direction.
    higher-low → higher-high = UP; lower-high → lower-low = DOWN.

    No MSS-style invalidation — the k=30 1-min fractals are already fast
    enough to flip after a reversal (~30 min), and the MSS layer
    backtested worse: it blocked profitable setups too aggressively
    (PF dropped from 1.43 to 1.26 across multiple parameter combos)."""
    if len(bars) < 2 * HTF_PIVOT_K + 1:
        return "FLAT"
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    n = len(bars)
    last_h_val = last_l_val = None
    last_h_src = last_l_src = -1
    for t in range(HTF_PIVOT_K, n - HTF_PIVOT_K):
        win = slice(t - HTF_PIVOT_K, t + HTF_PIVOT_K + 1)
        if h[t] == h[win].max():
            last_h_val = float(h[t]); last_h_src = t
        if l[t] == l[win].min():
            last_l_val = float(l[t]); last_l_src = t
    if last_h_val is None or last_l_val is None:
        return "FLAT"
    if last_h_src > last_l_src and last_h_val > last_l_val:
        return "UP"
    if last_l_src > last_h_src and last_l_val < last_h_val:
        return "DOWN"
    return "FLAT"


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
        # Levels + pivot anchor timestamps — dashboard uses these to draw
        # the historical entry/stop/target line segments after the trade.
        "stop_px": float(trade.stop_px),
        "target_px": float(trade.target_px),
        "pivot_high_ts": trade.setup.pivot_high_ts,
        "pivot_low_ts": trade.setup.pivot_low_ts,
    }


# ---------------------------------------------------------------------------
# Top-level tick — call this each time new 1-min bar data arrives
# ---------------------------------------------------------------------------
def on_new_1m_bar(state: FibStrategyState, lucid: LucidState,
                  bars_setup: pd.DataFrame, last_1m_bar: pd.Series,
                  now: datetime, n_mnq: int = DEFAULT_SIZE,
                  bars_trend: Optional[pd.DataFrame] = None
                  ) -> Optional[dict]:
    """Single entry point for the runtime. Pass the latest 1-min bar
    history (for setup detection), the latest live 1-min synth bar (for
    exit walking), the bot's clock, and the 5-min trend bars. Returns
    the closed trade dict if a trade just closed, else None.

    `bars_setup`: 1-min OHLCV history (used by detect_setup pivot scan).
    `bars_trend`: 5-min OHLCV history (used by compute_htf_trend). If
       None, the HTF filter is disabled (trades fire either direction).

    Side effects: mutates FibStrategyState (adds setups, opens/closes
    trades, updates rolling history, may trip circuit breaker, updates
    htf_trend)."""
    # circuit breaker is a hard stop
    check_circuit_breaker(state)
    if state.circuit_breaker_tripped:
        return None

    # Refresh 5-min HTF trend state + chop index once per tick. Setups
    # detected this tick will be filtered against both.
    if bars_trend is not None and not bars_trend.empty:
        state.htf_trend = compute_htf_trend(bars_trend)
        state.chop_index = compute_chop_index(bars_trend)

    # Update peak high/low and arm-state for ALL pending setups, EVERY
    # tick — even while another trade is open. This makes the entry
    # trigger sticky: a level50 touch that happens during another trade's
    # lifetime gets remembered and fires once active_trade clears.
    #
    # IMPORTANT: arming uses the most recent CLOSED 1-min bar from
    # bars_setup, NOT the live synthesized sub-minute bar. A sub-minute
    # wick that spikes through level50 then immediately retreats was
    # historically arming setups and firing trades that hit target in
    # 10-15 seconds — the user's "the bot is mistaking tiny choppy
    # price action for real 1-min Fib trades" observation. Using the
    # closed 1-min bar makes arming require an ACTUAL 1-min-bar close
    # whose high/low spans level50, not just an intra-bar wick.
    arming_bar = last_1m_bar
    if bars_setup is not None and not bars_setup.empty:
        try:
            arming_bar = bars_setup.iloc[-1]
        except Exception:
            arming_bar = last_1m_bar
    for setup in state.pending_setups:
        if setup.used:
            continue
        was_armed = setup.entry_armed
        setup.update_from_bar(arming_bar)
        if setup.entry_armed and not was_armed:
            logger.info("[ARMED] %s level50=%.2f (peak_h=%.2f peak_l=%.2f)",
                        setup.side, setup.level50,
                        setup.peak_high, setup.peak_low)

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

    # 2. detect new setup on closed 1-min bars
    new_setup = detect_setup(bars_setup, now)
    if new_setup is not None:
        key = _setup_key(new_setup)
        # HTF trend filter — LONG only when 1-min trend is UP, SHORT
        # only when DOWN. Backtested at HTF_PIVOT_K=5 with PF 1.98
        # (vs 1.52 without filter).
        if bars_trend is not None:
            if (state.htf_trend == "UP" and new_setup.side != "LONG") or \
               (state.htf_trend == "DOWN" and new_setup.side != "SHORT") or \
               (state.htf_trend == "FLAT"):
                logger.debug("[HTF-FILTER] %s setup rejected — trend=%s",
                             new_setup.side, state.htf_trend)
                new_setup = None
        # Chop filter — block setups when the market is wiggling in a
        # range with no directional progress (chop_index < threshold).
        # Backtested at CHOP_THRESHOLD=0.30: PF 1.83 → 2.06, DD reduced
        # 23%, at cost of ~30% fewer trades.
        if new_setup is not None and state.chop_index < CHOP_THRESHOLD:
            logger.debug("[CHOP-FILTER] %s setup rejected — chop=%.2f < %.2f",
                         new_setup.side, state.chop_index, CHOP_THRESHOLD)
            new_setup = None
        # Skip if we've recently fired on this exact pivot pair.
        # Prevents the "same setup re-fires on every tick" loop where
        # the bot keeps re-detecting the same h_val/l_val until new
        # pivots form on the chart.
        if new_setup is not None and key in state.recent_used_setups:
            new_setup = None
        elif new_setup is not None and any(
                s.side == new_setup.side
                and abs(s.level50 - new_setup.level50) < 0.5
                for s in state.pending_setups if not s.used):
            # already in pending list as well
            new_setup = None
        elif new_setup is not None:
            # Seed extremes with the bar that detected the setup, so a
            # setup that's confirmed AT a level50 touch (the pivot was
            # k=5 bars ago, price has since moved) arms immediately.
            new_setup.update_from_bar(last_1m_bar)
            state.pending_setups.append(new_setup)
            logger.debug("[SETUP] %s level50=%.2f leg=%.1fpts armed=%s htf=%s",
                         new_setup.side, new_setup.level50,
                         new_setup.leg_pts, new_setup.entry_armed,
                         state.htf_trend)

    # 3. expire stale setups + drop pre-entry invalidations (price already
    #    reached target or stop without us ever firing).
    fresh: list[FibSetup] = []
    for s in state.pending_setups:
        if s.used or s.expires_at <= now:
            continue
        if s.is_invalidated():
            why = "target" if s.target_reached() else "stop"
            logger.info("[INVALID] %s level50=%.2f — price reached %s "
                        "before entry (peak_h=%.2f peak_l=%.2f tgt=%.2f "
                        "stop=%.2f)", s.side, s.level50, why,
                        s.peak_high, s.peak_low, s.target_px, s.stop_px)
            continue
        fresh.append(s)
    state.pending_setups = fresh

    # 4. fire any armed setup. We iterate every tick (not just the bar a
    #    setup arms on) so Lucid blocks naturally retry until the setup
    #    fires, invalidates, or expires.
    for setup in state.pending_setups:
        if not setup.entry_armed:
            continue
        setup.fire_attempted = True   # gate post-arm invalidation
        # Re-check HTF trend + chop AT FIRE TIME, not just at detection.
        # Otherwise a setup detected during clean trend conditions can
        # wait in pending_setups for minutes, and fire later when
        # conditions have deteriorated to chop or the trend has flipped
        # against the setup's side. The chop filter shipped earlier was
        # only running at detect time — this closes the gap.
        if bars_trend is not None:
            tr = state.htf_trend
            if (tr == "UP" and setup.side != "LONG") or \
               (tr == "DOWN" and setup.side != "SHORT") or \
               (tr == "FLAT"):
                logger.debug("[HTF-FILTER@fire] %s blocked — trend now %s",
                             setup.side, tr)
                continue
        if state.chop_index < CHOP_THRESHOLD:
            logger.debug("[CHOP-FILTER@fire] %s blocked — chop=%.2f < %.2f",
                         setup.side, state.chop_index, CHOP_THRESHOLD)
            continue
        # Lucid pre-check — try the default size first. If Lucid rejects
        # but suggests a smaller fittable size (e.g. wide stop pushes
        # default size past DLL room), retry at that size. This converts
        # blocked-too-big-trades into smaller-but-firing trades — the
        # `suggested_n` fix the backtest showed was already +5-15% P&L.
        size_to_use = n_mnq
        decision = lucid_precheck(setup, size_to_use, lucid)
        if not decision.allowed and decision.suggested_n >= MIN_DYNAMIC_MNQ \
                and decision.suggested_n < size_to_use:
            shrunk = decision.suggested_n
            decision_shrunk = lucid_precheck(setup, shrunk, lucid)
            if decision_shrunk.allowed:
                logger.info("[AUTO-SIZED] %s %d MNQ -> %d MNQ (reason: %s)",
                            setup.side, size_to_use, shrunk, decision.reason)
                size_to_use = shrunk
                decision = decision_shrunk
        if not decision.allowed:
            # DON'T mark used — Lucid limits can shift across the day
            # (DLL window, trail-floor changes). Setup keeps retrying on
            # subsequent ticks until it fires, gets invalidated by price,
            # or expires. Surface the block reason on the dashboard.
            if decision.reason != setup.last_block_reason:
                logger.info("[BLOCKED] %s level50=%.2f reason=%s",
                            setup.side, setup.level50, decision.reason)
            setup.last_block_reason = decision.reason
            setup.last_block_at = now
            continue
        # entry at this bar's close — closest realistic fill
        entry_px = float(last_1m_bar["close"])
        # Entry-sanity gate: if price has already ripped past level50 toward
        # the stop, the trade has almost no risk-room and gets stopped out
        # in the next bar (the user's -$15/6-sec SHORT case). Skip this
        # tick — DON'T mark used, so the setup keeps watching. If price
        # retraces back into the valid zone we'll fire properly; if it
        # never does, the setup expires or invalidates safely with no
        # trade.
        actual_risk = abs(setup.stop_px - entry_px)
        min_risk = setup.leg_pts * MIN_ENTRY_RISK_FRAC
        if actual_risk < min_risk:
            logger.info("[SKIP-TICK] %s level50=%.2f — entry %.2f only "
                        "%.1fpts from stop %.2f (min %.1fpts = %.0f%% of "
                        "leg %.1fpts); waiting for better fill",
                        setup.side, setup.level50, entry_px, actual_risk,
                        setup.stop_px, min_risk,
                        MIN_ENTRY_RISK_FRAC * 100, setup.leg_pts)
            continue
        new_trade = open_trade(setup, size_to_use, entry_px, now)
        if new_trade is None:
            # geometry guard tripped — already logged; this is structural,
            # mark used so we don't keep retrying.
            setup.used = True
            state.recent_used_setups.append(_setup_key(setup))
            continue
        state.active_trade = new_trade
        setup.used = True
        state.recent_used_setups.append(_setup_key(setup))
        logger.info("[OPEN] %s %d MNQ @ %.2f  stop=%.2f tgt=%.2f  htf=%s",
                    setup.side, size_to_use, entry_px,
                    setup.stop_px, setup.target_px, state.htf_trend)
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
            "entry_armed": s.entry_armed,
            "last_block_reason": s.last_block_reason,
            "last_block_at": s.last_block_at.isoformat()
                if s.last_block_at and hasattr(s.last_block_at, "isoformat")
                else None,
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
        "htf_trend": state.htf_trend,
        "chop_index": state.chop_index,
        "chop_threshold": CHOP_THRESHOLD,
        "setup_timeframe": "1min",
        "trend_timeframe": "1min",
    }

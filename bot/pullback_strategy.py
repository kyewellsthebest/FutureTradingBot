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
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional

import pandas as pd

from research.lucid_guard import LucidState, GuardDecision

logger = logging.getLogger("pullback_strategy")

# Env override: BOT_HTF_TREND_FILTER=0 disables the HTF trend gate entirely.
# Use when the filter is wedging trades (e.g. choppy days where pivots flip
# every few bars and reject every setup direction). Default ON.
_HTF_FILTER_ENV = os.environ.get("BOT_HTF_TREND_FILTER", "1") != "0"
# Fractal-pivot half-window for HTF trend on 1-min bars. Design intent was
# k=30 (~30 min trend confirmation) per the fib_main comment; was previously
# hardcoded to 5, which made the trend flip on every minor wiggle and gated
# 100% of setups on chop days. Override with BOT_HTF_K env var.
_HTF_K = int(os.environ.get("BOT_HTF_K", "30"))


# -------- Slippage / spread modeling for paper P&L --------
# Paper traditionally assumed exit at the exact stop_px and zero spread
# cost. Broker reality:
#   - STOP fills are stop-MARKET on touch -> next available bid/ask,
#     consistently 0.25-1pt against the trader on MNQ during liquid
#     hours; worse around news.
#   - TARGET fills are LIMIT -> at the target level or better
#     (queue priority matters but no slip).
#   - Every entry pays half-spread (we cross the book by taking the
#     opposite side) and every market exit pays half-spread too.
# Default values are conservative -- override via env if your historical
# fills show different numbers. Set both to 0 to restore the legacy
# zero-cost paper model.
PAPER_STOP_SLIP_PTS = float(
    os.environ.get("PAPER_STOP_SLIP_PTS", "0.5"))
PAPER_SPREAD_PTS = float(
    os.environ.get("PAPER_SPREAD_PTS", "0.0"))


def _read_slip_override() -> Optional[float]:
    """If the dashboard's Apply button wrote a slip_override.json into
    the account data dir, prefer it over the env var. Lets the user
    auto-tune without a Railway redeploy."""
    try:
        from bot.account_ctx import data_dir as _acct_dir
        p = _acct_dir() / "slip_override.json"
        if p.exists():
            import json as _json
            d = _json.loads(p.read_text())
            v = d.get("PAPER_STOP_SLIP_PTS")
            if v is not None:
                return float(v)
    except Exception:
        pass
    return None


def get_effective_stop_slip() -> float:
    """Resolve the effective stop-slip value: override file > env var."""
    ov = _read_slip_override()
    return ov if ov is not None else PAPER_STOP_SLIP_PTS


# -------- Decision log (entry block / fire reasons) --------
# Every setup outcome (detected, blocked, fired, expired) gets a row
# here with full snapshot. The dashboard bundle exports this so we can
# see WHY each potential trade did or didn't happen.
_DECISION_LOG: "deque[dict]" = deque(maxlen=500)


def _log_decision(event: str, **fields) -> None:
    import time as _t
    _DECISION_LOG.append({
        "ts": _t.time(), "event": event, **fields,
    })


def get_decision_log() -> list:
    return list(_DECISION_LOG)


# ============================================================================
# Strategy parameters (validated OOS-positive on NQ tick data + 24-mo OHLC)
#
# Bake-off vs 5 candidate strategies showed wider targets dominate.
# Updated TARGET_PTS 12 -> 18 after the strategy_bakeoff_tick.py sweep.
#
# Full 3-month tick sim @ Lucid costs ($0.74 RT, 0.25pt adv slip), 2 MNQ:
#   +27.06%/mo, 1.75% max DD, PF 1.30, RR 2.19, WR 37.3%, 7,286 trades
#
# OOS split-half (40d train / 40d val) at target=18:
#   train +18.01%/mo (1.75% DD), val +36.18%/mo (1.59% DD)
#   -- beats target=12 baseline on BOTH halves, not overfit
#
# Monte Carlo (1000 resamples) at target=18:
#   median +27.04%/mo, 5-95% [+22.67, +31.76]
#   P(positive)=100%, P(>=10%)=100%, P(>=20%)=99.6%
#   P(blow $2K trail)=0.2%  (was 0.1% at target=12, negligible change)
# ============================================================================
DEFAULT_SIZE = 1                  # 1 MNQ default for live -- conservative; bump via FIB_N_MNQ env if scaling on a funded account
IMPULSE_PTS = 5.0                 # min net move (in NQ pts) over IMPULSE_WINDOW_BARS
IMPULSE_WINDOW_BARS = 4           # impulse measured across last 4 closed 1-min bars
PULLBACK_PCT = 0.618              # 61.8% retracement of impulse range
STOP_PTS = 6.0                    # stop distance from entry (NQ pts)
TARGET_PTS = 18.0                 # target distance from entry (NQ pts) -- widened
                                  # from 12 after bake-off; lets winners run further
MAX_HOLD_SECS = 600               # 10 minutes max in trade
MAX_WAIT_SECS = 300               # pullback setup expires if not filled in 5 min
COOLDOWN_SECS = 60                # min gap between trades
MIN_TARGET_HOLD_SECONDS = 10      # Lucid microscalp safety: target exits < 10s become "instant scalp"
MICROSCALP_HARD_THRESHOLD = 0.40  # circuit breaker if >40% of recent trades < MIN_TARGET_HOLD_SECONDS
MICROSCALP_WINDOW_DAYS = 30

# MNQ futures tick is 0.25. All entry/stop/target prices MUST be tick-
# aligned or paper and broker will disagree on every fill: paper marks
# itself filled when price taps the raw float (e.g. 29683.287), while
# the broker LIMIT sits at the nearest tick (29683.25 or 29683.50) and
# only fills there. That ~0.04-0.20pt offset compounds across 200 trades
# into the paper-vs-broker leak the user is seeing.
TICK_SIZE = 0.25


def _tick_round(px: float, side: str, role: str) -> float:
    """Round a price to MNQ's 0.25 tick.

    role determines rounding direction so the trade is no easier than
    intended:
      - entry: round AWAY from current (toward the move) so the LIMIT
        fills no easier than the strategy planned. LONG entry rounds
        DOWN (price has to come further to fill); SHORT rounds UP.
      - stop: round TOWARD the entry (smaller risk) so we never have
        wider stop than designed. LONG stop rounds UP, SHORT rounds DOWN.
      - target: round AWAY from entry (more profit needed) so we never
        take a smaller target than designed. LONG target rounds UP,
        SHORT rounds DOWN.
    """
    import math
    n = float(px) / TICK_SIZE
    if role == "entry":
        # Make entry harder to fill (toward fill direction)
        n = math.floor(n) if side == "LONG" else math.ceil(n)
    elif role == "stop":
        # Make stop tighter (toward entry)
        n = math.ceil(n) if side == "LONG" else math.floor(n)
    elif role == "target":
        # Make target wider (away from entry)
        n = math.ceil(n) if side == "LONG" else math.floor(n)
    else:
        n = round(n)
    return round(n * TICK_SIZE, 2)

# Lucid Allowed Trading Times -- per Lucid Help Center:
#   "All positions must be closed by 4:45 PM EST, Monday through Friday"
#   "Trading resumes at 6:00 PM EST, Sunday through Thursday"
# We block new ENTRIES during the closed window. Existing positions ride
# out: MAX_HOLD_SECS = 600s means anything we open in the last 10 min
# before 4:45 PM ET would naturally exit before Lucid's auto-close, and
# Lucid explicitly says "holding a position past this time does not result
# in a failed account" -- they handle the auto-close, no penalty to us.
# So the simplest correct gate is: block entries inside the closed window.


# News blackout: TIGHT window around the big macro releases that move NQ
# 20-50pts in seconds (CPI, FOMC, NFP, PCE, GDP, Powell speeches, ISM,
# Retail Sales). The 6pt stop is meaningless against that kind of shock --
# a stop-market gets filled wherever the next ask lands, often 15-30pts
# adverse. One blown stop into CPI = 5+ regular losses.
#
# Window: 5 min pre, 15 min post. The 5-min pre window catches the
# pre-release algo positioning; the 15-min post window covers the
# fast-thin-spread aftermath while still letting us trade most of the day.
NEWS_PRE_MIN = 5
NEWS_POST_MIN = 15


def _news_blackout_reason(now: datetime, calendar) -> Optional[str]:
    """Returns a string reason if `now` is inside a news blackout window
    around a blackout-worthy event, else None. Fail-open on any error --
    a calendar fetch failure should never stop the bot from trading."""
    if calendar is None:
        return None
    try:
        upcoming = calendar.next_event_within(
            now, minutes=NEWS_PRE_MIN, only_blackout=True)
        if upcoming is not None:
            mins = upcoming.minutes_until(now)
            return f"news_pre:{upcoming.title}@{mins:.1f}min"
        # Post-event window: look back for any blackout-worthy events
        # in the last NEWS_POST_MIN minutes.
        recent = calendar.upcoming(
            now - timedelta(minutes=NEWS_POST_MIN), hours=1,
            only_blackout=True)
        passed = [e for e in recent if e.ts <= now]
        if passed:
            most_recent = max(passed, key=lambda e: e.ts)
            mins_since = (now - most_recent.ts).total_seconds() / 60.0
            if mins_since <= NEWS_POST_MIN:
                return f"news_post:{most_recent.title}@{mins_since:.1f}min"
    except Exception:
        return None
    return None


def _in_lucid_closed_window(now: datetime) -> bool:
    """True if `now` falls inside the broker's no-trade window.

    Two modes (selected via BOT_TRADING_HOURS env var):

      "cme" (DEFAULT)     -- respects only real CME futures hours:
        - Mon-Thu 17:00 ET to 18:00 ET   (1hr daily maintenance break)
        - Fri 17:00 ET through Sun 18:00 ET  (weekend close)

      "lucid"             -- Lucid funded-account stricter rules:
        - Mon-Thu 16:45 ET to 18:00 ET   (15min buffer before CME close)
        - Fri 16:45 ET through Sun 18:00 ET  (weekend close, 15min buffer)

      "always_open"       -- never blocks; trust whatever the broker accepts

    User explicitly moved off Lucid funded to a personal Tradovate
    demo account. CME hours are the real constraint, not Lucid's. The
    bundle diagnostic showed 6+ hours of setups blocked by Lucid mode
    even though personal Tradovate would have accepted them.

    Returns False if outside the closed window (open for entries).
    """
    import os as _os
    mode = _os.environ.get("BOT_TRADING_HOURS", "cme").lower()
    if mode == "always_open":
        return False
    try:
        ny = pd.Timestamp(now).tz_convert("America/New_York")
    except Exception:
        return False  # if tz handling fails, don't block (fail-open)
    dow = ny.weekday()   # 0=Mon ... 6=Sun
    hm = ny.hour * 60 + ny.minute
    OPEN = 18 * 60          # 18:00 ET = market open
    if mode == "lucid":
        CLOSE = 16 * 60 + 45    # 16:45 ET = Lucid mandatory close
    else:                       # "cme" default
        CLOSE = 17 * 60         # 17:00 ET = real CME daily close
    if dow == 5:                          # Saturday
        return True
    if dow == 4 and hm >= CLOSE:          # Friday after close
        return True
    if dow == 6 and hm < OPEN:            # Sunday before 18:00 ET
        return True
    if dow <= 3 and CLOSE <= hm < OPEN:   # Mon-Thu in the daily break
        return True
    return False


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
    # Post-streak circuit-breaker state (optional, governed by params).
    # Tracks consecutive losses; when threshold hit, blocks new entries
    # until pause_until_ts. Reset on any winning trade.
    consecutive_losses: int = 0
    pause_until_ts: Optional[datetime] = None


# ============================================================================
# Setup detection from last N closed bars
# ============================================================================
def _compute_htf_trend(bars: pd.DataFrame, htf_k: int = 5) -> str:
    """Trend state from the last two confirmed major (k=htf_k) fractal
    pivots. Ported from bot/fib_strategy.compute_htf_trend.

    Returns "UP" (higher-low followed by higher-high),
    "DOWN" (lower-high followed by lower-low), or "FLAT" (no clear
    structure or insufficient bars).

    Backtest improvement when wired into pullback strategy: PF 1.52 ->
    1.98. Cuts the counter-trend losing trades that were dominating
    bad regimes.
    """
    if bars is None or len(bars) < 2 * htf_k + 1:
        return "FLAT"
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    n = len(bars)
    last_h_val = last_l_val = None
    last_h_src = last_l_src = -1
    for t in range(htf_k, n - htf_k):
        win = slice(t - htf_k, t + htf_k + 1)
        if h[t] == h[win].max():
            last_h_val = float(h[t])
            last_h_src = t
        if l[t] == l[win].min():
            last_l_val = float(l[t])
            last_l_src = t
    if last_h_val is None or last_l_val is None:
        return "FLAT"
    if last_h_src > last_l_src and last_h_val > last_l_val:
        return "UP"
    if last_l_src > last_h_src and last_l_val < last_h_val:
        return "DOWN"
    return "FLAT"


def detect_pullback_setup(bars: pd.DataFrame, now: datetime,
                          params: Optional[dict] = None
                          ) -> Optional[FibSetup]:
    """Look at last IMPULSE_WINDOW_BARS closed bars; if their net move
    >= IMPULSE_PTS, return a pending pullback setup. Else None.

    `params` overrides the module-level defaults so different accounts
    can run different strategy params side-by-side. Expected keys:
    IMPULSE_PTS, IMPULSE_WINDOW_BARS, PULLBACK_PCT, STOP_PTS, TARGET_PTS.
    Optional:
      STRONG_TREND_LOOKBACK_BARS (e.g. 240 = 4h)
      STRONG_TREND_THRESHOLD_PTS (e.g. 80) -- if last lookback bars'
        close-vs-close move exceeds this, treat as "strong trend" and
        widen the COUNTER-TREND stop (not with-trend) so the strategy
        doesn't get whipped out as fast during sustained directional
        moves. Validated +28%/mo, lower DD than baseline.
      STOP_PTS_COUNTER_TREND (e.g. 10.0) -- the wider stop used when
        the new setup opposes the current strong-trend bias.
    """
    p = params or {}
    imp_pts    = p.get("IMPULSE_PTS",        IMPULSE_PTS)
    imp_window = p.get("IMPULSE_WINDOW_BARS", IMPULSE_WINDOW_BARS)
    pull_pct   = p.get("PULLBACK_PCT",       PULLBACK_PCT)
    stop_pts   = p.get("STOP_PTS",           STOP_PTS)
    tgt_pts    = p.get("TARGET_PTS",         TARGET_PTS)
    # Trend-aware stop widening (optional)
    trend_lb   = p.get("STRONG_TREND_LOOKBACK_BARS")
    trend_thr  = p.get("STRONG_TREND_THRESHOLD_PTS")
    counter_stop_pts = p.get("STOP_PTS_COUNTER_TREND")

    if bars is None or len(bars) < imp_window:
        return None
    window = bars.iloc[-imp_window:]
    net = float(window["close"].iloc[-1]) - float(window["open"].iloc[0])
    if abs(net) < imp_pts:
        return None
    impulse_high = float(window["high"].max())
    impulse_low = float(window["low"].min())
    impulse_range = impulse_high - impulse_low
    if impulse_range <= 0:
        return None

    side = "LONG" if net > 0 else "SHORT"

    # Compute strong-trend bias if configured. If the setup direction
    # opposes the current trend, use the wider counter-trend stop so the
    # trade survives intra-trend whipsaws.
    effective_stop_pts = stop_pts
    if (trend_lb is not None and trend_thr is not None
            and counter_stop_pts is not None and len(bars) >= trend_lb):
        try:
            c_arr = bars["close"].to_numpy()
            trend_net = float(c_arr[-1] - c_arr[-trend_lb])
            if abs(trend_net) >= float(trend_thr):
                trend_dir = "LONG" if trend_net > 0 else "SHORT"
                if trend_dir != side:
                    effective_stop_pts = float(counter_stop_pts)
        except Exception:
            pass

    if side == "LONG":
        pullback_entry = impulse_high - pull_pct * impulse_range
        stop_px = pullback_entry - effective_stop_pts
        target_px = pullback_entry + tgt_pts
    else:
        pullback_entry = impulse_low + pull_pct * impulse_range
        stop_px = pullback_entry + effective_stop_pts
        target_px = pullback_entry - tgt_pts

    # Tick-align so paper and broker agree on fill levels. Without this,
    # paper fills at the raw float (e.g. 29683.287) but the broker LIMIT
    # sits at 29683.25 -- they fill at different times and prices. This
    # is one of the biggest paper-vs-broker divergence sources.
    pullback_entry = _tick_round(pullback_entry, side, "entry")
    stop_px = _tick_round(stop_px, side, "stop")
    target_px = _tick_round(target_px, side, "target")

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
    """% of recent target-exit trades that closed in < MIN_TARGET_HOLD_SECONDS.

    Reads the persistent trades DB instead of the in-memory completed_trades
    deque -- the latter was empty after every bot restart, so the dashboard
    gauge was stuck at 0% even after thousands of live trades. (Bug spotted
    by user on May 25.)"""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MICROSCALP_WINDOW_DAYS)
    try:
        from bot import persistence
        # Pull every target exit in the lookback window. We avoid loading
        # losing trades because Lucid's rule only counts profitable scalps.
        sql_cutoff = cutoff.isoformat()
        with persistence._conn() as conn:
            rows = conn.execute(
                """SELECT exit_reason, exit_time, entry_time, pnl
                   FROM trades
                   WHERE exit_time IS NOT NULL
                     AND exit_time >= ?
                     AND exit_reason = 'target'""",
                (sql_cutoff,)
            ).fetchall()
        targets = [dict(r) for r in rows]
    except Exception:
        # Fall back to in-memory deque (older code path) if DB unreachable
        targets = [t for t in (completed or [])
                   if t.get("exit_reason") == "target"
                   and pd.to_datetime(t.get("exit_ts", t.get("entry_ts"))).to_pydatetime()
                       > cutoff]
    if not targets: return 0.0
    def _hold_s(t: dict) -> float:
        # Persisted rows give entry/exit timestamps; in-memory rows give hold_s.
        if t.get("hold_s") is not None:
            return float(t["hold_s"])
        try:
            et = pd.to_datetime(t.get("entry_time") or t.get("entry_ts"))
            xt = pd.to_datetime(t.get("exit_time") or t.get("exit_ts"))
            return (xt - et).total_seconds()
        except Exception:
            return 999.0
    scalps = sum(1 for t in targets if _hold_s(t) < MIN_TARGET_HOLD_SECONDS)
    return scalps / len(targets)


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
      - STOPS fire IMMEDIATELY -- losses are NOT subject to microscalp
        rule (Lucid only counts profitable trades held <=5s).
        Cutting losses fast is good risk management.
      - TARGETS require >= MIN_TARGET_HOLD_SECONDS (10s) of hold time.
        Lucid's microscalp threshold is 5s; we use 10s as safety buffer.
      - TIMEOUTS naturally past 10s (10-min max hold).

    LOOK-AHEAD BIAS GUARD: skip exit detection on bars that started AT
    OR BEFORE the trade was opened. The entry bar's high/low includes
    ticks from BEFORE the entry, which would otherwise let the bot
    falsely "detect" a stop/target hit that actually happened pre-entry.
    This was inflating paper-account wins and causing the dashboard to
    show ~10-15s trade durations while Tradovate's real-time bracket
    saw the trade play out differently. With this guard, exits only
    fire on bars that started AFTER the entry timestamp.
    """
    try:
        bar_start = last_1m_bar.name
        if hasattr(bar_start, "to_pydatetime"):
            bar_start = bar_start.to_pydatetime()
        if bar_start.tzinfo is None:
            bar_start = bar_start.replace(tzinfo=timezone.utc)
        if bar_start <= trade.entry_ts:
            return None
    except Exception:
        # If bar timestamp parsing fails, fall through to exit check.
        pass

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
    # Effective fill = bracket level, ADJUSTED for the broker realities
    # paper has historically ignored. This makes paper P&L track broker
    # P&L far more tightly. Set the env vars to 0 to disable.
    adj_exit_px = exit_px
    slip_value = get_effective_stop_slip()
    if reason == "stop" and slip_value > 0:
        # Stop-market triggers at stop_px then fills at the NEXT bid/ask.
        # That fill is always WORSE than stop_px on the trader's side.
        if trade.side == "LONG":
            adj_exit_px = exit_px - slip_value
        else:
            adj_exit_px = exit_px + slip_value
    if reason == "timeout" and PAPER_SPREAD_PTS > 0:
        # Timeout exit is a flatten MARKET -> pays half-spread.
        half = PAPER_SPREAD_PTS / 2.0
        if trade.side == "LONG":
            adj_exit_px = exit_px - half
        else:
            adj_exit_px = exit_px + half
    pnl_pts = (trade.entry_px - adj_exit_px) if trade.side == "SHORT" \
              else (adj_exit_px - trade.entry_px)
    # Every entry pays half-spread (we crossed to take the LIMIT).
    # Skip for target exits since the LIMIT fills at the level by def.
    spread_cost_pts = 0.0
    if PAPER_SPREAD_PTS > 0:
        spread_cost_pts = PAPER_SPREAD_PTS / 2.0  # entry side only
    pnl_pts -= spread_cost_pts
    pnl_usd = pnl_pts * trade.n_mnq * 2.0   # $2/pt per MNQ; commissions
                                            # handled in the account layer
    return {
        "ts": now,  # alias for exit_ts -- dashboard publish uses t.get("ts")
        "entry_ts": trade.entry_ts, "exit_ts": now,
        "side": trade.side, "n_mnq": trade.n_mnq,
        "entry_px": trade.entry_px, "exit_px": exit_px,
        "adj_exit_px": adj_exit_px,
        "slip_pts": round(abs(adj_exit_px - exit_px), 4),
        "spread_cost_pts": spread_cost_pts,
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
                  bars_trend: Optional[pd.DataFrame] = None,
                  params: Optional[dict] = None,
                  calendar=None,
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
            # Post-streak circuit breaker: track consecutive losses; pause
            # entries after N in a row. Reset on any winning trade.
            n_losses_trip = (params or {}).get("POST_STREAK_LOSSES")
            pause_mins    = (params or {}).get("POST_STREAK_PAUSE_MINS")
            if n_losses_trip is not None and pause_mins is not None:
                if record["pnl_usd"] < 0:
                    state.consecutive_losses += 1
                    if state.consecutive_losses >= int(n_losses_trip):
                        from datetime import timedelta
                        state.pause_until_ts = now + timedelta(minutes=int(pause_mins))
                        logger.warning(f"[STREAK BREAK] {state.consecutive_losses} consecutive losses — "
                                       f"pausing new entries until {state.pause_until_ts.isoformat()}")
                        state.consecutive_losses = 0   # arm again after pause
                else:
                    state.consecutive_losses = 0
            logger.info("[CLOSE] %s pnl=$%.2f hold=%.1fs reason=%s",
                        record["side"], record["pnl_usd"],
                        record["hold_s"], record["exit_reason"])
            return record
        return None

    # 2a. Cooldown gate (no new entries until COOLDOWN_SECS after last close)
    in_cooldown = (state.last_trade_close_ts is not None and
                   (now - state.last_trade_close_ts).total_seconds() < COOLDOWN_SECS)
    # 2b. Lucid trading-window gate (no entries during 16:45-18:00 ET daily
    # break, or Fri 16:45 ET through Sun 18:00 ET weekend close). Existing
    # positions are NOT force-closed here -- Lucid handles their 16:45 auto-
    # close with no penalty per their rules.
    lucid_blocked = _in_lucid_closed_window(now)

    # 2b'. News blackout gate -- block entries 5 min before / 15 min after
    # blackout-worthy USD events (CPI, FOMC, NFP, PCE, GDP, Powell speeches,
    # ISM, Retail Sales, etc.). Stop-market fills during these releases can
    # turn a routine 6pt stop into a 20-30pt slip; one bad release wipes
    # 5+ regular trades' worth of edge.
    news_blackout = _news_blackout_reason(now, calendar)

    # 2c. ATR regime filter (params["MIN_ATR"]). Worst-day forensics found
    # baseline LOSES money predominantly on low-ATR drift days (ATR < 3).
    # Skipping setup detection when ATR < threshold drops max DD ~15%
    # without sacrificing return (-0.08%). OOS-validated on both halves.
    #
    # ALSO: vol-ratio filter (params["MIN_VOL_RATIO"]). When the recent
    # 5-bar ATR is significantly smaller than the 60-bar ATR (< 0.5x), it
    # indicates the "calm before the storm" -- volatility is collapsing,
    # which historically precedes losing trades (69.6% loss rate vs 63%
    # baseline, NEGATIVE total P&L). Skip these entries.
    atr_blocked = False
    min_atr = (params or {}).get("MIN_ATR")
    min_vol_ratio = (params or {}).get("MIN_VOL_RATIO")
    if (min_atr is not None or min_vol_ratio is not None) and \
            bars_setup is not None and len(bars_setup) >= 60:
        h_arr = bars_setup["high"].to_numpy()
        l_arr = bars_setup["low"].to_numpy()
        c_arr = bars_setup["close"].to_numpy()
        import numpy as _np
        # 14-bar ATR
        h14 = h_arr[-15:]; l14 = l_arr[-15:]; c14 = c_arr[-15:]
        tr14 = _np.maximum.reduce([h14 - l14,
                                    _np.abs(h14 - _np.r_[c14[0], c14[:-1]]),
                                    _np.abs(l14 - _np.r_[c14[0], c14[:-1]])])
        atr14_now = float(tr14[1:].mean())
        if min_atr is not None and atr14_now < float(min_atr):
            atr_blocked = True
        # Vol-ratio: 5-bar ATR / 60-bar ATR
        if not atr_blocked and min_vol_ratio is not None:
            h5 = h_arr[-6:]; l5 = l_arr[-6:]; c5 = c_arr[-6:]
            tr5 = _np.maximum.reduce([h5 - l5,
                                       _np.abs(h5 - _np.r_[c5[0], c5[:-1]]),
                                       _np.abs(l5 - _np.r_[c5[0], c5[:-1]])])
            atr5_now = float(tr5[1:].mean())
            h60 = h_arr[-61:]; l60 = l_arr[-61:]; c60 = c_arr[-61:]
            tr60 = _np.maximum.reduce([h60 - l60,
                                        _np.abs(h60 - _np.r_[c60[0], c60[:-1]]),
                                        _np.abs(l60 - _np.r_[c60[0], c60[:-1]])])
            atr60_now = float(tr60[1:].mean())
            if atr60_now > 0 and (atr5_now / atr60_now) < float(min_vol_ratio):
                atr_blocked = True

    # 2d. HTF TREND FILTER -- port of the fib_strategy filter that
    # backtested at PF 1.98 vs 1.52 without (30% improvement). The
    # pullback strategy was firing both LONG and SHORT setups regardless
    # of prevailing trend, causing counter-trend setups to get repeatedly
    # stopped in trending markets. This filter:
    #   - LONG setups only fire when 1-min trend is UP
    #   - SHORT setups only fire when 1-min trend is DOWN
    #   - FLAT trend: skip everything (chop kills pullback strategy)
    # Computed from the most recent two confirmed major pivots (k=5
    # fractal on the bars_trend series). Toggleable via params for A/B.
    htf_trend = "FLAT"
    htf_filter_enabled = (
        bool((params or {}).get("HTF_TREND_FILTER", True))
        and _HTF_FILTER_ENV
    )
    # The filter can only apply when bars_trend has enough history for
    # the k-period fractal pivot scan. During warmup (e.g. WS-built
    # bars are still accumulating) we don't have enough -- in that
    # case, BYPASS the filter rather than letting htf_trend stay FLAT
    # and reject every setup. Without this bypass the strategy never
    # fires until 2*HTF_K+1 bars exist (~61 min on a fresh restart).
    htf_history_ready = (bars_trend is not None
                         and len(bars_trend) >= 2 * _HTF_K + 1)
    if htf_filter_enabled and htf_history_ready:
        htf_trend = _compute_htf_trend(bars_trend, htf_k=_HTF_K)
        state.htf_trend = htf_trend  # surface to dashboard

    # 3. DETECT new setup from latest 1-min bar history
    new_setup = None if atr_blocked else detect_pullback_setup(bars_setup, now, params=params)
    if new_setup is not None and htf_filter_enabled and htf_history_ready:
        # HTF trend filter: require setup direction to MATCH the trend.
        # FLAT trend means no setups (chop is poison for pullbacks).
        if (htf_trend == "UP" and new_setup.side != "LONG") or \
           (htf_trend == "DOWN" and new_setup.side != "SHORT") or \
           (htf_trend == "FLAT"):
            logger.info("[HTF-FILTER] %s setup rejected -- trend=%s",
                        new_setup.side, htf_trend)
            new_setup = None
    elif new_setup is not None and htf_filter_enabled and not htf_history_ready:
        n_bars = len(bars_trend) if bars_trend is not None else 0
        logger.info(f"[HTF-FILTER bypass] insufficient bars "
                    f"({n_bars}/{2*_HTF_K+1}); allowing setup through")
    if new_setup is not None:
        key = _setup_key(new_setup)
        # dedup against recent + pending
        already = (key in state.recent_used_setups or
                   any(_setup_key(s) == key for s in state.pending_setups if not s.used))
        if already:
            _log_decision("setup_dedup",
                           side=new_setup.side,
                           pullback_entry=new_setup.pullback_entry,
                           stop_px=new_setup.stop_px_val,
                           target_px=new_setup.target_px_val,
                           htf_trend=htf_trend)
        if not already:
            state.pending_setups.append(new_setup)
            _log_decision("setup_detected",
                           side=new_setup.side,
                           impulse_high=new_setup.impulse_high,
                           impulse_low=new_setup.impulse_low,
                           pullback_entry=new_setup.pullback_entry,
                           stop_px=new_setup.stop_px_val,
                           target_px=new_setup.target_px_val,
                           htf_trend=htf_trend)
            logger.info("[SETUP] %s impulse=[%.2f,%.2f] pullback=%.2f stop=%.2f tgt=%.2f trend=%s",
                        new_setup.side, new_setup.impulse_low,
                        new_setup.impulse_high, new_setup.pullback_entry,
                        new_setup.stop_px_val, new_setup.target_px_val,
                        htf_trend)

    # 4. Drop expired/invalidated setups
    state.pending_setups = [s for s in state.pending_setups
                            if not s.is_invalidated(now)]

    # 5. FIRE armed setups
    if in_cooldown:
        if state.pending_setups:
            _log_decision("entry_blocked",
                           reason="cooldown",
                           pending_count=len(state.pending_setups))
        return None
    # Auto daily-loss limit -- self-imposed DLL well below Lucid's $1,200
    # so a bad regime can't blow the account before the user can react.
    # Writes the same pause flag the manual button uses, with a different
    # reason tag, and an ny_date stamp so it auto-clears on the next day.
    try:
        _check_auto_daily_loss(lucid, now)
    except Exception as e:
        logger.debug(f"auto-DLL check skipped: {e!r}")
    # Manual pause gate -- user pressed the Pause button on the dashboard.
    # Blocks new entries only; the active trade (if any) was already managed
    # in step 1 above and runs to its stop/target normally.
    try:
        from bot.account_ctx import is_paused as _is_manually_paused
        if _is_manually_paused():
            for s in state.pending_setups:
                if not s.used:
                    s.last_block_reason = "manual_pause"
                    s.last_block_at = now
            if state.pending_setups:
                _log_decision("entry_blocked", reason="manual_pause",
                               pending_count=len(state.pending_setups))
            return None
    except Exception:
        pass
    # Post-streak pause: if active, block entries until expiry
    if state.pause_until_ts is not None and now < state.pause_until_ts:
        for s in state.pending_setups:
            if not s.used:
                s.last_block_reason = "post_streak_pause"
                s.last_block_at = now
        if state.pending_setups:
            _log_decision("entry_blocked", reason="post_streak_pause",
                           pending_count=len(state.pending_setups))
        return None
    if atr_blocked:
        # Low-ATR regime -- skip firing too. Setups already armed before
        # ATR dropped will resume when ATR climbs back.
        for s in state.pending_setups:
            if not s.used:
                s.last_block_reason = "low_atr"
                s.last_block_at = now
        if state.pending_setups:
            _log_decision("entry_blocked", reason="low_atr",
                           pending_count=len(state.pending_setups))
        return None
    if lucid_blocked:
        # Tag pending setups so the dashboard can show "Lucid window closed"
        # instead of silently sitting on armed setups.
        for s in state.pending_setups:
            if not s.used:
                s.last_block_reason = "lucid_trading_window_closed"
                s.last_block_at = now
        if state.pending_setups:
            _log_decision("entry_blocked",
                           reason="lucid_trading_window_closed",
                           pending_count=len(state.pending_setups))
        return None
    if news_blackout is not None:
        # Tag pending setups so the dashboard can show the news reason
        # (which event + how close). Setups stay armed; they'll fire as
        # soon as the post-event window expires.
        for s in state.pending_setups:
            if not s.used:
                s.last_block_reason = news_blackout
                s.last_block_at = now
        if state.pending_setups:
            _log_decision("entry_blocked", reason="news_blackout",
                           event=news_blackout,
                           pending_count=len(state.pending_setups))
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
                _log_decision("entry_blocked",
                               reason=f"lucid_precheck:{decision.reason}",
                               side=setup.side,
                               pullback_entry=setup.pullback_entry)
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
        _log_decision("trade_opened",
                       side=setup.side, qty=size_to_use,
                       entry_px=entry_px,
                       stop_px=setup.stop_px_val,
                       target_px=setup.target_px_val,
                       source="bar")
        logger.info("[OPEN] %s %d MNQ @ %.2f  stop=%.2f tgt=%.2f",
                    setup.side, size_to_use, entry_px,
                    setup.stop_px_val, setup.target_px_val)
        break   # only one position at a time

    return None


def try_fire_on_tick(state: FibStrategyState, lucid: LucidState,
                     live_price: float, now: datetime, *,
                     n_mnq: int = DEFAULT_SIZE,
                     params: Optional[dict] = None,
                     calendar=None) -> bool:
    """Tick-level entry trigger -- fire pending pullback setups the
    INSTANT live price touches the pullback level, instead of waiting
    for the 1-min bar to close.

    Old flow (bar-only):
      t=0:    bar closes, setup detected
      t=0-60: price retraces to pullback level mid-bar
      t=60:   next bar closes, is_filled() sees high/low touched
              pullback -> trade fires
      Total latency: up to 60s between price touching pullback and
      bot's entry signal reaching the broker.

    New flow (tick + bar):
      t=0:    bar closes, setup detected (unchanged)
      t=12:   live tick from Polygon WS shows price touched pullback
              -> trade fires immediately
      Total latency: ~0.5s (Polygon WS tick + bot _tick poll interval).

    The bar-based on_new_1m_bar() firing path still exists as a
    backstop. If a tick is missed (e.g. PriceMonitor down), the bar's
    high/low will catch the touch on the next close. Defense in depth.

    Returns True if a trade was opened on this tick (state.active_trade
    is now set), False otherwise. Caller (fib_main._tick) should call
    its _on_trade_open hook when True.

    SAFETY: applies the SAME pre-flight checks as the bar-based fire
    path -- circuit breaker, manual pause, auto-DLL, cooldown, Lucid
    closed window, news blackout, Lucid precheck. Single source of
    truth for "may we trade right now."
    """
    if state.active_trade is not None:
        return False  # already in a trade
    if not state.pending_setups:
        return False
    if state.circuit_breaker_tripped:
        return False
    # Manual / auto pause -- same gates as on_new_1m_bar
    p = _get_manual_pause_state()
    if p.get("paused"):
        return False
    try:
        _check_auto_daily_loss(lucid, now)
    except Exception:
        pass
    p = _get_manual_pause_state()
    if p.get("paused"):
        return False
    # Cooldown
    if state.last_trade_close_ts is not None:
        if (now - state.last_trade_close_ts).total_seconds() < COOLDOWN_SECS:
            return False
    # Lucid trading window
    if _in_lucid_closed_window(now):
        return False
    # News blackout
    blackout = _news_blackout_reason(now, calendar)
    if blackout is not None:
        for s in state.pending_setups:
            if not s.used:
                s.last_block_reason = blackout
                s.last_block_at = now
        return False

    # Find a setup whose pullback level has been touched by the live tick.
    # LIMIT semantics: LONG fires when price comes DOWN to pullback;
    # SHORT fires when price goes UP to pullback.
    fired = None
    for setup in state.pending_setups:
        if setup.used:
            continue
        if setup.is_invalidated(now):
            continue
        if setup.side == "LONG" and live_price <= setup.pullback_entry:
            fired = setup
            break
        if setup.side == "SHORT" and live_price >= setup.pullback_entry:
            fired = setup
            break
    if fired is None:
        return False

    # Lucid precheck
    decision = lucid_precheck(fired, n_mnq, lucid)
    if not decision.allowed:
        if decision.reason != fired.last_block_reason:
            logger.info("[BLOCKED tick] %s reason=%s", fired.side, decision.reason)
        fired.last_block_reason = decision.reason
        fired.last_block_at = now
        return False
    size_to_use = decision.suggested_n if decision.suggested_n > 0 else n_mnq

    # Open the trade. The bot's entry to the broker is a MARKET order
    # (subscription owns the bracket distances). Paper account books
    # at the pullback level for clean strategy outcome tracking; broker
    # executes at current tick. The two will differ by ~0-1pt typically,
    # which is acceptable.
    entry_px = float(fired.pullback_entry)
    new_trade = open_trade(fired, size_to_use, entry_px, now)
    if fired.armed_at_ts is None:
        fired.armed_at_ts = now
        fired.entry_armed = True
    fired.fire_attempted = True
    state.active_trade = new_trade
    fired.used = True
    state.recent_used_setups.append(_setup_key(fired))
    _log_decision("trade_opened",
                   side=fired.side, qty=size_to_use,
                   entry_px=entry_px, live_px=live_price,
                   stop_px=fired.stop_px_val,
                   target_px=fired.target_px_val,
                   source="tick")
    logger.info("[OPEN tick] %s %d MNQ pullback=%.2f live=%.2f "
                "stop=%.2f tgt=%.2f",
                fired.side, size_to_use, entry_px, live_price,
                fired.stop_px_val, fired.target_px_val)
    return True


def _get_manual_pause_state() -> dict:
    """Safe wrapper -- never let a snapshot read crash the bot loop."""
    try:
        from bot.account_ctx import get_pause_state
        return get_pause_state()
    except Exception:
        return {"paused": False}


def _auto_dll_limit() -> float:
    """Self-imposed daily loss limit (positive number = max $ allowed loss).
    Tunable via env var FIB_AUTO_DLL. Default 700.0 = ~58% of Lucid's $1,200
    DLL, leaves a $500 buffer for one more bad fill. Set to 0 to disable."""
    import os as _os
    try:
        return float(_os.environ.get("FIB_AUTO_DLL", "700.0"))
    except Exception:
        return 700.0


def _check_auto_daily_loss(lucid, now: datetime) -> None:
    """Run every tick. Sets / clears the auto-DLL pause flag based on
    today's realized P&L and the NY-day calendar. Reuses the manual-pause
    file as the single source of truth: when today_pnl breaches the limit
    we write the pause file with reason='auto_daily_loss_limit' and an
    ny_date stamp. The next NY day rolls the auto-pause off; manual pauses
    (reason=='user_manual') are NEVER auto-cleared."""
    try:
        from bot.account_ctx import get_pause_state, pause_file
        from bot.lucid_account import _ny_date_iso
    except Exception:
        return
    limit = _auto_dll_limit()
    if limit <= 0:
        return  # feature disabled
    today_pnl = float(getattr(lucid, "today_pnl", 0.0) or 0.0)
    ny_today = _ny_date_iso(now)
    pstate = get_pause_state()
    paused = bool(pstate.get("paused"))
    reason = pstate.get("reason", "")

    # 1) Auto-clear yesterday's auto-DLL pause when the NY day rolls.
    if paused and reason == "auto_daily_loss_limit":
        pause_day = pstate.get("ny_date")
        if pause_day and pause_day != ny_today:
            try:
                pause_file().unlink()
                logger.warning(f"[AUTO-DLL] NY day rolled {pause_day} -> {ny_today} -- clearing auto-pause")
            except Exception:
                pass
            paused = False

    # 2) Trip the auto-pause when today's loss breaches the threshold.
    #    Don't overwrite a manual pause -- user's intent wins.
    if not paused and today_pnl <= -limit:
        try:
            import json as _json
            from datetime import timezone as _tz
            payload = {
                "paused": True,
                "since": now.astimezone(_tz.utc).isoformat() if now.tzinfo else
                         now.replace(tzinfo=_tz.utc).isoformat(),
                "reason": "auto_daily_loss_limit",
                "ny_date": ny_today,
                "today_pnl_at_trip": round(today_pnl, 2),
                "limit": round(limit, 2),
            }
            p = pause_file()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_json.dumps(payload))
            logger.warning(f"[AUTO-DLL] today P&L ${today_pnl:+.2f} <= -${limit:.2f} -- "
                           f"auto-pausing until NY day {ny_today} rolls")
        except Exception as e:
            logger.warning(f"[AUTO-DLL] failed to write pause file: {e!r}")


# ============================================================================
# Snapshot (for dashboard)
# ============================================================================
def snapshot(state: FibStrategyState,
             dashboard_extras: Optional[dict] = None,
             current_price: Optional[float] = None) -> dict:
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
        "lucid_window_blocked": _in_lucid_closed_window(
            datetime.now(timezone.utc) if state else datetime.now(timezone.utc)),
        "htf_trend": state.htf_trend,
        "chop_index": state.chop_index,
        "circuit_breaker": {
            "tripped": state.circuit_breaker_tripped,
            "reason": state.circuit_breaker_reason,
        },
        "manual_pause": _get_manual_pause_state(),
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
        if current_price is not None:
            side = 1 if t.side == "LONG" else -1
            unrealized_pts = (current_price - t.entry_px) * side
            out["active_trade"]["current_price"] = current_price
            out["active_trade"]["unrealized_pnl_pts"] = round(unrealized_pts, 2)
            out["active_trade"]["unrealized_pnl_usd"] = round(
                unrealized_pts * 2.0 * t.n_mnq, 2)
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

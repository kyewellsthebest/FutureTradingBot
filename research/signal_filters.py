"""
Pre-trade filters (filters 3.5 / 4 / 5 / 6 / 7 / 8 from the spec).

All functions are pure helpers — no I/O, no global state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Literal

import numpy as np
import pandas as pd

from research.filter_config import CONFIG

NY_TZ = "America/New_York"

# ---- Cost model (per spec) ----
CONTRACTS = 30
DOLLARS_PER_POINT = 60.0
SLIPPAGE_POINTS = 2.0          # entry slippage (always)
ADVERSE_SLIPPAGE_POINTS = 2.0  # extra adverse on stop fills
COMMISSION_ROUND_TRIP = 60.0   # 30 contracts × $2

# ---- Daily bias exempt list ----
BIAS_EXEMPT_PREFIXES = ("GAP_FILL_", "PDL_", "PDH_", "FAILED_BREAKDOWN")

# ---- Kill zones (NY local time) ----
KILL_ZONES: list[tuple[str, time, time]] = [
    ("London Open",     time(2, 0),  time(5, 0)),
    ("Pre-NY",          time(5, 0),  time(7, 0)),
    ("NY Open",         time(7, 0),  time(10, 0)),
    ("London Close",    time(10, 0), time(12, 0)),
    ("Afternoon NY",    time(13, 0), time(15, 0)),
    ("Early Sydney",    time(17, 0), time(19, 0)),
    ("Sydney Open",     time(19, 0), time(21, 0)),
    ("Asian Midnight",  time(0, 0),  time(2, 0)),
]
# 24-hour exempt families (signals that key off rare structural events)
KILLZONE_EXEMPT_PREFIXES = (
    "PDL_BSL_SWEEP", "PDH_BSL_SWEEP", "PDL_TOUCH", "PDH_TOUCH",
    "POWERHOUR_REVERT_", "FAILED_BREAKDOWN_", "PDH_FLIP_",
    "THREE_HIGHER_LOWS_",
)

# ---- Key-level proximity: families exempt from the 30pt rule ----
PROXIMITY_EXEMPT_PREFIXES = (
    "PDL_", "PDH_",                                  # key off the level
    "VWAP_", "THIRD_VWAP_",                          # supply own targets
    "STOPRUN_", "BIGBAR_", "ASIAN_BREAK_",
    "POWERHOUR_", "FAILED_BREAKDOWN_",
    "PDH_FLIP_", "THREE_HIGHER_LOWS_", "GAP_FILL_",
)
PROXIMITY_MAX_POINTS = 30.0

# ---- Per-signal R:R minimums ----
DEFAULT_MIN_RR = 2.0
MIN_RR: dict[str, float] = {
    "GAP_FILL_SHORT": 4.0,
    "GAP_FILL_LONG": 1.3,        # high historic win rate
    "VWAP_RECLAIM_LONG": 1.5,
    "VWAP_REJECT_SHORT": 1.5,
    "THIRD_VWAP_TOUCH_LONG": 1.5,
    "THIRD_VWAP_TOUCH_SHORT": 1.5,
    "FAILED_BREAKDOWN_LONG": 1.5,
    "FAILED_BREAKDOWN_LONG_3BAR": 1.5,
    "THREE_HIGHER_LOWS_LONG": 1.5,
    "ASIAN_LOWQ_LONG": 1.5,
    "MIDDAY_LOW_BOUNCE_LONG": 1.5,
    "OVERNIGHT_DROP_RECOVER_LONG": 1.5,
    "PDH_FLIP_SUPPORT_LONG": 1.5,
    "TRIPLE_DOJI_BREAK_LONG": 1.5,
    "INSIDE2_BREAK_LONG": 1.5,
    "LIQ_POCKET_BREAK_LONG": 1.5,
    "GAPFILL_LONG": 1.5,
    "BARS_SINCE_LOD_LONG": 1.5,
}

# ---- Cooldown (per spec) ----
MAX_TRADES_PER_DAY = 2
MIN_GAP_BETWEEN_MIN = 90
MIN_GAP_AFTER_WINNER_MIN = 120


# =====================================================================
# Trade history reference (used by cooldown filter; built from SQLite)
# =====================================================================

@dataclass
class TradeRef:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp | None
    side: str
    pnl: float
    signal_name: str = ""

    @property
    def is_winner(self) -> bool:
        return self.pnl is not None and self.pnl > 0


# =====================================================================
# Filter 3.5 — Daily bias
# =====================================================================

DailyBias = Literal["BULLISH", "BEARISH", "MIXED"]


def daily_bias_at(daily: pd.DataFrame, ts: pd.Timestamp) -> DailyBias:
    """Last 3 *completed* daily candles before ts."""
    if daily is None or daily.empty:
        return "MIXED"
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    prior = daily[daily.index < ts.normalize()].tail(3)
    if len(prior) < 3:
        return "MIXED"
    closes = prior["close"].values
    opens = prior["open"].values
    if all(c > o for c, o in zip(closes, opens)):
        return "BULLISH"
    if all(c < o for c, o in zip(closes, opens)):
        return "BEARISH"
    return "MIXED"


def daily_bias_filter(side: str, bias: DailyBias, signal_name: str) -> tuple[bool, str]:
    if signal_name.startswith(BIAS_EXEMPT_PREFIXES):
        return True, f"bias exempt ({signal_name})"
    if side == "LONG" and bias in ("BULLISH", "MIXED"):
        return True, f"bias {bias} allows LONG"
    if side == "SHORT" and bias in ("BEARISH", "MIXED"):
        return True, f"bias {bias} allows SHORT"
    if not CONFIG.daily_bias_as_veto:
        return True, f"bias {bias} against {side} (soft mode, size×{CONFIG.daily_bias_soft_size_mult})"
    return False, f"bias {bias} blocks {side}"


def daily_bias_size_mult(side: str, bias: DailyBias, signal_name: str) -> float:
    """When daily_bias_as_veto=False, return size multiplier instead of vetoing."""
    if signal_name.startswith(BIAS_EXEMPT_PREFIXES):
        return 1.0
    if side == "LONG" and bias == "BEARISH":
        return CONFIG.daily_bias_soft_size_mult
    if side == "SHORT" and bias == "BULLISH":
        return CONFIG.daily_bias_soft_size_mult
    return 1.0


# =====================================================================
# Filter 4 — Kill zones
# =====================================================================

def kill_zone_filter(signal_name: str, ts: pd.Timestamp) -> tuple[bool, str]:
    if signal_name.startswith(KILLZONE_EXEMPT_PREFIXES):
        return True, "kill-zone exempt"
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    ny = ts.tz_convert(NY_TZ).time()
    for name, start, end in KILL_ZONES:
        if start <= ny < end:
            return True, name
    if not CONFIG.killzone_as_veto:
        return True, f"outside zones (soft mode, size×{CONFIG.killzone_soft_size_mult})"
    return False, "outside any kill zone"


def kill_zone_size_mult(signal_name: str, ts: pd.Timestamp) -> float:
    """When killzone_as_veto=False, return the size multiplier instead of vetoing."""
    if signal_name.startswith(KILLZONE_EXEMPT_PREFIXES):
        return 1.0
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    ny = ts.tz_convert(NY_TZ).time()
    for name, start, end in KILL_ZONES:
        if start <= ny < end:
            return 1.0
    return CONFIG.killzone_soft_size_mult


# =====================================================================
# Filter 5 — Key-level proximity
# =====================================================================

def key_level_proximity_filter(signal_name: str, entry_px: float,
                               pdh: float, pdl: float, eq50: float
                               ) -> tuple[bool, str]:
    if signal_name.startswith(PROXIMITY_EXEMPT_PREFIXES):
        return True, "proximity exempt"
    levels = [(pdh, "PDH"), (pdl, "PDL"), (eq50, "EQ50")]
    dists = [(abs(entry_px - lv), name) for lv, name in levels if lv == lv and lv > 0]
    if not dists:
        return True, "no levels available"
    nearest_d, nearest_name = min(dists)
    if nearest_d > PROXIMITY_MAX_POINTS:
        if not CONFIG.proximity_as_veto:
            return True, f"{nearest_d:.1f}pts from {nearest_name} (soft mode, size×{CONFIG.proximity_soft_size_mult})"
        return False, f"{nearest_d:.1f}pts from {nearest_name} > {PROXIMITY_MAX_POINTS}"
    return True, f"{nearest_d:.1f}pts from {nearest_name} ≤ {PROXIMITY_MAX_POINTS}"


def proximity_size_mult(signal_name: str, entry_px: float,
                         pdh: float, pdl: float, eq50: float) -> float:
    if signal_name.startswith(PROXIMITY_EXEMPT_PREFIXES):
        return 1.0
    levels = [(pdh, "PDH"), (pdl, "PDL"), (eq50, "EQ50")]
    dists = [abs(entry_px - lv) for lv, _ in levels if lv == lv and lv > 0]
    if not dists or min(dists) <= PROXIMITY_MAX_POINTS:
        return 1.0
    return CONFIG.proximity_soft_size_mult


# =====================================================================
# Target derivation + Filter 6 (Min R:R)
# =====================================================================

def derive_target(signal_name: str, side: str, entry_px: float,
                  pdh: float, pdl: float, eq50: float,
                  hint: float = float("nan"),
                  prev_close: float = float("nan")) -> float:
    """Pick a target price using the signal's natural anchor.

    Targets per strategy_report.txt:
      PDL_TOUCH         -> EQ50 midpoint (LONG)
      PDH_TOUCH         -> EQ50 midpoint (SHORT)
      GAP_FILL_LONG     -> previous session close
      GAP_FILL_SHORT    -> previous session close
      EQ50_LONG/SHORT   -> EQ50 itself (since price is far from EQ50 at entry)
      ZSCORE_*          -> z-score 0 = rolling mean (≈ entry's anchor; use eq50 fallback)
      VWAP_*            -> small fixed target (5-min: 30pt, HF: handled separately)
    """
    if hint == hint and hint > 0:
        return float(hint)

    # Gap-fill signals target the previous session close (the gap level)
    if signal_name.startswith("GAP_FILL_") or signal_name.startswith("PREV_CLOSE_"):
        if prev_close == prev_close and prev_close > 0:
            return float(prev_close)
        return float(eq50) if eq50 == eq50 else entry_px

    # PDL_TOUCH (LONG): bounce off PDL toward the midpoint
    # PDH_TOUCH (SHORT): rejection from PDH toward the midpoint
    if signal_name.startswith("PDL_TOUCH") or signal_name.startswith("PDH_TOUCH"):
        return float(eq50) if eq50 == eq50 else entry_px + 30 * (1 if side == "LONG" else -1)

    # PDL/PDH sweep signals reverse off the level — target the opposite key level
    # but capped at a reasonable RR
    if signal_name.startswith("PDL_BSL") or signal_name.startswith("PDL_") or \
       signal_name.startswith("FAILED_BREAKDOWN_"):
        # LONG bias: target halfway to PDH or 30pt, whichever closer
        if eq50 == eq50:
            return float(eq50)
        return entry_px + 30
    if signal_name.startswith("PDH_BSL") or signal_name.startswith("PDH_FLIP") or \
       signal_name.startswith("PDH_"):
        if eq50 == eq50:
            return float(eq50)
        return entry_px - 30

    # EQ50 mean-reversion: target the EQ50 level
    if signal_name.startswith("EQ50_"):
        return float(eq50) if eq50 == eq50 else entry_px

    # ZSCORE: target the rolling 20-bar mean. Since we don't have it threaded
    # through here, just project a fixed 25pt in trade direction. The eq50
    # anchor is wrong because it can be on the same side as entry (50-bar
    # midpoint vs 20-bar mean).
    if signal_name.startswith("ZSCORE_"):
        return entry_px + 25 * (1 if side == "LONG" else -1)

    # VWAP signals: fixed small target
    if signal_name.startswith("VWAP_") or signal_name.startswith("THIRD_VWAP_"):
        return entry_px + (20 if side == "LONG" else -20)

    # VOL_COMP / pattern_discovery: 30 pts in trade direction
    return entry_px + (30 if side == "LONG" else -30)


def min_rr_for(signal_name: str) -> float:
    if signal_name.startswith("MINED_"):
        return 2.0
    if signal_name.startswith("WR_"):
        return 0.8   # WR signals deliberately use ~1:1 RR with 60%+ WR
    if signal_name.startswith("V3_"):
        return 1.8   # V3 patterns use exact 1:2 RR by construction
    return MIN_RR.get(signal_name, DEFAULT_MIN_RR)


def min_rr_filter(signal_name: str, side: str, entry_px: float,
                   stop_pts: float, target_px: float
                   ) -> tuple[bool, str, float]:
    if stop_pts <= 0:
        return False, "invalid stop", 0.0
    target_pts = (target_px - entry_px) if side == "LONG" else (entry_px - target_px)
    if target_pts <= 0:
        return False, "target wrong side of entry", 0.0
    rr = float(target_pts / stop_pts)
    threshold = min_rr_for(signal_name)
    if rr < threshold:
        return False, f"RR={rr:.2f} < {threshold}", rr
    return True, f"RR={rr:.2f} ≥ {threshold}", rr


# =====================================================================
# Filter 7 — Cooldown
# =====================================================================

def cooldown_filter(ts: pd.Timestamp, prior_trades: list[TradeRef],
                     max_per_day: int | None = None) -> tuple[bool, str]:
    """Cooldown thresholds come from filter_config.CONFIG (env-driven)."""
    if max_per_day is None:
        max_per_day = CONFIG.max_trades_per_day
    min_gap = CONFIG.min_gap_between_min
    min_gap_winner = CONFIG.min_gap_after_winner_min
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    today = ts.tz_convert(NY_TZ).date()
    todays = [t for t in prior_trades if (t.entry_time.tz_convert(NY_TZ).date() == today
                                           if t.entry_time.tzinfo else False)]
    if len(todays) >= max_per_day:
        return False, f"already {len(todays)} trades today (max {max_per_day})"
    last = max((t for t in prior_trades if t.exit_time is not None),
               key=lambda t: t.exit_time, default=None)
    if last is not None:
        gap = (ts - last.exit_time).total_seconds() / 60.0
        if last.is_winner and gap < min_gap_winner:
            return False, f"only {gap:.0f}min since winner (need {min_gap_winner})"
        if gap < min_gap:
            return False, f"only {gap:.0f}min since last trade (need {min_gap})"
    return True, "cooldown clear"


# =====================================================================
# Filter 8 — Volatility regime sizing
# =====================================================================

VolRegime = Literal["LOW", "NORMAL", "HIGH"]


@dataclass
class VolRegimeInfo:
    regime: VolRegime
    stop_pts: float
    size_mult: float


def vol_regime_at(daily: pd.DataFrame, ts: pd.Timestamp) -> VolRegimeInfo:
    """5-day avg daily range / 20-day avg daily range."""
    if daily is None or len(daily) < 25:
        return VolRegimeInfo("NORMAL", 15.0, 1.0)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    prior = daily[daily.index <= ts]
    if len(prior) < 25:
        return VolRegimeInfo("NORMAL", 15.0, 1.0)
    rng = (prior["high"] - prior["low"]).tail(20)
    if rng.empty or rng.tail(20).mean() <= 0:
        return VolRegimeInfo("NORMAL", 15.0, 1.0)
    ratio = float(rng.tail(5).mean() / rng.tail(20).mean())
    if ratio > 1.5:
        return VolRegimeInfo("HIGH", 20.0, 0.5)
    if ratio < 0.7:
        return VolRegimeInfo("LOW", 10.0, 1.0)
    return VolRegimeInfo("NORMAL", 15.0, 1.0)

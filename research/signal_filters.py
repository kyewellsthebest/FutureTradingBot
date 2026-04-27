"""
Pre-trade filters: daily bias, vol regime, kill zones, level proximity, R:R, cooldown.

All functions are pure helpers — no I/O, no global state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Literal

import numpy as np
import pandas as pd

# Constants the rest of the system imports
SLIPPAGE_POINTS = 2.0
COMMISSION_PER_RT = 60.0
DOLLARS_PER_POINT = 60.0  # 30 MNQ contracts * $2/pt

NY = "America/New_York"

DailyBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]


@dataclass
class TradeRef:
    """Lightweight reference to a closed trade — used by cooldown_filter."""
    signal_time: pd.Timestamp
    close_time: pd.Timestamp
    side: str
    pnl_pts: float
    was_winner: bool


@dataclass
class VolRegime:
    regime: Literal["LOW", "NORMAL", "HIGH"]
    stop_pts: float
    size_mult: float


# ---------------------------------------------------------------------------
# Daily bias
# ---------------------------------------------------------------------------

def daily_bias_at(daily: pd.DataFrame, ts: pd.Timestamp) -> DailyBias:
    """3-candle bias: BULLISH if last 3 daily closes are higher than opens, etc."""
    if daily is None or daily.empty:
        return "NEUTRAL"
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    past = daily[daily.index < ts]
    if len(past) < 3:
        return "NEUTRAL"
    last3 = past.iloc[-3:]
    bull = (last3["close"] > last3["open"]).sum()
    bear = (last3["close"] < last3["open"]).sum()
    if bull >= 2 and bear == 0:
        return "BULLISH"
    if bear >= 2 and bull == 0:
        return "BEARISH"
    return "NEUTRAL"


def daily_bias_filter(side: str, bias: DailyBias, name: str) -> tuple[bool, str]:
    """Block trades that fight a strong opposite daily bias.

    Mean-reversion fade signals (GAP_FILL_*, ZSCORE_*, EQ50_*) are allowed against bias.
    """
    fade_signals = {
        "GAP_FILL_LONG", "GAP_FILL_SHORT",
        "ZSCORE_LONG", "ZSCORE_SHORT",
        "EQ50_LONG", "EQ50_SHORT",
        "VWAP_RECLAIM_LONG", "VWAP_REJECT_SHORT",
        "PDL_TOUCH", "PDH_TOUCH",
    }
    if name in fade_signals or bias == "NEUTRAL":
        return True, f"bias={bias} ok (fade-allowed)"
    if side == "LONG" and bias == "BEARISH":
        return False, f"bias={bias} blocks LONG"
    if side == "SHORT" and bias == "BULLISH":
        return False, f"bias={bias} blocks SHORT"
    return True, f"bias={bias} ok"


# ---------------------------------------------------------------------------
# Vol regime
# ---------------------------------------------------------------------------

def vol_regime_at(daily: pd.DataFrame, ts: pd.Timestamp) -> VolRegime:
    """Compare 5-day range to 20-day average range to bucket vol."""
    if daily is None or daily.empty:
        return VolRegime("NORMAL", 15.0, 1.0)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    past = daily[daily.index < ts]
    if len(past) < 25:
        return VolRegime("NORMAL", 15.0, 1.0)
    rng = (past["high"] - past["low"])
    r5 = float(rng.tail(5).mean())
    r20 = float(rng.tail(20).mean())
    if r20 <= 0:
        return VolRegime("NORMAL", 15.0, 1.0)
    ratio = r5 / r20
    if ratio > 1.5:
        return VolRegime("HIGH", 20.0, 0.5)
    if ratio < 0.7:
        return VolRegime("LOW", 10.0, 1.0)
    return VolRegime("NORMAL", 15.0, 1.0)


# ---------------------------------------------------------------------------
# Kill zones (ICT-style sessions, all in New York time)
# ---------------------------------------------------------------------------

KILL_ZONES = [
    ("Asian",        time(20, 0), time(23, 0)),
    ("London",       time(2, 0),  time(5, 0)),
    ("NY AM",        time(9, 30), time(11, 30)),
    ("NY Lunch",     time(11, 30), time(13, 0)),
    ("NY PM",        time(13, 30), time(16, 0)),
    ("Early Sydney", time(17, 0), time(19, 0)),
]

# Some signals are explicitly opening-range or session-specific
SESSION_LOCK = {
    "ORB_LONG": ["NY AM"], "ORB_SHORT": ["NY AM"],
    "MOMO_LONG": ["NY AM"], "MOMO_SHORT": ["NY AM"],
    "GAP_FILL_LONG": ["NY AM"], "GAP_FILL_SHORT": ["NY AM"],
    "ASIAN_BREAK_LONG": ["London"], "ASIAN_BREAK_SHORT": ["London"],
}


def _ny_time(ts: pd.Timestamp) -> time:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(NY).time()


def kill_zone_filter(name: str, ts: pd.Timestamp) -> tuple[bool, str]:
    nyt = _ny_time(ts)
    active = [zname for zname, s, e in KILL_ZONES if s <= nyt < e]
    locked = SESSION_LOCK.get(name)
    if locked:
        ok = any(z in locked for z in active)
        return ok, f"kz={active or 'none'} need {locked}"
    if not active:
        return False, "kz=none"
    return True, f"kz={active[0]}"


def active_kill_zone(ts: pd.Timestamp) -> str | None:
    nyt = _ny_time(ts)
    for zname, s, e in KILL_ZONES:
        if s <= nyt < e:
            return zname
    return None


def next_kill_zone(ts: pd.Timestamp) -> str:
    nyt = _ny_time(ts)
    for zname, s, _e in KILL_ZONES:
        if nyt < s:
            return f"{zname} @ {s.strftime('%H:%M')} EST"
    z, s, _e = KILL_ZONES[0]
    return f"{z} @ {s.strftime('%H:%M')} EST"


# ---------------------------------------------------------------------------
# Level proximity
# ---------------------------------------------------------------------------

PROX_RULES = {
    "PDL_TOUCH":  ("near_pdl", 5.0),
    "PDH_TOUCH":  ("near_pdh", 5.0),
    "PDL_BSL_SWEEP": ("near_pdl", 8.0),
    "PDH_BSL_SWEEP": ("near_pdh", 8.0),
    "EQ50_LONG":  ("near_eq50_below", 40.0),
    "EQ50_SHORT": ("near_eq50_above", 40.0),
}


def key_level_proximity_filter(name: str, entry: float,
                               pdh: float, pdl: float, eq: float) -> tuple[bool, str]:
    rule = PROX_RULES.get(name)
    if rule is None:
        return True, "no-prox-rule"
    kind, dist = rule
    if kind == "near_pdl":
        if not np.isfinite(pdl):
            return False, "pdl=NaN"
        ok = abs(entry - pdl) <= dist
        return ok, f"|entry-pdl|={abs(entry-pdl):.1f} <= {dist}"
    if kind == "near_pdh":
        if not np.isfinite(pdh):
            return False, "pdh=NaN"
        ok = abs(entry - pdh) <= dist
        return ok, f"|entry-pdh|={abs(entry-pdh):.1f} <= {dist}"
    if kind == "near_eq50_below":
        if not np.isfinite(eq):
            return False, "eq50=NaN"
        ok = (eq - entry) >= dist
        return ok, f"eq50-entry={eq-entry:.1f} >= {dist}"
    if kind == "near_eq50_above":
        if not np.isfinite(eq):
            return False, "eq50=NaN"
        ok = (entry - eq) >= dist
        return ok, f"entry-eq50={entry-eq:.1f} >= {dist}"
    return True, "ok"


# ---------------------------------------------------------------------------
# Targets and R:R
# ---------------------------------------------------------------------------

TARGET_RULES: dict[str, tuple[str, float]] = {
    "PDL_TOUCH":   ("eq50", 0),
    "PDH_TOUCH":   ("eq50", 0),
    "EQ50_LONG":   ("pdh", 0),
    "EQ50_SHORT":  ("pdl", 0),
    "GAP_FILL_LONG":  ("prev_close_proxy_pdh_minus", 30),
    "GAP_FILL_SHORT": ("prev_close_proxy_pdl_plus", 30),
    "ZSCORE_LONG":  ("ratio", 60),
    "ZSCORE_SHORT": ("ratio", 60),
    "VOL_COMP_LONG":  ("ratio", 80),
    "VOL_COMP_SHORT": ("ratio", 80),
    "VWAP_RECLAIM_LONG": ("ratio", 50),
    "VWAP_REJECT_SHORT": ("ratio", 50),
    "ASIAN_BREAK_LONG":  ("ratio", 35),
    "ASIAN_BREAK_SHORT": ("ratio", 35),
    "MOMO_LONG":  ("ratio", 60),
    "MOMO_SHORT": ("ratio", 60),
    "ORB_LONG":  ("ratio", 70),
    "ORB_SHORT": ("ratio", 70),
    "STOPRUN_LONG":  ("ratio", 45),
    "STOPRUN_SHORT": ("ratio", 45),
    "THIRD_VWAP_TOUCH_LONG": ("ratio", 40),
    "PDL_BSL_SWEEP":  ("ratio", 40),
    "PDH_BSL_SWEEP":  ("ratio", 40),
}


def derive_target(name: str, side: str, entry: float,
                  pdh: float, pdl: float, eq: float, hint: float) -> float:
    """Pick a target price using the per-signal rule, falling back to a fixed offset."""
    if np.isfinite(hint) and hint > 0:
        return float(hint)
    rule = TARGET_RULES.get(name, ("ratio", 50))
    kind, fixed = rule
    if kind == "eq50" and np.isfinite(eq):
        return float(eq)
    if kind == "pdh" and np.isfinite(pdh):
        return float(pdh)
    if kind == "pdl" and np.isfinite(pdl):
        return float(pdl)
    if kind == "prev_close_proxy_pdh_minus" and np.isfinite(pdh):
        return float(pdh - fixed)
    if kind == "prev_close_proxy_pdl_plus" and np.isfinite(pdl):
        return float(pdl + fixed)
    if side == "LONG":
        return entry + float(fixed)
    return entry - float(fixed)


MIN_RR = {
    "PDL_TOUCH": 2.0,
    "PDH_TOUCH": 2.0,
    "EQ50_LONG": 2.0,
    "EQ50_SHORT": 2.0,
    "GAP_FILL_LONG": 4.0,
    "GAP_FILL_SHORT": 4.0,
}
DEFAULT_MIN_RR = 1.5


def min_rr_filter(name: str, side: str, entry: float, stop_pts: float,
                  target: float) -> tuple[bool, str, float]:
    if stop_pts <= 0:
        return False, "stop=0", 0.0
    reward = (target - entry) if side == "LONG" else (entry - target)
    rr = float(reward / stop_pts)
    need = MIN_RR.get(name, DEFAULT_MIN_RR)
    ok = rr >= need
    return ok, f"rr={rr:.2f} need {need}", rr


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

COOLDOWN_AFTER_WINNER_MIN = 120
MIN_GAP_BETWEEN_TRADES_MIN = 90
MAX_TRADES_PER_DAY = 2


def cooldown_filter(ts: pd.Timestamp,
                    prior_trades: list[TradeRef]) -> tuple[bool, str]:
    if not prior_trades:
        return True, "no prior trades"
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    today = ts.tz_convert(NY).date()
    today_count = 0
    for t in prior_trades:
        ct = t.close_time
        if ct.tzinfo is None:
            ct = ct.tz_localize("UTC")
        if ct.tz_convert(NY).date() == today:
            today_count += 1
    if today_count >= MAX_TRADES_PER_DAY:
        return False, f"max {MAX_TRADES_PER_DAY} trades/day"

    last = max(prior_trades, key=lambda t: t.close_time)
    last_close = last.close_time
    if last_close.tzinfo is None:
        last_close = last_close.tz_localize("UTC")
    delta = ts - last_close
    if delta < timedelta(minutes=MIN_GAP_BETWEEN_TRADES_MIN):
        return False, f"gap {delta} < {MIN_GAP_BETWEEN_TRADES_MIN}m"
    if last.was_winner and delta < timedelta(minutes=COOLDOWN_AFTER_WINNER_MIN):
        return False, f"winner cooldown {delta}"
    return True, "cooldown ok"

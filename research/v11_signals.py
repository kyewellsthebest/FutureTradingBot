"""
v11 Signal Registry — production-ready loader for the 119 user-pass NQ-ES
stat-arb strategies discovered by pattern_miner_v11.

Each v11 strategy is fully described by a small parameter set:
  * window N         (Z-score lookback in 5-min bars: 10, 15, 20, 30, 45, 60, 90, 120)
  * threshold T      (Z-score absolute threshold: 1.5, 1.7, 2.0, 2.2, 2.5, 2.7, 3.0)
  * side             (LONG = fade NQ underperformance; SHORT = fade NQ overperformance)
  * time context     (NY-afternoon time slice)
  * stop_atr         (1.0 or 1.5 ATR stop)
  * target_atr       (2.0–4.0 ATR target)
  * max_hold_min     (45–90 minutes)

Live evaluation per 5-min bar:
  1. Compute NQ-ES return divergence Z-score for each window N
  2. For each loaded strategy:
       fires if (current bar in time context) AND (Z crosses threshold in side direction)
  3. If fires: return TradeCandidate with entry=next bar open, stop=entry ± stop_atr*ATR,
     target=entry ± target_atr*ATR

This module REPLACES the old V3/V6/V9 signal_engine for v11-only deployment.
No VPIN, no regime, no ML, no alt-data — pure NQ-ES stat-arb.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"

logger = logging.getLogger("v11_signals")


# ----------------------------------------------------------------------------
# Strategy definition
# ----------------------------------------------------------------------------
@dataclass
class V11Strategy:
    """Live-runnable v11 strategy."""
    name: str
    side: str           # "LONG" or "SHORT"
    z_window: int       # 10, 15, 20, 30, 45, 60, 90, 120
    z_threshold: float  # 1.5–3.0
    time_context: str   # "t_1300_1330", "t_1330_1400", ..., "pm_full", "t_1330_1530"
    stop_atr: float
    target_atr: float
    max_hold_min: int
    # Mining stats (informational, used by dashboard)
    test_n: int = 0
    test_wr: float = 0.0
    test_pf: float = 0.0
    test_sharpe: float = 0.0
    test_net: float = 0.0
    cpcv_positive: int = 0


# ----------------------------------------------------------------------------
# Parse a strategy name from mining JSON to extract the live-runnable params
# ----------------------------------------------------------------------------
def _parse_strategy(s: dict) -> Optional[V11Strategy]:
    """Convert a JSON dict from mined_v11_patterns.json to V11Strategy."""
    name = s["name"]
    side = s["side"]
    trigger = s["trigger"]              # e.g. "sa_long_45_25"
    contexts = s["contexts"]            # e.g. ["t_1530_1600"]
    if not contexts:
        return None

    # Parse trigger like "sa_long_45_25" → window=45, threshold=2.5
    parts = trigger.split("_")
    if len(parts) < 4:
        return None
    try:
        window = int(parts[2])
        thr_raw = int(parts[3])         # 25 → 2.5
        threshold = thr_raw / 10.0
    except (ValueError, IndexError):
        return None

    return V11Strategy(
        name=name,
        side=side,
        z_window=window,
        z_threshold=threshold,
        time_context=contexts[0],       # all v11 strategies have one context
        stop_atr=s["stop_atr"],
        target_atr=s["target_atr"],
        max_hold_min=s["max_hold_min"],
        test_n=s.get("test", {}).get("n", 0),
        test_wr=s.get("test", {}).get("wr", 0.0),
        test_pf=s.get("test", {}).get("pf", 0.0),
        test_sharpe=s.get("test", {}).get("sharpe", 0.0),
        test_net=s.get("test", {}).get("net", 0.0),
        cpcv_positive=s.get("cpcv_positive", 0),
    )


# ----------------------------------------------------------------------------
# Strategy registry loader
# ----------------------------------------------------------------------------
def load_v11_strategies(json_path: Path = DATA / "mined_v11_patterns.json",
                          min_pf: float = 1.0,
                          require_cpcv: int = 0) -> list[V11Strategy]:
    """Load all user-pass v11 strategies (default: PF > 1.0, no CPCV req).

    Args:
        json_path: path to mined_v11_patterns.json
        min_pf: minimum profit factor (default 1.0 = real edge)
        require_cpcv: minimum CPCV folds positive (0 = ignore)

    Returns:
        List of V11Strategy, sorted by Sharpe descending.
    """
    data = json.loads(json_path.read_text())
    user_passers = data.get("user_passers", [])
    out = []
    for s in user_passers:
        if s.get("test", {}).get("pf", 0) < min_pf:
            continue
        if s.get("cpcv_positive", 0) < require_cpcv:
            continue
        v = _parse_strategy(s)
        if v is None:
            continue
        out.append(v)
    out.sort(key=lambda x: -x.test_sharpe)
    return out


# ----------------------------------------------------------------------------
# Time context evaluation (NY local time)
# ----------------------------------------------------------------------------
def in_time_context(ctx: str, ny_hour: int, ny_min: int) -> bool:
    """Check if (ny_hour, ny_min) falls inside the named time context."""
    if ctx == "t_1300_1330":  return ny_hour == 13 and ny_min < 30
    if ctx == "t_1330_1400":  return ny_hour == 13 and ny_min >= 30
    if ctx == "t_1400_1430":  return ny_hour == 14 and ny_min < 30
    if ctx == "t_1430_1500":  return ny_hour == 14 and ny_min >= 30
    if ctx == "t_1500_1530":  return ny_hour == 15 and ny_min < 30
    if ctx == "t_1530_1600":  return ny_hour == 15 and ny_min >= 30
    if ctx == "pm_full":      return 14 <= ny_hour < 16
    if ctx == "t_1330_1530":  return ((ny_hour == 13 and ny_min >= 30)
                                          or ny_hour == 14
                                          or (ny_hour == 15 and ny_min < 30))
    return False


# ----------------------------------------------------------------------------
# Z-score computation
# ----------------------------------------------------------------------------
def compute_div_z(nq_close: pd.Series, es_close: pd.Series, window: int,
                    rolling: int = 200) -> pd.Series:
    """NQ-ES return divergence Z-score for a single window.

    Z = (NQ_pct_change_N - ES_pct_change_N - rolling_mean_200) / rolling_std_200

    Negative Z → NQ underperformed → LONG signal
    Positive Z → NQ overperformed  → SHORT signal
    """
    es = es_close.reindex(nq_close.index, method="ffill")
    div = nq_close.pct_change(window) - es.pct_change(window)
    mu = div.rolling(rolling).mean()
    sd = div.rolling(rolling).std()
    z = (div - mu) / sd
    return z.replace([np.inf, -np.inf], np.nan)


# ----------------------------------------------------------------------------
# Live state container — keeps Z-scores per window updated
# ----------------------------------------------------------------------------
class V11State:
    """Maintains rolling Z-scores per window. Call update_bar() each new 5-min bar."""

    def __init__(self, strategies: list[V11Strategy]):
        self.strategies = strategies
        # Unique windows we need to compute
        self.windows = sorted({s.z_window for s in strategies})
        self.z_current: dict[int, float] = {w: float("nan") for w in self.windows}
        # Track most recent bar timestamp processed
        self.last_bar_ts: Optional[pd.Timestamp] = None
        self.atr_current: float = float("nan")

    def update_from_history(self, nq_5m: pd.DataFrame, es_5m: pd.DataFrame,
                              atr_series: Optional[pd.Series] = None,
                              latest_n: int = 250):
        """Refresh Z-scores using the most recent N bars of NQ + ES history."""
        nq = nq_5m.tail(latest_n + max(self.windows) + 200)
        es = es_5m.reindex(nq.index, method="ffill")
        for w in self.windows:
            z = compute_div_z(nq["close"], es["close"], w)
            self.z_current[w] = float(z.iloc[-1]) if len(z) else float("nan")
        if atr_series is not None and len(atr_series):
            self.atr_current = float(atr_series.iloc[-1])
        self.last_bar_ts = nq.index[-1] if len(nq) else None

    def get_z(self, window: int) -> float:
        return self.z_current.get(window, float("nan"))

    def evaluate_strategies(self, ny_hour: int, ny_min: int) -> list[dict]:
        """Return list of fired strategies (one dict each) for current bar."""
        fired = []
        for s in self.strategies:
            if not in_time_context(s.time_context, ny_hour, ny_min):
                continue
            z = self.get_z(s.z_window)
            if np.isnan(z):
                continue
            if s.side == "LONG" and z < -s.z_threshold:
                fired.append({
                    "strategy": s,
                    "z_value": z,
                    "trigger_threshold": -s.z_threshold,
                })
            elif s.side == "SHORT" and z > s.z_threshold:
                fired.append({
                    "strategy": s,
                    "z_value": z,
                    "trigger_threshold": s.z_threshold,
                })
        return fired

    def distance_to_trigger(self, top_n: int = 10) -> list[dict]:
        """Return the N strategies CLOSEST to firing (for the Brain tab)."""
        rows = []
        for s in self.strategies:
            z = self.get_z(s.z_window)
            if np.isnan(z):
                continue
            if s.side == "LONG":
                trigger = -s.z_threshold
                distance = z - trigger    # if z < trigger, distance < 0 = fired
            else:
                trigger = s.z_threshold
                distance = trigger - z    # if z > trigger, distance < 0 = fired
            rows.append({
                "name": s.name,
                "side": s.side,
                "z_window": s.z_window,
                "z_threshold": s.z_threshold,
                "z_current": z,
                "distance": distance,
                "fired": distance < 0,
                "time_ctx": s.time_context,
            })
        rows.sort(key=lambda r: r["distance"])
        return rows[:top_n]


# ----------------------------------------------------------------------------
# Convenience
# ----------------------------------------------------------------------------
def summary_stats(strategies: list[V11Strategy]) -> dict:
    """High-level metrics for the dashboard Strategies tab."""
    if not strategies:
        return {}
    return {
        "count": len(strategies),
        "long_count": sum(1 for s in strategies if s.side == "LONG"),
        "short_count": sum(1 for s in strategies if s.side == "SHORT"),
        "median_wr": float(np.median([s.test_wr for s in strategies])),
        "median_pf": float(np.median([s.test_pf for s in strategies])),
        "median_sharpe": float(np.median([s.test_sharpe for s in strategies])),
        "total_mining_net_1mnq": sum(s.test_net for s in strategies),
        "z_windows": sorted({s.z_window for s in strategies}),
        "time_contexts": sorted({s.time_context for s in strategies}),
    }

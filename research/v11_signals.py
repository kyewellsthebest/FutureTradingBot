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
    """Live-runnable strategy. Spans v11/v12 (NQ-ES stat-arb) plus v13
    (NQ-VIX residual, NQ-RTY rotation, VIX-regime-gated stat-arb)."""
    name: str
    side: str           # "LONG" or "SHORT"
    z_window: int       # lookback bars
    z_threshold: float  # |Z| at which the trigger fires
    time_context: str   # time-of-day or VIX-regime bucket
    stop_atr: float
    target_atr: float
    max_hold_min: int
    # Family — which feature stream the trigger reads from:
    #   "es" → NQ-ES return divergence Z (v11, v12, v13C)
    #   "vix" → NQ-VIX residual Z (v13A)
    #   "rty" → NQ-RTY return divergence Z (v13B)
    family: str = "es"
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
    """Convert a JSON dict (mined_v11/v12/v13) to V11Strategy.

    Trigger names encode the feature family in their prefix:
      "sa_long_45_25"   → NQ-ES residual Z, family=es
      "vix_long_60_25"  → NQ-VIX residual Z, family=vix
      "rty_long_30_20"  → NQ-RTY divergence Z, family=rty
    Window and threshold come from the trailing two underscored fields.
    """
    name = s["name"]
    side = s["side"]
    trigger = s["trigger"]
    contexts = s["contexts"]
    if not contexts:
        return None

    parts = trigger.split("_")
    if len(parts) < 4:
        return None
    prefix = parts[0]
    family = {"sa": "es", "vix": "vix", "rty": "rty"}.get(prefix, "es")
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
        time_context=contexts[0],
        stop_atr=s["stop_atr"],
        target_atr=s["target_atr"],
        max_hold_min=s["max_hold_min"],
        family=family,
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
def load_v11_strategies(json_paths: list[Path] | Path | None = None,
                          min_pf: float = 1.0,
                          require_cpcv: int = 0,
                          deployed_only: bool = True) -> list[V11Strategy]:
    """Load all user-pass strategies from v11 + v12 mining (or a custom list).

    By default, looks in:
      - data/mined_v11_patterns.json   (NY afternoon stat-arb)
      - data/mined_v12_patterns.json   (overnight / AEST-daytime stat-arb)

    Args:
        json_paths: single Path, list of Paths, or None to use defaults
        min_pf: minimum profit factor (default 1.0 = real edge)
        require_cpcv: minimum CPCV folds positive (0 = ignore)
        deployed_only: if True (default), filter to names listed in
            data/deployed_strategies.json. This is the post-stress-test
            keepers list — bulletproof + moderate + fragile SHORTs (kept
            for L/S balance). Set False to load every user-pass strategy.

    Returns:
        List of V11Strategy, sorted by Sharpe descending.
    """
    if json_paths is None:
        json_paths = [DATA / "mined_v11_patterns.json",
                        DATA / "mined_v12_patterns.json",
                        DATA / "mined_v13_patterns.json"]
    elif isinstance(json_paths, Path):
        json_paths = [json_paths]

    # Optional deployment filter
    deployed_names = None
    if deployed_only:
        dep_path = DATA / "deployed_strategies.json"
        if dep_path.exists():
            try:
                d = json.loads(dep_path.read_text())
                deployed_names = set(d.get("names", []))
            except Exception:
                deployed_names = None

    out = []
    seen_names = set()
    for path in json_paths:
        if not path.exists():
            logger.warning(f"strategy file not found, skipping: {path}")
            continue
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            logger.warning(f"failed to parse {path}: {e}")
            continue
        for s in data.get("user_passers", []):
            if s.get("test", {}).get("pf", 0) < min_pf:
                continue
            if s.get("cpcv_positive", 0) < require_cpcv:
                continue
            if deployed_names is not None and s["name"] not in deployed_names:
                continue
            if s["name"] in seen_names:
                continue
            v = _parse_strategy(s)
            if v is None:
                continue
            seen_names.add(s["name"])
            out.append(v)
    out.sort(key=lambda x: -x.test_sharpe)
    return out


# ----------------------------------------------------------------------------
# Time context evaluation (NY local time)
# ----------------------------------------------------------------------------
def in_time_context(ctx: str, ny_hour: int, ny_min: int,
                       vix_pct: float = float("nan"),
                       vix_z: float = float("nan")) -> bool:
    """Check if the current bar matches the named context.

    Time-only contexts use ny_hour/ny_min. v13 VIX-regime contexts also
    consult the VIX percentile (0-1) and VIX Z-score. Combined contexts
    like 'pm_vix_high' require BOTH the time AND the regime to be active.
    """
    # ---- v13 VIX regime gates --------------------------------------
    if ctx == "vix_low":      return vix_pct == vix_pct and vix_pct < 0.25
    if ctx == "vix_mid":      return vix_pct == vix_pct and 0.25 <= vix_pct < 0.75
    if ctx == "vix_high":     return vix_pct == vix_pct and vix_pct >= 0.75
    if ctx == "vix_spike":    return vix_z == vix_z and vix_z > 2.0
    if ctx == "vix_collapse": return vix_z == vix_z and vix_z < -2.0
    # ---- v13 combined PM + VIX ------------------------------------
    in_pm = 14 <= ny_hour < 16
    if ctx == "pm_vix_low":  return in_pm and vix_pct == vix_pct and vix_pct < 0.25
    if ctx == "pm_vix_mid":  return in_pm and vix_pct == vix_pct and 0.25 <= vix_pct < 0.75
    if ctx == "pm_vix_high": return in_pm and vix_pct == vix_pct and vix_pct >= 0.75
    # ---- v11 NY-afternoon contexts -------------------------------------
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
    # ---- v12 NY-overnight contexts (AEST daytime) ----------------------
    if ctx == "t_1900_2000":  return ny_hour == 19   #  9-10 AM AEST
    if ctx == "t_2000_2100":  return ny_hour == 20   # 10-11 AM AEST
    if ctx == "t_2100_2200":  return ny_hour == 21   # 11 AM-12 PM AEST
    if ctx == "t_2200_2300":  return ny_hour == 22   # 12-1 PM AEST
    if ctx == "t_2300_2400":  return ny_hour == 23   #  1-2 PM AEST
    if ctx == "t_0000_0100":  return ny_hour == 0    #  2-3 PM AEST
    if ctx == "t_0100_0200":  return ny_hour == 1    #  3-4 PM AEST
    if ctx == "t_0200_0300":  return ny_hour == 2    #  4-5 PM AEST
    if ctx == "evening_us":   return 19 <= ny_hour <= 22       #  9 AM-1 PM AEST
    if ctx == "overnight":    return ny_hour >= 23 or ny_hour <= 2   # 1 AM-5 PM AEST
    if ctx == "t_0300_0900":  return 3 <= ny_hour <= 8         # 5-11 AM AEST (no edge)
    return False


# ----------------------------------------------------------------------------
# Z-score computation
# ----------------------------------------------------------------------------
def compute_div_z(nq_close: pd.Series, other_close: pd.Series, window: int,
                    rolling: int = 200) -> pd.Series:
    """Generic NQ vs other-asset return-divergence Z-score for a window.

    Z = (NQ_pct_change_N - other_pct_change_N - rolling_mean) / rolling_std
    """
    other = other_close.reindex(nq_close.index, method="ffill")
    div = nq_close.pct_change(window) - other.pct_change(window)
    mu = div.rolling(rolling).mean()
    sd = div.rolling(rolling).std()
    z = (div - mu) / sd
    return z.replace([np.inf, -np.inf], np.nan)


def compute_residual_z(nq_close: pd.Series, other_close: pd.Series, window: int,
                          rolling: int = 200) -> pd.Series:
    """NQ-vs-other return Z-score using a regression-residual definition
    (used for NQ-VIX where the relationship is structurally negative).
    Same math as compute_div_z but kept separate for clarity."""
    return compute_div_z(nq_close, other_close, window, rolling)


# ----------------------------------------------------------------------------
# Live state container — multi-family Z-scores + VIX regime + ATR
# ----------------------------------------------------------------------------
class V11State:
    """Maintains rolling Z-scores per (family, window). Call
    update_from_history() each new 5-min bar."""

    def __init__(self, strategies: list[V11Strategy]):
        self.strategies = strategies
        # Per-family unique windows we need to compute
        self.windows_by_family: dict[str, list[int]] = {}
        for s in strategies:
            self.windows_by_family.setdefault(s.family, set()).add(s.z_window)
        self.windows_by_family = {f: sorted(ws) for f, ws in self.windows_by_family.items()}
        # Backward-compat: flat list for "es" family (legacy V11State.windows)
        self.windows = self.windows_by_family.get("es", [])
        # z_current[family][window] = latest Z value
        self.z_current: dict[str, dict[int, float]] = {
            fam: {w: float("nan") for w in ws}
            for fam, ws in self.windows_by_family.items()
        }
        self.last_bar_ts: Optional[pd.Timestamp] = None
        self.atr_current: float = float("nan")
        # v13 VIX regime state
        self.vix_pct_current: float = float("nan")   # rolling 500-bar percentile [0,1]
        self.vix_z_current: float = float("nan")     # rolling 200-bar Z

    def update_from_history(self, nq_5m: pd.DataFrame, es_5m: pd.DataFrame,
                              atr_series: Optional[pd.Series] = None,
                              rty_5m: Optional[pd.DataFrame] = None,
                              vix_5m: Optional[pd.DataFrame] = None,
                              latest_n: int = 250):
        """Refresh Z-scores for all loaded families plus VIX regime fields."""
        max_window = max(
            (max(ws) for ws in self.windows_by_family.values() if ws),
            default=120
        )
        nq = nq_5m.tail(latest_n + max_window + 500)
        # NQ-ES residual Z (es family)
        if "es" in self.windows_by_family and es_5m is not None:
            es = es_5m["close"].reindex(nq.index, method="ffill")
            for w in self.windows_by_family["es"]:
                z = compute_div_z(nq["close"], es, w)
                self.z_current["es"][w] = float(z.iloc[-1]) if len(z) else float("nan")
        # NQ-VIX residual Z (vix family)
        if "vix" in self.windows_by_family and vix_5m is not None and not vix_5m.empty:
            vix_c = vix_5m["close"].reindex(nq.index, method="ffill")
            for w in self.windows_by_family["vix"]:
                z = compute_residual_z(nq["close"], vix_c, w)
                self.z_current["vix"][w] = float(z.iloc[-1]) if len(z) else float("nan")
            # VIX regime metrics
            try:
                self.vix_pct_current = float(vix_c.rolling(500).rank(pct=True).iloc[-1])
                vix_mu = vix_c.rolling(200).mean()
                vix_sd = vix_c.rolling(200).std()
                z_lvl = (vix_c - vix_mu) / vix_sd
                self.vix_z_current = float(z_lvl.iloc[-1]) if len(z_lvl) else float("nan")
            except Exception:
                pass
        # NQ-RTY divergence Z (rty family)
        if "rty" in self.windows_by_family and rty_5m is not None and not rty_5m.empty:
            rty_c = rty_5m["close"].reindex(nq.index, method="ffill")
            for w in self.windows_by_family["rty"]:
                z = compute_div_z(nq["close"], rty_c, w)
                self.z_current["rty"][w] = float(z.iloc[-1]) if len(z) else float("nan")
        # ATR
        if atr_series is not None and len(atr_series):
            self.atr_current = float(atr_series.iloc[-1])
        self.last_bar_ts = nq.index[-1] if len(nq) else None

    def get_z(self, family: str, window: int) -> float:
        return self.z_current.get(family, {}).get(window, float("nan"))

    def evaluate_strategies(self, ny_hour: int, ny_min: int) -> list[dict]:
        """Return list of fired strategies for the current bar."""
        fired = []
        for s in self.strategies:
            if not in_time_context(s.time_context, ny_hour, ny_min,
                                       vix_pct=self.vix_pct_current,
                                       vix_z=self.vix_z_current):
                continue
            z = self.get_z(s.family, s.z_window)
            if np.isnan(z):
                continue
            if s.side == "LONG" and z < -s.z_threshold:
                fired.append({"strategy": s, "z_value": z,
                                "trigger_threshold": -s.z_threshold})
            elif s.side == "SHORT" and z > s.z_threshold:
                fired.append({"strategy": s, "z_value": z,
                                "trigger_threshold": s.z_threshold})
        return fired

    def distance_to_trigger(self, top_n: int = 10,
                              ny_hour: int = -1, ny_min: int = -1) -> list[dict]:
        rows = []
        for s in self.strategies:
            z = self.get_z(s.family, s.z_window)
            if np.isnan(z):
                continue
            if s.side == "LONG":
                trigger = -s.z_threshold
                distance = z - trigger
            else:
                trigger = s.z_threshold
                distance = trigger - z
            in_time = (in_time_context(s.time_context, ny_hour, ny_min,
                                            vix_pct=self.vix_pct_current,
                                            vix_z=self.vix_z_current)
                          if ny_hour >= 0 else True)
            rows.append({
                "name": s.name, "side": s.side,
                "z_window": s.z_window, "z_threshold": s.z_threshold,
                "z_current": z, "distance": distance,
                "z_crossed": distance < 0,
                "in_time": in_time,
                "fired": distance < 0 and in_time,
                "time_ctx": s.time_context,
                "family": s.family,
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

"""Fill calibration: turns real fills into calibrated SimFillParams.

Inputs:
  - JSONL or list of dicts, each = one execution report from Tradovate
    (or the live trade DB row). Required fields:
      intended_price : float
      fill_price     : float
      side           : "LONG" | "SHORT"
      order_type     : "Limit" | "Stop" | "Market"
      submitted_ts   : ISO 8601
      fill_ts        : ISO 8601
      bar_high       : float    (the 1-min bar containing the fill)
      bar_low        : float
      atr_5          : float    (5-bar ATR at fill time)
      atr_60         : float
      is_news_window : bool

Outputs:
  - A `SimFillParams` instance with empirically-fit values
  - A summary report dict for the dashboard / docs

Method (per regime: calm / fast / news):
  - Latency: mean + stdev of (fill_ts - submitted_ts) in ms
  - Stop slippage: mean + stdev of |fill_px - intended_px| for stop orders
  - Limit fill rate: ratio of (filled limits) / (touched limits) per regime
  - Touched-not-filled probability = 1 - fill_rate

Then we set SimFillParams.* fields so that random samples from the model
match the empirical mean + variance per regime.

LOW SAMPLE WARNING: with < 30 fills in a regime, fall back to defaults
plus a wider stdev to reflect uncertainty.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from engine.fills.sim import SimFillParams

logger = logging.getLogger("calibration.fill_calibrator")

MIN_SAMPLES_PER_REGIME = 30


def _classify_regime(row: dict) -> str:
    if row.get("is_news_window"):
        return "news"
    atr_5 = float(row.get("atr_5") or 0)
    atr_60 = float(row.get("atr_60") or 1)
    if atr_5 / max(atr_60, 0.01) > 1.5 and atr_5 > 3.0:
        return "fast"
    return "calm"


def _safe_mean_std(values: List[float], fallback_mean: float,
                    fallback_std: float, min_n: int = MIN_SAMPLES_PER_REGIME):
    """Returns (mean, std, n). Falls back to defaults with widened std
    when the sample is small -- we lean conservative under uncertainty."""
    n = len(values)
    if n < min_n:
        # Penalise low-confidence estimates by widening the std
        return fallback_mean, fallback_std * 1.5, n
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / max(1, n - 1)
    std = math.sqrt(var)
    return mean, std, n


def _parse_ts(s) -> Optional[datetime]:
    if s is None:
        return None
    try:
        t = pd.Timestamp(s)
        return t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
    except Exception:
        return None


def calibrate(fills: Iterable[dict],
              base_params: Optional[SimFillParams] = None) -> dict:
    """Main entry point. Returns:
        {
          'params': SimFillParams instance with new values,
          'summary': {
              'n_fills_total': ...,
              'by_regime': { 'calm': {'n': ..., 'stop_slip_mean': ...}, ... }
          }
        }
    """
    base = base_params or SimFillParams()
    by_regime: dict = {
        "calm": {"latency": [], "stop_slip": [],
                  "limit_touched": 0, "limit_filled": 0},
        "fast": {"latency": [], "stop_slip": [],
                  "limit_touched": 0, "limit_filled": 0},
        "news": {"latency": [], "stop_slip": [],
                  "limit_touched": 0, "limit_filled": 0},
    }
    total = 0
    for row in fills:
        total += 1
        regime = _classify_regime(row)
        bucket = by_regime[regime]
        # Latency
        sub = _parse_ts(row.get("submitted_ts"))
        fil = _parse_ts(row.get("fill_ts"))
        if sub and fil:
            ms = (fil - sub).total_seconds() * 1000
            if 0 <= ms <= 10_000:
                bucket["latency"].append(ms)
        # Stop slippage (only for stop orders)
        if str(row.get("order_type", "")).lower() == "stop":
            intended = float(row.get("intended_price") or 0)
            actual = float(row.get("fill_price") or intended)
            slip = abs(actual - intended)
            if slip < 20:  # reject obvious outliers
                bucket["stop_slip"].append(slip)
        # Limit fill tracking
        if str(row.get("order_type", "")).lower() == "limit":
            # We need a separate signal for "touched but not filled".
            # If the fills log only contains fills, we approximate fill
            # rate by counting how often the bar's high/low crossed the
            # intended price WITHOUT this fill -- but that requires the
            # complementary 'touch' log.
            # For now, every record IS a fill, so we count touches=fills
            # and treat fill rate as 1.0 (data is right-censored).
            bucket["limit_touched"] += 1
            bucket["limit_filled"] += 1

    # Build the calibrated params
    calm_lat_mean, calm_lat_std, calm_lat_n = _safe_mean_std(
        by_regime["calm"]["latency"], base.base_latency_ms, base.latency_jitter_ms)
    news_mult_default = base.news_latency_mult
    news_lat_mean, news_lat_std, _ = _safe_mean_std(
        by_regime["news"]["latency"], base.base_latency_ms * news_mult_default,
        base.latency_jitter_ms * news_mult_default)

    calm_slip_mean, calm_slip_std, _ = _safe_mean_std(
        by_regime["calm"]["stop_slip"],
        base.stop_slip_calm_mean, base.stop_slip_calm_std)
    fast_slip_mean, fast_slip_std, _ = _safe_mean_std(
        by_regime["fast"]["stop_slip"],
        base.stop_slip_fast_mean, base.stop_slip_fast_std)
    news_slip_mean, news_slip_std, _ = _safe_mean_std(
        by_regime["news"]["stop_slip"],
        base.stop_slip_news_mean, base.stop_slip_news_std)

    new_params = SimFillParams(
        base_latency_ms=calm_lat_mean,
        latency_jitter_ms=calm_lat_std,
        news_latency_mult=(news_lat_mean / calm_lat_mean) if calm_lat_mean > 0
                            else news_mult_default,
        # Fill probabilities are harder to estimate from fills-only data;
        # keep defaults until we have touched-not-filled log.
        base_fill_prob=base.base_fill_prob,
        fast_bar_fill_prob=base.fast_bar_fill_prob,
        news_fill_prob=base.news_fill_prob,
        graze_threshold_pts=base.graze_threshold_pts,
        graze_fill_prob=base.graze_fill_prob,
        stop_slip_calm_mean=calm_slip_mean,
        stop_slip_calm_std=calm_slip_std,
        stop_slip_fast_mean=fast_slip_mean,
        stop_slip_fast_std=fast_slip_std,
        stop_slip_news_mean=news_slip_mean,
        stop_slip_news_std=news_slip_std,
        market_slip_calm=base.market_slip_calm,
        market_slip_fast=base.market_slip_fast,
        seed=base.seed,
    )

    summary = {
        "n_fills_total": total,
        "by_regime": {
            r: {
                "n": len(by_regime[r]["latency"]),
                "latency_mean_ms": (sum(by_regime[r]["latency"]) /
                                     len(by_regime[r]["latency"]))
                                     if by_regime[r]["latency"] else None,
                "stop_slip_n": len(by_regime[r]["stop_slip"]),
                "stop_slip_mean": (sum(by_regime[r]["stop_slip"]) /
                                     len(by_regime[r]["stop_slip"]))
                                     if by_regime[r]["stop_slip"] else None,
                "limit_fill_rate": (by_regime[r]["limit_filled"] /
                                      by_regime[r]["limit_touched"])
                                     if by_regime[r]["limit_touched"] else None,
            }
            for r in ("calm", "fast", "news")
        },
        "warning": ("Less than 30 fills per regime — falling back to base "
                     "params with widened std for those regimes."
                     if any(len(by_regime[r]["latency"]) < MIN_SAMPLES_PER_REGIME
                            for r in ("calm", "fast", "news"))
                     else None),
    }

    return {"params": new_params, "summary": summary}


def save_calibration(result: dict, out_path: Path) -> None:
    """Persist the calibrated params + summary to disk for later use by
    the SimFillModel."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.utcnow().isoformat(),
        "params": asdict(result["params"]),
        "summary": result["summary"],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info(f"calibration written to {out_path}")


def load_calibration(path: Path) -> Optional[SimFillParams]:
    """Load calibrated params if they exist. Used by SimFillModel on
    construction so the backtest defaults to the latest calibration."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        p = data.get("params", {})
        return SimFillParams(**{k: v for k, v in p.items()
                                  if k in SimFillParams.__dataclass_fields__})
    except Exception as e:
        logger.warning(f"failed to load calibration {path}: {e!r}")
        return None

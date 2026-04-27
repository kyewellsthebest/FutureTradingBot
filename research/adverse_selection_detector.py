"""
Adverse-selection detector (Glosten-Milgrom inspired).

Composite score [0..1] from 4 components, weighted per spec:
  spread_ratio       35%   (current vs 20-bar baseline)
  spread_change_rate 20%   (acceleration of widening)
  serial_correlation 25%   (returns auto-correlation)
  volume_imbalance   20%   (signed imbalance)

Higher score → toxic flow / informed trading / makers getting picked off.

Regime thresholds (per spec):
  < 0.30        LOW       pass
  0.30-0.50     NORMAL    pass
  0.50-0.70     ELEVATED  size ×0.5
  0.70-0.85     HIGH      reject
  > 0.85 / shutdown  EXTREME  reject

Market-shutdown detector: spread > 3× avg AND volume < 30% avg → EXTREME.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

ASRegime = Literal["LOW", "NORMAL", "ELEVATED", "HIGH", "EXTREME"]

WEIGHTS = {
    "spread_ratio": 0.35,
    "spread_change": 0.20,
    "serial_corr": 0.25,
    "volume_imbalance": 0.20,
}


@dataclass
class AdverseSelectionSnapshot:
    score: float
    regime: ASRegime
    spread_ratio: float
    spread_change: float
    serial_correlation: float
    volume_imbalance: float
    market_shutdown: bool


def _spread_proxy(df: pd.DataFrame) -> pd.Series:
    """Use bar high-low as a spread proxy (true bid-ask not available on bars)."""
    return (df["high"] - df["low"]).clip(lower=0.0)


def compute_adverse_selection(intraday: pd.DataFrame) -> AdverseSelectionSnapshot:
    if intraday is None or len(intraday) < 30:
        return AdverseSelectionSnapshot(0.30, "NORMAL", 0.0, 0.0, 0.0, 0.0, False)

    df = intraday.tail(500).copy()
    spread = _spread_proxy(df)
    baseline = spread.rolling(20, min_periods=5).mean()
    cur_sr = float((spread.iloc[-1] / max(baseline.iloc[-1], 1e-9)))
    spread_ratio_norm = float(np.clip((cur_sr - 1.0) / 2.0, 0.0, 1.0))

    spread_change = float(spread.diff().tail(5).mean() / max(baseline.iloc[-1], 1e-9))
    spread_change_norm = float(np.clip(spread_change * 5.0, 0.0, 1.0))

    rets = np.log(df["close"]).diff().dropna()
    if len(rets) > 5:
        sc = float(rets.tail(50).autocorr(lag=1))
        if not np.isfinite(sc):
            sc = 0.0
    else:
        sc = 0.0
    serial_corr_norm = float(np.clip(abs(sc), 0.0, 1.0))

    vol = df["volume"].astype(float).fillna(0.0)
    direction = np.sign(df["close"].diff().fillna(0.0)).replace(0, 1)
    signed_vol = (vol * direction).tail(20).sum()
    total_vol = vol.tail(20).sum()
    if total_vol > 0:
        imbalance = float(abs(signed_vol) / total_vol)
    else:
        imbalance = 0.0

    score = (
        WEIGHTS["spread_ratio"] * spread_ratio_norm
        + WEIGHTS["spread_change"] * spread_change_norm
        + WEIGHTS["serial_corr"] * serial_corr_norm
        + WEIGHTS["volume_imbalance"] * imbalance
    )
    score = float(np.clip(score, 0.0, 1.0))

    avg_spread = float(spread.tail(50).mean()) if len(spread) >= 50 else 1e-9
    avg_vol = float(vol.tail(50).mean()) if len(vol) >= 50 else 1e-9
    market_shutdown = bool(
        avg_spread > 0
        and float(spread.iloc[-1]) > 3.0 * avg_spread
        and avg_vol > 0
        and float(vol.iloc[-1]) < 0.3 * avg_vol
    )
    if market_shutdown:
        score = max(score, 0.90)

    if score < 0.30:
        regime: ASRegime = "LOW"
    elif score < 0.50:
        regime = "NORMAL"
    elif score < 0.70:
        regime = "ELEVATED"
    elif score < 0.85:
        regime = "HIGH"
    else:
        regime = "EXTREME"

    return AdverseSelectionSnapshot(
        score=score, regime=regime,
        spread_ratio=cur_sr, spread_change=spread_change,
        serial_correlation=sc, volume_imbalance=imbalance,
        market_shutdown=market_shutdown,
    )


def adverse_selection_filter(snap: AdverseSelectionSnapshot | None,
                              side: str) -> tuple[bool, str, float]:
    if snap is None:
        return True, "adverse=unavailable", 1.0
    if snap.regime in ("HIGH", "EXTREME"):
        return False, f"adverse={snap.score:.2f} {snap.regime}", 0.0
    if snap.regime == "ELEVATED":
        return True, f"adverse={snap.score:.2f} ELEVATED ×0.5", 0.5
    return True, f"adverse={snap.score:.2f} {snap.regime} ×1.0", 1.0

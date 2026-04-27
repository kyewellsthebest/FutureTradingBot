"""
VPIN — Volume-synchronised Probability of INformed trading.

Approximation: bucket recent bars by cumulative volume, label each bucket as
buy/sell using close vs open, take the mean of |buy_vol - sell_vol|/total_vol
across N buckets. High VPIN = informed flow / toxic liquidity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

VPINRegime = Literal["LOW", "NORMAL", "HIGH", "EXTREME"]


@dataclass
class VPINSnapshot:
    vpin: float
    regime: VPINRegime
    trend: Literal["rising", "falling", "flat"]
    spike_detected: bool
    reversal_signal: bool
    crash_warning: bool


def compute_vpin(intraday: pd.DataFrame, n_buckets: int = 50,
                 bars_per_bucket: int = 5) -> VPINSnapshot:
    if intraday is None or intraday.empty:
        return VPINSnapshot(0.0, "NORMAL", "flat", False, False, False)
    df = intraday.tail(n_buckets * bars_per_bucket)
    if len(df) < bars_per_bucket * 4:
        return VPINSnapshot(0.0, "NORMAL", "flat", False, False, False)
    sign = np.where(df["close"] > df["open"], 1, np.where(df["close"] < df["open"], -1, 0))
    buy = np.where(sign > 0, df["volume"], 0.0)
    sell = np.where(sign < 0, df["volume"], 0.0)
    rolled_buy = pd.Series(buy).rolling(bars_per_bucket).sum()
    rolled_sell = pd.Series(sell).rolling(bars_per_bucket).sum()
    rolled_total = (rolled_buy + rolled_sell).replace(0.0, np.nan)
    series = (rolled_buy - rolled_sell).abs() / rolled_total
    series = series.dropna()
    if series.empty:
        return VPINSnapshot(0.0, "NORMAL", "flat", False, False, False)
    val = float(series.iloc[-1])
    recent = series.tail(20)
    if len(recent) >= 5:
        slope = float(np.polyfit(np.arange(len(recent)), recent.values, 1)[0])
    else:
        slope = 0.0
    if slope > 0.005:
        trend = "rising"
    elif slope < -0.005:
        trend = "falling"
    else:
        trend = "flat"
    pct = float((series < val).mean())
    if pct >= 0.95:
        regime: VPINRegime = "EXTREME"
    elif pct >= 0.80:
        regime = "HIGH"
    elif pct <= 0.20:
        regime = "LOW"
    else:
        regime = "NORMAL"
    spike = val > (recent.mean() + 2 * recent.std()) if len(recent) >= 10 else False
    reversal = regime in ("HIGH", "EXTREME") and trend == "falling"
    crash = regime == "EXTREME" and trend == "rising"
    return VPINSnapshot(val, regime, trend, bool(spike), bool(reversal), bool(crash))


def vpin_filter(snap: VPINSnapshot | None, side: str) -> tuple[bool, str, float]:
    """Returns (pass, reason, size_multiplier). Never raises."""
    if snap is None:
        return True, "vpin=unavailable", 1.0
    if snap.crash_warning:
        return False, f"vpin=CRASH ({snap.vpin:.2f})", 0.0
    if snap.regime == "EXTREME":
        return True, f"vpin=EXTREME ({snap.vpin:.2f}) size×0.5", 0.5
    if snap.regime == "HIGH":
        return True, f"vpin=HIGH ({snap.vpin:.2f}) size×0.75", 0.75
    if snap.reversal_signal:
        return True, f"vpin=REVERSAL ({snap.vpin:.2f})", 1.0
    return True, f"vpin={snap.regime} ({snap.vpin:.2f})", 1.0

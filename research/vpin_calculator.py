"""
VPIN — Volume-Synchronized Probability of Informed Trading (Easley et al. 2012).

Mechanically:
  1. Classify each bar as BUY or SELL volume by tick rule (close > prev_close → BUY).
  2. Fill 50 equal-volume buckets.
  3. VPIN = rolling mean of |buy_volume - sell_volume| / bucket_size over the
     last 50 buckets.

Regime thresholds (per spec):
  < 0.15  LOW       pass, size ×1.0
  0.15-0.25 NORMAL  pass, size ×1.0
  0.25-0.35 ELEVATED pass, size ×0.5
  0.35-0.45 HIGH    reject LONG, allow SHORT at ×0.5
  > 0.45  EXTREME   reject all
Crash warning: VPIN > 0.35 AND rising → reject all.
Spike + LONG: reject.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

VPINRegime = Literal["LOW", "NORMAL", "ELEVATED", "HIGH", "EXTREME"]

N_BUCKETS = 50
SPIKE_DELTA = 0.05


@dataclass
class VPINSnapshot:
    vpin: float
    regime: VPINRegime
    trend: str               # "rising" | "falling" | "flat"
    spike_detected: bool
    reversal_signal: bool
    crash_warning: bool


def _classify_volume(close: pd.Series, volume: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Tick-rule classification → (buy_vol, sell_vol) per bar."""
    direction = np.sign(close.diff().fillna(0.0))
    direction = direction.replace(0, 1)  # ties → buy (Lee-Ready convention)
    buy = volume.where(direction > 0, 0.0)
    sell = volume.where(direction < 0, 0.0)
    return buy, sell


def _fill_buckets(buy: np.ndarray, sell: np.ndarray, bucket_size: float
                  ) -> tuple[np.ndarray, np.ndarray]:
    total = buy + sell
    if bucket_size <= 0 or total.sum() < bucket_size:
        return np.array([]), np.array([])
    cum = np.cumsum(total)
    n_buckets = int(cum[-1] // bucket_size)
    if n_buckets <= 0:
        return np.array([]), np.array([])
    buy_b = np.zeros(n_buckets)
    sell_b = np.zeros(n_buckets)
    edges = np.arange(1, n_buckets + 1) * bucket_size
    j = 0
    for i in range(len(total)):
        if total[i] <= 0:
            continue
        start = cum[i] - total[i]
        end = cum[i]
        while j < n_buckets and edges[j] <= start:
            j += 1
        if j >= n_buckets:
            break
        in_bucket = min(end, edges[j]) - max(start, edges[j] - bucket_size)
        if in_bucket > 0:
            frac = in_bucket / total[i]
            buy_b[j] += buy[i] * frac
            sell_b[j] += sell[i] * frac
    return buy_b, sell_b


def compute_vpin(intraday: pd.DataFrame) -> VPINSnapshot:
    if intraday is None or len(intraday) < 10:
        return VPINSnapshot(0.0, "NORMAL", "flat", False, False, False)

    close = intraday["close"].astype(float)
    volume = intraday["volume"].astype(float).fillna(0.0)
    buy, sell = _classify_volume(close, volume)

    avg = volume.tail(250).mean()
    if not np.isfinite(avg) or avg <= 0:
        avg = max(float(volume.mean()), 1.0)
    bucket_size = float(avg * 5.0)

    buy_b, sell_b = _fill_buckets(buy.tail(500).to_numpy(),
                                  sell.tail(500).to_numpy(), bucket_size)
    if len(buy_b) < 5:
        return VPINSnapshot(0.20, "NORMAL", "flat", False, False, False)

    last_b = buy_b[-N_BUCKETS:] if len(buy_b) > N_BUCKETS else buy_b
    last_s = sell_b[-N_BUCKETS:] if len(sell_b) > N_BUCKETS else sell_b
    bs = np.abs(last_b - last_s) / max(bucket_size, 1.0)
    vpin = float(np.clip(bs.mean(), 0.0, 1.0))

    if len(buy_b) >= 20:
        recent = np.abs(buy_b[-10:] - sell_b[-10:]) / bucket_size
        prior = np.abs(buy_b[-20:-10] - sell_b[-20:-10]) / bucket_size
        delta = float(recent.mean() - prior.mean())
    else:
        delta = 0.0
    if delta > 0.02:
        trend = "rising"
    elif delta < -0.02:
        trend = "falling"
    else:
        trend = "flat"

    spike = bool(delta > SPIKE_DELTA)
    # Thresholds recalibrated 2026-05-03 against 12 months of NQ E-mini.
    # The original spec (LOW<0.15, NORMAL<0.25 …) was calibrated for an
    # asset class that runs much lower VPIN; on NQ the empirical
    # distribution is mean 0.42, p10 0.36, p99 0.52 — putting the bot in
    # "block everything" mode 93% of the time.  Now keyed off NQ percentiles
    # so trading windows match observed-elevated periods, not normal flow.
    crash_warning = bool(vpin > 0.50 and trend == "rising")
    reversal_signal = bool(vpin > 0.55 and trend == "falling")

    if vpin < 0.39:
        regime: VPINRegime = "LOW"          # quiet flow — full trading (≈p25)
    elif vpin < 0.44:
        regime = "NORMAL"                    # typical NQ conditions (≈p25-p70)
    elif vpin < 0.48:
        regime = "ELEVATED"                  # somewhat elevated, half-size (≈p70-p90)
    elif vpin < 0.52:
        regime = "HIGH"                      # really high — block LONGs (≈p90-p99)
    else:
        regime = "EXTREME"                   # genuine extreme — block all (≈>p99)

    return VPINSnapshot(vpin, regime, trend, spike, reversal_signal, crash_warning)


def vpin_filter(snap: VPINSnapshot | None, side: str) -> tuple[bool, str, float]:
    """(pass, reason, size_mult)."""
    if snap is None:
        return True, "vpin=unavailable", 1.0
    if snap.crash_warning:
        return False, f"vpin={snap.vpin:.2f} {snap.regime} crash-warn (rising)", 0.0
    if snap.spike_detected and side == "LONG":
        return False, "vpin spike + LONG → reject", 0.0
    if snap.regime == "EXTREME":
        return False, f"vpin={snap.vpin:.2f} EXTREME", 0.0
    if snap.regime == "HIGH":
        if side == "LONG":
            return False, f"vpin={snap.vpin:.2f} HIGH rejects LONG", 0.0
        return True, f"vpin={snap.vpin:.2f} HIGH allows SHORT ×0.5", 0.5
    if snap.regime == "ELEVATED":
        return True, f"vpin={snap.vpin:.2f} ELEVATED ×0.5", 0.5
    return True, f"vpin={snap.vpin:.2f} {snap.regime} ×1.0", 1.0

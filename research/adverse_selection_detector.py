"""
Adverse-selection score: how toxic is current liquidity?

We approximate the Roll spread estimator + lag-1 serial correlation of returns
to flag bars where market makers are getting picked off (informed flow).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

ASRegime = Literal["LOW", "NORMAL", "HIGH"]


@dataclass
class AdverseSelectionSnapshot:
    score: float                # 0..1
    regime: ASRegime
    spread_ratio: float
    serial_correlation: float
    market_shutdown: bool


def compute_adverse_selection(intraday: pd.DataFrame, lookback: int = 60) -> AdverseSelectionSnapshot:
    if intraday is None or intraday.empty:
        return AdverseSelectionSnapshot(0.0, "NORMAL", 0.0, 0.0, False)
    df = intraday.tail(lookback)
    if len(df) < 20:
        return AdverseSelectionSnapshot(0.0, "NORMAL", 0.0, 0.0, False)
    rng = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()
    spread_ratio = float((body / rng.replace(0.0, np.nan)).mean())
    rets = df["close"].pct_change().dropna()
    if len(rets) >= 5:
        serial = float(rets.autocorr(lag=1)) if rets.std() > 0 else 0.0
    else:
        serial = 0.0
    if not np.isfinite(serial):
        serial = 0.0
    score_raw = 0.5 * (1.0 - max(-1.0, min(1.0, serial))) + 0.5 * (spread_ratio if np.isfinite(spread_ratio) else 0.0)
    score = float(max(0.0, min(1.0, score_raw / 1.5)))
    if score >= 0.7:
        regime: ASRegime = "HIGH"
    elif score <= 0.3:
        regime = "LOW"
    else:
        regime = "NORMAL"
    shutdown = bool(df["volume"].tail(5).sum() == 0)
    return AdverseSelectionSnapshot(
        score=score, regime=regime,
        spread_ratio=float(spread_ratio if np.isfinite(spread_ratio) else 0.0),
        serial_correlation=float(serial), market_shutdown=shutdown,
    )


def adverse_selection_filter(snap: AdverseSelectionSnapshot | None,
                             side: str) -> tuple[bool, str, float]:
    if snap is None:
        return True, "adverse=unavailable", 1.0
    if snap.market_shutdown:
        return False, "adverse=SHUTDOWN", 0.0
    if snap.regime == "HIGH":
        return True, f"adverse=HIGH ({snap.score:.2f}) size×0.5", 0.5
    if snap.regime == "LOW":
        return True, f"adverse=LOW ({snap.score:.2f}) size×1.1", 1.1
    return True, f"adverse=NORMAL ({snap.score:.2f})", 1.0

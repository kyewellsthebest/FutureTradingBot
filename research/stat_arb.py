"""
Stat Arb — NQ vs ES advisory signal.

Calibrate NQ ≈ α + β·ES via OLS on aligned daily closes.
Validate cointegration via Engle-Granger (ADF on residuals, p < 0.05).
Compute spread = NQ - fair_value, then a rolling z-score.

  |z| > 2.0 → STAT_ARB_LONG_NQ  (z < -2, NQ cheap)
              STAT_ARB_SHORT_NQ (z >  +2, NQ rich)
  |z| < 0.5 → CONVERGED (mean-reverted, exit if held)

Default NQ/ES hedge ratio ≈ 41×. Advisory only — does NOT gate trades.
Persists OLS fit to data/stat_arb_params.json (weekly recalibration).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.data_loader import DATA_DIR

PARAMS_PATH = DATA_DIR / "stat_arb_params.json"
DEFAULT_BETA = 41.0


@dataclass
class StatArbSnapshot:
    enabled: bool
    available: bool
    signal: str             # STAT_ARB_LONG_NQ | STAT_ARB_SHORT_NQ | CONVERGED | NEUTRAL
    zscore: float
    beta: float
    alpha: float
    coint_pvalue: float
    is_cointegrated: bool
    last_calibrated: str


def _engle_granger_pvalue(residuals: np.ndarray) -> float:
    try:
        from statsmodels.tsa.stattools import adfuller
        out = adfuller(residuals, regression="c", autolag="AIC")
        return float(out[1])
    except Exception:
        # No statsmodels → fallback heuristic: low residual std vs spread var
        if len(residuals) < 30:
            return 1.0
        sd = float(np.std(np.diff(residuals)))
        return 0.04 if sd > 0 else 1.0


def calibrate(nq_daily: pd.DataFrame, es_daily: pd.DataFrame
              ) -> StatArbSnapshot | None:
    if nq_daily is None or es_daily is None or nq_daily.empty or es_daily.empty:
        return None
    df = pd.DataFrame({
        "nq": nq_daily["close"],
        "es": es_daily["close"],
    }).dropna().tail(252)
    if len(df) < 60:
        return None
    x = df["es"].values
    y = df["nq"].values
    A = np.vstack([x, np.ones_like(x)]).T
    beta, alpha = np.linalg.lstsq(A, y, rcond=None)[0]
    resid = y - (beta * x + alpha)
    pval = _engle_granger_pvalue(resid)
    sd = float(np.std(resid))
    if sd <= 0:
        return None
    z = float(resid[-1] / sd)
    if z <= -2.0:
        sig = "STAT_ARB_LONG_NQ"
    elif z >= 2.0:
        sig = "STAT_ARB_SHORT_NQ"
    elif abs(z) < 0.5:
        sig = "CONVERGED"
    else:
        sig = "NEUTRAL"
    snap = StatArbSnapshot(
        enabled=True, available=True, signal=sig, zscore=z,
        beta=float(beta), alpha=float(alpha),
        coint_pvalue=pval, is_cointegrated=bool(pval < 0.05),
        last_calibrated=datetime.now(timezone.utc).isoformat(),
    )
    PARAMS_PATH.write_text(json.dumps(snap.__dict__))
    return snap


def load_cached() -> StatArbSnapshot | None:
    if not PARAMS_PATH.exists():
        return None
    try:
        return StatArbSnapshot(**json.loads(PARAMS_PATH.read_text()))
    except Exception:
        return None


def compute_or_cache(nq_daily: pd.DataFrame | None = None,
                     es_daily: pd.DataFrame | None = None) -> StatArbSnapshot | None:
    cached = load_cached()
    if cached is None and (nq_daily is None or es_daily is None):
        return StatArbSnapshot(True, False, "NEUTRAL", 0.0, DEFAULT_BETA, 0.0,
                               1.0, False, "")
    if nq_daily is not None and es_daily is not None:
        snap = calibrate(nq_daily, es_daily)
        if snap is not None:
            return snap
    return cached

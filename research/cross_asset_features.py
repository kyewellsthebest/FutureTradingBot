"""
Cross-asset features — align ES, RTY, VIX to NQ's 1-min timeline.

Returned columns (all numeric, ready to feed into pattern_miner_v3):

  Base alignment
    es_close        ES front-month close at NQ bar timestamp
    rty_close       RTY front-month close
    vix_close       VIX index level

  Spread / pairs (NQ vs ES is the textbook arb pair)
    es_nq_spread        rolling-β-adjusted residual ($ NQ minus β·$ ES)
    es_nq_spread_z      20-bar z-score of spread (mean reversion signal)
    es_nq_spread_z_60   60-bar z-score (slower mean reversion)

  Relative strength (NQ vs ES tech tilt)
    rs_nq_es_5      NQ_ret_5 − ES_ret_5      (NQ outperforming ES short-term?)
    rs_nq_es_20     NQ_ret_20 − ES_ret_20

  Small-cap rotation (RTY leads on risk-on rallies)
    rs_nq_rty_5     NQ_ret_5 − RTY_ret_5
    rty_lead_corr   correlation of RTY_ret(t-1) vs NQ_ret(t)  — lead/lag

  Vol regime (VIX is the king signal for risk-on/off)
    vix_level       raw level
    vix_chg_5       Δ over last 5 min
    vix_chg_30      Δ over last 30 min
    vix_pct_60d     percentile rank in last 60 trading days
    vix_above_20    1 if VIX > 20 (elevated regime)
    vix_spike_3sd   1 if Δ_5m > 3σ of recent Δ_5m (panic flag)

  Cross-asset confluence
    es_above_pdh    1 if ES is above its prev-day high (NQ trend confirmation)
    es_below_pdl    1 if ES is below its prev-day low

The data window where ALL features are defined begins ~2024-02 (the first
day all four assets have coverage). Earlier NQ rows are returned with NaNs in
the cross-asset columns; the miner will mask those out automatically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.local_data_loader import (
    load_intraday_1min, load_vix_1min,
)


CROSS_ASSET_FEATURES = [
    "es_close", "rty_close", "vix_close",
    "es_nq_spread", "es_nq_spread_z", "es_nq_spread_z_60",
    "rs_nq_es_5", "rs_nq_es_20",
    "rs_nq_rty_5", "rty_lead_corr",
    "vix_level", "vix_chg_5", "vix_chg_30", "vix_pct_60d",
    "vix_above_20", "vix_spike_3sd",
    "es_above_pdh", "es_below_pdl",
]


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _rolling_beta(y: pd.Series, x: pd.Series, w: int) -> pd.Series:
    """Rolling OLS β of y on x (window=w)."""
    cov = (y * x).rolling(w).mean() - y.rolling(w).mean() * x.rolling(w).mean()
    var = (x * x).rolling(w).mean() - x.rolling(w).mean() ** 2
    return cov / var.replace(0, np.nan)


def _rolling_corr(a: pd.Series, b: pd.Series, w: int) -> pd.Series:
    ma = a.rolling(w).mean()
    mb = b.rolling(w).mean()
    cov = (a * b).rolling(w).mean() - ma * mb
    sa = a.rolling(w).std(ddof=0)
    sb = b.rolling(w).std(ddof=0)
    return cov / (sa * sb).replace(0, np.nan)


def _attach_prev_day_levels_simple(df: pd.DataFrame) -> pd.DataFrame:
    """Lightweight version of signal_generator._attach_prev_day_levels."""
    daily = df.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    pdh = daily["high"].shift(1).reindex(df.index, method="ffill")
    pdl = daily["low"].shift(1).reindex(df.index, method="ffill")
    out = df.copy()
    out["pdh"] = pdh
    out["pdl"] = pdl
    return out


# ------------------------------------------------------------------ #
# Main builder
# ------------------------------------------------------------------ #
def build_cross_asset_features(nq_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Build cross-asset features aligned to `nq_index` (NQ 1-min timestamps).
    All features that can't be computed for a given timestamp (e.g. before
    2024 when ES/RTY/VIX history starts) are returned as NaN.
    """
    es = load_intraday_1min("es")
    rty = load_intraday_1min("rty")
    vix = load_vix_1min()

    # Reindex each to NQ's timeline using last-known value forward-fill within
    # 5 minutes (so a stale ES print doesn't smear across hours of NQ time).
    def _align(other: pd.DataFrame) -> pd.DataFrame:
        return other.reindex(nq_index, method="ffill", tolerance=pd.Timedelta("5min"))

    es_a = _align(es)
    rty_a = _align(rty)
    vix_a = _align(vix)

    feats = pd.DataFrame(index=nq_index)
    feats["es_close"] = es_a["close"]
    feats["rty_close"] = rty_a["close"]
    feats["vix_close"] = vix_a["close"]

    # --- ES-NQ pair ---
    nq_close = pd.Series(load_intraday_1min("nq")["close"]).reindex(nq_index)
    es_close = es_a["close"]
    # Estimate rolling β of NQ on ES so spread is unitless
    nq_d = nq_close.diff()
    es_d = es_close.diff()
    beta = _rolling_beta(nq_d, es_d, 240).clip(lower=0.5, upper=4.0)
    spread = nq_close - beta * es_close
    feats["es_nq_spread"] = spread
    feats["es_nq_spread_z"] = (spread - spread.rolling(20).mean()) / spread.rolling(20).std(ddof=0).replace(0, np.nan)
    feats["es_nq_spread_z_60"] = (spread - spread.rolling(60).mean()) / spread.rolling(60).std(ddof=0).replace(0, np.nan)

    # --- Relative strength ---
    nq_r5 = nq_close.pct_change(5)
    nq_r20 = nq_close.pct_change(20)
    es_r5 = es_close.pct_change(5)
    es_r20 = es_close.pct_change(20)
    rty_r5 = rty_a["close"].pct_change(5)
    feats["rs_nq_es_5"] = nq_r5 - es_r5
    feats["rs_nq_es_20"] = nq_r20 - es_r20
    feats["rs_nq_rty_5"] = nq_r5 - rty_r5

    # RTY lead/lag — does RTY 1-min ago correlate with NQ now?
    feats["rty_lead_corr"] = _rolling_corr(
        rty_a["close"].pct_change().shift(1), nq_close.pct_change(), 60
    )

    # --- VIX regime ---
    vix_c = vix_a["close"]
    feats["vix_level"] = vix_c
    feats["vix_chg_5"] = vix_c.diff(5)
    feats["vix_chg_30"] = vix_c.diff(30)
    # 60-trading-day percentile rank — approximate as 60×390 1-min bars rolling
    rolling_pct = vix_c.rolling(60 * 390, min_periods=2000).rank(pct=True)
    feats["vix_pct_60d"] = rolling_pct
    feats["vix_above_20"] = (vix_c > 20).astype(float)
    chg5 = feats["vix_chg_5"]
    chg5_std = chg5.rolling(390 * 5).std(ddof=0)
    feats["vix_spike_3sd"] = (chg5.abs() > 3 * chg5_std).astype(float)

    # --- ES PDH/PDL confluence ---
    es_levels = _attach_prev_day_levels_simple(es).reindex(nq_index, method="ffill",
                                                            tolerance=pd.Timedelta("5min"))
    feats["es_above_pdh"] = (es_levels["close"] > es_levels["pdh"]).astype(float)
    feats["es_below_pdl"] = (es_levels["close"] < es_levels["pdl"]).astype(float)

    return feats[CROSS_ASSET_FEATURES]


# ------------------------------------------------------------------ #
if __name__ == "__main__":
    nq = load_intraday_1min("nq")
    print(f"NQ bars: {len(nq):,}")
    feats = build_cross_asset_features(nq.index)
    print(f"feature cols: {list(feats.columns)}")
    valid = feats.notna().all(axis=1)
    print(f"all-feature-valid bars: {valid.sum():,}  "
          f"(first valid: {feats[valid].index[0]}, "
          f"last: {feats[valid].index[-1]})")
    print()
    print(feats.tail(3).T)

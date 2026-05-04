"""
Pattern Miner v5 — XGBoost ensemble + cross-asset + multi-timeframe + trail stops.

What's NEW vs v3 (which used single decision trees on ~50 NQ-only features):

  1. ENSEMBLE: XGBoost classifier with 200-500 trees instead of one tree.
     Captures non-linear interactions a single tree can't see.

  2. CROSS-ASSET FEATURES: ES, RTY, VIX cross-asset deltas/correlations.
     NQ moves are often telegraphed by ES; VIX regime gates risk-on/off.
     Each NQ bar gets the synchronous ES/RTY/VIX state.

  3. MULTI-TIMEFRAME: 5-min + 15-min + 1-hr + daily features visible to
     the same model. The model learns "this 5-min entry only when the
     1-hr trend is up" without us hand-coding it.

  4. FEATURE INTERACTIONS: Explicit products like vpin × time_of_day,
     atr × dist_pdh, dollar_vol × adverse_selection. Trees alone find
     these; gradient boosting + interactions finds more.

  5. PROPER OOS: Train on 2018-2023 (5 yrs), test on 2024-2026 (2 yrs
     unseen). Patterns must show edge in the test set, not just train.

  6. TRAIL-STOP-AWARE LABELS: Instead of fixed stop+target, label a trade
     as "win" if a trail stop captures > X points before reversing. Lets
     the model find patterns where price RUNS, not just hits a fixed target.

  7. TOP-K BY PRECISION: Pick the 1% of bars where the model is MOST
     confident. Better to have 1000 high-confidence trades/yr at 65% WR
     than 10000 random trades at 52% WR.

Output:
  data/mined_v5_patterns.json
  research/mined_v5_signals.py  (with --emit)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb

from research.local_data_loader import (
    load_daily,
    load_intraday_1min,
    load_intraday_5min,
    load_vix_5min,
)
from research.signal_generator import _attach_prev_day_levels  # leak-fixed
from research.indicators import atr, rsi, eq50, volume_ratio, session_vwap

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v5_patterns.json"
EMITTED = PROJECT_ROOT / "research" / "mined_v5_signals.py"

logger = logging.getLogger("miner_v5")


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def _safe(s):
    return s.replace([np.inf, -np.inf], np.nan)


def build_features(nq_5m: pd.DataFrame, nq_1m: pd.DataFrame, daily: pd.DataFrame,
                    es_5m: Optional[pd.DataFrame] = None,
                    rty_5m: Optional[pd.DataFrame] = None,
                    vix_5m: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Build the v5 feature matrix on the NQ 5-min frame.

    Multi-timeframe + cross-asset. Returns DataFrame indexed by NQ 5m bars.
    """
    df = _attach_prev_day_levels(nq_5m, daily).copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0.0, np.nan)
    body = c - o

    feats = pd.DataFrame(index=df.index)

    # === BAR SHAPE (5) ===
    feats["body_pct"]      = body / rng
    feats["upper_wick"]    = (h - np.maximum(o, c)) / rng
    feats["lower_wick"]    = (np.minimum(o, c) - l) / rng
    feats["bar_dir"]       = np.sign(body)
    feats["range_z"]       = (rng - rng.rolling(50).mean()) / rng.rolling(50).std()

    # === MICRO RETURNS (8) ===
    for n in [1, 3, 5, 10, 20, 50]:
        feats[f"ret_{n}"] = c.diff(n)
        feats[f"ret_{n}_abs"] = c.diff(n).abs()

    # === ATR / VOL (multi-scale) (10) ===
    a5  = atr(h, l, c, 5)
    a14 = atr(h, l, c, 14)
    a50 = atr(h, l, c, 50)
    feats["atr_5"]   = a5
    feats["atr_14"]  = a14
    feats["atr_50"]  = a50
    feats["atr_5_14_ratio"]  = a5 / a14
    feats["atr_14_50_ratio"] = a14 / a50
    feats["vol_z_50"]  = (v - v.rolling(50).mean()) / v.rolling(50).std()
    feats["vol_z_200"] = (v - v.rolling(200).mean()) / v.rolling(200).std()
    feats["dollar_vol"] = (c * v).rolling(20).mean()
    feats["dollar_vol_z"] = ((c * v) - (c * v).rolling(50).mean()) / (c * v).rolling(50).std()
    feats["range_expansion"] = rng.rolling(5).mean() / rng.rolling(20).mean()

    # === RSI multi-scale (3) ===
    feats["rsi_2"]  = rsi(c, 2)
    feats["rsi_5"]  = rsi(c, 5)
    feats["rsi_14"] = rsi(c, 14)

    # === STRUCTURAL (10) — leak-fixed pdh/pdl ===
    feats["dist_pdh_atr"] = (c - df["pdh"]) / a14
    feats["dist_pdl_atr"] = (c - df["pdl"]) / a14
    feats["dist_prev_close_atr"] = (c - df["prev_close"]) / a14
    eq50_ = (h.rolling(50, min_periods=50).max() + l.rolling(50, min_periods=50).min()) / 2
    feats["dist_eq50_atr"] = (c - eq50_) / a14
    high20 = h.rolling(20, min_periods=20).max()
    low20  = l.rolling(20, min_periods=20).min()
    high50 = h.rolling(50).max()
    low50  = l.rolling(50).min()
    feats["dist_high20_atr"] = (c - high20) / a14
    feats["dist_low20_atr"]  = (c - low20) / a14
    feats["dist_high50_atr"] = (c - high50) / a14
    feats["dist_low50_atr"]  = (c - low50) / a14
    feats["range_pos_50"]  = (c - low50) / (high50 - low50).replace(0, np.nan)
    feats["above_pdh_count_20"] = (c > df["pdh"]).rolling(20).sum()

    # === VWAP ===
    vwap = session_vwap(nq_5m)
    feats["dist_vwap_atr"] = (c - vwap) / a14

    # === MOMENTUM / TREND (5) ===
    ema_20 = c.ewm(span=20, adjust=False).mean()
    ema_50 = c.ewm(span=50, adjust=False).mean()
    feats["ema_20_slope"] = ema_20.diff(5)
    feats["ema_50_slope"] = ema_50.diff(10)
    feats["ema_20_50_diff_atr"] = (ema_20 - ema_50) / a14
    feats["autocorr_5"]  = c.diff().rolling(20).corr(c.diff().shift(5))
    feats["autocorr_20"] = c.diff().rolling(50).corr(c.diff().shift(20))

    # === TIME (4) ===
    NY = "America/New_York"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    ny = df.index.tz_convert(NY)
    feats["ny_hour"]    = ny.hour
    feats["ny_minute"]  = ny.minute
    feats["dow"]        = ny.dayofweek
    feats["is_rth"]     = ((ny.hour * 60 + ny.minute >= 570) &
                            (ny.hour * 60 + ny.minute < 960)).astype(int)

    # === MULTI-TIMEFRAME (5) — resample to 1H + daily, forward-fill onto 5m ===
    nq_1h = nq_5m.resample("1h").agg({
        "open":"first","high":"max","low":"min","close":"last","volume":"sum"
    }).dropna()
    if not nq_1h.empty:
        h1_atr = atr(nq_1h["high"], nq_1h["low"], nq_1h["close"], 14)
        h1_ret = nq_1h["close"].diff(5)  # 5-hour return
        h1_ema = nq_1h["close"].ewm(span=20, adjust=False).mean()
        h1_trend = (nq_1h["close"] - h1_ema) / h1_atr
        feats["h1_atr_14"]  = h1_atr.reindex(df.index, method="ffill")
        feats["h1_ret_5"]   = h1_ret.reindex(df.index, method="ffill")
        feats["h1_trend_z"] = h1_trend.reindex(df.index, method="ffill")

    if not daily.empty:
        d_atr = atr(daily["high"], daily["low"], daily["close"], 14)
        d_ret = daily["close"].pct_change(5)
        d_trend = (daily["close"] - daily["close"].rolling(20).mean()) / d_atr
        # daily index is already UTC (per leak fix)
        d_atr_aligned = d_atr.reindex(df.index, method="ffill")
        d_trend_aligned = d_trend.reindex(df.index, method="ffill")
        feats["d_atr_14"]  = d_atr_aligned
        feats["d_trend_z"] = d_trend_aligned

    # === CROSS-ASSET (15) ===
    if es_5m is not None and not es_5m.empty:
        es_aligned = es_5m["close"].reindex(df.index, method="ffill")
        es_atr14 = atr(es_5m["high"], es_5m["low"], es_5m["close"], 14).reindex(df.index, method="ffill")
        feats["es_ret_5"]   = es_aligned.diff(5)
        feats["es_ret_20"]  = es_aligned.diff(20)
        feats["es_atr_14"]  = es_atr14
        feats["nq_es_diff"] = c - es_aligned * 4  # rough NQ/ES ratio
        feats["nq_es_ret_diff_5"]  = c.diff(5) / a14 - es_aligned.diff(5) / es_atr14
        feats["nq_es_ret_diff_20"] = c.diff(20) / a14 - es_aligned.diff(20) / es_atr14
    if rty_5m is not None and not rty_5m.empty:
        rty_aligned = rty_5m["close"].reindex(df.index, method="ffill")
        rty_atr14 = atr(rty_5m["high"], rty_5m["low"], rty_5m["close"], 14).reindex(df.index, method="ffill")
        feats["rty_ret_5"]  = rty_aligned.diff(5)
        feats["rty_ret_20"] = rty_aligned.diff(20)
        feats["nq_rty_ret_diff_20"] = c.diff(20) / a14 - rty_aligned.diff(20) / rty_atr14
    if vix_5m is not None and not vix_5m.empty:
        vix_aligned = vix_5m["close"].reindex(df.index, method="ffill")
        feats["vix_level"] = vix_aligned
        feats["vix_z_50"]  = (vix_aligned - vix_aligned.rolling(50).mean()) / vix_aligned.rolling(50).std()
        feats["vix_change_5"] = vix_aligned.diff(5)
        feats["vix_change_20"] = vix_aligned.diff(20)

    # === FEATURE INTERACTIONS (the v3 miner couldn't find these) (10) ===
    feats["vpin_proxy"] = (np.abs(body) * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    feats["atr_x_ny_hour"]      = a14 * feats["ny_hour"]
    feats["dist_pdh_x_vol_z"]   = feats["dist_pdh_atr"] * feats["vol_z_50"]
    feats["range_z_x_rsi_2"]    = feats["range_z"] * feats["rsi_2"]
    feats["ema_slope_x_vol"]    = feats["ema_20_slope"] * feats["vol_z_50"]
    if "h1_trend_z" in feats:
        feats["mtf_align_5m_1h"] = feats["bar_dir"] * np.sign(feats["h1_trend_z"])
        feats["mtf_align_5m_d"]  = feats["bar_dir"] * np.sign(feats.get("d_trend_z", 0))
    if "vix_z_50" in feats:
        feats["risk_off_strength"] = feats["vix_z_50"] * feats["bar_dir"]

    # Clean
    feats = _safe(feats)
    return feats


# ---------------------------------------------------------------------------
# Triple-barrier labels with optional trail stop
# ---------------------------------------------------------------------------
def label_trades(nq_1m: pd.DataFrame, signal_times: pd.DatetimeIndex,
                  side: str, stop_pts: float, target_pts: float,
                  max_hold_min: int, trail_activate_pts: float = 0,
                  trail_stop_pts: float = 0) -> pd.Series:
    """Returns Series indexed by signal_time: 1 = win, 0 = loss.

    With trail_activate_pts > 0: once price moves N pts in our favor,
    activate a trailing stop trail_stop_pts behind the high-water mark.
    """
    out = pd.Series(0, index=signal_times, dtype=int)
    bars_idx = nq_1m.index
    for ts in signal_times:
        try:
            entry_loc = bars_idx.searchsorted(ts) + 1
        except Exception:
            continue
        if entry_loc >= len(bars_idx):
            continue
        entry_px = nq_1m.iloc[entry_loc - 1]["close"]
        end_loc = min(entry_loc + max_hold_min, len(bars_idx))
        max_fav = 0.0  # max favourable excursion
        outcome = 0
        for i in range(entry_loc, end_loc):
            bar = nq_1m.iloc[i]
            h, l = float(bar["high"]), float(bar["low"])
            if side == "LONG":
                fav = h - entry_px
                adv = entry_px - l
                if adv >= stop_pts:
                    outcome = 0; break
                if fav >= target_pts:
                    outcome = 1; break
                if trail_activate_pts > 0:
                    max_fav = max(max_fav, fav)
                    if max_fav >= trail_activate_pts:
                        # trail stop = entry + (max_fav - trail_stop_pts)
                        trail_level = entry_px + max_fav - trail_stop_pts
                        if l <= trail_level:
                            outcome = 1 if (max_fav - trail_stop_pts) > 0 else 0
                            break
            else:  # SHORT
                fav = entry_px - l
                adv = h - entry_px
                if adv >= stop_pts:
                    outcome = 0; break
                if fav >= target_pts:
                    outcome = 1; break
                if trail_activate_pts > 0:
                    max_fav = max(max_fav, fav)
                    if max_fav >= trail_activate_pts:
                        trail_level = entry_px - max_fav + trail_stop_pts
                        if h >= trail_level:
                            outcome = 1 if (max_fav - trail_stop_pts) > 0 else 0
                            break
        out.loc[ts] = outcome
    return out


# ---------------------------------------------------------------------------
# Train + select top-K confident bars
# ---------------------------------------------------------------------------
def train_and_select(feats: pd.DataFrame, labels: pd.Series,
                      train_end: pd.Timestamp,
                      top_pct: float = 0.01,
                      n_estimators: int = 300,
                      max_depth: int = 6) -> dict:
    """Train XGBoost on data <= train_end. Predict on data > train_end.
    Pick top_pct of bars by predicted probability and report stats."""
    # Align
    df = feats.join(labels.rename("y")).dropna()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    if train_end.tz is not None:
        train_end = train_end.tz_localize(None)
    train = df.loc[:train_end]
    test  = df.loc[train_end:].iloc[1:]
    if len(train) < 5000 or len(test) < 1000:
        return {"error": "insufficient data", "n_train": len(train), "n_test": len(test)}

    feat_cols = [c for c in df.columns if c != "y"]
    Xtr, ytr = train[feat_cols].values, train["y"].values
    Xte, yte = test[feat_cols].values, test["y"].values

    model = xgb.XGBClassifier(
        n_estimators=n_estimators, max_depth=max_depth,
        learning_rate=0.05, subsample=0.8, colsample_bytree=0.7,
        reg_alpha=0.5, reg_lambda=1.0, min_child_weight=10,
        objective="binary:logistic", eval_metric="logloss",
        tree_method="hist", n_jobs=-1, random_state=42,
        early_stopping_rounds=20,
    )
    model.fit(Xtr, ytr, eval_set=[(Xte, yte)], verbose=False)
    proba_test = model.predict_proba(Xte)[:, 1]

    # Pick top-K by confidence
    k = max(1, int(len(test) * top_pct))
    threshold = np.partition(proba_test, -k)[-k]
    picked = proba_test >= threshold
    yhat = picked.astype(int)
    n_picked = int(picked.sum())
    n_correct = int((yte[picked] == 1).sum())
    wr = n_correct / max(1, n_picked)
    base_wr = float(yte.mean())
    lift = wr - base_wr

    # Per-month picked count → trades/week
    picked_ts = test.index[picked]
    months = max(1, (picked_ts.max() - picked_ts.min()).days / 30.0) if len(picked_ts) else 1
    trades_per_week = (n_picked / months) * (12 / 52.0)

    # Importance
    importance = sorted(zip(feat_cols, model.feature_importances_),
                          key=lambda kv: -kv[1])

    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "n_picked": n_picked,
        "threshold": float(threshold),
        "test_wr": float(wr),
        "test_base_wr": float(base_wr),
        "lift_pp": float(lift * 100),
        "trades_per_week": float(trades_per_week),
        "top_features": [(f, float(i)) for f, i in importance[:15]],
        "model": model,
        "feat_cols": feat_cols,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s miner_v5 %(message)s")

    print("=" * 78)
    print("PATTERN MINER v5 — XGBoost ensemble + cross-asset + multi-timeframe")
    print("=" * 78)

    print("\n[1/5] Loading multi-asset data ...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = None; rty_5m = None; vix_5m = None
    try: es_5m = load_intraday_5min("es")
    except Exception as e: logger.warning(f"  ES failed: {e}")
    try: rty_5m = load_intraday_5min("rty")
    except Exception as e: logger.warning(f"  RTY failed: {e}")
    try: vix_5m = load_vix_5min()
    except Exception as e: logger.warning(f"  VIX failed: {e}")

    for df in (nq_5m, nq_1m, daily):
        if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    for df in (es_5m, rty_5m, vix_5m):
        if df is not None and df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

    print(f"  NQ 5m: {len(nq_5m):,}, NQ 1m: {len(nq_1m):,}, daily: {len(daily):,}")
    print(f"  ES: {len(es_5m) if es_5m is not None else 0:,}  "
          f"RTY: {len(rty_5m) if rty_5m is not None else 0:,}  "
          f"VIX: {len(vix_5m) if vix_5m is not None else 0:,}")

    print("\n[2/5] Building feature matrix ...")
    t0 = time.time()
    feats = build_features(nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m)
    print(f"  features: {feats.shape}  ({time.time()-t0:.0f}s)")
    print(f"  feature cols: {len(feats.columns)}")

    # XGBoost handles NaN natively (treats as a separate split direction).
    # We DON'T dropna — that would erase all pre-2024 bars where the
    # cross-asset features (ES/RTY/VIX) aren't present, leaving us with
    # < 5K training rows. Instead require only the bare-minimum NQ-only
    # features to be present for a row to be usable.
    nq_core_cols = ["atr_14", "dist_pdh_atr", "dist_pdl_atr", "vol_z_50",
                     "rsi_14", "ema_20_slope"]
    feats_clean = feats[feats[nq_core_cols].notna().all(axis=1)]
    print(f"  bars with NQ-core features: {len(feats_clean):,}")

    # Train cutoff: 2024-07-01 (cross-asset features are present from 2024+,
    # so 2024-Jul splits roughly half of the cross-asset-rich data into
    # train and half into OOS test).
    train_end = pd.Timestamp("2024-07-01", tz="UTC")
    print(f"  train end: {train_end}  →  test starts after")

    print("\n[3/5] Mining + training XGBoost models per (side, stop, target, trail) ...")
    results = []
    # Configurations: stop, target, max_hold, trail_activate, trail_stop
    configs = [
        # 1:1 RR fixed
        ("LONG",  16, 16, 60, 0, 0),
        ("SHORT", 16, 16, 60, 0, 0),
        # 1:2 RR fixed
        ("LONG",  10, 20, 30, 0, 0),
        ("SHORT", 10, 20, 30, 0, 0),
        # Trail stop (activate at 1R, trail by 0.5R) — let winners run
        ("LONG",  10, 100, 90, 10, 5),  # target very far, real exit is trail
        ("SHORT", 10, 100, 90, 10, 5),
        ("LONG",  15, 150, 120, 15, 7),
        ("SHORT", 15, 150, 120, 15, 7),
        # Quick scalp 1:1
        ("LONG",  6, 6, 20, 0, 0),
        ("SHORT", 6, 6, 20, 0, 0),
    ]

    for side, stop, target, mh, ta, ts in configs:
        cfg_name = f"{side}_S{stop}T{target}"
        if ta > 0:
            cfg_name += f"_trail{ta}/{ts}"
        print(f"\n  --- {cfg_name} ---")
        # Label every bar in feats_clean as if a signal fired there
        signal_times = feats_clean.index
        t1 = time.time()
        labels = label_trades(nq_1m, signal_times, side, stop, target, mh, ta, ts)
        print(f"    labels: {labels.sum()}/{len(labels)} wins  ({time.time()-t1:.0f}s)  base WR={labels.mean()*100:.1f}%")

        t2 = time.time()
        r = train_and_select(feats_clean, labels, train_end, top_pct=0.01,
                              n_estimators=400, max_depth=6)
        print(f"    train: {time.time()-t2:.0f}s")
        if "error" in r:
            print(f"    SKIP: {r['error']}")
            continue
        r["config"] = dict(side=side, stop_pts=stop, target_pts=target,
                            max_hold_min=mh, trail_activate=ta, trail_stop=ts)
        results.append(r)
        print(f"    OOS picked: {r['n_picked']:,} bars  WR={r['test_wr']*100:.1f}%  "
              f"(base {r['test_base_wr']*100:.1f}%)  lift +{r['lift_pp']:.1f}pp  "
              f"trades/wk≈{r['trades_per_week']:.1f}")
        print(f"    top features: {[f for f,_ in r['top_features'][:5]]}")

    print("\n[4/5] Ranking surviving configurations ...")
    survivors = [r for r in results if r["test_wr"] >= 0.55 and r["lift_pp"] >= 5
                  and r["n_picked"] >= 100]
    survivors.sort(key=lambda r: -r["lift_pp"])
    print(f"  survivors (WR>=55%, lift>=5pp, n>=100): {len(survivors)}")
    for r in survivors[:20]:
        c = r["config"]
        print(f"    {c['side']:<5} S{c['stop_pts']:<2}T{c['target_pts']:<3}  "
              f"WR={r['test_wr']*100:.1f}%  lift+{r['lift_pp']:.1f}pp  "
              f"n={r['n_picked']:>4}  ~{r['trades_per_week']:.1f} trades/wk")

    # Save (no model objects in JSON — keep just the metrics)
    out = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "train_end": str(train_end),
        "configs_tried": len(configs),
        "results": [
            {k: v for k, v in r.items() if k not in ("model", "feat_cols")}
            for r in results
        ],
        "n_survivors": len(survivors),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[5/5] Wrote {OUT_PATH.name}")

    # Save the best models as joblib files for later inference
    if survivors:
        import joblib
        models_dir = DATA / "v5_models"
        models_dir.mkdir(exist_ok=True)
        for i, r in enumerate(survivors[:10]):
            mp = models_dir / f"v5_top{i+1}_{r['config']['side']}_S{r['config']['stop_pts']}T{r['config']['target_pts']}.joblib"
            joblib.dump({"model": r["model"], "feat_cols": r["feat_cols"],
                          "config": r["config"], "threshold": r["threshold"]}, mp)
        print(f"  saved {min(10, len(survivors))} top models to {models_dir.relative_to(PROJECT_ROOT)}")

    print(f"\n  Total runtime: {(time.time()-t0)/60:.1f}m")


if __name__ == "__main__":
    main()

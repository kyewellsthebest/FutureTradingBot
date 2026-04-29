"""
ML meta-model — gradient-boosted classifier predicting whether each strategy's
firing will hit target before stop, given the current market state.

Why this matters: each strategy fires whenever its hard constraints match,
regardless of context. Some of those firings are in regimes the strategy
wasn't trained for (e.g. a mean-reversion pattern firing during a strong
trend). The meta-model adds a CONFIDENCE GATE: skip firings the model thinks
are likely losers.

Pipeline:
    1. For every whitelisted strategy, regenerate all entries on 8yr NQ.
    2. For each entry, snapshot the v3 + SMC + cross-asset features at that bar.
    3. Train a XGBoost / LightGBM / sklearn-GBM classifier:
         features = market state at entry
         label = 1 if trade hit target before stop, 0 otherwise
       (One model per strategy — strategies are too different to share.)
    4. Save model + per-strategy AUC + feature importance.

At runtime, the bot calls the model on each new firing and skips trades with
predicted P(win) below a configurable threshold.

Output:
    data/meta_models/<strategy>.pkl       per-strategy model
    data/meta_model_summary.json          AUCs + feature importances
"""
from __future__ import annotations

import json
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from research.local_data_loader import load_daily, load_intraday_1min, load_intraday_5min
from research.pattern_miner_v3 import V3_FEATURES, build_v3_features
from research.smc_features import SMC_FEATURES, build_smc_features
from research.validate_mined_full import fixed_target_stop_simulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "data" / "meta_models"
SUMMARY_PATH = PROJECT_ROOT / "data" / "meta_model_summary.json"


def main():
    print("=" * 80)
    print("META-MODEL TRAINING — per-strategy confidence gate")
    print("=" * 80)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Loading data + features ...", flush=True)
    t0 = time.time()
    m1 = load_intraday_1min("nq")
    m5 = load_intraday_5min("nq")
    daily = load_daily("nq")

    # Build full feature matrix (v3 + SMC) once for each timeframe
    print("  building v3 + SMC features (1-min) ...", flush=True)
    X1 = pd.concat([
        build_v3_features(m1, daily),
        build_smc_features(m1, daily),
    ], axis=1)
    print(f"  1-min features: {X1.shape}   ({time.time()-t0:.1f}s)")

    print("  building v3 + SMC features (5-min) ...", flush=True)
    X5 = pd.concat([
        build_v3_features(m5, daily),
        build_smc_features(m5, daily),
    ], axis=1)
    print(f"  5-min features: {X5.shape}")

    val = json.loads((PROJECT_ROOT / "data" / "validation_results.json").read_text())
    whitelist = {k: v for k, v in val["signals"].items() if v.get("recommended")}
    print(f"  whitelist: {len(whitelist)} strategies")

    from research.signal_generator import ALL_SIGNALS
    from research.mined_wr_signals import ALL_WR_SIGNALS
    from research.mined_v3_signals import ALL_V3_SIGNALS
    sig_objs = {}
    for s in list(ALL_SIGNALS) + list(ALL_WR_SIGNALS) + list(ALL_V3_SIGNALS):
        if hasattr(s, "name"):
            sig_objs[s.name] = s

    h1 = m1["high"].to_numpy(); l1 = m1["low"].to_numpy(); c1 = m1["close"].to_numpy()
    h5 = m5["high"].to_numpy(); l5 = m5["low"].to_numpy(); c5 = m5["close"].to_numpy()

    print("\n[2/3] Per-strategy meta-model ...\n", flush=True)
    print(f"{'name':<32} {'n':>6} {'AUC':>5} {'top features':<30}")
    print("-" * 80)

    summary = {"models": {}, "generated_at": datetime.now(timezone.utc).isoformat()}

    for name, info in whitelist.items():
        sig = sig_objs.get(name)
        if sig is None:
            continue
        if name.startswith("V3_") or name.startswith("WR_"):
            intraday = m1; X = X1; h, l, c = h1, l1, c1
        else:
            intraday = m5; X = X5; h, l, c = h5, l5, c5
        stop = float(info.get("stop_pts") or getattr(sig, "stop_pts", 15.0))
        target = float(info.get("target_pts") or getattr(sig, "target_pts", 30.0))
        max_hold = int(getattr(sig, "max_hold_bars", 80))
        side = info.get("side") or getattr(sig, "side", "LONG")

        try:
            df = sig.generate(intraday, daily)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        sig_times = pd.DatetimeIndex(df["signal_time"])
        pos = intraday.index.get_indexer(sig_times)
        entries = [int(p) for p in pos
                   if p >= 0 and p < len(intraday) - max_hold - 1]
        if len(entries) < 200:
            continue

        # Compute outcome (1 = win) for each entry
        pts = fixed_target_stop_simulate(h, l, c, entries, side, stop, target, max_hold)
        if not pts:
            continue
        y = (np.asarray(pts) > 0).astype(int)
        # Snapshot features at each entry
        feat_idx = [entries[i] for i in range(len(pts))]
        X_strat = X.iloc[feat_idx].copy()
        # Drop rows with NaN
        valid_mask = X_strat.notna().all(axis=1).to_numpy()
        if valid_mask.sum() < 200:
            continue
        X_strat = X_strat.iloc[valid_mask]
        y = y[valid_mask]

        # Time-series split (last 25% as test)
        cut = int(len(y) * 0.75)
        X_tr, X_te = X_strat.iloc[:cut], X_strat.iloc[cut:]
        y_tr, y_te = y[:cut], y[cut:]
        if len(set(y_tr)) < 2 or len(set(y_te)) < 2:
            continue

        try:
            model = GradientBoostingClassifier(
                n_estimators=80, max_depth=4, learning_rate=0.05,
                subsample=0.8, random_state=42,
            )
            model.fit(X_tr, y_tr)
            te_pred = model.predict_proba(X_te)[:, 1]
            auc = float(roc_auc_score(y_te, te_pred))
        except Exception as e:
            print(f"  [{name}] training failed: {e}")
            continue

        # Top 5 most important features
        importances = pd.Series(model.feature_importances_, index=X_strat.columns)
        top5 = importances.nlargest(5)
        top_str = ", ".join(f"{k}({v:.2f})" for k, v in top5.head(3).items())

        # Persist
        with (MODELS_DIR / f"{name}.pkl").open("wb") as f:
            pickle.dump({
                "model": model,
                "feature_names": list(X_strat.columns),
                "auc": auc,
                "n_train": len(y_tr), "n_test": len(y_te),
                "win_rate_train": float(y_tr.mean()),
                "win_rate_test": float(y_te.mean()),
            }, f)
        summary["models"][name] = {
            "auc": auc,
            "n_total": int(len(y)),
            "n_train": int(len(y_tr)),
            "n_test": int(len(y_te)),
            "wr_train": float(y_tr.mean()),
            "wr_test": float(y_te.mean()),
            "top_features": top5.to_dict(),
        }
        print(f"{name:<32} {len(y):>6} {auc:.3f} {top_str:<60}")

    # Aggregate AUC
    aucs = [m["auc"] for m in summary["models"].values()]
    print("\n[3/3] Summary:")
    print(f"  Strategies modeled: {len(aucs)}")
    if aucs:
        print(f"  Mean AUC:           {np.mean(aucs):.3f}")
        print(f"  Median AUC:         {np.median(aucs):.3f}")
        print(f"  Models with AUC>0.55: {sum(1 for a in aucs if a > 0.55)}/{len(aucs)}")

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n  Wrote -> {SUMMARY_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  Per-strategy models in -> {MODELS_DIR.relative_to(PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()

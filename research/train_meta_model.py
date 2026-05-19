"""
Adaptive brain — STAGE 2: the meta-model.

Trains a gradient-boosted model to predict, for every signal the
97-strategy book fires, whether that trade will be profitable — using
only the point-in-time context features from Stage 1 (the strategy's own
name is deliberately excluded so the model generalises from
characteristics + recency rather than memorising identities).

The honest test is NOT accuracy. It is a PURGED WALK-FORWARD:
  * train on the past, predict the future, never overlap an open trade
  * pool the out-of-sample predictions
  * ask: sorted by the model's score, do realised outcomes actually
    separate (quintile monotonicity)? and does meta-FILTERED / meta-SIZED
    trading beat the raw book out-of-sample?

If the walk-forward shows skill, the final model (fit on all data) is
saved for Stage 4 wiring. If it does not, that is reported plainly and
nothing is saved — the meta-model only ships if it earns it.
"""
from __future__ import annotations

import json
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
IN_CSV = DATA / "signal_dataset.csv"
MODEL_OUT = DATA / "meta_model.pkl"
REPORT_OUT = DATA / "meta_model_report.json"
logger = logging.getLogger("meta_model")

FEATURES = [
    "z_value", "z_window", "z_threshold", "z_excess", "stop_atr", "target_atr",
    "rr", "max_hold_min", "side_long", "family_vix", "ny_hour", "ny_minute",
    "day_of_week", "atr14", "atr_pct", "rv20", "rv60", "nq_ret_5", "nq_ret_20",
    "nq_ret_60", "nq_vs_sma50", "nq_vs_sma200", "trend_20_50_atr",
    "range20_atr", "vol_ratio", "es_ret_20", "rty_ret_20", "vix_level",
    "vix_pct", "vix_z", "vix_ret_20", "n_windows_os", "n_windows_ob",
    "n_concurrent_fires", "strat_recent_winrate", "strat_recent_r",
    "strat_recent_n",
]
TARGET = "profitable"

# Conservative — shallow trees resist over-fitting on ~13k rows.
XGB_PARAMS = dict(
    n_estimators=500, max_depth=3, learning_rate=0.03,
    subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
    reg_lambda=1.0, eval_metric="logloss", early_stopping_rounds=40,
)

N_TEST_FOLDS = 4
TRAIN_FRAC0 = 0.45      # first fold trains on the earliest 45%


def make_model() -> XGBClassifier:
    return XGBClassifier(**XGB_PARAMS)


def _maxdd(curve: np.ndarray) -> float:
    """Max drawdown of a cumulative-R curve, in R units."""
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def walk_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Purged expanding walk-forward. Returns pooled OOS rows + per-fold info."""
    n = len(df)
    bounds = [int(n * TRAIN_FRAC0)]
    step = (n - bounds[0]) // N_TEST_FOLDS
    for k in range(1, N_TEST_FOLDS):
        bounds.append(bounds[0] + k * step)
    bounds.append(n)

    oos_parts, fold_info = [], []
    for f in range(N_TEST_FOLDS):
        tr_end, te_end = bounds[f], bounds[f + 1]
        test = df.iloc[tr_end:te_end]
        test_start = test["signal_ts"].iloc[0]
        # PURGE: a training trade may only be used if it fully closed before
        # the test window opens — otherwise an open trade straddles the split.
        train = df.iloc[:tr_end]
        train = train[train["exit_ts"] < test_start]
        if len(train) < 500 or len(test) < 100:
            continue
        # carve a chronological tail of train for early-stopping validation
        v = int(len(train) * 0.85)
        X_tr, y_tr = train[FEATURES].iloc[:v], train[TARGET].iloc[:v]
        X_va, y_va = train[FEATURES].iloc[v:], train[TARGET].iloc[v:]

        model = make_model()
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        p = model.predict_proba(test[FEATURES])[:, 1]

        part = test[["signal_ts", "strategy", "family", "r_multiple",
                      "profitable"]].copy()
        part["pred_p"] = p
        part["fold"] = f
        oos_parts.append(part)
        try:
            auc = roc_auc_score(test[TARGET], p)
        except ValueError:
            auc = float("nan")
        fold_info.append({"fold": f, "n_train": int(len(train)),
                          "n_test": int(len(test)), "auc": round(auc, 4),
                          "test_start": str(test_start)[:10]})
        logger.info(f"  fold {f}: train={len(train):,} test={len(test):,} "
                    f"AUC={auc:.4f}")
    return pd.concat(oos_parts).reset_index(drop=True), fold_info


def evaluate(oos: pd.DataFrame) -> dict:
    """The honest tests on pooled out-of-sample predictions."""
    r = oos["r_multiple"].to_numpy()
    p = oos["pred_p"].to_numpy()
    n = len(oos)

    auc = roc_auc_score(oos["profitable"], p)

    # --- quintile separation: sort by score, do outcomes line up? ----------
    order = np.argsort(p)
    quintiles = []
    for q in range(5):
        sl = order[q * n // 5:(q + 1) * n // 5]
        quintiles.append({
            "quintile": q + 1,
            "pred_p_mean": round(float(p[sl].mean()), 4),
            "realized_profit_rate": round(float((r[sl] > 0).mean()), 4),
            "realized_avg_r": round(float(r[sl].mean()), 4),
            "n": int(len(sl)),
        })

    # --- filter test: baseline vs dropping the worst-scored trades ---------
    def stats(mask):
        rr = r[mask]
        if len(rr) == 0:
            return {"n": 0, "total_r": 0.0, "avg_r": 0.0, "maxdd_r": 0.0}
        return {"n": int(len(rr)), "total_r": round(float(rr.sum()), 1),
                "avg_r": round(float(rr.mean()), 4),
                "maxdd_r": round(_maxdd(np.cumsum(rr)), 1)}

    thr_b1 = np.quantile(p, 0.20)
    thr_b2 = np.quantile(p, 0.40)
    filt = {
        "baseline_all": stats(np.ones(n, bool)),
        "drop_bottom_20pct": stats(p >= thr_b1),
        "drop_bottom_40pct": stats(p >= thr_b2),
    }

    # --- sizing test: same total capital, allocated by predicted edge ------
    size_raw = np.clip(p - 0.50, 0.0, None)   # only positive-edge trades sized
    flat_total = float(r.sum())
    if size_raw.sum() > 0:
        size = size_raw / size_raw.mean()      # mean size 1 -> same gross capital
        sized_r = size * r
        sizing = {
            "flat_total_r": round(flat_total, 1),
            "flat_maxdd_r": round(_maxdd(np.cumsum(r)), 1),
            "sized_total_r": round(float(sized_r.sum()), 1),
            "sized_maxdd_r": round(_maxdd(np.cumsum(sized_r)), 1),
            "sized_uplift_pct": round((sized_r.sum() / flat_total - 1) * 100, 1)
            if flat_total != 0 else None,
        }
    else:
        sizing = {"flat_total_r": round(flat_total, 1), "note": "no positive-edge trades"}

    return {"n_oos": n, "pooled_auc": round(float(auc), 4),
            "quintiles": quintiles, "filter_test": filt, "sizing_test": sizing}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    print("=" * 74)
    print("ADAPTIVE BRAIN — STAGE 2: meta-model (purged walk-forward)")
    print("=" * 74)

    df = pd.read_csv(IN_CSV, parse_dates=["signal_ts", "entry_ts", "exit_ts"])
    df = df.sort_values("signal_ts").reset_index(drop=True)
    logger.info(f"loaded {len(df):,} firings, base profitable-rate "
                f"{df[TARGET].mean()*100:.1f}%")

    oos, fold_info = walk_forward(df)
    logger.info(f"pooled OOS predictions: {len(oos):,}")

    ev = evaluate(oos)

    # null check — shuffle labels, the model should lose all skill
    rng = np.random.default_rng(0)
    sh = df.copy()
    sh[TARGET] = rng.permutation(sh[TARGET].to_numpy())
    sh_oos, _ = walk_forward(sh)
    null_auc = roc_auc_score(sh_oos["profitable"], sh_oos["pred_p"])

    q = ev["quintiles"]
    monotone = all(q[i]["realized_avg_r"] <= q[i + 1]["realized_avg_r"]
                   for i in range(4))
    spread = q[-1]["realized_avg_r"] - q[0]["realized_avg_r"]
    skilled = (ev["pooled_auc"] > 0.53 and spread > 0.05
               and ev["filter_test"]["drop_bottom_40pct"]["avg_r"]
               > ev["filter_test"]["baseline_all"]["avg_r"])

    print("\n--- per-fold ---")
    for fi in fold_info:
        print(f"  fold {fi['fold']}  test from {fi['test_start']}  "
              f"n={fi['n_test']:>5}  AUC={fi['auc']}")
    print(f"\npooled OOS AUC : {ev['pooled_auc']}   (shuffled-label null: "
          f"{null_auc:.4f})")
    print("\n--- quintile separation (low score -> high score) ---")
    print(f"  {'Q':<3}{'pred_p':>9}{'realized_profit%':>19}{'realized_avg_R':>17}{'n':>8}")
    for x in q:
        print(f"  {x['quintile']:<3}{x['pred_p_mean']:>9.3f}"
              f"{x['realized_profit_rate']*100:>18.1f}%"
              f"{x['realized_avg_r']:>17.4f}{x['n']:>8}")
    print(f"  monotone={monotone}  top-minus-bottom avg R = {spread:+.4f}")
    print("\n--- filter test (out-of-sample) ---")
    for k, v in ev["filter_test"].items():
        print(f"  {k:<20} n={v['n']:>5}  total_R={v['total_r']:>8}  "
              f"avg_R={v['avg_r']:>+8.4f}  maxDD_R={v['maxdd_r']:>8}")
    print("\n--- sizing test (same gross capital, allocated by predicted edge) ---")
    for k, v in ev["sizing_test"].items():
        print(f"  {k:<20} {v}")

    verdict = ("SKILL CONFIRMED — meta-model improves OOS selection"
               if skilled else
               "NO RELIABLE SKILL — meta-model does not beat the raw book OOS")
    print(f"\nVERDICT: {verdict}")

    report = {"n_firings": int(len(df)), "folds": fold_info,
              "evaluation": ev, "shuffled_null_auc": round(float(null_auc), 4),
              "quintile_monotone": monotone, "top_bottom_r_spread": round(spread, 4),
              "skilled": bool(skilled), "verdict": verdict}
    REPORT_OUT.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {REPORT_OUT.relative_to(PROJECT_ROOT)}")

    if skilled:
        v = int(len(df) * 0.9)
        final = make_model()
        final.fit(df[FEATURES].iloc[:v], df[TARGET].iloc[:v],
                  eval_set=[(df[FEATURES].iloc[v:], df[TARGET].iloc[v:])],
                  verbose=False)
        with open(MODEL_OUT, "wb") as fh:
            pickle.dump({"model": final, "features": FEATURES,
                         "target": TARGET, "trained_rows": int(len(df))}, fh)
        imp = sorted(zip(FEATURES, final.feature_importances_),
                     key=lambda t: -t[1])[:12]
        print("\ntop features:")
        for name, val in imp:
            print(f"  {name:<22}{val:.4f}")
        print(f"\nSaved {MODEL_OUT.relative_to(PROJECT_ROOT)}")
    else:
        print("\nModel NOT saved — it has to earn deployment.")


if __name__ == "__main__":
    main()

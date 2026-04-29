"""
Apply the v3 pattern miner to ES + RTY (each as its own NQ-substitute).

We have ~2 yrs of ES and RTY 1-min data. The same v3 50-feature set + the
same 5-test rigor gauntlet applied independently. If a pattern shows up
across multiple assets, it's much less likely to be NQ-specific noise.

Usage:
    python -m research.multi_asset_miner --asset es
    python -m research.multi_asset_miner --asset rty
    python -m research.multi_asset_miner --asset all   # both, sequentially
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

from research.local_data_loader import load_daily, load_intraday_1min
from research.pattern_miner_v3 import (
    V3_FEATURES, build_v3_features, label_1_to_2_rr,
    cpcv_fold_indices, _path_constraints, V3Rule,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mine(asset: str, target_rr: float, combos: list[tuple[float, int]],
         min_cpcv_mean: float, min_cpcv_fold: float, top: int) -> dict:
    print("=" * 78)
    print(f"MULTI-ASSET MINER — {asset.upper()}  RR=1:{target_rr}")
    print("=" * 78)

    intraday = load_intraday_1min(asset)
    daily = load_daily(asset)
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"  bars: {len(intraday):,}   days: {days}")

    X = build_v3_features(intraday, daily)
    valid = X.notna().all(axis=1).to_numpy()
    print(f"  feature-valid: {valid.sum():,}")

    weeks = days / 7.0
    all_rules = []
    for stop, max_hold in combos:
        target = target_rr * stop
        for side in ("LONG", "SHORT"):
            outcome, vlbl = label_1_to_2_rr(intraday, stop, max_hold, side, target_rr=target_rr)
            mask_idx = (vlbl & valid).nonzero()[0]
            X_arr = X.values[mask_idx]; y = outcome[mask_idx]
            n = len(y)
            if n < 1000:
                continue
            cut = int(n * 0.7)
            tree = DecisionTreeClassifier(max_depth=10, min_samples_leaf=200,
                                           random_state=42, class_weight="balanced")
            tree.fit(X_arr[:cut], y[:cut])
            leaves = tree.apply(X_arr)
            cpcv = cpcv_fold_indices(n, 5, 30)
            for leaf in np.unique(leaves):
                in_leaf_full = leaves == leaf
                if in_leaf_full.sum() < 200:
                    continue
                fold_wrs = []
                for _, te in cpcv:
                    m = in_leaf_full[te]
                    if m.sum() < 20: continue
                    fold_wrs.append(float(y[te][m].mean()))
                if len(fold_wrs) < 3: continue
                mean_wr = float(np.mean(fold_wrs))
                min_wr = float(np.min(fold_wrs))
                if mean_wr < min_cpcv_mean or min_wr < min_cpcv_fold: continue
                if in_leaf_full.sum() / weeks < 0.5: continue
                rule = V3Rule(
                    name="", side=side, stop_pts=stop, target_pts=target,
                    max_hold=max_hold, n_total=int(in_leaf_full.sum()),
                    train_wr=float(y[:cut][leaves[:cut] == leaf].mean()) if (leaves[:cut] == leaf).sum() > 0 else 0,
                    cpcv_mean_wr=mean_wr, cpcv_min_wr=min_wr, cpcv_max_wr=float(np.max(fold_wrs)),
                    cpcv_n_folds=len(fold_wrs),
                    constraints=_path_constraints(tree, leaf, V3_FEATURES),
                )
                all_rules.append(rule)
            print(f"    {side} stop={stop}: {len(all_rules)} cumulative survivors")

    # Sort + take top
    all_rules.sort(key=lambda r: -r.cpcv_mean_wr * (r.n_total ** 0.3))
    all_rules = all_rules[:top]
    by_side = {"LONG": 0, "SHORT": 0}
    for r in all_rules:
        by_side[r.side] += 1
        r.name = f"{asset.upper()}_V3_{r.side}_S{int(r.stop_pts)}T{int(r.target_pts)}_{by_side[r.side]:02d}"
    print(f"  Total: {len(all_rules)} (LONG={by_side['LONG']}, SHORT={by_side['SHORT']})")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset, "target_rr": target_rr,
        "patterns": [r.__dict__ for r in all_rules],
    }
    out_path = PROJECT_ROOT / "data" / f"mined_v3_{asset}.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  Wrote -> {out_path.relative_to(PROJECT_ROOT)}")
    return payload


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", choices=["es", "rty", "all"], default="all")
    p.add_argument("--target-rr", type=float, default=2.0)
    args = p.parse_args()

    combos = [(8.0, 25), (10.0, 30), (12.0, 35), (15.0, 45), (20.0, 60)]
    min_mean = 0.50; min_fold = 0.45
    if args.target_rr >= 3.0:
        min_mean = 0.30; min_fold = 0.25
    elif args.target_rr >= 2.5:
        min_mean = 0.36; min_fold = 0.30

    if args.asset in ("es", "all"):
        try:
            mine("es", args.target_rr, combos, min_mean, min_fold, top=15)
        except Exception as e:
            print(f"ES mine failed: {e}")
    if args.asset in ("rty", "all"):
        try:
            mine("rty", args.target_rr, combos, min_mean, min_fold, top=15)
        except Exception as e:
            print(f"RTY mine failed: {e}")


if __name__ == "__main__":
    main()

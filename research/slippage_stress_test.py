"""
Slippage Stress Test for v11 + v12 strategies.

Re-runs every user-pass strategy through 3 slippage scenarios:

  Baseline   : 2 pt entry / 2 pt adverse stop  (current backtest)
  Moderate   : 4 pt entry / 4 pt adverse stop  (typical retail off-RTH)
  Severe     : 6 pt entry / 6 pt adverse stop  (overnight thin liquidity)

For each scenario, re-labels each strategy and recomputes metrics. Reports
how many strategies still pass the user-pass thresholds (PF>1, WR>=50%,
n>=100) at each level.

This answers: "if real-world overnight slippage is 2-3x what we backtest,
which v12 strategies survive?"
"""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

import research.pattern_miner_v6 as pmv6
from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, evaluate_strategy, StrategyDef, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import build_v11_extras, make_v11_detector_dicts
from research.pattern_miner_v12 import make_v12_detector_dicts
from research.pattern_miner_v13 import build_v13_extras, make_v13_detector_dicts
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "slippage_stress_results.json"

logger = logging.getLogger("slip_stress")

SCENARIOS = [
    ("baseline", 2.0, 2.0),
    ("moderate", 4.0, 4.0),
    ("severe",   6.0, 6.0),
]

USER_MIN_WR = 0.50
USER_MIN_RR = 2.0
USER_MIN_TRADES = 100
USER_MIN_PF = 1.0


def load_all_user_passers():
    out = []
    for fname, src in [("mined_v11_patterns.json", "v11"),
                          ("mined_v12_patterns.json", "v12"),
                          ("mined_v13_patterns.json", "v13")]:
        p = DATA / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for s in d.get("user_passers", []):
            t = s.get("test", {})
            if t.get("pf", 0) < USER_MIN_PF:
                continue
            s["_source"] = src
            out.append(s)
    return out


def main():
    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(message)s",
                          handlers=[logging.StreamHandler(sys.stdout)])

    logger.info("Loading data + features (one-time)...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = load_intraday_5min("rty")
    vix_5m = load_vix_5min()
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    F = build_v13_extras(F, nq_5m, rty_5m, vix_5m)

    contexts_d_v11, triggers_d_v11 = make_v11_detector_dicts(F)
    contexts_d_v12, _ = make_v12_detector_dicts(F)
    contexts_d_v13, triggers_d_v13 = make_v13_detector_dicts(F)
    # Merge all contexts and triggers — names are already namespaced per family
    contexts_d = {**contexts_d_v11, **contexts_d_v12, **contexts_d_v13}
    triggers_d = {**triggers_d_v11, **triggers_d_v13}

    strategies = load_all_user_passers()
    logger.info(f"Loaded {len(strategies)} profitable user-pass strategies "
                  f"({sum(1 for s in strategies if s['_source']=='v11')} v11, "
                  f"{sum(1 for s in strategies if s['_source']=='v12')} v12)")

    # For each scenario, re-evaluate every strategy
    report = {scen[0]: {"n_total": len(strategies), "results": []}
                for scen in SCENARIOS}

    for scen_name, slip, adv in SCENARIOS:
        logger.info(f"\n=== Scenario: {scen_name}  (entry={slip}pt, stop={adv}pt) ===")
        # Patch slippage constants
        pmv6.SLIPPAGE_PT = slip
        pmv6.ADVERSE_SLIP_PT = adv

        for i, s in enumerate(strategies):
            if i % 30 == 0:
                logger.info(f"  {i+1}/{len(strategies)}...")
            strat = StrategyDef(
                name=s["name"], side=s["side"], contexts=s["contexts"],
                trigger=s["trigger"], context_window_bars=5,
                stop_atr=s["stop_atr"], target_atr=s["target_atr"],
                max_hold_min=s["max_hold_min"],
            )
            try:
                trades = label_strategy(F, nq_5m, nq_1m, daily, strat,
                                          contexts_d, triggers_d)
                ev = evaluate_strategy(trades, TRAIN_END)
            except Exception as e:
                logger.warning(f"  {s['name']} crashed: {e}")
                continue
            t = ev.get("test", {})
            rr = s["target_atr"] / s["stop_atr"]
            passes = (t.get("n", 0) >= USER_MIN_TRADES
                        and t.get("wr", 0) >= USER_MIN_WR
                        and t.get("pf", 0) >= USER_MIN_PF
                        and rr >= USER_MIN_RR)
            report[scen_name]["results"].append({
                "name": s["name"],
                "source": s["_source"],
                "side": s["side"],
                "time_ctx": (s.get("contexts") or [None])[0],
                "n": t.get("n", 0),
                "wr": t.get("wr", 0),
                "pf": t.get("pf", 0),
                "sharpe": t.get("sharpe", 0),
                "net": t.get("net", 0),
                "passes": passes,
            })

    # Reset slippage constants
    pmv6.SLIPPAGE_PT = 2.0
    pmv6.ADVERSE_SLIP_PT = 2.0

    # Summarize
    print("\n" + "=" * 78)
    print("SLIPPAGE STRESS TEST — survival counts at each level")
    print("=" * 78)
    summary = {}
    for scen_name, slip, adv in SCENARIOS:
        rows = report[scen_name]["results"]
        n_pass = sum(1 for r in rows if r["passes"])
        v11_pass = sum(1 for r in rows if r["passes"] and r["source"] == "v11")
        v12_pass = sum(1 for r in rows if r["passes"] and r["source"] == "v12")
        avg_pf = np.mean([r["pf"] for r in rows if r["passes"]]) if n_pass else 0
        avg_wr = np.mean([r["wr"] for r in rows if r["passes"]]) if n_pass else 0
        total_net = sum(r["net"] for r in rows if r["passes"])
        summary[scen_name] = {
            "slip_pt": slip, "adverse_pt": adv,
            "n_passing": n_pass,
            "v11_passing": v11_pass,
            "v12_passing": v12_pass,
            "avg_pf_passing": float(avg_pf),
            "avg_wr_passing": float(avg_wr),
            "total_net_passing": float(total_net),
        }
        print(f"\n  [{scen_name:<10}] entry={slip}pt stop={adv}pt")
        print(f"    Strategies passing: {n_pass}/{len(rows)} "
                f"({v11_pass} v11 + {v12_pass} v12)")
        print(f"    Avg PF (passing):   {avg_pf:.2f}")
        print(f"    Avg WR (passing):   {avg_wr*100:.1f}%")
        print(f"    Sum net @ 1 MNQ:    ${total_net:,.0f}")

    # Per-strategy survival across all 3 levels
    survival = defaultdict(set)
    for scen_name in [s[0] for s in SCENARIOS]:
        for r in report[scen_name]["results"]:
            if r["passes"]:
                survival[r["name"]].add(scen_name)

    bulletproof = [n for n, scens in survival.items() if len(scens) == 3]
    moderate_only = [n for n, scens in survival.items()
                       if "moderate" in scens and "severe" not in scens]

    print("\n" + "=" * 78)
    print("ROBUSTNESS TIER (passes at 2/4/6pt slippage)")
    print("=" * 78)
    print(f"  Bulletproof (passes ALL 3 levels): {len(bulletproof)}")
    print(f"  Moderate (2-4pt only):              {len(moderate_only)}")
    print(f"  Fragile (2pt only — bot only):      "
            f"{len(strategies) - len(bulletproof) - len(moderate_only)}")

    # Save report
    out = {
        "summary": summary,
        "bulletproof_strategies": bulletproof,
        "moderate_strategies": moderate_only,
        "scenarios": report,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    logger.info(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

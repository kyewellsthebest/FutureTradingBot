"""
Slippage stress test for v14 first-touch structural-reversal strategies.

v14 strategies are not StrategyDef-based (no contexts/triggers/ATR stops) —
they're V14Strategy first-touch reversals. So they need their own stress
test: re-label every user-pass v14 strategy at three slippage levels and
report how many still pass.

  Baseline   : 2 pt entry / 2 pt adverse stop
  Moderate   : 4 pt entry / 4 pt adverse stop
  Severe     : 6 pt entry / 6 pt adverse stop

Output: data/slippage_stress_v14.json
"""
from __future__ import annotations
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import research.pattern_miner_v14 as pmv14
from research.pattern_miner_v14 import (
    V14Strategy, build_v14_frame, label_v14,
)
from research.pattern_miner_v6 import evaluate_strategy, TRAIN_END
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "slippage_stress_v14.json"
logger = logging.getLogger("slip_stress_v14")

SCENARIOS = [
    ("baseline", 2.0, 2.0),
    ("moderate", 4.0, 4.0),
    ("severe",   6.0, 6.0),
]

USER_MIN_WR = 0.50
USER_MIN_TRADES = 100
USER_MIN_PF = 1.0


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    p = DATA / "mined_v14_patterns.json"
    if not p.exists():
        logger.error("mined_v14_patterns.json not found — run the miner first")
        return
    passers = json.loads(p.read_text()).get("user_passers", [])
    # only keep genuinely profitable ones
    passers = [s for s in passers if s.get("test", {}).get("pf", 0) >= USER_MIN_PF]
    logger.info(f"Loaded {len(passers)} profitable v14 user-pass strategies")

    logger.info("Loading data + building frame (one-time)...")
    m5 = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    for df in (m5, nq_1m, daily):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    F = build_v14_frame(m5, daily)

    report = {scen[0]: [] for scen in SCENARIOS}

    for scen_name, slip, adv in SCENARIOS:
        logger.info(f"\n=== Scenario: {scen_name} (entry={slip}pt, stop={adv}pt) ===")
        pmv14.SLIPPAGE_PT = slip
        pmv14.ADVERSE_SLIP_PT = adv
        for i, s in enumerate(passers):
            if i % 20 == 0:
                logger.info(f"  {i+1}/{len(passers)}...")
            strat = V14Strategy(
                name=s["name"], level=s["level"], side=s["side"],
                tolerance=float(s["tolerance"]), stop_buf=float(s["stop_buf"]),
                rr=float(s["rr"]), vol_gate=s["vol_gate"],
                max_hold_min=int(s["max_hold_min"]),
            )
            try:
                trades = label_v14(F, nq_1m, strat)
                ev = evaluate_strategy(trades, TRAIN_END)
            except Exception as e:
                logger.warning(f"  {s['name']} crashed: {e}")
                continue
            t = ev.get("test", {})
            passes = (t.get("n", 0) >= USER_MIN_TRADES
                      and t.get("wr", 0) >= USER_MIN_WR
                      and t.get("pf", 0) >= USER_MIN_PF)
            report[scen_name].append({
                "name": s["name"], "level": s["level"], "side": s["side"],
                "n": t.get("n", 0), "wr": t.get("wr", 0), "pf": t.get("pf", 0),
                "sharpe": t.get("sharpe", 0), "net": t.get("net", 0),
                "passes": passes,
            })

    pmv14.SLIPPAGE_PT = 2.0
    pmv14.ADVERSE_SLIP_PT = 2.0

    print("\n" + "=" * 78)
    print("v14 SLIPPAGE STRESS TEST — survival at each level")
    print("=" * 78)
    summary = {}
    for scen_name, slip, adv in SCENARIOS:
        rows = report[scen_name]
        n_pass = sum(1 for r in rows if r["passes"])
        avg_pf = np.mean([r["pf"] for r in rows if r["passes"]]) if n_pass else 0
        avg_wr = np.mean([r["wr"] for r in rows if r["passes"]]) if n_pass else 0
        total_net = sum(r["net"] for r in rows if r["passes"])
        summary[scen_name] = {
            "slip_pt": slip, "adverse_pt": adv, "n_passing": n_pass,
            "avg_pf_passing": float(avg_pf), "avg_wr_passing": float(avg_wr),
            "total_net_passing": float(total_net),
        }
        print(f"\n  [{scen_name:<10}] entry={slip}pt stop={adv}pt")
        print(f"    Passing: {n_pass}/{len(rows)}")
        print(f"    Avg PF:  {avg_pf:.2f}   Avg WR: {avg_wr*100:.1f}%")
        print(f"    Sum net @ 1 MNQ: ${total_net:,.0f}")

    survival = defaultdict(set)
    for scen_name in [s[0] for s in SCENARIOS]:
        for r in report[scen_name]:
            if r["passes"]:
                survival[r["name"]].add(scen_name)
    bulletproof = sorted(n for n, sc in survival.items() if len(sc) == 3)
    moderate_only = sorted(n for n, sc in survival.items()
                           if "moderate" in sc and "severe" not in sc)

    print("\n" + "=" * 78)
    print("ROBUSTNESS TIER (passes at 2/4/6pt slippage)")
    print("=" * 78)
    print(f"  Bulletproof (all 3 levels): {len(bulletproof)}")
    print(f"  Moderate (2-4pt only):      {len(moderate_only)}")
    print(f"  Fragile (2pt only):         "
          f"{len(passers) - len(bulletproof) - len(moderate_only)}")

    OUT_PATH.write_text(json.dumps({
        "summary": summary,
        "bulletproof_strategies": bulletproof,
        "moderate_strategies": moderate_only,
        "scenarios": report,
    }, indent=2, default=str))
    logger.info(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

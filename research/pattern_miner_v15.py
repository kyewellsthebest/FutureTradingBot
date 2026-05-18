"""
Pattern Miner v15 — coverage expansion of the NQ-ES stat-arb book.

Motivation: the deployed v11/v12/v13 books only ever entered in the NY
afternoon (13:00-16:00) and overnight, because pattern_miner_v11 only
ENUMERATED candidates for those hours (see its TIME_CTXS). The US morning
and lunch (09:30-13:00 ET) were never mined — not rejected by the
gauntlet, simply never tested. A textbook oversold setup in that window
cannot be taken by any deployed strategy.

v15 closes two gaps, running the IDENTICAL 11-test gauntlet as v11
(evaluate_strategy / CPCV / 5000-trial permutation) — no goalposts moved:

  Group A  MORNING/LUNCH COVERAGE
     the existing single-window NQ-ES divergence triggers, paired with
     morning + lunch + wide intraday contexts the v11 miner never tried.

  Group B  CONSENSUS TRIGGERS
     fire when MANY divergence look-back windows read oversold at once
     (>=K of 8 windows beyond the Z threshold). A multi-window consensus
     is a robust reading that needn't be clock-gated, so these run on
     wide contexts (whole RTH). This is the "all the Z-bars at -2 and
     every strategy waiting" case turned into a testable strategy.

Survivors are written to mined_v15_patterns.json; deployment is a
separate, deliberate step — the gauntlet decides, nothing is forced.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, evaluate_strategy, StrategyDef, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import (
    build_v11_extras, v11_trigger_detectors, v11_context_detectors,
)
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
SMOKE = bool(os.environ.get("V15_SMOKE"))
OUT_PATH = DATA / ("mined_v15_patterns_smoke.json" if SMOKE else "mined_v15_patterns.json")
PROGRESS_PATH = DATA / ("v15_progress_smoke.json" if SMOKE else "v15_progress.json")
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v15.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v15")

USER_MIN_WR = 0.50
USER_MIN_RR = 2.0
USER_MIN_TRADES = 100

DIV_WINDOWS = [10, 15, 20, 30, 45, 60, 90, 120]


def v15_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    """Morning / lunch / whole-session NY-time slices the v11 miner skipped."""
    h = F["ny_hour"]; m = F["ny_minute"]
    rth = (((h == 9) & (m >= 30)) | ((h >= 10) & (h < 16)))
    C = {
        # the untested morning + lunch zone
        "t_0930_1100": ((h == 9) & (m >= 30)) | (h == 10),
        "t_1100_1300": (h == 11) | (h == 12),
        "t_am_full":   ((h == 9) & (m >= 30)) | (h == 10) | (h == 11) | (h == 12),
        # whole regular session — for consensus signals that need no clock gate
        "t_rth_full":  rth,
    }
    return {k: v.fillna(False) for k, v in C.items()}


def v15_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    """Consensus triggers: >=K of the 8 divergence windows agree on oversold/
    overbought at once. Every input column is a rolling Z-score ending at the
    current bar, so the count is strictly point-in-time (no look-ahead)."""
    zcols = [f"nq_es_div_z_{w}" for w in DIV_WINDOWS
             if f"nq_es_div_z_{w}" in F.columns]
    Z = F[zcols]
    T = {}
    for t_int in (20, 25):
        t = t_int / 10.0
        long_cnt = (Z < -t).sum(axis=1)    # NaN < -t is False — safe
        short_cnt = (Z > t).sum(axis=1)
        for k in (4, 5, 6):
            T[f"sa_long_cons_{k}_{t_int}"] = long_cnt >= k
            T[f"sa_short_cons_{k}_{t_int}"] = short_cnt >= k
    return {k: v.fillna(False) for k, v in T.items()}


def make_v15_detector_dicts(F: pd.DataFrame):
    """Merge v11's contexts/triggers with v15's new ones."""
    ctx_series = {**v11_context_detectors(F), **v15_context_detectors(F)}
    trig_series = {**v11_trigger_detectors(F), **v15_trigger_detectors(F)}

    def make_fn(s):
        return lambda F, _s=s: _s

    return ({k: make_fn(v) for k, v in ctx_series.items()},
            {k: make_fn(v) for k, v in trig_series.items()})


def enumerate_v15_strategies() -> list[StrategyDef]:
    rr_profiles = [
        (1.0, 2.0, 45, "RR2_std"),
        (1.0, 2.5, 60, "RR2_5"),
        (1.5, 3.0, 75, "RR2_wide"),
        (1.5, 4.0, 90, "RR2_7wide"),
    ]
    strategies: list[StrategyDef] = []
    sid = 0

    # --- Group A: morning/lunch coverage, single-window triggers ----------
    single_trigs = []
    for w in (15, 20, 30, 45, 60, 90):
        for thr in (20, 22, 25, 27, 30):
            single_trigs.append((f"sa_long_{w}_{thr}", "LONG"))
            single_trigs.append((f"sa_short_{w}_{thr}", "SHORT"))
    morning_ctxs = ["t_0930_1100", "t_1100_1300", "t_am_full"]
    for trig, side in single_trigs:
        for ctx in morning_ctxs:
            for stop_a, tgt_a, mh, rrl in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"V15AM_{side}_{trig[:14]}_x_{ctx[:12]}_{rrl}_{sid:05d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=5,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh))

    # --- Group B: consensus triggers, wide (un-clock-gated) contexts ------
    cons_trigs = []
    for t_int in (20, 25):
        for k in (4, 5, 6):
            cons_trigs.append((f"sa_long_cons_{k}_{t_int}", "LONG"))
            cons_trigs.append((f"sa_short_cons_{k}_{t_int}", "SHORT"))
    wide_ctxs = ["t_rth_full", "t_am_full", "pm_full"]
    for trig, side in cons_trigs:
        for ctx in wide_ctxs:
            for stop_a, tgt_a, mh, rrl in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"V15CN_{side}_{trig[:18]}_x_{ctx[:12]}_{rrl}_{sid:05d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=5,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh))
    return strategies


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v15 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print(f"PATTERN MINER v15 — morning/lunch coverage + consensus triggers"
          f"{'  [SMOKE]' if SMOKE else ''}")
    print("=" * 78)

    progress = {"completed": [], "results": []}
    if PROGRESS_PATH.exists():
        try:
            progress = json.loads(PROGRESS_PATH.read_text())
            logger.info(f"resuming with {len(progress['completed'])} done")
        except Exception:
            pass

    print("\n[1/4] Loading data ...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = vix_5m = None
    try: rty_5m = load_intraday_5min("rty")
    except Exception: pass
    try: vix_5m = load_vix_5min()
    except Exception: pass
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df is not None and df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    print(f"  NQ 5m: {len(nq_5m):,} bars   ES 5m: {len(es_5m):,} bars")

    print("\n[2/4] Building features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    print(f"  {F.shape}")

    print("\n[3/4] Enumerating ...")
    strats = enumerate_v15_strategies()
    if SMOKE:
        strats = strats[:6]
    print(f"  TOTAL: {len(strats)}")

    contexts_d, triggers_d = make_v15_detector_dicts(F)

    completed = set(progress.get("completed", []))
    results = list(progress.get("results", []))
    started_at = time.time()
    last_save = started_at
    n_done_now = 0

    print(f"\n[4/4] Mining {len(strats)} strategies ...")
    for idx, strat in enumerate(strats):
        if strat.name in completed:
            continue
        try:
            trades = label_strategy(F, nq_5m, nq_1m, daily, strat,
                                    contexts_d, triggers_d)
            ev = evaluate_strategy(trades, TRAIN_END)
            ev["name"] = strat.name
            ev["side"] = strat.side
            ev["contexts"] = strat.contexts
            ev["trigger"] = strat.trigger
            ev["stop_atr"] = strat.stop_atr
            ev["target_atr"] = strat.target_atr
            ev["max_hold_min"] = strat.max_hold_min
            t = ev.get("test", {})
            rr = strat.target_atr / strat.stop_atr
            ev["user_pass"] = (
                t.get("wr", 0) >= USER_MIN_WR
                and rr >= USER_MIN_RR
                and t.get("n", 0) >= USER_MIN_TRADES
            )
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            if ev.get("user_pass"):
                u_count = sum(1 for r in results if r.get("user_pass"))
                logger.info(
                    f"  [USER-PASS #{u_count}] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} cpcv={ev.get('cpcv_positive',0)}/5 "
                    f"pnl=${t['net']:+,.0f}"
                )
            elif (idx % 25) == 0:
                rate = (idx + 1 - len(progress.get("completed", []))) / max(
                    0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                u_pass = sum(1 for r in results if r.get("user_pass"))
                logger.info(
                    f"  [{idx+1:>5}/{len(strats)}] u_pass={u_pass}  ETA {eta:.0f}m")

            now = time.time()
            if n_done_now >= 5 or (now - last_save) > 30:
                progress["completed"] = sorted(completed)
                progress["results"] = results
                PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))
                last_save = now
                n_done_now = 0
        except Exception as e:
            logger.exception(f"strategy {strat.name} crashed: {e}")
            results.append({"name": strat.name, "error": str(e),
                            "passes_all": False, "user_pass": False})
            completed.add(strat.name)

    progress["completed"] = sorted(completed)
    progress["results"] = results
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))

    user_passers = [r for r in results if r.get("user_pass")]
    print(f"\n[DONE] runtime: {(time.time()-started_at)/60:.1f}m")
    print(f"  total tested: {len(results)}")
    print(f"  USER-PASS: {len(user_passers)}")

    if user_passers:
        user_passers.sort(key=lambda r: -r["test"]["net"])
        for r in user_passers[:60]:
            t = r["test"]
            print(f"    {r['name'][:55]:<55}  n={t['n']:>4}  "
                  f"WR={t['wr']*100:.1f}%  PF={t['pf']:.2f}  "
                  f"$/contract={t['net']:+,.0f}")

    OUT_PATH.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "n_strategies": len(results),
        "n_user_pass": len(user_passers),
        "user_passers": user_passers,
        "all_results": results,
    }, indent=2, default=str))
    print(f"\nWrote {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"main() crashed: {e}")
        raise

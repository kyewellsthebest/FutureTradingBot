"""5-test rigor validator for v4 patterns. Mirrors validate_v3_full.py."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from research.backtest_engine import SLIP_ENTRY_PTS, SLIP_STOP_PTS, monte_carlo
from research.local_data_loader import load_daily, load_intraday_1min
from research.validate_v3_full import (
    fixed_target_stop_simulate,
    shuffle_returns_inplace,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "v4_full_validation.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--fast", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    n_perm = 200 if args.fast else 1000
    n_mc = 2000 if args.fast else 10000

    print("=" * 80)
    print("V4 FULL VALIDATION — 5 rigor tests on v4 patterns")
    print(f"  permutations: {n_perm}    monte_carlo paths: {n_mc}")
    print("=" * 80)

    print("\n[1/3] Loading data and v4 patterns ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()

    try:
        from research.mined_v4_signals import ALL_V4_SIGNALS
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    print(f"  v4 patterns to test: {len(ALL_V4_SIGNALS)}")
    if not ALL_V4_SIGNALS:
        print("  (no v4 patterns to validate)")
        RESULTS_PATH.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "patterns": [],
            "n_all_pass": 0,
        }, indent=2))
        return 0

    cpcv_path = PROJECT_ROOT / "data" / "mined_v4_patterns.json"
    cpcv_data = json.loads(cpcv_path.read_text())
    cpcv_by_name = {p["name"]: p for p in cpcv_data["patterns"]}

    h_arr = intraday["high"].to_numpy(dtype=np.float64)
    l_arr = intraday["low"].to_numpy(dtype=np.float64)
    c_arr = intraday["close"].to_numpy(dtype=np.float64)

    print(f"\n[2/3] Running 5 rigor tests per pattern ...\n")

    results = []
    for k, sig_obj in enumerate(ALL_V4_SIGNALS, 1):
        cname = sig_obj.name
        side = sig_obj.side
        stop_pts = sig_obj.stop_pts
        target_pts = sig_obj.target_pts
        max_hold = sig_obj.max_hold_bars
        cpcv = cpcv_by_name.get(cname, {})

        print(f"  [{k:>2}/{len(ALL_V4_SIGNALS)}] {cname}", flush=True)
        t1 = time.time()

        sig_df = sig_obj.generate(intraday, daily)
        if sig_df.empty:
            print("       no entries — SKIP")
            continue
        time_to_idx = {ts: i for i, ts in enumerate(intraday.index)}
        real_entries = [time_to_idx[t] for t in sig_df["signal_time"].to_numpy()
                        if t in time_to_idx]
        if len(real_entries) < 30:
            print(f"       only {len(real_entries)} entries — SKIP")
            continue

        real_pts = fixed_target_stop_simulate(
            h_arr, l_arr, c_arr, real_entries, side, stop_pts, target_pts, max_hold
        )
        if not real_pts:
            print("       no completed trades — SKIP")
            continue
        real_pts_arr = np.array(real_pts)
        contracts = 5
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl = real_pts_arr * dpp - comm
        n_trades = len(real_pts_arr)
        wins = int((real_pts_arr > 0).sum())
        wr = wins / n_trades
        winsum = pnl[pnl > 0].sum()
        losssum = -pnl[pnl <= 0].sum()
        pf = (winsum / losssum) if losssum > 0 else float("inf")
        ev = float(pnl.mean())
        net_pnl = float(pnl.sum())
        ev_passes = ev > 0
        print(f"       EV:    {n_trades:>4} trades  WR={wr*100:5.1f}%  "
              f"PF={pf if math.isfinite(pf) else 999:5.2f}  "
              f"EV=${ev:+6.2f}  net=${net_pnl:+,.0f}  "
              f"{'PASS' if ev_passes else 'FAIL'}")

        # Permutation test
        if not ev_passes or pf <= 0:
            perm_p = 1.0
        else:
            beats = 0
            for p in range(n_perm):
                new_c, new_h, new_l = shuffle_returns_inplace(c_arr, h_arr, l_arr, seed=p)
                pp = fixed_target_stop_simulate(
                    new_h, new_l, new_c, real_entries, side, stop_pts, target_pts, max_hold
                )
                if not pp:
                    continue
                pp_arr = np.array(pp)
                pp_pnl = pp_arr * dpp - comm
                pw = pp_pnl[pp_pnl > 0].sum()
                pl = -pp_pnl[pp_pnl <= 0].sum()
                ppf = pw / pl if pl > 0 else float("inf")
                if ppf >= pf:
                    beats += 1
            perm_p = (beats + 1) / (n_perm + 1)
        perm_passes = perm_p < 0.05
        print(f"       PERM:  p={perm_p:.4f}  {'PASS' if perm_passes else 'FAIL'}")

        cpcv_mean = cpcv.get("cpcv_mean_wr", 0)
        cpcv_min = cpcv.get("cpcv_min_wr", 0)
        wf_passes = cpcv_mean >= 0.55 and cpcv_min >= 0.50
        print(f"       WF:    CPCV mean={cpcv_mean*100:.1f}%  min={cpcv_min*100:.1f}%  "
              f"{'PASS' if wf_passes else 'FAIL'}")

        trades_for_mc = [type("T", (), {"pnl": float(p), "entry_time": None})() for p in pnl]
        mc = monte_carlo(trades_for_mc, n_paths=n_mc, starting_balance=50000.0,
                         apex_target=9000.0, apex_max_dd=3000.0, seed=42)
        mc_passes = mc["median_final"] > 50000.0 and mc["p_apex_pass"] >= 0.30
        print(f"       MC:    median=${mc['median_final']:,.0f}  Apex={mc['p_apex_pass']*100:.0f}%  "
              f"{'PASS' if mc_passes else 'FAIL'}")

        sens = {}
        for label, mult in [("low", 0.8), ("high", 1.2)]:
            alt = fixed_target_stop_simulate(
                h_arr, l_arr, c_arr, real_entries, side,
                stop_pts * mult, target_pts * mult, max_hold
            )
            if not alt:
                sens[label] = 0.0
                continue
            alt_arr = np.array(alt)
            alt_pnl = alt_arr * dpp - comm
            aw = alt_pnl[alt_pnl > 0].sum()
            al = -alt_pnl[alt_pnl <= 0].sum()
            sens[label] = float(aw / al) if al > 0 else float("inf")
        thr = 0.7 * pf if math.isfinite(pf) else 0.7 * 5.0
        sens_passes = sens["low"] >= thr and sens["high"] >= thr
        print(f"       SENS:  default={pf if math.isfinite(pf) else 999:5.2f} "
              f"low={sens['low']:5.2f} high={sens['high']:5.2f}  "
              f"{'PASS' if sens_passes else 'FAIL'}")

        all_pass = ev_passes and perm_passes and wf_passes and mc_passes and sens_passes
        print(f"       OVERALL: {'✅ ALL 5 PASS' if all_pass else '⚠️  partial'}  "
              f"({time.time()-t1:.1f}s)\n")

        results.append({
            "name": cname, "side": side,
            "stop_pts": stop_pts, "target_pts": target_pts,
            "n_trades": n_trades, "win_rate": wr, "ev_dollars": ev,
            "net_pnl": net_pnl, "profit_factor": pf if math.isfinite(pf) else None,
            "tests": {
                "ev": {"value": ev, "pass": ev_passes},
                "permutation": {"p_value": perm_p, "n_perm": n_perm, "pass": perm_passes},
                "walk_forward": {"cpcv_mean": cpcv_mean, "cpcv_min": cpcv_min, "pass": wf_passes},
                "monte_carlo": {"median_final": mc["median_final"],
                                "p_apex_pass": mc["p_apex_pass"], "pass": mc_passes},
                "parameter_sensitivity": {"pf_default": pf if math.isfinite(pf) else None,
                                          "pf_low": sens["low"], "pf_high": sens["high"],
                                          "pass": sens_passes},
            },
            "all_pass": all_pass,
        })

    n_all_pass = sum(1 for r in results if r["all_pass"])
    print("=" * 80)
    print(f"SUMMARY: {n_all_pass} of {len(results)} v4 patterns passed ALL 5 rigor tests")
    print("=" * 80)
    if n_all_pass:
        print("\nGold-standard v4 patterns:")
        for r in sorted([x for x in results if x["all_pass"]], key=lambda x: -x["net_pnl"]):
            pv = r["tests"]["permutation"]["p_value"]
            print(f"  {r['name']:<32} {r['side']:<6} WR={r['win_rate']*100:5.1f}% "
                  f"PF={r['profit_factor'] or 0:5.2f} net=${r['net_pnl']:>9,.0f} p={pv:.4f}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_perm": n_perm, "n_mc": n_mc,
        "n_patterns_tested": len(results),
        "n_all_pass": n_all_pass,
        "patterns": results,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Wrote -> {RESULTS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  Total runtime: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

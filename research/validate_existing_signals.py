"""
5-test rigor gauntlet for the EXISTING 5-min and WR (1-min) strategies,
run on the full 8 yrs of NQ data.

Same gauntlet as validate_mined_full but starts from a Signal class
(rather than a constraint chain). Calls signal.generate(intraday, daily)
and uses the resulting signal_time index as entries.

For 5-min strategies (research.signal_generator.ALL_SIGNALS): runs on 5-min
bars with stop=15 / target=30 (1:2 R:R, the bot's runtime default).

For WR strategies (research.mined_wr_signals.ALL_WR_SIGNALS): runs on 1-min
bars with each strategy's own stop_pts / target_pts / max_hold_bars.

Tier rules (same as merge_validated_patterns):
    Tier A : WR ≥ 60% AND 5/5 tests pass
    Tier B : positive EV AND ≥3/5 tests AND walk-forward + permutation pass
    Reject : everything else
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.backtest_engine import SLIP_ENTRY_PTS, SLIP_STOP_PTS, monte_carlo
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min,
)
from research.validate_mined_full import (
    _sim_inner, fixed_target_stop_simulate, shuffle_returns,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="data/validated_existing_8yr.json")
    p.add_argument("--n-perm", type=int, default=500)
    p.add_argument("--n-mc", type=int, default=10000)
    p.add_argument("--family", choices=["all", "5min", "wr"], default="all")
    return p.parse_args()


def _entries_from_signal(sig, intraday, daily):
    """Run signal.generate() and return positional indices into intraday."""
    try:
        df = sig.generate(intraday, daily)
    except Exception as e:
        print(f"       generate() failed: {e}")
        return []
    if df is None or df.empty:
        return []
    sig_times = df["signal_time"].to_numpy()
    pos = intraday.index.get_indexer(pd.DatetimeIndex(sig_times))
    return [i for i in pos if i >= 0]


def _validate_one(sig, intraday, daily, *, stop_pts, target_pts, max_hold,
                   family_label, n_perm, n_mc, contracts):
    name = getattr(sig, "name", sig.__class__.__name__)
    side = getattr(sig, "side", None) or ("LONG" if "LONG" in name.upper() else "SHORT")

    h_arr = intraday["high"].to_numpy(dtype=np.float64)
    l_arr = intraday["low"].to_numpy(dtype=np.float64)
    c_arr = intraday["close"].to_numpy(dtype=np.float64)

    print(f"  [{name}]  side={side}  stop={stop_pts}/target={target_pts}  "
          f"max_hold={max_hold}  contracts={contracts}", flush=True)
    t0 = time.time()
    entries = _entries_from_signal(sig, intraday, daily)
    if len(entries) < 30:
        print(f"       only {len(entries)} entries — SKIP")
        return None
    end_cap = len(intraday) - max_hold - 1
    entries = [i for i in entries if i < end_cap]

    # ---- EV ----
    real_pts = fixed_target_stop_simulate(h_arr, l_arr, c_arr, entries, side,
                                            stop_pts, target_pts, max_hold)
    if not real_pts:
        print("       no completed trades — SKIP")
        return None
    pts_arr = np.asarray(real_pts)
    dpp = contracts * 2.0
    comm = contracts * 2.0
    pnl = pts_arr * dpp - comm
    n_trades = len(pnl)
    wins = int((pts_arr > 0).sum())
    wr = wins / n_trades
    wins_ = pnl[pnl > 0].sum()
    losses_ = -pnl[pnl <= 0].sum()
    pf = float(wins_ / losses_) if losses_ > 0 else float("inf")
    ev_dollars = float(pnl.mean())
    net_pnl = float(pnl.sum())
    ev_pass = ev_dollars > 0
    print(f"       EV:    n={n_trades:>4}  WR={wr*100:5.1f}%  "
          f"PF={(pf if math.isfinite(pf) else 999):5.2f}  "
          f"EV=${ev_dollars:+6.2f}/trade  net=${net_pnl:+,.0f}  "
          f"{'PASS' if ev_pass else 'FAIL'}")

    # ---- PERMUTATION ----
    if not ev_pass or not math.isfinite(pf) or pf <= 0:
        perm_p = 1.0
    else:
        beats = 0
        for s in range(n_perm):
            nc, nh, nl = shuffle_returns(c_arr, h_arr, l_arr, seed=s)
            pp = fixed_target_stop_simulate(nh, nl, nc, entries, side,
                                              stop_pts, target_pts, max_hold)
            if not pp:
                continue
            pa = np.asarray(pp)
            ppnl = pa * dpp - comm
            pw = ppnl[ppnl > 0].sum()
            pl = -ppnl[ppnl <= 0].sum()
            ppf = pw / pl if pl > 0 else float("inf")
            if ppf >= pf:
                beats += 1
        perm_p = (beats + 1) / (n_perm + 1)
    perm_pass = perm_p < 0.05
    print(f"       PERM:  {n_perm} shuffles  p={perm_p:.4f}  "
          f"{'PASS' if perm_pass else 'FAIL'}")

    # ---- WALK-FORWARD (chronological 5-fold WR consistency) ----
    pts_chron = pts_arr  # entries are already chronological
    fold_size = len(pts_chron) // 5
    fold_wrs = []
    for k in range(5):
        a = k * fold_size
        b = (k + 1) * fold_size if k < 4 else len(pts_chron)
        slice_ = pts_chron[a:b]
        if len(slice_) < 5:
            continue
        fold_wrs.append((slice_ > 0).mean())
    wf_mean = float(np.mean(fold_wrs)) if fold_wrs else 0
    wf_min = float(np.min(fold_wrs)) if fold_wrs else 0
    # WF pass: same as v3 — mean ≥ 50% AND every fold ≥ 40%  (relaxed for 1:2 RR
    # where break-even WR is ~37%, so WR≥40% means positive EV per fold)
    wf_pass = wf_mean >= 0.50 and wf_min >= 0.40
    print(f"       WF:    fold_mean={wf_mean*100:5.1f}%  fold_min={wf_min*100:5.1f}%  "
          f"{'PASS' if wf_pass else 'FAIL'}")

    # ---- MONTE CARLO ----
    trades_for_mc = [type("T", (), {"pnl": float(x), "entry_time": None})()
                     for x in pnl]
    mc = monte_carlo(trades_for_mc, n_paths=n_mc,
                     starting_balance=50000.0,
                     apex_target=9000.0, apex_max_dd=3000.0, seed=42)
    mc_pass = (mc["median_final"] > 50000.0) and (mc["p_apex_pass"] >= 0.30)
    print(f"       MC:    median=${mc['median_final']:>10,.0f}  "
          f"Apex={mc['p_apex_pass']*100:.0f}%  {'PASS' if mc_pass else 'FAIL'}")

    # ---- SENSITIVITY (±20% stop) ----
    sens = {}
    for tag, mult in [("low", 0.8), ("high", 1.2)]:
        ap = fixed_target_stop_simulate(h_arr, l_arr, c_arr, entries, side,
                                          stop_pts * mult, target_pts * mult,
                                          max_hold)
        if not ap:
            sens[tag] = 0.0; continue
        ap_arr = np.asarray(ap)
        apnl = ap_arr * dpp - comm
        apw = apnl[apnl > 0].sum()
        apl = -apnl[apnl <= 0].sum()
        sens[tag] = float(apw / apl) if apl > 0 else float("inf")
    thresh = 0.7 * (pf if math.isfinite(pf) else 5.0)
    sens_pass = sens["low"] >= thresh and sens["high"] >= thresh
    print(f"       SENS:  pf_def={(pf if math.isfinite(pf) else 999):5.2f}  "
          f"low={sens['low']:5.2f}  high={sens['high']:5.2f}  "
          f"{'PASS' if sens_pass else 'FAIL'}")

    n_pass = sum([ev_pass, perm_pass, wf_pass, mc_pass, sens_pass])
    if wr >= 0.60 and n_pass == 5:
        tier = "A"
    elif ev_pass and n_pass >= 3 and wf_pass and perm_pass:
        tier = "B"
    else:
        tier = "REJECT"
    print(f"       TIER {tier}  ({n_pass}/5)  ({time.time()-t0:.1f}s)\n")

    return {
        "name": name, "side": side, "family": family_label,
        "stop_pts": float(stop_pts), "target_pts": float(target_pts),
        "max_hold": int(max_hold),
        "n_trades": n_trades, "win_rate": wr,
        "ev_dollars": ev_dollars, "net_pnl": net_pnl,
        "profit_factor": float(pf) if math.isfinite(pf) else None,
        "tests": {
            "ev": {"value": ev_dollars, "pass": ev_pass},
            "permutation": {"p_value": perm_p, "n_perm": n_perm, "pass": perm_pass},
            "walk_forward": {"fold_mean": wf_mean, "fold_min": wf_min,
                              "fold_wrs": fold_wrs, "pass": wf_pass},
            "monte_carlo": {**mc, "pass": mc_pass},
            "parameter_sensitivity": {
                "pf_default": float(pf) if math.isfinite(pf) else None,
                "pf_low_20pct": sens["low"], "pf_high_20pct": sens["high"],
                "pass": sens_pass,
            },
        },
        "n_passes": n_pass, "tier": tier,
    }


def main() -> int:
    args = parse_args()
    n_perm = args.n_perm
    n_mc = args.n_mc

    print("=" * 80)
    print(f"VALIDATE EXISTING SIGNALS on 8 yrs NQ data — 5-test rigor gauntlet")
    print(f"  perms: {n_perm}    monte_carlo paths: {n_mc}")
    print(f"  family: {args.family}")
    print("=" * 80)

    # Load both timeframes
    print("\n[1/3] Loading data ...", flush=True)
    t0 = time.time()
    m5 = load_intraday_5min("nq")
    m1 = load_intraday_1min("nq")
    daily = load_daily("nq")
    print(f"  5-min bars: {len(m5):,}    1-min bars: {len(m1):,}    "
          f"daily: {len(daily):,}   ({time.time()-t0:.1f}s)")

    targets = []
    if args.family in ("all", "5min"):
        from research.signal_generator import ALL_SIGNALS
        for s in ALL_SIGNALS:
            targets.append((s, m5, "5min", 15.0, 30.0, 80, 30))   # bot defaults: stop=15, RR=2, max_hold=80 5min bars, 30 MNQ
    if args.family in ("all", "wr"):
        from research.mined_wr_signals import ALL_WR_SIGNALS
        for s in ALL_WR_SIGNALS:
            targets.append((s, m1, "wr",
                            float(s.stop_pts), float(s.target_pts),
                            int(s.max_hold_bars), 5))

    print(f"\n[2/3] Validating {len(targets)} strategies ...\n", flush=True)
    results = []
    for sig, intra, fam, stop, target, mh, contracts in targets:
        res = _validate_one(sig, intra, daily,
                              stop_pts=stop, target_pts=target, max_hold=mh,
                              family_label=fam, n_perm=n_perm, n_mc=n_mc,
                              contracts=contracts)
        if res is not None:
            results.append(res)

    # Summary
    n_a = sum(1 for r in results if r["tier"] == "A")
    n_b = sum(1 for r in results if r["tier"] == "B")
    n_r = sum(1 for r in results if r["tier"] == "REJECT")
    print("=" * 80)
    print(f"BUCKETING:  Tier A = {n_a}    Tier B = {n_b}    Reject = {n_r}")
    print("=" * 80)
    for tier in ("A", "B", "REJECT"):
        rows = [r for r in results if r["tier"] == tier]
        if not rows: continue
        print(f"\nTier {tier}:")
        for r in sorted(rows, key=lambda x: -x["net_pnl"]):
            pf = r["profit_factor"] or 0
            print(f"  {r['name']:<30} {r['side']:<6} WR={r['win_rate']*100:5.1f}%  "
                  f"PF={pf:5.2f}  net=${r['net_pnl']:+,.0f}  "
                  f"({r['n_passes']}/5)")

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_perm": n_perm, "n_mc": n_mc,
        "patterns": results,
    }, indent=2, default=str))
    print(f"\n  Wrote -> {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

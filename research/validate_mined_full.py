"""
Generic 5-test rigor validator for ANY mined-patterns JSON.

Reads a `mined_v3_*.json` produced by pattern_miner_v3 and runs all 5 rigor
tests on each pattern by reconstructing the entry signal directly from the
saved constraints (no need for emitted Signal classes).

Tests:
    1. Mathematical EV       — net P&L > 0 after slippage + commission
    2. Permutation (1000x)   — real PF beats ≥ 95% of shuffled-bar permutations
    3. Walk-forward / CPCV   — already enforced upstream, copied through
    4. Monte Carlo (10k x)   — median final > start AND P(Apex pass) ≥ 30%
    5. Parameter sensitivity — ±20% stop preserves ≥ 70% of default PF

Pattern bucketing on output:
    Tier A  — WR ≥ 60%  AND  passes 5/5 tests           (live-ready)
    Tier B  — WR ≥ 55%  AND  passes ≥ 3/5 tests         (watchlist)
    Reject  — everything else

Usage:
    python -m research.validate_mined_full \\
        --input  data/mined_v3_8yr.json \\
        --output data/validated_v3_8yr.json
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
from research.local_data_loader import load_daily, load_intraday_1min
from research.pattern_miner_v3 import V3_FEATURES, build_v3_features

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="mined_v3_*.json path")
    p.add_argument("--output", required=True, help="validated output JSON path")
    p.add_argument("--fast", action="store_true",
                   help="200 perms / 2k MC paths (default 1000 / 10k)")
    p.add_argument("--n-perm", type=int, default=None,
                   help="Override perm count")
    p.add_argument("--n-mc", type=int, default=None,
                   help="Override MC paths")
    p.add_argument("--with-cross-asset", action="store_true",
                   help="Build cross-asset features (use when mined with --with-cross-asset)")
    p.add_argument("--max-patterns", type=int, default=None,
                   help="Limit how many patterns get validated (for testing)")
    return p.parse_args()


def constraints_to_mask(X: pd.DataFrame, constraints: list) -> np.ndarray:
    """Reproduce a tree-leaf mask from the saved (feature, op, threshold) chain."""
    mask = np.ones(len(X), dtype=bool)
    for feat, op, thr in constraints:
        if feat not in X.columns:
            return np.zeros(len(X), dtype=bool)
        v = X[feat].to_numpy()
        if op == "<=":
            mask &= (v <= thr)
        elif op == ">":
            mask &= (v > thr)
        else:
            return np.zeros(len(X), dtype=bool)
    # Drop NaN rows (any NaN in features means constraint can't be evaluated)
    nan_mask = X[[c[0] for c in constraints if c[0] in X.columns]].isna().any(axis=1).to_numpy()
    mask &= ~nan_mask
    return mask


try:
    from numba import njit
except ImportError:
    def njit(*a, **k):
        def deco(f): return f
        return deco


@njit(cache=True, fastmath=True)
def _sim_inner(h_arr, l_arr, c_arr, entries, is_long,
               stop_pts, target_pts, max_hold, slip_in, slip_stop):
    n = len(c_arr)
    out = np.empty(len(entries), dtype=np.float64)
    out_n = 0
    for k in range(len(entries)):
        i = entries[k]
        if i + max_hold >= n:
            continue
        entry_raw = c_arr[i]
        if is_long:
            entry = entry_raw + slip_in
            stop = entry - stop_pts
            target = entry + target_pts
            done = False
            res = 0.0
            for j in range(i + 1, i + 1 + max_hold):
                lo = l_arr[j]; hi = h_arr[j]
                if lo <= stop:
                    res = -(stop_pts + slip_stop); done = True; break
                if hi >= target:
                    res = target_pts; done = True; break
            if not done:
                res = c_arr[i + max_hold] - entry
        else:
            entry = entry_raw - slip_in
            stop = entry + stop_pts
            target = entry - target_pts
            done = False
            res = 0.0
            for j in range(i + 1, i + 1 + max_hold):
                lo = l_arr[j]; hi = h_arr[j]
                if hi >= stop:
                    res = -(stop_pts + slip_stop); done = True; break
                if lo <= target:
                    res = target_pts; done = True; break
            if not done:
                res = entry - c_arr[i + max_hold]
        out[out_n] = res
        out_n += 1
    return out[:out_n]


def fixed_target_stop_simulate(h_arr, l_arr, c_arr, entries, side,
                                stop_pts, target_pts, max_hold,
                                slip_in=SLIP_ENTRY_PTS, slip_stop=SLIP_STOP_PTS):
    if len(entries) == 0:
        return []
    ent_arr = np.asarray(entries, dtype=np.int64)
    res = _sim_inner(h_arr, l_arr, c_arr, ent_arr, side == "LONG",
                     float(stop_pts), float(target_pts), int(max_hold),
                     float(slip_in), float(slip_stop))
    return list(res)


def shuffle_returns(c_orig, h_orig, l_orig, seed):
    """Shuffle log-returns and rebuild OHL preserving bar geometry."""
    rng = np.random.default_rng(seed)
    log_rets = np.diff(np.log(c_orig))
    rng.shuffle(log_rets)
    new_c = c_orig[0] * np.exp(np.concatenate([[0.0], np.cumsum(log_rets)]))
    bar_range_orig = h_orig - l_orig
    body_orig = c_orig - np.concatenate([[c_orig[0]], c_orig[:-1]])
    new_open = np.concatenate([[new_c[0]], new_c[:-1]])
    range_part = np.abs(bar_range_orig - np.abs(body_orig)) * 0.5
    new_h = np.maximum(new_open, new_c) + range_part
    new_l = np.minimum(new_open, new_c) - range_part
    return new_c, new_h, new_l


def main() -> int:
    args = parse_args()
    n_perm = args.n_perm if args.n_perm else (200 if args.fast else 1000)
    n_mc = args.n_mc if args.n_mc else (2000 if args.fast else 10000)

    in_path = Path(args.input)
    if not in_path.is_absolute():
        in_path = PROJECT_ROOT / in_path
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path

    print("=" * 80)
    print("MINED-PATTERN VALIDATOR — 5 rigor tests + Tier A/B bucketing")
    print(f"  input:  {in_path.relative_to(PROJECT_ROOT) if in_path.is_relative_to(PROJECT_ROOT) else in_path}")
    print(f"  output: {out_path.relative_to(PROJECT_ROOT) if out_path.is_relative_to(PROJECT_ROOT) else out_path}")
    print(f"  perms: {n_perm}    monte_carlo paths: {n_mc}")
    print(f"  cross-asset features: {args.with_cross_asset}")
    print("=" * 80)

    print("\n[1/3] Loading data + building features ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"  1-min bars: {len(intraday):,}  ({days} days)")
    X = build_v3_features(intraday, daily)
    feature_names = list(V3_FEATURES)
    if args.with_cross_asset:
        from research.cross_asset_features import (
            build_cross_asset_features, CROSS_ASSET_FEATURES,
        )
        xa = build_cross_asset_features(intraday.index)
        X = pd.concat([X, xa], axis=1)
        feature_names = list(V3_FEATURES) + list(CROSS_ASSET_FEATURES)
    print(f"  features: {len(feature_names)}  ({time.time()-t0:.1f}s)")

    payload = json.loads(in_path.read_text())
    patterns = payload["patterns"]
    if args.max_patterns:
        patterns = patterns[: args.max_patterns]
    print(f"  patterns to validate: {len(patterns)}")

    h_arr = intraday["high"].to_numpy(dtype=np.float64)
    l_arr = intraday["low"].to_numpy(dtype=np.float64)
    c_arr = intraday["close"].to_numpy(dtype=np.float64)

    print(f"\n[2/3] Running 5 rigor tests on each pattern ...\n")

    results = []
    for k, p in enumerate(patterns, 1):
        cname = p["name"]
        side = p["side"]
        stop_pts = float(p["stop_pts"])
        target_pts = float(p["target_pts"])
        max_hold = int(p["max_hold"])
        constraints = [tuple(c) for c in p["constraints"]]
        cpcv_mean = float(p.get("cpcv_mean_wr", 0))
        cpcv_min = float(p.get("cpcv_min_wr", 0))

        print(f"  [{k:>2}/{len(patterns)}] {cname}", flush=True)
        t1 = time.time()

        # Reconstruct entry mask + cap to in-window indices
        mask = constraints_to_mask(X, constraints)
        end_cap = len(intraday) - max_hold - 1
        mask[end_cap:] = False
        real_entries = np.where(mask)[0].tolist()
        if len(real_entries) < 30:
            print(f"       only {len(real_entries)} entries — SKIP")
            continue

        # ---- Test 1: EV ----
        real_pts = fixed_target_stop_simulate(
            h_arr, l_arr, c_arr, real_entries, side, stop_pts, target_pts, max_hold
        )
        if not real_pts:
            print("       no completed trades — SKIP"); continue
        real_pts_arr = np.asarray(real_pts)
        contracts = 5
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl = real_pts_arr * dpp - comm
        net_pnl = float(pnl.sum())
        n_trades = len(pnl)
        wins = int((real_pts_arr > 0).sum())
        wr = wins / n_trades
        wins_ = pnl[pnl > 0].sum()
        losses_ = -pnl[pnl <= 0].sum()
        pf = float(wins_ / losses_) if losses_ > 0 else float("inf")
        ev_dollars = float(pnl.mean())
        ev_pass = ev_dollars > 0
        print(f"       EV:    n={n_trades:>4}  WR={wr*100:5.1f}%  "
              f"PF={pf if math.isfinite(pf) else 999:5.2f}  "
              f"EV=${ev_dollars:+6.2f}/trade  net=${net_pnl:+,.0f}  "
              f"{'PASS' if ev_pass else 'FAIL'}")

        # ---- Test 2: Permutation ----
        if not ev_pass or not math.isfinite(pf) or pf <= 0:
            perm_p = 1.0
        else:
            beats = 0
            for s in range(n_perm):
                nc, nh, nl = shuffle_returns(c_arr, h_arr, l_arr, seed=s)
                pp = fixed_target_stop_simulate(nh, nl, nc, real_entries,
                                                 side, stop_pts, target_pts, max_hold)
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

        # ---- Test 3: WF / CPCV (from upstream) ----
        wf_pass = cpcv_mean >= 0.55 and cpcv_min >= 0.50
        print(f"       WF:    CPCV mean={cpcv_mean*100:5.1f}%  min_fold={cpcv_min*100:5.1f}%  "
              f"{'PASS' if wf_pass else 'FAIL'}")

        # ---- Test 4: Monte Carlo ----
        trades_for_mc = [type("T", (), {"pnl": float(x), "entry_time": None})()
                         for x in pnl]
        mc = monte_carlo(trades_for_mc, n_paths=n_mc,
                         starting_balance=50000.0,
                         apex_target=9000.0, apex_max_dd=3000.0,
                         seed=42)
        mc_pass = (mc["median_final"] > 50000.0) and (mc["p_apex_pass"] >= 0.30)
        print(f"       MC:    median=${mc['median_final']:>10,.0f}  "
              f"p5=${mc['p5_final']:>10,.0f}  Apex={mc['p_apex_pass']*100:.0f}%  "
              f"{'PASS' if mc_pass else 'FAIL'}")

        # ---- Test 5: Parameter sensitivity ----
        sens = {}
        for tag, mult in [("low", 0.8), ("high", 1.2)]:
            ap = fixed_target_stop_simulate(h_arr, l_arr, c_arr, real_entries,
                                             side, stop_pts * mult, target_pts * mult,
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
        print(f"       SENS:  pf_default={pf if math.isfinite(pf) else 999:5.2f}  "
              f"pf_low={sens['low']:5.2f}  pf_high={sens['high']:5.2f}  "
              f"{'PASS' if sens_pass else 'FAIL'}")

        n_pass = sum([ev_pass, perm_pass, wf_pass, mc_pass, sens_pass])
        # Bucketing logic
        if wr >= 0.60 and n_pass == 5:
            tier = "A"
        elif wr >= 0.55 and n_pass >= 3:
            tier = "B"
        else:
            tier = "REJECT"
        print(f"       TIER {tier}  ({n_pass}/5 tests)  ({time.time()-t1:.1f}s)\n")

        results.append({
            "name": cname,
            "side": side,
            "stop_pts": stop_pts,
            "target_pts": target_pts,
            "max_hold": max_hold,
            "n_trades": n_trades,
            "win_rate": wr,
            "ev_dollars": ev_dollars,
            "net_pnl": net_pnl,
            "profit_factor": float(pf) if math.isfinite(pf) else None,
            "cpcv_mean_wr": cpcv_mean,
            "cpcv_min_wr": cpcv_min,
            "tests": {
                "ev": {"value": ev_dollars, "pass": ev_pass},
                "permutation": {"p_value": perm_p, "n_perm": n_perm, "pass": perm_pass},
                "walk_forward": {"cpcv_mean": cpcv_mean, "cpcv_min": cpcv_min, "pass": wf_pass},
                "monte_carlo": {**mc, "pass": mc_pass},
                "parameter_sensitivity": {
                    "pf_default": float(pf) if math.isfinite(pf) else None,
                    "pf_low_20pct": sens["low"], "pf_high_20pct": sens["high"],
                    "pass": sens_pass,
                },
            },
            "n_passes": n_pass,
            "tier": tier,
            "constraints": constraints,
        })

    # Final summary
    n_a = sum(1 for r in results if r["tier"] == "A")
    n_b = sum(1 for r in results if r["tier"] == "B")
    n_r = sum(1 for r in results if r["tier"] == "REJECT")
    print("=" * 80)
    print(f"BUCKETING:  Tier A = {n_a}     Tier B = {n_b}     REJECT = {n_r}")
    print("=" * 80)

    print("\nTier A (60%+ WR, 5/5 rigor tests):")
    print(f"  {'name':<35} {'side':<6} {'WR':>6} {'PF':>5} {'net':>11} {'p_val':>7}")
    print("  " + "-" * 78)
    for r in sorted([x for x in results if x["tier"] == "A"], key=lambda x: -x["net_pnl"]):
        pf_ = r["profit_factor"] or 0.0
        print(f"  {r['name']:<35} {r['side']:<6} {r['win_rate']*100:>5.1f}% "
              f"{pf_:>5.2f} ${r['net_pnl']:>10,.0f} "
              f"{r['tests']['permutation']['p_value']:>7.4f}")

    print("\nTier B (watchlist — 55%+ WR, 3+/5 tests):")
    print(f"  {'name':<35} {'side':<6} {'WR':>6} {'PF':>5} {'net':>11} {'tests':>7}")
    print("  " + "-" * 78)
    for r in sorted([x for x in results if x["tier"] == "B"], key=lambda x: -x["net_pnl"]):
        pf_ = r["profit_factor"] or 0.0
        print(f"  {r['name']:<35} {r['side']:<6} {r['win_rate']*100:>5.1f}% "
              f"{pf_:>5.2f} ${r['net_pnl']:>10,.0f}    {r['n_passes']}/5")

    out_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(in_path.relative_to(PROJECT_ROOT)) if in_path.is_relative_to(PROJECT_ROOT) else str(in_path),
        "n_perm": n_perm,
        "n_mc": n_mc,
        "with_cross_asset": args.with_cross_asset,
        "n_validated": len(results),
        "n_tier_a": n_a, "n_tier_b": n_b, "n_reject": n_r,
        "patterns": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2, default=str))
    print(f"\n  Wrote -> {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

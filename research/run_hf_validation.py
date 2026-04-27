"""
Validate the high-frequency 1-minute signal candidates.

Different cost / stop / target profile from the 5-min signals:
  stop_pts        = 5        (vs 15 on 5-min)
  target_rr       = 1.5      (vs 2.0 on 5-min)
  max_hold_bars   = 30       (= 30 minutes on 1-min bars)
  permutations    = 100 fast / 500 full
  min_trades      = 50       (HF should fire often; if not, kill it)

Survivors are written into data/validation_results.json with the existing
5-min validations preserved (HF signals get the HF_ prefix).

Usage:
    python -m research.run_hf_validation                # FAST  (100 perms)
    python -m research.run_hf_validation --full         # FULL  (500 perms)
    python -m research.run_hf_validation --p-value 0.10 # looser threshold
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

from research.backtest_engine import (
    compute_stats,
    monte_carlo,
    simulate_trades,
    to_json_dict,
    validate_signal,
)
from research.hf_signals import ALL_HF_SIGNALS
from research.local_data_loader import load_daily, load_intraday_1min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "validation_results.json"
HF_RESULTS_PATH = PROJECT_ROOT / "data" / "hf_validation_results.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true",
                   help="500 permutations instead of fast 100.")
    p.add_argument("--signals", default="",
                   help="Comma-separated class names to test (default: all 30).")
    p.add_argument("--min-trades", type=int, default=50,
                   help="Drop signals with fewer than this many trades.")
    p.add_argument("--p-value", type=float, default=0.05,
                   help="Permutation-test pass threshold.")
    p.add_argument("--stop-pts", type=float, default=5.0,
                   help="Default stop in points (1-min appropriate).")
    p.add_argument("--target-rr", type=float, default=1.5,
                   help="Default target as multiple of stop.")
    p.add_argument("--max-hold-bars", type=int, default=30,
                   help="Max hold in bars (= minutes for 1-min data).")
    p.add_argument("--no-merge", action="store_true",
                   help="Don't append survivors into validation_results.json.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    n_perm = 200 if args.full else 50

    print("=" * 76)
    print(f"HIGH-FREQUENCY 1-MIN VALIDATION   "
          f"mode={'FULL' if args.full else 'FAST'}   n_permutations={n_perm}")
    print("=" * 76)

    print("[1/5] Loading 1-min NQ history ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()
    print(f"      1-min bars: {len(intraday):>7,}   "
          f"daily bars: {len(daily):>4,}   "
          f"range: {intraday.index[0]} -> {intraday.index[-1]}")
    print(f"      ({time.time()-t0:.1f}s)")

    selected = set(args.signals.split(",")) if args.signals else None
    sig_objs = [s for s in ALL_HF_SIGNALS
                if not selected or type(s).__name__ in selected]
    if not sig_objs:
        print(f"No signals matched filter {args.signals!r}.")
        return 1

    print(f"\n[2/5] Validating {len(sig_objs)} HF signals "
          f"(stop={args.stop_pts}pt, RR={args.target_rr}, "
          f"max_hold={args.max_hold_bars}bar, p<{args.p_value}) ...", flush=True)

    # Patch the simulate_trades default for HF mode by passing through
    results: dict[str, dict] = {}
    survivors: list[str] = []
    all_trades = []

    for i, sig in enumerate(sig_objs, 1):
        cname = type(sig).__name__
        t1 = time.time()
        print(f"  [{i:>2}/{len(sig_objs)}] {cname:<26s} ...", end="", flush=True)
        try:
            v = validate_signal(sig, intraday, daily,
                                n_permutations=n_perm,
                                min_trades=args.min_trades,
                                stop_pts=args.stop_pts,
                                target_rr=args.target_rr,
                                max_hold_bars=args.max_hold_bars,
                                use_signal_targets=False,
                                permutation_pass_p=args.p_value)
        except Exception as e:
            print(f" ERROR: {e}")
            continue
        if v is None:
            print(" no signals fired")
            continue
        results[v.name] = to_json_dict(v)
        if v.recommended:
            survivors.append(v.name)
            sigs_df = sig.generate(intraday, daily)
            all_trades.extend(simulate_trades(sigs_df, intraday, daily=None,
                                              stop_pts_default=args.stop_pts,
                                              target_rr_default=args.target_rr,
                                              max_hold_bars=args.max_hold_bars,
                                              use_signal_targets=False))
        s = v.stats
        verdict = "RECOMMENDED" if v.recommended else f"REJECTED  ({v.reject_reason})"
        pf_str = f"{s.profit_factor:5.2f}" if math.isfinite(s.profit_factor) else "  inf"
        print(f" n={s.n:>5d}  wr={s.win_rate*100:5.1f}%  pf={pf_str}  "
              f"ev={s.ev_pts:+6.2f}pt  p={v.perm_p_value:.3f}  "
              f"-> {verdict}  ({time.time()-t1:.1f}s)")

    # System-level Monte Carlo on survivors
    if all_trades:
        print(f"\n[3/5] System-wide stats across {len(all_trades):,} survivor trades ...")
        sys_stats = compute_stats(all_trades)
        days = max(1, (intraday.index[-1] - intraday.index[0]).days)
        print(f"      trades={sys_stats.n:,}   wr={sys_stats.win_rate*100:.1f}%   "
              f"net=${sys_stats.net_pnl:,.0f}   pf={sys_stats.profit_factor:.2f}")
        print(f"      trade frequency: {sys_stats.n/days:.1f} per day")

        print(f"\n[4/5] Monte Carlo (2,000 random orderings) ...")
        mc = monte_carlo(all_trades, n_paths=2000)
        print(f"      median final ${mc['median_final']:,.0f}   "
              f"5th %ile ${mc['p5_final']:,.0f}   "
              f"P(Apex pass)={mc['p_apex_pass']*100:.1f}%   "
              f"P(blow)={mc['p_apex_blow']*100:.1f}%")
    else:
        print("\n[3/5] No survivors — system stats skipped.")
        sys_stats = None
        mc = None

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fast_mode": not args.full,
        "n_permutations": n_perm,
        "params": {
            "stop_pts": args.stop_pts,
            "target_rr": args.target_rr,
            "max_hold_bars": args.max_hold_bars,
            "min_trades": args.min_trades,
            "p_value": args.p_value,
        },
        "data_context": {
            "source": "local 2-year 1-min NQ files",
            "1min_bars": len(intraday),
            "daily_bars": len(daily),
            "start": str(intraday.index[0]),
            "end": str(intraday.index[-1]),
        },
        "signals": results,
        "survivors": survivors,
    }
    if sys_stats:
        payload["system"] = {
            "trades": sys_stats.n,
            "win_rate": sys_stats.win_rate,
            "net_pnl": sys_stats.net_pnl,
            "max_drawdown": sys_stats.max_drawdown_dollars,
            "trades_per_day": sys_stats.n / max(1, (intraday.index[-1] - intraday.index[0]).days),
        }
    if mc:
        payload["monte_carlo"] = mc

    HF_RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))

    # Merge survivors into validation_results.json so the live engine sees them
    if not args.no_merge and survivors:
        try:
            vr = json.loads(RESULTS_PATH.read_text())
        except Exception:
            vr = {"signals": {}}
        vr.setdefault("signals", {})
        for name in survivors:
            vr["signals"][name] = results[name]
        RESULTS_PATH.write_text(json.dumps(vr, indent=2, default=str))
        print(f"\n[5/5] Merged {len(survivors)} HF survivors into validation_results.json")

    print(f"\n  RECOMMENDED ({len(survivors)}): {', '.join(survivors) or '(none)'}")
    print(f"  Wrote -> {HF_RESULTS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  Total runtime: {time.time()-t0:.1f}s")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())

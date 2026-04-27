"""
Run the full validation pipeline against the local 2-year NQ history,
write data/validation_results.json, and print a one-line summary per signal.

Usage:
    python -m research.run_validation              # FAST mode (200 permutations)
    python -m research.run_validation --full       # FULL mode (1000 permutations)
    python -m research.run_validation --signals PDLTouch,EQ50Long
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
    SignalValidation,
    compute_stats,
    monte_carlo,
    simulate_trades,
    to_json_dict,
    validate_signal,
)
from research.local_data_loader import load_daily, load_intraday_5min
from research.signal_generator import ALL_SIGNALS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "validation_results.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true",
                   help="Use 1000 permutations instead of fast 200.")
    p.add_argument("--signals", default="",
                   help="Comma-separated class names to test (default: all).")
    p.add_argument("--min-trades", type=int, default=20,
                   help="Drop signals with fewer than this many trades.")
    p.add_argument("--p-value", type=float, default=0.05,
                   help="Permutation-test pass threshold.")
    p.add_argument("--stop-pts", type=float, default=15.0)
    p.add_argument("--target-rr", type=float, default=2.0)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    n_perm = 1000 if args.full else 200

    print("=" * 76)
    print(f"NQ STRATEGY VALIDATION   mode={'FULL' if args.full else 'FAST'}   "
          f"n_permutations={n_perm}")
    print("=" * 76)

    print("[1/5] Loading 2-year local NQ history ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_5min()
    daily = load_daily()
    print(f"      5-min bars: {len(intraday):>7,}   "
          f"daily bars: {len(daily):>4,}   "
          f"range: {intraday.index[0]} -> {intraday.index[-1]}")
    print(f"      ({time.time()-t0:.1f}s)")

    selected = set(args.signals.split(",")) if args.signals else None
    sig_objs = [s for s in ALL_SIGNALS
                if not selected or type(s).__name__ in selected]
    if not sig_objs:
        print(f"No signals matched filter {args.signals!r}.")
        return 1

    print(f"\n[2/5] Validating {len(sig_objs)} signals "
          f"(min_trades={args.min_trades}, p<{args.p_value}) ...", flush=True)

    results: dict[str, dict] = {}
    all_trades = []
    for i, sig in enumerate(sig_objs, 1):
        cname = type(sig).__name__
        t1 = time.time()
        print(f"  [{i:>2}/{len(sig_objs)}] {cname:<22s} ...", end="", flush=True)
        v = validate_signal(sig, intraday, daily,
                            n_permutations=n_perm,
                            min_trades=args.min_trades,
                            stop_pts=args.stop_pts,
                            target_rr=args.target_rr,
                            permutation_pass_p=args.p_value)
        if v is None:
            print(" no signals fired")
            continue
        results[v.name] = to_json_dict(v)
        # Collect trades for system-wide stats
        sigs_df = sig.generate(intraday, daily)
        all_trades.extend(simulate_trades(sigs_df, intraday, daily=daily,
                                          stop_pts_default=args.stop_pts,
                                          target_rr_default=args.target_rr))
        s = v.stats
        verdict = "RECOMMENDED" if v.recommended else f"REJECTED  ({v.reject_reason})"
        print(f" n={s.n:>4d}  wr={s.win_rate*100:5.1f}%  "
              f"pf={s.profit_factor if math.isfinite(s.profit_factor) else 999:5.2f}  "
              f"ev={s.ev_pts:+6.2f}pt  p={v.perm_p_value:.3f}  wf={v.wf_consistency:.2f}  "
              f"-> {verdict}  ({time.time()-t1:.1f}s)")

    # System-level stats
    print(f"\n[3/5] System-wide stats across all {len(all_trades):,} simulated trades ...")
    sys_stats = compute_stats(all_trades)
    final_eq = 50000.0 + sys_stats.net_pnl
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    ann_ret = (final_eq / 50000.0) ** (365.0 / days) - 1.0
    calmar = ann_ret / abs(sys_stats.max_drawdown_dollars / 50000.0) if sys_stats.max_drawdown_dollars < 0 else 0.0
    sys_dict = {
        "trades": sys_stats.n,
        "win_rate": sys_stats.win_rate,
        "net_pnl": sys_stats.net_pnl,
        "final_equity": final_eq,
        "max_drawdown": sys_stats.max_drawdown_dollars,
        "ann_return": ann_ret,
        "calmar": calmar,
    }
    print(f"      trades={sys_stats.n:,}   wr={sys_stats.win_rate*100:.1f}%   "
          f"net=${sys_stats.net_pnl:,.0f}   max_dd=${sys_stats.max_drawdown_dollars:,.0f}   "
          f"calmar={calmar:.2f}")

    # Stage 6: Monte Carlo system-wide
    print(f"\n[4/5] Monte Carlo (2,000 random orderings, Apex sim) ...")
    mc = monte_carlo(all_trades, n_paths=2000)
    print(f"      median final ${mc['median_final']:,.0f}   "
          f"5th %ile ${mc['p5_final']:,.0f}   "
          f"P(Apex pass)={mc['p_apex_pass']*100:.1f}%   "
          f"P(blow)={mc['p_apex_blow']*100:.1f}%")

    # Write results
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fast_mode": not args.full,
        "data_context": {
            "source": "local 2-year 1-min NQ files",
            "5min_bars": len(intraday),
            "daily_bars": len(daily),
            "start": str(intraday.index[0]),
            "end": str(intraday.index[-1]),
        },
        "signals": results,
        "system": sys_dict,
        "monte_carlo": mc,
    }

    print(f"\n[5/5] Writing results -> {RESULTS_PATH.relative_to(PROJECT_ROOT)} ...")
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    rec = sorted([n for n, r in results.items() if r["recommended"]])
    rej = sorted([n for n, r in results.items() if not r["recommended"]])
    print(f"\n  RECOMMENDED ({len(rec)}): {', '.join(rec) or '(none)'}")
    print(f"  REJECTED    ({len(rej)}): {', '.join(rej) or '(none)'}")
    print()
    print(f"  Total runtime: {time.time()-t0:.1f}s")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())

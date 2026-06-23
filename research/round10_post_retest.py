"""Round 10 post-hoc re-test: runs the GA survivors and any RL strategy
against the full 60-day window after the main pass completes.

We append the resulting metrics to round10_results.md (Section 8 — POST)
and to round10_summary.csv.
"""
from __future__ import annotations
import argparse
import csv
import os
import pickle
import sys
import time
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from research import round4_search as _r4
from research import round6_search as _r6
from research import round7_search as _r7
from research import round8_search as _r8
from research import round9_search as _r9
from research import round10_search as _r10

MarketablePullback = _r6.MarketablePullback
BarBuilder = _r4.BarBuilder
MARKET = _r8.MARKET
REGIME = _r9.REGIME
TAPE = _r10.TAPE
PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
NQ_PER_PT = 20.0
FEE_FULL_RT = _r7.TOTAL_RT_COST
FEE_PROP_RT = _r7.COMM_RT
r9_bot_on_tick = _r9.r9_bot_on_tick
attach_r7_executor = _r7.attach_r7_executor

DEFAULT_OFFSET = 7_820_974_790


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--max-days", type=int, default=60)
    args = ap.parse_args()

    survivors = []
    p = "/home/user/HFTBot/research/round10_ga_survivors.pkl"
    if os.path.exists(p):
        with open(p, "rb") as f:
            survivors = pickle.load(f)

    if not survivors:
        print("[post] No GA survivors found, nothing to do.", file=sys.stderr)
        return

    strats_1m = []
    strats_15s = []
    strats_30s = []
    for spec in survivors[:15]:
        max_hold = 120 if spec['granularity'] == '15s' else (180 if spec['granularity'] == '30s' else 600)
        name = f"D2_GA_{spec['id']}"
        s = MarketablePullback(
            name,
            impulse_pts=spec['impulse_pts'],
            impulse_bars=spec['impulse_bars'],
            pull_pct=spec['pull_pct'],
            stop_pts=spec['stop_pts'],
            target_pts=spec['target_pts'],
            invert=spec['invert'],
            session_start=spec.get('ses_start'),
            session_end=spec.get('ses_end'),
            max_hold=max_hold,
        )
        attach_r7_executor(s)
        if spec['granularity'] == '15s':
            strats_15s.append(s)
        elif spec['granularity'] == '30s':
            strats_30s.append(s)
        else:
            strats_1m.append(s)

    all_strats = strats_1m + strats_15s + strats_30s
    print(f"[post] Re-testing {len(all_strats)} GA survivors on {args.max_days}d",
          file=sys.stderr)

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = BarBuilder(granularity_secs=15, max_history=200)
    bb_30s = BarBuilder(granularity_secs=30, max_history=200)

    day_counter = -1
    last_day_key = None
    max_day_counter = -1 + args.max_days
    n_lines = 0
    t0 = time.time()

    with open(PATH, "rb") as f:
        f.seek(args.offset)
        f.readline()
        for raw in f:
            n_lines += 1
            try:
                line = raw.decode("ascii", errors="ignore")
                stamp_str, vals = line.split(";", 1)
                vp = vals.split(";")
                if len(vp) < 3:
                    continue
                last = float(vp[0])
                bid = float(vp[1])
                ask = float(vp[2])
                p = stamp_str.split()
                if len(p) < 2:
                    continue
                yy = int(p[0][:4]); mm = int(p[0][4:6]); dd = int(p[0][6:8])
                hh = int(p[1][:2]); mn = int(p[1][2:4]); ss = int(p[1][4:6])
                ns = int(p[2]) if len(p) > 2 else 0
            except Exception:
                continue

            day_key = (yy, mm, dd)
            if day_key != last_day_key:
                day_counter += 1
                last_day_key = day_key
                if day_counter >= max_day_counter:
                    break

            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7
            MARKET.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    for s in strats_1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            if strats_15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in strats_15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            if strats_30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in strats_30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)

            for s in all_strats:
                r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

            if n_lines % 1_000_000 == 0:
                print(f"  [post] {n_lines/1e6:.1f}M ticks elapsed={(time.time()-t0)/60:.1f}m day={day_counter}",
                      file=sys.stderr, flush=True)

    total_days = day_counter + 1
    print(f"\n[post] DONE in {(time.time()-t0)/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    # Report each strategy under both fee models + NQ
    rows_191 = [_r10.report_strategy(s, total_days, FEE_FULL_RT) for s in all_strats]
    rows_074 = [_r10.report_strategy(s, total_days, FEE_PROP_RT) for s in all_strats]
    rows_nq_191 = [_r10.report_strategy(s, total_days, FEE_FULL_RT, NQ_PER_PT) for s in all_strats]
    rows_nq_074 = [_r10.report_strategy(s, total_days, FEE_PROP_RT, NQ_PER_PT) for s in all_strats]

    # Append to round10_results.md
    md_path = "/home/user/HFTBot/research/round10_results.md"
    rows_191.sort(key=lambda r: -r['per_day'])
    rows_074_by_name = {r['name']: r for r in rows_074}
    rows_nq_191_by_name = {r['name']: r for r in rows_nq_191}
    rows_nq_074_by_name = {r['name']: r for r in rows_nq_074}

    L = []
    L.append("\n\n## Section 8 — POST-HOC: GA survivors re-tested on full 60d\n\n")
    L.append(f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n")
    L.append("These strategies were evolved by the GA on a 7-day window and "
             "then re-tested under bot-faithful execution on the full 60d "
             "window with $1.91 and $0.74 fees, MNQ and NQ point values.\n\n")
    L.append("| Strategy | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ 191 | $/d NQ 074 | DD 191 | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in rows_191:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq = rows_nq_191_by_name[n]
        rnq74 = rows_nq_074_by_name[n]
        L.append(f"| {n} | {r['n']:,} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${rnq['per_day']:,.0f} | "
                 f"${rnq74['per_day']:,.0f} | ${r['max_dd']:,.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    def is_pass(r):
        return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000)
    pass_191 = [r for r in rows_191 if is_pass(r)]
    pass_074 = [r for r in rows_074 if is_pass(r)]
    pass_nq_191 = [r for r in rows_nq_191 if is_pass(r)]
    pass_nq_074 = [r for r in rows_nq_074 if is_pass(r)]
    L.append(f"\nGA passers (60d): MNQ$1.91={len(pass_191)} MNQ$0.74={len(pass_074)} "
             f"NQ$1.91={len(pass_nq_191)} NQ$0.74={len(pass_nq_074)}\n")

    with open(md_path, "a") as mf:
        mf.write("".join(L))
    print(f"[post] appended GA section to {md_path}", file=sys.stderr)

    # Print summary
    print("\n[post] GA survivor results:")
    for r in rows_191[:15]:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq74 = rows_nq_074_by_name[n]
        print(f"  {n:>50s} n={r['n']:>5d} tpd={r['trades_per_day']:>5.1f} "
              f"wr={r['wr']*100:>4.1f}% $/d={r['per_day']:>+5.0f} "
              f"prop=${r74['per_day']:>+5.0f} NQ-prop=${rnq74['per_day']:>+5.0f}")


if __name__ == "__main__":
    main()

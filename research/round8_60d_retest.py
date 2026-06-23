"""Round 8 60-day re-test: take CANDIDATE strategy names from CLI and
run them under the same bot-faithful execution model on the FULL 60-day
window (offset 7_820_974_790). Writes round8_60d_results.md.

Usage:
  python3 round8_60d_retest.py --candidates name1,name2,name3
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from research import round7_search as r7  # noqa
from research import round8_search as r8  # noqa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True,
                    help="Comma-separated strategy names to re-test")
    ap.add_argument("--offset", type=int, default=7_820_974_790)
    ap.add_argument("--max-days", type=int, default=60)
    ap.add_argument("--out", default="/home/user/HFTBot/research/round8_60d_results.md")
    args = ap.parse_args()

    wanted = set(args.candidates.split(","))

    v1m, v15s, v30s, vtick, aux, _ = r8.build_variants_round8()
    all_strats = v1m + v15s + v30s + vtick
    keep_set = set(s.name for s in all_strats if s.name in wanted)
    missing = wanted - keep_set
    if missing:
        print(f"[60d] MISSING from build: {sorted(missing)}", file=sys.stderr)
    v1m = [s for s in v1m if s.name in keep_set]
    v15s = [s for s in v15s if s.name in keep_set]
    v30s = [s for s in v30s if s.name in keep_set]
    vtick = [s for s in vtick if s.name in keep_set]
    # Keep aux around so gates can use MARKET
    all_strats = v1m + v15s + v30s + vtick
    all_runnable = all_strats + aux
    print(f"[60d] Re-testing {len(all_strats)} candidates + {len(aux)} aux on 60d", file=sys.stderr)
    if not all_strats:
        return

    bb_1m = r7.BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = r7.BarBuilder(granularity_secs=15, max_history=200)
    bb_30s = r7.BarBuilder(granularity_secs=30, max_history=200)

    day_counter = -1
    last_day_key = None
    n_lines = 0
    t_start = time.time()

    with open(r7.PATH, "rb") as f:
        f.seek(args.offset)
        f.readline()
        for raw in f:
            n_lines += 1
            if n_lines % 1_000_000 == 0:
                elapsed = time.time() - t_start
                print(f"  [60d] {n_lines/1e6:.1f}M ticks elapsed={elapsed/60:.1f}m day={day_counter}",
                      file=sys.stderr, flush=True)
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
                if day_counter >= args.max_days:
                    break
            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

            r8.MARKET.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    r8.MARKET.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
                    for s in aux:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            if v15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            if v30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)
            for s in vtick:
                s.feed_tick(ts, last)
            for s in all_runnable:
                r7.r7_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    total_days = day_counter + 1
    rows = [r7._report(s, total_days) for s in all_strats]
    rows.sort(key=lambda r: -r['per_day'])

    full_pass = [r for r in rows if r['trades_per_day'] >= 300
                 and r['wr'] >= 0.45 and r['per_day'] >= 1000
                 and r['max_dd'] <= 5000]
    with open(args.out, "w") as f:
        f.write(f"# Round 8 60-DAY re-test\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Period: {total_days} day buckets, offset {args.offset:,}\n\n")
        f.write(f"## FULL_PASS on 60d: {len(full_pass)}\n\n")
        for r in full_pass:
            f.write(f"- **{r['name']}** -- {r['n']:,} trades ({r['trades_per_day']:.1f}/day), "
                    f"WR={r['wr']*100:.1f}%, ${r['per_day']:,.0f}/day, maxDD=${r['max_dd']:,.0f}\n")
        f.write("\n## All candidates\n\n")
        f.write("| Strategy | Trades | Tr/day | WR% | $/day | $/tr | maxDD | Sharpe |\n")
        f.write("|----------|-------:|-------:|----:|------:|-----:|------:|-------:|\n")
        for r in rows:
            f.write(f"| {r['name']} | {r['n']:,} | {r['trades_per_day']:.1f} | "
                    f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                    f"${r['per_trade']:.2f} | ${r['max_dd']:,.0f} | "
                    f"{r['sharpe']:.2f} |\n")
    print(f"[60d] wrote {args.out}", file=sys.stderr)
    print(f"FULL_PASS on 60d: {len(full_pass)}")


if __name__ == "__main__":
    main()

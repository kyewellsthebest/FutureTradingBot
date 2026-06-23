"""Run JUST the CANON variant using the round4 harness to verify the fix.

Compares directly to sim_on_60d.py / sim_honest_battery.py.

Differences accepted vs sim_on_60d.py:
  - Uses $1.91/RT (commission + exchange fees), not $0.74-only.
    That subtracts ~$1.17 per trade.
  - Otherwise the trigger logic and bar building must match.
"""
import math, os, sys, time
from collections import deque

sys.path.insert(0, "/home/user/HFTBot/research")
from round4_search import (
    PullbackStrategy, BarBuilder, TOTAL_RT_COST, COMM_RT, EXCH_FEES_RT,
    MNQ_PER_PT, ENTRY_SLIP, STOP_SLIP, START_OFFSET, PATH,
)

# Single canonical variant: same as sim_honest_battery INV_236_s10t20_cd10
canon = PullbackStrategy(
    "CANON_INV_236_s10t20", impulse_pts=5.0, impulse_bars=4,
    pull_pct=0.236, stop_pts=10, target_pts=20, invert=True, cooldown_s=10,
)

bb_1m = BarBuilder(granularity_secs=60, max_history=300)

day_counter = -1
last_day_key = None
n_lines = 0
t_start = time.time()
last_progress_t = t_start

print(f"[verify] Streaming from offset {START_OFFSET:,}", file=sys.stderr)
with open(PATH, "rb") as f:
    f.seek(START_OFFSET)
    f.readline()
    for raw in f:
        n_lines += 1
        if n_lines % 2_000_000 == 0:
            now = time.time()
            print(f"  [verify] {n_lines/1e6:.1f}M ticks "
                  f"elapsed={(now - t_start)/60:.1f}m "
                  f"trades={canon.n_trades}",
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
        ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

        if bb_1m.on_tick(ts, last):
            closed = bb_1m.closed_bar()
            if closed is not None:
                o, h, l, c = closed
                canon.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)

        canon.on_tick(ts, bid, ask, day_counter, hh, mn)

elapsed = time.time() - t_start
total_days = day_counter + 1
print(f"\n[verify] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
      f"{total_days} days", file=sys.stderr)

r = canon.report(total_days)
print(f"\nCANON_INV_236_s10t20 (round4 harness, $1.91/RT):")
print(f"  trades       : {r['n']}")
print(f"  trades/day   : {r['trades_per_day']:.1f}")
print(f"  win rate     : {r['wr']*100:.1f}%")
print(f"  net P&L      : ${r['net']:+,.2f}")
print(f"  $/day        : ${r['per_day']:+,.2f}")
print(f"  per-trade    : ${r['per_trade']:+,.3f}")
print(f"  max DD       : ${r['max_dd']:,.2f}")
print(f"  worst day    : ${r['worst']:+,.2f}")
print(f"  best day     : ${r['best']:+,.2f}")
print(f"  days         : {r['n_days']} ({r['pos_d']} pos, {r['neg_d']} neg)")
print()
print("Expected from sim_honest_battery (NOTE: uses $0.74/RT not $1.91):")
print("  trades ~ a few hundred to ~1500, WR > 45%, $/day > $1000")
print(f"  If you see $0.74/RT-equivalent here, add back ${EXCH_FEES_RT}×n_trades=")
print(f"    ${EXCH_FEES_RT * r['n']:.2f} for direct apples-to-apples sim compare.")

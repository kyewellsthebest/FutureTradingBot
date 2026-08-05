"""HF passive-scalp grid: liquidity provision against second-scale overshoots.

Stage 1: signal sweep at fixed execution (off=2t, window=10s, tgt=3t, stop=8t).
Stage 2: execution sweep on the best signals.
All selection on IS (Sep 2023 - Feb 2025); OOS reported for chosen configs only
at the end. Costs: model A = flat $4.40/RT (user spec); model B = $1.40
commission + $1.50 per market leg.
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H
from tick_features import load_sec
from hf_sim import scalp, scalp_stats, fmt, TICK

IS_END = "2025-03-01"

df = load_sec(columns=["n_trades", "ofi10", "burst"])
arrays = H.get_arrays(df)
c = df["close"]
act = (df["n_trades"].rolling(30).sum() > 150)
rth = df["rth"]
hh = df["hhmm"]
pm = (hh >= 1330) & (hh < 1555)
base = act & rth & (hh < 1555)

d5 = (c - c.shift(5)) / TICK
d15 = (c - c.shift(15)) / TICK

SIGNALS = {
    "d5-6_L":  ((d5 <= -6) & base, +1),
    "d5-8_L":  ((d5 <= -8) & base, +1),
    "d5-12_L": ((d5 <= -12) & base, +1),
    "d5+6_S":  ((d5 >= 6) & base, -1),
    "d5+8_S":  ((d5 >= 8) & base, -1),
    "d5+12_S": ((d5 >= 12) & base, -1),
    "d15-16_L": ((d15 <= -16) & base, +1),
    "d15+16_S": ((d15 >= 16) & base, -1),
    "pm_d15-8_L": ((d15 <= -8) & act & pm, +1),
    "pm_d15+8_S": ((d15 >= 8) & act & pm, -1),
}

print("=== STAGE 1: signal sweep (off=2, win=10, tgt=3, stop=8, hold=120) — IS only ===")
stage1 = {}
for name, (sig, d) in SIGNALS.items():
    t = scalp(df, arrays, sig, d, entry_off=2, entry_window=10,
              target=3, stop=8, max_hold=120)
    s = scalp_stats(t, end=IS_END)
    stage1[name] = s
    print(fmt(name, s))

best = sorted([k for k, v in stage1.items() if v.get("n", 0) > 500],
              key=lambda k: -stage1[k].get("wkA", -9e9))[:4]
print(f"\nbest by $wkA: {best}")

print("\n=== STAGE 2: execution sweep on best signals — IS only ===")
grid_results = {}
for name in best:
    sig, d = SIGNALS[name]
    for off in (1, 2, 3):
        for tgt in (2, 3, 4, 6):
            for stp in (6, 8, 12):
                for hold in (60, 120):
                    t = scalp(df, arrays, sig, d, entry_off=off, entry_window=10,
                              target=tgt, stop=stp, max_hold=hold)
                    s = scalp_stats(t, end=IS_END)
                    key = f"{name}_o{off}t{tgt}s{stp}h{hold}"
                    grid_results[key] = s

rows = [(v.get("wkA", -9e9), k, v) for k, v in grid_results.items()
        if v.get("n", 0) > 1000 and v.get("trades_wk", 0) >= 60]
rows.sort(reverse=True)
print("top 20 configs by IS $wkA (per-signal; portfolio combines sides):")
for w, k, v in rows[:20]:
    print(fmt(k, v))

json.dump({k: v for k, v in grid_results.items()},
          open(H.CACHE / "hf_grid_results.json", "w"), default=str)
print("saved grid")

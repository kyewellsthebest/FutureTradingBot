"""Deep, skeptical validation of the search winners before any live use.

Checks:
 1. Unbiased selection: rank by TRAIN-only, report TEST (true OOS).
 2. Month-by-month $/day (regime consistency).
 3. Profit concentration: share of net from top-10 trades.
 4. Slip stress 0.25 -> 1.0 pt on the (tighter) 5pt stop.
 5. Beyond-grid-edge probe: does the optimum keep running, or plateau?
"""
from __future__ import annotations
import numpy as np, pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               simulate, stats, SimCfg)

FINALISTS = [
    ("S2 winner i2_w3_p.118_s5_t44_cd30", dict(IMPULSE_PTS=2.0, IMPULSE_WINDOW_BARS=3, PULLBACK_PCT=0.118, STOP_PTS=5.0, TARGET_PTS=44.0, INVERT=True), 30),
    ("conservative i3_w4_p.236_s6_t30_cd60", dict(IMPULSE_PTS=3.0, IMPULSE_WINDOW_BARS=4, PULLBACK_PCT=0.236, STOP_PTS=6.0, TARGET_PTS=30.0, INVERT=True), 60),
    ("S1 winner i3_w3_p.236_s6_t30_cd60", dict(IMPULSE_PTS=3.0, IMPULSE_WINDOW_BARS=3, PULLBACK_PCT=0.236, STOP_PTS=6.0, TARGET_PTS=30.0, INVERT=True), 60),
    ("hi-WR i2_w4_p.118_s7_t24_cd30", dict(IMPULSE_PTS=2.0, IMPULSE_WINDOW_BARS=4, PULLBACK_PCT=0.118, STOP_PTS=7.0, TARGET_PTS=24.0, INVERT=True), 30),
]
# beyond-grid-edge probe (does it keep improving past the edge?)
BEYOND = [
    ("edge++ p.06_s4_t50", dict(IMPULSE_PTS=2.0, IMPULSE_WINDOW_BARS=3, PULLBACK_PCT=0.06, STOP_PTS=4.0, TARGET_PTS=50.0, INVERT=True), 30),
    ("edge++ p.118_s4_t60", dict(IMPULSE_PTS=2.0, IMPULSE_WINDOW_BARS=3, PULLBACK_PCT=0.118, STOP_PTS=4.0, TARGET_PTS=60.0, INVERT=True), 30),
    ("edge++ i1.5_p.118_s5_t44", dict(IMPULSE_PTS=1.5, IMPULSE_WINDOW_BARS=3, PULLBACK_PCT=0.118, STOP_PTS=5.0, TARGET_PTS=44.0, INVERT=True), 30),
]

def deep(ticks, bars, label, params, cd, split_ns):
    setups = precompute_setups(bars, params)
    rows = {}
    for slip in (0.25, 0.5, 0.75, 1.0):
        df = simulate(ticks, setups, SimCfg(cooldown_s=cd, stop_slip=slip))
        rows[slip] = df
    df = rows[0.25]
    s = stats(df)
    tr = df[df.fire_ts < split_ns]; te = df[df.fire_ts >= split_ns]
    s_tr, s_te = stats(tr), stats(te)
    # monthly
    dfm = df.copy(); dfm["ym"] = dfm["dt"].dt.to_period("M")
    monthly = dfm.groupby("ym").apply(
        lambda g: round(g.pnl.sum()/max(1,g.dt.dt.normalize().nunique()),0), include_groups=False)
    # profit concentration
    top10 = df.nlargest(10, "pnl").pnl.sum()
    conc = round(100*top10/df.pnl.sum(),1) if df.pnl.sum()>0 else None
    # exit mix
    rc = df.reason.value_counts(normalize=True).mul(100).round(1).to_dict()
    print(f"\n### {label}")
    print(f"  full: {s['n']} tr, {s['tr_per_day']}/d, WR {s['wr']}%, +${s['per_day']}/d, "
          f"$/tr {s['per_trade']}, maxDD ${s['maxDD']}")
    print(f"  TRAIN +${s_tr.get('per_day')}/d  ->  TEST(OOS) +${s_te.get('per_day')}/d (WR {s_te.get('wr')}%)")
    print(f"  exit mix: tgt {rc.get('target')}% stop {rc.get('stop')}% timeout {rc.get('timeout')}%")
    print(f"  slip 0.25/0.5/0.75/1.0 -> " +
          " / ".join(f"${stats(rows[x])['per_day']}" for x in (0.25,0.5,0.75,1.0)) + " per day")
    print(f"  top-10 trades = {conc}% of net  (lower = less concentrated/luck)")
    print(f"  monthly $/day: {dict(monthly)}")
    return s

def main():
    ticks = load_ticks(); bars = build_1m_bars(ticks[0], ticks[1])
    split_ns = ticks[0][0] + int(0.70*(ticks[0][-1]-ticks[0][0]))
    print("="*70 + "\nFINALISTS\n" + "="*70)
    for label, p, cd in FINALISTS:
        deep(ticks, bars, label, p, cd, split_ns)
    print("\n" + "="*70 + "\nBEYOND-GRID-EDGE PROBE (overfit check)\n" + "="*70)
    for label, p, cd in BEYOND:
        deep(ticks, bars, label, p, cd, split_ns)

if __name__ == "__main__":
    main()

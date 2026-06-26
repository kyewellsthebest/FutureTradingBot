"""Realistic-execution strategy search.

Unlike the original search (idealized fills, 0.25pt slip), this charges the
execution costs MEASURED from the live bundles:
  - entry slip 0.75pt (marketable fill cost / spillover)
  - stop slip 1.3pt (stop-market fill, live avg loss implied this)
and tests an HTF trend filter (regime defense: only fade with the trend).

Ranks by WORST-MONTH $/day (regime robustness) so the winner survives bad
months, not just the average. Flags configs that still meet the user's
minimums ($1000/day, 200-300 tr/day on 1 MNQ) under realistic costs.
"""
from __future__ import annotations
import itertools, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               simulate, stats, SimCfg)

# realistic execution costs (from live bundles)
ENTRY_SLIP = 0.75
STOP_SLIP = 1.3

_TICKS=None; _BARS=None
def _init():
    global _TICKS,_BARS
    _TICKS=load_ticks(); _BARS=build_1m_bars(_TICKS[0],_TICKS[1])

def _monthly(df):
    if df.empty: return {}, 0
    m=df.copy(); m["ym"]=m["dt"].dt.to_period("M")
    g=m.groupby("ym").apply(lambda x: x.pnl.sum()/max(1,x.dt.dt.normalize().nunique()), include_groups=False)
    return {str(k):round(v,0) for k,v in g.items()}, round(float(g.min()),0)

def _eval(t):
    imp,W,pull,stop,tgt,htf=t
    p=dict(IMPULSE_PTS=imp,IMPULSE_WINDOW_BARS=W,PULLBACK_PCT=pull,STOP_PTS=stop,
           TARGET_PTS=tgt,INVERT=True,HTF_LOOKBACK_BARS=htf)
    su=precompute_setups(_BARS,p)
    if su is None or len(su["det_ts"])==0: return None
    df=simulate(_TICKS,su,SimCfg(entry_slip=ENTRY_SLIP,stop_slip=STOP_SLIP))
    if df.empty or len(df)<100: return None
    s=stats(df); months,worst=_monthly(df)
    return {"name":f"i{imp}_w{W}_p{pull}_s{stop}_t{tgt}_htf{htf}",
            "imp":imp,"W":W,"pull":pull,"stop":stop,"tgt":tgt,"htf":htf,
            "n":s["n"],"tr_day":s["tr_per_day"],"wr":s["wr"],"to%":s["to%"],
            "net":s["net"],"per_day":s["per_day"],"per_trade":s["per_trade"],
            "maxDD":s["maxDD"],"worst_month":worst,"months":months}

def build_grid():
    return list(itertools.product(
        [2.0,3.0,5.0],        # impulse
        [3,4],                # window
        [0.118,0.236,0.382,0.5,0.618],  # pullback
        [5.0,8.0,10.0,14.0],  # stop
        [24.0,40.0,60.0],     # target
        [0,30,60]))           # htf lookback (0=off)

def main():
    t0=time.time(); grid=build_grid()
    print(f"realistic grid: {len(grid)} configs (entry_slip={ENTRY_SLIP}, stop_slip={STOP_SLIP})",flush=True)
    _init()
    res=[]
    with ProcessPoolExecutor(max_workers=4,initializer=_init) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%40==0: print(f"  {i+1}/{len(grid)} {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res)
    df.to_csv("research/tick_search_realistic_results.csv",index=False)
    pd.set_option("display.width",240,"display.max_columns",40)
    cols=["name","n","tr_day","wr","per_day","per_trade","maxDD","worst_month"]
    print(f"\nDONE {time.time()-t0:.0f}s  ({len(df)} configs)")
    print("\n=== TOP 15 by WORST-MONTH $/day (regime-robust) ===")
    print(df.sort_values("worst_month",ascending=False).head(15)[cols].to_string(index=False))
    print("\n=== TOP 10 by AVG $/day ===")
    print(df.sort_values("per_day",ascending=False).head(10)[cols].to_string(index=False))
    # minimums check
    mins=df[(df.per_day>=1000)&(df.tr_day>=200)]
    print(f"\n=== meet MINIMUMS ($1000/day & 200+ tr/day, realistic): {len(mins)} ===")
    if len(mins): print(mins.sort_values("worst_month",ascending=False).head(10)[cols].to_string(index=False))
    pos=df[df.worst_month>0]
    print(f"\nconfigs profitable EVERY month: {len(pos)}")
    if len(pos):
        best=pos.sort_values("worst_month",ascending=False).iloc[0]
        print("most-robust config months:", best["months"])

if __name__=="__main__":
    main()

"""Rigorous tick-only robustness search — the 'use the 3 months properly' run.

Goal: surface only strategy configs that are CREDIBLE, not curve-fit, using
solely the real NQ tick data we have (Dec 2025 - Feb 2026).

Every config is charged REAL execution costs (entry+stop slip from the live
bundles) and must pass ALL of these gates:

  G1 WALK-FORWARD CONSISTENCY: positive $/day in every chronological
     time-block (data split into N blocks in time order). Kills configs
     that only worked in one lucky stretch.
  G2 REGIME ROBUSTNESS: acceptable on TREND days (not just saved by chop).
     This is the gate that would have rejected the June-killed strategy.
  G3 PLATEAU: the config's grid neighbours (±1 step in each param) must
     also be profitable. A lone spike = overfit; a plateau = real edge.
  G4 SAMPLE: >= 150 trades and a positive daily Sharpe.

Trend-filter (HTF_LOOKBACK_BARS) is a searched dimension, so the data
decides whether sitting out trends helps.
"""
from __future__ import annotations
import itertools, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               simulate, SimCfg, NS)

ENTRY_SLIP = 0.75      # realistic marketable entry cost (live-measured)
STOP_SLIP = 1.3        # realistic stop-market slip (live avg-loss implied)
N_BLOCKS = 6           # walk-forward time blocks
TREND_EFF = 0.30       # RTH efficiency >= this = trend day

_TICKS=None; _BARS=None; _REGIME=None; _BLOCKS=None

def _label_regimes(bars):
    """Per calendar day: 'trend' if RTH 15-min efficiency>=TREND_EFF else 'chop'."""
    b=bars.copy(); b["h"]=b.index.hour+b.index.minute/60
    rth=b[(b.h>=14.5)&(b.h<21.0)]
    r15=rth.resample("15min").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    r15["day"]=r15.index.normalize()
    reg={}
    for day,g in r15.groupby("day"):
        if len(g)<10: continue
        net=abs(g["close"].iloc[-1]-g["open"].iloc[0]); path=g["close"].diff().abs().sum()
        eff=net/path if path>0 else 0
        reg[pd.Timestamp(day).date()]="trend" if eff>=TREND_EFF else "chop"
    return reg

def _init():
    global _TICKS,_BARS,_REGIME,_BLOCKS
    _TICKS=load_ticks(); _BARS=build_1m_bars(_TICKS[0],_TICKS[1])
    _REGIME=_label_regimes(_BARS)
    # chronological block boundaries by tick time
    t0,t1=_TICKS[0][0],_TICKS[0][-1]
    _BLOCKS=[t0+int((t1-t0)*k/N_BLOCKS) for k in range(N_BLOCKS+1)]

def _per_day(df):
    g=df.groupby(df["dt"].dt.normalize())["pnl"].sum()
    return g

def _eval(t):
    imp,W,pull,stop,tgt,htf=t
    p=dict(IMPULSE_PTS=imp,IMPULSE_WINDOW_BARS=W,PULLBACK_PCT=pull,STOP_PTS=stop,
           TARGET_PTS=tgt,INVERT=True,HTF_LOOKBACK_BARS=htf)
    su=precompute_setups(_BARS,p)
    if su is None or len(su["det_ts"])==0: return None
    df=simulate(_TICKS,su,SimCfg(entry_slip=ENTRY_SLIP,stop_slip=STOP_SLIP))
    if df.empty or len(df)<150: return None
    days=df["dt"].dt.normalize().nunique()
    perday=df["pnl"].sum()/max(1,days)
    # walk-forward blocks
    block_pd=[]
    for k in range(N_BLOCKS):
        seg=df[(df["fire_ts"]>=_BLOCKS[k])&(df["fire_ts"]<_BLOCKS[k+1])]
        d=seg["dt"].dt.normalize().nunique() if not seg.empty else 0
        block_pd.append(round(seg["pnl"].sum()/d,1) if d else 0.0)
    worst_block=min(block_pd)
    # regime split
    reg=df["dt"].dt.normalize().map(lambda x:_REGIME.get(pd.Timestamp(x).date(),"chop"))
    tr=df[reg.values=="trend"]; ch=df[reg.values=="chop"]
    def pd_(x):
        dd=x["dt"].dt.normalize().nunique() if not x.empty else 0
        return round(x["pnl"].sum()/dd,1) if dd else 0.0
    trend_pd=pd_(tr); chop_pd=pd_(ch)
    # daily sharpe
    dp=_per_day(df)
    sharpe=round(float(dp.mean()/dp.std()*np.sqrt(252)),2) if dp.std()>0 else 0.0
    # maxDD
    eq=df["pnl"].cumsum().to_numpy(); dd=float((np.maximum.accumulate(eq)-eq).max())
    n=len(df)
    return {"name":f"i{imp}_w{W}_p{pull}_s{stop}_t{tgt}_htf{htf}",
            "imp":imp,"W":W,"pull":pull,"stop":stop,"tgt":tgt,"htf":htf,
            "n":n,"tr_day":round(n/days,1),"per_day":round(perday,1),"maxDD":round(dd,0),
            "sharpe":sharpe,"worst_block":worst_block,"trend_pd":trend_pd,"chop_pd":chop_pd,
            "blocks":block_pd}

GRID=dict(imp=[2.0,3.0,4.0],W=[3,4],pull=[0.118,0.236,0.382,0.5],
          stop=[5.0,8.0,12.0],tgt=[20.0,30.0,44.0],htf=[0,20,40])

def build_grid():
    return list(itertools.product(GRID["imp"],GRID["W"],GRID["pull"],GRID["stop"],GRID["tgt"],GRID["htf"]))

def _neighbors(row):
    """grid neighbours: +-1 step in each axis."""
    out=[]
    for ax in ["imp","W","pull","stop","tgt","htf"]:
        vals=GRID[ax]; i=vals.index(row[ax])
        for j in (i-1,i+1):
            if 0<=j<len(vals):
                nb=dict(row); nb[ax]=vals[j]; out.append(nb)
    return out

def main():
    t0=time.time(); grid=build_grid()
    print(f"robust grid: {len(grid)} configs | slip entry{ENTRY_SLIP}/stop{STOP_SLIP} | {N_BLOCKS} blocks | trend_eff>={TREND_EFF}",flush=True)
    _init()
    tr_days=sum(1 for v in _REGIME.values() if v=="trend"); ch_days=sum(1 for v in _REGIME.values() if v=="chop")
    print(f"regime days: trend {tr_days}, chop {ch_days}",flush=True)
    res=[]
    with ProcessPoolExecutor(max_workers=4,initializer=_init) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%80==0: print(f"  {i+1}/{len(grid)} {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/tick_robust_results.csv",index=False)
    by={r["name"]:r for r in res}
    # plateau score: fraction of neighbours with per_day>0
    for r in res:
        nbs=_neighbors(r); found=[by.get(f"i{n['imp']}_w{n['W']}_p{n['pull']}_s{n['stop']}_t{n['tgt']}_htf{n['htf']}") for n in nbs]
        found=[x for x in found if x]
        r["plateau"]=round(sum(1 for x in found if x["per_day"]>0)/len(found),2) if found else 0.0
    df=pd.DataFrame(res)
    pd.set_option("display.width",260,"display.max_columns",40)
    cols=["name","n","tr_day","per_day","worst_block","trend_pd","chop_pd","sharpe","maxDD","plateau"]
    # GATES
    survivors=df[(df.worst_block>0)&(df.trend_pd>-50)&(df.sharpe>0.5)&(df.plateau>=0.7)&(df.n>=150)]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} evaluated | {len(survivors)} pass ALL gates")
    print("\n=== SURVIVORS (walk-forward+ +trend-ok +plateau>=0.7 +sharpe>0.5), top 15 by worst_block ===")
    print(survivors.sort_values("worst_block",ascending=False).head(15)[cols].to_string(index=False) if len(survivors) else "  NONE")
    print("\n=== for reference: top 10 by worst_block (pre-gate) ===")
    print(df.sort_values("worst_block",ascending=False).head(10)[cols].to_string(index=False))

if __name__=="__main__":
    main()

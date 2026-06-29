"""Avenue F: SWING / POSITION TREND-FOLLOWING (multi-day holds).

Every prior grid capped holds at <=6h -- pure intraday. Trend-following is
the one price-based class with documented long-run positive expectancy, and
it holds for DAYS, so the $2.50/trade cost is negligible. Tested here:
  * Donchian channel breakout (enter on N-bar high/low break)
  * Exit on opposite M-bar channel, ATR trailing, or time
  * Higher timeframes resampled from the 1-min bars (60m / 240m / daily)
Realistic per-trade cost (commission + spread + slip), per-quarter walk-forward.

Run: python -m research.avenue_swing
"""
from __future__ import annotations
import time, itertools
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import _init, PT, COMM

SPREAD=0.25; SLIP=0.5   # entry/exit friction in pts (round turn applied once)

def resample(bars, rule):
    o=bars["open"].resample(rule).first(); h=bars["high"].resample(rule).max()
    l=bars["low"].resample(rule).min(); c=bars["close"].resample(rule).last()
    df=pd.DataFrame({"open":o,"high":h,"low":l,"close":c}).dropna()
    return df

def donchian_trades(df, N, M, longonly, atr_trail):
    """Simulate Donchian breakout on bar closes. Returns list of (exit_ts,pnl_pts)."""
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    n=len(c)
    hi_n=pd.Series(h).rolling(N).max().shift(1).to_numpy()
    lo_n=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    hi_m=pd.Series(h).rolling(M).max().shift(1).to_numpy()
    lo_m=pd.Series(l).rolling(M).min().shift(1).to_numpy()
    tr=np.maximum(h-l,np.abs(c-np.concatenate([[c[0]],c[:-1]])))
    atr=pd.Series(tr).rolling(20).mean().to_numpy()
    pos=0; entry=0.0; peak=0.0; trades=[]
    for i in range(max(N,M,20),n):
        if pos==0:
            if c[i]>hi_n[i]:
                pos=1; entry=c[i]; peak=c[i]
            elif (not longonly) and c[i]<lo_n[i]:
                pos=-1; entry=c[i]; peak=c[i]
        elif pos==1:
            peak=max(peak,c[i])
            exit_=(c[i]<lo_m[i]) or (atr_trail>0 and c[i]<peak-atr_trail*atr[i])
            if exit_:
                pnl=(c[i]-entry)-(SPREAD+SLIP); trades.append((ts[i],pnl)); pos=0
        elif pos==-1:
            peak=min(peak,c[i])
            exit_=(c[i]>hi_m[i]) or (atr_trail>0 and c[i]>peak+atr_trail*atr[i])
            if exit_:
                pnl=(entry-c[i])-(SPREAD+SLIP); trades.append((ts[i],pnl)); pos=0
    return trades

def metrics(trades):
    if len(trades)<30: return None
    ts=np.array([t[0] for t in trades]); pts=np.array([t[1] for t in trades])
    pnl=pts*PT-COMM
    dt=pd.to_datetime(ts); span_days=max(1,(dt.max()-dt.min()).days)
    q=pd.Series(dt).dt.to_period("Q").astype(str)
    fold=pd.DataFrame({"q":q.values,"pnl":pnl})
    fq=fold.groupby("q").pnl.sum()
    # per-day = total pnl / calendar days in span (trades are sparse)
    per_day=pnl.sum()/span_days
    # daily sharpe approximation from per-trade dispersion annualized by trades/yr
    tr_yr=len(trades)/(span_days/365)
    sharpe=float(pnl.mean()/pnl.std()*np.sqrt(tr_yr)) if pnl.std()>0 else 0
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max())
    return {"n":len(trades),"tr_yr":round(tr_yr,1),"wr":round(100*(pnl>0).mean(),1),
            "per_day":round(per_day,1),"per_trade":round(pnl.mean(),1),"total":round(pnl.sum(),0),
            "maxDD":round(dd,0),"sharpe":round(sharpe,2),"worst_q":round(float(fq.min()),0),
            "n_folds":len(fq),"pos_folds":int((fq>0).sum())}

def main():
    t0=time.time(); _init(); bars=Z._BARS
    print(f"bars {len(bars):,}  {time.time()-t0:.0f}s",flush=True)
    res=[]
    for rule in ["60min","240min","1D"]:
        df=resample(bars,rule)
        for N in (10,20,40,55):
            for M in (5,10,20):
                for lo in (True,False):
                    for atr_trail in (0,3.0):
                        tr=donchian_trades(df,N,M,lo,atr_trail)
                        m=metrics(tr)
                        if not m: continue
                        m["name"]=f"DON_{rule}_N{N}M{M}_{'L' if lo else 'LS'}_at{atr_trail}"
                        res.append(m)
    df=pd.DataFrame(res); df.to_csv("research/avenue_swing_results.csv",index=False)
    cols=["name","n","tr_yr","wr","per_day","per_trade","total","sharpe","maxDD","worst_q","pos_folds","n_folds"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    print("\n=== TOP 25 by per_day ===")
    print(df.sort_values("per_day",ascending=False).head(25)[cols].to_string(index=False))
    print("\n=== TOP 12 by worst-quarter ===")
    print(df.sort_values("worst_q",ascending=False).head(12)[cols].to_string(index=False))
    robust=df[(df.worst_q>0)&(df.pos_folds==df.n_folds)&(df.sharpe>1)]
    print(f"\n=== profitable EVERY quarter AND sharpe>1: {len(robust)} ===")
    if len(robust): print(robust.sort_values("per_day",ascending=False)[cols].to_string(index=False))

if __name__=="__main__":
    main()

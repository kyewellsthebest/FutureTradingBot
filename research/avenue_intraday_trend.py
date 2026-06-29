"""Avenue G: INTRADAY TREND-CONTINUATION held to the close.

Prior intraday grids used short fixed holds or mean-reversion. This tests the
opposite: catch an intraday breakout IN THE DIRECTION OF THE DAILY TREND and
RIDE IT to the session close (or a trailing stop). NQ trends hard within the
day; this aims for more $/day than the multi-day swing system by trading ~1x
per day but capturing the whole intraday move.

Entries (on 5m/15m bars, RTH only):
  * PDH/PDL break   -- break of prior-day high/low
  * ORB             -- break of first 30/60-min range
  * Donchian-intraday -- break of N-bar intraday high/low
Trend filter: only longs when close > daily SMA(50) (and mirror for shorts),
or no filter. Exit: end-of-day, or ATR trailing, or fixed stop/target.
Realistic costs, per-quarter + per-year walk-forward.

Run: python -m research.avenue_intraday_trend
"""
from __future__ import annotations
import time
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import _init, PT, COMM

SPREAD=0.25; SLIP=0.5
RTH_LO=14.5; RTH_HI=20.92   # ~14:30-20:55 UTC

def prep(bars, rule):
    o=bars["open"].resample(rule).first(); h=bars["high"].resample(rule).max()
    l=bars["low"].resample(rule).min(); c=bars["close"].resample(rule).last()
    df=pd.DataFrame({"open":o,"high":h,"low":l,"close":c}).dropna()
    df["hr"]=df.index.hour+df.index.minute/60
    df["day"]=df.index.normalize()
    # daily trend filter via daily close SMA. CRITICAL: a given day's close is
    # only known at EOD, so today's intraday entries may use ONLY yesterday's
    # signal -> shift(1). Without this it's lookahead.
    dc=bars["close"].resample("1D").last().dropna()
    sma=dc.rolling(50).mean()
    trend=((dc>sma).astype(int)-(dc<sma).astype(int)).shift(1)   # +1 up, -1 down, lagged 1 day
    df["trend"]=df["day"].map(trend).fillna(0).to_numpy()
    # prior day high/low
    dh=bars["high"].resample("1D").max(); dl=bars["low"].resample("1D").min()
    df["pdh"]=df["day"].map(dh.shift(1)); df["pdl"]=df["day"].map(dl.shift(1))
    tr=np.maximum(df["high"]-df["low"],(df["close"]-df["close"].shift()).abs())
    df["atr"]=tr.rolling(20).mean()
    return df

def run_strat(df, entry, N, ob_min, use_trend, exit_mode, stop, tgt, atr_trail):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    trend=df["trend"].to_numpy(); pdh=df["pdh"].to_numpy(); pdl=df["pdl"].to_numpy(); atr=df["atr"].to_numpy()
    don_hi=pd.Series(h).rolling(N).max().shift(1).to_numpy()
    don_lo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    n=len(c); trades=[]
    # opening-range per day
    uniq=np.unique(day); orh={}; orl={}
    if entry=="orb":
        for d in uniq:
            m=(day==d)&(hr>=RTH_LO)&(hr<RTH_LO+ob_min/60)
            if m.any(): orh[d]=h[m].max(); orl[d]=l[m].min()
    i=0; in_rth=(hr>=RTH_LO)&(hr<RTH_HI)
    pos=0; entry_px=0.0; peak=0.0; cur_day=None
    for i in range(max(N,20),n):
        d=day[i]
        # force close at session end
        if pos!=0 and (hr[i]>=RTH_HI or d!=cur_day):
            pnl=(c[i]-entry_px)*pos-(SPREAD+SLIP); trades.append((ts[i],pnl)); pos=0
        if not in_rth[i]: continue
        if pos==0:
            sig=0
            if entry=="pdh":
                if not np.isnan(pdh[i]) and c[i]>pdh[i]: sig=1
                elif not np.isnan(pdl[i]) and c[i]<pdl[i]: sig=-1
            elif entry=="orb":
                oh=orh.get(d); ol=orl.get(d)
                if oh is not None and hr[i]>=RTH_LO+ob_min/60:
                    if c[i]>oh: sig=1
                    elif c[i]<ol: sig=-1
            elif entry=="don":
                if not np.isnan(don_hi[i]) and c[i]>don_hi[i]: sig=1
                elif not np.isnan(don_lo[i]) and c[i]<don_lo[i]: sig=-1
            if sig!=0 and (not use_trend or trend[i]==sig or trend[i]==0):
                if not use_trend or trend[i]==sig:
                    pos=sig; entry_px=c[i]; peak=c[i]; cur_day=d
        else:
            peak=max(peak,c[i]) if pos==1 else min(peak,c[i])
            g=(c[i]-entry_px)*pos
            ex=False
            if stop>0 and g<=-stop: ex=True
            if tgt>0 and g>=tgt: ex=True
            if atr_trail>0 and ((pos==1 and c[i]<peak-atr_trail*atr[i]) or (pos==-1 and c[i]>peak+atr_trail*atr[i])): ex=True
            if ex:
                pnl=g-(SPREAD+SLIP); trades.append((ts[i],pnl)); pos=0
    return trades

def metrics(trades):
    if len(trades)<60: return None
    ts=np.array([t[0] for t in trades]); pts=np.array([t[1] for t in trades]); pnl=pts*PT-COMM
    dt=pd.to_datetime(ts); span=max(1,(dt.max()-dt.min()).days)
    s=pd.Series(pnl,index=dt)
    yr=s.groupby(s.index.year).sum(); q=s.groupby(s.index.to_period("Q")).sum()
    days=pd.Series(dt).dt.normalize().nunique()
    dpd=s.groupby(s.index.normalize()).sum()
    sharpe=float(dpd.mean()/dpd.std()*np.sqrt(252)) if dpd.std()>0 else 0
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max())
    return {"n":len(trades),"tr_day":round(len(trades)/days,2),"wr":round(100*(pnl>0).mean(),1),
            "per_day":round(pnl.sum()/days,1),"per_trade":round(pnl.mean(),1),"total":round(pnl.sum(),0),
            "maxDD":round(dd,0),"sharpe":round(sharpe,2),"worst_q":round(float(q.min()),0),
            "pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),"worst_yr":round(float(yr.min()),0)}

def main():
    t0=time.time(); _init(); bars=Z._BARS
    res=[]
    for rule in ["5min","15min"]:
        df=prep(bars,rule); print(f"{rule}: {len(df):,} bars  {time.time()-t0:.0f}s",flush=True)
        for entry in ["pdh","orb","don"]:
            for use_trend in (True,False):
                for exit_mode in ["eod"]:
                    grids=[]
                    if entry=="don":
                        for N in (12,24,48): grids.append({"N":N,"ob":0})
                    elif entry=="orb":
                        for ob in (30,60): grids.append({"N":0,"ob":ob})
                    else: grids.append({"N":0,"ob":0})
                    for gp in grids:
                        for (stop,tgt,at) in [(0,0,0),(0,0,2.0),(30,0,3.0),(20,60,0),(40,0,0)]:
                            tr=run_strat(df,entry,gp["N"],gp["ob"],use_trend,exit_mode,stop,tgt,at)
                            m=metrics(tr)
                            if not m: continue
                            m["name"]=f"{entry.upper()}_{rule}_N{gp['N']}ob{gp['ob']}_{'T' if use_trend else 'x'}_s{stop}t{tgt}a{at}"
                            res.append(m)
    df=pd.DataFrame(res); df.to_csv("research/avenue_intraday_trend_results.csv",index=False)
    cols=["name","n","tr_day","wr","per_day","per_trade","total","sharpe","maxDD","worst_q","worst_yr","pos_yrs","n_yrs"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    print("\n=== TOP 25 by per_day ===")
    print(df.sort_values("per_day",ascending=False).head(25)[cols].to_string(index=False))
    print("\n=== positive EVERY year, by per_day ===")
    rob=df[(df.pos_yrs==df.n_yrs)&(df.sharpe>0.8)].sort_values("per_day",ascending=False)
    print(f"({len(rob)} configs)")
    print(rob.head(20)[cols].to_string(index=False))

if __name__=="__main__":
    main()

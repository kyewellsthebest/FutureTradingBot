"""DEEP exhaustive strategy search on NQ (1-MNQ, $2/pt).
~13 indicator families x timeframes x sessions x exits, with the REAL
one-position-at-a-time constraint, realistic costs, intrabar stop/target on
high/low, and a per-YEAR walk-forward gate. Designed to run for hours.

Survivors (beat the $74 stack's RTH sleeve, i.e. per_day>46 AND positive
every year AND sharpe>1.3) stream to research/mega_survivors.csv; full
results to research/mega_all.csv.

Run: python -m research.mega_search
"""
from __future__ import annotations
import itertools, time, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

BARS="data/tick/nq_bars_1m_vol.parquet"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5
RTH_LO=14.5; RTH_HI=20.92
SESSIONS={"rth":(14.5,20.92),"morning":(14.5,17.5),"afternoon":(17.5,20.92),"full":(0.0,23.99)}

_TF={}   # tf -> dict of arrays

def _resample(b,rule):
    g=b.resample(rule)
    df=pd.DataFrame({"open":g["open"].first(),"high":g["high"].max(),"low":g["low"].min(),
                     "close":g["close"].last(),"vol":g["vol"].sum()}).dropna()
    return df

def _prep_tf(b,rule):
    df=_resample(b,rule)
    o=df["open"].to_numpy();h=df["high"].to_numpy();l=df["low"].to_numpy();c=df["close"].to_numpy();v=df["vol"].to_numpy()
    idx=df.index
    hr=(idx.hour+idx.minute/60).to_numpy(); day=idx.normalize().to_numpy()
    ts=idx.to_numpy("datetime64[ns]").astype("int64")
    yr=idx.year.to_numpy()
    # daily context (lagged 1 day, no lookahead)
    dC=df["close"].resample("1D").last(); dH=df["high"].resample("1D").max(); dL=df["low"].resample("1D").min()
    sma=dC.rolling(50).mean()
    trend=((dC>sma).astype(int)-(dC<sma).astype(int)).shift(1)
    dayidx=pd.DatetimeIndex(day)
    trend_b=pd.Series(trend.reindex(dC.index).values,index=dC.index).reindex(dayidx,method=None)
    tmap=dict(zip(dC.index.normalize().values,trend.values))
    trend_arr=np.array([tmap.get(d,np.nan) for d in day])
    pdh=dH.shift(1); pdl=dL.shift(1)
    pdhmap=dict(zip(dH.index.normalize().values,pdh.values)); pdlmap=dict(zip(dL.index.normalize().values,pdl.values))
    pdh_arr=np.array([pdhmap.get(d,np.nan) for d in day]); pdl_arr=np.array([pdlmap.get(d,np.nan) for d in day])
    tr=np.maximum(h-l,np.abs(c-np.concatenate([[c[0]],c[:-1]])))
    atr=pd.Series(tr).rolling(14).mean().to_numpy()
    return dict(o=o,h=h,l=l,c=c,v=v,hr=hr,day=day,ts=ts,yr=yr,atr=atr,
                trend=trend_arr,pdh=pdh_arr,pdl=pdl_arr,n=len(c))

def _init():
    global _TF
    b=pd.read_parquet(BARS)
    for rule in ("3min","5min","10min"):
        _TF[rule]=_prep_tf(b,rule)

# ---------------- indicators ----------------
def _sma(x,n): return pd.Series(x).rolling(n).mean().to_numpy()
def _ema(x,n): return pd.Series(x).ewm(span=n,adjust=False).mean().to_numpy()
def _rsi(x,n):
    d=np.diff(x,prepend=x[0]); up=pd.Series(np.where(d>0,d,0)).rolling(n).mean().to_numpy()
    dn=pd.Series(np.where(d<0,-d,0)).rolling(n).mean().to_numpy()
    return 100-100/(1+up/(dn+1e-9))
def _roll_max(x,n): return pd.Series(x).rolling(n).max().shift(1).to_numpy()
def _roll_min(x,n): return pd.Series(x).rolling(n).min().shift(1).to_numpy()
def _std(x,n): return pd.Series(x).rolling(n).std().to_numpy()

# ---------- entry-trigger signal generators: return int8 {-1,0,1} ----------
def sig(name,A,p):
    c=A["c"]; h=A["h"]; l=A["l"]; n=A["n"]; z=np.zeros(n,"int8")
    if name=="donch":
        N=p[0]; up=c>_roll_max(h,N); dn=c<_roll_min(l,N); z[up]=1; z[dn]=-1
    elif name=="ma":
        f,s=p; mf=_sma(c,f); ms=_sma(c,s); d=np.sign(mf-ms); ch=np.diff(d,prepend=d[0]); z[ch>0]=1; z[ch<0]=-1
    elif name=="ema":
        f,s=p; mf=_ema(c,f); ms=_ema(c,s); d=np.sign(mf-ms); ch=np.diff(d,prepend=d[0]); z[ch>0]=1; z[ch<0]=-1
    elif name=="rsirev":
        P,lo,hi=p; r=_rsi(c,P); pr=np.concatenate([[np.nan],r[:-1]])
        z[(r<lo)&(pr>=lo)]=1; z[(r>hi)&(pr<=hi)]=-1
    elif name=="rsimom":
        P,lo,hi=p; r=_rsi(c,P); pr=np.concatenate([[np.nan],r[:-1]])
        z[(r>hi)&(pr<=hi)]=1; z[(r<lo)&(pr>=lo)]=-1
    elif name=="bbbreak":
        P,k=p; m=_sma(c,P); sd=_std(c,P); z[c>m+k*sd]=1; z[c<m-k*sd]=-1
    elif name=="bbrev":
        P,k=p; m=_sma(c,P); sd=_std(c,P); z[c>m+k*sd]=-1; z[c<m-k*sd]=1
    elif name=="macd":
        f,s,sg=p; ml=_ema(c,f)-_ema(c,s); sl=_ema(ml,sg); d=np.sign(ml-sl); ch=np.diff(d,prepend=d[0]); z[ch>0]=1; z[ch<0]=-1
    elif name=="mom":
        k,thr=p; r=np.concatenate([np.full(k,np.nan),c[k:]/c[:-k]-1]); z[r>=thr]=1; z[r<=-thr]=-1
    elif name=="zrev":
        lb,zt=p; m=_sma(c,lb); sd=_std(c,lb); zs=(c-m)/(sd+1e-9); z[zs>=zt]=-1; z[zs<=-zt]=1
    elif name=="zmom":
        lb,zt=p; m=_sma(c,lb); sd=_std(c,lb); zs=(c-m)/(sd+1e-9); z[zs>=zt]=1; z[zs<=-zt]=-1
    elif name=="pdhl":
        z[c>A["pdh"]]=1; z[c<A["pdl"]]=-1
    elif name=="keltbreak":
        P,k=p; m=_ema(c,P); z[c>m+k*A["atr"]]=1; z[c<m-k*A["atr"]]=-1
    return z

GRID={
 "donch":[(N,) for N in (4,6,8,12,16,24)],
 "ma":[(f,s) for f in (5,9,20) for s in (20,50,100) if f<s],
 "ema":[(f,s) for f in (5,9,20) for s in (20,50,100) if f<s],
 "rsirev":[(P,lo,hi) for P in (7,14) for lo,hi in [(30,70),(20,80),(25,75)]],
 "rsimom":[(P,lo,hi) for P in (7,14) for lo,hi in [(40,60),(45,55)]],
 "bbbreak":[(P,k) for P in (20,50) for k in (1.5,2.0,2.5)],
 "bbrev":[(P,k) for P in (20,50) for k in (2.0,2.5)],
 "macd":[(12,26,9),(5,35,5),(8,21,5)],
 "mom":[(k,thr) for k in (3,5,10,20) for thr in (0.001,0.002,0.004)],
 "zrev":[(lb,z) for lb in (20,60) for z in (1.5,2.0,2.5)],
 "zmom":[(lb,z) for lb in (20,60) for z in (2.0,2.5)],
 "pdhl":[()],
 "keltbreak":[(P,k) for P in (20,50) for k in (1.0,1.5,2.0)],
}
EXITS=[("eod",0,0,0)]+[("st",s,t,0) for s in (10,20,30) for t in (20,40,60)]+[("trail",0,0,a) for a in (2.0,3.0,5.0)]
EXIT_FLIP=[False,True]

def backtest(z, A, sess, exit_spec, flip):
    """single position; enter at bar close on trigger when flat & in session;
    exit on stop/target(intrabar) / trailing / EOD / opposite trigger(if flip)."""
    c=A["c"];h=A["h"];l=A["l"];hr=A["hr"];day=A["day"];ts=A["ts"];atr=A["atr"];n=A["n"]
    lo_h,hi_h=SESSIONS[sess]; mode,stop,tgt,am=exit_spec
    ins=(hr>=lo_h)&(hr<hi_h)
    trades=[]; pos=0; epx=0.0; peak=0.0; entday=None; start=60
    for i in range(start,n):
        if pos!=0:
            ex=False; xpx=c[i]
            # intrabar stop/target
            if mode=="st":
                if pos==1:
                    if l[i]<=epx-stop: xpx=epx-stop; ex=True
                    elif h[i]>=epx+tgt: xpx=epx+tgt; ex=True
                else:
                    if h[i]>=epx+stop: xpx=epx+stop; ex=True
                    elif l[i]<=epx-tgt: xpx=epx-tgt; ex=True
            elif mode=="trail":
                peak=max(peak,h[i]) if pos==1 else min(peak,l[i])
                if pos==1 and l[i]<=peak-am*atr[i]: xpx=peak-am*atr[i]; ex=True
                elif pos==-1 and h[i]>=peak+am*atr[i]: xpx=peak+am*atr[i]; ex=True
            # session-end / day change
            if not ex and (hr[i]>=hi_h or day[i]!=entday): xpx=c[i]; ex=True
            # opposite trigger
            if not ex and flip and z[i]==-pos: xpx=c[i]; ex=True
            if ex:
                trades.append((ts[i],(xpx-epx)*pos-(SPREAD+SLIP))); pos=0
        if pos==0 and ins[i] and z[i]!=0:
            # one entry per day for eod-mode to avoid churn; else allow re-entry
            if mode=="eod" and entday==day[i]: continue
            pos=int(z[i]); epx=c[i]; peak=c[i]; entday=day[i]
    return trades

def metrics(trades):
    if len(trades)<60: return None
    ts=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    dt=pd.to_datetime(ts); dser=pd.Series(pnl,index=dt).groupby(pd.Series(dt).dt.normalize().values).sum()
    if len(dser)<100: return None
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    yr=pd.Series(pnl,index=dt).groupby(dt.year).sum()
    dd=(dser.cumsum().cummax()-dser.cumsum()).max()
    return dict(per_day=round(dser.sum()/len(dser),1),total=round(pnl.sum(),0),sharpe=round(sh,2),
                maxDD=round(dd,0),pos_yrs=int((yr>0).sum()),n_yrs=len(yr),n=len(trades),
                worst_yr=round(float(yr.min()),0))

def _eval(item):
    tf,name,p=item; A=_TF[tf]; z=sig(name,A,p); out=[]
    if (z!=0).sum()<80: return out
    for sess in ("rth","morning","afternoon","full"):
        for ex in EXITS:
            for flip in EXIT_FLIP:
                if ex[0]!="eod" and flip: continue   # limit explosion
                m=metrics(backtest(z,A,sess,ex,flip))
                if not m: continue
                m.update(tf=tf,sig=name,p=str(p),sess=sess,exit=f"{ex[0]}{ex[1]}/{ex[2]}/{ex[3]}",flip=flip)
                out.append(m)
    return out

def main():
    t0=time.time(); _init()
    items=[(tf,name,p) for tf in ("3min","5min","10min") for name,ps in GRID.items() for p in ps]
    print(f"DEEP SEARCH: {len(items)} signal-configs x ~{len(SESSIONS)}sess x {len(EXITS)}exits  {time.time()-t0:.0f}s",flush=True)
    allrows=[]; surv=[]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,res in enumerate(ex.map(_eval,items,chunksize=2)):
            allrows.extend(res)
            for m in res:
                if m["per_day"]>46 and m["pos_yrs"]==m["n_yrs"] and m["sharpe"]>1.3 and m["worst_yr"]>0:
                    surv.append(m); print("SURVIVOR:",{k:m[k] for k in ("per_day","sharpe","pos_yrs","n_yrs","tf","sig","p","sess","exit","flip","n")},flush=True)
            if (i+1)%30==0:
                print(f"  {i+1}/{len(items)}  {time.time()-t0:.0f}s  rows={len(allrows)} surv={len(surv)}",flush=True)
                pd.DataFrame(allrows).to_csv("research/mega_all.csv",index=False)
                if surv: pd.DataFrame(surv).to_csv("research/mega_survivors.csv",index=False)
    df=pd.DataFrame(allrows); df.to_csv("research/mega_all.csv",index=False)
    if surv: pd.DataFrame(surv).to_csv("research/mega_survivors.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} results | {len(surv)} survivors (>$46/day, +every yr, Sh>1.3)",flush=True)
    cols=["per_day","sharpe","maxDD","pos_yrs","n_yrs","worst_yr","n","tf","sig","p","sess","exit","flip"]
    print("\n=== TOP 30 by per_day (all) ===")
    print(df.sort_values("per_day",ascending=False).head(30)[cols].to_string(index=False))
    rob=df[(df.pos_yrs==df.n_yrs)&(df.sharpe>1.3)&(df.worst_yr>0)]
    print(f"\n=== robust (every yr +, Sh>1.3): {len(rob)} ; TOP 20 by per_day ===")
    print(rob.sort_values("per_day",ascending=False).head(20)[cols].to_string(index=False))

if __name__=="__main__":
    main()

"""Next-gen hunt: maximize per-contract $/day by improving each non-overlapping
sleeve, then stacking. Loads BARS ONLY (fast). Ruthless on lookahead.

Sleeves / experiments:
  1) RTH regime-switch: classify each day by first-hour efficiency ratio
     (known before we act); trend day -> breakout ride-to-close, range day ->
     VWAP fade. Mutually exclusive -> 1 position.
  2) Active overnight: London/Asia breakout vs passive drift.
  3) Breakout exit upgrade: partial/trailing vs hold-to-close.
Each reported with $/trading-day, Sharpe, maxDD, per-year.
"""
import numpy as np, pandas as pd, time
BARS="data/tick/nq_bars_1m_2p5y.parquet"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def prep(rule):
    b=pd.read_parquet(BARS)
    o=b["open"].resample(rule).first(); h=b["high"].resample(rule).max()
    l=b["low"].resample(rule).min(); c=b["close"].resample(rule).last()
    df=pd.DataFrame({"open":o,"high":h,"low":l,"close":c}).dropna()
    df["hr"]=df.index.hour+df.index.minute/60; df["day"]=df.index.normalize()
    return df

def dstats(trades):
    if not trades: return None
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    s=pd.Series(pnl,index=ts); dser=s.groupby(s.index.normalize()).sum()
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    eq=dser.cumsum(); dd=(eq.cummax()-eq).max(); yr=dser.groupby(dser.index.year).sum()
    return {"n":len(trades),"per_day":round(dser.sum()/len(dser),1),"total":round(pnl.sum(),0),
            "sharpe":round(sh,2),"maxDD":round(dd,0),"pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),
            "yrs":"/".join(f"{y}:{v:.0f}" for y,v in yr.items()),"dser":dser}

def pr(name,st):
    if not st: print(f"{name}: none"); return
    print(f"{name}: ${st['per_day']}/day total=${st['total']} sharpe={st['sharpe']} maxDD=${st['maxDD']} pos={st['pos_yrs']}/{st['n_yrs']} [{st['yrs']}]")

def regime_switch(df, N, er_thr, stretch, first_h=1.0):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    tr=[]; days=np.unique(day)
    for dd in days:
        di=np.where(day==dd)[0]
        if len(di)<5: continue
        # first-hour efficiency ratio
        fh=di[(hr[di]>=RTH_LO)&(hr[di]<RTH_LO+first_h)]
        if len(fh)<5: continue
        net=abs(c[fh[-1]]-c[fh[0]]); path=np.abs(np.diff(c[fh])).sum()
        if path<=0: continue
        er=net/path
        trend_day = er>=er_thr
        # trade window: after first hour to close
        act=di[(hr[di]>=RTH_LO+first_h)&(hr[di]<RTH_HI)]
        if len(act)<2: continue
        # session vwap accumulation over RTH
        rth=di[(hr[di]>=RTH_LO)&(hr[di]<RTH_HI)]
        vw=np.cumsum(c[rth])/np.arange(1,len(rth)+1); vwmap=dict(zip(rth,vw))
        pos=0; epx=0
        for i in act:
            if pos!=0 and (hr[i]>=RTH_HI): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0; continue
            if pos==0:
                if trend_day:
                    sig=1 if c[i]>dhi[i] else (-1 if c[i]<dlo[i] else 0)
                    if sig: pos=sig; epx=c[i]
                else:
                    dev=c[i]-vwmap.get(i,c[i])
                    if dev>=stretch: pos=-1; epx=c[i]
                    elif dev<=-stretch: pos=1; epx=c[i]
            else:
                if not trend_day:  # range: exit back at vwap
                    dev=c[i]-vwmap.get(i,c[i])
                    if (pos==1 and dev>=0) or (pos==-1 and dev<=0):
                        tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if pos!=0: tr.append((ts[act[-1]],(c[act[-1]]-epx)*pos-(SPREAD+SLIP)))
    return tr

def plain_breakout(df,N=8):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(N+2,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0:
            sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
            if sig and cur!=day[i]: pos=sig; epx=c[i]; cur=day[i]
    return tr

t0=time.time(); df3=prep("3min"); print(f"prepped {time.time()-t0:.0f}s\n")
pr("baseline breakout(3m,N8)", dstats(plain_breakout(df3,8)))
print("\n--- RTH regime-switch grid ---")
best=None
for N in (6,8,12):
    for er in (0.3,0.4,0.5):
        for st in (8.0,15.0,25.0):
            s=dstats(regime_switch(df3,N,er,st))
            if s and (best is None or s["per_day"]>best[1]):
                best=(f"RS_N{N}_er{er}_st{st}",s["per_day"],s)
            if s and s["per_day"]>40:
                pr(f"RS N{N} er{er} st{st}",s)
print("\nBEST regime-switch:", best[0] if best else None)
if best: pr("  -> ",best[2])

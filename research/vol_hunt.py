"""Volume avenue (never used before — size was dropped earlier).
Tests whether trade VOLUME adds edge to the NQ breakout:
  - volume-confirmed breakout (RVOL > thr on the breakout bar)
  - high-RVOL-day filter
  - volume-spike climax reversal
All minute-scale, honest costs, per-year robustness. Baseline = $46 breakout."""
import numpy as np, pandas as pd, time
BARS="data/tick/nq_bars_1m_vol.parquet"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def prep(rule):
    b=pd.read_parquet(BARS)
    g=b.resample(rule)
    df=pd.DataFrame({"open":g["open"].first(),"high":g["high"].max(),"low":g["low"].min(),
                     "close":g["close"].last(),"vol":g["vol"].sum()}).dropna()
    df["hr"]=df.index.hour+df.index.minute/60; df["day"]=df.index.normalize()
    return df

def dstats(trades):
    if not trades or len(trades)<40: return None
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    s=pd.Series(pnl,index=ts); dser=s.groupby(s.index.normalize()).sum()
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    dd=(dser.cumsum().cummax()-dser.cumsum()).max(); yr=dser.groupby(dser.index.year).sum()
    return {"per_day":round(dser.sum()/len(dser),1),"total":round(pnl.sum(),0),"sharpe":round(sh,2),
            "maxDD":round(dd,0),"pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),"n":len(trades),
            "yrs":"/".join(f"{y}:{v:.0f}" for y,v in yr.items())}
def pr(n,s): print(f"{n}: ${s['per_day']}/day tot=${s['total']} sh={s['sharpe']} dd=${s['maxDD']} pos={s['pos_yrs']}/{s['n_yrs']} n={s['n']} [{s['yrs']}]" if s else f"{n}: none")

def breakout_vol(df,N=8,rvol_min=0.0,spike_mode=None,spike_k=3.0):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy(); v=df["vol"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    vavg=pd.Series(v).rolling(30).mean().shift(1).to_numpy()
    rvol=v/np.where(vavg>0,vavg,np.nan)
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(max(N,30)+1,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0 and cur!=day[i]:
            if spike_mode=="climax":   # extreme volume + move -> fade
                if rvol[i]>=spike_k:
                    mv=np.sign(c[i]-c[i-1])
                    if mv: pos=-int(mv); epx=c[i]; cur=day[i]
                continue
            sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
            if sig and (np.isnan(rvol[i]) or rvol[i]>=rvol_min):
                pos=sig; epx=c[i]; cur=day[i]
    return tr

if __name__=="__main__":
    import os
    while not os.path.exists(BARS): time.sleep(5)
    t0=time.time()
    for rule in ["3min","5min"]:
        df=prep(rule); print(f"\n===== {rule}  {len(df):,} bars =====",flush=True)
        pr("baseline breakout (rvol_min=0)", dstats(breakout_vol(df,8,0.0)))
        print("-- volume-CONFIRMED breakout --")
        for rv in (1.0,1.5,2.0,3.0):
            pr(f"breakout rvol>={rv}", dstats(breakout_vol(df,8,rv)))
        print("-- volume CLIMAX reversal --")
        for k in (3.0,5.0,8.0):
            pr(f"climax k{k}", dstats(breakout_vol(df,8,spike_mode='climax',spike_k=k)))
    print(f"\ndone {time.time()-t0:.0f}s")

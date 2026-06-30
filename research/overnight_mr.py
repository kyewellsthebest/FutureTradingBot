"""Overnight/Globex mean-reversion: the Asian session (low volume) is range-
bound -> fade z-score extremes. Different edge than the passive long drift.
Tested as an alternative overnight sleeve. Honest costs, per-year."""
import numpy as np, pandas as pd, time
BARS="data/tick/nq_bars_1m_2p5y.parquet"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5

def prep(rule):
    b=pd.read_parquet(BARS); g=b.resample(rule)
    df=pd.DataFrame({"open":g["open"].first(),"high":g["high"].max(),"low":g["low"].min(),"close":g["close"].last()}).dropna()
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

def overnight_fade(df,lo,hi,lb,z,stop,maxhold):
    """Fade z-score of close vs rolling mean during overnight window [lo,hi) UTC."""
    c=df["close"].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy()
    ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    m=pd.Series(c).rolling(lb).mean(); sd=pd.Series(c).rolling(lb).std()
    zz=((c-m)/sd).to_numpy()
    inwin=(hr>=lo)|(hr<hi) if lo>hi else (hr>=lo)&(hr<hi)   # wraps midnight
    tr=[]; pos=0; epx=0; ent=0
    for i in range(lb+1,len(c)):
        if pos!=0:
            held=i-ent
            g=(c[i]-epx)*pos
            if (not inwin[i]) or held>=maxhold or g<=-stop or (abs(zz[i])<0.3):
                tr.append((ts[i],g-(SPREAD+SLIP))); pos=0
        if not inwin[i] or np.isnan(zz[i]): continue
        if pos==0:
            if zz[i]>=z: pos=-1; epx=c[i]; ent=i
            elif zz[i]<=-z: pos=1; epx=c[i]; ent=i
    return tr

t0=time.time()
for rule in ["3min","5min"]:
    df=prep(rule); print(f"\n===== {rule} =====",flush=True)
    # Asian/Globex window options (UTC): 23->6, 0->7, 22->5
    for (lo,hi) in [(23.0,6.0),(0.0,7.0),(22.0,5.0)]:
        for lb in (20,40):
            for z in (1.5,2.0,2.5):
                for stop in (10.0,20.0):
                    s=dstats(overnight_fade(df,lo,hi,lb,z,stop,30))
                    if s and s["per_day"]>8 and s["pos_yrs"]>=3:
                        pr(f"win{lo}-{hi} lb{lb} z{z} stop{stop}",s)
print(f"\ndone {time.time()-t0:.0f}s")

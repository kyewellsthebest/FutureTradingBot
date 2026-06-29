"""Finer/smarter search on the intraday breakout-to-close family (the only
real edge). Tests fine N, more timeframes, ATR/vol filter, morning-only
window, and re-entry. Same honest costs + positive-every-year gate."""
import time, numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.avenue_intraday_trend import prep, metrics
from research.tick_zoo_2p5y import PT, COMM
SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def strat(df, N, win_hi, vol_q, reentry):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    atr=df["atr"].to_numpy()
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    # ATR regime: only trade when atr above its rolling median quantile
    atr_thr=pd.Series(atr).rolling(200).quantile(vol_q).to_numpy() if vol_q>0 else None
    n=len(c); trades=[]; pos=0; epx=0.0; cur=None
    inrth=(hr>=RTH_LO)&(hr<RTH_HI)
    for i in range(max(N,200),n):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur):
            trades.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if hr[i]>=win_hi: continue
        if pos==0:
            if atr_thr is not None and not (atr[i]>=atr_thr[i]): continue
            sig=0
            if not np.isnan(dhi[i]) and c[i]>dhi[i]: sig=1
            elif not np.isnan(dlo[i]) and c[i]<dlo[i]: sig=-1
            if sig and (reentry or cur!=day[i]):
                pos=sig; epx=c[i]; cur=day[i]
    return trades

t0=time.time(); Z._init(); bars=Z._BARS; res=[]
for rule in ["3min","5min","10min","15min","30min"]:
    df=prep(bars,rule); print(f"{rule} {len(df):,}  {time.time()-t0:.0f}s",flush=True)
    for N in (6,8,10,12,16,20,24,32):
        for win_hi in (RTH_HI,17.0,16.0):     # all-day / until 17 / morning-only
            for vol_q in (0,0.5):
                for reentry in (False,True):
                    tr=strat(df,N,win_hi,vol_q,reentry); m=metrics(tr)
                    if not m: continue
                    m["name"]=f"{rule}_N{N}_w{win_hi:.0f}_v{vol_q}_re{int(reentry)}"
                    res.append(m)
d=pd.DataFrame(res); d.to_csv("research/intraday_fine_results.csv",index=False)
cols=["name","n","tr_day","wr","per_day","per_trade","total","sharpe","maxDD","worst_yr","pos_yrs","n_yrs"]
print(f"\nDONE {time.time()-t0:.0f}s | {len(d)} configs")
print("\n=== TOP 20 by per_day (positive every year, sharpe>1.2) ===")
rob=d[(d.pos_yrs==d.n_yrs)&(d.sharpe>1.2)].sort_values("per_day",ascending=False)
print(f"({len(rob)} qualify)")
print(rob.head(20)[cols].to_string(index=False))

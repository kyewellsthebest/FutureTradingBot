"""Untried avenues with the new data:
  1) OVERNIGHT cross-asset -> NQ RTH prediction (ES/ZB/GC move while NQ quiet
     predicts NQ's session direction). Morning signal, ride to close.
  2) RISK-FILTERED overnight sleeve: skip nights when bonds rally / vol high
     (risk-off) -> protect & boost the long-biased overnight drift.
All minute-scale, honest costs, per-year walk-forward."""
import numpy as np, pandas as pd, time, os
NQ="data/tick/nq_bars_1m_2p5y.parquet"; XDIR="data/xasset"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def load():
    nq=pd.read_parquet(NQ)[["open","high","low","close"]].copy()
    for p in ["ES","ZB","GC"]:
        f=f"{XDIR}/{p}_1s.parquet"
        if os.path.exists(f):
            d=pd.read_parquet(f); d.index=pd.to_datetime(d["ts"])
            nq=nq.join(d.resample("1min")["close"].last().rename(p),how="left")
    nq=nq.ffill(limit=5); nq["hr"]=nq.index.hour+nq.index.minute/60; nq["day"]=nq.index.normalize()
    return nq

def dstats(trades):
    if not trades or len(trades)<40: return None
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    s=pd.Series(pnl,index=ts); dser=s.groupby(s.index.normalize()).sum()
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    dd=(dser.cumsum().cummax()-dser.cumsum()).max(); yr=dser.groupby(dser.index.year).sum()
    return {"per_day":round(dser.sum()/len(dser),1),"total":round(pnl.sum(),0),"sharpe":round(sh,2),
            "maxDD":round(dd,0),"pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),"n":len(trades),
            "yrs":"/".join(f"{y}:{v:.0f}" for y,v in yr.items()),"dser":dser}
def pr(n,s): print(f"{n}: ${s['per_day']}/day tot=${s['total']} sh={s['sharpe']} dd=${s['maxDD']} pos={s['pos_yrs']}/{s['n_yrs']} n={s['n']} [{s['yrs']}]" if s else f"{n}: none")

# daily helper: per-day arrays
def day_groups(df):
    return df.groupby("day")

def overnight_lead(df, lead, thr, sign):
    """For each day: overnight return of `lead` = lead@~14:25 / lead@prev~21:00 - 1.
    If strong, enter NQ at RTH open (~14:30) dir=sign*signal, hold to close."""
    days=sorted(df["day"].unique()); tr=[]
    # precompute per-day series
    g={d:x for d,x in df.groupby("day")}
    prev=None
    for d in days:
        x=g[d]
        # overnight lead move: from prev day 21:00 close to today 14:25
        if prev is not None and lead in df:
            pe=g[prev]; pe_eod=pe[(pe.hr>=20.9)]
            tod_pre=x[(x.hr>=14.0)&(x.hr<14.5)]
            rth=x[(x.hr>=RTH_LO)&(x.hr<RTH_HI)]
            if len(pe_eod) and len(tod_pre) and len(rth)>3:
                l0=pe_eod[lead].iloc[-1] if not np.isnan(pe_eod[lead].iloc[-1]) else np.nan
                l1=tod_pre[lead].iloc[-1] if not np.isnan(tod_pre[lead].iloc[-1]) else np.nan
                if np.isfinite(l0) and np.isfinite(l1) and l0>0:
                    onr=l1/l0-1
                    sig=sign*(1 if onr>=thr else (-1 if onr<=-thr else 0))
                    if sig:
                        e=rth["close"].iloc[0]; xpx=rth["close"].iloc[-1]
                        ts=rth.index[-1].value
                        tr.append((ts,(xpx-e)*sig-(SPREAD+SLIP)))
        prev=d
    return tr

def overnight_filtered(df, filt_lead, filt_thr, mode):
    """Long NQ overnight (21:00->next 14:30) but SKIP nights flagged risk-off.
    risk-off proxy: filt_lead overnight-to-entry move (bonds up = flight to safety).
    mode='skip_leadup' skip when lead rose >thr; 'skip_leaddn' skip when fell."""
    days=sorted(df["day"].unique()); g={d:x for d,x in df.groupby("day")}; tr=[]
    for i in range(len(days)-1):
        d=days[i]; nd=days[i+1]; x=g[d]; xn=g[nd]
        ein=x[(x.hr>=21.0)]; xout=xn[(xn.hr>=14.5)]
        if not len(ein) or not len(xout): continue
        e=ein["close"].iloc[0]; xpx=xout["close"].iloc[0]; ts=xout.index[0].value
        take=True
        if filt_lead in df:
            l0=ein[filt_lead].iloc[0]
            # lead move during early overnight (entry -> +3h) as risk gauge
            win=xn[(xn.hr>=11.0)&(xn.hr<14.5)] if False else x[(x.hr>=21.0)]
            l1=win[filt_lead].iloc[-1] if len(win) else l0
            if np.isfinite(l0) and np.isfinite(l1) and l0>0:
                lr=l1/l0-1
                if mode=="skip_leadup" and lr>filt_thr: take=False
                if mode=="skip_leaddn" and lr<-filt_thr: take=False
        if take: tr.append((ts,(xpx-e)*1-(SPREAD+SLIP)))
    return tr

def overnight_plain(df):
    days=sorted(df["day"].unique()); g={d:x for d,x in df.groupby("day")}; tr=[]
    for i in range(len(days)-1):
        x=g[days[i]]; xn=g[days[i+1]]
        ein=x[(x.hr>=21.0)]; xout=xn[(xn.hr>=14.5)]
        if not len(ein) or not len(xout): continue
        e=ein["close"].iloc[0]; xpx=xout["close"].iloc[0]
        tr.append((xout.index[0].value,(xpx-e)-(SPREAD+SLIP)))
    return tr

t0=time.time(); df=load(); print(f"loaded {time.time()-t0:.0f}s",flush=True)
print("\n== overnight plain (baseline) =="); pr("overnight", dstats(overnight_plain(df)))
print("\n== overnight cross-asset LEAD -> NQ RTH ==")
for lead in ["ES","ZB","GC"]:
    for thr in (0.001,0.003,0.006):
        for sign in (1,-1):
            s=dstats(overnight_lead(df,lead,thr,sign))
            if s and s["per_day"]>10 and s["pos_yrs"]>=3: pr(f"on-lead {lead} thr{thr} s{sign}",s)
print("\n== risk-FILTERED overnight drift ==")
for lead in ["ZB","GC","ES"]:
    for thr in (0.002,0.004,0.008):
        for mode in ("skip_leadup","skip_leaddn"):
            s=dstats(overnight_filtered(df,lead,thr,mode))
            if s and s["sharpe"]>1.5: pr(f"on-filt {lead} {mode} thr{thr}",s)
print(f"\ndone {time.time()-t0:.0f}s")

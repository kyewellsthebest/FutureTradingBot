"""Improve the overnight sleeve and the breakout exit. Bars-only (fast)."""
import numpy as np, pandas as pd, time
BARS="data/tick/nq_bars_1m_2p5y.parquet"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def prep(rule):
    b=pd.read_parquet(BARS)
    o=b["open"].resample(rule).first(); h=b["high"].resample(rule).max()
    l=b["low"].resample(rule).min(); c=b["close"].resample(rule).last()
    df=pd.DataFrame({"open":o,"high":h,"low":l,"close":c}).dropna()
    df["hr"]=df.index.hour+df.index.minute/60; df["day"]=df.index.normalize()
    tr=np.maximum(df["high"]-df["low"],(df["close"]-df["close"].shift()).abs())
    df["atr"]=tr.rolling(20).mean()
    return df

def dstats(trades):
    if not trades or len(trades)<30: return None
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    s=pd.Series(pnl,index=ts); dser=s.groupby(s.index.normalize()).sum()
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    eq=dser.cumsum(); dd=(eq.cummax()-eq).max(); yr=dser.groupby(dser.index.year).sum()
    return {"n":len(trades),"per_day":round(dser.sum()/len(dser),1),"total":round(pnl.sum(),0),
            "sharpe":round(sh,2),"maxDD":round(dd,0),"pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),
            "yrs":"/".join(f"{y}:{v:.0f}" for y,v in yr.items()),"dser":dser}
def pr(n,s):
    if not s: print(f"{n}: none"); return
    print(f"{n}: ${s['per_day']}/day total=${s['total']} sharpe={s['sharpe']} maxDD=${s['maxDD']} pos={s['pos_yrs']}/{s['n_yrs']} [{s['yrs']}]")

# overnight window = 21:00 -> next 14:30
def overnight_passive(df,d=1):
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); c=df["close"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    tr=[]; days=np.unique(day)
    for k in range(len(days)-1):
        i=np.where((day==days[k])&(hr>=21.0))[0]; o=np.where((day==days[k+1])&(hr>=14.5))[0]
        if len(i) and len(o): tr.append((ts[o[0]],(c[o[0]]-c[i[0]])*d-(SPREAD+SLIP)))
    return tr

def overnight_breakout(df,N=8):
    # Donchian breakout active during the overnight window, flat at 14:30
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    # overnight = hr>=21 OR hr<14.5
    on=(hr>=21.0)|(hr<RTH_LO); tr=[]; pos=0; epx=0; cur=None
    for i in range(N+2,len(c)):
        # flat at RTH open
        if pos!=0 and not on[i]: tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not on[i]: continue
        sesh=day[i] if hr[i]>=21.0 else day[i]-np.timedelta64(1,'D')
        if pos==0:
            sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
            if sig and cur!=sesh: pos=sig; epx=c[i]; cur=sesh
    return tr

def breakout_exit(df,N=8,mode="eod",atr_mult=0.0,stop=0.0):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64"); atr=df["atr"].to_numpy()
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; peak=0; cur=None
    for i in range(N+2,len(c)):
        if pos!=0:
            peak=max(peak,c[i]) if pos==1 else min(peak,c[i])
            ex=False
            if hr[i]>=RTH_HI or day[i]!=cur: ex=True
            elif stop>0 and (c[i]-epx)*pos<=-stop: ex=True
            elif atr_mult>0 and ((pos==1 and c[i]<peak-atr_mult*atr[i]) or (pos==-1 and c[i]>peak+atr_mult*atr[i])): ex=True
            if ex: tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0:
            sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
            if sig and cur!=day[i]: pos=sig; epx=c[i]; peak=c[i]; cur=day[i]
    return tr

t0=time.time(); df3=prep("3min"); df5=prep("5min"); print(f"prepped {time.time()-t0:.0f}s\n")
print("--- overnight sleeve options ---")
pr("passive drift(5m)", dstats(overnight_passive(df5,1)))
for N in (6,8,12,20):
    pr(f"overnight breakout 3m N{N}", dstats(overnight_breakout(df3,N)))
print("\n--- RTH breakout exit upgrades (baseline eod=$46) ---")
pr("eod (baseline)", dstats(breakout_exit(df3,8,"eod")))
for am in (2.0,3.0,5.0):
    pr(f"atr-trail {am}", dstats(breakout_exit(df3,8,"trail",atr_mult=am)))
for s in (15,30,50):
    pr(f"hard-stop {s}+eod", dstats(breakout_exit(df3,8,"eod",stop=s)))

def breakout_window(df,N,lo,hi):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    win=(hr>=lo)&(hr<hi); tr=[]; pos=0; epx=0; cur=None
    for i in range(N+2,len(c)):
        if pos!=0 and (hr[i]>=hi or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not win[i]: continue
        if pos==0:
            sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
            if sig and cur!=day[i]: pos=sig; epx=c[i]; cur=day[i]
    return tr

if __name__=="__main__" and True:
    print("\n--- RTH split AM/PM (each breakout-to-subclose) ---")
    for N in (6,8):
        am=dstats(breakout_window(df3,N,14.5,17.5)); pm=dstats(breakout_window(df3,N,17.5,20.92))
        pr(f"AM 14:30-17:30 N{N}",am); pr(f"PM 17:30-20:55 N{N}",pm)
        if am and pm:
            comb=am["dser"].add(pm["dser"],fill_value=0)
            sh=comb.mean()/comb.std()*np.sqrt(252); dd=(comb.cumsum().cummax()-comb.cumsum()).max()
            yr=comb.groupby(comb.index.year).sum()
            print(f"   AM+PM stacked N{N}: ${comb.sum()/len(comb):.1f}/day total=${comb.sum():.0f} sharpe={sh:.2f} maxDD=${dd:.0f} pos={(yr>0).sum()}/{len(yr)}")
    # full stack: best RTH + overnight
    print("\n--- FULL STACK candidates ---")
    rth=dstats(breakout_exit(df3,8,"eod")); on=dstats(overnight_passive(df5,1))
    full=rth["dser"].add(on["dser"],fill_value=0)
    sh=full.mean()/full.std()*np.sqrt(252); dd=(full.cumsum().cummax()-full.cumsum()).max(); yr=full.groupby(full.index.year).sum()
    print(f"RTH-breakout + overnight: ${full.sum()/len(full):.1f}/day total=${full.sum():.0f} sharpe={sh:.2f} maxDD=${dd:.0f} pos={(yr>0).sum()}/{len(yr)} [{'/'.join(f'{y}:{v:.0f}' for y,v in yr.items())}]")
    # try adding AM+PM split instead of single RTH
    am=dstats(breakout_window(df3,6,14.5,17.5)); pm=dstats(breakout_window(df3,6,17.5,20.92))
    full2=am["dser"].add(pm["dser"],fill_value=0).add(on["dser"],fill_value=0)
    sh=full2.mean()/full2.std()*np.sqrt(252); dd=(full2.cumsum().cummax()-full2.cumsum()).max(); yr=full2.groupby(full2.index.year).sum()
    print(f"AM+PM + overnight:        ${full2.sum()/len(full2):.1f}/day total=${full2.sum():.0f} sharpe={sh:.2f} maxDD=${dd:.0f} pos={(yr>0).sum()}/{len(yr)} [{'/'.join(f'{y}:{v:.0f}' for y,v in yr.items())}]")

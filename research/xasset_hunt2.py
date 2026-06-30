"""Cross-asset lead-lag hunt v2: use ES/ZB/GC as LEADING information, not
confirmation. All minute-scale (executable). Stacks tested vs $74 system."""
import numpy as np, pandas as pd, time, os
NQ_BARS="data/tick/nq_bars_1m_2p5y.parquet"; XDIR="data/xasset"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def load_align():
    nq=pd.read_parquet(NQ_BARS)[["open","high","low","close"]].copy()
    for p in ["ES","ZB","GC"]:
        f=f"{XDIR}/{p}_1s.parquet"
        if not os.path.exists(f): continue
        d=pd.read_parquet(f); d.index=pd.to_datetime(d["ts"]); g=d.resample("1min")["close"].last()
        nq=nq.join(g.rename(f"{p}"),how="left")
    nq=nq.ffill(limit=5)
    nq["hr"]=nq.index.hour+nq.index.minute/60; nq["day"]=nq.index.normalize()
    return nq

def to_tf(df,rule):
    g=df.resample(rule)
    out=pd.DataFrame({"open":g["open"].first(),"high":g["high"].max(),"low":g["low"].min(),"close":g["close"].last()})
    for c in ["ES","ZB","GC"]:
        if c in df: out[c]=g[c].last()
    out=out.dropna(subset=["close"]); out["hr"]=out.index.hour+out.index.minute/60; out["day"]=out.index.normalize()
    return out

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

def leadlag(df,k,thr,hold,lead="ES"):
    """ES outran NQ over last k bars -> NQ catches up. Enter NQ, hold `hold` bars or EOD."""
    if lead not in df: return []
    c=df["close"].to_numpy(); L=df[lead].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy()
    ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    nqr=np.concatenate([np.full(k,np.nan), c[k:]/c[:-k]-1])
    lr =np.concatenate([np.full(k,np.nan), L[k:]/L[:-k]-1])
    diff=lr-nqr
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; ent=0
    for i in range(k+1,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=day[ent] or (i-ent)>=hold):
            tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i] or np.isnan(diff[i]): continue
        if pos==0:
            if diff[i]>=thr: pos=1; epx=c[i]; ent=i
            elif diff[i]<=-thr: pos=-1; epx=c[i]; ent=i
    return tr

def es_mom(df,k,thr,lead="ES"):
    """Strong ES move over k bars -> ride NQ same dir to close (ES leads)."""
    if lead not in df: return []
    c=df["close"].to_numpy(); L=df[lead].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy()
    ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    lr=np.concatenate([np.full(k,np.nan), L[k:]/L[:-k]-1])
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(k+1,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i] or np.isnan(lr[i]): continue
        if pos==0 and cur!=day[i]:
            if lr[i]>=thr: pos=1; epx=c[i]; cur=day[i]
            elif lr[i]<=-thr: pos=-1; epx=c[i]; cur=day[i]
    return tr

def ratio_rev(df,lb,z,lead="ES"):
    """NQ/ES ratio z-score: fade NQ when it over/under-extends vs ES."""
    if lead not in df: return []
    c=df["close"].to_numpy(); L=df[lead].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy()
    ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    ratio=pd.Series(c/L); m=ratio.rolling(lb).mean(); sd=ratio.rolling(lb).std()
    zz=((ratio-m)/sd).to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; ent=0
    for i in range(lb+1,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=day[ent] or abs(zz[i])<0.3):
            tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i] or np.isnan(zz[i]): continue
        if pos==0:
            if zz[i]>=z: pos=-1; epx=c[i]; ent=i      # NQ rich vs ES -> short
            elif zz[i]<=-z: pos=1; epx=c[i]; ent=i
    return tr

t0=time.time(); base=load_align(); print(f"loaded+aligned {time.time()-t0:.0f}s",flush=True)
for rule in ["1min","3min"]:
    df=to_tf(base,rule) if rule!="1min" else base
    print(f"\n===== {rule} =====",flush=True)
    print("-- ES lead-lag catch-up --")
    for k in (1,2,3,5):
        for thr in (0.0005,0.001,0.002):
            for hold in (5,10,20):
                s=dstats(leadlag(df,k,thr,hold))
                if s and s["per_day"]>15 and s["pos_yrs"]>=3: pr(f"leadlag k{k} thr{thr} h{hold}",s)
    print("-- ES momentum->NQ to close --")
    for k in (3,5,10):
        for thr in (0.001,0.002,0.004):
            s=dstats(es_mom(df,k,thr))
            if s and s["per_day"]>15 and s["pos_yrs"]>=3: pr(f"es_mom k{k} thr{thr}",s)
    print("-- NQ/ES ratio reversion --")
    for lb in (20,60):
        for z in (1.5,2.0,2.5):
            s=dstats(ratio_rev(df,lb,z))
            if s and s["per_day"]>15 and s["pos_yrs"]>=3: pr(f"ratio_rev lb{lb} z{z}",s)

# ---- appended: ZB/GC (uncorrelated) leads, both polarities, RTH-to-close ----
def lead_toclose(df,lead,k,thr,sign):
    if lead not in df: return []
    c=df["close"].to_numpy(); L=df[lead].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy()
    ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    lr=np.concatenate([np.full(k,np.nan), L[k:]/L[:-k]-1])
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(k+1,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i] or np.isnan(lr[i]): continue
        if pos==0 and cur!=day[i]:
            d=sign*(1 if lr[i]>=thr else (-1 if lr[i]<=-thr else 0))
            if d: pos=d; epx=c[i]; cur=day[i]
    return tr

if __name__=="__main__":
    print("\n===== ZB / GC uncorrelated leads (3min, both polarities) =====",flush=True)
    df=to_tf(base,"3min")
    for lead in ["ZB","GC"]:
        for k in (5,10,20):
            for thr in (0.0008,0.002):
                for sign in (1,-1):
                    s=dstats(lead_toclose(df,lead,k,thr,sign))
                    if s and s["per_day"]>12 and s["pos_yrs"]>=3: pr(f"{lead} k{k} thr{thr} sign{sign}",s)
    # ---- STACK TEST: does the best RTH replacement beat plain breakout, and does
    #      breakout+overnight stay the best 1-contract stack? ----
    print("\n===== STACK CHECK =====",flush=True)
    # plain breakout daily series (reuse from nextgen logic, inline)
    def breakout(df,N=8):
        c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
        hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
        dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
        inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
        for i in range(N+2,len(c)):
            if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
            if not inrth[i]: continue
            if pos==0 and cur!=day[i]:
                sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
                if sig: pos=sig; epx=c[i]; cur=day[i]
        return tr
    df3=to_tf(base,"3min")
    bo=dstats(breakout(df3,8)); pr("plain breakout(3m,N8)",bo)
    em=dstats(es_mom(df3,5,0.001)); pr("es_mom k5 (best ES RTH)",em)
    if bo and em:
        # correlation of daily pnl (do they overlap or diversify?)
        j=pd.concat([bo["dser"].rename("bo"),em["dser"].rename("em")],axis=1).fillna(0)
        print(f"  corr(breakout, es_mom) daily = {j['bo'].corr(j['em']):.2f}",flush=True)

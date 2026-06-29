"""Cross-asset lead-lag hunt (runs when data/xasset/*.parquet exist).

Hypothesis set (all minute-scale, retail-executable, stack on the $74 system):
  1) ES-confirmed NQ breakout: only take the NQ RTH breakout when ES is also
     breaking the same way (cross-confirmation cuts false breakouts).
  2) ES-lead NQ: when ES's last-k-min return is strongly +/-, ride NQ to close.
  3) VIX regime: trade NQ breakout only when VIX is falling / below SMA
     (risk-on); flip/skip when VIX spiking.
  4) Bond (ZB) divergence: bonds down + equities up = risk-on confirm.
As a STANDALONE sleeve and STACKED onto the existing NQ breakout+overnight.
Everything aligned on 1-min UTC index. Honest costs, per-year robustness.
"""
import numpy as np, pandas as pd, time, os
NQ_BARS="data/tick/nq_bars_1m_2p5y.parquet"
XDIR="data/xasset"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def load():
    nq=pd.read_parquet(NQ_BARS)              # index=DatetimeIndex, OHLC
    nq=nq[["open","high","low","close"]].copy()
    x={}
    for p in ["ES","ZB","GC","VIX"]:
        f=f"{XDIR}/{p}_1m.parquet"
        if os.path.exists(f):
            d=pd.read_parquet(f); d.index=pd.to_datetime(d["ts"]); 
            x[p]=d[["open","high","low","close"]].rename(columns=lambda c:f"{p}_{c}")
    return nq,x

def align(nq,x):
    df=nq.copy()
    for p,d in x.items():
        df=df.join(d.resample("1min").last(),how="left")
    return df.ffill(limit=3)

def dstats(dser):
    if dser is None or len(dser)<60: return None
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    dd=(dser.cumsum().cummax()-dser.cumsum()).max(); yr=dser.groupby(dser.index.year).sum()
    return {"per_day":round(dser.sum()/len(dser),1),"total":round(dser.sum(),0),"sharpe":round(sh,2),
            "maxDD":round(dd,0),"pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),
            "yrs":"/".join(f"{y}:{v:.0f}" for y,v in yr.items())}
def pr(n,s): print(f"{n}: ${s['per_day']}/day total=${s['total']} sharpe={s['sharpe']} maxDD=${s['maxDD']} pos={s['pos_yrs']}/{s['n_yrs']} [{s['yrs']}]" if s else f"{n}: none")

def to_3m(df):
    g=df.resample("3min")
    out=pd.DataFrame({"open":g["open"].first(),"high":g["high"].max(),"low":g["low"].min(),"close":g["close"].last()})
    for c in df.columns:
        if c not in ("open","high","low","close"): out[c]=g[c].last()
    out=out.dropna(subset=["close"]); out["hr"]=out.index.hour+out.index.minute/60; out["day"]=out.index.normalize()
    return out

def daily(trades):
    if not trades: return None
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    s=pd.Series(pnl,index=ts); return s.groupby(s.index.normalize()).sum()

def es_confirmed_breakout(df,N=8,esk=8):
    """NQ breakout, but require ES also above its own N-bar high (long)/below (short)."""
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    es=df["ES_close"].to_numpy() if "ES_close" in df else None
    if es is not None:
        ehi=pd.Series(df["ES_high"]).rolling(N).max().shift(1).to_numpy(); elo=pd.Series(df["ES_low"]).rolling(N).min().shift(1).to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(N+2,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0 and cur!=day[i]:
            long_ok = (c[i]>dhi[i]) and (es is None or es[i]>ehi[i])
            short_ok= (c[i]<dlo[i]) and (es is None or es[i]<elo[i])
            sig=1 if long_ok else (-1 if short_ok else 0)
            if sig: pos=sig; epx=c[i]; cur=day[i]
    return tr

def vix_filtered_breakout(df,N=8,vix_sma=60):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    if "VIX_close" not in df: return []
    vix=df["VIX_close"]; vsma=vix.rolling(vix_sma).mean().to_numpy(); vix=vix.to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(max(N,vix_sma)+2,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0 and cur!=day[i]:
            risk_on = vix[i]<vsma[i]   # falling/low vol
            sig=1 if (c[i]>dhi[i]) else (-1 if c[i]<dlo[i] else 0)
            # in risk-on, favor longs; in risk-off, allow shorts only
            if sig==1 and risk_on: pos=1; epx=c[i]; cur=day[i]
            elif sig==-1 and not risk_on: pos=-1; epx=c[i]; cur=day[i]
    return tr

def plain_breakout(df,N=8):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(N+2,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0 and cur!=day[i]:
            sig=1 if (c[i]>dhi[i]) else (-1 if c[i]<dlo[i] else 0)
            if sig: pos=sig; epx=c[i]; cur=day[i]
    return tr

def main():
    t0=time.time(); nq,x=load()
    print(f"NQ {len(nq):,} bars; xasset loaded: {list(x.keys())}  {time.time()-t0:.0f}s",flush=True)
    if not x:
        print("NO cross-asset data yet — run the Actions workflow first."); return
    df=to_3m(align(nq,x)); print(f"aligned 3m {len(df):,}  cols={[c for c in df.columns if '_' in c]}  {time.time()-t0:.0f}s",flush=True)
    pr("baseline NQ breakout(3m,N8)", dstats(daily(plain_breakout(df,8))))
    print("\n--- cross-asset variants ---")
    for N in (6,8,12):
        pr(f"ES-confirmed breakout N{N}", dstats(daily(es_confirmed_breakout(df,N))))
    for N in (6,8,12):
        pr(f"VIX-filtered breakout N{N}", dstats(daily(vix_filtered_breakout(df,N))))
    # stack best cross-asset RTH sleeve onto overnight drift handled separately
if __name__=="__main__": main()

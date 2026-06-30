"""ML with CROSS-ASSET features: predict NQ next-H-min direction using NQ +
ES/ZB/GC lagged returns/spreads. Walk-forward, train-before-test, tree model
(scale-invariant). Trade confident OOS predictions RTH, exit fixed horizon.
Honest costs + per-year robustness. This is the NQ-only ML test, upgraded
with the new cross-asset information."""
import warnings, time, numpy as np, pandas as pd, os
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier
NQ="data/tick/nq_bars_1m_2p5y.parquet"; XDIR="data/xasset"
PT=2.0; COMM=0.74; SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92; SEED=7

def load():
    nq=pd.read_parquet(NQ)[["open","high","low","close"]].copy()
    for p in ["ES","ZB","GC"]:
        f=f"{XDIR}/{p}_1s.parquet"
        if os.path.exists(f):
            d=pd.read_parquet(f); d.index=pd.to_datetime(d["ts"])
            nq=nq.join(d.resample("1min")["close"].last().rename(p),how="left")
    return nq.ffill(limit=5)

def feats(df):
    c=df["close"].astype(float); F=pd.DataFrame(index=df.index)
    lc=np.log(c)
    for w in (1,3,5,15,30,60): F[f"nqr{w}"]=lc.diff(w)
    for w in (10,30): F[f"nqvol{w}"]=lc.diff().rolling(w).std()
    h=df["high"].astype(float); l=df["low"].astype(float)
    for w in (15,30): F[f"pos{w}"]=(c-l.rolling(w).min())/(h.rolling(w).max()-l.rolling(w).min()+1e-9)
    # cross-asset features: their own returns + lead diff vs NQ
    for p in ["ES","ZB","GC"]:
        if p in df:
            lp=np.log(df[p].astype(float))
            for w in (1,3,5,15,30):
                F[f"{p}r{w}"]=lp.diff(w)
                F[f"{p}lead{w}"]=lp.diff(w)-lc.diff(w)   # lead minus NQ (catch-up signal)
    hr=df.index.hour+df.index.minute/60
    F["hr_sin"]=np.sin(2*np.pi*hr/24); F["hr_cos"]=np.cos(2*np.pi*hr/24); F["dow"]=df.index.dayofweek
    return F

def simulate(det_ts, d, stop, tgt, max_hold_s=900):
    # exit on fixed stop/target within horizon using NQ 1-min closes (executable, minute-scale)
    pass

def label(df,H):
    c=np.log(df["close"].astype(float)); fwd=c.shift(-H)-c
    return (fwd>0).astype(int), fwd

def walk(F,y,q):
    proba=np.full(len(F),np.nan); X=F.to_numpy("float32"); uq=sorted(pd.unique(q))
    for qi in uq:
        tr=q<qi; te=q==qi
        if tr.sum()<60000: continue
        m=HistGradientBoostingClassifier(max_iter=300,max_depth=4,learning_rate=0.05,
            l2_regularization=1.0,min_samples_leaf=200,early_stopping=True,random_state=SEED)
        m.fit(X[tr],y[tr]); proba[te]=m.predict_proba(X[te])[:,1]
    return proba

def trade(df,sig_idx,dirs,H):
    """enter at bar close, exit H bars later. ONE position at a time (real 1-MNQ
    constraint): skip any signal that fires while a trade is still open."""
    c=df["close"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64"); n=len(c)
    tr=[]; free=-1
    for i,d in zip(sig_idx,dirs):
        if i<free: continue          # already in a position -> can't take it on 1 contract
        if i+H>=n: break
        e=c[i]; xpx=c[i+H]; tr.append((ts[i],(xpx-e)*d-(SPREAD+SLIP))); free=i+H
    return tr

def dstats(trades):
    if not trades or len(trades)<60: return None
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    s=pd.Series(pnl,index=ts); dser=s.groupby(s.index.normalize()).sum()
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    yr=dser.groupby(dser.index.year).sum(); dd=(dser.cumsum().cummax()-dser.cumsum()).max()
    return {"per_day":round(dser.sum()/len(dser),1),"total":round(pnl.sum(),0),"sharpe":round(sh,2),
            "maxDD":round(dd,0),"pos_yrs":int((yr>0).sum()),"n_yrs":len(yr),"n":len(trades),
            "wr":round(100*(pnl>0).mean(),1),"yrs":"/".join(f"{y}:{v:.0f}" for y,v in yr.items())}

t0=time.time(); df=load(); print(f"loaded {time.time()-t0:.0f}s",flush=True)
F=feats(df); hr=df.index.hour+df.index.minute/60; rth=np.asarray((hr>=RTH_LO)&(hr<RTH_HI))
q=pd.PeriodIndex(df.index,freq="Q").astype(str).to_numpy()
ix=np.arange(len(df))
for H in (10,20,30):
    y,fwd=label(df,H); valid=F.notna().all(axis=1).to_numpy() & ~np.isnan(fwd.to_numpy()) & rth
    Fv=F[valid]; yv=y.to_numpy()[valid]; qv=q[valid]; iv=ix[valid]
    print(f"\nH={H}: {valid.sum():,} RTH bars, {Fv.shape[1]} feats (incl cross-asset)  {time.time()-t0:.0f}s",flush=True)
    proba=walk(Fv,yv,qv)
    for margin in (0.08,0.12,0.18):
        mask=~np.isnan(proba)&((proba>=0.5+margin)|(proba<=0.5-margin))
        si=iv[mask]; d=np.where(proba[mask]>=0.5,1,-1)
        if mask.sum()<60: print(f"  m{margin}: {mask.sum()} sigs"); continue
        s=dstats(trade(df,si,d,H))
        if s: print(f"  m{margin}: per_day=${s['per_day']} sharpe={s['sharpe']} wr={s['wr']} pos={s['pos_yrs']}/{s['n_yrs']} n={s['n']} [{s['yrs']}]",flush=True)
print(f"\ndone {time.time()-t0:.0f}s")

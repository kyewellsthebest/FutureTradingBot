"""Avenue E: ML FEATURE MODEL with strict walk-forward.

Engineer ~25 features per 1-min bar (multi-window returns, vol, range
position, ATR, EMA distance, RSI, time-of-day), label each bar by its
forward return sign, and train a HistGradientBoosting classifier
EXPANDING-WINDOW walk-forward: model for test-quarter Q is trained ONLY on
bars strictly before Q. Out-of-sample predictions become trade signals;
confident ones are executed through the realistic tick sim (delay+misfill+
costs). Per-quarter metrics are therefore genuine OOS.

Tree model => scale-invariant => no normalization leakage. Target uses a
forward window but is never a feature. Train-before-test prevents leakage.

Run: python -m research.avenue_ml
"""
from __future__ import annotations
import time, warnings
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import _init, NS, PT, HALF_SPREAD, COMM, STOP_SLIP, SEED, COOLDOWN_S
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier

def make_features(bars):
    c=bars["close"].astype("float64"); h=bars["high"].astype("float64"); l=bars["low"].astype("float64"); o=bars["open"].astype("float64")
    lr=np.log(c).diff()
    F=pd.DataFrame(index=bars.index)
    for w in (1,2,3,5,10,15,30,60):
        F[f"ret{w}"]=np.log(c).diff(w)
    for w in (10,30,60):
        F[f"vol{w}"]=lr.rolling(w).std()
    for w in (15,30,60):
        rng=(c-l.rolling(w).min())/(h.rolling(w).max()-l.rolling(w).min()+1e-9)
        F[f"pos{w}"]=rng
    tr=np.maximum(h-l,np.abs(c-c.shift()))
    for w in (14,30):
        F[f"atr{w}"]=tr.rolling(w).mean()/c
    for w in (9,21,50):
        F[f"ema{w}"]=(c-c.ewm(span=w).mean())/c
    # RSI14
    d=c.diff(); up=d.clip(lower=0).rolling(14).mean(); dn=(-d.clip(upper=0)).rolling(14).mean()
    F["rsi14"]=100-100/(1+up/(dn+1e-9))
    hr=bars.index.hour+bars.index.minute/60
    F["hr_sin"]=np.sin(2*np.pi*hr/24); F["hr_cos"]=np.cos(2*np.pi*hr/24)
    F["dow"]=bars.index.dayofweek
    F["hour"]=bars.index.hour
    return F

def make_label(bars, horizon):
    c=bars["close"].astype("float64")
    fwd=np.log(c).shift(-horizon)-np.log(c)
    return (fwd>0).astype("int8"), fwd

def simulate(det_ts, tdir, stop, tgt, max_hold_s=900, seed=SEED):
    ts=Z._TS; px=Z._PX; ntick=len(ts); rng=np.random.default_rng(seed)
    cooldown=COOLDOWN_S*NS; max_hold=max_hold_s*NS; trades=[]; t_free=ts[0]
    order=np.argsort(det_ts); det_ts=det_ts[order]; tdir=tdir[order]
    for k in range(len(det_ts)):
        dts=int(det_ts[k])
        if dts<t_free: continue
        d=int(tdir[k])
        if d==0: continue
        delay=int(rng.uniform(100,800))*1_000_000
        fidx=np.searchsorted(ts,dts+delay,"left")
        if fidx>=ntick: break
        e=float(px[fidx])+d*(HALF_SPREAD+rng.uniform(0,0.5)); fire=ts[fidx]
        hi=np.searchsorted(ts,fire+max_hold,"right"); lo=fidx+1
        if lo>=hi: continue
        seg=px[lo:hi]; tseg=ts[lo:hi]; g=d*(seg-e)
        s_hit=g<=-stop; t_hit=g>=tgt; ex=s_hit|t_hit
        if ex.any():
            xi=int(np.argmax(ex)); gain=(tgt if (t_hit[xi] and not s_hit[xi]) else -stop-STOP_SLIP); xts=tseg[xi]
        else:
            xi=len(g)-1; gain=float(g[xi]); xts=tseg[xi]
        trades.append((fire,gain*PT-COMM)); t_free=xts+cooldown
    return trades

def _metrics(trades):
    if len(trades)<150: return None
    fire=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])
    dt=pd.to_datetime(fire); days=pd.Series(dt).dt.normalize().nunique()
    q=pd.Series(dt).dt.to_period("Q").astype(str)
    fold=pd.DataFrame({"q":q.values,"pnl":pnl,"day":pd.Series(dt).dt.normalize().values})
    fpd=fold.groupby("q").apply(lambda g:g.pnl.sum()/max(1,g.day.nunique()),include_groups=False)
    dpd=fold.groupby("day").pnl.sum()
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max())
    sharpe=float(dpd.mean()/dpd.std()*np.sqrt(252)) if dpd.std()>0 else 0
    return {"n":len(trades),"tr_day":round(len(trades)/days,1),"wr":round(100*(pnl>0).mean(),1),
            "per_day":round(pnl.sum()/days,1),"per_trade":round(pnl.mean(),2),"maxDD":round(dd,0),
            "sharpe":round(sharpe,2),"worst_q":round(float(fpd.min()),1),"n_folds":len(fpd),"pos_folds":int((fpd>0).sum())}

def walk_forward(F, y, ts_ns, quarters, min_train=80000):
    """Expanding-window OOS probabilities. Returns array of P(up), NaN where untrained."""
    proba=np.full(len(F),np.nan)
    uq=sorted(pd.unique(quarters))
    Xall=F.to_numpy("float32")
    for qi,q in enumerate(uq):
        test=quarters==q; train=quarters<q  # strictly before
        if train.sum()<min_train: continue
        clf=HistGradientBoostingClassifier(max_iter=250,max_depth=4,learning_rate=0.05,
                                           l2_regularization=1.0,min_samples_leaf=200,
                                           early_stopping=True,validation_fraction=0.1,random_state=SEED)
        clf.fit(Xall[train],y[train])
        proba[test]=clf.predict_proba(Xall[test])[:,1]
    return proba

def main():
    t0=time.time()
    _init(); print(f"loaded ticks {Z._TS.shape[0]:,}  {time.time()-t0:.0f}s",flush=True)
    bars=Z._BARS
    F=make_features(bars)
    ts_ns=bars.index.to_numpy("datetime64[ns]").astype("int64")
    quarters=pd.PeriodIndex(bars.index,freq="Q").astype(str).to_numpy()
    hr=bars.index.hour+bars.index.minute/60
    rth=(hr>=14.5)&(hr<21.0)
    print(f"features built {F.shape}  {time.time()-t0:.0f}s",flush=True)
    results=[]
    for horizon in (5,15,30):
        ylab,fwd=make_label(bars,horizon)
        valid=F.notna().all(axis=1).to_numpy() & ~np.isnan(fwd.to_numpy()) & rth
        Fv=F[valid]; yv=ylab.to_numpy()[valid]; qv=quarters[valid]; tv=ts_ns[valid]
        print(f"H={horizon}: training walk-forward on {valid.sum():,} RTH bars  {time.time()-t0:.0f}s",flush=True)
        proba=walk_forward(Fv,yv,tv,qv)
        for margin in (0.06,0.10,0.15):
            sigmask=~np.isnan(proba)&((proba>=0.5+margin)|(proba<=0.5-margin))
            det=tv[sigmask]+60*NS
            d=np.where(proba[sigmask]>=0.5,1,-1).astype("int8")
            if len(det)<150:
                print(f"  margin {margin}: only {len(det)} signals, skip",flush=True); continue
            for stop,tgt in [(15.0,30.0),(20.0,40.0),(30.0,60.0)]:
                m=_metrics(simulate(det,d,stop,tgt))
                if not m: continue
                m["name"]=f"ML_H{horizon}m{margin}_S{stop}T{tgt}"; m["horizon"]=horizon; m["margin"]=margin
                results.append(m)
                print(f"  {m['name']}: per_day={m['per_day']} per_tr={m['per_trade']} wr={m['wr']} sharpe={m['sharpe']} worstQ={m['worst_q']} pos={m['pos_folds']}/{m['n_folds']}",flush=True)
    df=pd.DataFrame(results); df.to_csv("research/avenue_ml_results.csv",index=False)
    cols=["name","n","tr_day","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    if len(df):
        print("\n=== ALL by per_day ===")
        print(df.sort_values("per_day",ascending=False)[cols].to_string(index=False))
        robust=df[(df.worst_q>0)&(df.pos_folds==df.n_folds)&(df.sharpe>1)]
        print(f"\n=== profitable EVERY quarter AND sharpe>1: {len(robust)} ===")
        if len(robust): print(robust.sort_values("per_day",ascending=False)[cols].to_string(index=False))

if __name__=="__main__":
    main()

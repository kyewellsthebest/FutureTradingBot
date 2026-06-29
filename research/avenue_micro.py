"""Avenue C: TICK-LEVEL MICROSTRUCTURE.

Signals built from the raw 280M-tick stream, not 1-min bars:
  * OFI proxy  -- tick-rule order-flow imbalance: rolling sum of sign(dPrice)
                  over a short window. Strong positive imbalance => buyers in
                  control. Test both momentum (follow) and reversion (fade).
  * INTENSITY  -- bursts of trade activity (ticks/sec) often precede reversals
                  or continuation; fade/follow a spike.
  * MICRO-REVERSION -- price stretched N pts from a short EMA in M seconds.

We resample the tick stream to fixed time buckets (default 5s) computing, per
bucket: last price, tick count, net tick-sign sum. Signals fire on buckets;
entry/exit use the realistic market sim (delay+misfill+costs).

Run: python -m research.avenue_micro
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import _init, NS, PT, HALF_SPREAD, COMM, STOP_SLIP, SEED, COOLDOWN_S, MAX_HOLD_S

BUCKET_S=5
_FB=None  # feature buckets: dict of arrays

def build_buckets(bucket_s=BUCKET_S):
    """Memory-frugal: no full cumsum. Uses reduceat for per-bucket OFI sum
    and frees big temporaries as we go (4.5GB ticks already resident)."""
    ts=Z._TS; px=Z._PX; n=len(ts)
    b=ts//(bucket_s*NS)                        # bucket id per tick (int64)
    change=np.empty(n,bool); change[0]=True; np.not_equal(b[1:],b[:-1],out=change[1:])
    starts=np.nonzero(change)[0]
    del change, b
    ends=np.empty(len(starts),"int64"); ends[:-1]=starts[1:]; ends[-1]=n
    cnt=(ends-starts).astype("float64")
    last_px=px[ends-1].astype("float64")
    # CRITICAL: a bucket's features (last_px, ofi, cnt) are only known at the
    # bucket's END. Stamp the signal time as the last tick of the bucket so the
    # sim enters AFTER that, never before. Using bucket START = lookahead.
    bts=ts[ends-1].astype("int64")
    sgn=np.sign(np.diff(px,prepend=px[0]))     # tick rule, 280M float
    ofi=np.add.reduceat(sgn,starts).astype("float64")
    del sgn
    return {"ts":bts,"px":last_px,"cnt":cnt,"ofi":ofi}

def _init_micro():
    global _FB
    _init(); _FB=build_buckets()

def sig_ofi(fb, win, thr, follow):
    ofi=pd.Series(fb["ofi"]).rolling(win).sum().to_numpy()
    up=ofi>=thr; dn=ofi<=-thr
    idx=np.where(up|dn)[0]; base=np.where(up[idx],1,-1)
    d=(base*follow).astype("int8")
    return fb["ts"][idx], d

def sig_intensity(fb, win, mult, follow):
    """Fire when bucket count >> its rolling mean; dir = sign of recent move*follow."""
    cnt=fb["cnt"]; m=pd.Series(cnt).rolling(win).mean().to_numpy()
    spike=cnt>mult*m
    ret=np.sign(np.diff(fb["px"], prepend=fb["px"][0]))
    idx=np.where(spike)[0]; idx=idx[ret[idx]!=0]
    d=(ret[idx]*follow).astype("int8")
    return fb["ts"][idx], d

def sig_microrev(fb, ema_n, stretch, follow):
    px=pd.Series(fb["px"]); ema=px.ewm(span=ema_n).mean().to_numpy()
    dev=fb["px"]-ema
    up=dev>=stretch; dn=dev<=-stretch
    idx=np.where(up|dn)[0]
    # stretched up => fade short (follow=-1) by default
    base=np.where(up[idx],-1,1)
    d=(base*follow).astype("int8")
    return fb["ts"][idx], d

def simulate(det_ts, tdir, stop, tgt, seed=SEED):
    ts=Z._TS; px=Z._PX; ntick=len(ts); rng=np.random.default_rng(seed)
    cooldown=COOLDOWN_S*NS; max_hold=MAX_HOLD_S*NS; trades=[]; t_free=ts[0]
    for k in range(len(det_ts)):
        dts=det_ts[k]
        if dts<t_free: continue
        d=int(tdir[k])
        delay=int(rng.uniform(100,800))*1_000_000
        fidx=np.searchsorted(ts,dts+delay,"left")
        if fidx>=ntick: break
        e=float(px[fidx])+d*(HALF_SPREAD+rng.uniform(0,0.5)); fire=ts[fidx]
        hi=np.searchsorted(ts,fire+max_hold,"right"); lo=fidx+1
        if lo>=hi: continue
        seg=px[lo:hi]; tseg=ts[lo:hi]; g=d*(seg-e)
        s_hit=g<=-stop; t_hit=g>=tgt
        ex=s_hit|t_hit
        if ex.any():
            xi=int(np.argmax(ex)); gain=(tgt if (t_hit[xi] and not s_hit[xi]) else -stop-STOP_SLIP); xts=tseg[xi]
        else:
            xi=len(g)-1; gain=float(g[xi]); xts=tseg[xi]
        trades.append((fire,gain*PT-COMM)); t_free=xts+cooldown
    return trades

def _metrics(trades):
    if len(trades)<200: return None
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

def _eval(spec):
    fam=spec[0]
    if fam=="ofi": det,d=sig_ofi(_FB,spec[1],spec[2],spec[3]); stop,tgt=spec[4],spec[5]; name=f"OFI w{spec[1]}t{spec[2]}f{spec[3]}"
    elif fam=="int": det,d=sig_intensity(_FB,spec[1],spec[2],spec[3]); stop,tgt=spec[4],spec[5]; name=f"INT w{spec[1]}x{spec[2]}f{spec[3]}"
    elif fam=="mr": det,d=sig_microrev(_FB,spec[1],spec[2],spec[3]); stop,tgt=spec[4],spec[5]; name=f"MR e{spec[1]}s{spec[2]}f{spec[3]}"
    else: return None
    if len(det)<200: return None
    m=_metrics(simulate(det,d,stop,tgt))
    if not m: return None
    m["name"]=name.replace(" ",""); m["fam"]=fam
    return m

def build_grid():
    g=[]
    for win in (6,12,24):                 # 30s/60s/120s of 5s buckets
        for thr in (8,15,25):
            for f in (1,-1):
                for stop,tgt in [(10.0,20.0),(15.0,30.0),(20.0,40.0)]:
                    g.append(("ofi",win,float(thr),f,stop,tgt))
    for win in (12,60):
        for mult in (3.0,5.0):
            for f in (1,-1):
                for stop,tgt in [(10.0,20.0),(20.0,40.0)]:
                    g.append(("int",win,mult,f,stop,tgt))
    for ema in (12,60):
        for stretch in (5.0,10.0):
            for f in (1,-1):
                for stop,tgt in [(15.0,30.0),(20.0,40.0)]:
                    g.append(("mr",ema,stretch,f,stop,tgt))
    return g

def main():
    t0=time.time(); grid=build_grid()
    print(f"Avenue-C MICRO grid: {len(grid)} configs",flush=True)
    _init();
    global _FB; _FB=build_buckets()
    print(f"loaded {Z._TS.shape[0]:,} ticks, {_FB['ts'].shape[0]:,} buckets  {time.time()-t0:.0f}s",flush=True)
    res=[]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%40==0: print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/avenue_micro_results.csv",index=False)
    cols=["name","fam","n","tr_day","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    print("\n=== TOP 25 by per_day ===")
    print(df.sort_values("per_day",ascending=False).head(25)[cols].to_string(index=False))
    print("\n=== TOP 12 by worst-quarter ===")
    print(df.sort_values("worst_q",ascending=False).head(12)[cols].to_string(index=False))
    robust=df[(df.worst_q>0)&(df.pos_folds==df.n_folds)&(df.sharpe>1)]
    print(f"\n=== profitable EVERY quarter AND sharpe>1: {len(robust)} ===")
    if len(robust): print(robust.sort_values("per_day",ascending=False).head(15)[cols].to_string(index=False))

if __name__=="__main__":
    main()

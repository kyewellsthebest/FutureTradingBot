"""Avenue B: ALTERNATIVE BAR TYPES (Renko / range-grid).

Time bars sample the clock; range/Renko bars sample PRICE MOVEMENT, which
often exposes trend/breakout structure that 1-min bars blur. Built directly
from the sorted tick price array (price-only, vectorizable):

  level = floor(price / R)   -> a "brick" prints whenever the level changes.
  brick direction = sign of the level change; brick time = the crossing tick.

Signals (all stamped at the crossing tick = no lookahead):
  * MOMENTUM  -- after N consecutive same-direction bricks, enter that way.
  * REVERSAL  -- after N consecutive same-direction bricks, fade.
Executed through the realistic market sim (delay+misfill+costs), per-quarter
walk-forward gate.

Run: python -m research.avenue_bars
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import _init, NS, PT, HALF_SPREAD, COMM, STOP_SLIP, SEED, COOLDOWN_S, MAX_HOLD_S

_BRK={}  # R -> (ts[], dir[]) brick series cache (per process)

def build_bricks(R):
    px=Z._PX; ts=Z._TS
    lvl=np.floor(px/R).astype("int64")
    d=np.diff(lvl)
    idx=np.nonzero(d!=0)[0]+1
    bdir=np.sign(d[idx-1]).astype("int8")     # +1 up brick, -1 down
    bts=ts[idx].astype("int64")
    return bts, bdir

def _bricks(R):
    if R not in _BRK: _BRK[R]=build_bricks(R)
    return _BRK[R]

def sig_renko(R, N, follow):
    """After N consecutive same-direction bricks, trade follow*dir."""
    bts,bdir=_bricks(R)
    if len(bdir)<N+1: return np.empty(0,"int64"),np.empty(0,"int8")
    # run-length: count consecutive same dir ending at i
    same=(bdir[1:]==bdir[:-1])
    run=np.ones(len(bdir),"int32")
    for i in range(1,len(bdir)):       # cheap: brick count << ticks
        if same[i-1]: run[i]=run[i-1]+1
    fire=np.where(run>=N)[0]
    # only fire at the FIRST bar that reaches the run (avoid every-bar spam)
    fire=fire[(run[fire]==N)]
    d=(bdir[fire]*follow).astype("int8")
    return bts[fire], d

def simulate(det_ts, tdir, stop, tgt, seed=SEED):
    ts=Z._TS; px=Z._PX; ntick=len(ts); rng=np.random.default_rng(seed)
    cooldown=COOLDOWN_S*NS; max_hold=MAX_HOLD_S*NS; trades=[]; t_free=ts[0]
    order=np.argsort(det_ts); det_ts=det_ts[order]; tdir=tdir[order]
    for k in range(len(det_ts)):
        dts=int(det_ts[k])
        if dts<t_free: continue
        d=int(tdir[k])
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
    R,N,follow,stop,tgt=spec
    det,d=sig_renko(R,N,follow)
    if len(det)<200: return None
    m=_metrics(simulate(det,d,stop,tgt))
    if not m: return None
    m["name"]=f"RENKO R{R}N{N}{'mom' if follow==1 else 'rev'}_S{stop}T{tgt}"
    return m

def build_grid():
    g=[]
    for R in (2.0,3.0,5.0,10.0):
        for N in (2,3,4):
            for follow in (1,-1):
                for stop,tgt in [(10.0,20.0),(15.0,30.0),(20.0,40.0),(30.0,60.0)]:
                    g.append((R,N,follow,stop,tgt))
    return g

def main():
    t0=time.time(); grid=build_grid()
    print(f"Avenue-B BARS grid: {len(grid)} configs",flush=True)
    _init(); print(f"loaded {Z._TS.shape[0]:,} ticks  {time.time()-t0:.0f}s",flush=True)
    # warm brick caches in parent so workers inherit them
    for R in (2.0,3.0,5.0,10.0):
        bts,bd=_bricks(R); print(f"  R={R}: {len(bd):,} bricks",flush=True)
    res=[]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%30==0: print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/avenue_bars_results.csv",index=False)
    cols=["name","n","tr_day","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    print("\n=== TOP 20 by per_day ===")
    print(df.sort_values("per_day",ascending=False).head(20)[cols].to_string(index=False))
    print("\n=== TOP 10 by worst-quarter ===")
    print(df.sort_values("worst_q",ascending=False).head(10)[cols].to_string(index=False))
    robust=df[(df.worst_q>0)&(df.pos_folds==df.n_folds)&(df.sharpe>1)]
    print(f"\n=== profitable EVERY quarter AND sharpe>1: {len(robust)} ===")
    if len(robust): print(robust.sort_values("per_day",ascending=False)[cols].to_string(index=False))

if __name__=="__main__":
    main()

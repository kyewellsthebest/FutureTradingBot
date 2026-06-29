"""Fill-aware strategy ZOO on 2.75 years of real NQ ticks (280M trades).

Every strategy here:
  * ENTERS AT MARKET on a bar signal (always fillable; no limit-sniping
    fantasy). Paper == broker by construction.
  * Pays REALISTIC costs: half-spread on entry, +random adverse misfill,
    a RANDOM entry delay (100-800ms) so the fill lands at the real price a
    moment later, 1.3pt stop slip, $0.74/RT commission, $2/pt.
  * Uses WIDE stops so a few pts of delay/misfill is noise, not fatal.

Only strategies that stay profitable ACROSS every half-year fold (walk-
forward) AND survive the random misfill get surfaced. Families tested:
momentum, fade, MA-cross, opening-range breakout, z-score reversion.

Run: python -m research.tick_zoo_2p5y
"""
from __future__ import annotations
import itertools, time, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
import pyarrow.parquet as pq

TICKS_F = "data/tick/nq_ticks_2p5y.parquet"
BARS_F  = "data/tick/nq_bars_1m_2p5y.parquet"
NS = 1_000_000_000
PT = 2.0
HALF_SPREAD = 0.125      # NQ ~1-tick spread
COMM = 0.74
STOP_SLIP = 1.3
COOLDOWN_S = 60
MAX_HOLD_S = 600
SEED = 7

_TS=None; _PX=None; _BARS=None

def _init():
    global _TS,_PX,_BARS
    t = pq.read_table(TICKS_F, columns=["ts","price"])
    _TS = t.column("ts").to_numpy()
    _PX = t.column("price").to_numpy().astype("float64")
    _BARS = pd.read_parquet(BARS_F)

# ---------- signal families: each returns (det_ts_ns[], trade_dir[+1/-1]) ----------
def sig_impulse(bars, imp, W, invert):
    o=bars["open"].to_numpy(); c=bars["close"].to_numpy()
    st=bars.index.to_numpy("datetime64[ns]").astype("int64"); n=len(bars)
    net=c[W-1:]-o[:n-W+1]; idx=np.arange(W-1,n)
    keep=np.abs(net)>=imp
    idx=idx[keep]; up=net[keep]>0
    long_ = ~up if invert else up
    return st[idx]+60*NS, np.where(long_,1,-1).astype("int8")

def sig_macross(bars, fast, slow):
    c=pd.Series(bars["close"].to_numpy())
    mf=c.rolling(fast).mean(); ms=c.rolling(slow).mean()
    cross=np.sign(mf-ms).diff()           # +2 up-cross, -2 down-cross
    st=bars.index.to_numpy("datetime64[ns]").astype("int64")
    up=np.where(cross.to_numpy()>0)[0]; dn=np.where(cross.to_numpy()<0)[0]
    idx=np.concatenate([up,dn]); dirs=np.concatenate([np.ones(len(up)),-np.ones(len(dn))])
    order=np.argsort(idx)
    return st[idx[order]]+60*NS, dirs[order].astype("int8")

def sig_orb(bars, oh, ob_min, brk):
    """Opening-range breakout: break of first ob_min mins after 14:30 UTC."""
    df=bars.copy(); df["h"]=df.index.hour+df.index.minute/60
    st=df.index.to_numpy("datetime64[ns]").astype("int64")
    hi=df["high"].to_numpy(); lo=df["low"].to_numpy(); cl=df["close"].to_numpy()
    day=df.index.normalize().to_numpy()
    out_ts=[]; out_dir=[]
    open_h=14.5
    for d in np.unique(day):
        m=(day==d)&(df["h"].to_numpy()>=open_h)&(df["h"].to_numpy()<open_h+ob_min/60)
        if m.sum()<2: continue
        orh=hi[m].max(); orl=lo[m].min()
        after=(day==d)&(df["h"].to_numpy()>=open_h+ob_min/60)&(df["h"].to_numpy()<21.0)
        ai=np.where(after)[0]
        for i in ai:
            if cl[i]>orh+brk: out_ts.append(st[i]+60*NS); out_dir.append(1); break
            if cl[i]<orl-brk: out_ts.append(st[i]+60*NS); out_dir.append(-1); break
    return np.array(out_ts,dtype="int64"), np.array(out_dir,dtype="int8")

def sig_zscore(bars, lb, z, invert):
    c=pd.Series(bars["close"].to_numpy())
    m=c.rolling(lb).mean(); sd=c.rolling(lb).std()
    zs=((c-m)/sd).to_numpy()
    st=bars.index.to_numpy("datetime64[ns]").astype("int64")
    hi=np.where(zs>=z)[0]; loi=np.where(zs<=-z)[0]
    # z high => price stretched up => fade short (invert) / momentum long
    dir_hi = -1 if invert else 1
    idx=np.concatenate([hi,loi]); dirs=np.concatenate([np.full(len(hi),dir_hi),np.full(len(loi),-dir_hi)])
    order=np.argsort(idx)
    return st[idx[order]]+60*NS, dirs[order].astype("int8")

# ---------- market-entry sim with random delay + misfill ----------
def simulate(det_ts, tdir, stop, tgt, seed=SEED):
    ts=_TS; px=_PX; ntick=len(ts)
    rng=np.random.default_rng(seed)
    cooldown=COOLDOWN_S*NS; max_hold=MAX_HOLD_S*NS
    trades=[]; t_free=ts[0]
    for k in range(len(det_ts)):
        dts=det_ts[k]
        if dts<t_free: continue
        d=int(tdir[k])
        # random entry delay 100-800ms -> fill at the real price then
        delay=int(rng.uniform(100,800))*1_000_000
        fidx=np.searchsorted(ts,dts+delay,"left")
        if fidx>=ntick: break
        # market fill: pay half-spread + random adverse misfill 0..0.5pt
        misfill=rng.uniform(0,0.5)
        e=float(px[fidx])+d*(HALF_SPREAD+misfill)
        fire=ts[fidx]
        s_px=e-d*stop; t_px=e+d*tgt
        hi=np.searchsorted(ts,fire+max_hold,"right"); lo=fidx+1
        if lo>=hi: continue
        seg=px[lo:hi]; tseg=ts[lo:hi]
        if d==1:
            stop_hit=seg<=s_px; tgt_hit=seg>=t_px
        else:
            stop_hit=seg>=s_px; tgt_hit=seg<=t_px
        ex=stop_hit|tgt_hit
        if ex.any():
            xi=int(np.argmax(ex)); xts=tseg[xi]
            if stop_hit[xi]:
                reason="stop"; xpx=s_px-d*STOP_SLIP
            else:
                reason="target"; xpx=t_px
        else:
            xi=len(tseg)-1; xts=tseg[xi]; reason="timeout"; xpx=float(seg[xi])
        pnl=d*(xpx-e)*PT-COMM
        trades.append((fire,pnl,reason)); t_free=xts+cooldown
    return trades

def _metrics(trades):
    if len(trades)<200: return None
    fire=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])
    dt=pd.to_datetime(fire)
    days=pd.Series(dt).dt.normalize().nunique()
    # half-year folds
    period=pd.Series(dt).dt.to_period("Q").astype(str)
    fold=pd.DataFrame({"p":period.values,"pnl":pnl,"day":pd.Series(dt).dt.normalize().values})
    fpd=fold.groupby("p").apply(lambda g: g.pnl.sum()/max(1,g.day.nunique()), include_groups=False)
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max())
    dpd=fold.groupby("day").pnl.sum()
    sharpe=float(dpd.mean()/dpd.std()*np.sqrt(252)) if dpd.std()>0 else 0
    return {"n":len(trades),"tr_day":round(len(trades)/days,1),
            "wr":round(100*(pnl>0).mean(),1),"per_day":round(pnl.sum()/days,1),
            "per_trade":round(pnl.mean(),2),"maxDD":round(dd,0),"sharpe":round(sharpe,2),
            "worst_q":round(float(fpd.min()),1),"n_folds":len(fpd),"pos_folds":int((fpd>0).sum())}

def _eval(spec):
    fam=spec[0]
    if fam=="imp": det,dr=sig_impulse(_BARS,spec[1],spec[2],spec[3]); stop,tgt=spec[4],spec[5]; name=f"{'FADE' if spec[3] else 'MOM'}_imp{spec[1]}w{spec[2]}_s{spec[4]}t{spec[5]}"
    elif fam=="ma": det,dr=sig_macross(_BARS,spec[1],spec[2]); stop,tgt=spec[3],spec[4]; name=f"MA{spec[1]}x{spec[2]}_s{spec[3]}t{spec[4]}"
    elif fam=="orb": det,dr=sig_orb(_BARS,0,spec[1],spec[2]); stop,tgt=spec[3],spec[4]; name=f"ORB{spec[1]}b{spec[2]}_s{spec[3]}t{spec[4]}"
    elif fam=="zs": det,dr=sig_zscore(_BARS,spec[1],spec[2],spec[3]); stop,tgt=spec[4],spec[5]; name=f"{'ZFADE' if spec[3] else 'ZMOM'}{spec[1]}z{spec[2]}_s{spec[4]}t{spec[5]}"
    else: return None
    if len(det)<200: return None
    m=_metrics(simulate(det,dr,stop,tgt))
    if not m: return None
    m["name"]=name; m["fam"]=fam
    return m

def build_grid():
    g=[]
    for inv in (True,False):
        for imp in (5,8,12):
            for W in (3,5):
                for s in (10,15,20):
                    for t in (15,25,40):
                        g.append(("imp",imp,W,inv,float(s),float(t)))
    for f,sl in [(5,20),(9,30),(20,60),(10,50)]:
        for s in (10,15,20):
            for t in (20,40):
                g.append(("ma",f,sl,float(s),float(t)))
    for ob in (15,30,60):
        for brk in (1.0,3.0):
            for s in (10,15,20):
                for t in (20,40):
                    g.append(("orb",ob,brk,float(s),float(t)))
    for inv in (True,False):
        for lb in (20,60):
            for z in (2.0,3.0):
                for s in (10,15):
                    for t in (20,40):
                        g.append(("zs",lb,z,inv,float(s),float(t)))
    return g

def main():
    t0=time.time(); grid=build_grid()
    print(f"ZOO grid: {len(grid)} configs on 280M ticks, 2.75yr",flush=True)
    _init()
    print(f"loaded {_TS.shape[0]:,} ticks, {len(_BARS):,} bars  {time.time()-t0:.0f}s",flush=True)
    res=[]
    # NO initializer: children fork() and inherit _TS/_PX/_BARS via copy-on-write.
    # searchsorted is read-only so the ~4.5GB arrays are never copied. Loading
    # per-worker instead would be 4x that = OOM on a 15GB box.
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%40==0: print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/tick_zoo_2p5y_results.csv",index=False)
    pd.set_option("display.width",240,"display.max_columns",40)
    cols=["name","fam","n","tr_day","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    print("\n=== TOP 20 by worst-quarter $/day (regime-robust) ===")
    print(df.sort_values("worst_q",ascending=False).head(20)[cols].to_string(index=False))
    robust=df[(df.worst_q>0)&(df.pos_folds==df.n_folds)&(df.sharpe>1)]
    print(f"\n=== profitable EVERY quarter AND sharpe>1: {len(robust)} ===")
    if len(robust): print(robust.sort_values("per_day",ascending=False).head(15)[cols].to_string(index=False))

if __name__=="__main__":
    main()

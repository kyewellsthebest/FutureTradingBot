"""Avenue D: CALENDAR / SEASONALITY + VOLATILITY REGIMES.

Edges that aren't price-patterns at all:
  * Hour-of-day directional drift  (e.g. long the US open, short the close)
  * Day-of-week bias
  * Overnight gap follow / fade
  * Volatility-regime breakout (ATR / NR7 style)
All with the SAME realistic market-entry costs and per-quarter walk-forward.
Holds can be hours, so this sim takes an explicit hold horizon.

Run: python -m research.avenue_seasonality
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import _init, NS, PT, HALF_SPREAD, COMM, STOP_SLIP, SEED

def sim_hold(det_ts, tdir, hold_s, stop, tgt, seed=SEED):
    """Market entry, exit at min(stop, target, hold horizon)."""
    ts=Z._TS; px=Z._PX; ntick=len(ts); rng=np.random.default_rng(seed)
    hold=int(hold_s)*NS; trades=[]; t_free=ts[0]
    for k in range(len(det_ts)):
        dts=det_ts[k]
        if dts<t_free: continue
        d=int(tdir[k])
        delay=int(rng.uniform(100,800))*1_000_000
        fidx=np.searchsorted(ts,dts+delay,"left")
        if fidx>=ntick: break
        e=float(px[fidx])+d*(HALF_SPREAD+rng.uniform(0,0.5)); fire=ts[fidx]
        hi=np.searchsorted(ts,fire+hold,"right"); lo=fidx+1
        if lo>=hi: continue
        seg=px[lo:hi]; tseg=ts[lo:hi]; g=d*(seg-e)
        s_hit=g<=-stop if stop>0 else np.zeros(len(g),bool)
        t_hit=g>=tgt if tgt>0 else np.zeros(len(g),bool)
        ex=s_hit|t_hit
        if ex.any():
            xi=int(np.argmax(ex)); gain=(tgt if (t_hit[xi] and not s_hit[xi]) else -stop-STOP_SLIP); xts=tseg[xi]
        else:
            xi=len(g)-1; gain=float(g[xi]); xts=tseg[xi]
        trades.append((fire,gain*PT-COMM)); t_free=xts
    return trades

def _metrics(trades,min_n=150):
    if len(trades)<min_n: return None
    fire=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])
    dt=pd.to_datetime(fire); days=pd.Series(dt).dt.normalize().nunique()
    q=pd.Series(dt).dt.to_period("Q").astype(str)
    fold=pd.DataFrame({"q":q.values,"pnl":pnl,"day":pd.Series(dt).dt.normalize().values})
    fpd=fold.groupby("q").apply(lambda g:g.pnl.sum()/max(1,g.day.nunique()),include_groups=False)
    dpd=fold.groupby("day").pnl.sum()
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max())
    sharpe=float(dpd.mean()/dpd.std()*np.sqrt(252)) if dpd.std()>0 else 0
    return {"n":len(trades),"wr":round(100*(pnl>0).mean(),1),"per_day":round(pnl.sum()/days,1),
            "per_trade":round(pnl.mean(),2),"maxDD":round(dd,0),"sharpe":round(sharpe,2),
            "worst_q":round(float(fpd.min()),1),"n_folds":len(fpd),"pos_folds":int((fpd>0).sum())}

def _daily_open_ts(bars):
    st=bars.index.to_numpy("datetime64[ns]").astype("int64")
    h=(bars.index.hour+bars.index.minute/60).to_numpy()
    day=bars.index.normalize().to_numpy()
    o=bars["open"].to_numpy(); c=bars["close"].to_numpy(); hi=bars["high"].to_numpy(); lo=bars["low"].to_numpy()
    return st,h,day,o,c,hi,lo

def sig_hour(bars, H, d):
    """Enter dir d at the bar nearest hour H (UTC) each trading day."""
    st,h,day,*_=_daily_open_ts(bars)
    out=[]
    for dd in np.unique(day):
        m=(day==dd)&(h>=H)&(h<H+0.25)
        idx=np.where(m)[0]
        if len(idx): out.append(st[idx[0]])
    out=np.array(out,dtype="int64")
    return out, np.full(len(out),d,dtype="int8")

def sig_gap(bars, thr, follow):
    """Overnight gap: compare today's first RTH (14.5) bar open vs prior day
    last (20.75) close. follow=1 trade gap direction, -1 fade it."""
    st,h,day,o,c,*_=_daily_open_ts(bars)
    days=np.unique(day); out=[]; dirs=[]
    prev_close=None
    for dd in days:
        rth=np.where((day==dd)&(h>=14.5)&(h<14.75))[0]
        eod=np.where((day==dd)&(h>=20.5)&(h<21.0))[0]
        if len(rth) and prev_close is not None:
            gap=o[rth[0]]-prev_close
            if abs(gap)>=thr:
                g=1 if gap>0 else -1
                out.append(st[rth[0]]); dirs.append(g*follow)
        if len(eod): prev_close=c[eod[-1]]
    return np.array(out,dtype="int64"), np.array(dirs,dtype="int8")

def sig_volbreak(bars, lb, k, rth_only):
    """ATR-style: enter on close breaking prior-close +/- k*ATR(lb)."""
    c=bars["close"].to_numpy(); hi=bars["high"].to_numpy(); lo=bars["low"].to_numpy()
    st=bars.index.to_numpy("datetime64[ns]").astype("int64")
    h=(bars.index.hour+bars.index.minute/60).to_numpy()
    tr=np.maximum(hi-lo,np.abs(np.concatenate([[0],np.diff(c)])))
    atr=pd.Series(tr).rolling(lb).mean().to_numpy()
    up=c>(np.concatenate([[np.nan],c[:-1]])+k*atr); dn=c<(np.concatenate([[np.nan],c[:-1]])-k*atr)
    idx=np.where(up|dn)[0]; d=np.where(up[idx],1,-1).astype("int8")
    if rth_only:
        keep=(h[idx]>=14.5)&(h[idx]<21.0); idx=idx[keep]; d=d[keep]
    return st[idx]+60*NS, d

def _eval(spec):
    fam=spec[0]
    if fam=="hour": det,d=sig_hour(Z._BARS,spec[1],spec[2]); hold,stop,tgt=spec[3],spec[4],spec[5]; name=f"HOUR{spec[1]}d{spec[2]}h{spec[3]}"
    elif fam=="gap": det,d=sig_gap(Z._BARS,spec[1],spec[2]); hold,stop,tgt=spec[3],spec[4],spec[5]; name=f"GAP{spec[1]}f{spec[2]}h{spec[3]}"
    elif fam=="vol": det,d=sig_volbreak(Z._BARS,spec[1],spec[2],spec[3]); hold,stop,tgt=spec[4],spec[5],spec[6]; name=f"VOL{spec[1]}k{spec[2]}r{int(spec[3])}h{spec[4]}"
    else: return None
    if len(det)<120: return None
    m=_metrics(sim_hold(det,d,hold,stop,tgt))
    if not m: return None
    m["name"]=name; m["fam"]=fam
    return m

def build_grid():
    g=[]
    for H in [13.5,14.5,15.0,15.5,19.0,20.0]:
        for d in (1,-1):
            for hold in (3600,7200,21600):
                for stop,tgt in [(20.0,40.0),(30.0,60.0),(0.0,0.0)]:
                    g.append(("hour",H,d,hold,stop,tgt))
    for thr in (10.0,25.0,50.0):
        for follow in (1,-1):
            for hold in (3600,7200,21600):
                for stop,tgt in [(20.0,40.0),(30.0,60.0)]:
                    g.append(("gap",thr,follow,hold,stop,tgt))
    for lb in (14,30):
        for k in (1.5,2.5):
            for rth in (True,False):
                for hold in (1800,3600):
                    for stop,tgt in [(20.0,40.0),(30.0,60.0)]:
                        g.append(("vol",lb,k,rth,hold,stop,tgt))
    return g

def main():
    t0=time.time(); grid=build_grid()
    print(f"Avenue-D SEASONALITY grid: {len(grid)} configs",flush=True)
    _init(); print(f"loaded {Z._TS.shape[0]:,} ticks  {time.time()-t0:.0f}s",flush=True)
    res=[]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%50==0: print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/avenue_seasonality_results.csv",index=False)
    cols=["name","fam","n","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
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

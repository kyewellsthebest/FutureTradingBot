"""Zoo v2: add the highest-value filters to carve edge from a ~zero-edge base.

v1 proved raw signal edge ~= 0 (best per-trade -$1.51 vs ~$2.5 cost drag).
v2 keeps the SAME market-entry sim + real costs + per-quarter walk-forward
gate, but adds:
  * SESSION filter  -- trade only inside chosen UTC hour windows (e.g. RTH).
  * HTF TREND filter -- only take trades aligned with a slow MA slope.
  * Larger targets / wider stops to dilute fixed cost per trade.
Families: impulse (mom/fade), z-score (mom/fade), MA-cross, plus a
wide-target trend-follower. Reuses simulate()/_metrics() from v1.

Run: python -m research.tick_zoo_v2
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from research.tick_zoo_2p5y import (_init, simulate, _metrics, sig_impulse,
                                    sig_zscore, sig_macross, NS)
import research.tick_zoo_2p5y as Z

# ---- filters operate on (det_ts_ns, dir) using the bars index for context ----
def _bar_ctx(bars):
    idx = bars.index
    hour = (idx.hour + idx.minute/60).to_numpy()
    st = idx.to_numpy("datetime64[ns]").astype("int64")
    c = bars["close"].to_numpy()
    return st, hour, c

def _apply_session(det_ts, d, st, hour, lo_h, hi_h):
    # map each det_ts (= bar_st+60s) back to its bar hour
    pos = np.searchsorted(st, det_ts-60*NS, "left")
    pos = np.clip(pos, 0, len(hour)-1)
    h = hour[pos]
    keep = (h>=lo_h)&(h<hi_h)
    return det_ts[keep], d[keep]

def _apply_trend(det_ts, d, st, c, slow, align):
    """align=+1 keep only trades whose dir matches slow-MA slope sign;
       align=-1 keep only counter-trend; align=0 no filter."""
    if align==0: return det_ts, d
    ma = pd.Series(c).rolling(slow).mean().to_numpy()
    slope = np.sign(np.concatenate([[0], np.diff(ma)]))
    pos = np.searchsorted(st, det_ts-60*NS, "left"); pos=np.clip(pos,0,len(c)-1)
    sl = slope[pos]
    keep = (d==sl) if align==1 else (d==-sl)
    return det_ts[keep], d[keep]

def sig_trendfollow(bars, slow, brk):
    """Enter in direction of slow-MA slope when price breaks N pts beyond MA."""
    c=bars["close"].to_numpy(); st=bars.index.to_numpy("datetime64[ns]").astype("int64")
    ma=pd.Series(c).rolling(slow).mean().to_numpy()
    slope=np.sign(np.concatenate([[0],np.diff(ma)]))
    up=(c>ma+brk)&(slope>0); dn=(c<ma-brk)&(slope<0)
    idx=np.where(up|dn)[0]
    d=np.where(up[idx],1,-1).astype("int8")
    return st[idx]+60*NS, d

def _eval(spec):
    st,hour,c = Z._BARS_CTX
    fam=spec[0]
    if fam=="imp":
        _,imp,W,inv,stop,tgt,sess,align,slow=spec
        det,d=sig_impulse(Z._BARS,imp,W,inv); name=f"{'FADE' if inv else 'MOM'}{imp}w{W}"
    elif fam=="zs":
        _,lb,z,inv,stop,tgt,sess,align,slow=spec
        det,d=sig_zscore(Z._BARS,lb,z,inv); name=f"{'ZFADE' if inv else 'ZMOM'}{lb}z{z}"
    elif fam=="ma":
        _,f,sl,stop,tgt,sess,align,slow=spec
        det,d=sig_macross(Z._BARS,f,sl); name=f"MA{f}x{sl}"
    elif fam=="tf":
        _,slowp,brk,stop,tgt,sess,align,slow=spec
        det,d=sig_trendfollow(Z._BARS,slowp,brk); name=f"TF{slowp}b{brk}"
    else: return None
    if sess: det,d=_apply_session(det,d,st,hour,sess[0],sess[1]); name+=f"_s{sess[0]}-{sess[1]}"
    if align: det,d=_apply_trend(det,d,st,c,slow,align); name+=f"_{'with' if align==1 else 'anti'}{slow}"
    name+=f"_S{stop}T{tgt}"
    if len(det)<200: return None
    m=_metrics(simulate(det,d,stop,tgt))
    if not m: return None
    m["name"]=name; m["fam"]=fam
    return m

def build_grid():
    g=[]
    SESS=[None,(14.5,21.0),(14.5,16.0),(13.0,15.0)]   # all / RTH / open-90m / EU-US overlap
    ALIGN=[0,1,-1]
    for sess in SESS:
        for align in ALIGN:
            for stop,tgt in [(15.0,30.0),(20.0,40.0),(20.0,60.0),(30.0,60.0)]:
                for inv in (True,False):
                    for imp in (5,8):
                        g.append(("imp",imp,3,inv,stop,tgt,sess,align,50))
                    for lb,z in [(20,2.0),(60,2.0),(60,3.0)]:
                        g.append(("zs",lb,z,inv,stop,tgt,sess,align,50))
                g.append(("ma",9,30,stop,tgt,sess,align,50))
                g.append(("ma",20,60,stop,tgt,sess,align,50))
                for slowp,brk in [(60,5.0),(120,8.0)]:
                    g.append(("tf",slowp,brk,stop,tgt,sess,align,slowp))
    return g

def _worker_init():
    _init()
    Z._BARS_CTX=_bar_ctx(Z._BARS)

def main():
    t0=time.time(); grid=build_grid()
    print(f"ZOO v2 grid: {len(grid)} configs",flush=True)
    _init(); Z._BARS_CTX=_bar_ctx(Z._BARS)
    print(f"loaded {Z._TS.shape[0]:,} ticks  {time.time()-t0:.0f}s",flush=True)
    res=[]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=2)):
            if r: res.append(r)
            if (i+1)%60==0: print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/tick_zoo_v2_results.csv",index=False)
    cols=["name","fam","n","tr_day","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs evaluated")
    print("\n=== TOP 20 by per_day ===")
    print(df.sort_values("per_day",ascending=False).head(20)[cols].to_string(index=False))
    print("\n=== TOP 10 by worst-quarter ===")
    print(df.sort_values("worst_q",ascending=False).head(10)[cols].to_string(index=False))
    robust=df[(df.worst_q>0)&(df.pos_folds==df.n_folds)&(df.sharpe>1)]
    print(f"\n=== profitable EVERY quarter AND sharpe>1: {len(robust)} ===")
    if len(robust): print(robust.sort_values("per_day",ascending=False).head(15)[cols].to_string(index=False))

if __name__=="__main__":
    main()

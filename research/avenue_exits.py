"""Avenue A: EXIT ENGINEERING.

A signal with ~zero directional edge can still be profitable with the right
exit: a trailing stop rides trends, a breakeven move cuts losers to scratch,
a time stop dodges chop. v1/v2 only used fixed stop+target. Here we keep the
same realistic market-entry costs but explore advanced exits, vectorized so
the whole 2.75yr runs fast.

Exit modes (all long-described; short is mirrored):
  fixed   : stop=e-S,  target=e+T                       (baseline)
  trail   : trailing stop T pts below running max, optional target cap
  be      : stop=e-S until price hits e+B, then stop=e   (breakeven), target=e+T
  trailbe : breakeven AND trailing combined
plus a hard time stop (MAX_HOLD_S) on every mode.

Run: python -m research.avenue_exits
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
import research.tick_zoo_2p5y as Z
from research.tick_zoo_2p5y import (_init, _metrics, sig_impulse, sig_zscore,
                                    sig_macross, NS, PT, HALF_SPREAD, COMM,
                                    STOP_SLIP, COOLDOWN_S, MAX_HOLD_S, SEED)
from research.tick_zoo_v2 import (_bar_ctx, _apply_session, _apply_trend,
                                  sig_trendfollow)

def simulate_adv(det_ts, tdir, mode, S, T, B, trail, seed=SEED):
    """Advanced-exit market sim. S=stop pts, T=target pts (0=>none),
    B=breakeven trigger pts (0=>off), trail=trailing dist pts (0=>off)."""
    ts=Z._TS; px=Z._PX; ntick=len(ts)
    rng=np.random.default_rng(seed)
    cooldown=COOLDOWN_S*NS; max_hold=MAX_HOLD_S*NS
    trades=[]; t_free=ts[0]
    INF=1e18
    for k in range(len(det_ts)):
        dts=det_ts[k]
        if dts<t_free: continue
        d=int(tdir[k])
        delay=int(rng.uniform(100,800))*1_000_000
        fidx=np.searchsorted(ts,dts+delay,"left")
        if fidx>=ntick: break
        misfill=rng.uniform(0,0.5)
        e=float(px[fidx])+d*(HALF_SPREAD+misfill)
        fire=ts[fidx]
        hi=np.searchsorted(ts,fire+max_hold,"right"); lo=fidx+1
        if lo>=hi: continue
        seg=px[lo:hi]; tseg=ts[lo:hi]
        # work in "favorable" coordinates: g = signed gain in pts from entry
        g=d*(seg-e)
        run_max=np.maximum.accumulate(g)         # best favorable excursion so far
        # base stop level in gain-space (negative)
        base=np.full(len(g),-S)
        if B>0:
            be_active=run_max>=B
            base=np.where(be_active,0.0,-S)       # move stop to breakeven
        stop_lvl=base
        if trail>0:
            stop_lvl=np.maximum(stop_lvl,run_max-trail)  # trail only tightens
        stop_hit=g<=stop_lvl
        tgt_hit=g>=T if T>0 else np.zeros(len(g),bool)
        ex=stop_hit|tgt_hit
        if ex.any():
            xi=int(np.argmax(ex))
            if tgt_hit[xi] and (not stop_hit[xi]):
                gain=T
            else:
                gain=float(stop_lvl[xi])-STOP_SLIP   # slip through the stop
            xts=tseg[xi]
        else:
            xi=len(g)-1; gain=float(g[xi]); xts=tseg[xi]
        pnl=gain*PT-COMM
        trades.append((fire,pnl)); t_free=xts+cooldown
    return trades

def _metrics2(trades):
    if len(trades)<200: return None
    fire=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])
    dt=pd.to_datetime(fire); days=pd.Series(dt).dt.normalize().nunique()
    q=pd.Series(dt).dt.to_period("Q").astype(str)
    fold=pd.DataFrame({"q":q.values,"pnl":pnl,"day":pd.Series(dt).dt.normalize().values})
    fpd=fold.groupby("q").apply(lambda g:g.pnl.sum()/max(1,g.day.nunique()),include_groups=False)
    dpd=fold.groupby("day").pnl.sum()
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max())
    sharpe=float(dpd.mean()/dpd.std()*np.sqrt(252)) if dpd.std()>0 else 0
    return {"n":len(trades),"tr_day":round(len(trades)/days,1),
            "wr":round(100*(pnl>0).mean(),1),"per_day":round(pnl.sum()/days,1),
            "per_trade":round(pnl.mean(),2),"maxDD":round(dd,0),"sharpe":round(sharpe,2),
            "worst_q":round(float(fpd.min()),1),"n_folds":len(fpd),"pos_folds":int((fpd>0).sum())}

def _eval(spec):
    st,hour,c=Z._BARS_CTX
    fam,sig_args,sess,align,slow,mode,S,T,B,trail=spec
    if fam=="imp": det,d=sig_impulse(Z._BARS,*sig_args); base=f"{'FADE' if sig_args[2] else 'MOM'}{sig_args[0]}w{sig_args[1]}"
    elif fam=="zs": det,d=sig_zscore(Z._BARS,*sig_args); base=f"{'ZFADE' if sig_args[2] else 'ZMOM'}{sig_args[0]}z{sig_args[1]}"
    elif fam=="ma": det,d=sig_macross(Z._BARS,*sig_args); base=f"MA{sig_args[0]}x{sig_args[1]}"
    elif fam=="tf": det,d=sig_trendfollow(Z._BARS,*sig_args); base=f"TF{sig_args[0]}b{sig_args[1]}"
    else: return None
    if sess: det,d=_apply_session(det,d,st,hour,sess[0],sess[1]); base+=f"_s{sess[0]}-{sess[1]}"
    if align: det,d=_apply_trend(det,d,st,c,slow,align); base+=f"_{'w' if align==1 else 'a'}{slow}"
    if len(det)<200: return None
    name=f"{base}_{mode}S{S}T{T}B{B}tr{trail}"
    m=_metrics2(simulate_adv(det,d,mode,S,T,B,trail))
    if not m: return None
    m["name"]=name; m["fam"]=fam; m["mode"]=mode
    return m

def build_grid():
    g=[]
    sigs=[("imp",(5,3,True)),("imp",(8,3,True)),("imp",(5,3,False)),("imp",(8,3,False)),
          ("zs",(20,2.0,True)),("zs",(60,2.0,True)),("zs",(60,3.0,False)),
          ("ma",(9,30)),("ma",(20,60)),("tf",(60,5.0)),("tf",(120,8.0))]
    SESS=[None,(14.5,21.0),(14.5,16.0)]
    ALIGN=[0,1,-1]
    # exit modes: (mode,S,T,B,trail)
    EXITS=[("trail",30,0,0,8),("trail",30,0,0,15),("trail",40,0,0,20),
           ("trail",30,60,0,12),("be",20,40,10,0),("be",30,60,15,0),
           ("trailbe",30,0,12,15),("trailbe",40,80,15,20),
           ("fixed",20,40,0,0),("fixed",30,60,0,0)]
    for fam,sa in sigs:
        for sess in SESS:
            for align in ALIGN:
                slow=50 if fam not in("tf",) else sa[0]
                for (mode,S,T,B,trail) in EXITS:
                    g.append((fam,sa,sess,align,slow,mode,float(S),float(T),float(B),float(trail)))
    return g

def main():
    t0=time.time(); grid=build_grid()
    print(f"Avenue-A EXITS grid: {len(grid)} configs",flush=True)
    _init(); Z._BARS_CTX=_bar_ctx(Z._BARS)
    print(f"loaded {Z._TS.shape[0]:,} ticks  {time.time()-t0:.0f}s",flush=True)
    res=[]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=4)):
            if r: res.append(r)
            if (i+1)%100==0: print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/avenue_exits_results.csv",index=False)
    cols=["name","fam","mode","n","tr_day","wr","per_day","per_trade","sharpe","maxDD","worst_q","pos_folds","n_folds"]
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

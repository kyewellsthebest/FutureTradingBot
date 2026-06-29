"""CORRECT sim of the legacy pullback-fade strategy.

Settles the question: is the legacy strategy (imp2/pull0.118/stop5/tgt44/
invert) actually profitable, or was the old chat's number a fill artifact?

tick_sim.py has two broken fill models:
  A) idealized: fills at the exact pullback LEVEL every time (fantasy -- you
     can't get 157 limit fills/day at the touch price).
  B) mechanistic: fills at market after latency BUT leaves the stop/target
     anchored to the LEVEL, not the fill -> "stops" can exit in profit.

This sim does it right:
  * entry: when price touches the level, fill at market = level + adverse
    slip (LONG buys the ask ~= level+spread; SHORT sells the bid ~= level-
    spread). Configurable adverse_pts.
  * brackets: stop = fill -/+ stop_pts, target = fill +/- tgt_pts, ANCHORED
    TO THE ACTUAL FILL (this is what any real broker bracket does).
  * exit: LONG stop bid<=s, tgt bid>=t; SHORT stop ask>=s, tgt ask<=t;
    stop pays stop_slip; timeout at mid.
  * costs: $0.74 RT, $2/pt. cooldown 60s, max_wait 300s, max_hold 600s.

Run: python -m research.legacy_correct
"""
from __future__ import annotations
import time, numpy as np, pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               _in_break_ns, NS, PT_VALUE)

def simulate_correct(ticks, setups, adverse_pts=0.25, stop_slip=0.25,
                     cooldown_s=60, max_wait_s=300, max_hold_s=600,
                     comm_rt=0.74, block_breaks=True):
    ts, price, bid, ask = ticks
    det_ts=setups["det_ts"]; tdir=setups["trade_dir"]; orig_up=setups["orig_up"]
    entry=setups["entry"]; stop_pts_arr=None
    # recover stop_pts / tgt_pts distances from the level-anchored arrays
    s_lvl=setups["stop"]; t_lvl=setups["tgt"]
    nset=len(det_ts); ntick=len(ts)
    max_wait=max_wait_s*NS; max_hold=max_hold_s*NS; cooldown=cooldown_s*NS
    trades=[]; t_free=ts[0]; used=set(); si=0
    while True:
        while si<nset and det_ts[si]+max_wait<t_free: si+=1
        if si>=nset: break
        best=None; j=si
        while j<nset:
            dts=det_ts[j]
            if best is not None and dts>best[0]: break
            exp=dts+max_wait
            if exp<t_free: j+=1; continue
            key=(round(float(entry[j]),2),int(tdir[j]))
            if key in used: j+=1; continue
            lo=np.searchsorted(ts,dts,"left"); hi=np.searchsorted(ts,exp,"right")
            if lo>=hi: j+=1; continue
            seg_p=price[lo:hi]
            touch=(seg_p<=entry[j]) if orig_up[j] else (seg_p>=entry[j])
            if not touch.any(): j+=1; continue
            tk=lo+int(np.argmax(touch)); fire=ts[tk]
            if fire<t_free: fire=t_free
            if fire>exp: j+=1; continue
            eidx=np.searchsorted(ts,fire,"left")
            if eidx>=ntick: j+=1; continue
            if block_breaks and _in_break_ns(np.array([ts[eidx]]))[0]:
                j+=1; continue
            if best is None or fire<best[0]: best=(fire,j,eidx)
            j+=1
        if best is None: break
        fire_ts,j,eidx=best
        d=int(tdir[j]); lvl=float(entry[j])
        # market fill at the touch tick: adverse to us
        e_px = (float(ask[eidx]) if d==1 else float(bid[eidx]))
        # guard: marketable fill is near the level; if quote missing fall back
        if not np.isfinite(e_px) or e_px<=0: e_px = lvl + d*adverse_pts
        stop_pts=abs(lvl-float(s_lvl[j])); tgt_pts=abs(float(t_lvl[j])-lvl)
        s_px = e_px - d*stop_pts            # anchored to FILL
        t_px = e_px + d*tgt_pts
        deadline=fire_ts+max_hold
        lo_x=np.searchsorted(ts,fire_ts,"right"); hi=np.searchsorted(ts,deadline,"right")
        b=bid[lo_x:hi]; a=ask[lo_x:hi]; tseg=ts[lo_x:hi]
        if len(tseg)==0:
            used.add((round(lvl,2),d)); t_free=fire_ts+cooldown; continue
        if d==1: stop_hit=b<=s_px; tgt_hit=b>=t_px
        else:    stop_hit=a>=s_px; tgt_hit=a<=t_px
        ex=stop_hit|tgt_hit
        if ex.any():
            xi=int(np.argmax(ex)); x_ts=tseg[xi]
            if stop_hit[xi]: reason="stop"; x_px=s_px-d*stop_slip
            else: reason="target"; x_px=t_px
        else:
            xi=len(tseg)-1; x_ts=tseg[xi]; reason="timeout"; x_px=(b[xi]+a[xi])/2.0
        pnl=d*(x_px-e_px)*PT_VALUE-comm_rt
        trades.append({"fire_ts":fire_ts,"side":"LONG" if d==1 else "SHORT",
                       "fill":e_px,"stop":s_px,"target":t_px,"exit_px":round(x_px,2),
                       "reason":reason,"pnl":pnl})
        used.add((round(lvl,2),d)); t_free=x_ts+cooldown
    df=pd.DataFrame(trades)
    if not df.empty: df["dt"]=pd.to_datetime(df["fire_ts"])
    return df

def stats(df):
    if df.empty: return {"n":0}
    n=len(df); days=max(1,df["dt"].dt.normalize().nunique())
    rc=df["reason"].value_counts().to_dict()
    return {"n":n,"tr_day":round(n/days,1),"wr":round(100*(df.pnl>0).mean(),1),
            "tgt%":round(100*rc.get("target",0)/n,1),"stop%":round(100*rc.get("stop",0)/n,1),
            "to%":round(100*rc.get("timeout",0)/n,1),"net":round(df.pnl.sum(),0),
            "per_day":round(df.pnl.sum()/days,1),"per_trade":round(df.pnl.mean(),2),
            "maxDD":round(float((np.maximum.accumulate(df.pnl.cumsum())-df.pnl.cumsum()).max()),0)}

if __name__=="__main__":
    t0=time.time()
    LEGACY={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}
    ticks=load_ticks(); bars=build_1m_bars(ticks[0],ticks[1]); setups=precompute_setups(bars,LEGACY)
    print(f"{len(ticks[0]):,} ticks, {len(setups['det_ts']):,} setups  {time.time()-t0:.0f}s\n")
    print("=== LEGACY strategy, CORRECT fill (market at level + adverse slip, brackets from fill) ===")
    for adv in (0.25,0.5,1.0):
        print(f"  adverse={adv}pt:",stats(simulate_correct(ticks,setups,adverse_pts=adv)))
    print("\n=== sanity: a few trades ===")
    df=simulate_correct(ticks,setups,adverse_pts=0.5)
    for r in ['stop','target']:
        s=df[df.reason==r].head(3)
        print(f"  {r}: pnl values ->", [round(x,1) for x in s.pnl.tolist()])

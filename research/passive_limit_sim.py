"""Does a PASSIVE limit (rest at level, fill AT level) capture the paper edge?
The live bot uses marketable orders (cross spread -> fills worse -> loses).
A passive limit fills at the level L, but only on trades that actually trade
THROUGH it (queue). Model: fill at L when price penetrates >= QT ticks beyond
the touch; fill price = L (limit, no spread paid); if price reverses to the
stop side before penetrating, NO fill (order pulled). Honest forward outcome
on bid/ask. Per-MONTH robustness. QT sweeps the queue assumption.
"""
import numpy as np, pandas as pd, time
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, _in_break_ns, NS, PT_VALUE
TICK=0.25; COMM=0.74; MAXWAIT=300; MAXHOLD=600; COOL=60; STOPSLIP=0.25
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}

def sim(ts,price,bid,ask,S,QT):
    det=S['det_ts'];tdir=S['trade_dir'];oup=S['orig_up'];entry=S['entry'];stop=S['stop'];tgt=S['tgt']
    n=len(det); trades=[]; t_free=ts[0]; ntick=len(ts)
    for j in range(n):
        dts=det[j]; exp=dts+MAXWAIT*NS
        if exp<t_free: continue
        lo=np.searchsorted(ts,dts,'left'); hi=np.searchsorted(ts,exp,'right')
        if lo>=hi: continue
        e=float(entry[j]); d=int(tdir[j]); s=float(stop[j]); tp=float(tgt[j])
        seg=price[lo:hi]; tseg=ts[lo:hi]
        # PASSIVE FILL: need price to trade >= QT ticks through the level.
        # orig_up: entry approached from above (price falls to e) -> penetration = e - price
        # else: approached from below -> penetration = price - e
        if oup[j]: pen = e - seg
        else:      pen = seg - e
        fillmask = pen >= (QT*TICK)
        if not fillmask.any(): continue      # never traded through enough -> no fill (order pulled)
        fk = int(np.argmax(fillmask)); fire = tseg[fk]
        if fire < t_free:                    # was busy; re-check fill after free
            # find first fill at/after t_free
            after = (tseg>=t_free)&fillmask
            if not after.any(): continue
            fk=int(np.argmax(after)); fire=tseg[fk]
        if fire>exp: continue
        gi = lo+fk
        if _in_break_ns(np.array([ts[gi]]))[0]: continue
        e_fill = e                            # LIMIT fills at the level (no spread paid)
        # forward outcome on bid/ask
        dl=fire+MAXHOLD*NS; xlo=np.searchsorted(ts,fire,'right'); xhi=np.searchsorted(ts,dl,'right')
        if xlo>=xhi: continue
        b=bid[xlo:xhi]; a=ask[xlo:xhi]; tx=ts[xlo:xhi]
        if d==1: sh=b<=s; th=b>=tp
        else:    sh=a>=s; th=a<=tp
        exm=sh|th
        if exm.any():
            xi=int(np.argmax(exm)); xts=tx[xi]
            if th[xi] and not sh[xi]: pnl=d*(tp-e_fill)*PT_VALUE-COMM
            else: xpx=s-d*STOPSLIP; pnl=d*(xpx-e_fill)*PT_VALUE-COMM
        else:
            xi=len(tx)-1; xts=tx[xi]; xpx=(b[xi]+a[xi])/2; pnl=d*(xpx-e_fill)*PT_VALUE-COMM
        trades.append((fire,pnl)); t_free=xts+COOL*NS
    return trades

def report(name,trades):
    if not trades: print(f"{name}: no fills"); return
    ts=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])
    dt=pd.to_datetime(ts); days=pd.Series(dt).dt.normalize().nunique()
    mth=pd.Series(pnl,index=dt).groupby(dt.to_period('M')).sum()
    wr=100*(pnl>0).mean()
    print(f"{name}: n={len(trades)} fill/day={len(trades)/days:.0f} WR={wr:.1f}% net=${pnl.sum():.0f} per_day=${pnl.sum()/days:.0f}")
    print(f"    per-month: {[f'{p}:{v:.0f}' for p,v in mth.items()]}")

def main():
    t0=time.time(); ts,price,bid,ask=load_ticks(); bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
    print(f"{len(ts):,} ticks, {len(S['det_ts']):,} setups {time.time()-t0:.0f}s\n",flush=True)
    print("PASSIVE LIMIT at level, fill only if price trades >= QT ticks through (queue assumption):")
    for QT in (1,2,3,4,6):
        report(f"QT={QT}tick", sim(ts,price,bid,ask,S,QT))
    print(f"\ndone {time.time()-t0:.0f}s")

if __name__=="__main__": main()

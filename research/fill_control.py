"""Control: fill on TOUCH (unbiased timing), no penetration selection.
Two fill prices: (A) at the level e [passive-limit optimistic], (B) at the
marketable bid/ask [realistic stop]. Also measure whether, at the touch, the
marketable price is better or worse than e (tells us the true order type)."""
import numpy as np, pandas as pd
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, _in_break_ns, NS, PT_VALUE
COMM=0.74; MAXWAIT=300; MAXHOLD=600; COOL=60; STOPSLIP=0.25
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}

def run(fillmode):
    ts,price,bid,ask=load_ticks(); bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
    det=S['det_ts'];tdir=S['trade_dir'];oup=S['orig_up'];entry=S['entry'];stop=S['stop'];tgt=S['tgt']
    n=len(det); trades=[]; t_free=ts[0]; worse=[]
    for j in range(n):
        dts=det[j]; exp=dts+MAXWAIT*NS
        if exp<t_free: continue
        lo=np.searchsorted(ts,dts,'left'); hi=np.searchsorted(ts,exp,'right')
        if lo>=hi: continue
        e=float(entry[j]); d=int(tdir[j]); s=float(stop[j]); tp=float(tgt[j]); seg=price[lo:hi]; tseg=ts[lo:hi]
        touch = seg<=e if oup[j] else seg>=e
        if not touch.any(): continue
        fk=int(np.argmax(touch)); fire=tseg[fk]
        if fire<t_free:
            aft=(tseg>=t_free)&touch
            if not aft.any(): continue
            fk=int(np.argmax(aft)); fire=tseg[fk]
        if fire>exp: continue
        gi=lo+fk
        if _in_break_ns(np.array([ts[gi]]))[0]: continue
        # fill price
        if fillmode=="level": e_fill=e
        else: e_fill=float(ask[gi]) if d==1 else float(bid[gi])   # marketable
        # is marketable worse than level? (short sells at bid; worse if bid<e)
        mk=float(ask[gi]) if d==1 else float(bid[gi])
        worse.append((mk-e)*d)   # <0 means marketable is worse than level
        dl=fire+MAXHOLD*NS; xlo=np.searchsorted(ts,fire,'right'); xhi=np.searchsorted(ts,dl,'right')
        if xlo>=xhi: continue
        b=bid[xlo:xhi]; a=ask[xlo:xhi]; tx=ts[xlo:xhi]
        if d==1: sh=b<=s; th=b>=tp
        else:    sh=a>=s; th=a<=tp
        exm=sh|th
        if exm.any():
            xi=int(np.argmax(exm)); xts=tx[xi]
            if th[xi] and not sh[xi]: xpx=tp
            else: xpx=s-d*STOPSLIP
        else:
            xi=len(tx)-1; xts=tx[xi]; xpx=(b[xi]+a[xi])/2
        trades.append((fire, d*(xpx-e_fill)*PT_VALUE-COMM)); t_free=xts+COOL*NS
    ts2=np.array([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])
    dt=pd.to_datetime(ts2); days=pd.Series(dt).dt.normalize().nunique()
    print(f"  fill={fillmode:8s}: n={len(trades)} WR={100*(pnl>0).mean():.1f}% net=${pnl.sum():.0f} per_day=${pnl.sum()/days:.0f}")
    return np.array(worse)

print("CONTROL: fill on TOUCH (no penetration selection):")
w=run("level")
run("market")
print(f"\nAt touch, marketable price vs level (avg pts, <0 = you fill WORSE than level): {w.mean():.2f}")
print(f"  fraction where marketable is worse than level: {(w<0).mean()*100:.0f}%")

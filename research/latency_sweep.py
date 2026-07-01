"""How much does BOT EXECUTION LATENCY cost? Detect touch, then fill at the
MARKET (bid/ask) `lat` ms later (models a marketable order sent on touch).
Sweep lat. Compare to a RESTING LIMIT that fills AT the level (lat-immune).
Answers: does 50ms fix it, or must it be a resting limit?"""
import numpy as np, pandas as pd
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, _in_break_ns, NS, PT_VALUE
COMM=0.74; MAXWAIT=300; MAXHOLD=600; COOL=60; STOPSLIP=0.25
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}
ts,price,bid,ask=load_ticks(); bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
det=S['det_ts'];tdir=S['trade_dir'];oup=S['orig_up'];entry=S['entry'];stop=S['stop'];tgt=S['tgt']
ntick=len(ts)

def run(mode, lat_ms=0):
    t_free=ts[0]; trades=[]; slip_sum=[]
    for j in range(len(det)):
        dts=det[j]; exp=dts+MAXWAIT*NS
        if exp<t_free: continue
        lo=np.searchsorted(ts,dts,'left'); hi=np.searchsorted(ts,exp,'right')
        if lo>=hi: continue
        e=float(entry[j]); d=int(tdir[j]); s=float(stop[j]); tp=float(tgt[j]); seg=price[lo:hi]; tseg=ts[lo:hi]
        touch=seg<=e if oup[j] else seg>=e
        if not touch.any(): continue
        fk=int(np.argmax(touch)); ttime=tseg[fk]
        if ttime<t_free:
            aft=(tseg>=t_free)&touch
            if not aft.any(): continue
            fk=int(np.argmax(aft)); ttime=tseg[fk]
        if ttime>exp: continue
        if mode=="limit":
            fire=ttime; gi=lo+fk; e_fill=e                       # resting limit fills AT level
        else:  # marketable, filled lat ms after touch at market
            fi=np.searchsorted(ts,ttime+lat_ms*1_000_000,'left')
            if fi>=ntick: continue
            fire=ts[fi]; gi=fi; e_fill=float(ask[fi]) if d==1 else float(bid[fi])
        if _in_break_ns(np.array([ts[gi]]))[0]: continue
        slip_sum.append((e_fill-e)*d)   # >0 = worse fill than level (for the trade dir)
        dl=fire+MAXHOLD*NS; xlo=np.searchsorted(ts,fire,'right'); xhi=np.searchsorted(ts,dl,'right')
        if xlo>=xhi: continue
        b=bid[xlo:xhi]; a=ask[xlo:xhi]; tx=ts[xlo:xhi]
        if d==1: sh=b<=s; th=b>=tp
        else:    sh=a>=s; th=a<=tp
        exm=sh|th
        if exm.any():
            xi=int(np.argmax(exm)); xts=tx[xi]; xpx=tp if (th[xi] and not sh[xi]) else s-d*STOPSLIP
        else:
            xi=len(tx)-1; xts=tx[xi]; xpx=(b[xi]+a[xi])/2
        trades.append((fire, d*(xpx-e_fill)*PT_VALUE-COMM)); t_free=xts+COOL*NS
    pnl=np.array([t[1] for t in trades]); dt=pd.to_datetime([t[0] for t in trades])
    days=pd.Series(dt).dt.normalize().nunique()
    sl=np.array(slip_sum)
    return dict(n=len(trades),wr=100*(pnl>0).mean(),per_day=pnl.sum()/days,slip=sl.mean())

print("RESTING LIMIT (fills at level, latency-immune):")
r=run("limit"); print(f"   n={r['n']} WR={r['wr']:.1f}% per_day=${r['per_day']:.0f} avg_fill_vs_level={r['slip']:+.2f}pt")
print("\nMARKETABLE order, filled X ms after touch (bot execution latency):")
for lat in (0,50,100,250,500,1000,2000,5000):
    r=run("mkt",lat); print(f"   lat={lat:>5}ms: n={r['n']} WR={r['wr']:.1f}% per_day=${r['per_day']:+.0f}  avg_fill_vs_level={r['slip']:+.2f}pt (worse)")

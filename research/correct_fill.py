"""DEFINITIVE test: correct LIMIT-order fills.
A limit at level e fills at e-or-better, but only when price genuinely
reaches e from the correct side:
  SHORT sell-limit at e: fills when price RISES to e (price>=e). If e<market
        at detection, it's marketable -> fill at current bid (>=e, i.e. better).
  LONG  buy-limit at e:  fills when price FALLS to e (price<=e). If e>market,
        marketable -> fill at current ask (<=e, better).
Fill at e (or the better marketable price). No fill if price never reaches e
within max_wait. Honest forward outcome. Per-month + fill rate.
"""
import numpy as np, pandas as pd
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, _in_break_ns, NS, PT_VALUE
COMM=0.74; MAXWAIT=300; MAXHOLD=600; COOL=60; STOPSLIP=0.25
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}
ts,price,bid,ask=load_ticks(); bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
det=S['det_ts'];tdir=S['trade_dir'];entry=S['entry'];stop=S['stop'];tgt=S['tgt']
ntick=len(ts)
setups_touched=0; trades=[]; t_free=ts[0]; passive=0; marketable=0
for j in range(len(det)):
    dts=det[j]; exp=dts+MAXWAIT*NS
    if exp<t_free: continue
    di=np.searchsorted(ts,dts,'left')
    if di>=ntick: break
    e=float(entry[j]); d=int(tdir[j]); s=float(stop[j]); tp=float(tgt[j])
    mkt_bid=float(bid[di]); mkt_ask=float(ask[di])
    lo=di; hi=np.searchsorted(ts,exp,'right')
    if lo>=hi: continue
    seg=price[lo:hi]; tseg=ts[lo:hi]
    if d==-1:  # SELL LIMIT at e
        if e < mkt_ask:            # e below market -> marketable, fill now at bid (better, >=e ideally)
            fire=ts[di]; gi=di; e_fill=max(e, mkt_bid); marketable+=1
        else:                       # passive: fill when price rises to e
            reach=seg>=e
            if not reach.any(): continue
            fk=int(np.argmax(reach)); fire=tseg[fk]; gi=lo+fk; e_fill=e; passive+=1
    else:      # BUY LIMIT at e
        if e > mkt_bid:            # e above market -> marketable, fill now at ask (better, <=e)
            fire=ts[di]; gi=di; e_fill=min(e, mkt_ask); marketable+=1
        else:
            reach=seg<=e
            if not reach.any(): continue
            fk=int(np.argmax(reach)); fire=tseg[fk]; gi=lo+fk; e_fill=e; passive+=1
    if fire<t_free: continue
    if fire>exp: continue
    if _in_break_ns(np.array([ts[gi]]))[0]: continue
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
days=pd.Series(dt).dt.normalize().nunique(); mth=pd.Series(pnl,index=dt).groupby(dt.to_period('M')).sum()
print(f"CORRECT LIMIT FILL: n={len(trades)}  ({passive} passive-limit, {marketable} marketable)")
print(f"  WR={100*(pnl>0).mean():.1f}%  net=${pnl.sum():.0f}  per_day=${pnl.sum()/days:.0f}")
print(f"  per-month: {[f'{p}:{v:.0f}' for p,v in mth.items()]}")

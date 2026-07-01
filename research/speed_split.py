"""Are FAST touches (missed by a slow bot) the winners or losers?
Split trades by detection->touch gap; compare WR and P&L (fill at level)."""
import numpy as np, pandas as pd
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, _in_break_ns, NS, PT_VALUE
COMM=0.74; MAXWAIT=300; MAXHOLD=600; COOL=60; STOPSLIP=0.25
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}
ts,price,bid,ask=load_ticks(); bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
det=S['det_ts'];tdir=S['trade_dir'];oup=S['orig_up'];entry=S['entry'];stop=S['stop'];tgt=S['tgt']
rows=[]; t_free=ts[0]
for j in range(len(det)):
    dts=det[j]; exp=dts+MAXWAIT*NS
    if exp<t_free: continue
    lo=np.searchsorted(ts,dts,'left'); hi=np.searchsorted(ts,exp,'right')
    if lo>=hi: continue
    e=float(entry[j]); d=int(tdir[j]); s=float(stop[j]); tp=float(tgt[j]); seg=price[lo:hi]; tseg=ts[lo:hi]
    touch=seg<=e if oup[j] else seg>=e
    if not touch.any(): continue
    fk=int(np.argmax(touch)); fire=tseg[fk]
    if fire<t_free:
        aft=(tseg>=t_free)&touch
        if not aft.any(): continue
        fk=int(np.argmax(aft)); fire=tseg[fk]
    if fire>exp: continue
    gi=lo+fk
    if _in_break_ns(np.array([ts[gi]]))[0]: continue
    gap=(fire-dts)/1e9
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
    rows.append((gap, d*(xpx-e)*PT_VALUE-COMM)); t_free=xts+COOL*NS
df=pd.DataFrame(rows,columns=['gap','pnl'])
def show(name,f):
    if len(f)==0: print(f"{name}: none"); return
    print(f"{name:28s}: n={len(f):5d}  WR={100*(f.pnl>0).mean():4.1f}%  net=${f.pnl.sum():8.0f}  per_trade=${f.pnl.mean():6.2f}")
print("Fill AT LEVEL, split by detection->touch speed:")
show("FAST  touch <=2s (missed by 2s bot)", df[df.gap<=2])
show("SLOW  touch >2s  (caught by 2s bot)", df[df.gap>2])
print()
show("  <=0.5s", df[df.gap<=0.5]); show("  0.5-2s", df[(df.gap>0.5)&(df.gap<=2)])
show("  2-10s", df[(df.gap>2)&(df.gap<=10)]); show("  >10s", df[df.gap>10])

"""How long between signal detection and price reaching the entry level?
If that gap >> 2s, a limit RESTED IN ADVANCE is on the book before price
arrives -> fills instantly on touch, immune to the 2s bot/API latency that
kills REACTIVE limit orders."""
import numpy as np, pandas as pd
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, NS
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}
ts,price,bid,ask=load_ticks(); bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
det=S['det_ts'];oup=S['orig_up'];entry=S['entry']
gaps=[]; MAXWAIT=300
for j in range(len(det)):
    dts=det[j]; exp=dts+MAXWAIT*NS
    lo=np.searchsorted(ts,dts,'left'); hi=np.searchsorted(ts,exp,'right')
    if lo>=hi: continue
    seg=price[lo:hi]; tseg=ts[lo:hi]
    touch=seg<=entry[j] if oup[j] else seg>=entry[j]
    if not touch.any(): continue
    tk=int(np.argmax(touch))
    gaps.append((tseg[tk]-dts)/1e9)   # seconds from detection to first touch
g=np.array(gaps)
print(f"touched setups: {len(g):,}")
print(f"gap detection->touch (sec):  median={np.median(g):.1f}  mean={g.mean():.1f}  25th={np.percentile(g,25):.1f}")
for thr in (0.5,1,2,5,10,30,60):
    print(f"  touch within {thr:>4}s of signal: {(g<=thr).mean()*100:5.1f}%   (>= = safe to rest in advance)")
print(f"\n  touches AFTER 2s (advance-rest fills these): {(g>2).mean()*100:.1f}%")
print(f"  touches within 2s (only these are at risk): {(g<=2).mean()*100:.1f}%")

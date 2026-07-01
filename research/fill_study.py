"""Does fill-rate selection favor winners or losers? Measures, per paper trade:
 - paper outcome (fill at level, brackets from level)  [= what the paper books]
 - how 'fillable' the entry really was: how far price traded BEYOND the limit
   level (in ticks) right after the touch — a resting retail limit needs trades
   through its price to fill; a 1-tick wick that reverses usually does NOT fill.
Then: is the realistically-fillable subset profitable, or are the misses the winners?
"""
import numpy as np, pandas as pd, time
from research.tick_sim import load_ticks, build_1m_bars, precompute_setups, _in_break_ns, NS, PT_VALUE
TICK=0.25
P={'IMPULSE_PTS':2.0,'IMPULSE_WINDOW_BARS':3,'PULLBACK_PCT':0.118,'STOP_PTS':5.0,'TARGET_PTS':44.0,'INVERT':True}
COMM=0.74; MAXWAIT=300; MAXHOLD=600; COOL=60

def main():
    t0=time.time(); ts,price,bid,ask=load_ticks(); print(f"{len(ts):,} ticks {time.time()-t0:.0f}s",flush=True)
    bars=build_1m_bars(ts,price); S=precompute_setups(bars,P)
    det=S['det_ts']; tdir=S['trade_dir']; oup=S['orig_up']; entry=S['entry']; stop=S['stop']; tgt=S['tgt']
    n=len(det); print(f"{n:,} setups",flush=True)
    rows=[]; t_free=ts[0]
    for j in range(n):
        dts=det[j]; exp=dts+MAXWAIT*NS
        if exp<t_free: continue
        lo=np.searchsorted(ts,dts,'left'); hi=np.searchsorted(ts,exp,'right')
        if lo>=hi: continue
        seg=price[lo:hi]
        if oup[j]: touch=seg<=entry[j]
        else:      touch=seg>=entry[j]
        if not touch.any(): continue
        tk=lo+int(np.argmax(touch)); fire=ts[tk]
        if fire<t_free: fire=t_free
        if fire>exp: continue
        if _in_break_ns(np.array([ts[tk]]))[0]: continue
        d=int(tdir[j]); e=float(entry[j]); s=float(stop[j]); tp=float(tgt[j])
        # paper outcome: brackets from level, exit on bid/ask like the bot
        dl=fire+MAXHOLD*NS; xlo=np.searchsorted(ts,fire,'right'); xhi=np.searchsorted(ts,dl,'right')
        if xlo>=xhi: continue
        b=bid[xlo:xhi]; a=ask[xlo:xhi]
        if d==1: sh=b<=s; th=b>=tp
        else:    sh=a>=s; th=a<=tp
        ex=sh|th
        if ex.any():
            xi=int(np.argmax(ex)); win=bool(th[xi] and not sh[xi]); reason='t' if win else 's'
        else:
            win=False; reason='to'
        # FILLABILITY: how far price traded BEYOND the level within 2s of touch
        w2=np.searchsorted(ts,ts[tk]+2*NS,'right'); seg2=price[tk:max(tk+1,w2)]
        if oup[j]: beyond=(e-seg2.min())/TICK      # price fell below entry by X ticks
        else:      beyond=(seg2.max()-e)/TICK
        rows.append((win,reason,beyond,d))
        # advance (paper books it regardless)
        t_free=ts[min(xhi-1, xlo+ (xi if ex.any() else len(b)-1))]+COOL*NS
    df=pd.DataFrame(rows,columns=['win','reason','beyond_ticks','dir'])
    # paper stats
    net_paper=(df['win']*(P['TARGET_PTS']) - (~df['win']&(df.reason=='s'))*(P['STOP_PTS']+0.25))*PT_VALUE-COMM
    print(f"\nPAPER: {len(df)} trades  WR={df.win.mean()*100:.1f}%  net=${net_paper.sum():.0f}")
    print(f"\nfill-'beyond' (ticks price traded through your level in 2s): win vs loss")
    print(df.groupby('win')['beyond_ticks'].describe()[['mean','50%','75%']])
    print("\n=== fill rate & P&L of fillable subset vs threshold d (need price to trade >= d ticks through level) ===")
    for d in (0,1,2,3,4):
        f=df[df.beyond_ticks>=d]
        if len(f)==0: continue
        net=(f['win']*P['TARGET_PTS'] - (~f['win']&(f.reason=='s'))*(P['STOP_PTS']+0.25))*PT_VALUE-COMM
        print(f"  d>={d}tick: fill_rate={len(f)/len(df)*100:4.0f}%  WR={f.win.mean()*100:4.1f}%  net=${net.sum():7.0f}  ({len(f)} trades)")
    print(f"\ndone {time.time()-t0:.0f}s")

if __name__=="__main__": main()

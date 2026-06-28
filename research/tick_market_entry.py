"""Market-entry search — the genuinely different direction.

The fill fantasy in the limit-at-a-level strategy exists ONLY because it
tries to buy/sell at a BETTER price than the market is offering (a limit at
a level price has already left). This sim enters at MARKET the instant the
signal fires: LONG pays the ask, SHORT pays the bid. That fill is ALWAYS
available, and paper and broker would fill identically -> the paper-vs-broker
gap structurally disappears.

We then test whether a real, FILLABLE edge exists, under realistic costs:
  - entry: market (ask for LONG, bid for SHORT) at signal time = pay spread
  - stop/target: from the ACTUAL fill (re-anchored, like a real bracket)
  - stop slip 1.3pt (live-measured), commission 0.74/RT, $2/pt
Both directions tested: fade the impulse (INVERT) and follow it (momentum).

Signal = impulse of >= IMPULSE_PTS over IMPULSE_WINDOW_BARS 1-min bars.
Optional HTF trend filter (only trade with the higher-timeframe trend).
"""
from __future__ import annotations
import itertools, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, _in_break_ns, stats, PT_VALUE, NS)

STOP_SLIP = 1.3
COMM = 0.74
COOLDOWN_S = 60
MAX_HOLD_S = 600

_TICKS=None; _BARS=None
def _init():
    global _TICKS,_BARS
    _TICKS=load_ticks(); _BARS=build_1m_bars(_TICKS[0],_TICKS[1])

def _signals(bars, imp, W, invert, htf_lb):
    """Return (det_ts_ns, trade_dir) for each bar whose window has an impulse."""
    o=bars["open"].to_numpy(); c=bars["close"].to_numpy()
    start=bars.index.to_numpy("datetime64[ns]").astype("int64"); n=len(bars)
    net=c[W-1:]-o[:n-W+1]; idx=np.arange(W-1,n)
    valid=np.abs(net)>=imp
    idx=idx[valid]; net=net[valid]
    up=net>0
    trade_long = ~up if invert else up
    if htf_lb>0:
        prev=idx-htf_lb; ok=prev>=0
        trend=np.zeros(len(idx)); trend[ok]=c[idx[ok]]-c[prev[ok]]
        keep=((trade_long&(trend>0))|(~trade_long&(trend<0)))&ok
        idx=idx[keep]; trade_long=trade_long[keep]
    det_ts=start[idx]+60*NS
    return det_ts, np.where(trade_long,1,-1).astype("int8")

def simulate_market(ticks, det_ts, tdir, stop_pts, tgt_pts, block_breaks=True):
    ts,price,bid,ask=ticks; ntick=len(ts)
    cooldown=COOLDOWN_S*NS; max_hold=MAX_HOLD_S*NS
    trades=[]; t_free=ts[0]
    for k in range(len(det_ts)):
        dt=det_ts[k]
        if dt<t_free: continue
        eidx=np.searchsorted(ts,dt,"left")
        if eidx>=ntick: break
        if block_breaks and _in_break_ns(np.array([ts[eidx]]))[0]: continue
        d=int(tdir[k])
        e_px = float(ask[eidx]) if d==1 else float(bid[eidx])   # pay the market
        fire=ts[eidx]
        s_px = e_px - d*stop_pts; t_px = e_px + d*tgt_pts
        hi=np.searchsorted(ts,fire+max_hold,"right"); lo=eidx+1
        if lo>=hi:
            continue
        b=bid[lo:hi]; a=ask[lo:hi]; tseg=ts[lo:hi]
        if d==1:
            stop_hit=b<=s_px; tgt_hit=b>=t_px
        else:
            stop_hit=a>=s_px; tgt_hit=a<=t_px
        ex=stop_hit|tgt_hit
        if ex.any():
            xi=int(np.argmax(ex)); xts=tseg[xi]
            if stop_hit[xi]:
                reason="stop"; xpx = s_px-STOP_SLIP if d==1 else s_px+STOP_SLIP
            else:
                reason="target"; xpx=t_px
        else:
            xi=len(tseg)-1; xts=tseg[xi]; reason="timeout"; xpx=(b[xi]+a[xi])/2
        pnl=d*(xpx-e_px)*PT_VALUE - COMM
        trades.append({"fire_ts":fire,"exit_ts":xts,"side":"LONG" if d==1 else "SHORT",
                       "entry":round(e_px,2),"exit_px":round(xpx,2),"reason":reason,
                       "hold_s":(xts-fire)/NS,"pnl":pnl})
        t_free=xts+cooldown
    df=pd.DataFrame(trades)
    if not df.empty: df["dt"]=pd.to_datetime(df["fire_ts"])
    return df

def _eval(t):
    imp,W,invert,stop,tgt,htf=t
    det,dr=_signals(_BARS,imp,W,invert,htf)
    if len(det)<150: return None
    df=simulate_market(_TICKS,det,dr,stop,tgt)
    if df.empty or len(df)<150: return None
    s=stats(df)
    dp=df.groupby(df.dt.dt.normalize())["pnl"].sum()
    sharpe=round(float(dp.mean()/dp.std()*np.sqrt(252)),2) if dp.std()>0 else 0
    return {"name":f"{'FADE' if invert else 'MOM'}_i{imp}_w{W}_s{stop}_t{tgt}_htf{htf}",
            "mode":"fade" if invert else "momentum","imp":imp,"W":W,"stop":stop,"tgt":tgt,"htf":htf,
            "n":s["n"],"tr_day":s["tr_per_day"],"wr":s["wr"],"per_day":s["per_day"],
            "per_trade":s["per_trade"],"maxDD":s["maxDD"],"sharpe":sharpe}

def main():
    t0=time.time()
    grid=list(itertools.product(
        [3.0,5.0,8.0,12.0],      # impulse pts
        [3,4,6],                  # window bars
        [True,False],             # invert: fade vs momentum
        [8.0,12.0,18.0,25.0],     # stop pts (WIDE - drift-tolerant)
        [12.0,20.0,35.0,50.0],    # target pts
        [0,30,60]))               # htf filter
    print(f"market-entry grid: {len(grid)} configs",flush=True)
    _init()
    res=[]
    with ProcessPoolExecutor(max_workers=4,initializer=_init) as ex:
        for i,r in enumerate(ex.map(_eval,grid,chunksize=4)):
            if r: res.append(r)
            if (i+1)%80==0: print(f"  {i+1}/{len(grid)} {time.time()-t0:.0f}s",flush=True)
    df=pd.DataFrame(res); df.to_csv("research/tick_market_entry_results.csv",index=False)
    pd.set_option("display.width",240,"display.max_columns",40)
    cols=["name","n","tr_day","wr","per_day","per_trade","sharpe","maxDD"]
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} configs")
    print("\n=== TOP 15 by $/day (market entry, realistic costs, paper==broker) ===")
    print(df.sort_values("per_day",ascending=False).head(15)[cols].to_string(index=False))
    print(f"\npositive configs: {len(df[df.per_day>0])}/{len(df)}")
    print(f"positive & sharpe>1: {len(df[(df.per_day>0)&(df.sharpe>1)])}")

if __name__=="__main__":
    main()

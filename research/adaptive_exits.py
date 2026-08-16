"""LEVELRIDE base + ADAPTIVE EXIT variants on real NQ 1-min bars (w/ volume).
Tests the user's ideas:
  - Breakeven stop when price isn't reaching target
  - Trailing stops
  - Volume-activity-scaled take profit (high vol -> extend TP)
  - Time-based stop-to-breakeven
Market entries => paper==broker by construction (no fill-assumption lie).
"""
import pandas as pd, numpy as np
from datetime import timedelta

DF = pd.read_csv("/home/user/HFTBot/data/polygon/NQ_1min.csv", parse_dates=["ts"])
DF = DF.sort_values("ts").reset_index(drop=True)
DF["date"] = DF["ts"].dt.date
DF["hm"] = DF["ts"].dt.hour*60 + DF["ts"].dt.minute
# rolling volume baseline (60-bar) for activity detection
DF["vol_ma"] = DF["volume"].rolling(60, min_periods=10).mean()

# LEVELRIDE constants
TGT=260.0; STP=80.0; HOLD_H=4; RUNG=[0.0,20.0,-20.0]; PTV=2.0; FEES=1.50; ADV=0.25
SESS_OPEN=14*60; ENTRY_END=20*60+26; FLAT=20*60+55

def run(mode, **kw):
    """mode: base | be | trail | voltp | timebe | combo"""
    trades=[]
    for date, g in DF.groupby("date"):
        g=g.reset_index(drop=True)
        op=g[g["hm"]>=SESS_OPEN]
        if len(op)==0: continue
        anchor=op.iloc[0]["open"]
        levels=[anchor+o for o in RUNG]
        prev_close=None; pos={}   # ri -> dict
        for _,bar in op.iterrows():
            hm=bar["hm"]; o,h,l,c,v=bar["open"],bar["high"],bar["low"],bar["close"],bar["volume"]
            vma=bar["vol_ma"] if not np.isnan(bar["vol_ma"]) else v
            flat_now = hm>=FLAT
            # manage open
            for ri in list(pos.keys()):
                p=pos[ri]; s=p["side"]
                # update peak favorable excursion
                fav = (h-p["entry"]) if s>0 else (p["entry"]-l)
                p["mfe"]=max(p["mfe"], fav)
                tgt=p["entry"]+TGT*s; stp=p["cur_stop"]
                # --- ADAPTIVE STOP LOGIC ---
                if mode in ("be","combo") and p["mfe"]>=kw.get("be_trig",60):
                    be = p["entry"]+kw.get("be_lock",0)*s
                    p["cur_stop"]= max(stp,be) if s>0 else min(stp,be)
                    stp=p["cur_stop"]
                if mode in ("trail","combo") and p["mfe"]>=kw.get("trail_start",80):
                    trail = (p["entry"]+p["mfe"]*s) - kw.get("trail_dist",60)*s
                    p["cur_stop"]= max(stp,trail) if s>0 else min(stp,trail)
                    stp=p["cur_stop"]
                if mode in ("timebe","combo"):
                    mins=(bar["ts"]-pd.Timestamp(p["t_in"])).total_seconds()/60
                    if mins>=kw.get("t_min",60) and p["mfe"]<kw.get("t_need",40):
                        be=p["entry"]
                        p["cur_stop"]= max(stp,be) if s>0 else min(stp,be)
                        stp=p["cur_stop"]
                # --- ADAPTIVE TARGET (volume) ---
                if mode in ("voltp","combo") and v> kw.get("vol_k",2.5)*vma:
                    tgt=p["entry"]+kw.get("vol_tgt",400)*s
                due = bar["ts"] >= pd.Timestamp(p["t_in"])+timedelta(hours=HOLD_H)
                hit_stop = l<=stp if s>0 else h>=stp
                hit_tgt  = h>=tgt if s>0 else l<=tgt
                if hit_stop:
                    trades.append(((stp-ADV*s - p["entry"])*s*PTV - FEES, date))
                    del pos[ri]
                elif hit_tgt:
                    trades.append(((tgt - p["entry"])*s*PTV - FEES, date))
                    del pos[ri]
                elif flat_now or due:
                    trades.append(((c-ADV*s - p["entry"])*s*PTV - FEES, date))
                    del pos[ri]
            # entries
            can_enter = hm>=SESS_OPEN and hm<=ENTRY_END and not flat_now
            if can_enter and prev_close is not None:
                for ri,lev in enumerate(levels):
                    if ri in pos: continue
                    a,bb=prev_close,c
                    if a==bb: continue
                    if not ((a<lev<=bb) or (a>lev>=bb)): continue
                    side=1 if bb>lev else -1
                    entry=c+ADV*side
                    pos[ri]={"side":side,"entry":entry,"t_in":bar["ts"].isoformat(),
                             "cur_stop":entry-STP*side,"mfe":0.0}
            prev_close=c
    if not trades: return None
    pnl=np.array([t[0] for t in trades])
    days=len(set(t[1] for t in trades))
    wins=(pnl>0).sum()
    # per-day series for DD
    bydate={}
    for p,d in trades: bydate[d]=bydate.get(d,0)+p
    series=np.array([bydate[d] for d in sorted(bydate)])
    cum=np.cumsum(series); dd=(np.maximum.accumulate(cum)-cum).max()
    return dict(mode=mode, n=len(pnl), wr=wins/len(pnl), net=pnl.sum(),
                per_day=pnl.sum()/days, per_wk=pnl.sum()/days*5, per_tr=pnl.mean(),
                maxDD=dd, days=days, kw=kw)

def show(r):
    if r is None: print("  no trades"); return
    tag=",".join(f"{k}={v}" for k,v in r["kw"].items())
    print(f"  {r['mode']:<8} {tag:<38} n={r['n']:>5} WR={r['wr']*100:4.1f}% "
          f"day=${r['per_day']:+6.0f} wk=${r['per_wk']:+6.0f} /tr=${r['per_tr']:+6.1f} DD=${r['maxDD']:.0f}")

print("=== BASE (reproduce LEVELRIDE ~$494/day) ===")
show(run("base"))
print("\n=== BREAKEVEN stop (move to BE after +X favorable) ===")
for trig in [40,60,80,100]:
    for lock in [0,5,10]:
        show(run("be", be_trig=trig, be_lock=lock))
print("\n=== TRAILING stop ===")
for st in [60,80,120]:
    for dist in [40,60,80]:
        show(run("trail", trail_start=st, trail_dist=dist))
print("\n=== TIME-BASED breakeven (not at +Y by minute M -> BE) ===")
for tmin in [30,60,90]:
    for need in [20,40,60]:
        show(run("timebe", t_min=tmin, t_need=need))
print("\n=== VOLUME-SCALED take profit (high vol -> extend TP) ===")
for k in [2.0,2.5,3.0]:
    for vt in [350,400,500]:
        show(run("voltp", vol_k=k, vol_tgt=vt))

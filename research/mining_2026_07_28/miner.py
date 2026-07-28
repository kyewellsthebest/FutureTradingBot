"""Fresh-grid miner on clean data. Train = start->2026-05-21 (must be
positive overall, every calendar year, >=70% pos weeks, >=$150/wk).
OOS gates = last 10 weeks AND last 3 weeks positive. Engine-exact
semantics. Usage: mega_grid.py MARKET"""
import json, sys, os, tempfile, itertools
import numpy as np, pandas as pd
sys.path.insert(0, "/home/user/FutureTradingBot")
os.environ.setdefault("BOT_DATA_DIR", tempfile.mkdtemp()); os.environ.setdefault("POLYGON_API","fake")
import bot.basket_engine as be

ROOT = sys.argv[1]
OUT = f"/tmp/claude-0/-home-user-FutureTradingBot/25529eed-cfb9-5eb3-98ab-625b175d900a/scratchpad/mine/grid_{ROOT}.json"
TRAIN_END = pd.Timestamp("2026-05-22T00:00:00Z")
W10 = pd.Timestamp("2026-05-18T00:00:00Z"); W3 = pd.Timestamp("2026-07-06T00:00:00Z")
T1 = pd.Timestamp("2026-07-27T20:54:00Z")

ST = [(0.0,1.0),(0.0,1.5),(0.0,2.5),(1.0,1.0),(2.5,1.0),(2.5,0.0)]
SESS4 = ["all","us","eu","asia"]
grid = []
for lb,k,H,sess,(sp,tp) in itertools.product([3,6,12,24,48],[0.8,1.2,1.8,2.5],[6,12,24,48],SESS4,ST):
    grid.append(dict(fam="fade",lb=lb,k=k,H=H,sess=sess,stopA=sp,tgtA=tp,limit=True))
for lb,k,H,sess,(sp,tp) in itertools.product([6,12,24,48],[1.2,1.8,2.5],[12,24,48],SESS4,ST):
    grid.append(dict(fam="momo",lb=lb,k=k,H=H,sess=sess,stopA=sp,tgtA=tp,limit=False))
for man,lb,H,sess,(sp,tp) in itertools.product([24,48,96],[3,6,12],[6,12,24,48],SESS4,ST):
    grid.append(dict(fam="pullback",man=man,lb=lb,H=H,sess=sess,stopA=sp,tgtA=tp,limit=True))
for rn,H,sess,(sp,tp) in itertools.product([24,48,96],[12,24,48],SESS4,ST[:5]):
    grid.append(dict(fam="breakout",rn=rn,H=H,sess=sess,stopA=sp,tgtA=tp,limit=False))
for k,H,sess,(sp,tp) in itertools.product([1.5,2.0,3.0],[12,24,48],SESS4,ST[:5]):
    grid.append(dict(fam="volspike",k=k,H=H,sess=sess,stopA=sp,tgtA=tp,limit=False))
print(f"{ROOT}: grid {len(grid)} configs", flush=True)

df=pd.read_csv(f"/home/user/FutureTradingBot/data/polygon/{ROOT}_5min.csv"); df["ts"]=pd.to_datetime(df.ts,utc=True)
df=df[df.ts<=T1].sort_values("ts").reset_index(drop=True)
tr=np.maximum(df.high-df.low,(df.close-df.close.shift(1)).abs())
F={"c":df.close.values,"o":df.open.values,"atr":tr.rolling(14).mean().values}
for lb in {c.get("lb") for c in grid if c.get("lb")}: F[f"mom{lb}"]=(df.close-df.close.shift(lb)).values
for n in {c.get("man") for c in grid if c.get("man")}: F[f"ma{n}"]=df.close.rolling(n).mean().values
for n in {c.get("rn") for c in grid if c.get("rn")}:
    F[f"rmax{n}"]=df.high.rolling(n).max().values; F[f"rmin{n}"]=df.low.rolling(n).min().values
v=df.volume; F["volz"]=((v-v.rolling(48).mean())/(v.rolling(48).std(ddof=0)+1e-9)).values
ts=df.ts; cdt=(ts+pd.Timedelta(minutes=5)).dt.tz_convert(None)
nh=(cdt.dt.hour+(cdt.dt.minute+0.75)/60).values
mkt=np.array([be.market_open(d.to_pydatetime()+pd.Timedelta(seconds=45)) for d in cdt])
H_=df.high.values; L_=df.low.values; C_=df.close.values; O_=df.open.values
# (pv, tick, commission/RT) — engine map for deployed roots; micro-
# contract economics for new markets (PROVISIONAL commissions, verify
# against the broker before any deployment)
EXT = {
    "NQ":  (2.0,     0.25,       1.80),   # trade as MNQ
    "ZN":  (1000.0,  0.015625,   4.50),
    "ZF":  (1000.0,  0.0078125,  4.50),
    "ZT":  (2000.0,  0.00390625, 4.50),
    "6E":  (12500.0, 0.0001,     1.60),   # trade as M6E
    "6B":  (6250.0,  0.0001,     1.60),   # M6B
    "6A":  (10000.0, 0.0001,     1.60),   # M6A
    "MBT": (0.1,     5.0,        2.20),
    "ETH": (0.1,     0.25,       2.20),   # trade as micro ether
    "SI":  (1000.0,  0.005,      2.20),   # trade as SIL (micro silver)
    "HG":  (2500.0,  0.0005,     2.20),   # trade as MHG (micro copper)
    "HO":  (42000.0, 0.0001,     4.50),   # FULL size - margin check before any deploy
    "RB":  (42000.0, 0.0001,     4.50),   # FULL size - margin check before any deploy
}
if ROOT in be.PV:
    PV, tick, COMM = be.PV[ROOT], be.TICKS[ROOT], be.COMM.get(ROOT, 1.80)
elif ROOT in EXT:
    PV, tick, COMM = EXT[ROOT]
else:
    raise SystemExit(f"no contract spec for {ROOT}")
warm_end = ts.iloc[0] + pd.Timedelta(days=7)
n=len(df)
# in-session mask per session key
sessmask={s: ((nh>=be.SESS[s][0]) & (nh<be.SESS[s][1])) for s in SESS4}
eod_exit_m = (nh>=be.EOD_UTC)&(nh<be.REOPEN_UTC)
eod_block_m = (nh>=be.EOD_UTC-0.5)&(nh<be.REOPEN_UTC)
by_sess = {s:[j for j,c in enumerate(grid) if c["sess"]==s] for s in SESS4}
state=[dict(pos=0,pend=None,cd=0,bh=0,epx=None,ei=None,stop=None,tgt=None) for _ in grid]
active=set()
trades=[[] for _ in grid]
def rnd(px): return round(round(px/tick)*tick,10)
def sig(cfg,i,c,o):
    a=F["atr"][i]
    if not np.isfinite(a) or a<=0: return 0,a
    fam=cfg["fam"]
    if fam in("fade","momo"):
        m=F[f"mom{cfg['lb']}"][i]
        if not np.isfinite(m) or abs(m)<=cfg["k"]*a: return 0,a
        return ((1 if m<0 else -1) if fam=="fade" else (1 if m>0 else -1)),a
    if fam=="breakout":
        if c>=F[f"rmax{cfg['rn']}"][i]-1e-9: return 1,a
        if c<=F[f"rmin{cfg['rn']}"][i]+1e-9: return -1,a
        return 0,a
    if fam=="pullback":
        ma=F[f"ma{cfg['man']}"][i]; m=F[f"mom{cfg['lb']}"][i]
        if not (np.isfinite(ma) and np.isfinite(m)): return 0,a
        if c>ma and m<0: return 1,a
        if c<ma and m>0: return -1,a
        return 0,a
    z=F["volz"][i]
    return ((1 if c>o else -1),a) if (np.isfinite(z) and z>cfg["k"]) else (0,a)
for i in range(n):
    h,l,c,o=H_[i],L_[i],C_[i],O_[i]; open_mkt=mkt[i]
    eod_x=eod_exit_m[i]; eod_b=eod_block_m[i]
    # stateful configs first
    for j in list(active):
        s=state[j]; cfg=grid[j]
        if s["pend"]:
            p=s["pend"]
            if (l<=p["px"]) if p["side"]>0 else (h>=p["px"]):
                s.update(pos=p["side"],epx=p["px"],ei=i,bh=0,cd=cfg["H"],stop=p["sp"],tgt=p["tp"],pend=None)
        if s["pos"]:
            px=None
            if s["stop"] is not None and ((s["pos"]>0 and l<=s["stop"]) or (s["pos"]<0 and h>=s["stop"])): px=s["stop"]
            elif s["tgt"] is not None and ((s["pos"]>0 and h>=s["tgt"]) or (s["pos"]<0 and l<=s["tgt"])): px=s["tgt"]
            if px is not None:
                trades[j].append((s["ei"],i,s["pos"],s["epx"],px)); s.update(pos=0,stop=None,tgt=None)
        if s["cd"]>0: s["cd"]-=1
        if s["pos"]:
            s["bh"]+=1
            if s["bh"]>=cfg["H"] or eod_x:
                trades[j].append((s["ei"],i,s["pos"],s["epx"],c-tick*s["pos"])); s.update(pos=0,stop=None,tgt=None)
        elif s["pend"]:
            s["pend"]["ttl"]-=1
            if s["pend"]["ttl"]<=0: s["pend"]=None
        if not (s["pos"] or s["pend"] or s["cd"]>0):
            active.discard(j)
    # new entries
    if open_mkt and not eod_b:
        for skey in SESS4:
            if not sessmask[skey][i]: continue
            for j in by_sess[skey]:
                s=state[j]
                if s["pos"] or s["pend"] or s["cd"]>0: continue
                cfg=grid[j]
                side,a=sig(cfg,i,c,o)
                if side==0: continue
                off=0.5*a*side if cfg.get("limit") else 0.0
                px=rnd(c-off)
                sp=rnd(px-cfg["stopA"]*a*side) if cfg.get("stopA") else None
                tp=rnd(px+cfg["tgtA"]*a*side) if cfg.get("tgtA") else None
                s["pend"]=dict(px=px,side=side,ttl=3,sp=sp,tp=tp)
                active.add(j)
    if i % 40000 == 0: print(f"  {ROOT} {i}/{n} active={len(active)}", flush=True)
# score
passers=[]
for j,cfg in enumerate(grid):
    rows=[t for t in trades[j] if ts.iloc[t[0]]>warm_end]
    if len(rows)<300: continue
    pnl=np.array([(xp-ep)*sd*PV-COMM for (ei,xi,sd,ep,xp) in rows])
    et=ts.iloc[[r[0] for r in rows]].reset_index(drop=True)
    xt=ts.iloc[[r[1] for r in rows]].reset_index(drop=True)
    d=pd.DataFrame(dict(pnl=pnl,et=et,xt=xt))
    tr_=d[d.et<TRAIN_END]
    if len(tr_)<200 or tr_.pnl.sum()<=0: continue
    wv=tr_.groupby(tr_.xt.dt.strftime("%G-W%V")).pnl.sum()
    if (wv>0).mean()<0.70 or wv.mean()<150: continue
    bad=False
    for y,g in tr_.groupby(tr_.xt.dt.year):
        if g.pnl.sum()<=0: bad=True
    if bad: continue
    o10=d[d.et>=W10]; o3=d[d.et>=W3]
    if not len(o10) or o10.pnl.sum()<=0 or not len(o3) or o3.pnl.sum()<=0: continue
    w10=o10.groupby(o10.xt.dt.strftime("%G-W%V")).pnl.sum()
    dv=tr_.groupby(tr_.xt.dt.date).pnl.sum()
    passers.append(dict(cfg=cfg, train_wk=round(wv.mean()), train_poswk=round(100*(wv>0).mean()),
        train_worst_wk=round(wv.min()), train_worst_day=round(dv.min()),
        n_train_wks=len(wv), oos10_wk=round(w10.mean()), oos10_pos=round(100*(w10>0).mean()),
        oos3_net=round(o3.pnl.sum()), tr_wk=round(len(d)/max(1,len(wv)),1)))
passers.sort(key=lambda r:-min(r["train_wk"], r["oos10_wk"]))
json.dump(dict(root=ROOT,n_grid=len(grid),n_pass=len(passers),passers=passers[:80]),
          open(OUT,"w"), indent=1)
print(f"{ROOT}: {len(passers)} PASS  -> {OUT}", flush=True)
for r in passers[:6]:
    c=r["cfg"]
    print(f"  {c['fam']:<9} H={c['H']:<3} {c['sess']:<5} lb={c.get('lb')} k={c.get('k')} man={c.get('man')} rn={c.get('rn')} SL{c['stopA']} TP{c['tgtA']} "
          f"train ${r['train_wk']}/wk {r['train_poswk']}% | oos10 ${r['oos10_wk']}/wk {r['oos10_pos']}% | 3wk ${r['oos3_net']} | {r['tr_wk']}tr/wk", flush=True)

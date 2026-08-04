"""PERPETUAL CONTINUOUS-PARAMETER HUNTER.

Two things a grid cannot do, both of which have cost us:

  CONTINUOUS PARAMETERS. A grid tests fixed points -- pullback 0.2, 0.35, 0.5.
  The best config has landed at or outside a grid boundary three separate
  times, which means the answer sits between the points we test. This samples
  real values and then walks downhill from whatever it finds, so no value is
  unreachable and no boundary is invisible.

  IT NEVER FINISHES. Every run picks a market and timeframe, hunts from fresh
  random seeds, and appends anything good to a leaderboard that persists in the
  repo. Run it again and it keeps going from where the record stands. Stop it
  by disabling the workflow; nothing else ends it.

Scoring is the account's, not the P&L's: risk per trade, drawdown, worst week
and green-week rate are constraints, and weekly dollars only ranks survivors.
"""
import json, os, sys, time, gzip
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from econ import ECON
REPO = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "hunter_board.json")
BUDGET = float(os.environ.get("HUNT_SECONDS", "600"))
SEED = int(os.environ.get("HUNT_SEED", "0"))
ACCT = 4100.0
MAXRISK = float(os.environ.get("M2_MAXRISK", "30"))
MAXDD = float(os.environ.get("M2_MAXDD", "800"))
MINGREEN = float(os.environ.get("M2_MINGREEN", "0.60"))
SLIP = float(os.environ.get("HUNT_SLIP", "1.0"))   # ticks charged on stop/time exits
# every market whose 2xATR stop fits the account, cheapest risk first
POOL = os.environ.get("HUNT_MARKETS", "RTY,YM,CL,HG,ES,NG,6E,6B,6A,MBT,ETH,ZF,ZT").split(",")
rng = np.random.default_rng(SEED if SEED else None)

def load(root, tf):
    pv, tick, comm, traded, marg, aff = ECON[root]
    d = pd.read_csv(f"{REPO}/data/polygon/{root}_5min.csv")
    d["ts"] = pd.to_datetime(d.ts, utc=True)
    if tf != 5:
        d = (d.set_index("ts").resample(f"{tf}min", label="left", closed="left")
             .agg(open=("open", "first"), high=("high", "max"),
                  low=("low", "min"), close=("close", "last"))
             .dropna(subset=["close"]).reset_index())
    d = d.sort_values("ts").reset_index(drop=True)
    C = d.close.values.astype(float); H = d.high.values.astype(float)
    L = d.low.values.astype(float); n = len(C)
    a = pd.Series(np.abs(np.r_[0, np.diff(C)]) / tick).rolling(50, min_periods=20).mean().values
    hr = (d.ts.dt.hour + d.ts.dt.minute / 60.0).values
    gapc = pd.Series((d.ts.diff() > pd.Timedelta("3h")).values).rolling(60, min_periods=1).max().fillna(0).values.astype(bool)
    ok = np.isfinite(a) & (a > 0) & ~gapc & ~((hr >= 21.0) & (hr < 22.5))
    P = 300
    return dict(root=root, tf=tf, traded=traded, dpt=pv * tick, tick=tick, comm=comm,
                C=C, Hp=np.r_[H, np.full(P, np.nan)], Lp=np.r_[L, np.full(P, np.nan)],
                Cp=np.r_[C, np.full(P, np.nan)], ATR=a, hr=hr, OK=ok, n=n,
                day=pd.factorize(d.ts.dt.date)[0], wk=pd.factorize(d.ts.dt.strftime("%G-W%V"))[0],
                wks=d.ts.dt.date.nunique() / 5.0, cut=int(n * 0.75))

REJC={}
def REJ(w):
    REJC[w]=REJC.get(w,0)+1; return None

def evaluate(M, p):
    """One continuous parameter vector -> the account's view of it."""
    C, ATR, n, tick, dpt = M["C"], M["ATR"], M["n"], M["tick"], M["dpt"]
    lb = int(round(p["lb"]))
    mom = np.r_[np.full(lb, np.nan), (C[lb:] - C[:-lb]) / tick]
    sig = M["OK"] & np.isfinite(mom) & (np.abs(mom) > p["k"] * ATR)
    sig[:max(lb, 60)] = False; sig[n - 200:] = False
    if p["sess"] == 1: sig &= (M["hr"] >= 13.5) & (M["hr"] < 20.0)
    elif p["sess"] == 2: sig &= (M["hr"] >= 7.0) & (M["hr"] < 13.5)
    elif p["sess"] == 3: sig &= (M["hr"] >= 13.5) & (M["hr"] < 16.0)
    idx = np.where(sig)[0]
    if len(idx) < 200: return REJ('signal')
    side = int(p["dirn"]) * np.sign(mom[idx]).astype(np.int64)
    lim = C[idx] - (p["pb"] * np.abs(mom[idx]) * tick) * side
    ttl = int(round(p["ttl"]))
    st = np.arange(1, ttl + 1); bars = idx[:, None] + st[None, :]
    adv = np.where(side[:, None] > 0, M["Lp"][bars], M["Hp"][bars])
    thr = (adv * side[:, None]) <= (lim * side)[:, None] - tick + 1e-9
    j = np.where(thr.any(1), thr.argmax(1), 10**9); ok = j < 10**9
    if ok.sum() < 200: return REJ('fills')
    fb = idx[ok] + 1 + j[ok]; sd = side[ok]; ep = lim[ok]; av = ATR[idx][ok]
    stk = np.maximum(p["sp"] * av, 2.0)
    risk = float(np.median(stk) * dpt)
    if risk > MAXRISK: return REJ('risk')
    hold = int(round(p["hold"]))
    js = np.arange(0, hold + 1); wb = fb[:, None] + js[None, :]
    g = sd[:, None].astype(float)
    lo = np.where(g > 0, M["Lp"][wb], M["Hp"][wb]) * g
    hi = np.where(g > 0, M["Hp"][wb], M["Lp"][wb]) * g
    cw = M["Cp"][wb]; ar = np.arange(len(fb)); eps = ep * sd
    sl = eps - stk * tick; tp = eps + p["rr"] * stk * tick
    hs = lo <= sl[:, None]; ht = hi >= tp[:, None]; ht[:, 0] = False
    j1 = np.where(hs.any(1), hs.argmax(1), 10**9); j2 = np.where(ht.any(1), ht.argmax(1), 10**9)
    ks_ = j1 <= np.minimum(j2, hold); kt = (~ks_) & (j2 <= hold)
    xj = np.where(ks_, np.minimum(j1, hold), np.where(kt, np.minimum(j2, hold), hold))
    xp = np.where(ks_, (sl - SLIP*tick) * sd, np.where(kt, tp * sd,
                  cw[ar, np.minimum(xj, hold)] - SLIP*tick * sd))
    gd = np.isfinite(xp)
    if gd.sum() < 200: return REJ('fills')
    pl = (xp[gd] - ep[gd]) * sd[gd] * (1 / tick) * dpt - M["comm"]*float(os.environ.get("HUNT_COMMMULT","1.0"))
    F = fb[gd]; X = fb[gd] + xj[gd]
    o = np.argsort(F); pl, F, X = pl[o], F[o], X[o]
    mp = int(round(p["maxpos"]))
    free = np.zeros(mp, dtype=np.int64); took = np.zeros(len(pl), bool)
    for i in range(len(pl)):          # a trade only happens if a slot is free
        s_ = int(np.argmin(free))
        if free[s_] <= F[i]: took[i] = True; free[s_] = X[i]
    pl, F = pl[took], F[took]
    if len(pl) < 120: return REJ('trades')
    eq = np.cumsum(pl); dd = float((eq - np.maximum.accumulate(eq)).min())
    if dd < -MAXDD: return REJ('drawdown')
    ds = np.bincount(M["day"][np.clip(F, 0, n - 1)], weights=pl)
    ws = np.bincount(M["wk"][np.clip(F, 0, n - 1)], weights=pl)
    ds = ds[ds != 0]; ws = ws[ws != 0]
    gw = float((ws > 0).mean())
    if gw < MINGREEN: return REJ('green')
    m = F < M["cut"]
    if m.sum() < 80 or (~m).sum() < 30: return REJ('too_few_in_split')
    # The one statistic that tells us whether an edge exists at all: of the
    # configs that made money in training, what share also made money in the
    # holdout? Chance says 50%. Materially above that is real signal; at or
    # below it, the search is mining noise however many configs it tests.
    if pl[m].mean() > 0:
        REJ('_train_positive')
        if pl[~m].mean() > 0: REJ('_and_holdout_positive')
        else: return REJ('holdout_negative')
    else:
        return REJ('train_negative')
    s = 0; mx = 0
    for q in pl:
        s = s + 1 if q <= 0 else 0; mx = max(mx, s)
    return dict(mkt=M["root"], traded=M["traded"], tf=M["tf"], risk=round(risk, 1),
                tpw=round(len(pl) / M["wks"], 1), wr=round(float((pl > 0).mean()), 4),
                wkly=round(float(pl.sum() / M["wks"]), 1), maxdd=round(dd, 0),
                worst_day=round(float(ds.min()), 0), worst_wk=round(float(ws.min()), 0),
                green_wk=round(gw, 3), green_day=round(float((ds > 0).mean()), 3),
                streak=int(mx), tr=round(float(pl[m].mean()), 3),
                ho=round(float(pl[~m].mean()), 3), n=int(len(pl)),
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()})

def draw():
    return dict(lb=float(rng.integers(1, 40)), k=float(rng.uniform(0.3, 4.0)),
                pb=float(rng.uniform(0.05, 2.0)), ttl=float(rng.integers(1, 20)),
                sp=float(rng.uniform(0.2, 12.0)), rr=float(rng.uniform(1.5, 2.0)),
                hold=float(rng.integers(1, 80)), sess=int(rng.integers(0, 4)),
                dirn=int(rng.choice([-1, 1])), maxpos=int(rng.integers(1, 4)))

def jitter(p, s):
    q = dict(p)
    for key, lo, hi in (("lb",1,40),("k",0.3,4.0),("pb",0.05,2.0),("ttl",1,20),
                        ("sp",0.2,12.0),("rr",1.5,2.0),("hold",1,80)):
        q[key] = float(np.clip(p[key] + rng.normal(0, s * (hi - lo)), lo, hi))
    if rng.random() < 0.2 * s * 10: q["sess"] = int(rng.integers(0, 4))
    if rng.random() < 0.1 * s * 10: q["maxpos"] = int(rng.integers(1, 4))
    return q

board = json.load(open(BOARD)) if os.path.exists(BOARD) else {"best": [], "runs": 0, "evals": 0}
# One market and timeframe per run. Loading a CSV on every draw was most of the
# wall clock; a run now spends its whole budget searching instead of reading.
ROOT = os.environ.get("HUNT_MARKET") or str(rng.choice(POOL))
TFR = int(os.environ.get("HUNT_TF") or rng.choice([1, 5, 15]))
cache = {"M": load(ROOT, TFR)}
print(f"hunting {ROOT} tf{TFR} for {BUDGET:.0f}s "
      f"(risk<=${MAXRISK:.0f}, dd<=${MAXDD:.0f}, green>={MINGREEN:.0%})", flush=True)
t0 = time.time(); found = []; ev = 0
rej = {"signal":0,"fills":0,"risk":0,"trades":0,"drawdown":0,"green":0,"split":0,"ok":0}
while time.time() - t0 < BUDGET:
    M = cache["M"]
    p = draw(); r = evaluate(M, p); ev += 1
    if r is None: continue
    found.append(r)
    # walk downhill from anything that survived -- this is what a grid cannot do
    best, bp, s = r, p, 0.06
    for _ in range(40):
        if time.time() - t0 > BUDGET: break
        q = jitter(bp, s); rq = evaluate(M, q); ev += 1
        if rq and rq["wkly"] > best["wkly"]:
            best, bp = rq, q; found.append(rq)
        else: s *= 0.85
    print(f"  {root} tf{tf}: ${best['wkly']:.0f}/wk {best['tpw']:.0f}tr "
          f"{best['wr']*100:.0f}%wr dd${best['maxdd']:.0f} risk${best['risk']:.0f}", flush=True)
board["runs"] += 1; board["evals"] += ev
allb = board["best"] + found
seen = set(); ded = []
for r in sorted(allb, key=lambda x: -x["wkly"]):
    kk = (r["mkt"], r["tf"], round(r["lb"]), round(r["k"], 1), round(r["pb"], 2),
          round(r["sp"], 1), r["maxpos"])
    if kk in seen: continue
    seen.add(kk); ded.append(r)
board["best"] = ded[:300]
json.dump(board, open(BOARD, "w"), indent=1)
print("\nwhy candidates died: " + "  ".join(f"{k}={v:,}" for k,v in
      sorted(REJC.items(), key=lambda x:-x[1])))
print(f"run {board['runs']}: {ev:,} evaluations, {len(found)} survived "
      f"({board['evals']:,} evaluations all-time)")
if board["best"]:
    b = pd.DataFrame(board["best"][:10])
    print(b[["mkt","tf","risk","tpw","wr","wkly","maxdd","worst_wk","green_wk",
             "streak","ho","maxpos"]].to_string(index=False))

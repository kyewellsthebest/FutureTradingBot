"""ONE STRATEGY, EVERY MARKET.

The cap is four strategies. That has been read as four books, which puts a
hard ceiling on trade count: the configs that survive fire five to seven times
a week, so four of them is thirty trades a week against a target of five
hundred. Read the cap the other way and the ceiling moves. A single parameter
vector run on fifteen markets is still one strategy -- one rule, one thing to
monitor, one thing that can break -- and it fires fifteen times as often.

It is also much harder to fool. Tuning fifteen separate configs finds fifteen
separate accidents. Requiring one vector to work everywhere at once is a
brutal filter, and anything that clears it is far more likely to be structure
than noise. Every parameter in the search is already dimensionless (multiples
of ATR) or measured in bars, so the same vector means the same thing on
Russell as it does on copper.

The capital constraint is applied ONCE, across the merged book. That is what
the account actually experiences: a position slot taken by copper is not
available to the Russell, whatever the per-market backtest says.

Usage: python multi.py [SECONDS] [TF]
"""
import os, sys, json, time, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from econ import ECON

src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)

SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 5
MKTS = os.environ.get("MULTI_MARKETS",
                      "RTY,YM,CL,HG,ES,NG,6E,6B,6A,MBT,ETH,ZF,ZT,ZC,ZW").split(",")
SLIP = float(os.environ.get("HUNT_SLIP", "1.0"))
COMMX = float(os.environ.get("HUNT_COMMMULT", "1.0"))
MAXRISK = float(os.environ.get("M2_MAXRISK", "30"))
MAXDD = float(os.environ.get("M2_MAXDD", "1200"))
MINGREEN = float(os.environ.get("M2_MINGREEN", "0.55"))
MAXPOS = int(os.environ.get("MULTI_MAXPOS", "4"))
BOARD = os.path.join(HERE, "multi_board.json")
rng = np.random.default_rng()

print(f"loading {len(MKTS)} markets at tf{TF} ...", flush=True)
MS = {}
for m in MKTS:
    try:
        MS[m] = H.load(m, TF)
    except Exception as e:
        print(f"  skip {m}: {e}")
print(f"loaded {len(MS)}: {', '.join(MS)}", flush=True)

# One shared calendar, so weeks line up across markets that trade different hours
ALLTS = np.concatenate([M["ts"] for M in MS.values()])
T0 = int(ALLTS.min()); T1 = int(ALLTS.max())
CUT = T0 + int((T1 - T0) * 0.75)              # chronological train / holdout
WKS = (T1 - T0) / (7 * 86400) * (5 / 7)       # trading weeks, roughly


def trades(M, p):
    """Every trade this vector would take on this market. Time-stamped, gross."""
    C, ATR, n, tick, dpt = M["C"], M["ATR"], M["n"], M["tick"], M["dpt"]
    idx, side, ref = H.signal(M, p)
    if len(idx) < 30: return None
    lim = C[idx] - (p["pb"] * ref * tick) * side
    ttl = int(round(p["ttl"]))
    st = np.arange(1, ttl + 1); bars = idx[:, None] + st[None, :]
    adv = np.where(side[:, None] > 0, M["Lp"][bars], M["Hp"][bars])
    thr = (adv * side[:, None]) <= (lim * side)[:, None] - tick + 1e-9
    j = np.where(thr.any(1), thr.argmax(1), 10**9); ok = j < 10**9
    if ok.sum() < 30: return None
    fb = idx[ok] + 1 + j[ok]; sd = side[ok]; ep = lim[ok]; av = ATR[idx][ok]
    stk = np.maximum(p["sp"] * av, 2.0)
    risk = float(np.median(stk) * dpt)
    # Each market must clear the per-trade risk cap on its own. A cheap market
    # cannot subsidise one whose stop costs three times the account's limit.
    if risk > MAXRISK: return None
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
    xp = np.where(ks_, (sl - SLIP * tick) * sd, np.where(kt, tp * sd,
                  cw[ar, np.minimum(xj, hold)] - SLIP * tick * sd))
    gd = np.isfinite(xp)
    if gd.sum() < 30: return None
    pl = (xp[gd] - ep[gd]) * sd[gd] * (1 / tick) * dpt - M["comm"] * COMMX
    fbi = fb[gd]; xbi = np.minimum(fb[gd] + xj[gd], n - 1)
    return (M["ts"][np.minimum(fbi, n - 1)], M["ts"][xbi], pl, risk)


def evaluate(p):
    """The same vector on every market, merged into one account."""
    fs, xs, ps, mk = [], [], [], []
    rsk = []
    for name, M in MS.items():
        r = trades(M, p)
        if r is None: continue
        fs.append(r[0]); xs.append(r[1]); ps.append(r[2])
        mk.append(np.full(len(r[2]), name)); rsk.append(r[3])
    if len(fs) < 3: return None                 # must work on at least 3 markets
    F = np.concatenate(fs); X = np.concatenate(xs)
    PL = np.concatenate(ps); MKn = np.concatenate(mk)
    o = np.argsort(F, kind="stable")
    F, X, PL, MKn = F[o], X[o], PL[o], MKn[o]
    # the account's one constraint, applied to the merged book
    free = np.zeros(MAXPOS, dtype=np.int64); took = np.zeros(len(PL), bool)
    for i in range(len(PL)):
        s_ = int(np.argmin(free))
        if free[s_] <= F[i]: took[i] = True; free[s_] = X[i]
    F, PL, MKn = F[took], PL[took], MKn[took]
    if len(PL) < 200: return None
    eq = np.cumsum(PL); dd = float((eq - np.maximum.accumulate(eq)).min())
    if dd < -MAXDD: return None
    wkid = (F - T0) // (7 * 86400)
    ws = pd.Series(PL).groupby(wkid).sum().values
    if len(ws) < 20: return None
    gw = float((ws > 0).mean())
    if gw < MINGREEN: return None
    m = F < CUT
    if m.sum() < 120 or (~m).sum() < 60: return None
    if PL[m].mean() <= 0: return None
    s = 0; mx = 0
    for q in PL:
        s = s + 1 if q <= 0 else 0; mx = max(mx, s)
    per = pd.Series(PL).groupby(MKn).agg(["size", "sum"])
    return dict(mech=p["mech"], tpw=round(len(PL) / WKS, 1),
                wkly=round(float(PL.sum() / WKS), 1),
                wr=round(float((PL > 0).mean()), 4), maxdd=round(dd, 0),
                worst_wk=round(float(ws.min()), 0), green_wk=round(gw, 3),
                streak=int(mx), n=int(len(PL)), nmkt=int(len(set(MKn))),
                risk=round(float(np.median(rsk)), 1),
                tr=round(float(PL[m].mean()), 3), ho=round(float(PL[~m].mean()), 3),
                ho_wkly=round(float(PL[~m].sum() / (WKS * 0.25)), 1),
                mkts=";".join(f"{k}:{int(v['size'])}" for k, v in per.iterrows()),
                slip=SLIP, commx=COMMX, tf=TF,
                **{k: (round(v, 4) if isinstance(v, float) else v)
                   for k, v in p.items() if k != "mech"})


board = json.load(open(BOARD)) if os.path.exists(BOARD) else {"best": [], "runs": 0, "evals": 0}
print(f"searching one-vector-all-markets for {SECS:.0f}s "
      f"(<=${MAXRISK:.0f}/trade, <=${MAXDD:.0f} drawdown, {MAXPOS} positions, "
      f"slip {SLIP}tk, comm x{COMMX})", flush=True)
t0 = time.time(); found = []; ev = 0
while time.time() - t0 < SECS:
    p = H.draw(); p["maxpos"] = MAXPOS
    r = evaluate(p); ev += 1
    if r is None: continue
    best, bp, s = r, p, 0.06
    for _ in range(25):
        if time.time() - t0 > SECS: break
        q = H.jitter(bp, s); q["maxpos"] = MAXPOS
        rq = evaluate(q); ev += 1
        if rq and rq["wkly"] > best["wkly"]: best, bp = rq, q; found.append(rq)
        else: s *= 0.85
    found.append(best)
    print(f"  {best['mech']}: ${best['wkly']:.0f}/wk  {best['tpw']:.0f} trades/wk  "
          f"{best['wr']*100:.0f}% win  {best['nmkt']} markets  dd ${best['maxdd']:.0f}",
          flush=True)

board["runs"] += 1; board["evals"] += ev
allb = [r for r in board["best"] if r.get("slip") == SLIP and r.get("commx") == COMMX] + found
seen = set(); ded = []
for r in sorted(allb, key=lambda x: -x["wkly"]):
    kk = (r["mech"], r["tf"], round(r["lb"]), round(r["k"], 1), round(r["pb"], 2),
          round(r["sp"], 1), round(r["rr"], 1))
    if kk in seen: continue
    seen.add(kk); ded.append(r)
board["best"] = ded[:200]
json.dump(board, open(BOARD, "w"), indent=1)
print(f"\nrun {board['runs']}: {ev:,} vectors, {len(found)} survived "
      f"({board['evals']:,} all-time)")
if board["best"]:
    b = pd.DataFrame(board["best"][:12])
    print(b[["mech", "tf", "nmkt", "risk", "tpw", "wr", "wkly", "ho_wkly", "maxdd",
             "worst_wk", "green_wk", "streak"]].to_string(index=False))

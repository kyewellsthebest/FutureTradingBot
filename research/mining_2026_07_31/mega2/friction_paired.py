"""How much of the edge does friction eat? Paired, on identical trades.

The first attempt at this ran the four cost settings as four sequential
searches. They drew different random vectors, and worse, the engine was being
edited between them, so the cheapest setting silently got six mechanisms the
others never saw. The comparison measured the edit, not the friction.

This cannot make that mistake. Each drawn vector produces ONE book of trades,
and the four cost settings are applied to that same book afterwards. Both
costs decompose exactly -- commission is a flat charge per trade, and exit
slippage is a flat charge on the trades that leave via stop or timeout -- so
nothing has to be re-simulated and nothing can drift between conditions.

Paired comparison is also far more sensitive: the difference between two cost
settings on the same trades has none of the variance that separate searches
would introduce.

Usage: python friction_paired.py MARKET [TF] [SECONDS]
"""
import os, sys, time, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)

MKT = sys.argv[1] if len(sys.argv) > 1 else "RTY"
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 5
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 300.0
MAXRISK = float(os.environ.get("M2_MAXRISK", "30"))

M = H.load(MKT, TF)
tick, dpt, comm = M["tick"], M["dpt"], M["comm"]

# slippage ticks on stop/time exits, commission multiple
CONDS = [("full cost today", 1.0, 1.0),
         ("no exit slippage", 0.0, 1.0),
         ("no commission", 1.0, 0.0),
         ("lifetime plan + stop-limit", 0.4, 0.51),
         ("frictionless", 0.0, 0.0)]


def book(p):
    """Trades gross of everything, plus a flag for which exits pay slippage."""
    C, ATR, n = M["C"], M["ATR"], M["n"]
    idx, side, ref = H.signal(M, p)
    if len(idx) < 100: return None
    lim = C[idx] - (p["pb"] * ref * tick) * side
    ttl = int(round(p["ttl"]))
    st = np.arange(1, ttl + 1); bars = idx[:, None] + st[None, :]
    adv = np.where(side[:, None] > 0, M["Lp"][bars], M["Hp"][bars])
    thr = (adv * side[:, None]) <= (lim * side)[:, None] - tick + 1e-9
    j = np.where(thr.any(1), thr.argmax(1), 10**9); ok = j < 10**9
    if ok.sum() < 100: return None
    fb = idx[ok] + 1 + j[ok]; sd = side[ok]; ep = lim[ok]; av = ATR[idx][ok]
    stk = np.maximum(p["sp"] * av, 2.0)
    if float(np.median(stk) * dpt) > MAXRISK: return None
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
    xp = np.where(ks_, sl * sd, np.where(kt, tp * sd, cw[ar, np.minimum(xj, hold)]))
    gd = np.isfinite(xp)
    if gd.sum() < 100: return None
    gross = (xp[gd] - ep[gd]) * sd[gd] * (1 / tick) * dpt
    slipped = ~kt[gd]                 # target exits are limit fills; the rest pay
    F = fb[gd]; X = fb[gd] + xj[gd]
    o = np.argsort(F)
    gross, slipped, F, X = gross[o], slipped[o], F[o], X[o]
    mp = int(round(p["maxpos"]))
    free = np.zeros(mp, dtype=np.int64); took = np.zeros(len(gross), bool)
    for i in range(len(gross)):
        s_ = int(np.argmin(free))
        if free[s_] <= F[i]: took[i] = True; free[s_] = X[i]
    gross, slipped, F = gross[took], slipped[took], F[took]
    if len(gross) < 100: return None
    m = F < M["cut"]
    if m.sum() < 60 or (~m).sum() < 30: return None
    return p["mech"], gross, slipped, m


rows = []
t0 = time.time()
n_draw = 0
while time.time() - t0 < SECS:
    p = H.draw(); n_draw += 1
    b = book(p)
    if b is None: continue
    mech, gross, slipped, m = b
    for name, slip, cx in CONDS:
        pl = gross - slip * dpt * slipped - comm * cx
        rows.append(dict(cond=name, mech=mech, tpw=len(pl) / M["wks"],
                         tr=float(pl[m].mean()), ho=float(pl[~m].mean()),
                         trpos=bool(pl[m].mean() > 0),
                         both=bool(pl[m].mean() > 0 and pl[~m].mean() > 0)))

d = pd.DataFrame(rows)
if d.empty:
    print(f"{MKT} tf{TF}: no books from {n_draw:,} draws"); sys.exit(0)
nb = len(d) // len(CONDS)
print(f"\n{MKT} tf{TF}: {nb:,} books from {n_draw:,} draws, "
      f"each scored under {len(CONDS)} cost settings (identical trades)\n")
print(f"{'cost setting':>28s} {'made money in train':>20s} {'and in holdout':>15s} "
      f"{'mean train $/trade':>19s}")
for name, slip, cx in CONDS:
    g = d[d.cond == name]
    print(f"{name:>28s} {g.trpos.sum():>13,} /{len(g):5,} {g.both.sum():>15,} "
          f"{g.tr.mean():19.2f}")

# The number that separates 'no edge' from 'edge eaten by cost': of the books
# that made money in training, what share also made money in the holdout?
print("\nholdout persistence (chance is 50%):")
for name, slip, cx in CONDS:
    g = d[(d.cond == name) & d.trpos]
    if len(g) < 5: print(f"{name:>28s}  too few to say ({len(g)})"); continue
    sh = float(g.both.mean())
    print(f"{name:>28s}  {sh:.0%} of {len(g):,}")

print("\nby mechanism, at today's full cost:")
g = d[d.cond == "full cost today"]
print(g.groupby("mech").agg(books=("tr", "size"), med_tpw=("tpw", "median"),
                            train=("tr", "mean"), holdout=("ho", "mean"),
                            trpos=("trpos", "sum")).round(2).to_string())
d.to_csv(os.path.join(HERE, f"friction_{MKT}_{TF}.csv"), index=False)

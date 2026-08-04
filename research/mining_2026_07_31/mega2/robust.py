"""Is it an edge, or did it just work here, this once?

VWAP reversion on 60-minute RTY beats a random-entry control by \$36 a trade
out of sample and survives drift adjustment. That is one market and one
holdout window, which is exactly the amount of evidence needed to fool
somebody. 16,134 configs sharing a single history is not 16,134 independent
tests -- if mean reversion simply worked on the Russell between February and
July 2026, every one of those configs says so at once.

So: the SAME parameter vectors, drawn once, evaluated on every market at four
different train/holdout boundaries. Sixty cells. In each one, pick the best 5%
by training and read off the holdout, against a random-entry control run
through the identical procedure in the same cell.

A real edge wins most cells. Regime luck wins the cell it was found in.

Drawing the configs once and reusing them everywhere makes the comparison
paired: a mechanism that beats the control in a cell does so on the same
market, the same period and the same split as the control it beat.

Usage: python robust.py [N_CONFIGS] [TF] [SECONDS_PER_MARKET]
"""
import os, sys, time, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)

NCFG = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 60
MKTS = os.environ.get("ROB_MARKETS",
                      "RTY,YM,CL,HG,ES,NG,6E,6B,6A,MBT,ETH,ZF,ZT,ZC,ZW").split(",")
SPLITS = [0.5, 0.6, 0.7, 0.8]

rng = np.random.default_rng(20260804)
H.rng = rng
CFGS = []
while len(CFGS) < NCFG:
    p = H.draw(); p["maxpos"] = int(rng.integers(1, 5))
    CFGS.append(p)
print(f"{len(CFGS):,} parameter vectors, {len(MKTS)} markets, "
      f"{len(SPLITS)} split points = {len(MKTS)*len(SPLITS)} cells, tf{TF}\n",
      flush=True)


def book(M, p):
    """Trades for one config on one market: P&L, fill bar, exit bar, side."""
    C, ATR, n, tick, dpt = M["C"], M["ATR"], M["n"], M["tick"], M["dpt"]
    idx, side, ref = H.signal(M, p)
    if len(idx) < 80: return None
    lim = C[idx] - (p["pb"] * ref * tick) * side
    ttl = int(round(p["ttl"]))
    st = np.arange(1, ttl + 1); bars = idx[:, None] + st[None, :]
    adv = np.where(side[:, None] > 0, M["Lp"][bars], M["Hp"][bars])
    thr = (adv * side[:, None]) <= (lim * side)[:, None] - tick + 1e-9
    j = np.where(thr.any(1), thr.argmax(1), 10**9); ok = j < 10**9
    if ok.sum() < 80: return None
    fb = idx[ok] + 1 + j[ok]; sd = side[ok]; ep = lim[ok]; av = ATR[idx][ok]
    stk = np.maximum(p["sp"] * av, 2.0)
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
    if gd.sum() < 80: return None
    pl = (xp[gd] - ep[gd]) * sd[gd] * (1 / tick) * dpt
    F = fb[gd]; X = np.minimum(fb[gd] + xj[gd], n - 1); SD = sd[gd]
    o = np.argsort(F); pl, F, X, SD = pl[o], F[o], X[o], SD[o]
    mp = int(round(p["maxpos"]))
    free = np.zeros(mp, dtype=np.int64); took = np.zeros(len(pl), bool)
    for i in range(len(pl)):
        s_ = int(np.argmin(free))
        if free[s_] <= F[i]: took[i] = True; free[s_] = X[i]
    if took.sum() < 80: return None
    return pl[took], F[took], X[took], SD[took]


rows = []
for mk in MKTS:
    t0 = time.time()
    try:
        # The cross-market mechanism needs a leader, and without one it
        # silently yields no signals and no column -- which is how it went
        # untested. ES leads the equity complex; NQ leads ES itself.
        M = H.load(mk, TF, lead=("NQ" if mk == "ES" else "ES"))
    except Exception as e:
        print(f"  skip {mk}: {e}"); continue
    C, tick, dpt, n = M["C"], M["tick"], M["dpt"], M["n"]
    books = []
    for p in CFGS:
        b = book(M, p)
        if b is not None: books.append((p["mech"], b))
    for sp in SPLITS:
        cut = int(n * sp)
        recs = []
        for mech, (pl, F, X, SD) in books:
            m = F < cut
            if m.sum() < 50 or (~m).sum() < 30: continue
            # charge each split its own drift, so the holdout trend is removed
            # from holdout trades and the training trend from training trades
            dd = np.empty(len(pl))
            for sel, lo, hi in ((m, 0, cut), (~m, cut, n - 1)):
                dd[sel] = (C[hi] - C[lo]) / max(hi - lo, 1) / tick * dpt
            adj = pl - dd * (X - F) * SD
            recs.append(dict(mech=mech, tr=float(adj[m].mean()),
                             ho=float(adj[~m].mean())))
        if not recs: continue
        r = pd.DataFrame(recs)
        for mech, g in r.groupby("mech"):
            top = g.nlargest(max(3, len(g) // 20), "tr")
            rows.append(dict(mkt=mk, split=sp, mech=mech, n=len(g),
                             tr=float(top.tr.mean()), ho=float(top.ho.mean())))
    print(f"  {mk}: {len(books):,} books, {time.time()-t0:.0f}s", flush=True)

d = pd.DataFrame(rows)
if d.empty:
    print("no cells produced results"); sys.exit(0)
d.to_csv(os.path.join(HERE, f"robust_{TF}.csv"), index=False)

ctl = d[d.mech == "rnd"][["mkt", "split", "ho"]].rename(columns={"ho": "ctl"})
d = d.merge(ctl, on=["mkt", "split"], how="left")
d["beat"] = d.ho > d.ctl

print(f"\n{len(d)} mechanism-cells over {d.groupby(['mkt','split']).ngroups} "
      f"market/split cells, all drift-adjusted\n")
print(f"{'mech':>6s} {'cells':>6s} {'holdout $':>10s} {'control $':>10s} "
      f"{'beats control':>14s} {'holdout>0':>10s}")
for mech, g in d.groupby("mech"):
    print(f"{mech:>6s} {len(g):6d} {g.ho.mean():10.2f} {g.ctl.mean():10.2f} "
          f"{g.beat.mean():13.0%} {float((g.ho>0).mean()):10.0%}")

print("\nper market, holdout $/trade after drift (control in the last column):")
pv = d.pivot_table(index="mkt", columns="mech", values="ho", aggfunc="mean")
print(pv.round(1).to_string())

print("\nper split point:")
pv2 = d.pivot_table(index="split", columns="mech", values="ho", aggfunc="mean")
print(pv2.round(1).to_string())

# The single number that matters: does the best mechanism beat its control
# in most cells, or only in the one it was discovered in?
for mech in ("vwr", "rev", "imp", "xmk", "cal", "sqz", "orb", "gap", "vol"):
    g = d[d.mech == mech]
    if not len(g): continue
    w = int(g.beat.sum()); k = len(g)
    # sign test against a coin flip
    from math import comb
    p_val = sum(comb(k, i) for i in range(w, k + 1)) / 2 ** k
    print(f"\n{mech}: beats the control in {w} of {k} cells, "
          f"sign test p = {p_val:.4f}")

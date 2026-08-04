"""Search event bars from the raw tape, with exits resolved by the real path.

Two changes from every test before this one.

NO CLOCK. Bars close on activity -- N trades, N contracts, N points of range --
so each carries the same amount of information instead of the same amount of
time.

EXACT EXITS. When a bar touches both the stop and the target, which one filled
depends on which came first inside the bar. OHLC cannot say, so every backtest
here assumed the stop. The tape knows, and hi_first carries the answer, so the
ambiguity is resolved by fact rather than by convention. The run reports how
many trades that assumption was deciding, which is the size of the error we
have been carrying.

Everything else is deliberately unchanged from robust.py: the same mechanisms,
the same random-entry control, drift adjustment, several split points, and a
sign test across cells. If event bars and true paths matter, they show up as a
difference against a test that is otherwise identical.

Usage: python tick_robust.py [SERIES] [N_CONFIGS]
"""
import os, sys, time, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
EV = os.path.join(ROOT, "data", "tick", "ev")

src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)

SERIES = sys.argv[1] if len(sys.argv) > 1 else "vol_5000"
NCFG = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
ROOTSYM = (sys.argv[3] if len(sys.argv) > 3 else "NQ").upper()
SPLITS = [0.5, 0.6, 0.7, 0.8]
# Each root trades its own micro with its own tick value and commission --
# using NQ's numbers everywhere would misprice every other market's costs.
from econ import ECON
_pv, TICK, COMM, TRADED, _mg, _af = ECON[ROOTSYM]
DPT = _pv * TICK
NS = 1_000_000_000


def load_ev(name):
    d = pd.read_parquet(os.path.join(EV, f"{ROOTSYM}_{name}.parquet"))
    d = d.sort_values("ts").reset_index(drop=True)
    C = d.close.values.astype(float); Hh = d.high.values.astype(float)
    L = d.low.values.astype(float); n = len(C)
    V = d.vol.values.astype(float)
    a = pd.Series(np.abs(np.r_[0, np.diff(C)]) / TICK).rolling(50, min_periods=20).mean().values
    esec = (d.ts.values // NS).astype(np.int64)
    ts = pd.to_datetime(esec, unit="s", utc=True)
    hr = (ts.hour + ts.minute / 60.0).values
    day = pd.factorize((esec + 2 * 3600) // 86400)[0]
    # a contract roll is a discontinuity; never let a bar span one
    roll = np.r_[False, d.contract.values[1:] != d.contract.values[:-1]]
    bad = pd.Series(roll).rolling(60, min_periods=1).max().fillna(0).values.astype(bool)
    ok = np.isfinite(a) & (a > 0) & ~bad
    tp = (Hh + L + C) / 3.0
    g = pd.DataFrame({"d": day, "pv": tp * V, "v": V}).groupby("d")
    vwap = (g.pv.cumsum() / np.maximum(g.v.cumsum(), 1e-9)).values
    bod = pd.Series(np.ones(n)).groupby(day).cumsum().values.astype(np.int64) - 1
    fob = np.zeros(n, bool)
    fob[pd.Series(np.arange(n)[ok]).groupby(day[ok]).min().values] = True
    P = 300
    CT = d.contract.values
    return dict(root=ROOTSYM, CT=CT, tf=0, lead=None, traded=TRADED, dpt=DPT, tick=TICK, comm=COMM,
                C=C, H=Hh, L=L, V=V, vwap=vwap, bod=bod,
                dhi=pd.Series(Hh).groupby(day).cummax().values,
                dlo=pd.Series(L).groupby(day).cummin().values,
                fob=fob, dow=((esec + 2 * 3600) // 86400 + 3) % 7,
                Hp=np.r_[Hh, np.full(P, np.nan)], Lp=np.r_[L, np.full(P, np.nan)],
                Cp=np.r_[C, np.full(P, np.nan)],
                HF=np.r_[d.hi_first.values.astype(bool), np.zeros(P, bool)],
                ATR=a, hr=hr, OK=ok, n=n, day=day,
                wk=np.zeros(n, np.int64), wks=len(np.unique(day)) / 5.0,
                cut=int(n * 0.75), ts=esec)


def book(M, p, exact=True):
    """Trades for one config. exact=True resolves same-bar stop/target by path."""
    C, ATR, n = M["C"], M["ATR"], M["n"]
    idx, side, ref = H.signal(M, p)
    if len(idx) < 80: return None
    lim = C[idx] - (p["pb"] * ref * TICK) * side
    ttl = int(round(p["ttl"]))
    st = np.arange(1, ttl + 1); bars = idx[:, None] + st[None, :]
    adv = np.where(side[:, None] > 0, M["Lp"][bars], M["Hp"][bars])
    thr = (adv * side[:, None]) <= (lim * side)[:, None] - TICK + 1e-9
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
    sl = eps - stk * TICK; tp_ = eps + p["rr"] * stk * TICK
    hs = lo <= sl[:, None]; ht = hi >= tp_[:, None]; ht[:, 0] = False
    j1 = np.where(hs.any(1), hs.argmax(1), 10**9)
    j2 = np.where(ht.any(1), ht.argmax(1), 10**9)
    both = (j1 == j2) & (j1 <= hold)          # both touched in the SAME bar
    if exact:
        # For a long the stop is the bar's low and the target its high, so the
        # stop filled first exactly when the low came first. Reversed short.
        hf = M["HF"][np.clip(fb[:, None] + js[None, :], 0, n - 1)]
        hf_at = hf[ar, np.minimum(j1, hold)]
        stop_first = np.where(sd > 0, ~hf_at, hf_at)
    else:
        stop_first = np.ones(len(fb), bool)    # the old convention
    ks_ = np.where(both, stop_first, j1 < j2) & (j1 <= hold)
    kt = (~ks_) & (j2 <= hold)
    xj = np.where(ks_, np.minimum(j1, hold), np.where(kt, np.minimum(j2, hold), hold))
    xp = np.where(ks_, sl * sd, np.where(kt, tp_ * sd, cw[ar, np.minimum(xj, hold)]))
    gd = np.isfinite(xp)
    if gd.sum() < 80: return None
    pl = (xp[gd] - ep[gd]) * sd[gd] * (1 / TICK) * DPT - COMM
    F = fb[gd]; X = np.minimum(fb[gd] + xj[gd], n - 1); SD = sd[gd]
    o = np.argsort(F); pl, F, X, SD = pl[o], F[o], X[o], SD[o]
    mp = int(round(p["maxpos"]))
    free = np.zeros(mp, dtype=np.int64); took = np.zeros(len(pl), bool)
    for i in range(len(pl)):
        s_ = int(np.argmin(free))
        if free[s_] <= F[i]: took[i] = True; free[s_] = X[i]
    if took.sum() < 80: return None
    return pl[took], F[took], X[took], SD[took], float(both[gd].mean())


M = load_ev(SERIES)
n = M["n"]
span = (M["ts"].max() - M["ts"].min()) / 86400
print(f"{ROOTSYM} {SERIES}: {n:,} bars over {span:.0f} days, "
      f"{len(np.unique(M['day']))} sessions\n", flush=True)

rng = np.random.default_rng(20260804)
H.rng = rng
CFGS = []
while len(CFGS) < NCFG:
    p = H.draw(); p["maxpos"] = int(rng.integers(1, 5))
    CFGS.append(p)

t0 = time.time()
books, ambig = [], []
for p in CFGS:
    b = book(M, p, exact=True)
    if b is not None:
        books.append((p["mech"], b[:4])); ambig.append(b[4])
print(f"{len(books):,} books from {NCFG:,} configs in {time.time()-t0:.0f}s")
if not books:
    print("no books"); sys.exit(0)
print(f"same-bar stop AND target touched on {np.mean(ambig):.1%} of trades -- "
      f"that is the share\n  the old assume-the-stop convention was deciding "
      f"by fiat.\n", flush=True)

C = M["C"]
CT = M["CT"]
# Only NQ has a tape, so one market x four splits is four cells -- far too few
# for a sign test, and the whole power of this design comes from cell count.
# But the tape is eight separate contracts covering eight different periods,
# and a contract is as good an out-of-sample unit as a market. 32 cells.
rows = []
for ct in sorted(set(CT)):
    sel_c = CT == ct
    lo_i, hi_i = int(np.argmax(sel_c)), int(n - np.argmax(sel_c[::-1]))
    nc = hi_i - lo_i
    if nc < 2000: continue
    for sp in SPLITS:
        cut = lo_i + int(nc * sp)
        recs = []
        for mech, (pl, F, X, SD) in books:
            inc = (F >= lo_i) & (F < hi_i)
            if inc.sum() < 80: continue
            plc, Fc, Xc, SDc = pl[inc], F[inc], X[inc], SD[inc]
            m = Fc < cut
            if m.sum() < 40 or (~m).sum() < 25: continue
            dd = np.empty(len(plc))
            for s_, a_, b_ in ((m, lo_i, cut), (~m, cut, hi_i - 1)):
                dd[s_] = (C[b_] - C[a_]) / max(b_ - a_, 1) / TICK * DPT
            adj = plc - dd * (Xc - Fc) * SDc
            recs.append(dict(mech=mech, tr=float(adj[m].mean()),
                             ho=float(adj[~m].mean()), tpw=len(plc) / M["wks"]))
        if not recs: continue
        r = pd.DataFrame(recs)
        for mech, g in r.groupby("mech"):
            top = g.nlargest(max(3, len(g) // 20), "tr")
            rows.append(dict(contract=ct, split=sp, mech=mech, n=len(g),
                             tr=float(top.tr.mean()), ho=float(top.ho.mean()),
                             tpw=float(top.tpw.mean())))

d = pd.DataFrame(rows)
ctl = d[d.mech == "rnd"][["contract", "split", "ho"]].rename(columns={"ho": "ctl"})
d = d.merge(ctl, on=["contract", "split"], how="left")
d["beat"] = d.ho > d.ctl
print(f"{'mech':>6s} {'cells':>6s} {'trades/wk':>10s} {'train $':>9s} "
      f"{'holdout $':>10s} {'control $':>10s} {'beats':>7s}")
for mech, g in d.groupby("mech"):
    print(f"{mech:>6s} {len(g):6d} {g.tpw.mean():10.1f} {g.tr.mean():9.2f} "
          f"{g.ho.mean():10.2f} {g.ctl.mean():10.2f} {g.beat.mean():6.0%}")
d.to_csv(os.path.join(HERE, f"tickrobust_{ROOTSYM}_{SERIES}.csv"), index=False)
print(f"\nper contract (holdout $/trade, drift-adjusted):")
print(d.pivot_table(index="contract", columns="mech", values="ho").round(1).to_string())
from math import comb
print()
for mech in sorted(set(d.mech)):
    if mech == "rnd": continue
    g = d[d.mech == mech].dropna(subset=["ctl"])
    if len(g) < 8: continue
    w, k = int(g.beat.sum()), len(g)
    pv = sum(comb(k, i) for i in range(w, k + 1)) / 2 ** k
    print(f"{mech:>5s}: beats the control in {w:2d} of {k} cells, "
          f"sign test p = {pv:.4f}")

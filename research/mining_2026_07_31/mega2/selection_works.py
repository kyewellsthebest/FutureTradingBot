"""Does picking winners on training data actually predict the holdout?

PORTFOLIO_PREVIEW.md reports Spearman(train $/wk, holdout $/wk) = +0.701 over
7,200 candidates, monotone through every decile, and calls it "the number that
matters more than any dollar figure". It was the basis for believing selection
works, and for the \$2,281/week book built on top of it.

Today's measurements say the opposite: configs chosen for the best training
performance persist into the holdout 19-29% of the time against 50% by chance.

Both cannot be true. This settles it with the one comparison the original
never ran: the same correlation, computed for RANDOM-ENTRY configs.

A random config contains no information. If train performance predicts holdout
performance for random entries too, then the correlation is not skill being
detected -- it is a market that trended in both periods, rewarding whichever
configs happened to be long, in training and in the holdout alike. Every real
mechanism inherits the same free ride, and +0.701 measures the trend rather
than the selection.

Reported four ways, and the differences are the answer:
  raw vs drift-adjusted     -- removing the trend should collapse a drift artifact
  real mechanisms vs random -- random is the floor; skill must clear it

Usage: python selection_works.py [TF] [N_CONFIGS]
"""
import os, sys, time, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)
R = types.ModuleType("rob"); R.__dict__["__file__"] = os.path.join(HERE, "robust.py")
rsrc = open(os.path.join(HERE, "robust.py")).read().split("\nrows = []")[0]
exec(compile(rsrc, "robust.py", "exec"), R.__dict__)

TF = int(sys.argv[1]) if len(sys.argv) > 1 else 15
NCFG = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
MKTS = os.environ.get("SEL_MARKETS", "RTY,YM,CL,HG,ES,NG,6E,6B,ZF,ZT").split(",")
CUTF = 0.75          # the same single boundary the original used


def spearman(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 50: return np.nan
    a = pd.Series(x[ok]).rank().values; b = pd.Series(y[ok]).rank().values
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else np.nan


rng = np.random.default_rng(20260804)
H.rng = rng
CFGS = []
while len(CFGS) < NCFG:
    p = H.draw(); p["maxpos"] = int(rng.integers(1, 5))
    CFGS.append(p)

rows = []
for mk in MKTS:
    try:
        M = H.load(mk, TF, lead="ES" if mk != "ES" else "NQ")
    except Exception as e:
        print(f"  skip {mk}: {e}"); continue
    C, tick, dpt, n = M["C"], M["tick"], M["dpt"], M["n"]
    cut = int(n * CUTF)
    got = 0
    for p in CFGS:
        b = R.book(M, p)
        if b is None: continue
        pl, F, X, SD = b
        m = F < cut
        if m.sum() < 50 or (~m).sum() < 30: continue
        dd = np.empty(len(pl))
        for sel, a_, b_ in ((m, 0, cut), (~m, cut, n - 1)):
            dd[sel] = (C[b_] - C[a_]) / max(b_ - a_, 1) / tick * dpt
        adj = pl - dd * (X - F) * SD
        wks_tr, wks_ho = M["wks"] * CUTF, M["wks"] * (1 - CUTF)
        rows.append(dict(mkt=mk, mech=p["mech"],
                         tr_wk=pl[m].sum() / wks_tr, ho_wk=pl[~m].sum() / wks_ho,
                         tr_adj=adj[m].sum() / wks_tr, ho_adj=adj[~m].sum() / wks_ho,
                         side=float(SD.mean())))
        got += 1
    print(f"  {mk}: {got:,} candidates", flush=True)

d = pd.DataFrame(rows)
if d.empty:
    print("no candidates"); sys.exit(0)
print(f"\n{len(d):,} candidates across {d.mkt.nunique()} markets, tf{TF}, "
      f"split at {CUTF:.0%}\n")

print("Spearman(train $/wk, holdout $/wk) -- the +0.701 claim:")
print(f"{'group':>22s} {'n':>7s} {'raw':>8s} {'drift-adjusted':>16s}")
allr = spearman(d.tr_wk.values, d.ho_wk.values)
alla = spearman(d.tr_adj.values, d.ho_adj.values)
print(f"{'every candidate':>22s} {len(d):7,} {allr:8.3f} {alla:16.3f}")
rnd = d[d.mech == "rnd"]
if len(rnd) > 50:
    print(f"{'RANDOM ENTRIES ONLY':>22s} {len(rnd):7,} "
          f"{spearman(rnd.tr_wk.values, rnd.ho_wk.values):8.3f} "
          f"{spearman(rnd.tr_adj.values, rnd.ho_adj.values):16.3f}")
real = d[d.mech != "rnd"]
print(f"{'real mechanisms':>22s} {len(real):7,} "
      f"{spearman(real.tr_wk.values, real.ho_wk.values):8.3f} "
      f"{spearman(real.tr_adj.values, real.ho_adj.values):16.3f}")

# Within a single market the trend is shared by every candidate, so a
# correlation that is strong pooled but weak per market is the trend talking.
per = [spearman(g.tr_wk.values, g.ho_wk.values) for _, g in d.groupby("mkt")]
pera = [spearman(g.tr_adj.values, g.ho_adj.values) for _, g in d.groupby("mkt")]
per = [x for x in per if np.isfinite(x)]; pera = [x for x in pera if np.isfinite(x)]
print(f"\nwithin single markets: raw median {np.median(per):+.3f}, "
      f"drift-adjusted median {np.median(pera):+.3f}")

print("\ndeciles by training $/wk (the table the original reported):")
for lbl, tc, hc in (("raw", "tr_wk", "ho_wk"), ("drift-adjusted", "tr_adj", "ho_adj")):
    d["dec"] = pd.qcut(d[tc], 10, labels=False, duplicates="drop")
    g = d.groupby("dec").agg(train=(tc, "mean"), holdout=(hc, "mean"),
                             net_long=("side", "mean"))
    print(f"  {lbl}:")
    print("   " + "  ".join(f"d{int(i)+1}:{r.train:.0f}->{r.holdout:.0f}"
                            for i, r in g.iterrows()))
    print(f"    net long by decile: " +
          " ".join(f"{r.net_long:+.2f}" for _, r in g.iterrows()))

rr = spearman(rnd.tr_wk.values, rnd.ho_wk.values) if len(rnd) > 50 else np.nan
print()
if np.isfinite(rr) and rr > 0.3:
    print(f"VERDICT: random entries show {rr:+.3f} on the same test. The "
          f"correlation is\n  the market trending in both periods, not "
          f"selection detecting skill.")
elif np.isfinite(alla) and alla > 0.3:
    print("VERDICT: the correlation survives drift adjustment and random "
          "entries do not\n  reproduce it. Selection is doing real work.")
else:
    print("VERDICT: the correlation does not survive drift adjustment. "
          "Whatever the\n  original measured, it was not selection skill.")
d.to_csv(os.path.join(HERE, f"selection_{TF}.csv"), index=False)

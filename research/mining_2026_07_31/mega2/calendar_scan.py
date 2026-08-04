"""Are there calendar effects? Measured, not searched.

Searching for a good (weekday, hour) config across fifteen markets means
testing hundreds of cells and keeping the best, which finds a winner whether
or not one exists -- the same selection trap that produced every result this
project has had to retract. So this does not search. It reports every cell
with a standard error, splits train from holdout, and applies a multiple-
testing correction to the whole grid at once.

What is measured: the forward return over the next H bars from the start of
each cell, in ATR units so markets pool sensibly, gross of costs. Costs are
irrelevant to the question "does the clock predict anything" -- if the answer
is no, cost cannot rescue it, and if yes, cost decides whether it is worth
trading, which is a later question.

Usage: python calendar_scan.py [HOLD_BARS] [TF]
"""
import os, sys, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)

HOLD = int(sys.argv[1]) if len(sys.argv) > 1 else 12
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 5
MKTS = os.environ.get("CAL_MARKETS",
                      "RTY,YM,CL,HG,ES,NG,6E,6B,6A,MBT,ETH,ZF,ZT,ZC,ZW").split(",")

rows = []
for m in MKTS:
    try:
        M = H.load(m, TF)
    except Exception as e:
        print(f"  skip {m}: {e}"); continue
    C, ATR, n = M["C"], M["ATR"], M["n"]
    fwd = np.r_[(C[HOLD:] - C[:-HOLD]), np.full(HOLD, np.nan)] / M["tick"]
    r = fwd / np.maximum(ATR, 1e-9)              # ATR units, so markets pool
    ok = M["OK"] & np.isfinite(r)
    rows.append(pd.DataFrame(dict(mkt=m, dow=M["dow"], hr=M["hr"].astype(int),
                                  r=r, train=np.arange(n) < M["cut"]))[ok])
    print(f"  {m}: {ok.sum():,} observations", flush=True)

d = pd.concat(rows, ignore_index=True)
print(f"\npooled: {len(d):,} observations across {d.mkt.nunique()} markets, "
      f"forward {HOLD} bars on tf{TF}, in ATR units\n")

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def cells(g, by):
    o = g.groupby(by).r.agg(["size", "mean", "std"])
    o["t"] = o["mean"] / (o["std"] / np.sqrt(o["size"]))
    return o


for by, label in ((["dow"], "day of week"), (["hr"], "hour of day (UTC)")):
    tr = cells(d[d.train], by); ho = cells(d[~d.train], by)
    j = tr.join(ho, rsuffix="_ho", how="inner")
    j = j[j["size"] >= 500]
    print(f"## {label}  (t over ~2 means nothing on its own -- see the "
          f"correction below)")
    show = j[["size", "mean", "t", "mean_ho", "t_ho"]].copy()
    show.index = [DOW[i] if by == ["dow"] else f"{i:02d}h" for i in show.index]
    print(show.round(4).to_string())
    # The whole grid was looked at, so the bar for "real" is not t>2 on the
    # best cell -- it is t>2 after paying for every cell that was inspected.
    k = len(j)
    need = float(np.sqrt(2) * (1 + 0.25 / k)) if k else 0
    from math import erfc
    best = j["t"].abs().max() if k else 0
    p_one = erfc(abs(best) / np.sqrt(2))
    print(f"   {k} cells inspected; best |t| = {best:.2f}, "
          f"p = {p_one:.4f}, after correction p = {min(1.0, p_one*k):.3f}")
    # And the only test that cannot be gamed: does the training sign repeat?
    if k:
        agree = float((np.sign(j["mean"]) == np.sign(j["mean_ho"])).mean())
        print(f"   sign agreement train vs holdout: {agree:.0%} of {k} cells "
              f"(chance is 50%)\n")

# Finally the interaction, which is where a real effect would hide if the
# marginals are flat -- but with far less data per cell.
g = d.groupby(["dow", "hr"]).r.agg(["size", "mean", "std"])
g = g[g["size"] >= 300]
g["t"] = g["mean"] / (g["std"] / np.sqrt(g["size"]))
print(f"## weekday x hour: {len(g)} cells with 300+ observations")
top = g.reindex(g["t"].abs().sort_values(ascending=False).index).head(8)
top.index = [f"{DOW[a]} {b:02d}h" for a, b in top.index]
print(top[["size", "mean", "t"]].round(4).to_string())
if len(g):
    from math import erfc
    b = g["t"].abs().max()
    print(f"   best |t| = {b:.2f}, p = {erfc(b/np.sqrt(2)):.4f}, "
          f"after correcting for {len(g)} cells = "
          f"{min(1.0, erfc(b/np.sqrt(2))*len(g)):.3f}")
    # what the largest |t| would look like if nothing were there at all
    exp = float(np.sqrt(2 * np.log(max(len(g), 2))))
    print(f"   with no effect at all, the largest |t| among {len(g)} cells "
          f"would be about {exp:.2f}")
d.to_csv(os.path.join(HERE, f"calendar_{TF}_{HOLD}.csv.gz"), index=False,
         compression="gzip")

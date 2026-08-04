"""Are there calendar effects? Measured, not searched.

Searching for a good (weekday, hour) cell across fifteen markets means testing
hundreds of cells and keeping the best, which finds a winner whether or not
one exists -- the trap that produced every result this project has had to
retract. So this does not search. Every cell is reported, train and holdout,
with a correction for how many cells were inspected.

The statistical trap underneath is subtler and cost us a wrong reading first
time round. Computing a forward H-bar return at every bar makes each
observation overlap H-1 others, and pooling fifteen markets that move together
correlates them further. Both inflate t, together by enough to turn a real t
of 1.8 into a printed 10. So the headline test uses ONE number per trading
day: markets averaged within the day, days never overlapping. That t is real.

Everything is gross of costs. If the clock predicts nothing, no cost structure
rescues it; if it predicts something, cost decides whether it is tradeable,
which is a later question.

Usage: python calendar_scan.py [HOLD_BARS] [TF]
"""
import os, sys, types
from math import erfc
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
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri"]

bar_rows, day_rows = [], []
for m in MKTS:
    try:
        M = H.load(m, TF)
    except Exception as e:
        print(f"  skip {m}: {e}"); continue
    C, ATR, n = M["C"], M["ATR"], M["n"]
    fwd = np.r_[(C[HOLD:] - C[:-HOLD]), np.full(HOLD, np.nan)] / M["tick"]
    r = fwd / np.maximum(ATR, 1e-9)
    ok = M["OK"] & np.isfinite(r)
    bar_rows.append(pd.DataFrame(dict(mkt=m, dow=M["dow"], hr=M["hr"].astype(int),
                                      r=r, train=np.arange(n) < M["cut"]))[ok])
    # one observation per market-day: the whole day's move, in ATR units
    f = pd.DataFrame(dict(day=M["day"], C=C, ATR=ATR, dow=M["dow"],
                          train=np.arange(n) < M["cut"]))[M["OK"]]
    a = f.groupby("day").agg(first=("C", "first"), last=("C", "last"),
                             atr=("ATR", "mean"), dow=("dow", "first"),
                             train=("train", "first"), bars=("C", "size"))
    a = a[a.bars >= 10]
    a["r"] = (a["last"] - a["first"]) / M["tick"] / np.maximum(a.atr, 1e-9)
    day_rows.append(a.reset_index().assign(mkt=m))
    print(f"  {m}: {ok.sum():,} bars, {len(a):,} days", flush=True)

d = pd.concat(bar_rows, ignore_index=True)
dd = pd.concat(day_rows, ignore_index=True)
print(f"\npooled: {len(d):,} bar observations and {len(dd):,} market-days "
      f"across {d.mkt.nunique()} markets, forward {HOLD} bars on tf{TF}\n")

# --- the headline test: one independent number per trading day ---------------
per_day = dd.groupby(["day", "dow", "train"], as_index=False).r.mean()
print("## weekday, one independent observation per trading day")
print("   markets averaged within the day, so nothing overlaps and nothing is")
print("   cross-correlated. These t values are the ones to believe.")
parts = []
for tr in (True, False):
    s = per_day[per_day.train == tr].groupby("dow").r.agg(["size", "mean", "std"])
    s["t"] = s["mean"] / (s["std"] / np.sqrt(s["size"]))
    parts.append(s)
j = parts[0].join(parts[1], rsuffix="_ho", how="inner")
j.index = [DOW[i] for i in j.index]
print(j[["size", "mean", "t", "size_ho", "mean_ho", "t_ho"]].round(4).to_string())
agree = float((np.sign(j["mean"]) == np.sign(j["mean_ho"])).mean())
bt = j["t"].abs().max()
print(f"   sign agreement train vs holdout: {agree:.0%} of {len(j)} weekdays "
      f"(chance 50%)")
print(f"   best |t| = {bt:.2f}; across {len(j)} weekdays a pure null would "
      f"produce about {np.sqrt(2*np.log(len(j))):.2f}")
print(f"   corrected p on the best weekday: "
      f"{min(1.0, erfc(bt/np.sqrt(2))*len(j)):.3f}\n")


def cells(g, by):
    o = g.groupby(by).r.agg(["size", "mean", "std"])
    o["t"] = o["mean"] / (o["std"] / np.sqrt(o["size"]))
    return o


# --- the overlapping bar-level tables, kept only for the sign check ----------
for by, label, floor in ((["hr"], "hour of day (UTC)", 500),
                         (["dow", "hr"], "weekday x hour", 300)):
    tr = cells(d[d.train], by); ho = cells(d[~d.train], by)
    k = tr.join(ho, rsuffix="_ho", how="inner")
    k = k[(k["size"] >= floor) & (k["size_ho"] >= floor // 3)]
    if not len(k): continue
    print(f"## {label}: {len(k)} cells")
    print("   t here is inflated by overlap and by cross-market correlation --")
    print("   read the sign agreement, not the t.")
    top = k.reindex(k["t"].abs().sort_values(ascending=False).index).head(8)
    top.index = ([f"{i:02d}h" for i in top.index] if by == ["hr"]
                 else [f"{DOW[a]} {b:02d}h" for a, b in top.index])
    print(top[["size", "mean", "t", "mean_ho", "t_ho"]].round(4).to_string())
    ag = float((np.sign(k["mean"]) == np.sign(k["mean_ho"])).mean())
    # of the cells that looked strongest in training, how many kept their sign?
    st = k.reindex(k["t"].abs().sort_values(ascending=False).index).head(max(5, len(k)//10))
    ags = float((np.sign(st["mean"]) == np.sign(st["mean_ho"])).mean())
    print(f"   sign agreement: {ag:.0%} of all {len(k)} cells, "
          f"{ags:.0%} of the {len(st)} strongest in training (chance 50%)\n")

dd.to_csv(os.path.join(HERE, f"calendar_days_{TF}.csv"), index=False)

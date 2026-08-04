"""Does order flow predict returns at all? Measured before anything is traded.

Eleven strategy families died this session, and every one of them died the
same way: a search found something, and the something was selection. So this
does not search. It asks the prior question -- is there any predictive
relationship between order flow and future returns -- and answers it with a
correlation, which cannot be cherry-picked because nothing is being chosen.

If the answer is no, no strategy built on these features can work, and we stop
without spending another day on config searches. If the answer is yes, then
the size of the correlation tells us in advance roughly what edge per trade to
expect, so we know whether it clears costs before building anything.

The features are the ones OHLC bars cannot express:
  delta          signed volume over the bar (tick rule)
  dratio         delta as a share of the bar's volume
  cumdelta       running signed volume, detrended
  bigratio       share of volume in trades of 10+ contracts
  szskew         size at the bar's high vs at its low -- who is resting where
  intensity      trades per second, versus the recent norm

Controls, both essential:
  shuffled       the same feature values in a random order. Destroys any real
                 relationship while preserving the distribution exactly, so
                 whatever IC it shows is what this pipeline produces from
                 nothing.
  price features return and range over the bar -- things OHLC already gives
                 us. Order flow has to beat these to be worth the data.

Usage: python orderflow_ic.py [BAR_SECONDS] [FORWARD_BARS]
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
BARSEC = int(sys.argv[1]) if len(sys.argv) > 1 else 300
FWD = int(sys.argv[2]) if len(sys.argv) > 2 else 3
NS = 1_000_000_000
BIG = 10

FEATS = ["delta", "dratio", "cumdelta", "bigratio", "szskew", "intensity"]
PRICE = ["ret", "rng"]


def bars_for(path):
    """Time bars with order-flow columns, from one contract's trade tape."""
    d = pd.read_parquet(path).sort_values("ts", kind="stable")
    # d["size"], never d.size -- the attribute is the DataFrame's element count
    ts = d.ts.values; px = d.price.values.astype(float)
    sz = d["size"].values.astype(float)
    # tick rule: a trade at a higher price than the last different price is
    # buyer-initiated. Flat trades inherit the previous sign.
    dp = np.diff(px, prepend=px[0])
    sgn = np.sign(dp)
    idx = np.where(sgn != 0)[0]
    if len(idx) == 0: return None
    filled = np.zeros(len(sgn))
    filled[idx] = sgn[idx]
    filled = pd.Series(filled).replace(0, np.nan).ffill().fillna(1.0).values
    b = ts // (BARSEC * NS)
    g = pd.DataFrame(dict(b=b, px=px, sz=sz, sv=filled * sz, ts=ts,
                          big=np.where(sz >= BIG, sz, 0.0)))
    a = g.groupby("b").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), delta=("sv", "sum"),
                           bigv=("big", "sum"), ntr=("px", "size"),
                           t0=("ts", "first"), t1=("ts", "last"))
    a = a[a.vol > 0]
    if len(a) < 500: return None
    # size resting at the extremes: what actually printed at the high and low
    hi = g.px.values == g.groupby("b").px.transform("max").values
    lo = g.px.values == g.groupby("b").px.transform("min").values
    a["hisz"] = g[hi].groupby("b").sz.sum().reindex(a.index).fillna(0)
    a["losz"] = g[lo].groupby("b").sz.sum().reindex(a.index).fillna(0)
    a["dratio"] = a.delta / a.vol
    a["bigratio"] = a.bigv / a.vol
    a["szskew"] = (a.hisz - a.losz) / np.maximum(a.hisz + a.losz, 1.0)
    dur = np.maximum((a.t1 - a.t0) / NS, 1e-3)
    a["intensity"] = a.ntr / dur
    a["intensity"] /= a["intensity"].rolling(200, min_periods=50).mean()
    a["cumdelta"] = a.delta.cumsum()
    a["cumdelta"] -= a.cumdelta.rolling(200, min_periods=50).mean()
    a["ret"] = a.close.diff()
    a["rng"] = a.high - a.low
    # forward return, in units of the recent bar range so contracts pool
    scale = a.rng.rolling(200, min_periods=50).mean()
    a["fwd"] = (a.close.shift(-FWD) - a.close) / np.maximum(scale, 1e-9)
    a["delta"] = a.delta / np.maximum(a.vol.rolling(200, min_periods=50).mean(), 1e-9)
    return a.dropna(subset=["fwd"] + FEATS + PRICE)


rows = []
files = sorted(glob.glob(os.path.join(RAW, "*.parquet")))
if not files:
    print(f"no tick parquets in {RAW}"); sys.exit(0)
for f in files:
    c = os.path.basename(f).replace(".parquet", "")
    try:
        a = bars_for(f)
    except Exception as e:
        print(f"  {c}: failed ({e})"); continue
    if a is None or len(a) < 1000:
        print(f"  {c}: too few bars"); continue
    a["contract"] = c
    rows.append(a)
    print(f"  {c}: {len(a):,} bars of {BARSEC}s", flush=True)

if not rows:
    print("nothing built"); sys.exit(0)
D = pd.concat(rows, ignore_index=True)
print(f"\n{len(D):,} bars across {D.contract.nunique()} contracts, "
      f"{BARSEC}s bars, forward {FWD} bars\n")

rng = np.random.default_rng(7)
D["shuffled"] = rng.permutation(D["dratio"].values)

# Split by contract so train and holdout are different market periods, and
# report each contract separately -- a feature that only works in one contract
# is the same regime luck that killed the 60-minute result.
cs = sorted(D.contract.unique())
tr_c, ho_c = cs[:max(1, len(cs) * 2 // 3)], cs[max(1, len(cs) * 2 // 3):]
print(f"train contracts: {', '.join(tr_c)}")
print(f"holdout contracts: {', '.join(ho_c)}\n")


def ic(g, col):
    x = g[col].values; y = g.fwd.values
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 500: return np.nan
    # Spearman by hand: Pearson on ranks. pandas routes method="spearman"
    # through scipy, which is not installed here, and ranking is faster anyway.
    a = pd.Series(x[ok]).rank().values; b = pd.Series(y[ok]).rank().values
    a = a - a.mean(); b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else np.nan


ALL = FEATS + PRICE + ["shuffled"]
print(f"{'feature':>10s} {'train IC':>9s} {'holdout IC':>11s} "
      f"{'contracts +ve':>14s} {'per-contract IC':>40s}")
out = []
for col in ALL:
    tr = ic(D[D.contract.isin(tr_c)], col)
    ho = ic(D[D.contract.isin(ho_c)], col)
    per = [ic(g, col) for _, g in D.groupby("contract")]
    per = [p for p in per if np.isfinite(p)]
    pos = float(np.mean([p > 0 for p in per])) if per else np.nan
    out.append((col, tr, ho, pos))
    txt = " ".join(f"{p:+.3f}" for p in per)
    print(f"{col:>10s} {tr:+9.4f} {ho:+11.4f} {pos:13.0%}  {txt}")

sh = [o for o in out if o[0] == "shuffled"][0]
print(f"\nthe shuffled control reads {sh[1]:+.4f} train / {sh[2]:+.4f} holdout.")
print("that is what this pipeline produces from a feature with no information.")
print("\nfeatures worth anything must clear it in the holdout AND be consistent")
print("across contracts:")
for col, tr, ho, pos in out:
    if col == "shuffled": continue
    flag = ("worth a look" if abs(ho) > abs(sh[2]) * 3 and (pos > 0.8 or pos < 0.2)
            else "no")
    print(f"   {col:>10s}: holdout {ho:+.4f} vs control {sh[2]:+.4f}, "
          f"{pos:.0%} of contracts same sign -> {flag}")

# An IC of x on a trade whose payoff is r translates to roughly x*r per trade.
# State it so the cost comparison happens before anyone builds a strategy.
best = max((o for o in out if o[0] not in ("shuffled",)), key=lambda o: abs(o[2]))
print(f"\nbest holdout IC is {best[0]} at {best[2]:+.4f}. On a trade risking "
      f"$25 with a 1.8 reward-to-risk\n   payoff spread of ~$70, an IC of "
      f"{abs(best[2]):.4f} is worth about ${abs(best[2])*70:.2f} a trade "
      f"gross,\n   against costs near $2.30. ", end="")
print("That clears costs." if abs(best[2]) * 70 > 4.6 else
      "That does NOT clear costs, and no amount of strategy design fixes it.")
D[["contract"] + ALL + ["fwd"]].to_csv(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 f"orderflow_{BARSEC}_{FWD}.csv.gz"), index=False, compression="gzip")

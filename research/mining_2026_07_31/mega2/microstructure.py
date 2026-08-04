"""Trade-level microstructure: the things that exist ONLY in the tape.

Everything measured so far -- even the event bars -- aggregates trades into
buckets first. That already throws away what the tape uniquely has: the
millisecond spacing between prints, whether size arrived as one block or a
hundred lots, and whether a burst walked the book or sat on one price.

These features cannot be computed from OHLC at any resolution:

  sweep      trades inside a 50ms window that walk the price in one direction.
             A real sweep is somebody crossing the spread through multiple
             levels because they want size NOW -- an urgency footprint.
  absorb     large volume printing at a SINGLE price without the price moving.
             Somebody is filling passively against everything thrown at them,
             and when they stop, price tends to go their way.
  runlen     consecutive same-signed trades. Long runs are one participant
             working an order, not a crowd disagreeing.
  gap_ms     median milliseconds between trades, against its recent norm.
             Compression means something started.
  blocksz    largest single print as a share of the window's volume. One
             500-lot is a different event from five hundred 1-lots.

Same discipline as everything else: forward returns, train/holdout split BY
CONTRACT, and a shuffled control that shows what this pipeline produces from
a feature carrying no information. Money conversion at the end, because an
information coefficient only matters relative to what trading costs.

Usage: python microstructure.py [WINDOW_TRADES] [FORWARD_TRADES]
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
W = int(sys.argv[1]) if len(sys.argv) > 1 else 200      # trades per observation
FWD = int(sys.argv[2]) if len(sys.argv) > 2 else 600    # forward horizon, trades
NS = 1_000_000_000
SWEEP_MS = 50

FEATS = ["sweep", "absorb", "runlen", "gap_ms", "blocksz", "delta", "bigshare"]


def feats_for(path):
    d = pd.read_parquet(path).sort_values("ts", kind="stable")
    ts = d.ts.values.astype(np.int64)
    px = d.price.values.astype(float)
    sz = d["size"].values.astype(float)
    n = len(px)
    if n < 50_000: return None
    dp = np.diff(px, prepend=px[0])
    sgn = pd.Series(np.where(np.sign(dp) == 0, np.nan, np.sign(dp))).ffill().fillna(1.0).values
    # run length: how many consecutive trades have pushed the same way
    chg = np.r_[True, sgn[1:] != sgn[:-1]]
    grp = np.cumsum(chg)
    pos = np.arange(n) - pd.Series(np.arange(n)).groupby(grp).transform("min").values
    dt_ms = np.r_[0, np.diff(ts)] / 1e6
    # sweep: this trade is part of a fast directional burst
    fast = dt_ms <= SWEEP_MS
    swept = fast & (np.sign(dp) == sgn) & (dp != 0)
    b = np.arange(n) // W
    g = pd.DataFrame(dict(b=b, px=px, sz=sz, sgn=sgn, sv=sgn * sz, pos=pos,
                          dt=dt_ms, swept=swept.astype(float),
                          big=np.where(sz >= 10, sz, 0.0)))
    a = g.groupby("b").agg(close=("px", "last"), vol=("sz", "sum"),
                           delta=("sv", "sum"), runlen=("pos", "max"),
                           gap_ms=("dt", "median"), sweep=("swept", "mean"),
                           bigv=("big", "sum"), blocksz=("sz", "max"),
                           lo=("px", "min"), hi=("px", "max"), ntr=("px", "size"))
    a = a[(a.vol > 0) & (a.ntr == W)]
    if len(a) < 2000: return None
    # absorption: lots of volume, almost no price movement across the window
    rngp = np.maximum(a.hi - a.lo, 0.25)
    a["absorb"] = a.vol / rngp
    a["absorb"] /= a["absorb"].rolling(200, min_periods=50).mean()
    a["blocksz"] = a.blocksz / a.vol
    a["bigshare"] = a.bigv / a.vol
    a["delta"] = a.delta / a.vol
    a["gap_ms"] = a.gap_ms / np.maximum(a.gap_ms.rolling(200, min_periods=50).mean(), 1e-9)
    step = max(FWD // W, 1)
    scale = (a.hi - a.lo).rolling(200, min_periods=50).mean()
    a["fwd"] = (a.close.shift(-step) - a.close) / np.maximum(scale, 1e-9)
    return a.dropna(subset=["fwd"] + FEATS)


def ic(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 500: return np.nan
    p = pd.Series(x[ok]).rank().values; q = pd.Series(y[ok]).rank().values
    p = p - p.mean(); q = q - q.mean()
    den = np.sqrt((p * p).sum() * (q * q).sum())
    return float((p * q).sum() / den) if den > 0 else np.nan


rows = []
for f in sorted(glob.glob(os.path.join(RAW, "*.parquet"))):
    c = os.path.basename(f).replace(".parquet", "")
    try:
        a = feats_for(f)
    except Exception as e:
        print(f"  {c}: failed ({e})"); continue
    if a is None:
        print(f"  {c}: too few"); continue
    a["contract"] = c
    rows.append(a)
    print(f"  {c}: {len(a):,} windows of {W} trades", flush=True)

if not rows:
    print("nothing built"); sys.exit(0)
D = pd.concat(rows, ignore_index=True)
rng = np.random.default_rng(11)
D["shuffled"] = rng.permutation(D["delta"].values)
cs = sorted(D.contract.unique())
tr_c = cs[:max(1, len(cs) * 2 // 3)]; ho_c = cs[max(1, len(cs) * 2 // 3):]
print(f"\n{len(D):,} windows of {W} trades, forward {FWD} trades, "
      f"{len(cs)} contracts")
print(f"train {', '.join(tr_c)}\nholdout {', '.join(ho_c)}\n")

print(f"{'feature':>10s} {'train IC':>9s} {'holdout IC':>11s} {'same sign':>10s}"
      f"   per contract")
out = []
for col in FEATS + ["shuffled"]:
    t = ic(D[D.contract.isin(tr_c)][col].values, D[D.contract.isin(tr_c)].fwd.values)
    h = ic(D[D.contract.isin(ho_c)][col].values, D[D.contract.isin(ho_c)].fwd.values)
    per = [ic(g[col].values, g.fwd.values) for _, g in D.groupby("contract")]
    per = [p for p in per if np.isfinite(p)]
    pos = float(np.mean([np.sign(p) == np.sign(h) for p in per])) if per else np.nan
    out.append((col, t, h, pos))
    print(f"{col:>10s} {t:+9.4f} {h:+11.4f} {pos:9.0%}   "
          + " ".join(f"{p:+.3f}" for p in per))

sh = [o for o in out if o[0] == "shuffled"][0]
print(f"\nshuffled control: {sh[1]:+.4f} train, {sh[2]:+.4f} holdout")
best = max((o for o in out if o[0] != "shuffled"), key=lambda o: abs(o[2]))
# NQ micro: a 1.8 reward-to-risk trade on ~$25 of risk spans roughly $70
worth = abs(best[2]) * 70
print(f"best: {best[0]} at {best[2]:+.4f} holdout, {best[3]:.0%} of contracts "
      f"agree\n  worth about ${worth:.2f} a trade gross against ~$1.74 of cost "
      f"on MNQ -> ", end="")
print("clears cost." if worth > 3.5 else "does NOT clear cost.")
D.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      f"micro_{W}_{FWD}.csv.gz"), index=False, compression="gzip")

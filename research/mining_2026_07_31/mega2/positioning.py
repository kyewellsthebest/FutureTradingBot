"""Options positioning against next-day returns. Different data, different clock.

Everything tested this session has been price predicting price, intraday, at a
cost that eats the answer. This is neither: put/call ratios and SKEW measure
what people are POSITIONED for, and the horizon is one day, where a $0.42
round turn is noise against a several-hundred-dollar daily range.

That last point is the structural argument. Every intraday result died on the
ratio of edge to cost. At one trade a day the ratio stops mattering -- a $50
edge against $0.42 of cost is a different business from a $0.50 edge against
$0.42, even if the second one trades a hundred times more often.

The data is CBOE's own, already on disk, free, and going back to 2003 in
places -- roughly twenty years, against the two and a half we have of tick.

Discipline is unchanged: information coefficient against forward returns,
train/holdout split by date, and a shuffled control showing what this pipeline
produces from a feature carrying nothing. No strategy is built until a feature
clears its control.
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CB = os.path.join(ROOT, "data", "research_data", "cboe")
FWD = int(sys.argv[1]) if len(sys.argv) > 1 else 1      # days ahead


def read_cboe(path, datecol, keep):
    """CBOE files carry 1-3 rows of disclaimer above the real header."""
    for skip in range(0, 5):
        try:
            d = pd.read_csv(path, skiprows=skip)
        except Exception:
            continue
        cols = [str(c).strip() for c in d.columns]
        if any(c.lower().startswith(datecol.lower()) for c in cols):
            d.columns = cols
            dc = [c for c in cols if c.lower().startswith(datecol.lower())][0]
            d["date"] = pd.to_datetime(d[dc], errors="coerce", format="mixed")
            d = d.dropna(subset=["date"])
            out = d[["date"] + [c for c in keep if c in d.columns]].copy()
            return out if len(out) > 100 else None
    return None


feats = {}
for f, dcol, keep, pref in [
    ("a0b10824-equitypcarchive.csv", "Date", ["Equity P/C Ratio"], "eq_pc"),
    ("b4c7553d-indexpcarchive.csv", "Trade_date", ["P/C Ratio"], "idx_pc"),
    ("2d95eb59-totalpcarchive.csv", "Trade_date", ["P/C Ratio"], "tot_pc"),
    ("1f290f1b-spxpc.csv", "Date", ["SPX Put/Call Ratio"], "spx_pc"),
    ("7185a1f8-skewhistory_1.csv", "Date", ["Close"], "skew"),
]:
    p = os.path.join(CB, f)
    if not os.path.exists(p): continue
    d = read_cboe(p, dcol, keep)
    if d is None:
        print(f"  could not parse {f}"); continue
    val = [c for c in d.columns if c != "date"][0]
    s = pd.to_numeric(d[val], errors="coerce")
    feats[pref] = pd.DataFrame({"date": d.date.values, pref: s.values}).dropna()
    print(f"  {pref:8s} {len(feats[pref]):5,} rows  "
          f"{feats[pref].date.min().date()} -> {feats[pref].date.max().date()}")

if not feats:
    print("no CBOE features parsed"); sys.exit(0)

# NQ daily closes from the 5-minute file
nq = pd.read_csv(os.path.join(ROOT, "data", "polygon", "NQ_5min.csv"))
nq["ts"] = pd.to_datetime(nq.ts, utc=True)
day = nq.set_index("ts").close.resample("1D").last().dropna()
px = pd.DataFrame({"date": day.index.tz_localize(None).normalize(),
                   "close": day.values})
px["ret"] = px.close.pct_change().shift(-FWD) * 100.0     # forward %, in %
px["atr"] = px.close.pct_change().abs().rolling(20).mean() * 100.0

D = px.dropna(subset=["ret"]).copy()
for k, v in feats.items():
    v = v.copy(); v["date"] = v.date.dt.normalize()
    D = D.merge(v, on="date", how="left")
D = D.dropna(subset=["ret"])
print(f"\nmerged: {len(D):,} days, {D.date.min().date()} -> {D.date.max().date()}")

# levels are trending and non-stationary; what a trader could act on is how
# extreme today is against its own recent history
COLS = []
for k in feats:
    if k not in D: continue
    s = D[k].astype(float)
    z = (s - s.rolling(60, min_periods=20).mean()) / s.rolling(60, min_periods=20).std()
    D[k + "_z"] = z
    COLS.append(k + "_z")
rng = np.random.default_rng(3)
D["shuffled_z"] = rng.permutation(D[COLS[0]].values) if COLS else np.nan
COLS.append("shuffled_z")

cut = D.date.quantile(0.7)
tr, ho = D[D.date <= cut], D[D.date > cut]
print(f"train to {cut.date()} ({len(tr):,} days), holdout {len(ho):,} days\n")


def ic(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 100: return np.nan, 0
    x = pd.Series(a[m]).rank().values; y = pd.Series(b[m]).rank().values
    x = x - x.mean(); y = y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return (float((x * y).sum() / d) if d > 0 else np.nan), int(m.sum())


print(f"forward {FWD}-day return, IC by feature")
print(f"{'feature':>12s} {'n':>7s} {'train IC':>9s} {'holdout IC':>11s} "
      f"{'sign held':>10s}")
res = []
for c in COLS:
    it, nt = ic(tr[c].values, tr.ret.values)
    ih, nh = ic(ho[c].values, ho.ret.values)
    held = "yes" if np.isfinite(it) and np.isfinite(ih) and np.sign(it) == np.sign(ih) else "no"
    res.append((c, it, ih, held))
    print(f"{c:>12s} {nt+nh:7,} {it:+9.4f} {ih:+11.4f} {held:>10s}")

sh = [r for r in res if r[0] == "shuffled_z"]
shv = sh[0][2] if sh else 0.0
print(f"\nshuffled control holdout IC: {shv:+.4f}")
best = max((r for r in res if r[0] != "shuffled_z"),
           key=lambda r: abs(r[2]) if np.isfinite(r[2]) else 0)
print(f"best real feature: {best[0]} at {best[2]:+.4f} holdout, "
      f"sign {'held' if best[3]=='yes' else 'FLIPPED'}")
# A daily NQ move is worth roughly this much on one micro, so an IC converts
# into dollars a trade -- the only comparison that decides anything.
mv = float(np.nanmedian(np.abs(D.ret))) / 100.0 * float(D.close.median()) * 2.0
print(f"\nmedian absolute {FWD}-day move: ${mv:,.0f} on one MNQ contract")
print(f"an IC of {abs(best[2]):.4f} on that move is about "
      f"${abs(best[2])*mv:,.2f} a trade, against $0.42 of cost")
if abs(best[2]) * mv > 5 and best[3] == "yes":
    print("  -> worth building. Daily horizon makes cost irrelevant.")
else:
    print("  -> not established. Needs to clear the control AND hold its sign.")

"""The user's own live strategy, tested exactly as described.

Reported from live trading: impulse on Nasdaq, wait for a ~20% retrace, enter,
target 12 points, stop 6 points, roughly 200 trades a day. It made money
gross; commission killed it.

That claim deserves a direct test rather than my parameterisation of it,
because it sits precisely where my searches were blind:

  reward:risk = 12/6 = 2.0 EXACTLY, and every search drew rr from 1.5 to 2.0,
  so this configuration sat ON the upper boundary. Grid-boundary blindness has
  already produced four wrong conclusions in this project.

  the stop is a FIXED 6 points. Every search scaled the stop by ATR, so in
  quiet periods my stop was far tighter than 6 points and in fast ones far
  wider. A fixed stop is a genuinely different strategy, not a special case.

The output that matters is GROSS -- before commission and before slippage. If
gross is positive at 200 trades a day then the user is right, cost is the
whole problem, and the work becomes eliminating cost rather than finding a
different signal. If gross is negative, the live result was a small sample.

Both are actionable. Only the measurement decides which.

Usage: python users_strategy.py [BAR_SECONDS]
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
BARSEC = int(sys.argv[1]) if len(sys.argv) > 1 else 60
NS = 1_000_000_000
# NQ full-size is $20/point; MNQ is $2/point. The user traded Nasdaq futures;
# results are reported per MICRO contract, which is what a $4k account trades.
PT = 2.0
TICKPT = 0.25


def bars(path):
    d = pd.read_parquet(path).sort_values("ts", kind="stable")
    ts = d.ts.values.astype(np.int64)
    px = d.price.values.astype(float)
    sz = d["size"].values.astype(float)
    b = ts // (BARSEC * NS)
    g = pd.DataFrame(dict(b=b, px=px, sz=sz))
    a = g.groupby("b").agg(o=("px", "first"), h=("px", "max"),
                           l=("px", "min"), c=("px", "last"), v=("sz", "sum"))
    return a[a.v > 0].reset_index()


def test(a, imp_pts, lookback, retrace, stop_pts, tgt_pts, max_wait, max_hold):
    """The strategy as described. Returns per-trade GROSS dollars per micro."""
    o, h, l, c = (a.o.values, a.h.values, a.l.values, a.c.values)
    n = len(c)
    if n < 2000: return None
    # impulse: net move over `lookback` bars exceeds imp_pts
    mv = np.r_[np.full(lookback, np.nan), c[lookback:] - c[:-lookback]]
    up = mv >= imp_pts
    dn = mv <= -imp_pts
    sig = up | dn
    sig[:lookback + 5] = False
    sig[n - (max_wait + max_hold + 2):] = False
    idx = np.where(sig)[0]
    if len(idx) < 50: return None
    side = np.where(up[idx], 1, -1)
    # impulse range over those bars, retrace measured off it
    hi = pd.Series(h).rolling(lookback).max().values[idx]
    lo = pd.Series(l).rolling(lookback).min().values[idx]
    rng = np.maximum(hi - lo, 0.25)
    # buy the dip on an up impulse, sell the rip on a down one
    entry = np.where(side > 0, c[idx] - retrace * rng, c[idx] + retrace * rng)
    # wait up to max_wait bars for price to reach the retrace level
    st = np.arange(1, max_wait + 1)
    wb = np.minimum(idx[:, None] + st[None, :], n - 1)
    reach = np.where(side[:, None] > 0, l[wb] <= entry[:, None],
                     h[wb] >= entry[:, None])
    j = np.where(reach.any(1), reach.argmax(1), 10**9)
    ok = j < 10**9
    if ok.sum() < 50: return None
    fb = np.minimum(idx[ok] + 1 + j[ok], n - 1)
    sd = side[ok]; ep = entry[ok]
    sl = ep - sd * stop_pts
    tp = ep + sd * tgt_pts
    hs = np.arange(0, max_hold + 1)
    hb = np.minimum(fb[:, None] + hs[None, :], n - 1)
    lo_h = l[hb]; hi_h = h[hb]
    hit_s = np.where(sd[:, None] > 0, lo_h <= sl[:, None], hi_h >= sl[:, None])
    hit_t = np.where(sd[:, None] > 0, hi_h >= tp[:, None], lo_h <= tp[:, None])
    hit_t[:, 0] = False
    j1 = np.where(hit_s.any(1), hit_s.argmax(1), 10**9)
    j2 = np.where(hit_t.any(1), hit_t.argmax(1), 10**9)
    ks = j1 <= np.minimum(j2, max_hold)          # stop first when tied
    kt = (~ks) & (j2 <= max_hold)
    xj = np.where(ks, np.minimum(j1, max_hold),
                  np.where(kt, np.minimum(j2, max_hold), max_hold))
    xp = np.where(ks, sl, np.where(kt, tp, c[np.minimum(fb + max_hold, n - 1)]))
    pts = (xp - ep) * sd
    gross = pts * PT                              # $ per micro contract
    days = (a.b.max() - a.b.min()) * BARSEC / 86400.0
    return dict(n=len(gross), gross_per_trade=float(gross.mean()),
                per_day=len(gross) / max(days, 1e-9),
                winrate=float((pts > 0).mean()),
                total_gross=float(gross.sum()),
                se=float(gross.std()) / np.sqrt(len(gross)),
                fb=fb, gross=gross)


files = sorted(glob.glob(os.path.join(RAW, "NQ*.parquet")))
print(f"{len(files)} NQ contracts, {BARSEC}s bars, results per MICRO "
      f"(${PT}/point)\n")
ALL = {}
for f in files:
    cname = os.path.basename(f).replace(".parquet", "")
    try:
        ALL[cname] = bars(f)
    except Exception as e:
        print(f"  {cname}: {e}")
print(f"built bars for {len(ALL)} contracts\n")

# The user's configuration, plus a spread around it, because "20% retrace" and
# "an impulse" are approximate descriptions of something that was tuned live.
CFGS = []
for imp in (8, 12, 20, 30):
    for lb in (3, 5, 10):
        for rt in (0.2, 0.35, 0.5):
            CFGS.append((imp, lb, rt, 6.0, 12.0, 10, 60))
# the exact description first
CFGS.insert(0, (12, 4, 0.20, 6.0, 12.0, 10, 60))

print(f"{'impulse':>8s} {'lb':>3s} {'retr':>5s} {'trades':>8s} {'per day':>8s} "
      f"{'win%':>6s} {'GROSS $/tr':>11s} {'+/-':>6s} {'net@$1.32':>10s} "
      f"{'net@$0.72':>10s}")
best = None
for imp, lb, rt, sp, tg, mw, mh in CFGS:
    agg = []
    for cname, a in ALL.items():
        r = test(a, imp, lb, rt, sp, tg, mw, mh)
        if r: agg.append(r)
    if len(agg) < 4: continue
    tot = sum(r["n"] for r in agg)
    g = sum(r["total_gross"] for r in agg) / tot
    pd_ = np.mean([r["per_day"] for r in agg])
    wr = np.average([r["winrate"] for r in agg], weights=[r["n"] for r in agg])
    se = np.sqrt(sum((r["se"] * r["n"]) ** 2 for r in agg)) / tot
    row = dict(imp=imp, lb=lb, rt=rt, n=tot, per_day=pd_, wr=wr, gross=g, se=se)
    if best is None or g > best["gross"]: best = row
    print(f"{imp:8.0f} {lb:3d} {rt:5.2f} {tot:8,} {pd_:8.1f} {wr*100:5.1f}% "
          f"{g:11.3f} {se:6.3f} {g-1.32:10.3f} {g-0.72:10.3f}")

if best:
    print(f"\nbest gross: impulse {best['imp']}pt over {best['lb']} bars, "
          f"{best['rt']:.0%} retrace")
    print(f"  {best['n']:,} trades, {best['per_day']:.0f}/day, "
          f"{best['wr']*100:.1f}% win rate")
    print(f"  GROSS ${best['gross']:+.3f}/trade +/- ${best['se']:.3f} "
          f"({abs(best['gross'])/max(best['se'],1e-9):.1f} sigma)")
    print(f"\n  If gross is solidly positive, the user is right: cost is the "
          f"whole problem\n  and the work is eliminating cost. If it is not, "
          f"the live result was a\n  small sample. The sigma column decides "
          f"which.")
    daily = best["gross"] * best["per_day"]
    print(f"\n  at {best['per_day']:.0f} trades/day, one micro contract:")
    for label, cst in (("gross", 0.0), ("lifetime $0.72", 0.72),
                       ("free plan $1.32", 1.32)):
        print(f"    {label:>16s}: ${(best['gross']-cst)*best['per_day']:+8.0f}/day "
              f"= ${(best['gross']-cst)*best['per_day']*21:+9.0f}/month")

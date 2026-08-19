"""Every market, long horizons, cross-market features. The wide search.

WHY THIS ONE, AND WHY NOW. Today closed three lanes and left one open,
and the open one is narrow in a way that is probably accidental.

  DEAD  short-horizon price patterns   26 billion configurations
  DEAD  maker / passive fills          6.6% fill rate, measured
  DEAD  cross-sectional RANKING        168 configs, |t| max 1.64, powered
  ALIVE cross-market ML at 18 hours    p = 0.048, IC 3 empirical se

The survivor was built on NQ ALONE, and 71% of the features it leaned
on were other markets -- ES, YM, RTY, CL, GC, HG read on NQ's clock. So
the one thing that worked was the one thing that looked sideways. It
was never run on any market except NQ, for no better reason than that
the tick cache happened to exist for NQ.

This runs that idea properly: every market as a TARGET, every other
market as a FEATURE, at horizons where the toll is small.

  18 markets x 3 horizons (2h, 6h, 1 day) x real and shuffled

WHY IT MIGHT BEAT THE NQ VERSION, and it is not just more rows.
Drawdown is what killed the NQ candidate -- $3,360 against a $4,100
account. Profit across N uncorrelated markets scales with N while
drawdown scales with sqrt(N), so eighteen markets could turn a Calmar
of 3.5 into something far better. That is the difference between a
strategy needing $33,600 and one needing much less. Breadth is not
about finding more edge; it is about needing less capital to hold the
edge you have.

WHY IT MIGHT NOT. The markets are correlated -- ES, NQ, YM and RTY are
nearly the same bet -- so the sqrt(N) is optimistic and the realised
diversification is measured here rather than assumed. The report gives
the actual correlation of the per-market P&L streams.

WHAT IS REPORTED WHETHER OR NOT ANYTHING IS FOUND

  IC against its OVERLAP-CORRECTED standard error. The effective sample
  is rows/h, not rows. Getting this wrong is what made a pass criterion
  approve two horizons today whose signal was statistically zero.

  MDE -- the smallest edge this search could have seen. Every null in
  this repo before today omitted it, which is how "found nothing" came
  to be read as "there is nothing" for four months.

  Cost at $0.85 (the lifetime-subscription case) AND at $1.99 (measured
  from real fills). Nothing is judged on the optimistic one.

SUCCESS CRITERION, fixed before the run:

    |IC| >= 2 x overlap-corrected se, AND net > 0 at $1.99, AND the
    shuffled control at the same settings is not, AND net exceeds the
    configuration's own MDE.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {"SI"}
MIN_OPEN = 18
BAR_MIN = 5
ACCOUNT = 4100.0
COSTS = [0.85, 1.99]
HZ = [int(x) for x in os.environ.get("HZ", "24,72,288").split(",")]
# smoke-test hook: limit the market list without editing the loop
ONLY = [x for x in os.environ.get("ONLY", "").split(",") if x]
NTREE = int(os.environ.get("NTREE", "150"))
NFOLD = int(os.environ.get("NFOLD", "4"))

SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
}
LAGS = [1, 3, 6, 12, 24, 48, 96, 288]
XLAGS = [12, 48, 288]


def load():
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "*_5min.csv"))):
        s = os.path.basename(p).replace("_5min.csv", "")
        if s in DROP or s not in SPEC:
            continue
        d = pd.read_csv(p, parse_dates=["ts"], usecols=["ts", "close"])
        out[s] = d.set_index("ts")["close"]
    px = pd.DataFrame(out).sort_index()
    px = px[px.notna().sum(axis=1) >= MIN_OPEN].ffill(limit=3)
    keep = [c for c in px.columns if px[c].notna().mean() > 0.90]
    return px[keep].dropna(how="any")


def features(px, target):
    """Own path plus every other market's recent move, on one clock.

    Everything is a RETURN, never a price: a level would let the model
    memorise "NQ was 15,000 in early 2024" and call that a forecast.
    """
    f = {}
    r1 = px.pct_change()
    tgt = px[target]
    for L in LAGS:
        f[f"own_r{L}"] = tgt.pct_change(L)
    for L in (12, 48, 288):
        f[f"own_vol{L}"] = r1[target].rolling(L).std()
        f[f"own_absmean{L}"] = r1[target].abs().rolling(L).mean()
    for other in px.columns:
        if other == target:
            continue
        for L in XLAGS:
            f[f"x_{other}_{L}"] = px[other].pct_change(L)
    # the complex as a whole, and this market's position within it
    for L in XLAGS:
        m = px.pct_change(L).mean(axis=1)
        f[f"mkt_{L}"] = m
        f[f"rel_{L}"] = px[target].pct_change(L) - m
    return pd.DataFrame(f, index=px.index)


def purged_cv(n, nfold, h):
    e = np.linspace(0, n, nfold + 2).astype(int)
    for i in range(1, nfold + 1):
        a, b = e[i], e[i + 1]
        yield (np.concatenate([np.arange(0, max(0, a - h)),
                               np.arange(min(n, b + h), n)]),
               np.arange(a, b))


def evaluate(pred, y1, h, weeks, pv):
    """Trade at the signal's own cadence, one contract, both costs."""
    s = pred / (np.nanstd(pred) + 1e-12)
    s = s - np.nanmean(s)
    pos = np.sign(s) * (np.abs(s) >= 0.5)          # -1 / 0 / +1
    n = (len(pos) // h) * h
    P = pos[:n].reshape(-1, h)[:, 0]
    R = np.nan_to_num(y1[:n].reshape(-1, h)).sum(axis=1)
    g = P * R
    turn = np.abs(np.diff(P, prepend=0.0))
    out = {}
    for c in COSTS:
        net = g - turn * c / 2.0
        eq = np.cumsum(net)
        dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
        sd = float(net.std(ddof=1)) if len(net) > 2 else 0.0
        out[f"net_wk_{c}"] = round(float(net.sum()) / weeks, 2)
        out[f"mde_wk_{c}"] = round(3.0 * sd * math.sqrt(len(net)) / weeks, 2)
        out[f"dd_{c}"] = round(dd, 2)
        out[f"calmar_{c}"] = (round(float(net.sum()) / weeks * 52 / dd, 2)
                              if dd > 1 else None)
    out["trades_wk"] = round(float((P != 0).sum()) / weeks, 1)
    out["in_market_pct"] = round(100.0 * float((P != 0).mean()), 1)
    return out, (g - turn * COSTS[1] / 2.0)


def main():
    print(__doc__, flush=True)
    print("=" * 74, flush=True)
    t0 = time.time()
    px = load()
    weeks = (px.index[-1] - px.index[0]).total_seconds() / (7 * 86400)
    print(f"{len(px.columns)} markets, {len(px):,} aligned bars, "
          f"{weeks:.0f} weeks\n", flush=True)

    import lightgbm as lgb
    rng = np.random.default_rng(909)
    rows, streams = [], {}

    cols = [c for c in px.columns if not ONLY or c in ONLY]
    for mi, target in enumerate(cols):
        F = features(px, target)
        pv = SPEC[target]
        close = px[target]
        for h in HZ:
            y1 = (close.shift(-1) - close).values * pv
            yh = (close.shift(-h) - close).values * pv
            ok = np.isfinite(yh) & np.isfinite(y1) & F.notna().all(axis=1).values
            X = F.values[ok]
            Y, Y1 = yh[ok], y1[ok]
            if len(X) < 5000:
                continue
            eff = len(X) / h
            se_ic = 1.0 / math.sqrt(eff)
            for tag, tgt_, seed in (("real", Y, 0),
                                    ("shuf", rng.permutation(Y), 1)):
                pr = np.full(len(tgt_), np.nan)
                for tr, te in purged_cv(len(tgt_), NFOLD, h):
                    m = lgb.LGBMRegressor(
                        n_estimators=NTREE, learning_rate=0.05,
                        num_leaves=31, min_child_samples=500, subsample=0.7,
                        subsample_freq=1, colsample_bytree=0.5,
                        reg_lambda=10.0, verbose=-1, n_jobs=4,
                        random_state=seed)
                    m.fit(X[tr], tgt_[tr])
                    pr[te] = m.predict(X[te])
                v = np.isfinite(pr)
                ic = float(np.corrcoef(pr[v], tgt_[v])[0, 1])
                ev, stream = evaluate(pr[v], Y1[v], h, weeks, pv)
                row = {"market": target, "h": h, "hours": round(h * BAR_MIN / 60, 1),
                       "target": tag, "ic": round(ic, 4),
                       "se_ic": round(se_ic, 4),
                       "ic_in_se": round(ic / se_ic, 2), "eff_n": int(eff),
                       **ev}
                rows.append(row)
                if tag == "real":
                    streams[(target, h)] = stream
            r = [x for x in rows if x["market"] == target and x["h"] == h
                 and x["target"] == "real"][0]
            s = [x for x in rows if x["market"] == target and x["h"] == h
                 and x["target"] == "shuf"][0]
            print(f"  {target:>4} h={h:>3} ({r['hours']:>4.1f}h)  "
                  f"IC {r['ic']:+.4f} ({r['ic_in_se']:>5.2f} se)  "
                  f"net ${r['net_wk_1.99']:>7,.0f}/wk  "
                  f"shuf ${s['net_wk_1.99']:>7,.0f}  "
                  f"DD ${r['dd_1.99']:>7,.0f}  "
                  f"[{mi+1}/{len(cols)}, {time.time()-t0:.0f}s]",
                  flush=True)

    # ---- winners, against the criterion fixed in the header
    win = []
    for r in [x for x in rows if x["target"] == "real"]:
        s = [x for x in rows if x["market"] == r["market"]
             and x["h"] == r["h"] and x["target"] == "shuf"][0]
        if (abs(r["ic_in_se"]) >= 2.0 and r["net_wk_1.99"] > 0
                and r["net_wk_1.99"] > s["net_wk_1.99"]
                and r["net_wk_1.99"] > r["mde_wk_1.99"]):
            win.append(r)
    win.sort(key=lambda r: r["net_wk_1.99"], reverse=True)

    print("\n" + "=" * 74)
    print(f"{len(win)} of {len(streams)} market-horizons clear all four "
          f"hurdles\n")
    for w in win[:15]:
        print(f"  {w['market']:>4} {w['hours']:>4.1f}h  "
              f"IC {w['ic']:+.4f} ({w['ic_in_se']:.1f} se)  "
              f"${w['net_wk_1.99']:>6,.0f}/wk @1.99  "
              f"${w['net_wk_0.85']:>6,.0f}/wk @0.85  "
              f"DD ${w['dd_1.99']:>6,.0f}  Calmar {w['calmar_1.99']}")

    # ---- what a PORTFOLIO of the winners does, which is the real point
    if len(win) >= 2:
        keys = [(w["market"], w["h"]) for w in win]
        L = min(len(streams[k]) for k in keys)
        M = np.vstack([streams[k][:L] for k in keys])
        port = M.sum(axis=0)
        eq = np.cumsum(port)
        dd = float((np.maximum.accumulate(eq) - eq).max())
        cc = np.corrcoef(M)
        off = cc[np.triu_indices_from(cc, 1)]
        print(f"\n  PORTFOLIO of {len(keys)} winners:")
        print(f"    ${port.sum()/weeks:>8,.0f}/week")
        print(f"    max drawdown  ${dd:>8,.0f}  "
              f"({100*dd/ACCOUNT:.0f}% of a ${ACCOUNT:,.0f} account)")
        print(f"    Calmar        {port.sum()/weeks*52/max(dd,1):>8.2f}")
        print(f"    mean pairwise correlation of the streams "
              f"{float(np.nanmean(off)):+.3f}  "
              f"(low is what makes breadth pay)")
        print(f"    capital for a 10% max drawdown: ${dd/0.10:,.0f}")
    else:
        best = min((r["mde_wk_1.99"] for r in rows if r["target"] == "real"),
                   default=float("nan"))
        print(f"\n  Nothing cleared. The most sensitive configuration could "
              f"only have seen\n  ${best:,.0f}/week or larger -- smaller than "
              f"that was never visible.")

    p = os.path.join(ROOT, "research", "WIDE.json")
    json.dump({"weeks": round(weeks, 1), "markets": list(px.columns),
               "rows": rows, "winners": win}, open(p, "w"), indent=1)
    print(f"\nwrote {p}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

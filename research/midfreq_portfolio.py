"""Round 3: PORTFOLIO of robust low-frequency edges -> the user's band.

Single configs at 100-300 trades/wk are underwater everywhere (2,064
honest tests). But the requirement is the ACCOUNT's totals. This round
re-runs every all-years-positive finalist capturing per-trade
timestamps, prunes correlated duplicates, and measures the combined
portfolio: total trades/wk, $/wk, worst week, max DD -- all at 1 MNQ
per signal (concurrent signals stack temporarily; also reported).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from research.midfreq_search import (FEES, PT, SLIP, load_bars, resample)

OUT = "research/midfreq_portfolio.json"


def trades_for(df, name):
    """Re-run one finalist config, returning list of (exit_ts, pnl$).
    Name grammar mirrors midfreq_search round-2 emit names."""
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    idx = df.index
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    ts = idx.asi8
    cs = pd.Series(c)
    tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    rth = (hrs >= 13.5) & (hrs < 20.9)

    parts = name.split("_")
    fam = parts[0]
    sess = parts[-1]
    mask = rth if sess == "rth" else np.ones(len(c), bool)
    exitspec = parts[-2]                      # e.g. time60h0 / trail2.5h10
    if exitspec.startswith("time"):
        mode = "time"
        p1, p2 = exitspec[4:].split("h")
        p1, p2 = float(p1), float(p2)
    else:
        mode = "trail"
        p1, p2 = exitspec[5:].split("h")
        p1, p2 = float(p1), float(p2)

    if fam == "THRX":
        k = float(parts[1][1:])
        thr = (h - l) > k * atr
        raw_l, raw_s = thr & (c > o), thr & (c < o)
    elif fam == "DONX":
        N = int(parts[1][1:])
        raw_l = c > pd.Series(h).rolling(N).max().shift(1).to_numpy()
        raw_s = c < pd.Series(l).rolling(N).min().shift(1).to_numpy()
    elif fam == "RSI2":
        delta = cs.diff()
        up = delta.clip(lower=0).rolling(2).mean()
        dn = (-delta.clip(upper=0)).rolling(2).mean()
        rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
        sma200 = cs.rolling(200).mean().to_numpy()
        raw_l = (rsi2 < 10) & (c > sma200)
        raw_s = (rsi2 > 90) & (c < sma200)
    elif fam == "IMPX":
        w = int(parts[1][1]); imp = float(parts[1].split("i")[1])
        mom = cs.diff(w).to_numpy()
        raw_l, raw_s = mom <= -imp, mom >= imp
    else:
        return []

    sig = np.where(raw_l & mask, 1, np.where(raw_s & mask, -1, 0))
    out = []
    n = len(c)
    i = 0
    while i < n - 2:
        s = sig[i]
        if s == 0:
            i += 1
            continue
        ei = i + 1
        entry = o[ei] + SLIP * s
        hard = entry - p2 * s if p2 > 0 else None
        peak = entry
        j = ei
        end = min(n - 1, ei + 300)
        pnl_pts = None
        while j <= end:
            if hard is not None and ((s > 0 and l[j] <= hard)
                                     or (s < 0 and h[j] >= hard)):
                pnl_pts = (hard - SLIP * s - entry) * s
                break
            if mode == "trail":
                peak = max(peak, h[j]) if s > 0 else min(peak, l[j])
                tp = peak - p1 * atr[j] * s
                if (s > 0 and l[j] <= tp) or (s < 0 and h[j] >= tp):
                    pnl_pts = (tp - SLIP * s - entry) * s
                    break
            elif mode == "time" and j - ei >= p1:
                pnl_pts = (c[j] - entry) * s
                break
            j += 1
        if pnl_pts is None:
            j = min(j, n - 1)
            pnl_pts = (c[j] - entry) * s
        out.append((ts[j], pnl_pts * PT - FEES))
        i = j + 1
    return out


def main():
    base = load_bars()
    span_days = (base.index[-1] - base.index[0]).days
    res = pd.read_csv("research/midfreq_results2.csv")
    fin = res[(res.pos_years == res.n_years) & (res.usd_wk > 40)]
    fin = fin.sort_values("usd_wk", ascending=False)
    print(f"finalists (all-years-positive, >$40/wk): {len(fin)}")

    frames = {tf: resample(base, tf) for tf in ("1min", "3min", "5min")}
    legs = {}
    for _, r in fin.iterrows():
        tf = r["tf"]
        trs = trades_for(frames[tf], r["name"])
        if trs:
            legs[r["name"]] = trs
            print(f"  {r['name']}: {len(trs)} trades, "
                  f"${sum(p for _, p in trs):,.0f}")

    # Correlation prune: weekly P&L series per leg; drop legs >0.7
    # correlated with an already-kept better leg.
    def weekly(trs):
        s = pd.Series({pd.Timestamp(t, unit="ns", tz="UTC"): p
                       for t, p in trs})
        return s.resample("1W").sum()

    wk = {k: weekly(v) for k, v in legs.items()}
    kept = []
    for name in legs:                       # already ordered by usd_wk
        ok = True
        for kname in kept:
            a, b = wk[name].align(wk[kname], fill_value=0)
            if len(a) > 10 and a.corr(b) > 0.7:
                ok = False
                break
        if ok:
            kept.append(name)
    print(f"\nkept after correlation prune (<0.7): {len(kept)}")

    # Portfolio series
    allw = None
    total_trades = 0
    for k in kept:
        total_trades += len(legs[k])
        w = wk[k]
        allw = w if allw is None else allw.add(w, fill_value=0)
    port = {
        "legs": kept,
        "n_legs": len(kept),
        "trades_per_week": round(total_trades / (span_days / 7), 1),
        "usd_per_week_avg": round(float(allw.mean()), 1),
        "usd_per_week_median": round(float(allw.median()), 1),
        "worst_week": round(float(allw.min()), 1),
        "best_week": round(float(allw.max()), 1),
        "pct_weeks_positive": round(100 * float((allw > 0).mean()), 1),
        "total": round(float(allw.sum()), 0),
        "max_dd_weekly_basis": round(float(
            (allw.cumsum().cummax() - allw.cumsum()).max()), 0),
        "yearly": {str(y): round(float(v), 0) for y, v in
                   allw.groupby(allw.index.year).sum().items()},
    }
    print(json.dumps(port, indent=1))
    with open(OUT, "w") as fh:
        json.dump({"portfolio": port,
                   "legs_detail": {k: {"trades": len(legs[k]),
                                       "total": round(sum(p for _, p in legs[k]), 0)}
                                    for k in kept}}, fh, indent=1)


if __name__ == "__main__":
    main()

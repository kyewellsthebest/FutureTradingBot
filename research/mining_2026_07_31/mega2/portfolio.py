"""Assemble a multi-market book from per-config weekly P&L.

The target is roughly 200 trades a week and roughly $1,000 a week. No single
config gets there: the best NQ survivors earn $6-10 per trade but fire eight to
seventeen times a week. Total P&L is (dollars per trade) x (trades per week) x
(number of streams), and only the last term is ours to choose. So the job is
selecting streams that stack.

Two rules make the difference between a book and a spreadsheet fantasy:

SELECT ON TRAIN, REPORT ON HOLDOUT. Streams are chosen using training weeks
only. The holdout weeks are then scored once, untouched. A portfolio optimised
over all weeks will always look wonderful and mean nothing.

DIVERSIFY ON MEASURED CORRELATION, NOT ON LABELS. Two configs on different
markets can still be the same trade -- ES and NQ both fade the same Fed
headline. Adding average weekly P&L across streams silently assumes perfect
diversification; here each candidate carries its actual weekly P&L vector, so
correlation is measured and a candidate too close to what is already in the
book is rejected however good it looks alone.

Usage: python portfolio.py <results_dir> [--trades 200] [--maxcorr 0.35]
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import re

import numpy as np
import pandas as pd

# Identity of a strategy, for collapsing the many near-duplicate rows a grid
# search emits. Rows differing only in a max hold the trade never reaches are
# the same trade seen twice.
IDENT = ["market", "tf", "fam", "lb", "k", "pb", "dep", "man", "N", "buf",
         "m", "g", "r", "ttl", "sp", "rr", "trail",
         "f_sess", "f_trend", "f_vol", "f_vix", "f_htf"]


def load(d, cap_per_shard=1200, hold_frac=0.20):
    """Every ranked config plus its weekly P&L, aligned to a common calendar.

    Markets do not share a span -- NG starts in 2022, ZS in late 2023 -- so
    each shard's weekly vector covers a different set of weeks. Stacking them
    positionally would silently add up P&L from different calendar weeks and
    invent diversification that does not exist. Everything is reindexed onto
    the union of weeks, missing weeks are zero (that market simply was not
    trading), and the train/holdout split is taken once on the global calendar
    so every stream is judged over the same period.
    """
    shards = []
    for jf in sorted(glob.glob(os.path.join(d, "**", "pf*_*.json.gz"), recursive=True)):
        base = os.path.basename(jf)
        m = re.match(r"pf(.+?)_([A-Z0-9]+)\.json\.gz$", base)
        if not m:
            continue
        suf, mkt = m.group(1), m.group(2)
        nf = os.path.join(os.path.dirname(jf), f"pf{suf}wk_{mkt}.npz")
        if not os.path.exists(nf):
            continue
        try:
            o = json.load(gzip.open(jf, "rt"))
            z = np.load(nf, allow_pickle=True)
        except Exception as e:
            print(f"  SKIP {base}: {e}")
            continue
        top, W, wks = o.get("top", []), z["wk"], [str(x) for x in z["weeks"]]
        if not top or len(W) != len(top) or W.shape[1] != len(wks):
            print(f"  SKIP {base}: {len(top)} rows / {W.shape} / {len(wks)} weeks")
            continue
        if len(top) > cap_per_shard:                 # keep the best by $/trade
            k = np.argsort([-(r.get("ev") or 0) for r in top])[:cap_per_shard]
            top, W = [top[i] for i in k], W[k]
        shards.append((mkt, o, top, W, wks))
    if not shards:
        return pd.DataFrame(), np.zeros((0, 0)), pd.DataFrame(), None, None

    allw = sorted({w for _, _, _, _, wk in shards for w in wk})
    pos = {w: i for i, w in enumerate(allw)}
    nW = len(allw)
    split = int(round(nW * (1.0 - hold_frac)))
    train = np.zeros(nW, bool); train[:split] = True
    hold = ~train
    print(f"  global calendar: {nW} weeks, {allw[0]} .. {allw[-1]} "
          f"(holdout from {allw[split]})")

    rows, mats, meta = [], [], []
    for mkt, o, top, W, wks in shards:
        cols = np.array([pos[w] for w in wks])
        A = np.zeros((len(top), nW), np.float32)
        A[:, cols] = W
        off = sum(len(x) for x in mats)
        for i, r in enumerate(top):
            r["market"], r["tf"], r["row"] = mkt, o.get("series", "?"), off + i
            rows.append(r)
        mats.append(A)
        meta.append({"market": mkt, "tf": o.get("series"),
                     "n_cfg": o.get("n_cfg", 0), "n_gated": o.get("n_gated", 0)})
    return pd.DataFrame(rows), np.vstack(mats), pd.DataFrame(meta), train, hold


def assemble(df, M, train, hold, target_trades, maxcorr, per_market, per_family):
    """Greedy forward selection on training weeks.

    At each step take the candidate that most improves the book's training
    Sharpe, skipping anything correlated above `maxcorr` with a stream already
    held. Stop when the trade budget is met or nothing improves the book.
    """
    Mtr = M[:, train]
    sd = Mtr.std(axis=1)
    live = np.where((sd > 1e-9) & (Mtr.mean(axis=1) > 0))[0]
    print(f"  {len(live):,} candidates with positive training P&L")
    Z = (Mtr - Mtr.mean(axis=1, keepdims=True)) / np.maximum(sd, 1e-9)[:, None]
    nw = Mtr.shape[1]

    chosen, cur = [], np.zeros(nw)
    mk_count, fam_count, trades = {}, {}, 0.0
    order = np.argsort(-(Mtr[live].mean(1) / np.maximum(sd[live], 1e-9)))
    pool = live[order][:9000]                       # best 6k by solo Sharpe

    # Take the best available stream each round rather than only ones that
    # improve the book's Sharpe. Requiring improvement stops the book at a
    # handful of streams and makes every trade budget produce the same answer,
    # which is exactly what happened. Weekly Sharpe grows with the square root
    # of trade count, so a stream that dilutes Sharpe slightly today still
    # helps once the budget is filled; the correlation cap, not a Sharpe
    # ratchet, is what keeps the book from stacking the same bet.
    while trades < target_trades:
        best, best_sh = None, -1e9
        for c in pool:
            r = df.iloc[c]
            if mk_count.get(r.market, 0) >= per_market:
                continue
            if fam_count.get((r.market, r.fam), 0) >= per_family:
                continue
            if chosen:
                # correlation against every stream already in the book
                if np.abs(Z[c] @ Z[[x for x in chosen]].T / nw).max() > maxcorr:
                    continue
            cand = cur + Mtr[c]
            sh = cand.mean() / max(cand.std(), 1e-9)
            if sh > best_sh:
                best_sh, best = sh, c
        if best is None:
            # Distinguish the two very different reasons for stopping: a cap
            # we chose, versus genuinely running out of uncorrelated edge.
            capped = [m for m, v in mk_count.items() if v >= per_market]
            famcap = [f"{m}/{f}" for (m, f), v in fam_count.items() if v >= per_family]
            why = ("per-market cap hit on " + ",".join(capped) if capped else "") or \
                  ("per-family cap hit on " + ",".join(famcap[:6]) if famcap else "") or \
                  "no remaining candidate is uncorrelated enough"
            print(f"  stopped at {trades:.0f} trades/wk, {len(chosen)} streams: {why}")
            break
        r = df.iloc[best]
        chosen.append(best)
        cur = cur + Mtr[best]
        mk_count[r.market] = mk_count.get(r.market, 0) + 1
        fam_count[(r.market, r.fam)] = fam_count.get((r.market, r.fam), 0) + 1
        trades += float(r.get("tpw", 0) or 0)
    return chosen, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default="pf_results")
    ap.add_argument("--trades", type=float, default=200.0)
    ap.add_argument("--maxcorr", type=float, default=0.35)
    ap.add_argument("--per-market", type=int, default=10)
    ap.add_argument("--per-family", type=int, default=5)
    # When the goal is a trade budget, a stream that fires four times a week
    # cannot help you reach five hundred however good its Sharpe is. Screening
    # the pool on frequency first spends the limited supply of uncorrelated
    # streams on the ones that actually carry trades.
    ap.add_argument("--min-tpw", type=float, default=0.0)
    a = ap.parse_args()

    df, M, meta, train, hold = load(a.dir)
    out = a.dir
    if not len(df):
        with open(os.path.join(out, "PORTFOLIO.md"), "w") as f:
            f.write("# Portfolio\n\nNo candidates.\n")
        print("NO CANDIDATES")
        return
    print(f"loaded {len(df):,} configs across {df.market.nunique()} markets, "
          f"matrix {M.shape}, {int(train.sum())} train / {int(hold.sum())} holdout weeks")

    # A resting limit that merely touches its price does not fill: the NQ tape
    # shows a median of two contracts at a bar's low, nowhere near enough to
    # clear a real queue. mf=1 configs required price to trade a full tick
    # through. Every earlier book was silently built on mf=0, the optimistic
    # convention, because this filter lived in the tick merge and never here.
    if "mf" in df.columns and "etype" in df.columns:
        n0 = len(df)
        df = df[(df.etype != "L") | (df.mf >= 1.0)].reset_index(drop=True)
        print(f"  honest-fill filter: {n0:,} -> {len(df):,} candidates "
              f"(dropped bare-touch limit entries)")
        if not len(df):
            print("  nothing survives the honest fill requirement")
    if a.min_tpw > 0 and "tpw" in df.columns:
        n0 = len(df)
        df = df[df.tpw >= a.min_tpw].reset_index(drop=True)
        print(f"  frequency screen >={a.min_tpw:g} trades/wk: {n0:,} -> {len(df):,}")
    ident = [c for c in IDENT if c in df.columns]
    keep = df.sort_values("ev", ascending=False).drop_duplicates(subset=ident).index
    df2 = df.loc[sorted(keep)].reset_index(drop=True)
    M2 = M[df2.row.values]
    print(f"deduplicated to {len(df2):,} distinct strategies")

    chosen, trades = assemble(df2, M2, train, hold, a.trades, a.maxcorr,
                              a.per_market, a.per_family)
    book = df2.iloc[chosen].copy()
    B = M2[chosen]
    tr_wk, ho_wk = B.sum(0)[train], B.sum(0)[hold]

    def stats(v):
        if not len(v):
            return {}
        cum = np.cumsum(v)
        dd = cum - np.maximum.accumulate(cum)
        return dict(per_week=round(float(v.mean()), 2),
                    median_week=round(float(np.median(v)), 2),
                    pos_weeks=round(float((v > 0).mean()), 3),
                    worst_week=round(float(v.min()), 0),
                    best_week=round(float(v.max()), 0),
                    sharpe=round(float(v.mean() / max(v.std(), 1e-9)), 3),
                    maxdd=round(float(dd.min()), 0),
                    total=round(float(v.sum()), 0))
    tr_s, ho_s = stats(tr_wk), stats(ho_wk)

    res = dict(streams=len(chosen), trades_per_week=round(trades, 1),
               markets=int(book.market.nunique()) if len(book) else 0,
               train=tr_s, holdout=ho_s,
               config=dict(target_trades=a.trades, maxcorr=a.maxcorr,
                           per_market=a.per_market, per_family=a.per_family),
               configs_searched=int(meta.n_cfg.sum()) if len(meta) else 0)
    with gzip.open(os.path.join(out, "PORTFOLIO.json.gz"), "wt") as f:
        json.dump({"result": res, "book": book.to_dict("records")}, f)

    L = ["# Portfolio — multi-market book\n",
         f"- searched **{res['configs_searched']:,}** configs across "
         f"{df.market.nunique()} markets",
         f"- book: **{len(chosen)} streams** over **{res['markets']} markets**, "
         f"**{trades:.0f} trades/week**",
         f"- selected on {int(train.sum())} training weeks; the "
         f"{int(hold.sum())} holdout weeks below were never used to choose\n"]
    if len(chosen):
        # Weekly Sharpe rises with sqrt(trade count) at fixed edge quality, so
        # report it next to frequency: that pairing is what a "clean equity
        # curve" actually means.
        L.append(f"- **{trades:.0f} trades/week**, holdout Sharpe "
                 f"**{ho_s.get('sharpe', 0):.2f}**, "
                 f"{ho_s.get('pos_weeks', 0)*100:.0f}% of holdout weeks positive\n")
    L.append("| | train | holdout |")
    L.append("|---|---|---|")
    for k in ("per_week", "median_week", "pos_weeks", "worst_week",
              "maxdd", "sharpe", "total"):
        L.append(f"| {k.replace('_',' ')} | {tr_s.get(k,'')} | {ho_s.get(k,'')} |")
    verdict = ("holdout holds up — worth exact replay"
               if ho_s.get("per_week", 0) > 0.5 * tr_s.get("per_week", 1)
               else "holdout collapses versus train — the book is fitted")
    L.append(f"\n**Reading: {verdict}**\n")

    if len(book):
        L.append("## Market mix\n")
        mm = book.groupby("market").agg(streams=("ev", "size"),
                                        trades_wk=("tpw", "sum"),
                                        ev=("ev", "mean")).round(2)
        L.append("| market | streams | trades/wk | avg $/trade |")
        L.append("|---|---|---|---|")
        for m_, r_ in mm.sort_values("trades_wk", ascending=False).iterrows():
            L.append(f"| {m_} | {int(r_.streams)} | {r_.trades_wk:.1f} | {r_.ev:.2f} |")
        L.append("\n## The book\n")
        cols = [c for c in ["market", "tf", "fam", "etype", "mf", "H_min", "tpw",
                            "n_tr", "wk", "ev", "pf", "poswk", "maxdd", "o10"]
                if c in book.columns]
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "---|" * len(cols))
        for _, r_ in book.iterrows():
            L.append("| " + " | ".join(
                f"{r_[c]:,.2f}" if isinstance(r_[c], float) else str(r_[c])
                for c in cols) + " |")
    with open(os.path.join(out, "PORTFOLIO.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"book: {len(chosen)} streams, {trades:.0f} trades/wk, "
          f"train ${tr_s.get('per_week',0):,.0f}/wk, "
          f"holdout ${ho_s.get('per_week',0):,.0f}/wk")


if __name__ == "__main__":
    main()

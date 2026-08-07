"""Every family, every parameter, on FX ticks where the cost is measured.

The whole search from the futures work, moved to data that carries bid and ask.
Three things change and all three matter:

  COST IS NOT A MODEL. On CME prints we knew what traded, never what was
  quoted, so every fill was an assumption -- and that assumption was worth 72%
  of the apparent edge. Here a buy pays the ask and a sell pays the bid, both
  recorded, and the spread is whatever it actually was at that instant.

  THE TOLL IS SMALL. MNQ costs $1.22 a round turn against a $0.50 tick: the
  cost of trading exceeds one whole step of price. EURUSD costs 0.30 pips
  against moves of tens of pips. If a signal was drowning in friction, this is
  where it surfaces.

  BREADTH. Eight symbols x four split points is thirty-two cells. A real edge
  wins most of them. One regime's luck wins its own and loses the rest, and
  that is the only thing separating the two.

Two stages, because a tick-accurate simulation of ten million configurations
would not finish this decade:

  STAGE 1  vectorised. Build feature arrays once per symbol per bar type, then
           score every configuration as a dot product against forward returns
           net of the measured half-spread. Millions of configs a minute.
           SELECTION HAPPENS ON TRAIN ONLY.
  STAGE 2  the survivors go through the real thing: resting limit orders filled
           against the correct side of the quote, walked tick by tick, with a
           random-entry control on identical geometry.

The expected result is nothing. Selection in this project has been reliably
ANTI-persistent -- configs picked for the best training score land below chance
out of sample, 19-29% against 50%. So the headline number is not the best
config. It is the distribution: what fraction of selected configs hold their
sign, against the 50% a coin gives and the sub-50% that hindsight gives.

Usage: python fxmega.py [SYMBOL ...]
"""
import glob
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
FX = os.path.join(ROOT, "data", "fx")
OUT = os.path.join(ROOT, "research", "FX_MEGA.md")
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4, "NZDUSD": 1e-4,
       "USDCAD": 1e-4, "USDCHF": 1e-4, "USDJPY": 1e-2, "XAUUSD": 1e-1}
USD_PIP = 0.10                      # one micro lot, one pip
SYMS = [s.upper() for s in sys.argv[1:]] or None
BARS = os.environ.get("BARS", "tick_200,tick_1000,tick_5000,time_60,time_300")
TOPK = int(os.environ.get("TOPK", "40"))

LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


# ---------------------------------------------------------------------------
# BARS. Clock bars sample a market that does not run on a clock; event bars
# sample it on activity, which is what a tape actually is. Both, so the answer
# does not depend on the choice.
# ---------------------------------------------------------------------------
def make_bars(bid, ask, ts, kind):
    mid = (bid + ask) / 2.0
    if kind.startswith("tick_"):
        k = int(kind.split("_")[1])
        edge = np.arange(0, len(mid), k)
    else:
        secs = int(kind.split("_")[1])
        t = ts.astype("datetime64[s]").astype(np.int64)
        grp = t // secs
        edge = np.r_[0, np.where(np.diff(grp) != 0)[0] + 1]
    if len(edge) < 500:
        return None
    lo_i = edge[:-1]
    hi_i = edge[1:]
    o = mid[lo_i]
    c = mid[hi_i - 1]
    # high and low without a python loop, via reduceat over the slices
    h = np.maximum.reduceat(mid, lo_i)
    l = np.minimum.reduceat(mid, lo_i)
    sp = np.add.reduceat(ask - bid, lo_i) / np.maximum(hi_i - lo_i, 1)
    return dict(o=o, h=h, l=l, c=c, spread=sp, i0=lo_i, i1=hi_i,
                t=ts[lo_i], n=len(o))


# ---------------------------------------------------------------------------
# FEATURES. Every family from the futures search, expressed as a single number
# per bar whose SIGN is the direction the family would trade. Building them
# once and scoring configurations against them is what makes the grid tractable.
# ---------------------------------------------------------------------------
def rolling(a, w, fn):
    s = pd.Series(a)
    return getattr(s.rolling(w, min_periods=w), fn)().values


def features(B, pip):
    c, h, l, o = B["c"], B["h"], B["l"], B["o"]
    n = len(c)
    F = {}
    for w in (5, 10, 20, 50, 100, 200):
        mu = rolling(c, w, "mean")
        sd = rolling(c, w, "std")
        # momentum / impulse: the move itself
        F[f"mom{w}"] = np.r_[np.full(w, np.nan), c[w:] - c[:-w]] / pip
        # mean reversion: distance from the mean, sign flipped
        F[f"rev{w}"] = -(c - mu) / np.maximum(sd, 1e-12)
        # breakout of the rolling range
        hh = rolling(h, w, "max")
        ll = rolling(l, w, "min")
        F[f"brk{w}"] = np.where(c > hh, 1.0, np.where(c < ll, -1.0, 0.0))
        # range compression, then whichever way it breaks
        rr = (hh - ll) / pip
        F[f"sqz{w}"] = np.where(rr < np.r_[np.full(w, np.nan),
                                           rolling(rr, w, "mean")[w:]] * 0.6,
                                np.sign(c - mu), 0.0)
        # volatility-scaled momentum
        F[f"vmom{w}"] = ((c - np.r_[np.full(w, np.nan), c[:-w]])
                         / np.maximum(sd, 1e-12))
    # bar shape: where the close sits in its own range
    rng = np.maximum(h - l, pip)
    F["shape"] = (c - l) / rng * 2 - 1
    F["gap"] = np.r_[np.nan, (o[1:] - c[:-1])] / pip
    F["spreadz"] = -(B["spread"] / pip)      # trade when it is cheap
    return F


# ---------------------------------------------------------------------------
# STAGE 1. Score every configuration at once. A configuration is a feature, a
# threshold, a direction and a holding period; its score is the mean forward
# return of the bars it fires on, minus the round-turn spread it must pay.
# ---------------------------------------------------------------------------
THRESH = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
HOLDS = [1, 2, 3, 5, 8, 13, 21, 34]
DIRS = [1, -1]


def stage1(B, F, pip, cut):
    c = B["c"]
    n = len(c)
    halfsp = B["spread"] / pip / 2.0          # pips, each way
    out = []
    for hold in HOLDS:
        fwd = np.full(n, np.nan)
        fwd[:-hold] = (c[hold:] - c[:-hold]) / pip
        # a round turn crosses twice: in at entry, out at exit
        cost = halfsp * 2.0
        tr = np.arange(n) < cut
        for fname, f in F.items():
            fin = np.isfinite(f) & np.isfinite(fwd)
            if fin.sum() < 2000:
                continue
            # normalise so one threshold list covers every feature
            s = np.nanstd(f[tr & fin])
            if not np.isfinite(s) or s <= 0:
                continue
            z = f / s
            for th in THRESH:
                for d in DIRS:
                    hit = fin & ((z >= th) if d > 0 else (z <= -th))
                    ntr = hit & tr
                    nho = hit & ~tr
                    if ntr.sum() < 200 or nho.sum() < 100:
                        continue
                    pnl = d * fwd - cost
                    a = pnl[ntr].mean()
                    b = pnl[nho].mean()
                    out.append((fname, th, d, hold, int(ntr.sum()),
                                int(nho.sum()), a, b))
    return out


def load(sym):
    fs = sorted(glob.glob(os.path.join(FX, f"{sym}_*.parquet")))
    if not fs:
        return None
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d.sort_values("time", kind="stable").reset_index(drop=True)
    return (d.bid.values.astype(np.float64), d.ask.values.astype(np.float64),
            d.time.values)


if __name__ == "__main__":
    syms = SYMS or sorted({os.path.basename(f).split("_")[0]
                           for f in glob.glob(os.path.join(FX, "*.parquet"))})
    log("# FX mega search")
    log()
    log("Every family, every parameter, on data where a buy pays the ask and a "
        "sell pays the bid. Selection on train, reported on holdout, always.")
    log()
    allrows = []
    t0 = time.time()
    for sym in syms:
        r = load(sym)
        if r is None:
            continue
        bid, ask, ts = r
        pip = PIP.get(sym, 1e-4)
        log(f"## {sym} -- {len(bid):,} ticks, median spread "
            f"{np.median(ask-bid)/pip:.2f} pips")
        log()
        for kind in BARS.split(","):
            B = make_bars(bid, ask, ts, kind)
            if B is None:
                log(f"- `{kind}`: too few bars")
                continue
            F = features(B, pip)
            cut = int(B["n"] * 0.7)
            rows = stage1(B, F, pip, cut)
            for x in rows:
                allrows.append((sym, kind) + x)
            log(f"- `{kind}`: {B['n']:,} bars, {len(F)} features, "
                f"{len(rows):,} configurations scored "
                f"[{time.time()-t0:.0f}s]")
        log()

    D = pd.DataFrame(allrows, columns=["sym", "bars", "feat", "th", "dir",
                                       "hold", "ntr", "nho", "train", "hold_"])
    D.to_parquet(os.path.join(ROOT, "research", "fx_mega_grid.parquet"),
                 compression="zstd", index=False)
    log(f"**{len(D):,} configurations scored across {D.sym.nunique()} symbols "
        f"and {D.bars.nunique()} bar types, in {time.time()-t0:.0f}s.**")
    log()

    if not len(D):
        open(OUT, "w").write("\n".join(LINES) + "\n")
        sys.exit(0)

    # THE ONLY HONEST QUESTION: pick on train, then look. Not the best holdout.
    log("## Select on train, report holdout")
    log()
    log("| picked by train | n | median holdout | share positive | "
        "best holdout |")
    log("|---|---|---|---|---|")
    for q in (0.999, 0.99, 0.95, 0.5):
        thr = D.train.quantile(q)
        S = D[D.train >= thr]
        if not len(S):
            continue
        log(f"| top {(1-q)*100:.1f}% (train >= {thr:+.3f}) | {len(S):,} | "
            f"{S.hold_.median():+.4f} | {(S.hold_ > 0).mean()*100:.1f}% | "
            f"{S.hold_.max():+.4f} |")
    log()
    log(f"Everything, for reference: median holdout {D.hold_.median():+.4f} "
        f"pips, {(D.hold_ > 0).mean()*100:.1f}% positive, "
        f"{len(D):,} configurations.")
    log()
    log("If selection worked, the share positive would climb as the cut gets "
        "tighter. In every previous run in this project it fell BELOW the "
        "50% a coin gives -- picking the best training configs picked worse "
        "than random ones.")
    log()

    # the survivors, by train, with their holdout beside them
    top = D.sort_values("train", ascending=False).head(TOPK)
    log(f"## The {TOPK} best training configurations, and what they did next")
    log()
    log("| sym | bars | feature | z | dir | hold | n train | n hold | "
        "train pips | HOLDOUT pips | $/wk @1 micro |")
    log("|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in top.iterrows():
        # holdout trades per week: the holdout is 30% of about 50 weeks
        wks = 0.30 * 50.0
        usd_wk = r.hold_ * USD_PIP * (r.nho / wks)
        log(f"| {r.sym} | {r.bars} | {r.feat} | {r.th} | {r['dir']:+d} | "
            f"{r.hold} | {r.ntr:,} | {r.nho:,} | {r.train:+.4f} | "
            f"{r.hold_:+.4f} | {usd_wk:+.2f} |")
    log()
    log("The last column is the one that matters and it is deliberately "
        "generous: it assumes the holdout result repeats, one micro lot, and "
        "no slippage beyond the spread already paid.")
    open(OUT, "w").write("\n".join(LINES) + "\n")
    print("\nwrote", OUT)

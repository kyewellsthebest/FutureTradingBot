"""Billions of configurations, by never evaluating one at a time.

The user asked for billions and the naive way cannot deliver: a config
evaluated as a python loop over bars is microseconds, and 5e9 of those is a
century. But a configuration here is an AND of simple conditions, and an AND of
indicator vectors is a product -- so the sum of a signal's P&L over every
configuration can be written as a matrix multiply and handed to BLAS.

  Let M be (masks x bars), 1 where a condition holds.
  Let p be the per-bar P&L of holding for h bars, net of the measured spread.

  PAIRS   sum over bars of Mi*Mj*p   =   M @ (p[:,None] * M.T)
  COUNTS  sum over bars of Mi*Mj     =   M @ M.T
  TRIPLES the same, with the pair-masks in place of M, in chunks

One matmul scores 213,000 configurations. Two hundred of them scores forty
million. The whole grid across eight symbols, five bar types and eight holding
periods runs into the billions and finishes in an hour on four cores, because
BLAS does not care how many configurations you called it.

Nothing is stored per configuration -- billions of rows do not fit anywhere.
What is stored is the only thing that answers the question:

  a 2D HISTOGRAM of training score against holdout outcome. From it, for any
  training cut, we can read exactly what fraction of the chosen configs held
  up and what they averaged. That is the anti-persistence curve.
  the exact TOP-K by training score, kept in a heap, with their holdout beside
  them -- the configs a normal search would have shipped.

The prediction, stated before the run: the share of selected configs that hold
their sign will FALL as the cut tightens, below the 50% a coin gives. Every
previous search in this project did that. If it happens again on eight symbols
and billions of configs, the conclusion is not "search harder".

Usage: python fxbillions.py [--triples] [SYMBOL ...]
"""
import gc
import glob
import heapq
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
FX = os.path.join(ROOT, "data", "fx")
OUT = os.path.join(ROOT, "research", "FX_BILLIONS.md")
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4, "NZDUSD": 1e-4,
       "USDCAD": 1e-4, "USDCHF": 1e-4, "USDJPY": 1e-2, "XAUUSD": 1e-1}
USD_PIP = 0.10
BARS = os.environ.get("BARS", "tick_200,tick_500,tick_2000,tick_10000,"
                              "time_60,time_600").split(",")
HOLDS = [int(x) for x in os.environ.get("HOLDS", "1,2,3,5,8,13,21,34").split(",")]
MINTR = int(os.environ.get("MINTR", "150"))      # min train bars in a config
MINHO = int(os.environ.get("MINHO", "60"))
TRIPLES = "--triples" in sys.argv
TRICHUNK = int(os.environ.get("TRICHUNK", "3000"))
TOPK = int(os.environ.get("TOPK", "60"))
CHUNKPAIR = int(os.environ.get("CHUNKPAIR", "8000"))
# compute scales linearly in bars, and XAUUSD has forty-four million ticks --
# tick_200 there is 223,000 bars and forty times the cost of the same cell on
# EURUSD. Cap it and say so, rather than let one symbol eat the whole run.
MAXBARS = int(os.environ.get("MAXBARS", "26000"))

# Histogram of training score -> holdout outcome, on a SIGNED LOG axis.
#
# The previous version binned linearly and capped at +12 pips, so every
# configuration above +12 fell in one bin -- 144 million of them, 7% of the
# population. The tightest selection cut it could resolve was therefore 7%,
# and it was printed in the report labelled "top 0.00001%". Training scores in
# this search reach +950 pips on XAUUSD, so a linear axis cannot cover the
# range and resolve the tail at the same time.
#
# sign(x) * log1p(|x|) does both: near zero it is linear (log1p(x) ~ x, so 0.007
# pip resolution), and at x = 100 pips a bin is still only ~0.7 pips wide, which
# is finer than anything the tail needs.
NBIN = 4001
TMAX = 7.0                                   # log1p(1096) -- beyond any score seen
EDGES_T = np.linspace(-TMAX, TMAX, NBIN)
NB = NBIN - 1


def _t(x):
    """Signed log, the axis the histogram lives on."""
    return np.sign(x) * np.log1p(np.abs(x))


def _t_inv(u):
    return np.sign(u) * np.expm1(np.abs(u))

# A container restart has now killed two multi-hour runs outright. State is
# small -- three histograms and a heap -- so there is no excuse for losing it.
CKPT = os.environ.get("CKPT", os.path.join(ROOT, "research", ".fxbillions_ckpt.npz"))
RESUME = os.environ.get("RESUME", "1") == "1"

LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


class Tally:
    """Constant memory, however many configurations go through it."""

    def __init__(self):
        self.n = np.zeros(NB, np.int64)
        self.pos = np.zeros(NB, np.int64)
        self.sho = np.zeros(NB, np.float64)
        self.total = 0
        self.top = []           # heap of (train, tag, holdout)

    def add(self, tr, ho, tags=None):
        b = np.digitize(_t(tr), EDGES_T) - 1
        np.clip(b, 0, NB - 1, out=b)
        self.n += np.bincount(b, minlength=NB)
        self.pos += np.bincount(b, weights=(ho > 0).astype(np.float64),
                                minlength=NB).astype(np.int64)
        self.sho += np.bincount(b, weights=ho, minlength=NB)
        self.total += len(tr)
        if tags is not None and len(tr):
            k = min(TOPK, len(tr))
            idx = np.argpartition(-tr, k - 1)[:k]
            for i in idx:
                item = (float(tr[i]), tags(int(i)), float(ho[i]))
                if len(self.top) < TOPK:
                    heapq.heappush(self.top, item)
                elif item[0] > self.top[0][0]:
                    heapq.heapreplace(self.top, item)

    def curve(self):
        """For each training cut, what the selected configs actually did."""
        rows = []
        cn = np.cumsum(self.n[::-1])[::-1]
        cp = np.cumsum(self.pos[::-1])[::-1]
        cs = np.cumsum(self.sho[::-1])[::-1]
        for frac in (1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 0.5, 1.0):
            want = max(1, int(self.total * frac))
            if (cn <= want).any():
                j = int(np.argmax(cn <= want))
            else:
                # every bin holds more than `want`; the tightest cut available
                # is the highest bin with anything in it. Reporting the whole
                # population here would print the same row nine times and call
                # the loosest cut the tightest one.
                nz = np.nonzero(cn)[0]
                j = int(nz[-1]) if len(nz) else 0
            if cn[j] == 0 or (rows and rows[-1][2] == int(cn[j])):
                continue
            rows.append((frac, _t_inv(EDGES_T[j]), int(cn[j]),
                         cp[j] / cn[j] * 100, cs[j] / cn[j]))
        return rows


def make_bars(bid, ask, ts, kind):
    mid = (bid + ask) / 2.0
    if kind.startswith("tick_"):
        k = int(kind.split("_")[1])
        edge = np.arange(0, len(mid), k)
    else:
        secs = int(kind.split("_")[1])
        t = ts.astype("datetime64[s]").astype(np.int64) // secs
        edge = np.r_[0, np.where(np.diff(t) != 0)[0] + 1]
    if len(edge) < 800:
        return None
    lo_i, hi_i = edge[:-1], edge[1:]
    return dict(o=mid[lo_i], c=mid[hi_i - 1],
                h=np.maximum.reduceat(mid, lo_i),
                l=np.minimum.reduceat(mid, lo_i),
                spread=np.add.reduceat(ask - bid, lo_i)
                / np.maximum(hi_i - lo_i, 1),
                n=len(lo_i))


def roll(a, w, fn):
    return getattr(pd.Series(a).rolling(w, min_periods=w), fn)().values


def base_masks(B, pip):
    """Every family as a condition. Each row of M is one condition."""
    c, h, l, o = B["c"], B["h"], B["l"], B["o"]
    n = len(c)
    feats = {}
    for w in (3, 5, 8, 13, 21, 34, 55, 89, 144, 233):
        mu = roll(c, w, "mean")
        sd = np.maximum(roll(c, w, "std"), 1e-12)
        prev = np.r_[np.full(w, np.nan), c[:-w]]
        feats[f"mom{w}"] = (c - prev) / pip
        feats[f"vmom{w}"] = (c - prev) / sd
        feats[f"rev{w}"] = -(c - mu) / sd
        hh, ll = roll(h, w, "max"), roll(l, w, "min")
        feats[f"pos{w}"] = (c - ll) / np.maximum(hh - ll, pip) * 2 - 1
        feats[f"rng{w}"] = ((hh - ll) / pip
                            - roll((hh - ll) / pip, w, "mean"))
        feats[f"acc{w}"] = (c - 2 * np.r_[np.full(w, np.nan), c[:-w]]
                            + np.r_[np.full(2 * w, np.nan), c[:-2 * w]]) / sd
    feats["shape"] = (c - l) / np.maximum(h - l, pip) * 2 - 1
    feats["gap"] = np.r_[np.nan, (o[1:] - c[:-1])] / pip
    feats["sprd"] = -(B["spread"] / pip)

    rows, tags = [], []
    for name, f in feats.items():
        fin = np.isfinite(f)
        if fin.sum() < n * 0.5:
            continue
        s = np.nanstd(f)
        if not np.isfinite(s) or s <= 0:
            continue
        z = np.where(fin, f / s, np.nan)
        for th in (0.0, 0.5, 1.0, 1.5, 2.0):
            for d in (1, -1):
                m = (z >= th) if d > 0 else (z <= -th)
                m = np.where(np.isfinite(z), m, False)
                if m.sum() < MINTR + MINHO:
                    continue
                rows.append(m)
                tags.append(f"{name}{'>' if d>0 else '<'}{'' if d>0 else '-'}{th}")
    if not rows:
        return None, None
    return np.asarray(rows, np.float32), tags


def pnl_vectors(B, pip, hold):
    c = B["c"]
    n = len(c)
    fwd = np.full(n, np.nan)
    fwd[:-hold] = (c[hold:] - c[:-hold]) / pip
    cost = B["spread"] / pip           # in + out, half-spread each way
    p = fwd - cost
    ok = np.isfinite(p)
    return np.where(ok, p, 0.0).astype(np.float32), ok.astype(np.float32)


def score_pairs(M, p, ok, cut, tallies, tags):
    """Every pair of conditions, in two matrix multiplies per split."""
    tr = np.zeros(len(p), np.float32); tr[:cut] = 1.0
    ho = 1.0 - tr
    A = M * (tr * ok)                       # masks restricted to train
    Bm = M * (ho * ok)
    Ntr = A @ A.T
    Str = A @ (p[:, None] * A.T)
    Nho = Bm @ Bm.T
    Sho = Bm @ (p[:, None] * Bm.T)
    good = (Ntr >= MINTR) & (Nho >= MINHO)
    iu = np.triu_indices(len(M), 1)
    g = good[iu]
    if not g.any():
        return 0
    a = (Str[iu][g] / Ntr[iu][g])
    b = (Sho[iu][g] / Nho[iu][g])
    ii, jj = iu[0][g], iu[1][g]
    for t in tallies:
        t.add(a, b, tags=lambda k: f"LONG {tags[ii[k]]} AND {tags[jj[k]]}")
        # SHORTING the same condition is a different configuration and half the
        # search space. It needs no second matmul: selling what you would have
        # bought earns exactly minus what buying earned, on both splits. Without
        # this the grid can express "buy after a fall" but never "sell after a
        # rise", and calls that a complete search.
        t.add(-a, -b, tags=lambda k: f"SHORT {tags[ii[k]]} AND {tags[jj[k]]}")
    return 2 * int(g.sum())


def score_triples(M, p, ok, cut, tallies, tags):
    """Pairs crossed with singles, in chunks so the pair matrix never lands."""
    nm = len(M)
    tr = np.zeros(len(p), np.float32); tr[:cut] = 1.0
    ho = 1.0 - tr
    A = M * (tr * ok)
    Bm = M * (ho * ok)
    iu = np.triu_indices(nm, 1)
    total = 0
    for s in range(0, len(iu[0]), TRICHUNK):
        i2, j2 = iu[0][s:s + TRICHUNK], iu[1][s:s + TRICHUNK]
        PA = A[i2] * A[j2]
        PB = Bm[i2] * Bm[j2]
        keep = (PA.sum(1) >= MINTR) & (PB.sum(1) >= MINHO)
        if not keep.any():
            continue
        PA, PB, i2, j2 = PA[keep], PB[keep], i2[keep], j2[keep]
        Ntr = PA @ A.T
        Str = PA @ (p[:, None] * A.T)
        Nho = PB @ Bm.T
        Sho = PB @ (p[:, None] * Bm.T)
        # A AND B AND C is the same rule however it is ordered. Crossing pairs
        # (i<j) against every single k counted each triple three times -- once
        # for each element that happened to be the "single" -- which is how
        # "2.04 billion configurations" was really about 680 million distinct
        # ones wearing three hats. Require k > j and each triple is counted once.
        good = (Ntr >= MINTR) & (Nho >= MINHO)
        good &= np.arange(nm)[None, :] > j2[:, None]
        if not good.any():
            continue
        r, cidx = np.where(good)
        a = Str[r, cidx] / Ntr[r, cidx]
        b = Sho[r, cidx] / Nho[r, cidx]
        for t in tallies:
            t.add(a, b, tags=lambda k: (f"LONG {tags[i2[r[k]]]} AND "
                                        f"{tags[j2[r[k]]]} AND {tags[cidx[k]]}"))
            t.add(-a, -b, tags=lambda k: (f"SHORT {tags[i2[r[k]]]} AND "
                                          f"{tags[j2[r[k]]]} AND {tags[cidx[k]]}"))
        total += 2 * int(good.sum())
    return total


def load(sym):
    """Column-at-a-time, preallocated. The concat version was killing the box.

    `pd.concat([read_parquet(f) for f in twelve_files])` holds all twelve
    frames AND the joined copy at once. XAUUSD is 44.7 million rows across
    five columns, so that peak is several gigabytes for a symbol whose useful
    content is two float arrays. Three container restarts, all during this
    call. Preallocating and filling per file halves the peak and never holds
    two copies of the same bytes.
    """
    import pyarrow.parquet as pq
    fs = sorted(glob.glob(os.path.join(FX, f"{sym}_*.parquet")))
    if not fs:
        return None
    rows = [pq.ParquetFile(f).metadata.num_rows for f in fs]
    n = sum(rows)
    bid = np.empty(n, np.float64)
    ask = np.empty(n, np.float64)
    ts = np.empty(n, "datetime64[ns]")
    at = 0
    for f, r in zip(fs, rows):
        t = pq.read_table(f, columns=["time", "bid", "ask"])
        bid[at:at + r] = t.column("bid").to_numpy(zero_copy_only=False)
        ask[at:at + r] = t.column("ask").to_numpy(zero_copy_only=False)
        ts[at:at + r] = t.column("time").to_numpy(zero_copy_only=False)
        at += r
        del t
    # files are month-ordered so the concatenation is already chronological;
    # verify rather than assume, and only pay for a sort if it is wrong
    if not np.all(np.diff(ts.view(np.int64)) >= 0):
        o = np.argsort(ts, kind="stable")
        bid, ask, ts = bid[o], ask[o], ts[o]
    return bid, ask, ts


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    syms = [s.upper() for s in args] or [
        x[1] for x in sorted(
            (sum(os.path.getsize(f) for f in
                 glob.glob(os.path.join(FX, f"{s_}_*.parquet"))), s_)
            for s_ in {os.path.basename(f).split("_")[0]
                       for f in glob.glob(os.path.join(FX, "*.parquet"))})]
    # smallest first: a crash then costs the cheapest remaining symbol, not
    # everything after the most expensive one
    log("# FX search, at scale")
    log()
    log("Every family, crossed with every other family, on data where a buy "
        "pays the ask and a sell pays the bid. Selection on train, always "
        "reported on holdout.")
    log()
    T = Tally()
    percell = {}
    t0 = time.time()
    seen_cells = set()
    if RESUME and os.path.exists(CKPT):
        z = np.load(CKPT, allow_pickle=True)
        T.n, T.pos, T.sho = z["n"], z["pos"], z["sho"]
        T.total = int(z["total"])
        T.top = [tuple(x) for x in z["top"].tolist()]
        seen_cells = set(z["cells"].tolist())
        log(f"Resumed from checkpoint: {T.total:,} configurations already "
            f"scored across {len(seen_cells)} cells.")
        log()


    def save_ckpt():
        np.savez(CKPT, n=T.n, pos=T.pos, sho=T.sho, total=T.total,
                 top=np.array(T.top, dtype=object),
                 cells=np.array(sorted(seen_cells), dtype=object))
    for sym in syms:
        r = load(sym)
        if r is None:
            continue
        bid, ask, ts = r
        del r
        pip = PIP.get(sym, 1e-4)
        for kind in BARS:
            B = make_bars(bid, ask, ts, kind)
            if B is None:
                continue
            if B["n"] > MAXBARS:
                log(f"- {sym} `{kind}`: {B['n']:,} bars exceeds the "
                    f"{MAXBARS:,} cap, SKIPPED (not silently truncated)")
                continue
            if f"{sym}|{kind}" in seen_cells:
                log(f"- {sym} `{kind}`: already in the checkpoint, skipped")
                continue
            M, tags = base_masks(B, pip)
            if M is None:
                continue
            cut = int(B["n"] * 0.7)
            cell = Tally()
            cnt = 0
            for hold in HOLDS:
                p, ok = pnl_vectors(B, pip, hold)
                cnt += score_pairs(M, p, ok, cut, (T, cell), tags)
                if TRIPLES:
                    cnt += score_triples(M, p, ok, cut, (T, cell), tags)
            percell[(sym, kind)] = cell
            seen_cells.add(f"{sym}|{kind}")
            save_ckpt()
            log(f"- {sym} `{kind}`: {B['n']:,} bars, {len(M)} conditions, "
                f"**{cnt:,}** configurations [{time.time()-t0:.0f}s, "
                f"running total {T.total:,}]")
            del B, M
        del bid, ask, ts
        gc.collect()
    log()
    log(f"## {T.total:,} configurations scored in {time.time()-t0:.0f} seconds")
    log()

    log("## Select on train, look at holdout")
    log()
    log("| training cut | score cut | configs kept | share positive out of "
        "sample | mean holdout |")
    log("|---|---|---|---|---|")
    for frac, cutv, n, pct, mean in T.curve():
        log(f"| top {frac*100:g}% | >= {cutv:+.2f} pips | {n:,} | "
            f"**{pct:.1f}%** | {mean:+.4f} pips |")
    log()
    log("A coin gives 50%. Anything below that means selecting the best "
        "training configurations selected WORSE than picking at random.")
    log()

    log("## The best configurations by training score, and what they did next")
    log()
    log("| train pips | HOLDOUT pips | rule |")
    log("|---|---|---|")
    for tr_, tag, ho_ in sorted(T.top, reverse=True)[:TOPK]:
        log(f"| {tr_:+.3f} | {ho_:+.3f} | `{tag}` |")
    log()

    log("## Per cell, so one symbol cannot carry the answer")
    log()
    log("| symbol / bars | configs | share positive in top 0.01% |")
    log("|---|---|---|")
    for (sym, kind), cell in percell.items():
        rows = [r for r in cell.curve() if r[0] == 1e-4]
        if rows:
            log(f"| {sym} `{kind}` | {cell.total:,} | {rows[0][3]:.1f}% |")
    open(OUT, "w").write("\n".join(LINES) + "\n")
    print("\nwrote", OUT)

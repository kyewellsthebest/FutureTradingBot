"""Five billion DISTINCT configurations in tick-event space, drift-free.

You asked for 5B+ non-duplicate configurations and 5B different ideas. This
delivers them, with every defect the cross-market audit found fixed FIRST --
because five billion configs through a broken null is five billion ways to be
wrong.

WHAT IS DIFFERENT FROM EVERY PREVIOUS ENGINE, and why each one mattered:

  DE-DRIFTED OUTCOMES. The audit's biggest find: YM's 13/13 and RTY's 21/21
  "passing" cells all decoded to one absolute direction -- the search had
  found the contract's rally, not a behaviour. A direction-signed cell
  inherits the market's drift, and a population baseline cancels drift ACROSS
  directions but never WITHIN a direction-specific cell. Fix: subtract the
  mean forward move from every outcome, computed per split, so the holdout is
  de-drifted by its OWN mean. A configuration can now only score by timing.

  A NULL THAT PRESERVES AUTOCORRELATION. The old control was one iid
  permutation, which destroys the +0.47..+0.64 serial correlation of the
  outcome series -- so the printed floor was biased low exactly where cells
  passed. Fix: CIRCULAR SHIFT of the outcome vector. The shifted series is
  exactly as autocorrelated as the real one and merely unaligned with the
  signal. The null runs the identical search, same size, same everything.
  There is no t-statistic anywhere in this engine: the shifted-null
  distribution IS the significance test, and unlike a t it needs no
  independence assumption, so the h-fold overlap of the outcome windows can
  no longer flatter anything.

  TESTED COUNTS PRINTED. "N passed, floor 0" is meaningless unless you know N
  was drawn from 400 or 400,000 tests. Evaluated and scored are both reported.

  TICK-EVENT BARS ONLY. Every bar closes after exactly K price prints. The
  clock never enters the representation -- it survives only as a FEATURE
  (how long those K prints took), which is tick velocity, not a time bar.

  DISTINCT COUNTING. Triples require k > j > i, so each unordered rule is
  counted once. An earlier engine's "2.04 billion" was ~680M distinct.

  DOLLARS, NOT TICKS. Every number below is net dollars per trade on one
  micro contract, after that market's own commission and slippage. Ticks are
  not comparable across markets; dollars are, and dollars are the goal.

Scoring is the matmul identity that makes billions tractable:
    pair sums = M @ (p[:,None] * M.T),  pair counts = M @ M.T
with triples formed by crossing deduplicated pair-masks against singles.

Usage: python megatick.py
Env: MARKETS, HOLDS, TARGET, BAND_LO/BAND_HI, TRICHUNK, NOTRIPLES=1
"""
import gc
import glob
import heapq
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
OUT = os.environ.get("OUT_MD", os.path.join(ROOT, "research", "MEGATICK.md"))
CKPT = os.path.join(ROOT, "research", ".megatick_ckpt.json")
HOLDS = [int(x) for x in os.environ.get("HOLDS", "1,3,8,21").split(",")]
MINTR = int(os.environ.get("MINTR", "120"))
MINHO = int(os.environ.get("MINHO", "50"))
TRIPLES = os.environ.get("NOTRIPLES", "0") != "1"
TRICHUNK = int(os.environ.get("TRICHUNK", "1500"))
TOPK = int(os.environ.get("TOPK", "40"))
TARGET = float(os.environ.get("TARGET", "5e9"))
SURVKEEP = int(os.environ.get("SURVKEEP", "150"))     # recorded per cell
SURVJL = os.path.join(ROOT, "research", "megatick_survivors.jsonl")
BAND = (int(os.environ.get("BAND_LO", "3500")),
        int(os.environ.get("BAND_HI", "7000")))
KLADDER = [100, 150, 250, 400, 650, 1000, 1600, 2600, 4000, 6500, 10000,
           16000, 26000, 40000]
THRESH = (0.0, 0.67, 1.35)
WINS = (5, 13, 34, 89)

# Cost model, in dollars per ROUND TURN on one micro contract.
#   commission: Tradovate measured from your own fills, $0.74/RT
#   slippage:   measured all-in was $2.00/RT on MNQ, i.e. $1.26 over
#               commission = 2.5 MNQ ticks. The same 2.5-tick rule is applied
#               to every futures market, which is conservative for the wide-
#               tick ones (YM, MES) and about right for NQ.
# FX is quoted, so its spread is measured from the data itself, per bar.
COMM = 0.74
SLIP_TICKS = 2.5

MARKETS = {
    "NQ":  dict(dir="data/tick/raw",   glob="NQ*.parquet",  usd_tick=0.50, tick=0.25),
    "ES":  dict(dir="data/tick/multi", glob="ES*.parquet",  usd_tick=1.25, tick=0.25),
    "GC":  dict(dir="data/tick/multi", glob="GC*.parquet",  usd_tick=1.00, tick=0.10),
    "CL":  dict(dir="data/tick/multi", glob="CL*.parquet",  usd_tick=1.00, tick=0.01),
    "RTY": dict(dir="data/tick/multi", glob="RTY*.parquet", usd_tick=0.50, tick=0.10),
    "YM":  dict(dir="data/tick/multi", glob="YM*.parquet",  usd_tick=0.50, tick=1.0),
    "HG":  dict(dir="data/tick/multi", glob="HG*.parquet",  usd_tick=1.25, tick=0.0005),
}
# FX: research-only markets (no micro future for these on the account). Sized
# at $1 per pip = 10k notional, spread measured from the tape, no commission.
for _s in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"):
    MARKETS[_s] = dict(dir="data/fx", glob=f"{_s}_*.parquet", tick=1e-5,
                       usd_tick=0.10, fx=True, comm=0.0)
MARKETS["USDJPY"] = dict(dir="data/fx", glob="USDJPY_*.parquet", tick=1e-3,
                         usd_tick=0.10, fx=True, comm=0.0)
MARKETS["XAUUSD"] = dict(dir="data/fx", glob="XAUUSD_*.parquet", tick=1e-3,
                         usd_tick=0.01, fx=True, comm=0.0)   # 10 oz

WANT = [m for m in os.environ.get("MARKETS", ",".join(MARKETS)).split(",")
        if m in MARKETS]

NBIN = 4001
EDGES_T = np.linspace(-6.0, 6.0, NBIN)      # signed-log dollars axis
NB = NBIN - 1
LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


def _t(x):
    return np.sign(x) * np.log1p(np.abs(x))


def _t_inv(u):
    return np.sign(u) * np.expm1(np.abs(u))


class Tally:
    """Constant-memory distribution of (train score -> holdout score).

    Signed-log bins so the extreme tail keeps resolution: the first engine
    capped its axis and dumped 144M configs into one bin labelled the top
    0.00001%. This axis resolves to a tenth of a cent near zero and still
    reaches +-$400.
    """

    def __init__(self):
        self.n = np.zeros(NB, np.int64)
        self.pos = np.zeros(NB, np.int64)
        self.sho = np.zeros(NB, np.float64)
        self.total = 0            # scored (passed the sample-size gate)
        self.evaluated = 0        # enumerated, distinct
        self.top = []
        self.mk = {}              # market -> [scored, sum_train, sum_hold]
        self.surv = 0             # profitable after costs on BOTH halves
        self.best = []            # heap of survivors, keyed on min(train, hold)

    def add(self, tr, ho, mk, tags=None, ctx=""):
        # SURVIVORS: profitable after real costs on BOTH halves. This, not the
        # training top-40, is the screen worth reading -- ledger #19 measured
        # selection-by-training-score to be actively harmful. The null runs
        # the identical test, so the count below has something to be compared
        # against instead of being compared against zero.
        sv = (tr > 0) & (ho > 0)
        ns = int(sv.sum())
        self.surv += ns
        if ns and tags is not None:
            idx = np.flatnonzero(sv)
            key = np.minimum(tr[idx], ho[idx])
            m = min(SURVKEEP, len(idx))
            for i in np.argpartition(-key, m - 1)[:m]:
                j = int(idx[i])
                item = (float(key[i]), float(tr[j]), float(ho[j]),
                        tags(j), mk, ctx)
                if len(self.best) < 500:
                    heapq.heappush(self.best, item)
                elif item[0] > self.best[0][0]:
                    heapq.heapreplace(self.best, item)
        b = np.clip(np.digitize(_t(tr), EDGES_T) - 1, 0, NB - 1)
        self.n += np.bincount(b, minlength=NB)
        self.pos += np.bincount(b, weights=(ho > 0).astype(np.float64),
                                minlength=NB).astype(np.int64)
        self.sho += np.bincount(b, weights=ho, minlength=NB)
        self.total += len(tr)
        r = self.mk.setdefault(mk, [0, 0.0, 0.0])
        r[0] += len(tr); r[1] += float(tr.sum()); r[2] += float(ho.sum())
        if tags is not None and len(tr):
            k = min(TOPK, len(tr))
            for i in np.argpartition(-tr, k - 1)[:k]:
                item = (float(tr[i]), tags(int(i)), float(ho[i]))
                if len(self.top) < TOPK:
                    heapq.heappush(self.top, item)
                elif item[0] > self.top[0][0]:
                    heapq.heapreplace(self.top, item)

    def curve(self):
        rows = []
        cn = np.cumsum(self.n[::-1])[::-1]
        cp = np.cumsum(self.pos[::-1])[::-1]
        cs = np.cumsum(self.sho[::-1])[::-1]
        for frac in (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 1.0):
            want = max(1, int(self.total * frac))
            nz = np.nonzero(cn)[0]
            if not len(nz):
                continue
            j = int(np.argmax(cn <= want)) if (cn <= want).any() else int(nz[-1])
            if cn[j] == 0 or (rows and rows[-1][2] == int(cn[j])):
                continue
            rows.append((frac, _t_inv(EDGES_T[j]), int(cn[j]),
                         cp[j] / cn[j] * 100, cs[j] / cn[j]))
        return rows

    def state(self):
        return dict(n=self.n.tolist(), pos=self.pos.tolist(),
                    sho=self.sho.tolist(), total=self.total,
                    evaluated=self.evaluated, top=self.top, mk=self.mk)

    def load(self, d):
        self.n = np.array(d["n"], np.int64)
        self.pos = np.array(d["pos"], np.int64)
        self.sho = np.array(d["sho"], np.float64)
        self.total = d["total"]; self.evaluated = d["evaluated"]
        self.top = [tuple(x) for x in d["top"]]; self.mk = d["mk"]
        self.surv = d.get("surv", 0)
        self.best = [tuple(x) for x in d.get("best", [])]


# ---------------------------------------------------------------- data -----

def load_one(f, cfg):
    """One file -> (price in ticks, size, spread in ticks, ts). SORTED, asserted.

    The ledger rule that cost us cell #21: raw parquets are 86-88% out of time
    order, with rows jumping back up to 73 hours. Sorting is not optional and
    the assertion is not decoration.
    """
    if cfg.get("fx"):
        t = pq.read_table(f, columns=["time", "bid", "ask",
                                      "bid_volume", "ask_volume"])
        ts = t.column("time").to_numpy(zero_copy_only=False)
        ts = ts.astype("datetime64[ns]").astype(np.int64)
        bid = t.column("bid").to_numpy(zero_copy_only=False).astype(np.float64)
        ask = t.column("ask").to_numpy(zero_copy_only=False).astype(np.float64)
        sz = (t.column("bid_volume").to_numpy(zero_copy_only=False)
              + t.column("ask_volume").to_numpy(zero_copy_only=False))
        sz = np.asarray(sz, np.float64)
        o = np.argsort(ts, kind="stable")
        px = ((bid[o] + ask[o]) * 0.5) / cfg["tick"]
        sp = (ask[o] - bid[o]) / cfg["tick"]
        sz, ts = sz[o], ts[o]
    else:
        t = pq.read_table(f, columns=["ts", "price", "size"])
        ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
        px = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
        sz = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
        o = np.argsort(ts, kind="stable")
        px, sz, ts = px[o] / cfg["tick"], sz[o], ts[o]
        sp = None                       # futures prints: modelled, see COST
    del t
    assert np.all(np.diff(ts) >= 0), f"{f} not monotone after sort"
    return px, sz, sp, ts


def event_bars(px, sz, sp, ts, k):
    """Bars closing every exactly-k price prints. No clock in the bar rule.

    reshape, not reduceat: reduceat's final segment runs to the end of the
    array, so the last bar would silently span more than k prints.
    """
    m = (len(px) // k) * k
    if m // k < 900:
        return None
    q = px[:m].reshape(-1, k)
    qt = ts[:m].reshape(-1, k)
    B = dict(o=q[:, 0].copy(), c=q[:, -1].copy(), h=q.max(1), l=q.min(1),
             v=sz[:m].reshape(-1, k).sum(1),
             dur=np.log1p(np.maximum(qt[:, -1] - qt[:, 0], 0) / 1e6),
             path=np.abs(np.diff(q, axis=1)).sum(1),
             ups=(np.diff(q, axis=1) > 0).sum(1) / (k - 1.0),
             n=m // k)
    B["sp"] = (sp[:m].reshape(-1, k).mean(1) if sp is not None
               else np.zeros(m // k))
    return B


# ------------------------------------------------------------ features -----

def roll(a, w, fn):
    return getattr(pd.Series(a).rolling(w, min_periods=w), fn)().values


def features(B):
    """The vocabulary. ~80 distinct QUESTIONS, each asked six ways.

    Every family below is one of the behaviours in the brief -- movement,
    path dependency, retracement, exhaustion, breakout and its failure,
    compression and expansion, tick velocity, volume relationships, price
    location, event counts. Nothing here is a clock feature; `dur` is how
    long K prints took, which is the market's own speed.
    """
    c, h, l, o, v = B["c"], B["h"], B["l"], B["o"], B["v"]
    dur, path, ups = B["dur"], B["path"], B["ups"]
    n = len(c)
    dc = np.r_[np.nan, np.diff(c)]
    sgn = np.sign(dc)
    F = {}

    for w in WINS:
        prev = np.r_[np.full(w, np.nan), c[:-w]]
        prev2 = np.r_[np.full(2 * w, np.nan), c[:-2 * w]]
        mu = roll(c, w, "mean")
        sd = np.maximum(roll(c, w, "std"), 1e-9)
        hh, ll = roll(h, w, "max"), roll(l, w, "min")
        rng = np.maximum(hh - ll, 1e-9)
        pw = np.maximum(roll(np.abs(dc), w, "sum"), 1e-9)
        net = c - prev
        F[f"mom{w}"] = net                                   # movement
        F[f"vmom{w}"] = net / sd                             # scaled movement
        F[f"rev{w}"] = -(c - mu) / sd                        # mean reversion
        F[f"pos{w}"] = (c - ll) / rng * 2 - 1                # price location
        F[f"acc{w}"] = (c - 2 * prev + prev2) / sd           # acceleration
        F[f"eff{w}"] = net / pw                              # path efficiency
        F[f"aeff{w}"] = np.abs(net) / pw                     # trendiness
        F[f"chop{w}"] = roll((sgn * np.r_[np.nan, sgn[:-1]] < 0).astype(float),
                             w, "mean")                      # direction flips
        F[f"dnh{w}"] = (c - hh) / sd                         # retrace from high
        F[f"upl{w}"] = (c - ll) / sd                         # bounce off low
        F[f"exp{w}"] = rng / np.maximum(roll(rng, w, "mean"), 1e-9) - 1
        F[f"brk{w}"] = (c - np.r_[np.full(1, np.nan), hh[:-1]]) / sd
        F[f"bdn{w}"] = (np.r_[np.full(1, np.nan), ll[:-1]] - c) / sd
        F[f"fail{w}"] = ((h - np.r_[np.nan, hh[:-1]]) > 0).astype(float) * \
            ((c - np.r_[np.nan, hh[:-1]]) < 0).astype(float)  # failed breakout
        F[f"faild{w}"] = ((np.r_[np.nan, ll[:-1]] - l) > 0).astype(float) * \
            ((np.r_[np.nan, ll[:-1]] - c) < 0).astype(float)
        F[f"vel{w}"] = -(dur - roll(dur, w, "mean")) / \
            np.maximum(roll(dur, w, "std"), 1e-9)             # tick velocity
        F[f"volz{w}"] = (v - roll(v, w, "mean")) / \
            np.maximum(roll(v, w, "std"), 1e-9)               # volume
        F[f"vpp{w}"] = roll(v, w, "mean") / \
            np.maximum(roll(np.abs(dc), w, "mean"), 1e-9)     # vol per tick moved
        F[f"absb{w}"] = F[f"volz{w}"] - F[f"exp{w}"]          # absorption
        F[f"vdir{w}"] = roll(sgn * v, w, "sum") / \
            np.maximum(roll(v, w, "sum"), 1e-9)               # signed volume
        F[f"run{w}"] = roll((sgn > 0).astype(float), w, "mean") * 2 - 1
        F[f"upsz{w}"] = (ups - roll(ups, w, "mean")) / \
            np.maximum(roll(ups, w, "std"), 1e-9)             # event counts
        F[f"pthz{w}"] = (path - roll(path, w, "mean")) / \
            np.maximum(roll(path, w, "std"), 1e-9)            # path length

    F["shape"] = (c - l) / np.maximum(h - l, 1e-9) * 2 - 1     # close in bar
    F["uwick"] = (h - np.maximum(o, c)) / np.maximum(h - l, 1e-9)
    F["lwick"] = (np.minimum(o, c) - l) / np.maximum(h - l, 1e-9)
    F["body"] = (c - o) / np.maximum(h - l, 1e-9)
    F["gap"] = np.r_[np.nan, o[1:] - c[:-1]]
    F["dc1"] = dc
    F["barvel"] = -dur
    F["barvol"] = v
    F["barpath"] = path
    F["barups"] = ups * 2 - 1
    F["ineff"] = (h - l) / np.maximum(path, 1e-9)              # range vs travel
    F["sprd"] = -B["sp"]
    F["cmp"] = roll(h - l, 5, "mean") / np.maximum(roll(h - l, 89, "mean"),
                                                   1e-9) - 1   # compression
    F["vratio"] = roll(v, 5, "mean") / np.maximum(roll(v, 89, "mean"), 1e-9) - 1
    F["dratio"] = roll(dur, 5, "mean") - roll(dur, 89, "mean")
    F["vwapd"] = (c - roll(c * v, 233, "sum") /
                  np.maximum(roll(v, 233, "sum"), 1e-9))
    F["volst"] = roll(np.abs(dc), 5, "mean") / \
        np.maximum(roll(np.abs(dc), 89, "mean"), 1e-9) - 1     # vol regime

    return F


def base_masks(B):
    """Threshold every feature at 3 strengths in 2 directions -> mask matrix."""
    F = features(B)
    n = len(B["c"])
    rows, tags = [], []
    for name, f in F.items():
        f = np.asarray(f, np.float64)
        fin = np.isfinite(f)
        if fin.sum() < n * 0.5:
            continue
        sd = np.nanstd(np.where(fin, f, np.nan))
        if not np.isfinite(sd) or sd <= 0:
            continue
        z = np.where(fin, (f - np.nanmean(np.where(fin, f, np.nan))) / sd, np.nan)
        for th in THRESH:
            for d in (1, -1):
                m = np.where(np.isfinite(z), (z >= th) if d > 0 else (z <= -th),
                             False)
                s = int(m.sum())
                if s < MINTR + MINHO or s > n - 20:
                    continue
                rows.append(m)
                tags.append(f"{name}{'>' if d > 0 else '<-'}{th}")
    if not rows:
        return None, None
    return np.asarray(rows, np.float32), tags


# ------------------------------------------------------------- scoring -----

def outcome(B, hold, cut, cost_usd, usd_tick, fx):
    """De-drifted forward move, in NET DOLLARS. The drift-decode fix.

    Each split's own mean forward move is removed, so a configuration cannot
    score by being long in a rising tape -- only by timing relative to it.
    Then the market's real cost is charged once per round turn.
    """
    c = B["c"]
    n = len(c)
    f = np.full(n, np.nan)
    f[:-hold] = c[hold:] - c[:-hold]
    ok = np.isfinite(f)
    tr = np.zeros(n, bool); tr[:cut] = True
    d = f.copy()
    a, b = ok & tr, ok & ~tr
    if a.any():
        d[tr] = f[tr] - f[a].mean()
    if b.any():
        d[~tr] = f[~tr] - f[b].mean()
    usd = d * usd_tick
    if fx:
        usd -= B["sp"] * usd_tick * 2.0        # measured spread, both sides
    else:
        usd -= cost_usd
    return np.where(ok, usd, 0.0).astype(np.float32), ok.astype(np.float32)


def score(M, p, ok, cut, tally, tags, mk, ctx="", shift=0,
          want_tags=True):
    """Every pair and every triple in a handful of matmuls."""
    n = len(p)
    if shift:
        p = np.roll(p, shift)                  # autocorrelation-preserving null
    trm = np.zeros(n, np.float32); trm[:cut] = 1.0
    A = M * (trm * ok)
    Bm = M * ((1.0 - trm) * ok)
    nm = len(M)
    ev = 0

    Ntr, Str = A @ A.T, A @ (p[:, None] * A.T)
    Nho, Sho = Bm @ Bm.T, Bm @ (p[:, None] * Bm.T)
    iu = np.triu_indices(nm, 1)
    ev += 2 * len(iu[0])
    g = ((Ntr >= MINTR) & (Nho >= MINHO))[iu]
    if g.any():
        a = Str[iu][g] / Ntr[iu][g]
        b = Sho[iu][g] / Nho[iu][g]
        ii, jj = iu[0][g], iu[1][g]
        tf = (lambda k: f"L {tags[ii[k]]} & {tags[jj[k]]}") if want_tags else None
        ts_ = (lambda k: f"S {tags[ii[k]]} & {tags[jj[k]]}") if want_tags else None
        tally.add(a, b, mk, tags=tf, ctx=ctx)
        tally.add(-a, -b, mk, tags=ts_, ctx=ctx)
    del Ntr, Str, Nho, Sho

    if TRIPLES:
        pA = p[:, None] * A.T
        pB = p[:, None] * Bm.T
        col = np.arange(nm)
        for s0 in range(0, len(iu[0]), TRICHUNK):
            i2, j2 = iu[0][s0:s0 + TRICHUNK], iu[1][s0:s0 + TRICHUNK]
            ev += 2 * int((nm - 1 - j2).clip(0).sum())     # k>j>i, no duplicates
            PA = A[i2] * A[j2]
            keep = PA.sum(1) >= MINTR
            if not keep.any():
                del PA
                continue
            i2, j2 = i2[keep], j2[keep]
            PA = PA[keep]
            PB = Bm[i2] * Bm[j2]
            Nt, St = PA @ A.T, PA @ pA
            Nh, Sh = PB @ Bm.T, PB @ pB
            gd = (Nt >= MINTR) & (Nh >= MINHO) & (col[None, :] > j2[:, None])
            if gd.any():
                r, ci = np.where(gd)
                a = St[r, ci] / Nt[r, ci]
                b = Sh[r, ci] / Nh[r, ci]
                if want_tags:
                    tally.add(a, b, mk, ctx=ctx, tags=lambda k: (
                        f"L {tags[i2[r[k]]]} & {tags[j2[r[k]]]} & {tags[ci[k]]}"))
                    tally.add(-a, -b, mk, ctx=ctx, tags=lambda k: (
                        f"S {tags[i2[r[k]]]} & {tags[j2[r[k]]]} & {tags[ci[k]]}"))
                else:
                    tally.add(a, b, mk, ctx=ctx)
                    tally.add(-a, -b, mk, ctx=ctx)
            del PA, PB, Nt, St, Nh, Sh, gd
        del pA, pB
    tally.evaluated += ev
    return ev


# ---------------------------------------------------------------- driver ---

def cells():
    """Every (file, K) with a bar count inside the compute band, round-robin
    across markets so breadth arrives before depth."""
    per = {}
    for mk in WANT:
        cfg = MARKETS[mk]
        out = []
        for f in sorted(glob.glob(os.path.join(ROOT, cfg["dir"], cfg["glob"]))):
            nrow = pq.ParquetFile(f).metadata.num_rows
            for k in KLADDER:
                if BAND[0] <= nrow // k <= BAND[1]:
                    out.append((mk, f, k))
        if out:
            per[mk] = out
        else:
            per[mk] = []
    order = []
    i = 0
    while any(len(v) > i for v in per.values()):
        for mk in WANT:
            if len(per[mk]) > i:
                order.append(per[mk][i])
        i += 1
    return order, {m: len(v) for m, v in per.items()}


def report(T, N, dt, nm_seen, head):
    """Written after every cell, so the file on disk is always current and the
    run can be read (or stopped) at any moment without losing the answer."""
    L = list(head)

    def w(s=""):
        L.append(s)

    w()
    w(f"## {T.evaluated:,} distinct configurations evaluated; "
      f"**{T.total:,} scored** (met the sample-size gate) in {dt / 3600:.2f} h")
    w()
    w(f"Null: {N.evaluated:,} evaluated, {N.total:,} scored — the identical "
      f"search on circularly-shifted outcomes, so the columns below are "
      f"directly comparable.")
    w()
    w("### What the whole population did, and what the null did")
    w()
    w("| selection | train cut | kept | % that made money OOS | "
      "avg OOS $/trade | NULL % | NULL avg $ |")
    w("|---|---|---|---|---|---|---|")
    nc = {r[0]: r for r in N.curve()}
    for frac, cut_, n_, pct, mean in T.curve():
        nr = nc.get(frac)
        tail = (f"{nr[3]:.1f}% | ${nr[4]:+.4f} |" if nr else "- | - |")
        w(f"| top {frac * 100:g}% | >= ${cut_:+.3f} | {n_:,} | "
          f"**{pct:.1f}%** | **${mean:+.4f}** | {tail}")
    w()
    w("Read the last two columns first. If the real search cannot beat the "
      "shifted one, the pattern is the calendar and not the market.")
    w()
    w("### Per market")
    w()
    w("| market | scored configs | avg train $ | avg holdout $ | "
      "NULL holdout $ |")
    w("|---|---|---|---|---|")
    for m in sorted(T.mk, key=lambda x: -T.mk[x][0]):
        a = T.mk[m]; b = N.mk.get(m, [1, 0.0, 0.0])
        w(f"| {m} | {a[0]:,} | ${a[1] / max(a[0], 1):+.4f} | "
          f"${a[2] / max(a[0], 1):+.4f} | ${b[2] / max(b[0], 1):+.4f} |")
    w()
    w("### The screen that actually matters: profitable on BOTH halves")
    w()
    rate = T.surv / max(T.total, 1) * 100
    nrate = N.surv / max(N.total, 1) * 100
    lift = (T.surv / max(T.total, 1)) / max(N.surv / max(N.total, 1), 1e-12)
    w(f"| | configs scored | made money on both halves | rate |")
    w("|---|---|---|---|")
    w(f"| **real search** | {T.total:,} | **{T.surv:,}** | {rate:.3f}% |")
    w(f"| shifted null | {N.total:,} | {N.surv:,} | {nrate:.3f}% |")
    w()
    w(f"Lift over chance: **{lift:.2f}x**. A lift near 1.0 means the survivors "
      f"are what shuffling produces anyway — that is the honest reading of a "
      f"long list of profitable-looking rules, and it is why the count alone "
      f"is never the answer.")
    w()
    w("Survivors ranked by their WORSE half, so nothing qualifies on one "
      "good split:")
    w()
    w("| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |")
    w("|---|---|---|---|---|")
    for key, tr_, ho_, tag, mkt, ctx in sorted(T.best, reverse=True)[:60]:
        w(f"| **${key:+.3f}** | ${tr_:+.3f} | ${ho_:+.3f} | {ctx} | `{tag}` |")
    w()
    w("### The best training scores, and what each did out of sample")
    w()
    w("| train $/trade | HOLDOUT $/trade | rule |")
    w("|---|---|---|")
    for tr_, tag, ho_ in sorted(T.top, reverse=True)[:TOPK]:
        w(f"| ${tr_:+.3f} | ${ho_:+.3f} | `{tag}` |")
    w()
    if nm_seen:
        w(f"Conditions per cell: {min(nm_seen)}-{max(nm_seen)} "
          f"(median {int(np.median(nm_seen))}).")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    open(tmp, "w").write("\n".join(L) + "\n")
    os.replace(tmp, OUT)


def main():
    T, N = Tally(), Tally()
    done = set()
    if os.path.exists(CKPT) and os.environ.get("RESUME", "1") == "1":
        d = json.load(open(CKPT))
        T.load(d["T"]); N.load(d["N"]); done = set(d["done"])
        log(f"Resumed: {T.evaluated:,} evaluated, {len(done)} cells done.")

    def save():
        tmp = CKPT + ".tmp"
        json.dump(dict(T=T.state(), N=N.state(), done=sorted(done)),
                  open(tmp, "w"))
        os.replace(tmp, CKPT)

    order, counts = cells()
    log("# MEGATICK — five billion distinct configurations in tick-event space")
    log()
    log("Bars close every K price prints; the clock is never a bar rule. "
        "Outcomes are de-drifted per split, charged real costs, and measured "
        "in **net dollars per trade on one micro contract**. The floor is the "
        "identical search run on a circularly-shifted outcome series — same "
        "autocorrelation, same sample sizes, no alignment with the signal.")
    log()
    log(f"Vocabulary: {len(WINS)} event-horizons x ~24 behavioural families "
        f"+ 18 bar-local questions, each asked at {len(THRESH)} strengths in "
        f"2 directions. Holds: {HOLDS} bars. "
        f"{len(order)} (contract x bar-size) cells available, visited "
        f"round-robin across markets so breadth arrives before depth.")
    log()
    log("Sizing: one micro futures contract per market. FX at $1 per pip "
        "(10k notional), gold at 10 oz — FX and gold are research-only, since "
        "the account cannot trade them; they exist here to test whether a "
        "behaviour transfers across markets.")
    log()
    miss = [m for m in WANT if not counts.get(m)]
    if miss:
        log(f"No usable tick cells: {', '.join(miss)}")
        log()
    t0 = time.time()
    nm_seen = []
    for mk, f, k in order:
        cid = f"{mk}|{os.path.basename(f)}|{k}"
        if cid in done:
            continue
        if T.total >= TARGET:
            break
        cfg = MARKETS[mk]
        try:
            px, sz, sp, ts = load_one(f, cfg)
        except Exception as e:                      # noqa: BLE001
            log(f"- {cid}: LOAD FAILED {type(e).__name__}: {e}")
            done.add(cid); save(); continue
        B = event_bars(px, sz, sp, ts, k)
        del px, sz, sp, ts
        gc.collect()
        if B is None:
            done.add(cid); save(); continue
        M, tags = base_masks(B)
        if M is None:
            done.add(cid); save(); continue
        nm_seen.append(len(M))
        cut = int(B["n"] * 0.7)
        cost = COMM + SLIP_TICKS * cfg["usd_tick"]
        before = T.evaluated
        for hold in HOLDS:
            p, ok = outcome(B, hold, cut, cost, cfg["usd_tick"],
                            bool(cfg.get("fx")))
            ctx = f"{mk} K={k} h={hold} {os.path.basename(f)}"
            score(M, p, ok, cut, T, tags, mk, ctx=ctx)
            score(M, p, ok, cut, N, tags, mk, ctx=ctx, shift=len(p) // 2,
                  want_tags=False)
        done.add(cid); save()
        log(f"- {mk} K={k} `{os.path.basename(f)}`: {B['n']:,} bars, "
            f"{len(M)} conditions, **{T.evaluated - before:,}** distinct "
            f"[{time.time() - t0:.0f}s, total {T.evaluated:,} eval / "
            f"{T.total:,} scored]")
        del B, M
        gc.collect()
        report(T, N, time.time() - t0, nm_seen, LINES)

    report(T, N, time.time() - t0, nm_seen, LINES)
    print("\nwrote", OUT)


if __name__ == "__main__":
    sys.exit(main())

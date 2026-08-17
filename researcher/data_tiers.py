"""The curriculum: coarse and wide first, fine and deep for survivors.

WHAT IS ACTUALLY ON DISK, and why it is not one dataset.

  tier 1  BREADTH   data/polygon/*_5min.csv      10 markets, ~185k bars
                    each, 2023-12 -> 2026-07. Cheap. Every hypothesis
                    starts here.
  tier 2  DEPTH     data/tick/raw/NQ*.parquet    8 NQ quarters, ~25M
                    trades each, 4.7 GB total. Resampled to 15s or 60s
                    on demand, one contract at a time -- the machine has
                    15 GiB and NO SWAP, and loading two of these at once
                    is how the range sweep was silently OOM-killed.
  tier 3  BOOK      data/depth/NQU6_book_1s.parquet   1.59M seconds of
                    top-of-book with depletion and add counts. NQ only,
                    ~4 weeks. Microstructure hypotheses only.

THE HONEST PART, and the reason this file has a long docstring.

Promotion through the tiers is NOT confirmation. Tier 2 NQ tick data and
tier 1 NQ 5-minute bars are THE SAME TAPE at different resolutions. A
hypothesis that survives both has been measured twice, more precisely
the second time -- it has not been replicated. Treating a tier-2 pass as
independent evidence would be the oldest error in this project: counting
one observation twice because it arrived in two files.

    tiers REFINE a measurement. Only the sealed vault CONFIRMS it.

So promotion does two legitimate things and no others:

  1  it spends expensive compute only where cheap compute already saw
     something, which is the entire point of a curriculum
  2  it measures at the resolution the hypothesis actually lives at. A
     microstructure claim tested on 5-minute bars is not a weak test of
     that claim, it is a test of a different claim.

And the pre-screen threshold is deliberately LOW -- it is a triage rule,
not a decision rule. Setting it high would mean the fine measurement
only ever sees hypotheses that already looked good on coarse data, which
selects for coarse-data noise and then measures it very precisely.

CROSS-MARKET REALITY CHECK. Ten markets is not ten independent tests.
NQ/ES/YM/RTY move together at roughly 0.9 correlation -- "four of four
equity markets agree" is approximately one observation, and this repo has
already retracted a claim built on exactly that mistake. `effective_n`
below reports the honest count.
"""
import gc
import glob
import os

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", os.getcwd())
NS = 1_000_000_000

# markets that move together, and so do not count as separate evidence
BLOCS = {
    "equity": ["NQ", "ES", "YM", "RTY"],
    "rates": ["ZB", "ZN", "ZF", "ZT"],
    "metals": ["GC"],
    "energy": ["CL"],
}


def effective_n(markets):
    """How many INDEPENDENT observations a set of markets really is.

    Members of a correlated bloc count as roughly one, with a small
    credit for the fact that they are not perfectly correlated. Four
    equity indices agreeing is about 1.5 observations, not 4.
    """
    tot = 0.0
    claimed = set()
    for _, members in BLOCS.items():
        k = [m for m in markets if m in members]
        if k:
            tot += 1.0 + 0.25 * (len(k) - 1)
            claimed.update(k)
    # anything not in a known bloc counts as its own observation. The
    # first version silently returned 0 for FX, crypto and NG -- an
    # undercount is the safe direction for a bar but the wrong direction
    # for deciding a market is worthless evidence.
    tot += sum(1 for m in markets if m not in claimed)
    return round(tot, 2)


# ------------------------------------------------------------- tier 1
def tier1(symbols=None, min_bars=5000):
    """Breadth. Every market with 5-minute bars on disk."""
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "*_5min.csv"))):
        sym = os.path.basename(p).split("_")[0]
        if symbols and sym not in symbols:
            continue
        try:
            d = pd.read_csv(p)
            d["ts"] = pd.to_datetime(d["ts"], utc=True)
            d = d.set_index("ts").sort_index()
            d = d[~d.index.duplicated(keep="last")]
            if len(d) < min_bars:
                continue
            d["absret"] = d["close"].diff().abs()
            d["n"] = d.get("volume", pd.Series(1.0, index=d.index))
            d["vol"] = d["n"]
            out[sym] = d[["close", "vol", "n", "absret"]]
        except Exception:                                     # noqa: BLE001
            continue
    return out


# ------------------------------------------------------------- tier 2
BARS = os.path.join(ROOT, "data", "research_bars")


def tier2_contracts():
    return sorted(glob.glob(os.path.join(ROOT, "data", "tick", "raw",
                                         "NQ*.parquet")))


def tier2_sources(bar_s):
    """Where the deep tier comes from at this resolution.

    PRECOMPUTED FIRST. `data/tick/` is 4.7 GB and gitignored, so it does
    not exist on any deploy target -- Railway builds from the repo. The
    committed bars in data/research_bars/ are the same close/vol/n/absret
    the searcher actually reads, resampled once by build_deep_bars.py,
    15 MB for all 24 contract-resolution combinations.

    Returns (name, kind, path). An EMPTY list is a real condition the
    caller must report, not skip quietly: a missing tier looks exactly
    like a healthy search from the outside, and that is the most
    dangerous thing a monitoring surface can show.
    """
    pre = sorted(glob.glob(os.path.join(BARS, f"NQ*_{bar_s}s.parquet")))
    if pre:
        return [(os.path.basename(p).split("_")[0], "pre", p) for p in pre]
    raw = tier2_contracts()
    return [(os.path.basename(p).replace(".parquet", ""), "raw", p)
            for p in raw]


def tier2_from(kind, path, bar_s):
    if kind == "pre":
        d = pd.read_parquet(path).astype("float64")
        return d.sort_index()
    return tier2(path, bar_s=bar_s)


def tier2(path, bar_s=60, rth_only=True):
    """Depth. ONE NQ contract, resampled. Streamed by row group.

    Reading a 25M-row parquet whole and then resampling peaks around
    2 GB per contract; row-group streaming keeps it near 200 MB. On a
    machine with no swap that is the difference between a result and a
    silent kill with no traceback.
    """
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    parts = []
    for i in range(pf.metadata.num_row_groups):
        t = pf.read_row_group(i, columns=["ts", "price", "size"])
        ts = t.column("ts").to_numpy()
        px = t.column("price").to_numpy().astype(np.float64)
        sz = t.column("size").to_numpy().astype(np.float64)
        del t
        b = ts // (bar_s * NS)
        g = pd.DataFrame({"b": b, "px": px, "sz": sz})
        a = g.groupby("b").agg(close=("px", "last"), high=("px", "max"),
                               low=("px", "min"), vol=("sz", "sum"),
                               n=("px", "size"))
        parts.append(a)
        del g, a, ts, px, sz
        if i % 6 == 5:
            gc.collect()
    if not parts:
        return None
    # row groups can straddle a bar boundary, so re-aggregate the seams
    a = pd.concat(parts)
    a = a.groupby(level=0).agg(close=("close", "last"), high=("high", "max"),
                               low=("low", "min"), vol=("vol", "sum"),
                               n=("n", "sum"))
    del parts
    gc.collect()
    a.index = pd.to_datetime(a.index.values * bar_s * NS, utc=True)
    a = a.sort_index()
    if rth_only:
        m = (a.index.hour * 60 + a.index.minute >= 13 * 60 + 30) & \
            (a.index.hour < 20)
        a = a[m]
    a["absret"] = a["close"].diff().abs()
    return a[["close", "vol", "n", "absret"]]


# ------------------------------------------------------------- tier 3
def tier3(bar_s=1):
    """Book. NQ top-of-book, one second per row, with flow columns.

    These columns do not exist at any other tier -- queue depletion and
    add rates are not recoverable from trades. A hypothesis that needs
    them cannot be screened at tier 1 at all, so book hypotheses enter
    HERE and pay the higher bar of a narrower dataset (one market, four
    weeks) rather than pretending they were screened.
    """
    p = os.path.join(ROOT, "data", "depth", "NQU6_book_1s.parquet")
    if not os.path.exists(p):
        return None
    d = pd.read_parquet(p)
    d.index = pd.to_datetime(d["sec"].values * NS, utc=True)
    d = d.sort_index()
    mid = (d["bid_px"] + d["ask_px"]) / 2.0
    out = pd.DataFrame(index=d.index)
    out["close"] = mid
    out["vol"] = d["tv_buy"] + d["tv_sell"]
    out["n"] = d["n_trade"]
    out["absret"] = mid.diff().abs()
    out["imb"] = (d["bid_sz"] - d["ask_sz"]) / \
        (d["bid_sz"] + d["ask_sz"]).replace(0, np.nan)
    out["spread"] = d["ask_px"] - d["bid_px"]
    out["qrate"] = d["n_evt"]
    out["depl"] = d["bid_depl"] - d["ask_depl"]
    out["adds"] = d["bid_add"] - d["ask_add"]
    out["tflow"] = d["tv_buy"] - d["tv_sell"]
    if bar_s > 1:
        r = out.resample(f"{bar_s}s")
        out = pd.DataFrame({
            "close": r["close"].last(), "vol": r["vol"].sum(),
            "n": r["n"].sum(), "imb": r["imb"].mean(),
            "spread": r["spread"].mean(), "qrate": r["qrate"].sum(),
            "depl": r["depl"].sum(), "adds": r["adds"].sum(),
            "tflow": r["tflow"].sum()}).dropna(subset=["close"])
        out["absret"] = out["close"].diff().abs()
    return out


# ---------------------------------------------------------- curriculum
class Curriculum:
    """Which tier a hypothesis has reached, and what it costs to go on.

    PRE_SCREEN is a triage threshold, NOT a decision threshold. It is set
    low on purpose: raising it would mean expensive fine-resolution
    measurement is only ever spent on things that already looked good on
    coarse data, which is a machine for measuring coarse-data noise very
    precisely.
    """
    PRE_SCREEN = 2.0          # sigma at tier 1 to earn a tier-2 look
    TIER_COST = {1: 1.0, 2: 40.0, 3: 15.0}   # rough relative compute

    def __init__(self):
        self.promoted = {}

    def should_promote(self, fp, z, n):
        if abs(z) < self.PRE_SCREEN or n < 60:
            return False
        if fp in self.promoted:
            return False
        return True

    def mark(self, fp, tier, result):
        self.promoted.setdefault(fp, []).append({"tier": tier,
                                                 "result": result})

    @staticmethod
    def caveat(tier_from, tier_to, market):
        if market == "NQ" and tier_from == 1 and tier_to == 2:
            return ("REFINEMENT, NOT REPLICATION: tier-2 NQ tick and "
                    "tier-1 NQ 5-minute bars are the same tape. This "
                    "measures the same claim more precisely; it does not "
                    "confirm it. Only the vault confirms.")
        return "refinement at finer resolution; not independent evidence"

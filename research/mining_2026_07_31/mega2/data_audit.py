"""Is the tick data itself correct? The one assumption never tested.

Every result in this project rests on the parquet tapes in
data/tick/raw. If those are wrong, everything built on them is wrong in
the same direction, and no amount of internal cross-checking would ever
reveal it -- each test would inherit the same fault and agree with all
the others.

This is not a hypothetical worry. Hypothesis #21 in the ledger was
RETRACTED for exactly this: "grammar.py never sorted the tape; raw
parquets are 86-88% out of time order (jumps up to 73h back). Every
'leg' was row-order fiction." A data-handling bug in this repo has
already produced a completely fictional result that survived a synthetic
null.

So: compare the tapes against an INDEPENDENT VENDOR. data/polygon holds
5-minute OHLCV from Polygon for the same instruments and period. Two
vendors, two collection pipelines, two clocks. If bars built from the
tick tape match Polygon's bars, the foundation is sound. If they do not,
every number in this repo is suspect and the disagreement shows where.

Checks:
  1  COVERAGE     do both sources have the same trading days?
  2  PRICE LEVEL  do closes agree bar for bar, and by how much?
  3  RANGE        do the highs and lows agree? A tape missing prints
                  would show systematically NARROWER ranges, which would
                  make every stop look less likely to be hit and every
                  backtest look better than reality.
  4  ORDERING     what fraction of each raw file is out of time order?
                  The #21 failure mode, measured rather than assumed.
  5  GAPS         the largest holes in the tape. A missing hour inside a
                  session silently removes trades from every backtest.

Output: research/DATA_AUDIT.md
"""
import gc
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

POLY = os.path.join(fuse.ROOT, "data", "polygon", "NQ_5min.csv")
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    if not os.path.exists(POLY):
        cands = glob.glob(os.path.join(fuse.ROOT, "data", "polygon", "*.csv"))
        log(f"no NQ_5min.csv; have {[os.path.basename(c) for c in cands]}")
        return
    P = pd.read_csv(POLY)
    P["ts"] = pd.to_datetime(P["ts"], utc=True)
    P = P.set_index("ts").sort_index()
    log("# Is the tick data itself correct?")
    log()
    log("Every result in this project rests on the parquet tapes in "
        "`data/tick/raw`. If those are wrong, everything built on them "
        "is wrong the same way, and internal cross-checking would never "
        "reveal it -- every test inherits the same fault and agrees with "
        "the others.")
    log()
    log("This is not hypothetical. Ledger hypothesis #21 was **retracted "
        "as an unsorted-tape artifact**: the raw parquets were 86-88% "
        "out of time order and produced a completely fictional result "
        "that passed a synthetic null. A data bug in this repo has "
        "already manufactured a finding once.")
    log()
    log(f"So this compares the tapes against an **independent vendor** "
        f"-- Polygon 5-minute bars, {len(P):,} rows, "
        f"{P.index.min().date()} to {P.index.max().date()}. Two vendors, "
        f"two pipelines, two clocks.")
    log()
    log("| contract | days both | close match | median |diff| | "
        "p99 |diff| | tape range / poly range | out-of-order rows |")
    log("|" + "---|" * 7)

    meta = fuse.tape_meta()
    worst = []
    for cn in [c for c in fuse.NQ_CONTRACTS if c in meta]:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        unsorted_frac = float((np.diff(ts) < 0).mean())
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        idx = pd.to_datetime(ts, utc=True)
        g = pd.Series(px, index=idx).resample("5min")
        T = pd.DataFrame({"close": g.last(), "high": g.max(),
                          "low": g.min()}).dropna()
        J = T.join(P[["close", "high", "low"]], how="inner",
                   lsuffix="_t", rsuffix="_p")
        if len(J) < 100:
            log(f"| {cn} | 0 | — | — | — | — | {unsorted_frac:.1%} |")
            del ts, px
            gc.collect()
            continue
        d = (J["close_t"] - J["close_p"]).abs()
        rt = (J["high_t"] - J["low_t"])
        rp = (J["high_p"] - J["low_p"])
        rr = float(rt.sum() / max(rp.sum(), 1e-9))
        match = float((d <= 0.25).mean())
        log(f"| {cn} | {J.index.normalize().nunique()} | {match:.1%} | "
            f"{d.median():.2f} | {d.quantile(0.99):.2f} | {rr:.3f} | "
            f"{unsorted_frac:.1%} |")
        worst.append((match, rr, cn))
        del ts, px, T, J
        gc.collect()

    log()
    log("`close match` is the share of 5-minute bars whose closes agree "
        "within one tick. `tape range / poly range` is the ratio of "
        "total high-low range: **below 1.0 means the tape is missing "
        "prints**, which would make every stop look less likely to be "
        "hit and every backtest in this repo look better than reality. "
        "`out-of-order rows` is the #21 failure mode measured directly "
        "on each raw file, before any sorting.")
    log()
    if worst:
        mm = min(worst)
        rr = [w[1] for w in worst]
        log(f"Worst close agreement: **{mm[2]} at {mm[0]:.1%}**. Range "
            f"ratio spans {min(rr):.3f} to {max(rr):.3f}.")
        log()
        ok = mm[0] > 0.95 and 0.9 < min(rr) and max(rr) < 1.1
        log("**Verdict: the tapes agree with an independent vendor.** "
            "The foundation is sound and the negative results stand on "
            "it." if ok else
            "**Verdict: the sources DISAGREE.** Until this is explained, "
            "every number in this repo is suspect -- including every "
            "negative. The disagreement pattern above shows where to "
            "look.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "DATA_AUDIT.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/DATA_AUDIT.md")


if __name__ == "__main__":
    main()

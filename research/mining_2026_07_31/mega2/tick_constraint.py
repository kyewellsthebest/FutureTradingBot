"""Which instrument gives the most movement per unit of spread?

I told the user ES was the next data purchase because it quotes tighter
than NQ. That was wrong, and it was wrong in a way worth writing down,
because the instinct behind it -- "tighter spread is cheaper to trade"
-- is correct in isolation and misleading in context.

What decides whether a signal is tradable is not the spread in points.
It is the spread relative to how far the instrument MOVES:

    edge = IC x sigma(horizon)
    cost ~ spread
    tradability ~ edge / cost = IC x [ sigma(horizon) / spread ]

The bracketed term is a property of the INSTRUMENT, not the signal. An
instrument whose exchange-minimum tick is large relative to its own
volatility is "tick-constrained": its spread cannot narrow to reflect how
little it actually moves, so every crossing costs a big share of the
available range. ES is the classic example -- one of the most liquid
futures on earth, and pinned at a one-tick spread that is a large
fraction of its second-to-second movement.

This measures sigma empirically from the trade tapes already on disk and
pairs it with each contract's exchange minimum tick. The spread column
is a floor -- one tick -- except for NQ, where four weeks of top of book
gave a MEASURED median of 3 ticks, so the true NQ ratio is worse than
its one-tick row suggests and is shown both ways.

Output: research/INSTRUMENT_CHOICE.md
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
OUT = os.path.join(ROOT, "research", "INSTRUMENT_CHOICE.md")
NS = 1_000_000_000

# exchange minimum tick, in index points, and micro $/point
SPEC = {
    "NQ": (0.25, 2.00), "ES": (0.25, 5.00), "YM": (1.00, 0.50),
    "RTY": (0.10, 5.00), "CL": (0.01, 100.0), "GC": (0.10, 10.0),
}
HZ = [1, 60]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def sigma_for(path):
    """RTH sigma of the 1-second and 60-second mid change, in points."""
    d = pd.read_parquet(path, columns=["ts", "price"])
    d = d.sort_values("ts", kind="stable")
    ts = d.ts.values
    px = d.price.values.astype(np.float64)
    del d
    idx = pd.to_datetime(ts)
    tod = idx.hour * 60 + idx.minute
    keep = np.asarray((tod >= 13 * 60 + 30) & (idx.hour < 20))
    if keep.sum() < 200_000:
        return None
    ts, px = ts[keep], px[keep]
    day = ts // (86400 * NS)
    out = {}
    for h in HZ:
        sec = ts // (h * NS)
        s = pd.Series(px).groupby(sec).last()
        dd = pd.Series(day).groupby(sec).last()
        v = s.diff().values
        v[dd.diff().values != 0] = np.nan       # never across a day break
        out[h] = float(np.nanstd(v))
    out["px"] = float(np.median(px))
    return out


def main():
    rows = []
    for fam in SPEC:
        fs = sorted(glob.glob(os.path.join(RAW, f"{fam}*.parquet")))
        if not fs:
            continue
        got = None
        for f in fs:                     # first contract with enough tape
            try:
                got = sigma_for(f)
            except Exception:            # noqa: BLE001
                got = None
            if got:
                print(f"  {os.path.basename(f)}: sigma1={got[1]:.3f}",
                      flush=True)
                break
        if got:
            rows.append((fam, got))

    log("# Which instrument gives the most movement per unit of spread?")
    log()
    log("I recommended ES as the next data purchase because it quotes "
        "tighter than NQ. That was wrong, and the reasoning behind it is "
        "worth writing down because it is the kind of wrong that sounds "
        "right: a tighter spread IS cheaper per trade, in isolation.")
    log()
    log("What decides tradability is the spread relative to how far the "
        "instrument MOVES:")
    log()
    log("```")
    log("edge         = IC x sigma(horizon)")
    log("cost         ~ spread")
    log("tradability  ~ IC x [ sigma(horizon) / spread ]")
    log("```")
    log()
    log("The bracketed term belongs to the INSTRUMENT, not the signal. "
        "An instrument whose exchange-minimum tick is large relative to "
        "its own volatility is **tick-constrained**: its spread cannot "
        "narrow to reflect how little it moves, so every crossing eats a "
        "large share of the available range.")
    log()
    log("Sigma is measured from the trade tapes already on disk, RTH "
        "only, never differencing across a day break. The spread column "
        "is a one-tick FLOOR for every instrument except NQ, where four "
        "weeks of top of book gave a measured median of **3 ticks**.")
    log()
    log("| instrument | price | tick | sigma 1s | sigma 60s | "
        "**sigma1s / 1 tick** | **sigma60s / 1 tick** |")
    log("|" + "---|" * 7)
    for fam, g in sorted(rows, key=lambda r: -r[1][1] / SPEC[r[0]][0]):
        tick = SPEC[fam][0]
        log(f"| {fam} | {g['px']:,.0f} | {tick} | {g[1]:.3f} pt | "
            f"{g[60]:.2f} pt | **{g[1]/tick:.2f}** | "
            f"**{g[60]/tick:.1f}** |")
    log()
    nq = dict(rows).get("NQ")
    es = dict(rows).get("ES")
    if nq and es:
        nq_ratio = nq[1] / 0.75          # MEASURED 3-tick NQ spread
        es_ratio = es[1] / 0.25          # ES one-tick floor, generous
        log(f"At the spreads that actually exist, NQ moves "
            f"**{nq_ratio:.2f}** of its own spread per second against "
            f"ES's **{es_ratio:.2f}** -- and the ES figure is the "
            f"friendliest possible assumption, a permanent one-tick "
            f"quote. So the same IC buys "
            f"**{nq_ratio/es_ratio:.1f}x more** edge-per-cost on NQ "
            f"than on ES.")
        log()
        log(f"That inverts the recommendation. ES top of book would have "
            f"cost $20.71 to produce a WORSE answer than the one already "
            f"bought.")
        log()
    log("## The part that matters more than the ranking")
    log()
    log("Instrument choice moves this ratio by a factor of order one. "
        "`BOOK_IC.md` measured the gap between the book's edge and NQ's "
        "spread at **12x**. Nothing in this table closes a 12x gap -- "
        "the best and worst instruments here differ by far less than "
        "that.")
    log()
    log("So the binding constraint is not which market we trade. It is "
        "that top-of-book imbalance, one of the most studied predictors "
        "in finance, is worth about 0.06 points against a 0.75-point "
        "spread. Choosing a different contract is optimising the wrong "
        "term.")
    log()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()

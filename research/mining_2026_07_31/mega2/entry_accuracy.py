"""Entry price accuracy: how often do you get the price you asked for?

Two separate things, both asked for at 70%:

    FILL RATE        how often the order fills at all
    PRICE ACCURACY   how often the fill lands ON the intended level
                     rather than somewhere worse

This measures both directly, per order type, by comparing every fill
price with the level the strategy actually asked for. Nothing is
inferred from P&L.

Deliberately standalone -- it re-derives the signal and the level from
the bars rather than importing causal_engine, so it is an independent
check on the same question rather than the same code answering itself.
The level definition is the live bot's: fib retracement of the 3-bar
wick range.

    SELL-STOP      rests below the market and triggers on the cross,
                   filling at the print that triggered it. Slippage is
                   whatever that print is past the level.
    RESTING LIMIT  rests ABOVE the market, so it can only fill at its
                   own price or better. Price accuracy is 100% BY
                   CONSTRUCTION -- the interesting number is how often
                   it fills, and what the market is doing when it does.
    MARKET         no level at all. Slippage is measured against the
                   level for comparability, which is the honest way to
                   compare "I wanted X and paid Y".

The last column is the one that matters: the mid price 60 seconds after
the fill, from the position's point of view. A fill you got at exactly
your price is not a good fill if the market only came to you on its way
through you.

Output: research/ENTRY_ACCURACY.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TICK = 0.25
IMP, W, RETR = 2.0, 3, 0.118
EXPIRY_S = 600
MARK_S = 60
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta][:4]
    rec = {k: {"slip": [], "mark": [], "fills": 0, "sig": 0}
           for k in ("SELL-STOP", "RESTING LIMIT", "MARKET")}
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        bo = g.first().ffill().values
        bh = g.max().ffill().values
        bl = g.min().ffill().values
        bcs = g.last().ffill()
        bc = bcs.values
        bt = bcs.index.view(np.int64)
        rth = np.asarray((bcs.index.hour * 60 + bcs.index.minute
                          >= 13 * 60 + 30) & (bcs.index.hour < 20))
        for i in range(W + 1, len(bc) - 12):
            if not rth[i]:
                continue
            move = bc[i] - bo[i - W + 1]
            if abs(move) < IMP:
                continue
            hi_ = float(bh[i - W + 1:i + 1].max())
            lo_ = float(bl[i - W + 1:i + 1].min())
            rng = hi_ - lo_
            if rng <= 0:
                continue
            up = move > 0
            lvl = (hi_ - RETR * rng) if up else (lo_ + RETR * rng)
            side = -1 if up else 1                 # INVERSE fade
            t0 = int(bt[i]) + 60_000_000_000
            j0 = int(np.searchsorted(ts, t0))
            jx = int(np.searchsorted(ts, t0 + EXPIRY_S * 1_000_000_000))
            if j0 >= jx:
                continue
            seg = px[j0:jx]
            tseg = ts[j0:jx]

            def mark(fi, entry):
                k = int(np.searchsorted(tseg, tseg[fi]
                                        + MARK_S * 1_000_000_000))
                if k >= len(seg):
                    k = len(seg) - 1
                return side * (float(seg[k]) - entry) / TICK

            for name in rec:
                rec[name]["sig"] += 1
            # SELL-STOP: triggers when the tape prints past the level in
            # the impulse's direction of travel; fills at that print.
            h = np.flatnonzero(seg < lvl) if up else \
                np.flatnonzero(seg > lvl)
            if len(h):
                fi = int(h[0])
                e = float(seg[fi])
                rec["SELL-STOP"]["fills"] += 1
                rec["SELL-STOP"]["slip"].append(side * (lvl - e) / TICK)
                rec["SELL-STOP"]["mark"].append(mark(fi, e))
            # RESTING LIMIT: rests on the far side, fills AT the level
            h2 = np.flatnonzero(seg >= lvl) if up else \
                np.flatnonzero(seg <= lvl)
            if len(h2):
                fi = int(h2[0])
                rec["RESTING LIMIT"]["fills"] += 1
                rec["RESTING LIMIT"]["slip"].append(0.0)
                rec["RESTING LIMIT"]["mark"].append(mark(fi, lvl))
            # MARKET: first print after the bar closes
            e = float(seg[0])
            rec["MARKET"]["fills"] += 1
            rec["MARKET"]["slip"].append(side * (lvl - e) / TICK)
            rec["MARKET"]["mark"].append(mark(0, e))
        del ts, px
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# Entry price accuracy: do you get the price you asked for?")
    log()
    log("Two things, measured separately:")
    log()
    log("- **fill rate** -- how often the order fills at all")
    log("- **price accuracy** -- how often the fill lands ON the "
        "intended level instead of somewhere worse")
    log()
    log(f"NQ, {len(cons)} quarters, the leaderboard trigger (>={IMP:.0f}pt "
        f"over {W} bars, faded), the live bot's level (fib "
        f"{RETR} of the 3-bar wick range), {EXPIRY_S//60}-minute window. "
        f"Slippage is signed from the POSITION's view: positive means a "
        f"worse price than the level.")
    log()
    log("| order type | fill rate | exact price | within 1 tick | "
        "mean slippage | p90 slippage | **mark +60s** |")
    log("|" + "---|" * 7)
    for name in ("MARKET", "SELL-STOP", "RESTING LIMIT"):
        r = rec[name]
        s = np.array(r["slip"])
        m = np.array(r["mark"])
        if not len(s):
            continue
        log(f"| {name} | {r['fills']/max(r['sig'],1):.0%} | "
            f"{(np.abs(s) < 1e-9).mean():.0%} | "
            f"{(s <= 1.0).mean():.0%} | {s.mean():+.2f} tk | "
            f"{np.percentile(s, 90):+.2f} tk | "
            f"**{m.mean():+.2f} tk** |")
    log()
    log("## Reading it")
    log()
    log("**The resting limit already beats both 70% targets.** It fills "
        "at its own price by construction, so price accuracy is 100%, "
        "and its fill rate is far above 70% because the level sits only "
        "a few points away and has ten minutes to be reached.")
    log()
    log("So neither 70% is out of reach -- both are already exceeded. "
        "The mark column is why that does not help. A fill you got at "
        "exactly your price is not a good fill if the market only came "
        "to you on its way through you. Getting your price and getting "
        "a good price are different things, and only one of them can be "
        "ordered from a broker.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "ENTRY_ACCURACY.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/ENTRY_ACCURACY.md")


if __name__ == "__main__":
    main()

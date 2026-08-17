"""46,000 points move every day. Why can we not catch 1.5% of it?

This is the best version of the "the market moves enough" argument and
it deserves the full arithmetic rather than an opinion.

FIRST, PATH LENGTH IS NOT A PROPERTY OF THE MARKET. It is a property of
how finely you slice time. Sum the absolute move of every 1-hour bar and
you get one number; do it for every 1-second tick and you get a number
fifty times larger, from the identical price history. So "NQ moves
46,000 points a day" is not a fact about NQ until you say at what
resolution -- and the resolution is something you choose.

For a random walk sliced into N pieces, each piece has standard
deviation sigma/sqrt(N), so:

    path length  =  N x sigma/sqrt(N) x sqrt(2/pi)  =  0.8 x sigma x sqrt(N)

PATH LENGTH GROWS AS sqrt(N). And to capture any of it you must
reposition, so:

    cost         =  N x cost_per_trade

COST GROWS AS N. The ratio between what is available and what it costs
to reach is therefore proportional to 1/sqrt(N): **the finer you slice,
the worse the deal gets.** More movement appears, and it recedes faster
than you can pay to chase it.

SECOND, WHAT "CATCHING A PERCENTAGE" ACTUALLY REQUIRES. If you are on
the correct side of each move with probability p, you capture

    f  =  2p - 1     of the path length

so capturing 1% needs p = 50.5%, which sounds trivially easy. The
question is never whether f is small. It is whether the f you need
EXCEEDS what the trading required to reach it costs.

This measures both, on real data, per market and per slicing, and
reports the break-even f at each: the fraction of path length that pays
for the trades needed to touch it.

Output: research/PATH_LENGTH.md
"""
import os

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
POLY = os.path.join(ROOT, "data", "polygon")
OUT = os.path.join(ROOT, "research", "PATH_LENGTH.md")
# file, micro $/point, micro RT cost
MKT = {
    "MNQ": ("NQ_5min.csv", 2.0, 1.83),
    "MES": ("ES_5min.csv", 5.0, 2.58),
    "MYM": ("YM_5min.csv", 0.5, 1.83),
    "M2K": ("RTY_5min.csv", 5.0, 1.38),
    "MGC": ("GC_5min.csv", 10.0, 1.83),
    "MCL": ("CL_5min.csv", 10.0, 1.83),
}
SLICES = [("1 hour", 12), ("30 min", 6), ("5 min", 1)]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    log("# 46,000 points move every day. Why not catch 1.5%?")
    log()
    log("**Path length is not a property of the market. It is a "
        "property of how finely you slice time.** Sum the absolute move "
        "of every 1-hour bar and you get one number; do it every second "
        "and you get a number fifty times larger, from the identical "
        "price history. So \"NQ moves 46,000 points a day\" is not a "
        "fact about NQ until you state the resolution -- and the "
        "resolution is something you choose.")
    log()
    log("For a random walk cut into N pieces:")
    log()
    log("    path length = 0.8 x sigma x sqrt(N)      grows as sqrt(N)")
    log("    cost        = N x cost_per_trade         grows as N")
    log()
    log("The ratio goes as 1/sqrt(N). **The finer you slice, the worse "
        "the deal.** More movement appears and it recedes faster than "
        "you can pay to chase it.")
    log()
    log("And capturing a fraction f of path length requires being on the "
        "right side with probability `p = (1 + f) / 2`. Capturing 1% "
        "needs 50.5% accuracy, which sounds easy. The question is never "
        "whether f is small -- it is whether the f you need is bigger "
        "than the f the trading costs.")
    log()

    for label, mult in SLICES:
        log(f"## Sliced every {label}")
        log()
        log("| market | trades/day | path length/day | gross value | "
            "cost/day | **break-even f** | accuracy needed |")
        log("|" + "---|" * 7)
        tot_path = 0.0
        for name, (fn, ppt, cost) in MKT.items():
            p = os.path.join(POLY, fn)
            if not os.path.exists(p):
                continue
            d = pd.read_csv(p)
            d["ts"] = pd.to_datetime(d["ts"], utc=True)
            s = d.set_index("ts")["close"].sort_index()
            if mult > 1:
                s = s.resample(f"{5*mult}min").last().dropna()
            dif = s.diff().abs()
            day = s.index.normalize()
            per = dif.groupby(day).sum()
            cnt = dif.groupby(day).count()
            pl = float(per.median())
            n = float(cnt.median())
            tot_path += pl
            gross = pl * ppt
            cday = n * cost
            be = cday / max(gross, 1e-9)
            acc = (1 + be) / 2
            log(f"| {name} | {n:.0f} | {pl:,.0f} pt | ${gross:,.0f} | "
                f"${cday:,.0f} | **{be:.1%}** | {acc:.1%} |")
        log()
        log(f"Combined path length across these six markets at {label} "
            f"resolution: **{tot_path:,.0f} points/day**.")
        log()

    log("## What the table says")
    log()
    log("Read the break-even column down the page. At coarse slicing you "
        "need a small fraction of a small pool; at fine slicing you need "
        "a large fraction of a large pool. The pool grows -- and the "
        "share of it you must capture grows faster.")
    log()
    log("That is the whole answer to \"there is 46,000 points of "
        "movement out there\". There is. There is also more of it at "
        "every finer resolution, without limit, all the way down to the "
        "tick -- and the finer you go, the larger the percentage you "
        "must take just to pay for the trades that reach it. The "
        "movement is not a pool you can dip into. It only exists at a "
        "resolution, and reaching that resolution costs more than the "
        "extra movement is worth.")
    log()
    log("The direction this points is the same one everything else in "
        "this project points: **fewer trades, longer holds.** Not "
        "because small edges are impossible, but because the break-even "
        "fraction falls as you slow down.")
    log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()

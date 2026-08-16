"""Are Treasuries really more deployable than MNQ, or is that metric wrong?

A second research effort concluded that ZB/ZN are deployable and MNQ is
not, on the grounds that "commission-per-tick makes the other 22 markets
UNDEPLOYABLE". Commission per tick genuinely does favour Treasuries: a
ZB tick is $31.25 and commission is a couple of dollars, while an MNQ
tick is $0.50 against $1.33 of commission -- one MNQ round trip costs
2.7 TICKS, one ZB round trip costs 0.08 ticks.

But commission is not the whole cost. Crossing the spread is, and a
one-tick ZB spread costs $31.25 to cross where a one-tick MNQ spread
costs $0.50. Sixty-two times more. Whether that is worth paying depends
entirely on how far the instrument MOVES for it, which is the
sigma/spread question from INSTRUMENT_CHOICE.md.

So this measures, for every instrument with data on disk:

    budget = sigma(1 hour) in DOLLARS / round-trip cost in DOLLARS

Read it as "how many round trips does one hour of movement pay for".
It is the honest version of commission-per-tick, because it counts the
spread and it counts how much the market actually moves. Higher is more
tradable, and it is the same quantity for every instrument, so they can
be ranked directly.

MARGIN is reported alongside, because it is decisive for a $4,000
account and no ratio survives not being able to hold the position. ZB
and ZN have no micro contract -- full size or nothing.

Output: research/TREASURY_CHECK.md
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
POLY = os.path.join(ROOT, "data", "polygon")
OUT = os.path.join(ROOT, "research", "TREASURY_CHECK.md")

# name: (file, $/point, tick in points, commission RT, approx margin,
#        micro available?)
SPEC = {
    "ZB 30y":  ("ZB_5min.csv", 1000.0, 1 / 32,   2.50, 4200, "no"),
    "ZN 10y":  ("ZN_5min.csv", 1000.0, 1 / 64,   2.50, 2100, "no"),
    "ZF 5y":   ("ZF_5min.csv", 1000.0, 1 / 128,  2.50, 1300, "no"),
    "ZT 2y":   ("ZT_5min.csv", 2000.0, 1 / 256,  2.50,  800, "no"),
    "MNQ":     ("NQ_5min.csv",    2.0, 0.25,     1.33,  100, "IS micro"),
    "MES":     ("ES_5min.csv",    5.0, 0.25,     1.33,  200, "IS micro"),
    "MYM":     ("YM_5min.csv",    0.5, 1.0,      1.33,  100, "IS micro"),
    "M2K":     ("RTY_5min.csv",   0.5, 0.10,     1.33,  100, "IS micro"),
    "MCL":     ("CL_5min.csv",   10.0, 0.01,     1.33,  200, "IS micro"),
    "MGC":     ("GC_5min.csv",   10.0, 0.10,     1.33,  300, "IS micro"),
}
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    rows = []
    for name, (fn, ppt, tick, comm, margin, micro) in SPEC.items():
        p = os.path.join(POLY, fn)
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        d["ts"] = pd.to_datetime(d["ts"], utc=True)
        d = d.set_index("ts").sort_index()
        c = d["close"].resample("1h").last().dropna()
        v = c.diff()
        # never difference across a session break
        gap = c.index.to_series().diff() > pd.Timedelta("2h")
        v[gap.values] = np.nan
        sig_pt = float(np.nanstd(v.values))
        sig_usd = sig_pt * ppt
        tick_usd = tick * ppt
        cost = comm + tick_usd          # commission + one spread crossed
        rows.append((sig_usd / cost, name, sig_pt, sig_usd, tick_usd,
                     comm, cost, margin, micro,
                     comm / tick_usd))
    rows.sort(reverse=True)

    log("# Are Treasuries really more deployable than MNQ?")
    log()
    log("A second research effort ruled MNQ out and ZB/ZN in, on the "
        "grounds that commission-per-tick makes everything else "
        "undeployable. That metric genuinely favours Treasuries -- one "
        "MNQ round trip costs **2.7 ticks** of commission, one ZB round "
        "trip costs **0.08**.")
    log()
    log("But commission is not the whole cost. Crossing a one-tick ZB "
        "spread costs **$31.25**; crossing a one-tick MNQ spread costs "
        "**$0.50**. Sixty-two times more. Whether that is worth paying "
        "depends on how far the instrument moves for it.")
    log()
    log("So: **how many round trips does one hour of movement pay for?** "
        "Same quantity for every instrument, counts the spread, counts "
        "the movement. Higher is more tradable.")
    log()
    log("| instrument | sigma 1h | tick $ | comm | spread+comm | "
        "**budget** | comm/tick | margin | micro |")
    log("|" + "---|" * 9)
    for (b, name, spt, susd, tu, comm, cost, marg, micro, cpt) in rows:
        log(f"| {name} | ${susd:,.0f} | ${tu:.2f} | ${comm:.2f} | "
            f"${cost:.2f} | **{b:.1f}x** | {cpt:.2f} ticks | "
            f"${marg:,} | {micro} |")
    log()
    log("`budget` is one hour of movement divided by one round trip. "
        "`comm/tick` is the metric the other effort used -- note it "
        "ranks the table almost backwards.")
    log()
    zb = next((r for r in rows if r[1].startswith("ZB")), None)
    mnq = next((r for r in rows if r[1] == "MNQ"), None)
    if zb and mnq:
        log(f"**MNQ's budget is {mnq[0]/zb[0]:.1f}x ZB's.** By "
            f"commission-per-tick ZB looks {mnq[9]/zb[9]:.0f}x better; "
            f"by movement-per-cost MNQ is {mnq[0]/zb[0]:.1f}x better. "
            f"The two metrics disagree because commission-per-tick "
            f"ignores the spread, and on Treasuries the spread IS the "
            f"cost -- ${zb[4]:.2f} a crossing against ${zb[5]:.2f} of "
            f"commission.")
        log()
    log("## The constraint that outranks the ratio")
    log()
    log("**ZB and ZN have no micro contract.** Full size or nothing: "
        "~$4,200 and ~$2,100 of day-trade margin against a $4,000 "
        "account. One ZB position is the entire account; the "
        "14-sleeve portfolio quoted at $4,093/week is not holdable at "
        "this capital regardless of whether its edge is real.")
    log()
    log("None of this says the ZB/ZN result is wrong. It says the reason "
        "given for preferring it -- commission per tick -- is not the "
        "quantity that decides tradability, and by the quantity that "
        "does, MNQ ranks better than the instrument being recommended "
        "over it.")
    log()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()

"""What IS the best entry order type -- and does any of them save this?

The question deserves every order that actually exists, measured side by
side on the same signals, with the FILL RATE of each one reported rather
than assumed.

Two different things get called "fill":

    fill RATE    how often you get in
    fill PRICE   what price you get when you do

They trade against each other and you cannot maximise both. That is the
entire point of this table.

  MARKET         cross the spread at the signal bar. ~100% fill rate,
                 worst price. Nothing to dispute about it.
  STOP           rest a trigger below the market; it fires as price
                 crosses and fills at the PRINT that triggered it, which
                 is past the level. High fill rate, poor price.
  RESTING LIMIT  put the sell ABOVE the market and wait for price to
                 come back up to it. Fills AT its own price -- the best
                 price available -- and pays for it with a fill rate
                 well under 100%, because price often never returns.
  AT-LEVEL       100% fill rate AND the limit price. This is the
                 leaderboard's assumption and it is not an order type.
                 No broker, exchange or venue offers it. It is in the
                 table as the control that shows what the assumption is
                 worth, not as a candidate.

The fill rate column is measured, not assumed: it is each mode's trade
count over the MARKET mode's trade count, since a market order takes
essentially every signal.

Output: research/ORDER_TYPES.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

TICK, TV, COMM = 0.25, 2.0, 1.33
HOLD_S = 600
CFGS = [
    ("1 S2-WINNER",  dict(imp=2.0, w=3, retr=0.118, S=5.0, T=44.0)),
    ("4 T36-W3",     dict(imp=2.0, w=3, retr=0.118, S=5.0, T=36.0)),
    ("- CANON live", dict(imp=5.0, w=4, retr=0.236, S=10.0, T=20.0)),
]
MODES = [
    ("MARKET",        dict(arch="stop", market_entry=True)),
    ("STOP",          dict(arch="stop")),
    ("RESTING LIMIT", dict(arch="stop", resting_limit=True,
                           slip_on=False)),
    ("AT-LEVEL (n/a)", dict(arch="stop", entry_at_level=True,
                            slip_on=False)),
]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {}
    days = 0
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        bt, bo, bh, bl, bc, rth = ce.bars_ohlc(ts, px)
        mi = ce.MinuteIndex(ts, px, bt)
        days += len(np.unique(pd.to_datetime(bt[rth]).normalize().values))
        for name, base in CFGS:
            for mname, mods in MODES:
                cell = dict(base, hold_s=HOLD_S, tick=TICK, tv=TV,
                            comm=COMM, anchor="range", bo=bo, bh=bh,
                            bl=bl, **mods)
                tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc), cell,
                                 mindex=mi)
                a = acc.setdefault((name, mname),
                                   {"pnl": [], "tgt": 0, "n": 0})
                a["pnl"].extend(t[4] for t in tr)
                a["tgt"] += sum(1 for t in tr if t[3] == "target")
                a["n"] += len(tr)
        del ts, px, mi
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# Which entry order type is best, and does any of them save it?")
    log()
    log("Two different things get called \"fill\":")
    log()
    log("- **fill RATE** -- how often you get in")
    log("- **fill PRICE** -- what price you get when you do")
    log()
    log("They trade against each other and no order type maximises "
        "both. A market order takes every signal at the worst price; a "
        "resting limit gets the best price and misses most of them. "
        "That trade-off is what this table measures.")
    log()
    log(f"NQ, 8 quarters, {days} RTH sessions, range anchor, "
        f"${COMM:.2f} round trip, 10-minute window, one position at a "
        f"time, timeouts marked to market. Fill rate is each mode's "
        f"trade count over MARKET's, since a market order takes "
        f"essentially every signal.")
    log()
    log("| config | order type | fill rate | trades/day | target-hit % "
        "| $/trade | $/trade before ANY commission |")
    log("|" + "---|" * 7)
    for name, _ in CFGS:
        base_n = max(acc[(name, "MARKET")]["n"], 1)
        for mname, _m in MODES:
            a = acc[(name, mname)]
            n = max(a["n"], 1)
            pt = sum(a["pnl"]) / n
            log(f"| {name} | {mname} | {a['n']/base_n:.0%} | "
                f"{a['n']/max(days,1):.0f} | {a['tgt']/n:.1%} | "
                f"**${pt:+.2f}** | ${pt + COMM:+.2f} |")
    log()
    log("## What this answers")
    log()
    log("**AT-LEVEL is not an order type.** 100% fill rate at the limit "
        "price is not something a broker declines to offer -- it is not "
        "a thing. It is in the table only to show what the assumption is "
        "worth, and the gap between its row and the other three is the "
        "entire result being claimed.")
    log()
    log("**The real orders bracket the truth.** MARKET is the most fills "
        "and the worst price; RESTING LIMIT is the best price and the "
        "fewest fills. Any real execution sits between them. If both "
        "ends lose, everything between them loses, and no smarter order "
        "routing changes that.")
    log()
    log("**The last column is the one that ends the argument.** It "
        "strips commission out completely -- free trading, no broker, no "
        "exchange fee. If a row is still negative there, then costs were "
        "never the problem and neither were fills.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "ORDER_TYPES.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/ORDER_TYPES.md")


if __name__ == "__main__":
    main()

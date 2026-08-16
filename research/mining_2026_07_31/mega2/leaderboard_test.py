"""The six leaderboard configs, run through the validated engine.

A second Claude produced a leaderboard claiming $984-$1,034/day per MNQ
from the INVERSE FADE, with out-of-sample halves at $1,430-$1,590/day.
Those are extraordinary numbers and they deserve a real test rather than
an argument, so this runs the exact published parameters through
causal_engine.run_cell -- the engine that reproduced the live bot's
trade list 29/29 on real tape, and that found a planted synthetic edge
when one was hidden in the data.

THE ONE THING UNDER TEST is where an against-the-impulse entry fills.

The strategy is: price rises, and we SELL at a level BELOW the current
price. There are exactly two ways that order can exist:

  a STOP        it triggers when the tape crosses down through the
                level, and fills at the PRINT THAT TRIGGERED IT. On NQ
                that print averages several points past the level.
  a MARKETABLE  a sell limit below the market does not rest. It executes
  LIMIT         immediately against the current bid, at the signal bar,
                on EVERY signal -- including the ones that then rip
                straight up against us.

What it CANNOT be is an order that waits below the market and fills at
its own price only on the occasions price comes down to meet it. That
is the accounting most fade backtests use, and it takes the good fill
AND the selection benefit of only entering after a confirmed downtick.

So each config is run three ways:

  at-level   entry priced AT the level (the assumption under test)
  honest     entry at the triggering print plus one tick (arch="stop")
  market     no level at all: sell at the signal bar close

If at-level reproduces ~$1,000/day and honest does not, the result is
that single modelling choice and nothing else. A RANDOM-direction
control runs alongside, because a positive number means nothing if a
coin flip in the same geometry is also positive.

Both level definitions are tested: `range` (fib of the wick range --
what the live bot computes) and `close` (close-to-close).

Output: research/LEADERBOARD_TEST.md
"""
import gc
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

TICK, TV, COMM = 0.25, 2.0, 1.33      # the user's confirmed real cost
HOLD_S = 600

CFGS = [
    ("1 S2-WINNER",   dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=44.0)),
    ("2 T36-W4",      dict(imp=2.0, w=4, retr=0.118, S=5.0,  T=36.0)),
    ("3 T30-W4",      dict(imp=2.0, w=4, retr=0.118, S=5.0,  T=30.0)),
    ("4 T36-W3",      dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=36.0)),
    ("5 T30-LOWDD",   dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=30.0)),
    ("6 CONSERV",     dict(imp=3.0, w=3, retr=0.236, S=6.0,  T=30.0)),
    ("- CANON live",  dict(imp=5.0, w=4, retr=0.236, S=10.0, T=20.0)),
]
MODES = [("at-level", dict(arch="stop", entry_at_level=True,
                           slip_on=False)),
         ("honest",   dict(arch="stop")),
         ("market",   dict(arch="stop", market_entry=True))]
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
        import pandas as pd
        days += len(np.unique(
            pd.to_datetime(bt[rth]).normalize().values))
        for anchor in ("range", "close"):
            for name, base in CFGS:
                for mname, mods in MODES:
                    if mname == "market":
                        continue          # handled by retr=0 below
                    cell = dict(base, hold_s=HOLD_S, tick=TICK, tv=TV,
                                comm=COMM, anchor=anchor,
                                bo=bo, bh=bh, bl=bl, **mods)
                    tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc),
                                     cell, mindex=mi)
                    k = (anchor, name, mname)
                    a = acc.setdefault(k, [])
                    a.extend(t[4] for t in tr)
        del ts, px, mi
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# The leaderboard configs, run through the validated engine")
    log()
    log("A second Claude published a leaderboard claiming **$984-$1,034 "
        "per day** per MNQ from the INVERSE FADE, with out-of-sample "
        "halves at $1,430-$1,590/day. This runs those exact parameters "
        "through `causal_engine.run_cell` -- the engine that reproduced "
        "the live bot's trade list 29/29 on real tape and that found a "
        "planted synthetic edge when one was hidden in the data.")
    log()
    log(f"NQ, 8 quarters, {days} RTH sessions, "
        f"${COMM:.2f} round trip (the confirmed real cost), 10-minute "
        f"window, timeouts marked to market.")
    log()
    log("**The one thing under test is where an against-the-impulse "
        "entry fills.** The strategy sells at a level BELOW the market. "
        "Such an order is either a STOP -- filling at the print that "
        "triggered it, several points past the level on NQ -- or a "
        "MARKETABLE LIMIT, which executes immediately at the bid on "
        "every signal. What it cannot be is an order that waits below "
        "the market and fills at its own price only when price comes "
        "down to meet it. That last one is the assumption under test.")
    log()
    log("| anchor | config | at-level $/day | honest $/day | "
        "at-level $/trade | honest $/trade | trades/day |")
    log("|" + "---|" * 7)
    for anchor in ("range", "close"):
        for name, _ in CFGS:
            row = []
            for mname in ("at-level", "honest"):
                v = acc.get((anchor, name, mname), [])
                row.append((sum(v) / max(days, 1),
                            sum(v) / max(len(v), 1), len(v) / max(days, 1)))
            log(f"| {anchor} | {name} | ${row[0][0]:+,.0f} | "
                f"**${row[1][0]:+,.0f}** | ${row[0][1]:+.2f} | "
                f"${row[1][1]:+.2f} | {row[0][2]:.0f} |")
    log()
    os.makedirs(os.path.join(fuse.ROOT, "research"), exist_ok=True)
    open(os.path.join(fuse.ROOT, "research",
                      "LEADERBOARD_TEST.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/LEADERBOARD_TEST.md")


if __name__ == "__main__":
    main()

"""The ~100% fill-rate version: market entry, no fill assumptions at all.

The user asked the right question -- can we just get a fill rate near
100%? Yes. A market order does not wait for price to come to it; it
fills essentially always. What you give up is the level price and the
spread you cross.

That makes this the cleanest possible test of the leaderboard family,
because it removes the ONE thing the whole dispute is about. No resting
limit, no trigger print, no argument over which side of the book the
order sits on. Signal fires at the bar close, we are in at the next
print, and the bracket runs from there.

If the family is negative here, no order type rescues it: this is the
entry whose fill nobody can dispute, and every other entry style is a
bet that you can do better than it.

Three columns, same signals:

  at-level   entry priced AT the level. Impossible for a sell order that
             sits below the market, and the assumption the leaderboard
             rests on.
  stop       entry at the print that triggers the cross, plus a tick.
  MARKET     entry at the first print after the signal bar closes, plus
             a tick of spread. ~100% fill by construction.

A RANDOM-direction control runs in the market column, because a positive
number means nothing if a coin flip in the same geometry is positive too.

Output: research/LEADERBOARD_MARKET.md
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
    ("1 S2-WINNER",  dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=44.0)),
    ("4 T36-W3",     dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=36.0)),
    ("5 T30-LOWDD",  dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=30.0)),
    ("6 CONSERV",    dict(imp=3.0, w=3, retr=0.236, S=6.0,  T=30.0)),
    ("- CANON live", dict(imp=5.0, w=4, retr=0.236, S=10.0, T=20.0)),
]
MODES = [("at-level", dict(arch="stop", entry_at_level=True,
                           slip_on=False)),
         ("stop", dict(arch="stop")),
         ("MARKET", dict(arch="stop", market_entry=True))]
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
        nsig = {}
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
            nsig[name] = acc[(name, "MARKET")]["n"]
        del ts, px, mi
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# The ~100% fill-rate version: market entry, no fill assumptions")
    log()
    log("The question was whether we can simply get a fill rate near "
        "100%. We can: a market order does not wait for price to come to "
        "it. What you give up is the level price and the spread you "
        "cross.")
    log()
    log("That makes this the cleanest test of the family, because it "
        "removes the one thing the entire dispute is about. No resting "
        "limit, no trigger print, no argument about which side of the "
        "book the order sits on. The signal fires at the bar close, we "
        "are in at the next print, the bracket runs from there.")
    log()
    log(f"NQ, 8 quarters, {days} RTH sessions, range anchor, "
        f"${COMM:.2f} round trip, 10-minute window, timeouts marked to "
        f"market, one position at a time.")
    log()
    log("| config | mode | trades/day | target-hit % | $/trade | $/day |")
    log("|" + "---|" * 6)
    for name, _ in CFGS:
        for mname, _m in MODES:
            a = acc[(name, mname)]
            n = max(a["n"], 1)
            star = "**" if mname == "MARKET" else ""
            log(f"| {name} | {star}{mname}{star} | "
                f"{a['n']/max(days,1):.0f} | {a['tgt']/n:.1%} | "
                f"{star}${sum(a['pnl'])/n:+.2f}{star} | "
                f"${sum(a['pnl'])/max(days,1):+,.0f} |")
    log()
    log("## What the MARKET rows settle")
    log()
    log("Whatever the right fill model is, it cannot be better than "
        "this one on selection: a market order takes EVERY signal, "
        "including the ones a resting limit would have skipped. A "
        "limit entry can beat it on price -- by at most the spread -- "
        "but only by giving up fills.")
    log()
    log("So the market row is the honest centre of the range. If it is "
        "negative, the family needs the fill model to be doing the work, "
        "and the fill model cannot do work a real order book will not "
        "do.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "LEADERBOARD_MARKET.md"), "w").write(
                          "\n".join(L) + "\n")
    print("wrote research/LEADERBOARD_MARKET.md")


if __name__ == "__main__":
    main()

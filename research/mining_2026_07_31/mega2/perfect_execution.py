"""The theoretical ceiling: execution better than physically possible.

The question was whether fills and entry price accuracy can be solved by
ANY means. This answers it by granting all of them at once, including
several that no exchange offers:

    100% fill rate        every signal is taken, none missed
    ZERO slippage         filled at the exact print, no spread crossed
                          in EITHER direction -- not the half-tick a
                          marketable limit costs, not the tick a stop
                          costs, nothing
    ZERO commission       no broker, no exchange fee, no clearing
    exit at zero cost     stops and timeouts also cross nothing

No account can do this. You cannot trade without crossing something --
somebody has to be on the other side and they charge for it. This is
strictly better than the best execution that has ever existed.

Its purpose is to bound the argument. Any real improvement -- posting
inside the spread, co-location, queue priority, a better broker, direct
market access, membership rates -- lands somewhere BELOW this number.
If this ceiling is negative, then execution is not a lever that can be
pulled hard enough, and the discussion about fills is finished.

Compared against the realistic market-entry row so the size of the
entire execution question is visible as one number.

Output: research/PERFECT_EXECUTION.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

TICK, TV = 0.25, 2.0
HOLD_S = 600
CFGS = [
    ("1 S2-WINNER",  dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=44.0)),
    ("4 T36-W3",     dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=36.0)),
    ("5 T30-LOWDD",  dict(imp=2.0, w=3, retr=0.118, S=5.0,  T=30.0)),
    ("6 CONSERV",    dict(imp=3.0, w=3, retr=0.236, S=6.0,  T=30.0)),
    ("- CANON live", dict(imp=5.0, w=4, retr=0.236, S=10.0, T=20.0)),
]
MODES = [
    ("realistic", dict(market_entry=True, comm=1.33, slip_on=True)),
    ("PERFECT",   dict(market_entry=True, comm=0.0, slip_on=False)),
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
                            anchor="range", bo=bo, bh=bh, bl=bl,
                            arch="stop", **mods)
                tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc), cell,
                                 mindex=mi)
                a = acc.setdefault((name, mname),
                                   {"p": 0.0, "n": 0, "t": 0})
                a["p"] += sum(t[4] for t in tr)
                a["t"] += sum(1 for t in tr if t[3] == "target")
                a["n"] += len(tr)
        del ts, px, mi
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# The theoretical ceiling: execution better than possible")
    log()
    log("The question was whether fills and entry price accuracy can be "
        "solved by ANY means. This grants all of them at once, including "
        "several no exchange offers:")
    log()
    log("- **100% fill rate** -- every signal taken, none missed")
    log("- **zero slippage** -- filled at the exact print, crossing "
        "nothing in either direction")
    log("- **zero commission** -- no broker, no exchange, no clearing")
    log("- **free exits** -- stops and timeouts also cross nothing")
    log()
    log("No account can do this. You cannot trade without crossing "
        "something; somebody is on the other side and they charge for "
        "it. This is strictly better than the best execution that has "
        "ever existed, and its purpose is to bound the argument. Posting "
        "inside the spread, co-location, queue priority, direct market "
        "access, membership rates -- every real improvement lands BELOW "
        "this line.")
    log()
    log(f"NQ, 8 quarters, {days} RTH sessions, range anchor, 10-minute "
        f"window, one position at a time, timeouts marked to market.")
    log()
    log("| config | realistic $/trade | **PERFECT $/trade** | "
        "target-hit % | the entire execution question is worth |")
    log("|" + "---|" * 5)
    for name, _ in CFGS:
        r = acc[(name, "realistic")]
        p = acc[(name, "PERFECT")]
        rn, pn = max(r["n"], 1), max(p["n"], 1)
        rv, pv = r["p"] / rn, p["p"] / pn
        log(f"| {name} | ${rv:+.2f} | **${pv:+.2f}** | "
            f"{p['t']/pn:.1%} | ${pv-rv:+.2f} |")
    log()
    best = max((acc[(n, "PERFECT")]["p"] / max(acc[(n, "PERFECT")]["n"], 1),
                n) for n, _ in CFGS)
    log("## What this settles")
    log()
    log(f"The best config under impossible execution is **{best[1]}** at "
        f"**${best[0]:+.2f}/trade**.")
    log()
    if best[0] <= 0:
        log("It is still negative. Every question about fill rate, entry "
            "price accuracy, order type, broker, commission tier and "
            "venue has now been answered at once, by granting all of "
            "them perfectly and for free. The strategy loses anyway.")
        log()
        log("The last column is the size of the entire execution "
            "question -- everything that separates a real account from "
            "a physically impossible one. Compare it with how far each "
            "row is from zero. Execution was never the gap.")
    else:
        log("It is positive -- so a ceiling exists, and the distance "
            "between the two columns is what execution quality is "
            "worth. That number is the budget for any real improvement, "
            "and no real improvement can capture all of it.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "PERFECT_EXECUTION.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/PERFECT_EXECUTION.md")


if __name__ == "__main__":
    main()

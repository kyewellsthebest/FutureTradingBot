"""The 11% a resting limit never fills -- are those the winners?

The hypothesis is sharp and the mechanism is right. A short resting
ABOVE the market only fills when price rises into it. When the fade
works immediately -- price drops and never comes back -- the order
never fills. So the unfilled trades are structurally the ones that went
your way, and missing them should hurt.

This measures exactly how much. Every signal is split in two:

    FILLED    the resting limit would have been reached
    MISSED    it never was

and BOTH groups are then priced as if entered at MARKET on the signal
bar, so the two are directly comparable on the same footing. If the
MISSED group is strongly positive, the hypothesis holds and the fill
rate really is the binding problem. If it is not, then capturing those
trades -- which is precisely what a market order does -- cannot rescue
the strategy.

Reported per bracket, because a group can look good at one geometry and
bad at another, and with the RANDOM-direction control alongside.

Output: research/MISSED_FILLS.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TICK, TV, COMM = 0.25, 2.0, 1.33
IMP, W, RETR = 2.0, 3, 0.118
HZ_S = 600
BRACKETS = [(5., 44.), (5., 36.), (5., 30.), (10., 20.)]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta][:4]
    acc = {}
    rng = np.random.default_rng(11)
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
            rg = hi_ - lo_
            if rg <= 0:
                continue
            up = move > 0
            lvl = (hi_ - RETR * rg) if up else (lo_ + RETR * rg)
            t0 = int(bt[i]) + 60_000_000_000
            j0 = int(np.searchsorted(ts, t0))
            jH = int(np.searchsorted(ts, t0 + HZ_S * 1_000_000_000))
            if j0 >= jH:
                continue
            seg = px[j0:jH]
            entry = float(seg[0])
            cmin = np.minimum.accumulate(seg)
            cmax = np.maximum.accumulate(seg)
            # would a limit resting on the far side ever be reached?
            reached = bool((seg >= lvl).any() if up else (seg <= lvl).any())
            grp = "FILLED" if reached else "MISSED"
            for tag, side in (("fade", -1 if up else 1),
                              ("RANDOM", 1 if rng.random() < 0.5 else -1)):
                for (S, T) in BRACKETS:
                    if side > 0:
                        si = np.searchsorted(-cmin, -(entry - S))
                        ti = np.searchsorted(cmax, entry + T)
                    else:
                        si = np.searchsorted(cmax, entry + S)
                        ti = np.searchsorted(-cmin, -(entry - T))
                    if ti < si:
                        pnl = T * TV
                    elif si < len(seg):
                        pnl = -S * TV
                    else:
                        k = len(seg) - 1
                        pnl = side * (float(seg[k]) - entry) * TV
                    a = acc.setdefault((tag, grp, S, T),
                                       {"p": 0.0, "n": 0, "t": 0})
                    a["p"] += pnl
                    a["n"] += 1
                    a["t"] += 1 if ti < si else 0
        del ts, px
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# The 11% a resting limit never fills -- are those the winners?")
    log()
    log("A short resting ABOVE the market only fills when price rises "
        "into it. When the fade works immediately -- price drops and "
        "never comes back -- the order never fills. So the unfilled "
        "trades are structurally the ones that went your way, and the "
        "hypothesis that missing them is what costs the strategy is "
        "mechanically sound. This measures how much it is worth.")
    log()
    log(f"NQ, {len(cons)} quarters. Every signal split by whether a "
        f"resting limit would ever have been reached, then BOTH groups "
        f"priced as MARKET entries on the signal bar so they are "
        f"comparable. Gross, before the ${COMM:.2f} commission, so the "
        f"fill question is isolated from the cost question.")
    log()
    log("| bracket | group | signals | target-first | gross $/trade | "
        "net $/trade |")
    log("|" + "---|" * 6)
    for (S, T) in BRACKETS:
        for grp in ("FILLED", "MISSED"):
            a = acc.get(("fade", grp, S, T))
            if not a:
                continue
            n = max(a["n"], 1)
            log(f"| {S:.0f}/{T:.0f} | {grp} | {a['n']:,} | "
                f"{a['t']/n:.1%} | **${a['p']/n:+.2f}** | "
                f"${a['p']/n - COMM:+.2f} |")
        r = acc.get(("RANDOM", "MISSED", S, T))
        if r:
            n = max(r["n"], 1)
            log(f"| {S:.0f}/{T:.0f} | _RANDOM, missed_ | {r['n']:,} | "
                f"{r['t']/n:.1%} | ${r['p']/n:+.2f} | "
                f"${r['p']/n - COMM:+.2f} |")
    log()
    log("## Reading it")
    log()
    log("If MISSED is strongly positive, the fill rate is the binding "
        "problem and the fix is a market order, which takes every one of "
        "them. If MISSED is not positive, then the trades the limit "
        "skips were never the prize, and no improvement in fill rate "
        "can rescue the strategy.")
    log()
    log("The RANDOM row matters here more than usual: MISSED is a "
        "selected subset -- these are the moves that ran away without "
        "looking back -- and a coin flip inside that same subset will "
        "not read zero. Only the difference between fade and RANDOM in "
        "the MISSED group is attributable to the signal.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "MISSED_FILLS.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/MISSED_FILLS.md")


if __name__ == "__main__":
    main()

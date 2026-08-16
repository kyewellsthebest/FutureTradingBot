"""Where does 70% accuracy live, and is it worth anything when you get there?

A win rate is not a property of a strategy. It is a property of the
BRACKET. For a driftless random walk the chance of touching +T before
-S is exactly S/(S+T), so:

    risk 10 make 20   ->  33.3% of the time you win
    risk 10 make 10   ->  50.0%
    risk 20 make 10   ->  66.7%
    risk 44 make  5   ->  89.8%

Any accuracy you want is available by choosing the geometry, and none of
it means anything on its own. The only quantity that carries information
is the GAP:

    gap = measured target-first rate  -  S/(S+T)

Zero gap is a coin flip dressed in whatever win rate you selected. A
positive gap is skill, and the SAME gap is worth the same money whether
it shows up as 35% on a 1:2 or 70% on a 2:1.

This measures the gap across a full grid of geometries on real tape,
entering at the MARKET so no fill assumption is involved, and reports
for each one:

    measured    what actually happens
    random walk S/(S+T), the no-skill expectation
    gap         measured minus random walk
    needed      (S+cost)/(S+T), the rate that actually pays at $1.33
    shortfall   needed minus measured -- the number that has to reach 0

Two entry populations are compared:

    UNCONDITIONAL   every 5th RTH minute. This is the market's own
                    barrier geometry with no signal at all, and it is
                    the control the whole table is read against.
    IMPULSE         only after a >=2pt 3-bar impulse, the leaderboard's
                    trigger, taken in the fade direction.

If the impulse rows do not beat the unconditional rows, the signal adds
nothing and the accuracy is pure geometry.

Output: research/ACCURACY_CURVE.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TV, COMM = 2.0, 1.33
HZ_S = 600
STEP = 5                       # sample every 5th RTH minute
STOPS = [2., 3., 5., 10., 15., 20., 30., 44.]
TGTS = [2., 3., 5., 10., 15., 20., 30., 44.]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta][:4]
    acc = {}
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        bcs = g.last().ffill()
        bo = g.first().ffill().values
        bc = bcs.values
        bt = bcs.index.view(np.int64)
        rth = np.asarray((bcs.index.hour * 60 + bcs.index.minute
                          >= 13 * 60 + 30) & (bcs.index.hour < 20))
        # the leaderboard trigger: >=2pt move over 3 bars, faded
        mv = np.full(len(bc), np.nan)
        mv[3:] = bc[3:] - bo[1:-2]
        for i in range(0, len(bc) - 12, STEP):
            if not rth[i]:
                continue
            t0 = int(bt[i]) + 60_000_000_000
            j0 = int(np.searchsorted(ts, t0))
            jH = int(np.searchsorted(ts, t0 + HZ_S * 1_000_000_000))
            if j0 >= jH:
                continue
            seg = px[j0:jH]
            entry = float(seg[0])
            cmin = np.minimum.accumulate(seg)
            cmax = np.maximum.accumulate(seg)
            pops = [("UNCOND", 1)]
            if np.isfinite(mv[i]) and abs(mv[i]) >= 2.0:
                pops.append(("IMPULSE", -1 if mv[i] > 0 else 1))
            for pname, side in pops:
                for S in STOPS:
                    for T in TGTS:
                        if side > 0:
                            si = np.searchsorted(-cmin, -(entry - S))
                            ti = np.searchsorted(cmax, entry + T)
                        else:
                            si = np.searchsorted(cmax, entry + S)
                            ti = np.searchsorted(-cmin, -(entry - T))
                        a = acc.setdefault((pname, S, T),
                                           {"t": 0, "n": 0, "s": 0})
                        a["n"] += 1
                        if ti < si:
                            a["t"] += 1
                        elif si < len(seg):
                            a["s"] += 1
        del ts, px, seg, cmin, cmax
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# Where does 70% accuracy live, and is it worth anything?")
    log()
    log("A win rate is a property of the BRACKET, not of a strategy. For "
        "a driftless random walk the chance of touching +T before -S is "
        "exactly `S/(S+T)`, so any accuracy you want is available by "
        "choosing the geometry -- risk 20 to make 10 and you win 66.7% "
        "of the time knowing nothing at all.")
    log()
    log("The only quantity carrying information is the **gap**: measured "
        "target-first minus `S/(S+T)`. The same gap is worth the same "
        "money whether it appears as 35% on a 1:2 or 70% on a 2:1.")
    log()
    log(f"NQ, {len(cons)} quarters, market entry at the bar close (no "
        f"fill assumption), 10-minute horizon, sampled every {STEP} RTH "
        f"minutes. `needed` is `(S+cost)/(S+T)` at ${COMM:.2f}.")
    log()
    for pname in ("UNCOND", "IMPULSE"):
        rows = []
        for S in STOPS:
            for T in TGTS:
                a = acc.get((pname, S, T))
                if not a or a["n"] < 500:
                    continue
                p = a["t"] / a["n"]
                rw = S / (S + T)
                need = (S + COMM / TV) / (S + T)
                rows.append((p - need, p, rw, need, S, T, a["n"]))
        if not rows:
            continue
        rows.sort(reverse=True)
        log(f"## {pname} entries")
        log()
        log("| stop | target | measured | random walk | **gap vs random** "
            "| needed to pay | **shortfall** |")
        log("|" + "---|" * 7)
        for _, p, rw, need, S, T, n in rows[:14]:
            log(f"| {S:.0f} | {T:.0f} | {p:.1%} | {rw:.1%} | "
                f"**{p-rw:+.2%}** | {need:.1%} | "
                f"**{need-p:+.2%}** |")
        pos = [r for r in rows if r[0] > 0]
        log()
        log(f"Geometries that clear the cost bar: **{len(pos)} of "
            f"{len(rows)}**")
        log()
        near70 = sorted(rows, key=lambda r: abs(r[1] - 0.70))[:3]
        log("Closest to a 70% win rate:")
        log()
        for _, p, rw, need, S, T, n in near70:
            log(f"- risk {S:.0f} / make {T:.0f}: **{p:.1%}** measured, "
                f"but a coin flip in that same bracket gives {rw:.1%} "
                f"and you need {need:.1%} to pay -- so the 70% is "
                f"{p-rw:+.2%} of actual skill.")
        log()
    log("## How to read this")
    log()
    log("Find the row nearest 70% measured. Then look at its random-walk "
        "column: that is what the same 70% would be worth with no "
        "information whatsoever. The gap between those two columns is "
        "the only thing any amount of research can move, and the "
        "shortfall column is how far it has to go.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "ACCURACY_CURVE.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/ACCURACY_CURVE.md")


if __name__ == "__main__":
    main()

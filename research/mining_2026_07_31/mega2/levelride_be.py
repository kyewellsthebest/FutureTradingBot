"""Does the time-based breakeven stop actually work?

The claim: "if a trade is not +40-60pt favourable by minute 30, pull the
stop to breakeven" turns LEVELRIDE from $32/day into $129/day and halves
the drawdown. That is the user's own idea and the only positive finding
on the table that a second implementation has not checked.

It deserves a hard look for two reasons.

FOUR RULES WERE TRIED AND ONE WON BY 4x. Fixed breakeven hurt, trailing
hurt, volume-scaled take-profit was flat. A one-in-four winner is where
luck lives.

IT ARGUES WITH A THEOREM. On a martingale every stopping rule has the
same expectancy, so an exit rule cannot manufacture edge from nothing. A
4x improvement means either genuine negative autocorrelation in losing
trades -- which would be a real and tradable finding -- or selection.

Those two are distinguishable, and that is the whole design here. A real
effect is a PLATEAU: it holds at 20, 30 and 40 minutes and at 30, 40, 50
and 60 points, because nothing in the market knows the exact number that
was tested. Selection is a SPIKE: it appears at precisely the tested
value and decays either side.

So the rule is swept across a grid instead of evaluated at its own
setting, at three slippage assumptions, with the no-rule baseline and a
RANDOM-direction control alongside.

Output: research/LEVELRIDE_BE.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TGT, STP = 260.0, 80.0
HOLD_S = 4 * 3600
PT, FEES = 2.0, 1.50
MAXC = 3
ENTRY_LO, ENTRY_HI = 14.0, 20.73
FLAT_H = 20 + 55 / 60.0
OFFS = [0., 25., -25., 50., -50., 75., -75., 100., -100., 150., -150.]
BE_MINS = [0, 20, 30, 40]          # 0 = rule off
BE_PTS = [30., 40., 50., 60.]
SLIPS = [0.25, 1.0]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def sim(sec, px, hrs, slip, be_min, be_pt, rng, randomise=False):
    n = len(px)
    i0 = int(np.searchsorted(hrs, ENTRY_LO))
    if i0 >= n:
        return []
    anchor = float(px[i0])
    levels = [anchor + o for o in OFFS]
    armed = [True] * len(levels)
    pos = {}
    out = []
    events = []
    for li, lev in enumerate(levels):
        d = px - lev
        s = np.sign(d)
        s[s == 0] = 1
        ch = np.flatnonzero(s[i0 + 1:] != s[i0:-1]) + i0 + 1
        for k in ch:
            events.append((int(k), li, 1 if px[k] > lev else -1))
    events.sort()
    ei = 0
    for k in range(i0, n):
        h = hrs[k]
        p = float(px[k])
        for li in list(pos.keys()):
            q = pos[li]
            s = q["side"]
            age = sec[k] - q["t"]
            # favourable excursion so far, in points
            q["mfe"] = max(q["mfe"], (p - q["entry"]) * s)
            # the rule: past be_min minutes without be_pt of favourable
            # movement, the stop comes to the entry price
            stp = q["entry"] - STP * s
            if be_min and age >= be_min * 60 and q["mfe"] < be_pt:
                stp = q["entry"]
            tgt = q["entry"] + TGT * s
            if (p - stp) * s <= 0:
                # GAP-AWARE. You get the WORSE of the stop level and the
                # market. This matters most the moment the breakeven
                # rule fires: if the trade is already 50 points under
                # water at minute 20, moving the stop "to entry" does
                # not let you exit at entry -- that price is behind the
                # market and there is nobody there. Booking it at entry
                # turned a -$100 loss into -$2 and made a driftless
                # random walk print +$43/day, which is impossible.
                ex = min(p, stp) if s > 0 else max(p, stp)
                out.append(((ex - slip * s - q["entry"]) * s * PT - FEES,
                            "stop"))
                del pos[li]
                armed[li] = True
            elif (p - tgt) * s >= 0:
                out.append(((tgt - q["entry"]) * s * PT - FEES, "target"))
                del pos[li]
                armed[li] = True
            elif age >= HOLD_S:
                out.append(((p - slip * s - q["entry"]) * s * PT - FEES,
                            "timer"))
                del pos[li]
                armed[li] = True
        if h >= FLAT_H:
            for li in list(pos.keys()):
                q = pos[li]
                s = q["side"]
                out.append(((p - slip * s - q["entry"]) * s * PT - FEES,
                            "eod"))
                del pos[li]
            break
        while ei < len(events) and events[ei][0] <= k:
            kk, li, side = events[ei]
            ei += 1
            if kk < k or not armed[li] or li in pos or len(pos) >= MAXC:
                continue
            if not (ENTRY_LO <= h < ENTRY_HI):
                continue
            if randomise:
                side = 1 if rng.random() < 0.5 else -1
            pos[li] = {"side": side, "entry": levels[li] + slip * side,
                       "t": sec[k], "mfe": -1e9}
            armed[li] = False
    return out


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {}
    days = 0
    rng = np.random.default_rng(9)
    for cn in cons:
        ts, pxr, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, pxr = ts[o_], pxr[o_]
        idx = pd.to_datetime(ts)
        s1 = pd.Series(pxr, index=idx).resample("1s").last().ffill()
        allsec = s1.index.view(np.int64) // 10**9
        allpx = s1.values.astype(np.float64)
        allhrs = (s1.index.hour + s1.index.minute / 60.0
                  + s1.index.second / 3600.0).values
        dow = s1.index.dayofweek.values
        dayid = allsec // 86400
        for d in np.unique(dayid):
            m = (dayid == d) & (dow < 5) & (allhrs >= ENTRY_LO - 0.1) \
                & (allhrs <= FLAT_H + 0.1)
            if m.sum() < 3600:
                continue
            sec, px, hrs = allsec[m], allpx[m], allhrs[m]
            days += 1
            for slip in SLIPS:
                for bm in BE_MINS:
                    bps = [0.] if bm == 0 else BE_PTS
                    for bp in bps:
                        for who in ("real", "RANDOM"):
                            r = sim(sec, px, hrs, slip, bm, bp, rng,
                                    randomise=(who == "RANDOM"))
                            a = acc.setdefault((slip, bm, bp, who),
                                               {"p": 0.0, "n": 0,
                                                "w": 0, "dd": 0.0,
                                                "eq": 0.0, "pk": 0.0})
                            for pnl, _rs in r:
                                a["p"] += pnl
                                a["n"] += 1
                                a["w"] += 1 if pnl > 0 else 0
                                a["eq"] += pnl
                                a["pk"] = max(a["pk"], a["eq"])
                                a["dd"] = min(a["dd"], a["eq"] - a["pk"])
        del ts, pxr, s1
        gc.collect()
        print(f"{cn} done ({days} days)", flush=True)

    log("# Does the time-based breakeven stop actually work?")
    log()
    log("The claim: pull the stop to breakeven if a trade is not "
        "+40-60pt favourable by minute 30, and LEVELRIDE goes from "
        "$32/day to $129/day with half the drawdown.")
    log()
    log("On a martingale every stopping rule has the same expectancy, so "
        "an exit rule cannot invent edge. A 4x gain means either real "
        "negative autocorrelation in losing trades -- a genuine, "
        "tradable finding -- or selection, since four rules were tried "
        "and one won.")
    log()
    log("Those are distinguishable. **A real effect is a plateau**: it "
        "holds at 20, 30 and 40 minutes and across 30-60 points, because "
        "nothing in the market knows which number was tested. "
        "**Selection is a spike** at exactly the tested value. So the "
        "rule is swept, not evaluated at its own setting.")
    log()
    log(f"NQ, 8 quarters, {days} sessions, 1-second resolution, "
        f"${FEES:.2f} round trip, 11-rung deployed ladder.")
    log()
    for slip in SLIPS:
        log(f"## entry slippage {slip:.2f} pt")
        log()
        log("| BE rule | trades/day | win % | $/trade | **$/day** | "
            "max DD | RANDOM $/day |")
        log("|" + "---|" * 7)
        for bm in BE_MINS:
            bps = [0.] if bm == 0 else BE_PTS
            for bp in bps:
                a = acc.get((slip, bm, bp, who := "real"))
                r = acc.get((slip, bm, bp, "RANDOM"))
                if not a or not a["n"]:
                    continue
                lbl = "OFF (baseline)" if bm == 0 else \
                    f"{bm}min / {bp:.0f}pt"
                log(f"| {lbl} | {a['n']/max(days,1):.1f} | "
                    f"{a['w']/a['n']:.1%} | ${a['p']/a['n']:+.2f} | "
                    f"**${a['p']/max(days,1):+,.0f}** | "
                    f"${a['dd']:,.0f} | "
                    f"${r['p']/max(days,1):+,.0f} |" if r else "")
        log()
    log("## Reading it")
    log()
    log("Compare every BE row with the OFF row at the same slippage. If "
        "the improvement holds across the whole grid it is real and it "
        "is the user's finding. If it appears only at one cell it is the "
        "four-rules-one-winner problem. And compare with the RANDOM "
        "column: a stop rule that also improves random-direction trades "
        "is managing exposure, not exploiting anything about the entry.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "LEVELRIDE_BE.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/LEVELRIDE_BE.md")


if __name__ == "__main__":
    main()

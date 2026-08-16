"""LEVELRIDE-LADDER, run against real tick data.

This is the strategy currently DEPLOYED and taking orders. It is
structurally different from the fade in the one way that matters, so it
deserves a real test rather than an inherited verdict.

WHY IT MIGHT SURVIVE WHERE THE FADE DID NOT

The fade died because ~3 points of entry error hit a 5-POINT stop -- 60%
of the risk gone before the trade started. LEVELRIDE's stop is 80
POINTS. The same 3 points is 3.75% of the risk. Wide stops are robust to
fill error; tight stops are not. That is a difference in kind.

Its entry is also triggered BY the crossing, in real time, so the level
is where price actually is at that instant. The fade computed a level
from a completed bar, by which time price had already left. That was the
whole disease.

WHAT IS UNDER TEST

  entry = lev + ADVERSE_PT * side

The engine books a resting stop as filling at its trigger price plus one
tick. A stop becomes a MARKET order when touched and fills at the next
available price, which can be worse. With an 80-point stop this should
barely matter -- but "should" is what the fade also had, so it is run at
0.25pt (the engine's assumption), 1pt and 2pt of entry slippage.

TWO LADDERS, because they are not the same strategy:

  deployed   OFFS = [0, +-25, +-50, +-75, +-100, +-150]   -- 11 rungs,
             what bot/levelride_engine.py actually runs
  dossier    OFFS = [0, +20, -20]                          -- 3 rungs,
             what the +$2,471/week backtest describes

CONTROL: the same crossings taken in a RANDOM direction. A breakout
system that cannot beat a coin flip on its own trigger events has no
directional edge, only exposure.

Faithful to the engine: anchor at the first price from 14:00 UTC, rungs
arm once and re-arm after their trade closes, 3 concurrent maximum,
target +260 / stop -80, 4-hour timer, flat at 20:55, $1.50 round trip,
$2/point, weekdays only.

Output: research/LEVELRIDE_TEST.md
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
LADDERS = {
    "deployed 11-rung": [0., 25., -25., 50., -50., 75., -75.,
                         100., -100., 150., -150.],
    "dossier 3-rung": [0., 20., -20.],
}
SLIPS = [0.25, 1.0, 2.0]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def sim(sec, px, hrs, offs, slip, rng, randomise=False):
    """One day. Returns list of (pnl, reason)."""
    n = len(px)
    i0 = int(np.searchsorted(hrs, ENTRY_LO))
    if i0 >= n:
        return []
    anchor = float(px[i0])
    levels = [anchor + o for o in offs]
    armed = [True] * len(levels)
    pos = {}
    out = []

    # vectorised crossing events per level, then replayed in time order
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
        # ---- exits first, exactly as the engine orders them
        for li in list(pos.keys()):
            q = pos[li]
            s = q["side"]
            tgt = q["entry"] + TGT * s
            stp = q["entry"] - STP * s
            if (p - stp) * s <= 0:
                out.append(((stp - slip * s - q["entry"]) * s * PT - FEES,
                            "stop"))
                del pos[li]
                armed[li] = True
            elif (p - tgt) * s >= 0:
                out.append(((tgt - q["entry"]) * s * PT - FEES, "target"))
                del pos[li]
                armed[li] = True
            elif sec[k] - q["t"] >= HOLD_S:
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
        # ---- entries
        while ei < len(events) and events[ei][0] <= k:
            kk, li, side = events[ei]
            ei += 1
            if kk < k or not armed[li] or li in pos or len(pos) >= MAXC:
                continue
            if not (ENTRY_LO <= h < ENTRY_HI):
                continue
            if randomise:
                side = 1 if rng.random() < 0.5 else -1
            entry = levels[li] + slip * side
            pos[li] = {"side": side, "entry": entry, "t": sec[k]}
            armed[li] = False
    return out


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {}
    days = 0
    rng = np.random.default_rng(5)
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
            for lname, offs in LADDERS.items():
                for slip in SLIPS:
                    for who in ("real", "RANDOM"):
                        r = sim(sec, px, hrs, offs, slip, rng,
                                randomise=(who == "RANDOM"))
                        a = acc.setdefault((lname, slip, who),
                                           {"p": 0.0, "n": 0, "t": 0,
                                            "w": 0})
                        a["p"] += sum(x[0] for x in r)
                        a["n"] += len(r)
                        a["t"] += sum(1 for x in r if x[1] == "target")
                        a["w"] += sum(1 for x in r if x[0] > 0)
        del ts, pxr, s1
        gc.collect()
        print(f"{cn} done ({days} days)", flush=True)

    log("# LEVELRIDE-LADDER against real tick data")
    log()
    log("The strategy currently deployed and taking orders. It is "
        "structurally different from the fade in the way that matters: "
        "the fade died because ~3 points of entry error hit a **5-point "
        "stop**. LEVELRIDE's stop is **80 points**, so the same error is "
        "3.75% of the risk instead of 60%. Its entry is also triggered "
        "BY the crossing in real time, so the level is where price "
        "actually is -- the fade computed its level from a finished bar, "
        "by which time price had left.")
    log()
    log(f"NQ, 8 quarters, {days} sessions, 1-second resolution (finer "
        f"than the bot's ~2s polling), ${FEES:.2f} round trip, "
        f"${PT:.0f}/point, target +{TGT:.0f} / stop -{STP:.0f}, 4-hour "
        f"timer, flat at 20:55, 3 concurrent maximum.")
    log()
    log("**Two ladders, because they are not the same strategy.** The "
        "deployed code runs 11 rungs at 0/+-25/+-50/+-75/+-100/+-150. "
        "The +$2,471/week backtest describes 3 rungs at 0/+-20.")
    log()
    log("| ladder | entry slip | side | trades/day | win % | target % | "
        "**$/trade** | **$/week** |")
    log("|" + "---|" * 8)
    for lname in LADDERS:
        for slip in SLIPS:
            for who in ("real", "RANDOM"):
                a = acc.get((lname, slip, who))
                if not a or not a["n"]:
                    continue
                n = a["n"]
                star = "**" if who == "real" else ""
                log(f"| {lname} | {slip:.2f} pt | {who} | "
                    f"{n/max(days,1):.1f} | {a['w']/n:.1%} | "
                    f"{a['t']/n:.1%} | {star}${a['p']/n:+.2f}{star} | "
                    f"{star}${a['p']/max(days,1)*5:+,.0f}{star} |")
    log()
    log("## Reading it")
    log()
    log("The claim is +$2,471/week at 63.9% wins. Compare the real rows "
        "with their RANDOM twin at the same ladder and slippage: a "
        "breakout system that cannot beat a coin flip on its own trigger "
        "events has no directional edge, only exposure. And compare the "
        "0.25pt row with the 2pt row -- if they are close, the wide stop "
        "really has made this robust to fill error, which is the "
        "structural claim being made for it.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "LEVELRIDE_TEST.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/LEVELRIDE_TEST.md")


if __name__ == "__main__":
    main()

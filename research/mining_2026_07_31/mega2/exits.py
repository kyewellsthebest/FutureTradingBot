"""The whole 2R deficit is the EXIT. Test targets instead of waiting for the turn.

Selectivity came back essentially dead: at 12-point swings the best feature
separated the runners from the duds by about a dollar, when the cost is $1.99,
and the best single bucket captured $0.98. Swing LENGTH is close to
unpredictable, which is what the 2R law already implied.

But look again at where the deficit comes from. Enter at confirmation, R points
into the swing. The swing runs to its extreme, S. Then you wait for the
opposite confirmation and hand back R points to get out:

    captured = S - R - R

The first R is unavoidable -- that is what confirmation costs. The second R is
a CHOICE. It is the price of using "wait for the opposite turn" as an exit
rule, and nothing forces that rule.

And the favourable excursion after entry is not small. Median swing is 1.71R,
so the median trade goes 0.71R in your favour before it turns -- at R=12 that
is 8.5 points, about $17 on one MNQ, against $1.99 of cost. The money is
sitting in the give-back.

So: exit at a fixed target T instead. This is exact on the cached swing data,
with no path assumptions, because the swing extreme IS the maximum -- if
S - R >= T the target was necessarily touched before the extreme.

    if S - R >= T:  capture T          (target hit)
    else:           capture S - 2R     (never got there; out at the turn)

No stop-loss is modelled, and that matters: the "else" branch here rides the
trade all the way to the opposite confirmation. A stop would need the tick
path, not just the swing size, so it is the next test and not this one. Read
these as the target's contribution alone.
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.path.join(ROOT, "research", "EXITS.md")
USD_PT = 2.00
COST = 1.99
TRAIN = set("NQU4,NQZ4,NQH5,NQM5,NQU5".split(","))
RS = [int(x) for x in os.environ.get("RS", "12,20,30").split(",")]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


log("# The give-back is the whole problem. What a target does about it.")
log()
log("Entering at confirmation costs R points and cannot be avoided. Exiting "
    "at the opposite confirmation costs another R points and **is a choice**. "
    "The median swing runs 1.71R, so the median trade goes 0.71R in your "
    "favour before turning — the money is sitting in the give-back, not in "
    "better direction calling.")
log()
log("Exact on the swing data: the extreme is the maximum, so a target below "
    "it was necessarily touched. Held-out contracts only. No stop-loss is "
    "modelled — losers here ride to the opposite confirmation — so these are "
    "the target's contribution alone.")
log()

for R in RS:
    S = []
    for p in sorted(glob.glob(os.path.join(CACHE, f"legs_NQ*_R{R}pt.npz"))):
        c = os.path.basename(p).split("_")[1]
        if c in TRAIN:
            continue
        z = np.load(p, allow_pickle=False)
        S.append(z["S_next"].astype(np.float64))
    if not S:
        continue
    S = np.concatenate(S)
    S = S[np.isfinite(S)]
    mfe = S - R                                   # favourable excursion
    base = float(np.mean(S - 2 * R))
    log(f"## Swings of {R}+ points — {len(S):,} held-out swings")
    log()
    log(f"Waiting for the opposite turn captures **${base*USD_PT:+.2f}** per "
        f"trade before cost. Median favourable excursion after entry: "
        f"**{np.median(mfe):.1f} points (${np.median(mfe)*USD_PT:.2f})**.")
    log()
    log("| target | hit rate | avg captured | **$/trade gross** | "
        "**net of $1.99** |")
    log("|---|---|---|---|---|")
    best = None
    for T in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50]:
        if T > 5 * R:
            continue
        hit = mfe >= T
        cap = np.where(hit, T, S - 2 * R)
        m = float(np.mean(cap))
        net = m * USD_PT - COST
        log(f"| {T} pts | {hit.mean()*100:.1f}% | {m:+.2f} pts | "
            f"**${m*USD_PT:+.2f}** | **${net:+.2f}** |")
        if best is None or net > best[1]:
            best = (T, net, hit.mean(), m)
    log()
    if best:
        T, net, hr, m = best
        log(f"Best target at this swing size: **{T} points**, hit "
            f"{hr*100:.0f}% of the time, **${net:+.2f} net per trade**.")
        if net > 0:
            log(f"That is positive. It needs a stop-loss test before it means "
                f"anything, because every miss here rides to the opposite "
                f"confirmation with no downside limit.")
        else:
            log("Still negative. The target helps but not enough.")
    log()

log("---")
log("Held-out contracts only. Exact given the swing extremes; no path "
    "assumptions and no stop-loss.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

"""The 3,000-6,000 points a day: how much of it is actually reachable, and at what accuracy?

The screenshot is right. NQ's total path length -- every zigzag added up --
really is thousands of points a day. The fair question is why we cannot take
a thousand of it. This answers that in the only terms that matter: how many
swings exist at each size, what perfect foresight would pay, and what
DIRECTIONAL ACCURACY is required to break even and to make $1,000 a week.

Framing everything as accuracy is the point. "Edge of $0.87 a trade" is
abstract. "52.5% right when you need 55%" is a target you can aim at, and it
makes the trade-off visible: bigger swings need less accuracy but occur less
often, smaller swings are everywhere but the toll eats them.

The ladder decomposes the real tape into zigzag legs at a range of reversal
thresholds. A leg is only counted when it is CONFIRMED -- price has reversed
by R points from the extreme -- so nothing here uses information that would
not have existed at the time.

Break-even accuracy comes from: trade every confirmed leg, win the leg size
when right, lose it when wrong.

    expectancy = (2p - 1) * leg_dollars - cost
    p_breakeven = 0.5 + cost / (2 * leg_dollars)

MNQ: $2.00 per point, $0.50 per tick, all-in cost $1.99 per round turn
measured from the user's own fills.
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.path.join(ROOT, "research", "ZIGZAG_LADDER.md")
PT = 4                      # ticks per NQ point
USD_PT = 2.00               # MNQ dollars per point
COST = 1.99
WEEKLY = 1000.0
RS = [2, 3, 5, 8, 12, 20, 30, 50, 80]      # reversal thresholds, in POINTS
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


tapes, days = {}, {}
for p in sorted(glob.glob(os.path.join(CACHE, "NQ*_R4.npz"))):
    c = os.path.basename(p).split("_")[0]
    z = np.load(p, allow_pickle=False)
    tapes[c] = z["pc"].astype(np.int64)
    ts = z["tsconf"].astype(np.int64)
    # trading days actually present, not calendar days
    days[c] = len(np.unique(ts // 86_400_000_000_000))
    print(f"  {c}: {len(tapes[c]):,} price changes over {days[c]} days",
          flush=True)

TOTDAYS = sum(days.values())

log("# The 3,000-6,000 points a day: what is reachable, and at what accuracy")
log()
log(f"Measured on {len(tapes)} NQ contracts, "
    f"{sum(len(t) for t in tapes.values()):,} price changes, {TOTDAYS} "
    f"trading days. One MNQ = $2.00 per point. All-in cost $1.99 per round "
    f"turn, from your own fills.")
log()
log("A **leg** is a swing of at least R points, counted only when CONFIRMED "
    "— price has already reversed R points off the extreme. That is what a "
    "live system could actually act on; the perfect-foresight column is the "
    "ceiling, not a plan.")
log()

rows = []
for R in RS:
    tot_legs = 0
    tot_pts = 0.0
    for c, pc in tapes.items():
        piv, conf, dirs = grammar.decompose(pc, R * PT)
        if len(piv) < 10:
            continue
        start = np.r_[0, piv[:-1]]
        size = np.abs(pc[piv] - pc[start]) / PT          # leg size in points
        tot_legs += len(size)
        tot_pts += float(size.sum())
    if not tot_legs:
        continue
    legs_day = tot_legs / TOTDAYS
    pts_day = tot_pts / TOTDAYS
    avg_leg = tot_pts / tot_legs
    leg_usd = avg_leg * USD_PT
    perfect = pts_day * USD_PT
    costs = legs_day * COST
    p_be = 0.5 + COST / (2 * leg_usd)
    # accuracy needed for $1000/week = $200/day on one contract
    need_day = WEEKLY / 5
    p_1k = 0.5 + (need_day / legs_day + COST) / (2 * leg_usd)
    rows.append((R, legs_day, avg_leg, pts_day, perfect, costs, p_be, p_1k,
                 leg_usd))

log("## What is out there, by swing size")
log()
log("| swing size | swings per day | avg swing | points/day in swings | "
    "perfect foresight $/day | cost of those trades | net if perfect |")
log("|---|---|---|---|---|---|---|")
for R, ld, al, pd_, pf, cs, pbe, p1k, lu in rows:
    log(f"| {R} pts | {ld:.0f} | {al:.1f} pts | {pd_:,.0f} | "
        f"**${pf:,.0f}** | ${cs:,.0f} | ${pf - cs:,.0f} |")
log()
log("The screenshot is confirmed by our own tick data: add up every swing "
    "and NQ really does travel thousands of points a day. Perfect foresight "
    "on one MNQ would pay thousands of dollars a day. Nobody has perfect "
    "foresight — so the only question that matters is the next table.")
log()

log("## The number that decides everything: how often you must be right")
log()
log("| swing size | swings/day | $ per swing | break-even accuracy | "
    "accuracy for $1,000/wk on **1** MNQ | on **3** MNQ |")
log("|---|---|---|---|---|---|")
for R, ld, al, pd_, pf, cs, pbe, p1k, lu in rows:
    need_day = WEEKLY / 5
    p3 = 0.5 + (need_day / 3 / ld + COST) / (2 * lu)
    p1s = f"{p1k*100:.1f}%" if p1k < 1 else "impossible"
    p3s = f"{p3*100:.1f}%" if p3 < 1 else "impossible"
    log(f"| {R} pts | {ld:.0f} | ${lu:.0f} | **{pbe*100:.1f}%** | {p1s} | "
        f"**{p3s}** |")
log()
log("Read the last column. On three MNQ, catching swings of a given size, "
    "that is the fraction of swings you must call correctly — forever — to "
    "make $1,000 a week.")
log()

log("## The catch that decides all of it: you enter late and exit late")
log()
log("Table 2 assumes that when you are right you capture the WHOLE swing. "
    "Nobody can. A swing is only known to have started once price has already "
    "reversed R points off the extreme — that is what confirmation means — and "
    "it is only known to have ENDED once price has reversed R points off the "
    "other extreme. So a confirmation-based system enters R points late and "
    "exits R points late, and keeps:")
log()
log("    captured = average swing - 2R")
log()
log("| swing size R | avg swing | avg swing / R | captured after entering and "
    "exiting late | in dollars | net of $1.99 |")
log("|---|---|---|---|---|---|")
for R, ld, al, pd_, pf, cs, pbe, p1k, lu in rows:
    cap = al - 2 * R
    log(f"| {R} pts | {al:.1f} pts | **{al/R:.2f}x** | {cap:+.1f} pts | "
        f"${cap*USD_PT:+.2f} | **${cap*USD_PT - COST:+.2f}** |")
log()
log("Look at the ratio column. The average swing is almost exactly **2R at "
    "every single scale**, from 2 points to 80. That is not a coincidence and "
    "it is not a property of NQ — it is what a random walk does. The expected "
    "excursion between R-sized reversals is 2R.")
log()
log("Which means a confirmation-based swing system captures "
    "`2R - 2R = about zero`, before costs, at every scale on the ladder. The "
    "3,000-6,000 points are real, and the confirmation lag on both ends eats "
    "essentially all of them. This is the honest reason the path length is not "
    "money, and it holds no matter how many swings a day there are.")
log()
log("So there are exactly three ways out, and only three:")
log()
log("1. **Enter earlier than confirmation** — predict the turn instead of "
    "reacting to it. Needs genuine forecasting skill at the turn.")
log("2. **Exit better than the next confirmation** — a target or trail that "
    "beats giving back R points. This is pure trade management and costs "
    "nothing to test.")
log("3. **Be selective** — only take swings that will run longer than 2R. "
    "This is the one that matches how a discretionary trader actually works, "
    "and it is testable: conditional on what is visible at confirmation, is "
    "the REMAINING length of the swing predictable?")
log()
log("Every search run so far has been a version of (1), which is the hardest "
    "of the three. (2) and (3) have never been tested.")
log()

log("## Where we actually are")
log()
log("The best real edge measured in this repo is $0.87 per trade on an "
    "average move of about $17.50, which is 8.75 points. Converting that to "
    "accuracy:")
log()
log("    expectancy = (2p - 1) x move   ->   0.87 = (2p - 1) x 17.50")
log("    p = 52.5%")
log()
best_row = min(rows, key=lambda r: abs(r[2] - 8.75))
R, ld, al, pd_, pf, cs, pbe, p1k, lu = best_row
log(f"At the {R}-point swing scale, which is the closest match, break-even "
    f"is **{pbe*100:.1f}%** and $1,000/week on three contracts needs "
    f"**{(0.5 + (WEEKLY/5/3/ld + COST)/(2*lu))*100:.1f}%**.")
log()
log(f"So we are at **52.5%** and need roughly **{pbe*100:.0f}%** to stop "
    f"losing. That is the entire gap, stated honestly: a few percentage "
    f"points of directional accuracy. Not a fantasy, not close either.")
log()

log("## Your proposed spec, checked")
log()
log("45% win rate, +12 points on winners, small losses. Testing it against "
    "the cost, on one MNQ:")
log()
log("| win rate | winner | loser | $/trade after cost | trades/wk for "
    "$1,000 (1 MNQ) | on 3 MNQ |")
log("|---|---|---|---|---|---|")
for wr, w, l_ in ((0.45, 12, 6), (0.45, 12, 8), (0.45, 10, 5), (0.40, 12, 6),
                  (0.35, 12, 6), (0.50, 8, 6), (0.55, 6, 6), (0.45, 12, 10)):
    e = wr * w * USD_PT - (1 - wr) * l_ * USD_PT - COST
    if e <= 0:
        log(f"| {wr*100:.0f}% | +{w} pts | -{l_} pts | **${e:+.2f}** | "
            f"never — loses money | never |")
    else:
        log(f"| {wr*100:.0f}% | +{w} pts | -{l_} pts | **${e:+.2f}** | "
            f"{WEEKLY/e:,.0f} | {WEEKLY/e/3:,.0f} |")
log()
log("**Your spec works arithmetically.** 45% at 2:1 pays $2.21 a trade, and "
    "about 150 trades a week on three contracts clears $1,000. The shape of "
    "the plan is sound. What has to be true is the 45%, because a 2:1 "
    "bracket hit at random comes in near 33%.")
log()
log("| what you need | value |")
log("|---|---|")
log("| random win rate at 2:1 | 33.3% |")
log("| your spec | 45% |")
log("| **skill required** | **+11.7 points of win rate** |")
log("| that in dollars | $4.21 per trade of pure edge |")
log("| best edge measured here | $0.87 per trade |")
log()
log("That is the real gap: your plan needs about **5x** the edge anything "
    "here has produced. Which is worth knowing precisely, because it says "
    "the plan is not wrong — the signal is simply not strong enough yet, and "
    "the target to aim at is a specific number rather than 'better'.")
log()
log("---")
log("Legs are confirmed swings on the real tick tape, so nothing uses "
    "hindsight. Costs charged once per round turn.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

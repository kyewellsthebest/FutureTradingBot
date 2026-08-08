"""What does $1,000 a week actually require? In the units everything is measured in.

Every result in this repo is reported as dollars per trade. The goal is
reported as dollars per week. Nobody has written down the bridge, which means
no result has ever been judged against the actual target -- only against
break-even, which is a much lower bar and the reason a $0.87 edge could feel
close.

This computes the bridge from measured numbers only:

  required gross edge per trade = (weekly target / (trades x contracts)) + cost

and then places it against what the market actually offers, so the required
edge is expressed as a share of a typical move over the matching holding
period -- because THAT is the number a search has to beat, and it is
comparable to the cost-to-move ratios in COST_RATIO.md.

Two constraints are applied that dollars alone hide:

  MARGIN. Micro index futures need roughly $50-100 of day-trade margin per
  contract at most brokers, but the real constraint on $4,100 is not margin,
  it is drawdown. A strategy whose measured max drawdown is D per contract
  cannot be run at N contracts unless N x D leaves the account alive. This
  prints the drawdown budget per contract at each size.

  FREQUENCY IS NOT FREE. Non-overlapping trades are bounded by holding
  period: you cannot take 500 trades a week each held 30 minutes, because a
  week only contains about 6,900 minutes of RTH-plus-overnight tape. The
  table marks combinations that are arithmetically impossible.

Nothing here is a prediction. It is the specification a candidate must meet.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import megatick as mt  # noqa: E402

OUT = os.path.join(mt.ROOT, "research", "TARGET_MATH.md")
WEEKLY = float(os.environ.get("WEEKLY", "1000"))
ACCOUNT = float(os.environ.get("ACCOUNT", "4100"))
# measured on MNQ from the user's own fills: $0.74 commission + 2.5 ticks
COST = mt.COMM + mt.SLIP_TICKS * 0.50
# NQ average absolute move by window, measured in COST_RATIO.md on NQM5.
# These scale as a random walk (x2.26 over 5x time against sqrt(5)=2.24,
# x2.39 over 6x against 2.45), which is the check that they belong to one
# series -- an earlier draft mixed two runs and had the 5-minute move larger
# than the 30-minute one.
MOVE = {1: 36.08, 5: 81.46, 30: 194.91, 120: 370.91}
MINUTES_PER_WEEK = 6900          # ~23h x 5 days of tradeable tape
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


log("# What $1,000 a week actually requires")
log()
log(f"Every result in this repo is stated as dollars per trade; the goal is "
    f"stated as dollars per week. This is the bridge, built only from "
    f"measured numbers: MNQ all-in cost **${COST:.2f}** per round turn "
    f"($0.74 commission plus 2.5 ticks, from your own fills) and NQ's own "
    f"average absolute move by window.")
log()
log("Until now every candidate was judged against break-even, which is a far "
    "lower bar than the target and is why an edge of $0.87 a trade could feel "
    "close to working. It was close to break-even. It was nowhere near "
    f"${WEEKLY:,.0f} a week.")
log()

log("## Required GROSS dollars per trade")
log()
log(f"To clear ${WEEKLY:,.0f}/week, one micro contract, before asking whether "
    f"it is achievable:")
log()
NS = [50, 100, 200, 350, 500, 750, 1000]
CS = [1, 2, 4, 8]
log("| trades/week | " + " | ".join(f"{c} micro{'s' if c > 1 else ''}"
                                    for c in CS) + " |")
log("|" + "---|" * (len(CS) + 1))
for n in NS:
    cells = []
    for c in CS:
        need = WEEKLY / (n * c) + COST
        cells.append(f"${need:,.2f}")
    log(f"| {n} | " + " | ".join(cells) + " |")
log()
log(f"Read a cell as: every trade must make this much gross, on average, "
    f"forever, before costs are taken out. The ${COST:.2f} toll is already "
    f"included.")
log()

log("## Is that edge available? Required edge as a share of a typical move")
log()
log("A trade held H minutes has a typical absolute move to work with. The "
    "required gross edge is shown as a percentage of it — directly comparable "
    "to the cost-to-move ratios in COST_RATIO.md, and to the 0.87 dollars the "
    "leg-grammar cell actually delivered.")
log()
log("| trades/week | hold implied | typical NQ move | required gross (1 "
    "micro) | as % of the move | required (4 micros) | as % |")
log("|---|---|---|---|---|---|---|")
for n in NS:
    hold_min = MINUTES_PER_WEEK / n
    w = min(MOVE, key=lambda k: abs(k - hold_min))
    mv = MOVE[w]
    n1 = WEEKLY / n + COST
    n4 = WEEKLY / (n * 4) + COST
    log(f"| {n} | {hold_min:.0f} min | ${mv:.0f} (at {w} min) | "
        f"${n1:,.2f} | **{n1/mv*100:.0f}%** | ${n4:,.2f} | "
        f"**{n4/mv*100:.0f}%** |")
log()
log("The hold column is the maximum average holding time consistent with that "
    "trade count on a single position — a week holds about "
    f"{MINUTES_PER_WEEK:,} minutes of tape, so more trades necessarily means "
    "shorter holds and less move to capture. That is the vice: raising "
    "frequency to reach the target shrinks the very thing being captured.")
log()

log("## The drawdown constraint, which binds before margin does")
log()
log(f"On ${ACCOUNT:,.0f}, size is limited by survivable drawdown, not by "
    f"margin. If a strategy's measured worst peak-to-trough is D per "
    f"contract, running N contracts risks N x D:")
log()
log("| contracts | drawdown budget per contract at 25% of account | "
    "at 50% |")
log("|---|---|---|")
for c in CS:
    log(f"| {c} | ${ACCOUNT * 0.25 / c:,.0f} | ${ACCOUNT * 0.50 / c:,.0f} |")
log()
log("For scale: the leg-grammar cell's measured max drawdown was **$10,836 "
    "per micro**. At one contract that is 2.6x the entire account. No size "
    "makes it survivable, which is why it was closed on the equity curve "
    "rather than on its mean.")
log()

log("## The specification")
log()
best = 0.87
log(f"The largest genuine, control-adjusted edge measured anywhere in this "
    f"repo is **${best:.2f} per trade** (the NQ leg-grammar cell, versus a "
    f"matched control). Against that:")
log()
for n, c in ((200, 4), (350, 4), (500, 4), (500, 8)):
    need = WEEKLY / (n * c) + COST
    log(f"- {n} trades/week on {c} micros needs **${need:,.2f}** gross per "
        f"trade — **{need/best:.1f}x** the best edge ever measured here")
log()
log("So the honest specification is not 'find an edge'. Edges have been "
    "found, three times, and all were real. The specification is: **find an "
    "edge roughly three to five times larger than anything measured so far, "
    "or reduce the toll enough to change the arithmetic.** Those are "
    "different projects, and only the second one has a known lever — bond "
    "tick data, where the tick is worth $15.62 to $31.25 against the same "
    "$0.74 commission.")
log()
log("---")
log(f"Costs measured from your own Tradovate fills. NQ move sizes measured "
    f"from tick data in COST_RATIO.md. Weekly target ${WEEKLY:,.0f}, account "
    f"${ACCOUNT:,.0f}.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

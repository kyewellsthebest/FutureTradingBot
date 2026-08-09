# The 3,000-6,000 points a day: what is reachable, and at what accuracy

Measured on 8 NQ contracts, 137,417,879 price changes, 623 trading days. One MNQ = $2.00 per point. All-in cost $1.99 per round turn, from your own fills.

A **leg** is a swing of at least R points, counted only when CONFIRMED — price has already reversed R points off the extreme. That is what a live system could actually act on; the perfect-foresight column is the ceiling, not a plan.

## What is out there, by swing size

| swing size | swings per day | avg swing | points/day in swings | perfect foresight $/day | cost of those trades | net if perfect |
|---|---|---|---|---|---|---|
| 2 pts | 11098 | 4.4 pts | 48,880 | **$97,760** | $22,085 | $75,674 |
| 3 pts | 5674 | 6.4 pts | 36,426 | **$72,852** | $11,292 | $61,560 |
| 5 pts | 2327 | 10.4 pts | 24,181 | **$48,362** | $4,632 | $43,731 |
| 8 pts | 985 | 16.3 pts | 16,045 | **$32,090** | $1,960 | $30,130 |
| 12 pts | 458 | 24.1 pts | 11,036 | **$22,072** | $911 | $21,161 |
| 20 pts | 168 | 40.0 pts | 6,718 | **$13,436** | $334 | $13,102 |
| 30 pts | 75 | 60.2 pts | 4,485 | **$8,971** | $148 | $8,822 |
| 50 pts | 27 | 100.8 pts | 2,702 | **$5,403** | $53 | $5,350 |
| 80 pts | 10 | 163.5 pts | 1,688 | **$3,376** | $21 | $3,355 |

The screenshot is confirmed by our own tick data: add up every swing and NQ really does travel thousands of points a day. Perfect foresight on one MNQ would pay thousands of dollars a day. Nobody has perfect foresight — so the only question that matters is the next table.

## The number that decides everything: how often you must be right

| swing size | swings/day | $ per swing | break-even accuracy | accuracy for $1,000/wk on **1** MNQ | on **3** MNQ |
|---|---|---|---|---|---|
| 2 pts | 11098 | $9 | **61.3%** | 61.4% | **61.3%** |
| 3 pts | 5674 | $13 | **57.8%** | 57.9% | **57.8%** |
| 5 pts | 2327 | $21 | **54.8%** | 55.0% | **54.9%** |
| 8 pts | 985 | $33 | **53.1%** | 53.4% | **53.2%** |
| 12 pts | 458 | $48 | **52.1%** | 52.5% | **52.2%** |
| 20 pts | 168 | $80 | **51.2%** | 52.0% | **51.5%** |
| 30 pts | 75 | $120 | **50.8%** | 51.9% | **51.2%** |
| 50 pts | 27 | $202 | **50.5%** | 52.3% | **51.1%** |
| 80 pts | 10 | $327 | **50.3%** | 53.3% | **51.3%** |

Read the last column. On three MNQ, catching swings of a given size, that is the fraction of swings you must call correctly — forever — to make $1,000 a week.

## The catch that decides all of it: you enter late and exit late

Table 2 assumes that when you are right you capture the WHOLE swing. Nobody can. A swing is only known to have started once price has already reversed R points off the extreme — that is what confirmation means — and it is only known to have ENDED once price has reversed R points off the other extreme. So a confirmation-based system enters R points late and exits R points late, and keeps:

    captured = average swing - 2R

| swing size R | avg swing | avg swing / R | captured after entering and exiting late | in dollars | net of $1.99 |
|---|---|---|---|---|---|
| 2 pts | 4.4 pts | **2.20x** | +0.4 pts | $+0.81 | **$-1.18** |
| 3 pts | 6.4 pts | **2.14x** | +0.4 pts | $+0.84 | **$-1.15** |
| 5 pts | 10.4 pts | **2.08x** | +0.4 pts | $+0.78 | **$-1.21** |
| 8 pts | 16.3 pts | **2.04x** | +0.3 pts | $+0.58 | **$-1.41** |
| 12 pts | 24.1 pts | **2.01x** | +0.1 pts | $+0.23 | **$-1.76** |
| 20 pts | 40.0 pts | **2.00x** | +0.0 pts | $+0.02 | **$-1.97** |
| 30 pts | 60.2 pts | **2.01x** | +0.2 pts | $+0.39 | **$-1.60** |
| 50 pts | 100.8 pts | **2.02x** | +0.8 pts | $+1.50 | **$-0.49** |
| 80 pts | 163.5 pts | **2.04x** | +3.5 pts | $+7.05 | **$+5.06** |

Look at the ratio column. The average swing is almost exactly **2R at every single scale**, from 2 points to 80. That is not a coincidence and it is not a property of NQ — it is what a random walk does. The expected excursion between R-sized reversals is 2R.

Which means a confirmation-based swing system captures `2R - 2R = about zero`, before costs, at every scale on the ladder. The 3,000-6,000 points are real, and the confirmation lag on both ends eats essentially all of them. This is the honest reason the path length is not money, and it holds no matter how many swings a day there are.

So there are exactly three ways out, and only three:

1. **Enter earlier than confirmation** — predict the turn instead of reacting to it. Needs genuine forecasting skill at the turn.
2. **Exit better than the next confirmation** — a target or trail that beats giving back R points. This is pure trade management and costs nothing to test.
3. **Be selective** — only take swings that will run longer than 2R. This is the one that matches how a discretionary trader actually works, and it is testable: conditional on what is visible at confirmation, is the REMAINING length of the swing predictable?

Every search run so far has been a version of (1), which is the hardest of the three. (2) and (3) have never been tested.

## Where we actually are

The best real edge measured in this repo is $0.87 per trade on an average move of about $17.50, which is 8.75 points. Converting that to accuracy:

    expectancy = (2p - 1) x move   ->   0.87 = (2p - 1) x 17.50
    p = 52.5%

At the 5-point swing scale, which is the closest match, break-even is **54.8%** and $1,000/week on three contracts needs **54.9%**.

So we are at **52.5%** and need roughly **55%** to stop losing. That is the entire gap, stated honestly: a few percentage points of directional accuracy. Not a fantasy, not close either.

## Your proposed spec, checked

45% win rate, +12 points on winners, small losses. Testing it against the cost, on one MNQ:

| win rate | winner | loser | $/trade after cost | trades/wk for $1,000 (1 MNQ) | on 3 MNQ |
|---|---|---|---|---|---|
| 45% | +12 pts | -6 pts | **$+2.21** | 452 | 151 |
| 45% | +12 pts | -8 pts | **$+0.01** | 100,000 | 33,333 |
| 45% | +10 pts | -5 pts | **$+1.51** | 662 | 221 |
| 40% | +12 pts | -6 pts | **$+0.41** | 2,439 | 813 |
| 35% | +12 pts | -6 pts | **$-1.39** | never — loses money | never |
| 50% | +8 pts | -6 pts | **$+0.01** | 100,000 | 33,333 |
| 55% | +6 pts | -6 pts | **$-0.79** | never — loses money | never |
| 45% | +12 pts | -10 pts | **$-2.19** | never — loses money | never |

**Your spec works arithmetically.** 45% at 2:1 pays $2.21 a trade, and about 150 trades a week on three contracts clears $1,000. The shape of the plan is sound. What has to be true is the 45%, because a 2:1 bracket hit at random comes in near 33%.

| what you need | value |
|---|---|
| random win rate at 2:1 | 33.3% |
| your spec | 45% |
| **skill required** | **+11.7 points of win rate** |
| that in dollars | $4.21 per trade of pure edge |
| best edge measured here | $0.87 per trade |

That is the real gap: your plan needs about **5x** the edge anything here has produced. Which is worth knowing precisely, because it says the plan is not wrong — the signal is simply not strong enough yet, and the target to aim at is a specific number rather than 'better'.

---
Legs are confirmed swings on the real tick tape, so nothing uses hindsight. Costs charged once per round turn.

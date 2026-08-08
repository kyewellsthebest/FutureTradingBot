# What $1,000 a week actually requires

Every result in this repo is stated as dollars per trade; the goal is stated as dollars per week. This is the bridge, built only from measured numbers: MNQ all-in cost **$1.99** per round turn ($0.74 commission plus 2.5 ticks, from your own fills) and NQ's own average absolute move by window.

Until now every candidate was judged against break-even, which is a far lower bar than the target and is why an edge of $0.87 a trade could feel close to working. It was close to break-even. It was nowhere near $1,000 a week.

## Required GROSS dollars per trade

To clear $1,000/week, one micro contract, before asking whether it is achievable:

| trades/week | 1 micro | 2 micros | 4 micros | 8 micros |
|---|---|---|---|---|
| 50 | $21.99 | $11.99 | $6.99 | $4.49 |
| 100 | $11.99 | $6.99 | $4.49 | $3.24 |
| 200 | $6.99 | $4.49 | $3.24 | $2.62 |
| 350 | $4.85 | $3.42 | $2.70 | $2.35 |
| 500 | $3.99 | $2.99 | $2.49 | $2.24 |
| 750 | $3.32 | $2.66 | $2.32 | $2.16 |
| 1000 | $2.99 | $2.49 | $2.24 | $2.12 |

Read a cell as: every trade must make this much gross, on average, forever, before costs are taken out. The $1.99 toll is already included.

## Is that edge available? Required edge as a share of a typical move

A trade held H minutes has a typical absolute move to work with. The required gross edge is shown as a percentage of it — directly comparable to the cost-to-move ratios in COST_RATIO.md, and to the 0.87 dollars the leg-grammar cell actually delivered.

| trades/week | hold implied | typical NQ move | required gross (1 micro) | as % of the move | required (4 micros) | as % |
|---|---|---|---|---|---|---|
| 50 | 138 min | $371 (at 120 min) | $21.99 | **6%** | $6.99 | **2%** |
| 100 | 69 min | $195 (at 30 min) | $11.99 | **6%** | $4.49 | **2%** |
| 200 | 34 min | $195 (at 30 min) | $6.99 | **4%** | $3.24 | **2%** |
| 350 | 20 min | $195 (at 30 min) | $4.85 | **2%** | $2.70 | **1%** |
| 500 | 14 min | $81 (at 5 min) | $3.99 | **5%** | $2.49 | **3%** |
| 750 | 9 min | $81 (at 5 min) | $3.32 | **4%** | $2.32 | **3%** |
| 1000 | 7 min | $81 (at 5 min) | $2.99 | **4%** | $2.24 | **3%** |

The hold column is the maximum average holding time consistent with that trade count on a single position — a week holds about 6,900 minutes of tape, so more trades necessarily means shorter holds and less move to capture. That is the vice: raising frequency to reach the target shrinks the very thing being captured.

## The drawdown constraint, which binds before margin does

On $4,100, size is limited by survivable drawdown, not by margin. If a strategy's measured worst peak-to-trough is D per contract, running N contracts risks N x D:

| contracts | drawdown budget per contract at 25% of account | at 50% |
|---|---|---|
| 1 | $1,025 | $2,050 |
| 2 | $512 | $1,025 |
| 4 | $256 | $512 |
| 8 | $128 | $256 |

For scale: the leg-grammar cell's measured max drawdown was **$10,836 per micro**. At one contract that is 2.6x the entire account. No size makes it survivable, which is why it was closed on the equity curve rather than on its mean.

## The specification

The largest genuine, control-adjusted edge measured anywhere in this repo is **$0.87 per trade** (the NQ leg-grammar cell, versus a matched control). Against that:

- 200 trades/week on 4 micros needs **$3.24** gross per trade — **3.7x** the best edge ever measured here
- 350 trades/week on 4 micros needs **$2.70** gross per trade — **3.1x** the best edge ever measured here
- 500 trades/week on 4 micros needs **$2.49** gross per trade — **2.9x** the best edge ever measured here
- 500 trades/week on 8 micros needs **$2.24** gross per trade — **2.6x** the best edge ever measured here

So the honest specification is not 'find an edge'. Edges have been found, three times, and all were real. The specification is: **find an edge roughly three to five times larger than anything measured so far, or reduce the toll enough to change the arithmetic.** Those are different projects, and only the second one has a known lever — bond tick data, where the tick is worth $15.62 to $31.25 against the same $0.74 commission.

---
Costs measured from your own Tradovate fills. NQ move sizes measured from tick data in COST_RATIO.md. Weekly target $1,000, account $4,100.

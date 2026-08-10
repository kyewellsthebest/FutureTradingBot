# The search with the toll switched off

Every row of the previous study lost money, which answers *can we afford it* and buries *is it there*. Those have different fixes: a big gross edge eaten by costs is an execution problem, a small gross edge everywhere is still a search problem. So this ranks on gross and reports the number that converts straight back —

> **gross $ per round turn = the cost we would have to pay for this to work.** We pay $1.99.

Horizons run from 1 to 500 bars (~147 seconds to ~20 hours). Positions are **non-overlapping** — one at a time, the way one account works — and filtered to the most confident top q% of predictions, so the output is in trades per week and dollars per trade.

**The shuffled column is not optional here.** Taking the best 0.2% of 293,000 predictions is a selection procedure, and selection invents edge from noise exactly as reliably as it finds it in signal. Every threshold is run identically on a model trained against scrambled outcomes. Read the pair; the real number alone means nothing.

## The best gross-per-trade anywhere in the space

| data | horizon | selectivity | trades/week | **gross $/trade** | same cut, shuffled | net $/week at $1.99 |
|---|---|---|---|---|---|---|
| + macro complex (CL/GC/HG) | 500 bars | top 1% | 1 | **$+15.28** | $-5.33 | $+18 |
| + macro complex (CL/GC/HG) | 500 bars | top 2% | 2 | **$+13.93** | $-0.84 | $+22 |
| + NQ order flow | 500 bars | top 0.2% | 1 | **$+13.66** | $+13.11 | $+6 |
| all four types | 500 bars | top 10% | 4 | **$+13.55** | $+6.27 | $+43 |
| + NQ order flow | 500 bars | top 1% | 2 | **$+13.49** | $+6.70 | $+19 |
| + NQ order flow | 500 bars | top 50% | 5 | **$+13.22** | $+6.92 | $+52 |
| everything EXCEPT price path | 500 bars | top 50% | 5 | **$+12.62** | $+4.61 | $+49 |
| all four types | 100 bars | top 0.2% | 1 | **$+11.91** | $+3.54 | $+7 |
| + index complex (ES/YM/RTY) | 500 bars | top 10% | 4 | **$+11.15** | $+11.18 | $+35 |
| + macro complex (CL/GC/HG) | 500 bars | top 10% | 4 | **$+10.91** | $-7.88 | $+32 |
| all four types | 500 bars | top 5% | 3 | **$+10.78** | $+10.74 | $+27 |
| price path only | 500 bars | top 1% | 2 | **$+10.47** | $-2.74 | $+13 |
| + NQ order flow | 500 bars | top 5% | 3 | **$+10.35** | $+4.41 | $+27 |
| + NQ order flow | 500 bars | top 2% | 2 | **$+10.27** | $+9.75 | $+19 |
| + index complex (ES/YM/RTY) | 500 bars | top 20% | 4 | **$+10.26** | $-0.78 | $+36 |
| price path only | 500 bars | top 2% | 2 | **$+10.14** | $-11.71 | $+18 |
| + index complex (ES/YM/RTY) | 500 bars | top 1% | 1 | **$+10.01** | $+7.08 | $+12 |
| all four types | 500 bars | top 20% | 4 | **$+9.96** | $-8.38 | $+34 |
| all four types | 200 bars | top 5% | 6 | **$+9.06** | $+0.33 | $+40 |
| everything EXCEPT price path | 500 bars | top 2% | 3 | **$+8.66** | $+11.35 | $+18 |

## Gross per trade against horizon

At a fixed, undemanding selectivity — the top 10% of signals — so the trend is not confounded by how hard each row is cherry-picking.

| horizon | price path only | + NQ order flow | + index complex (ES/YM/RTY) | + macro complex (CL/GC/HG) | all four types | everything EXCEPT price path |
|---|---|---|---|---|---|---|
| 1 bars (2 min) | $+0.09 | $+0.10 | $+0.10 | $+0.05 | $+0.16 | $+0.08 |
| 2 bars (5 min) | $+0.14 | $+0.22 | $+0.22 | $+0.08 | $+0.08 | $+0.04 |
| 5 bars (12 min) | $+0.38 | $+0.28 | $+0.22 | $+0.23 | $+0.12 | $+0.02 |
| 10 bars (24 min) | $+0.92 | $+0.57 | $+0.34 | $+0.30 | $+0.17 | $+0.13 |
| 20 bars (49 min) | $+0.85 | $+0.24 | $+0.24 | $+0.54 | $+0.57 | $-0.02 |
| 50 bars (2.0 h) | $+0.10 | $+1.86 | $+0.63 | $+1.38 | $-0.09 | $-0.83 |
| 100 bars (4.1 h) | $+0.28 | $-0.59 | $+2.28 | $+1.66 | $+0.92 | $-1.81 |
| 200 bars (8.2 h) | $+2.47 | $-0.03 | $+3.68 | $-0.42 | $+4.33 | $+0.85 |
| 500 bars (20.4 h) | $+5.61 | $+6.96 | $+11.15 | $+10.91 | $+13.55 | $+2.63 |

Read down a column. If gross-per-trade keeps climbing with horizon and only crosses $1.99 out at the long end, then the edge is real but slow, and high frequency is the thing making it unaffordable rather than the thing making it work.

_Ran in 42 min._

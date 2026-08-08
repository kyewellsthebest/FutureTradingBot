# Trading the confirmed cell: one position at a time, against a control

Signals are taken in chronological order; any signal that fires while a trade is open is skipped. The control takes the SAME number of trades in the same contract with the same hold, entering at random — identical exposure, no timing. Costs are charged once per round turn.

## 1. Non-overlapping, and against random entries with the same exposure

| hold | trades (holdout) | HOLDOUT gross $/trade | random entries | same signals slid down the tape | edge over the harder control | net @ $1.75 |
|---|---|---|---|---|---|---|
| 200 | 11,480 | **$+0.72** | $-0.00 | $+0.08 | **$+0.64** | $-1.03 |
| 400 | 10,619 | **$+1.07** | $+0.31 | $+0.36 | **$+0.70** | $-0.68 |
| 700 | 9,773 | **$+1.00** | $+0.08 | $+0.03 | **$+0.92** | $-0.75 |
| 1000 | 9,176 | **$+1.11** | $+0.39 | $+0.15 | **$+0.72** | $-0.64 |
| 1500 | 8,345 | **$+0.43** | $+0.43 | $+0.17 | **$+0.01** | $-1.32 |
| 2500 | 7,103 | **$+0.84** | $+1.50 | $+0.54 | **$-0.66** | $-0.91 |
| 4000 | 5,795 | **$+0.88** | $+1.54 | $+1.19 | **$-0.66** | $-0.87 |
| 8000 | 4,005 | **$+2.74** | $+2.06 | $+3.17 | **$-0.42** | $+0.99 |
| 16000 | 2,488 | **$+2.45** | $+1.65 | $+4.08 | **$-1.63** | $+0.70 |

The **difference** column is the one that matters. Gross dollars at a long hold are mostly exposure; only the gap over random entries with the same exposure is timing, and only timing is repeatable.

## 2. The account's experience at hold 700

### cost $1.75/round turn, one micro contract

| metric | value |
|---|---|
| trades | 9,773 over 232 days (42.1/day) |
| win rate | 48.2% |
| expectancy | **$-0.75** per trade |
| avg winner / loser | $+27.77 / $-27.27 |
| **average day** | **$-31.62** |
| positive days | 85/232 (37%) |
| average winning / losing day | $+175.05 / $-151.12 |
| best day / **WORST day** | $+793.00 / **$-834.25** |
| **average week** | **$-183.39** |
| positive weeks | 14/40 |
| avg winning / losing week | $+517.45 / $-560.77 |
| best week / **WORST week** | $+1924.50 / **$-1458.25** |
| max drawdown | $-8526.00 |
| longest losing streak | 12 trades |
| contracts for $1,000/wk | not reachable — weekly average is negative |

### cost $2.00/round turn, one micro contract

| metric | value |
|---|---|
| trades | 9,773 over 232 days (42.1/day) |
| win rate | 47.6% |
| expectancy | **$-1.00** per trade |
| avg winner / loser | $+27.88 / $-27.20 |
| **average day** | **$-42.15** |
| positive days | 82/232 (35%) |
| average winning / losing day | $+171.12 / $-158.74 |
| best day / **WORST day** | $+774.00 / **$-858.00** |
| **average week** | **$-244.47** |
| positive weeks | 13/40 |
| avg winning / losing week | $+492.85 / $-599.48 |
| best week / **WORST week** | $+1804.50 / **$-1575.50** |
| max drawdown | $-10836.50 |
| longest losing streak | 12 trades |
| contracts for $1,000/wk | not reachable — weekly average is negative |

---
Held-out contracts only. Day and week boundaries are UTC. The random control uses a fixed seed so the comparison is reproducible.

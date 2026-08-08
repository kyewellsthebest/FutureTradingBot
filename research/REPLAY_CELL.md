# Trading the confirmed cell: one position at a time, against a control

Signals are taken in chronological order; any signal that fires while a trade is open is skipped. The control takes the SAME number of trades in the same contract with the same hold, entering at random — identical exposure, no timing. Costs are charged once per round turn.

## 1. Non-overlapping, and against random entries with the same exposure

| hold | trades (holdout) | HOLDOUT gross $/trade | random-entry control $ | difference | net @ $1.75 | net @ $2.00 |
|---|---|---|---|---|---|---|
| 1000 | 9,176 | **$+1.11** | $+0.25 | **$+0.87** | $-0.64 | $-0.89 |
| 2500 | 7,103 | **$+0.84** | $+1.03 | **$-0.19** | $-0.91 | $-1.16 |
| 4000 | 5,795 | **$+0.88** | $+1.96 | **$-1.07** | $-0.87 | $-1.12 |
| 6000 | 4,715 | **$+1.37** | $+1.97 | **$-0.59** | $-0.38 | $-0.63 |
| 8000 | 4,005 | **$+2.74** | $+2.45 | **$+0.29** | $+0.99 | $+0.74 |
| 12000 | 3,057 | **$+4.49** | $+3.73 | **$+0.77** | $+2.74 | $+2.49 |
| 16000 | 2,488 | **$+2.45** | $+1.31 | **$+1.14** | $+0.70 | $+0.45 |

The **difference** column is the one that matters. Gross dollars at a long hold are mostly exposure; only the gap over random entries with the same exposure is timing, and only timing is repeatable.

## 2. The account's experience at hold 16000

### cost $1.75/round turn, one micro contract

| metric | value |
|---|---|
| trades | 2,488 over 217 days (11.5/day) |
| win rate | 50.8% |
| expectancy | **$+0.70** per trade |
| avg winner / loser | $+116.38 / $-118.56 |
| **average day** | **$+8.05** |
| positive days | 122/217 (56%) |
| average winning / losing day | $+358.23 / $-441.67 |
| best day / **WORST day** | $+2117.50 / **$-2035.50** |
| **average week** | **$+43.65** |
| positive weeks | 21/40 |
| avg winning / losing week | $+928.61 / $-934.46 |
| best week / **WORST week** | $+2950.75 / **$-2768.00** |
| max drawdown | $-8091.50 |
| longest losing streak | 9 trades |
| contracts for $1,000/wk | 23 micros |

### cost $2.00/round turn, one micro contract

| metric | value |
|---|---|
| trades | 2,488 over 217 days (11.5/day) |
| win rate | 50.6% |
| expectancy | **$+0.45** per trade |
| avg winner / loser | $+116.41 / $-118.52 |
| **average day** | **$+5.18** |
| positive days | 122/217 (56%) |
| average winning / losing day | $+355.66 / $-444.92 |
| best day / **WORST day** | $+2111.50 / **$-2042.50** |
| **average week** | **$+28.10** |
| positive weeks | 21/40 |
| avg winning / losing week | $+913.38 / $-950.37 |
| best week / **WORST week** | $+2937.00 / **$-2790.50** |
| max drawdown | $-8251.00 |
| longest losing streak | 10 trades |
| contracts for $1,000/wk | 36 micros |

---
Held-out contracts only. Day and week boundaries are UTC. The random control uses a fixed seed so the comparison is reproducible.

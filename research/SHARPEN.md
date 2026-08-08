# Sharpening the one real behaviour

31,587 instances of the confirmed cell across 8 NQ contracts, 13,782 of them in the three held-out ones. Every number is **net dollars per trade on one micro contract after the direction x contract x volume baseline** — the same correction that proved the behaviour is not drift. Choices are made on the training contracts; the HOLDOUT column is the answer.

## 1. Where does the money actually peak? (exit horizon)

| hold (price changes) | train $ | HOLDOUT $ | net @ $1.75 | net @ $2.00 |
|---|---|---|---|---|
| 25 | $+0.91 | **$+1.13** | $-0.62 | $-0.87 |
| 50 | $+0.76 | **$+0.80** | $-0.95 | $-1.20 |
| 100 | $+0.73 | **$+0.76** | $-0.99 | $-1.24 |
| 200 | $+0.70 | **$+0.97** | $-0.78 | $-1.03 |
| 400 | $+1.02 | **$+1.49** | $-0.26 | $-0.51 |
| 700 | $+1.22 | **$+1.54** | $-0.21 | $-0.46 |
| 1000 | $+1.40 | **$+1.52** | $-0.23 | $-0.48 |
| 1500 | $+1.90 | **$+1.37** | $-0.38 | $-0.63 |
| 2500 | $+2.35 | **$+2.13** | $+0.38 | $+0.13 |
| 4000 | $+3.73 | **$+2.56** | $+0.81 | $+0.56 |

Chosen on training data alone: **F = 4000**. Read the shape of the column rather than its maximum — a lone spike is a fitted number, a plateau is a real one.

## 2. Is the entry too early? (delay past confirmation)

| delay | train $ | HOLDOUT $ | n (holdout) | note |
|---|---|---|---|---|
| 0 | $+4.13 | **$+2.99** | 13,779 | bid-ask bounce still in it |
| 1 | $+3.73 | **$+2.56** | 13,779 | the audited entry |
| 2 | $+3.34 | **$+2.21** | 13,779 | -14% vs delay 1 |
| 5 | $+2.65 | **$+1.53** | 13,779 | -40% vs delay 1 |
| 10 | $+2.49 | **$+1.18** | 13,779 | -54% vs delay 1 |
| 25 | $+2.80 | **$+1.41** | 13,779 | -45% vs delay 1 |
| 50 | $+3.06 | **$+1.75** | 13,779 | -32% vs delay 1 |
| 100 | $+3.12 | **$+1.85** | 13,779 | -28% vs delay 1 |

This is the most valuable row in the file. If the edge is still there 25 or 50 price changes after confirmation, the behaviour is slow enough to enter with a resting limit order instead of crossing the spread — and not crossing is worth about a tick, which is $0.50, which is larger than the entire shortfall.

## 3. Does the edge concentrate in the extreme instances?

**dist_n** — how big the down-leg was

| quartile within the cell | n | train $ | HOLDOUT $ | net @ $1.75 |
|---|---|---|---|---|
| Q1 | 8,478 | $+3.29 | **$+2.17** | $+0.42 |
| Q2 | 7,516 | $+4.78 | **$+0.09** | $-1.66 |
| Q3 | 7,732 | $+2.71 | **$+0.79** | $-0.96 |
| Q4 | 7,851 | $+4.27 | **$+7.20** | $+5.45 |

**vel_n** — how fast it was

| quartile within the cell | n | train $ | HOLDOUT $ | net @ $1.75 |
|---|---|---|---|---|
| Q1 | 8,260 | $+1.01 | **$-0.27** | $-2.02 |
| Q2 | 8,039 | $+3.67 | **$+2.85** | $+1.10 |
| Q3 | 7,816 | $+7.25 | **$+3.46** | $+1.71 |
| Q4 | 7,462 | $+2.98 | **$+4.79** | $+3.04 |

**retr** — how deeply it retraced the prior leg

| quartile within the cell | n | train $ | HOLDOUT $ | net @ $1.75 |
|---|---|---|---|---|
| Q1 | 7,902 | $+2.70 | **$+4.40** | $+2.65 |
| Q2 | 7,676 | $+4.82 | **$+0.79** | $-0.96 |
| Q3 | 7,688 | $+0.88 | **$+0.30** | $-1.45 |
| Q4 | 8,311 | $+6.52 | **$+4.42** | $+2.67 |

**vol_n** — how thin the volume was — LOW is the cell

| quartile within the cell | n | train $ | HOLDOUT $ | net @ $1.75 |
|---|---|---|---|---|
| Q1 | 8,231 | $+1.33 | **$+2.75** | $+1.00 |
| Q2 | 8,068 | $+7.06 | **$+2.75** | $+1.00 |
| Q3 | 9,336 | $+2.46 | **$+3.47** | $+1.72 |
| Q4 | 5,942 | $+4.21 | **$+0.61** | $-1.14 |

## 4. Three attributes the original cell never looked at

| extra condition | n | train $ | HOLDOUT $ | net @ $1.75 |
|---|---|---|---|---|
| nchg_n above median (0.50) | 10,783 | $+3.41 | **$+0.49** | $-1.26 |
| nchg_n at or below median (0.50) | 20,794 | $+3.89 | **$+3.67** | $+1.92 |
| dur_n above median (0.28) | 16,301 | $+2.97 | **$+1.07** | $-0.68 |
| dur_n at or below median (0.28) | 15,276 | $+4.48 | **$+4.30** | $+2.55 |
| conf_lag above median (4.00) | 977 | $+4.20 | **$-2.12** | $-3.87 |
| conf_lag at or below median (4.00) | 30,600 | $+3.71 | **$+2.71** | $+0.96 |

## 5. So what would it pay per week?

| | value |
|---|---|
| signals, held-out contracts | 13,779 over 40 weeks |
| signals per week | 344.5 |
| holdout $/trade | **$+2.56** |
| **$/week at $1.75 cost, 1 micro** | **$+279** |
| **$/week at $2.00 cost, 1 micro** | **$+193** |
| contracts needed for $1,000/wk | 4 micros |

Signals overlap; a real account holds one position at a time, so true frequency is lower. This is the ceiling, not the forecast.

---
Nothing above re-searched anything. The behaviour was already found and already validated against drift; these are the trade-construction choices around it, made on training contracts and reported out of sample.

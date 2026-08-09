# Can we tell which swings will run? The selectivity test

The 2R law says the AVERAGE confirmed swing captures nothing. This asks whether swings differ from each other in a way that is visible at confirmation — which is exactly what a discretionary trader relies on when they skip the ordinary setups and take the ones that look like they will run. If the answer is yes, selection alone converts a zero into an edge with **no improvement in direction calling at all**.

Quintile edges come from the five training contracts. Every number below is from the three held-out ones. Beside each real spread is the same feature circularly shifted against the outcomes — same values, same distribution, no alignment. A feature only counts if it beats its shift.

## Swings of 12+ points

127,101 confirmed swings in the held-out contracts. Average captured after entering and exiting late: **+0.20 points ($+0.41)** against $1.99 of cost — the 2R law, restated on the holdout.

How fat is the tail? Swing length in multiples of R — median **1.71x**, 75th **2.42x**, 90th **3.33x**, 99th **5.60x**. Perfect selection of the top decile would capture **+16.0 points ($+32.00)** per trade. That is the prize if any feature can find them.

| feature | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | best-worst spread | SHIFTED spread |
|---|---|---|---|---|---|---|---|
| `retrace` | +0.50 | +0.98 | +0.40 | +0.26 | -0.10 | **$1.08** | $0.35 |
| `conf_secs` | -0.30 | +0.52 | +0.45 | +0.58 | +0.78 | **$1.08** | $0.16 |
| `leg_size` | +0.71 | +0.37 | +0.59 | +0.63 | -0.25 | **$0.96** | $0.24 |
| `leg_vol` | +0.45 | +0.68 | +0.71 | +0.40 | -0.23 | **$0.94** | $0.23 |
| `vol_regime` | +0.01 | +0.48 | +0.44 | +0.39 | +0.72 | **$0.70** | $0.09 |
| `two_back` | +0.27 | +0.42 | +0.52 | +0.12 | +0.72 | $0.60 | $0.39 |
| `leg_secs` | +0.14 | +0.71 | +0.36 | +0.46 | +0.34 | $0.58 | $0.49 |
| `leg_vol_per_pt` | +0.33 | +0.75 | +0.34 | +0.38 | +0.21 | $0.54 | $0.30 |
| `leg_speed` | +0.34 | +0.21 | +0.49 | +0.72 | +0.26 | **$0.51** | $0.07 |
| `conf_vol` | +0.52 | +0.66 | +0.41 | +0.18 | +0.26 | $0.49 | $0.37 |
| `conf_vs_leg_vol` | +0.23 | +0.26 | +0.68 | +0.46 | +0.41 | $0.45 | $0.41 |
| `conf_speed` | +0.34 | +0.22 | +0.66 | +0.44 | +0.36 | $0.44 | $0.33 |
| `conf_changes` | +0.36 | +0.45 | +0.66 | +0.23 | +0.34 | $0.43 | $0.33 |

Strongest separator: `leg_size`, spread $0.96 against a shifted spread of $0.24. Every cell is dollars captured per trade on one MNQ, BEFORE the $1.99 cost — so a quintile only pays if its number exceeds $1.99.

## Swings of 20+ points

47,208 confirmed swings in the held-out contracts. Average captured after entering and exiting late: **-0.07 points ($-0.13)** against $1.99 of cost — the 2R law, restated on the holdout.

How fat is the tail? Swing length in multiples of R — median **1.69x**, 75th **2.39x**, 90th **3.28x**, 99th **5.58x**. Perfect selection of the top decile would capture **+25.6 points ($+51.15)** per trade. That is the prize if any feature can find them.

| feature | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | best-worst spread | SHIFTED spread |
|---|---|---|---|---|---|---|---|
| `leg_vol_per_pt` | -1.47 | +0.06 | -0.01 | +0.36 | +0.42 | $1.89 | $1.18 |
| `conf_secs` | -0.71 | -0.20 | -0.71 | -0.03 | +1.05 | $1.76 | $1.08 |
| `leg_speed` | +0.34 | +0.46 | -0.13 | -0.13 | -1.21 | $1.67 | $1.55 |
| `leg_size` | +0.62 | +0.07 | +0.19 | -0.49 | -1.00 | **$1.62** | $0.51 |
| `conf_speed` | +0.45 | +0.43 | -0.38 | -0.25 | -0.91 | $1.36 | $0.93 |
| `conf_changes` | -0.91 | -0.25 | -0.39 | +0.44 | +0.45 | $1.36 | $0.93 |
| `leg_vol` | -0.93 | +0.28 | +0.40 | +0.00 | -0.37 | $1.33 | $0.98 |
| `leg_secs` | -0.59 | +0.61 | -0.54 | -0.64 | +0.56 | $1.25 | $1.84 |
| `conf_vol` | -0.94 | -0.45 | +0.22 | +0.22 | +0.30 | $1.23 | $0.89 |
| `conf_vs_leg_vol` | -0.32 | -0.82 | +0.36 | +0.13 | +0.03 | $1.18 | $1.44 |
| `retrace` | -0.20 | +0.49 | -0.25 | -0.48 | -0.23 | $0.96 | $0.76 |
| `vol_regime` | -0.53 | -0.34 | +0.41 | +0.03 | -0.17 | $0.93 | $1.52 |
| `two_back` | -0.01 | +0.25 | -0.27 | -0.22 | -0.37 | $0.62 | $0.99 |

Strongest separator: `leg_size`, spread $1.62 against a shifted spread of $0.51. Every cell is dollars captured per trade on one MNQ, BEFORE the $1.99 cost — so a quintile only pays if its number exceeds $1.99.

## Swings of 30+ points

20,980 confirmed swings in the held-out contracts. Average captured after entering and exiting late: **-0.05 points ($-0.11)** against $1.99 of cost — the 2R law, restated on the holdout.

How fat is the tail? Swing length in multiples of R — median **1.69x**, 75th **2.38x**, 90th **3.29x**, 99th **5.73x**. Perfect selection of the top decile would capture **+38.8 points ($+77.50)** per trade. That is the prize if any feature can find them.

| feature | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | best-worst spread | SHIFTED spread |
|---|---|---|---|---|---|---|---|
| `leg_secs` | +0.96 | -0.66 | -2.78 | +0.56 | +1.27 | $4.05 | $3.30 |
| `conf_vs_leg_vol` | +0.20 | +0.62 | -2.29 | -0.35 | +1.40 | $3.70 | $2.63 |
| `leg_speed` | +1.90 | -0.49 | -1.59 | +0.71 | -0.96 | **$3.49** | $1.49 |
| `two_back` | +1.91 | -0.42 | -1.32 | -0.72 | +0.15 | $3.24 | $1.93 |
| `conf_changes` | -2.01 | -0.53 | +1.14 | +0.95 | +0.09 | $3.15 | $2.44 |
| `conf_speed` | +0.08 | +0.95 | +1.11 | -0.50 | -2.01 | $3.12 | $2.49 |
| `conf_secs` | -0.61 | +0.02 | -1.40 | +0.13 | +1.38 | $2.78 | $2.59 |
| `conf_vol` | -1.65 | -0.90 | +0.92 | +1.13 | +0.17 | $2.78 | $4.01 |
| `leg_vol_per_pt` | -0.71 | +0.30 | -1.29 | -0.24 | +1.45 | $2.73 | $1.51 |
| `leg_vol` | -0.23 | -0.47 | -1.01 | -0.15 | +1.43 | $2.44 | $1.32 |
| `vol_regime` | +0.70 | -0.12 | +0.96 | -0.69 | -1.18 | $2.14 | $2.53 |
| `leg_size` | +0.70 | -0.11 | -0.30 | +0.57 | -1.26 | $1.96 | $1.35 |
| `retrace` | -0.56 | +0.22 | +0.59 | -0.88 | +0.09 | $1.48 | $2.39 |

Strongest separator: `leg_size`, spread $1.96 against a shifted spread of $1.35. Every cell is dollars captured per trade on one MNQ, BEFORE the $1.99 cost — so a quintile only pays if its number exceeds $1.99.

---
Swings are confirmation-anchored, so nothing uses hindsight. `captured` is swing size minus 2R, the real result of entering and exiting one confirmation late.

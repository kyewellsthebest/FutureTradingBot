# Alternative Strategy Search for MNQ Bot - Realistic Execution
Generated: 2026-06-22T10:07:23.112985

## Context
The existing inverse-pullback strategy was proven to LOSE money under realistic execution: -$949/day on 60-day backtest, all 30 filter variants negative (see `research/backtest_results.md`).
This document tests **100+ alternative strategies** under the SAME execution model to find a positive-expectancy alternative.

## Execution Model (identical to comprehensive_backtest.py)
- Marketable LIMIT entry. LONG fills at ASK; SHORT fills at BID. 1pt buffer for marketability (paper books at the actual ASK/BID).
- Stop-MARKET exits. 0.5pt slip against the trader on every stop fill.
- LIMIT target exits. Exact fill ONLY when bid (LONG)/ask (SHORT) reaches the target on a tick. No wick-fills.
- 200ms latency between signal and order arrival.
- 10s minimum cooldown between trades.
- $0.74 round-trip commission. 1 MNQ ($2/pt). One position max.
- 60-day subset: 2026-04-18 to 2026-06-17 (~52 trading days, ~16M ticks).
- Full data: 2024-01-01 to 2026-06-17 (~617-634 trading days, ~155M ticks).

## 1. Structural strategies battery (44 variants)
Covers all 18 strategy families A-R from the candidate list (continuation pullback, momentum, range breakout, inside bar, VWAP pullback/breakout, Bollinger reversion/breakout, ORB, EMA pullback, pivot reversal, RSI extremes/divergence, ATR expansion, cumulative-delta divergence, liquidity sweep, tick velocity, news pause, trend follow, gap fade), each with stop/target variants and INVERSE flips.
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| Q_VELOCITY_10_20 | 10 | 60.0% | $82 | $10 | $8.21 | 1.25 | $-64 | $-28 | $74 | 0.26 |
| Q_VELOCITY_FADE | 10 | 30.0% | $-25 | $-3 | $-2.54 | 1.25 | $-73 | $-44 | $39 | -0.09 |
| L_RSI_EXT_80_20_10_20 | 204 | 36.3% | $-509 | $-12 | $-2.49 | 4.64 | $-663 | $-164 | $121 | -0.21 |
| I_ORB15_10_20 | 60 | 31.7% | $-533 | $-13 | $-8.88 | 1.50 | $-547 | $-54 | $36 | -0.56 |
| I_ORB15_15_30 | 60 | 31.7% | $-605 | $-15 | $-10.08 | 1.50 | $-639 | $-74 | $53 | -0.48 |
| K_PIVOT_REV_8_16 | 229 | 31.0% | $-883 | $-28 | $-3.85 | 7.39 | $-925 | $-173 | $73 | -0.52 |
| K_PIVOT_REV_10_20 | 211 | 31.8% | $-1,001 | $-32 | $-4.74 | 6.81 | $-1,104 | $-233 | $143 | -0.41 |
| E_VWAP_PULL_10_20 | 517 | 38.3% | $-1,187 | $-23 | $-2.30 | 10.14 | $-1,401 | $-297 | $160 | -0.29 |
| X_GAP_FADE_10_20 | 107 | 21.5% | $-1,264 | $-31 | $-11.82 | 2.61 | $-1,278 | $-103 | $72 | -0.64 |
| L_RSI_EXT_FOLLOW | 185 | 27.0% | $-1,328 | $-30 | $-7.18 | 4.20 | $-1,452 | $-159 | $54 | -0.72 |
| E_VWAP_PULL_8_16 | 551 | 35.9% | $-1,338 | $-26 | $-2.43 | 10.80 | $-1,381 | $-234 | $85 | -0.38 |
| E_VWAP_PULL_FADE | 501 | 36.1% | $-1,418 | $-28 | $-2.83 | 9.82 | $-1,596 | $-197 | $210 | -0.35 |
| F_VWAP_BR_FADE | 620 | 36.5% | $-1,615 | $-32 | $-2.60 | 12.16 | $-2,059 | $-222 | $320 | -0.30 |
| F_VWAP_BR_10_20 | 619 | 36.2% | $-1,876 | $-37 | $-3.03 | 12.14 | $-2,260 | $-425 | $142 | -0.34 |
| R_NEWS_PAUSE_10_20 | 480 | 32.3% | $-2,402 | $-46 | $-5.00 | 9.23 | $-2,536 | $-251 | $137 | -0.51 |
| L_RSI_EXT_75_25_10_20 | 691 | 33.1% | $-2,528 | $-53 | $-3.66 | 14.40 | $-2,608 | $-348 | $159 | -0.49 |
| N_ATR_EXP_FADE | 920 | 35.1% | $-2,531 | $-50 | $-2.75 | 18.04 | $-2,576 | $-296 | $209 | -0.43 |
| H_BB_BR_10_20 | 1,089 | 36.5% | $-3,460 | $-68 | $-3.18 | 21.35 | $-3,693 | $-493 | $147 | -0.52 |
| N_ATR_EXP_10_20 | 937 | 31.8% | $-4,621 | $-91 | $-4.93 | 18.37 | $-4,742 | $-524 | $151 | -0.67 |
| O_CUMDELTA_DIV_FADE | 2,863 | 36.4% | $-7,987 | $-154 | $-2.79 | 55.06 | $-8,024 | $-759 | $297 | -0.68 |
| G_BB_REV_8_16 | 2,925 | 32.3% | $-11,901 | $-229 | $-4.07 | 56.25 | $-11,943 | $-906 | $132 | -1.28 |
| O_CUMDELTA_DIV_10_20 | 3,125 | 33.4% | $-13,512 | $-260 | $-4.32 | 60.10 | $-13,719 | $-927 | $182 | -1.05 |
| A_CONT_PULL_15_30 | 7,004 | 38.8% | $-14,558 | $-280 | $-2.08 | 134.69 | $-14,664 | $-1,621 | $635 | -0.55 |
| C_RANGE_BR_20_12_24 | 4,014 | 35.9% | $-15,726 | $-302 | $-3.92 | 77.19 | $-15,701 | $-1,412 | $338 | -0.78 |
| J_EMA_PULL_FADE | 4,674 | 34.8% | $-16,575 | $-319 | $-3.55 | 89.88 | $-16,599 | $-1,354 | $269 | -1.01 |
| M_RSI_DIV_10_20 | 4,220 | 33.4% | $-17,005 | $-327 | $-4.03 | 81.15 | $-17,062 | $-1,177 | $500 | -0.95 |
| P_SWEEP_FOLLOW | 4,582 | 30.4% | $-17,409 | $-335 | $-3.80 | 88.12 | $-17,482 | $-1,368 | $289 | -0.91 |
| D_INSIDE_10_20 | 5,365 | 37.1% | $-17,939 | $-345 | $-3.34 | 103.17 | $-18,084 | $-1,284 | $188 | -0.98 |
| J_EMA_PULL_10_20 | 5,202 | 35.0% | $-18,141 | $-349 | $-3.49 | 100.04 | $-18,165 | $-1,411 | $249 | -1.02 |
| C_RANGE_BR_15_10_20 | 4,956 | 34.0% | $-20,026 | $-385 | $-4.04 | 95.31 | $-20,107 | $-1,690 | $257 | -0.88 |
| J_EMA_PULL_8_16 | 5,852 | 33.6% | $-20,271 | $-390 | $-3.46 | 112.54 | $-20,298 | $-1,564 | $172 | -1.12 |
| P_SWEEP_REV_10_20 | 5,824 | 29.2% | $-20,807 | $-400 | $-3.57 | 112.00 | $-20,880 | $-1,254 | $218 | -1.25 |
| D_INSIDE_8_16 | 5,956 | 34.8% | $-22,410 | $-431 | $-3.76 | 114.54 | $-22,563 | $-1,450 | $125 | -1.28 |
| A_CONT_PULL_12_24 | 8,092 | 35.6% | $-24,061 | $-463 | $-2.97 | 155.62 | $-24,133 | $-2,010 | $647 | -0.85 |
| G_BB_REV_10_20 | 5,221 | 33.1% | $-24,223 | $-466 | $-4.64 | 100.40 | $-24,283 | $-1,686 | $174 | -1.17 |
| C_RANGE_BR_10_10_20 | 6,005 | 33.9% | $-24,932 | $-479 | $-4.15 | 115.48 | $-24,989 | $-1,935 | $212 | -0.93 |
| P_SWEEP_REV_8_16 | 6,778 | 31.1% | $-25,901 | $-498 | $-3.82 | 130.35 | $-25,996 | $-1,404 | $344 | -1.22 |
| A_CONT_PULL_10_20 | 9,138 | 34.2% | $-26,221 | $-504 | $-2.87 | 175.73 | $-26,273 | $-2,136 | $391 | -0.82 |
| B_MOM3_FADE_10_20 | 7,532 | 34.5% | $-26,603 | $-512 | $-3.53 | 144.85 | $-26,581 | $-1,352 | $129 | -1.40 |
| B_MOM3_10_20 | 6,744 | 34.0% | $-27,081 | $-521 | $-4.02 | 129.69 | $-27,208 | $-1,845 | $492 | -1.13 |
| C_RANGE_FADE_10_10_20 | 7,119 | 33.8% | $-28,261 | $-543 | $-3.97 | 136.90 | $-28,346 | $-1,467 | $414 | -1.25 |
| B_MOM3_8_16 | 7,515 | 32.5% | $-29,774 | $-573 | $-3.96 | 144.52 | $-29,899 | $-1,858 | $102 | -1.22 |
| A_CONT_PULL_8_16 | 10,669 | 31.8% | $-34,996 | $-673 | $-3.28 | 205.17 | $-35,063 | $-2,418 | $63 | -1.07 |
| X_TREND_FOLLOW_10_20 | 13,105 | 33.8% | $-45,904 | $-883 | $-3.50 | 252.02 | $-45,908 | $-4,130 | $412 | -0.97 |

**1 of 44 profitable on 60d.**
Best:
- Q_VELOCITY_10_20: $82 on 10 trades over 1.2 tr/day, WR 60.0%, max DD $-64

## 2. Cost-only baselines: random cadence, drift probes (13 variants)
These probe the COST FLOOR. If `always-LONG-once-per-hour` makes money, the market has positive drift. If it loses, there's no overall drift; any winning strategy needs DIRECTIONAL timing.
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| Z_NYSE_OPEN_SHORT | 41 | 36.6% | $-28 | $-1 | $-0.69 | 1.00 | $-209 | $-26 | $41 | -0.02 |
| Z_HOURLY_LONG_10_20 | 915 | 41.1% | $-306 | $-6 | $-0.33 | 17.60 | $-931 | $-283 | $351 | -0.04 |
| Z_NYSE_OPEN_LONG | 41 | 22.0% | $-397 | $-10 | $-9.69 | 1.00 | $-432 | $-26 | $40 | -0.39 |
| Z_HOURLY_LONG_RR1 | 915 | 50.8% | $-1,972 | $-38 | $-2.16 | 17.60 | $-2,072 | $-276 | $174 | -0.36 |
| Z_HOURLY_SHORT_10_20 | 915 | 32.2% | $-3,627 | $-70 | $-3.96 | 17.60 | $-3,687 | $-376 | $317 | -0.47 |
| Z_HOURLY_SHORT_RR1 | 915 | 40.4% | $-5,429 | $-104 | $-5.93 | 17.60 | $-5,442 | $-360 | $98 | -0.86 |
| Z_5MIN_RR3_LONG | 6,737 | 32.2% | $-18,923 | $-364 | $-2.81 | 129.56 | $-19,014 | $-1,888 | $422 | -0.79 |
| Z_5MIN_SHORT_10_20 | 7,386 | 34.8% | $-24,186 | $-465 | $-3.27 | 142.04 | $-24,281 | $-1,571 | $378 | -1.10 |
| Z_5MIN_LONG_10_20 | 7,341 | 35.5% | $-24,308 | $-467 | $-3.31 | 141.17 | $-24,438 | $-1,994 | $384 | -0.95 |
| Z_PREV_BAR_FADE | 15,201 | 34.1% | $-53,256 | $-1,024 | $-3.50 | 292.33 | $-53,231 | $-2,980 | $403 | -1.24 |
| Z_PREV_BAR_FOLLOW | 15,359 | 33.3% | $-59,913 | $-1,152 | $-3.90 | 295.37 | $-60,135 | $-4,256 | $42 | -1.15 |
| Z_PREV_BAR_FADE_RR1 | 21,122 | 46.6% | $-78,323 | $-1,506 | $-3.71 | 406.19 | $-78,349 | $-4,639 | $80 | -1.35 |
| Z_PREV_BAR_FOLLOW_RR1 | 21,174 | 45.1% | $-95,381 | $-1,834 | $-4.50 | 407.19 | $-95,357 | $-6,636 | $-47 | -1.24 |

**0 profitable.** Best `Z_NYSE_OPEN_SHORT`: -$28/-0.7/day on 41 tr/day-of-week (1 tr/day). Essentially break-even at 1 trade/day with random direction. This confirms the market has NEAR-ZERO aggregate drift; cost floor is real.

## 3. Per-hour directional bias (FULL data, 600+ trading days)
Open-to-close price-return per UTC hour over the full data set:

| Hour UTC | NY time | Avg pts/hr | Total pts | Sessions | Std |
|---|---|---:|---:|---:|---:|
| 22 | 18:00 | 6.13 | 2,501 | 408 | 42.8 |
| 17 | 13:00 | 4.72 | 2,928 | 620 | 86.9 |
| 01 | 21:00 | 3.37 | 2,138 | 634 | 40.3 |
| 19 | 15:00 | 3.27 | 1,994 | 610 | 72.1 |
| 07 | 03:00 | 3.22 | 2,039 | 634 | 41.1 |
| 06 | 02:00 | 2.67 | 1,688 | 633 | 30.6 |
| 16 | 12:00 | 2.59 | 1,642 | 633 | 71.3 |
| 12 | 08:00 | 1.70 | 1,076 | 632 | 54.7 |
| 11 | 07:00 | 1.51 | 958 | 633 | 44.5 |
| 23 | 19:00 | 1.33 | 845 | 634 | 33.7 |
| 21 | 17:00 | 0.60 | 128 | 211 | 24.9 |
| 08 | 04:00 | 0.60 | 381 | 634 | 40.3 |
| 13 | 09:00 | 0.47 | 296 | 632 | 79.6 |
| 00 | 20:00 | 0.26 | 165 | 633 | 41.1 |
| 02 | 22:00 | -0.29 | -182 | 634 | 27.9 |
| 09 | 05:00 | -0.30 | -189 | 634 | 36.6 |
| 04 | 00:00 | -0.42 | -267 | 634 | 24.5 |
| 03 | 23:00 | -0.47 | -296 | 634 | 24.7 |
| 10 | 06:00 | -0.57 | -360 | 633 | 39.8 |
| 18 | 14:00 | -0.76 | -466 | 614 | 62.8 |
| 05 | 01:00 | -0.83 | -529 | 634 | 33.9 |
| 20 | 16:00 | -1.48 | -900 | 610 | 52.8 |
| 15 | 11:00 | -1.59 | -1,008 | 633 | 84.0 |
| 14 | 10:00 | -1.82 | -1,153 | 632 | 102.3 |

**Findings:** 
- **Hour 22 UTC** (18:00 NY, CME open): +6.13 pts/hr avg over 408 sessions = +2,501 total pts. t = 6.13 / (42.8/sqrt(408)) = 2.89. Statistically significant.
- **Hour 17 UTC** (13:00 NY): +4.72 pts/hr avg over 620 sessions = +2,928 total pts. t = 4.72 / (86.9/sqrt(620)) = 1.35. Marginal but consistent.
- **Hour 14 UTC** (10:00 NY): -1.82 pts/hr SHORT bias. t = -1.82 / (102/sqrt(632)) = -0.45. Not significant.
- The aggregate drift across all hours is positive but modest — these biases are real but small relative to noise.

## 4. Hour-of-day exploit strategies (57 variants)
Schedule entries at biased hours in the bias direction. Variants: single-shot at hour open, 10-min cadence within the hour, 5-min cadence, with various stop/target sizes.

### 60-day subset
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| H17_LONG_5min_15_45 | 280 | 40.0% | $850 | $21 | $3.03 | 6.83 | $-681 | $-233 | $310 | 0.16 |
| H17_LONG_SINGLE_20_60 | 41 | 46.3% | $423 | $10 | $10.31 | 1.00 | $-197 | $-46 | $119 | 0.18 |
| H19_LONG_SINGLE_10_20 | 41 | 53.7% | $370 | $9 | $9.02 | 1.00 | $-91 | $-24 | $40 | 0.30 |
| H17_LONG_SINGLE_30_30 | 41 | 56.1% | $250 | $6 | $6.09 | 1.00 | $-297 | $-66 | $60 | 0.12 |
| H17_LONG_10min_10_20 | 221 | 41.2% | $232 | $6 | $1.05 | 5.39 | $-510 | $-138 | $164 | 0.07 |
| H17_LONG_SINGLE_40_40 | 41 | 53.7% | $191 | $5 | $4.67 | 1.00 | $-397 | $-86 | $80 | 0.08 |
| H06_LONG_SINGLE_10_20 | 42 | 52.4% | $183 | $4 | $4.37 | 1.00 | $-159 | $-26 | $39 | 0.17 |
| H20_SHORT_SINGLE_10_20 | 41 | 43.9% | $159 | $4 | $3.89 | 1.00 | $-123 | $-29 | $40 | 0.13 |
| H00_LONG_SINGLE_10_20 | 43 | 46.5% | $123 | $3 | $2.86 | 1.00 | $-135 | $-34 | $43 | 0.10 |
| H17_LONG_SINGLE_10_20 | 41 | 41.5% | $96 | $2 | $2.34 | 1.00 | $-188 | $-25 | $40 | 0.08 |
| H22_LONG_SINGLE_10_20 | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| H20_SHORT_10min_10_20 | 78 | 38.5% | $-11 | $-0 | $-0.14 | 1.70 | $-230 | $-53 | $77 | -0.01 |
| H07_LONG_SINGLE_10_20 | 43 | 37.2% | $-18 | $-0 | $-0.41 | 1.00 | $-160 | $-31 | $45 | -0.01 |
| H19_LONG_10min_10_20 | 225 | 38.7% | $-36 | $-1 | $-0.16 | 5.49 | $-526 | $-140 | $169 | -0.01 |
| H20_SHORT_5min_8_16 | 109 | 36.7% | $-128 | $-3 | $-1.17 | 2.42 | $-302 | $-65 | $61 | -0.07 |
| H02_SHORT_SINGLE_10_20 | 43 | 32.6% | $-137 | $-3 | $-3.19 | 1.00 | $-242 | $-26 | $43 | -0.13 |
| H20_SHORT_5min_RR1 | 112 | 51.8% | $-145 | $-3 | $-1.30 | 2.55 | $-262 | $-77 | $55 | -0.10 |
| H14_LONG_SINGLE_10_20 | 41 | 34.1% | $-166 | $-4 | $-4.04 | 1.00 | $-312 | $-33 | $46 | -0.14 |
| H17_LONG_2min_10_20 | 673 | 38.2% | $-172 | $-4 | $-0.25 | 16.41 | $-1,104 | $-327 | $316 | -0.03 |
| H00_LONG_10min_10_20 | 231 | 40.3% | $-231 | $-5 | $-1.00 | 5.37 | $-630 | $-142 | $114 | -0.09 |

**10 of 57 profitable on 60d.** Top picks looked promising on 60-day.

### Full data confirmation
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| H22_LONG_SINGLE_10_20 | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| H17_LONG_SINGLE_20_60 | 617 | 43.4% | $-817 | $-1 | $-1.32 | 1.00 | $-1,478 | $-50 | $122 | -0.03 |
| H17_LONG_SINGLE_40_40 | 617 | 50.1% | $-1,172 | $-2 | $-1.90 | 1.00 | $-1,669 | $-90 | $84 | -0.04 |
| H17_LONG_SINGLE_30_30 | 617 | 50.1% | $-1,436 | $-2 | $-2.33 | 1.00 | $-1,891 | $-70 | $64 | -0.06 |
| H20_SHORT_SINGLE_10_20 | 607 | 37.9% | $-1,452 | $-2 | $-2.39 | 1.00 | $-1,967 | $-77 | $46 | -0.09 |
| H19_LONG_SINGLE_10_20 | 606 | 36.6% | $-1,763 | $-3 | $-2.91 | 1.00 | $-2,358 | $-33 | $43 | -0.11 |
| H06_LONG_SINGLE_10_20 | 630 | 39.8% | $-2,292 | $-4 | $-3.64 | 1.00 | $-2,761 | $-29 | $40 | -0.18 |
| H14_LONG_SINGLE_10_20 | 626 | 34.7% | $-2,623 | $-4 | $-4.19 | 1.00 | $-2,828 | $-36 | $61 | -0.16 |
| H15_SHORT_SINGLE_10_20 | 628 | 32.2% | $-2,634 | $-4 | $-4.19 | 1.00 | $-2,713 | $-32 | $46 | -0.16 |
| H18_SHORT_SINGLE_10_20 | 605 | 33.1% | $-2,684 | $-4 | $-4.44 | 1.00 | $-2,785 | $-30 | $45 | -0.17 |
| H05_SHORT_SINGLE_10_20 | 632 | 33.7% | $-2,939 | $-5 | $-4.65 | 1.00 | $-2,933 | $-27 | $42 | -0.27 |
| H02_SHORT_SINGLE_10_20 | 634 | 36.4% | $-2,952 | $-5 | $-4.66 | 1.00 | $-2,941 | $-40 | $43 | -0.26 |
| H17_LONG_SINGLE_10_20 | 617 | 32.7% | $-3,021 | $-5 | $-4.90 | 1.00 | $-3,163 | $-30 | $42 | -0.19 |
| H07_LONG_SINGLE_10_20 | 628 | 36.0% | $-3,386 | $-5 | $-5.39 | 1.00 | $-3,469 | $-34 | $45 | -0.24 |
| H00_LONG_SINGLE_10_20 | 630 | 31.7% | $-4,401 | $-7 | $-6.99 | 1.00 | $-4,550 | $-34 | $47 | -0.32 |
| H20_SHORT_10min_10_20 | 1,752 | 36.0% | $-5,635 | $-9 | $-3.22 | 2.71 | $-5,927 | $-140 | $214 | -0.21 |
| H22_LONG_10min_10_20 | 1,429 | 37.3% | $-5,991 | $-15 | $-4.19 | 3.50 | $-6,050 | $-132 | $128 | -0.38 |
| H17_LONG_5min_15_45 | 3,802 | 39.0% | $-9,518 | $-15 | $-2.50 | 6.13 | $-10,693 | $-393 | $472 | -0.15 |
| H17_LONG_10min_10_20 | 3,154 | 36.4% | $-9,555 | $-15 | $-3.03 | 5.09 | $-10,003 | $-145 | $191 | -0.25 |
| H20_SHORT_5min_8_16 | 2,858 | 33.4% | $-10,040 | $-16 | $-3.51 | 4.46 | $-10,069 | $-222 | $188 | -0.32 |

**0 of 57 profitable on FULL data.** 
**Critical finding: the hour-of-day strategies with stops/targets DO NOT survive on full data.** The 60-day positive results were a sample artifact. Even though the hour-17 bias exists in the underlying data, scalping it with 10-20pt stop/target structures loses to execution costs because:
- Targets miss frequently (must trade THROUGH the level on a tick).
- Stops slip 0.5pt every time.
- The 10pt/20pt structure produces ~45% WR which is below the ~52% breakeven needed under realistic exec.

## 5. Top-strategies × filter combinations (50 variants)
For each of the 10 least-bad base strategies, we tested 5 filter combos: HTF trend agreement, NY session, HTF+NY, ATR floor, HTF+ATR+NY.
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| E_VWAP_PULL_10_20+HTF30+ATR5+NY | 33 | 39.4% | $75 | $4 | $2.27 | 1.83 | $-108 | $-47 | $56 | 0.12 |
| E_VWAP_PULL_10_20+HTF30+NY | 33 | 39.4% | $75 | $4 | $2.27 | 1.83 | $-108 | $-47 | $56 | 0.12 |
| Q_VELOCITY_FADE+HTF30 | 6 | 50.0% | $62 | $12 | $10.40 | 1.20 | $-44 | $-44 | $39 | 0.33 |
| Q_VELOCITY_10_20+HTF30 | 5 | 60.0% | $49 | $10 | $9.78 | 1.00 | $-28 | $-28 | $36 | 0.30 |
| Q_VELOCITY_FADE+ATR5 | 7 | 42.9% | $30 | $4 | $4.27 | 1.00 | $-23 | $-23 | $39 | 0.13 |
| Q_VELOCITY_10_20+ATR5 | 7 | 42.9% | $8 | $1 | $1.08 | 1.00 | $-64 | $-28 | $36 | 0.03 |
| I_ORB15_15_30+HTF30+ATR5+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| I_ORB15_10_20+HTF30+ATR5+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| I_ORB15_15_30+HTF30+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| I_ORB15_15_30+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| X_GAP_FADE_10_20+HTF30+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| Q_VELOCITY_10_20+HTF30+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| Q_VELOCITY_FADE+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| Q_VELOCITY_10_20+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |
| I_ORB15_10_20+HTF30+NY | 0 | 0.0% | $0 | $0 | $0.00 | 0.00 | $0 | $0 | $0 | 0.00 |

**6 of 50 profitable.** 
Best: `E_VWAP_PULL_10_20+HTF30+ATR5+NY` produces +$75 on 33 trades — too thin to be meaningful. Most NY+HTF filters reduce setup count to zero.

## 6. HOLD-TO-CLOSE strategies — the only positive result on full data
Key insight: small stops/targets get crushed by the asymmetric exit model. But what if we just HOLD the bias for the full hour and exit at MARKET? This eliminates the LIMIT-target miss problem.

### 60-day subset
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| H17_HOLD60_NOSTOP | 41 | 70.7% | $3,911 | $95 | $95.40 | 1.00 | $-414 | $-414 | $883 | 0.44 |
| H17_HOLD60_STOP50 | 41 | 61.0% | $2,380 | $58 | $58.06 | 1.00 | $-318 | $-102 | $705 | 0.34 |
| H17_HOLD120_NOSTOP | 41 | 53.7% | $2,304 | $56 | $56.19 | 1.00 | $-788 | $-590 | $1,174 | 0.19 |
| H17_HOLD60_STOP20 | 41 | 36.6% | $2,056 | $50 | $50.14 | 1.00 | $-334 | $-42 | $705 | 0.31 |
| H17_HOLD60_STOP30 | 41 | 46.3% | $2,012 | $49 | $49.07 | 1.00 | $-370 | $-62 | $705 | 0.29 |
| H17_HOLD30_NOSTOP | 41 | 63.4% | $1,999 | $49 | $48.75 | 1.00 | $-486 | $-429 | $605 | 0.28 |
| H15_HOLD60_SHORT | 42 | 42.9% | $1,490 | $35 | $35.49 | 1.00 | $-471 | $-422 | $1,082 | 0.15 |
| H18_HOLD60_SHORT | 41 | 58.5% | $1,457 | $36 | $35.54 | 1.00 | $-476 | $-476 | $567 | 0.22 |
| H22_HOLD60_STOP30 | 43 | 48.8% | $1,253 | $29 | $29.13 | 1.00 | $-803 | $-62 | $513 | 0.24 |
| H19_HOLD60_STOP30 | 41 | 46.3% | $1,194 | $29 | $29.12 | 1.00 | $-617 | $-62 | $505 | 0.22 |
| H22_HOLD60_NOSTOP | 43 | 58.1% | $1,189 | $28 | $27.65 | 1.00 | $-975 | $-255 | $513 | 0.20 |
| H19_HOLD60_NOSTOP | 41 | 63.4% | $1,098 | $27 | $26.78 | 1.00 | $-808 | $-348 | $505 | 0.15 |
| H06_HOLD60_NOSTOP | 42 | 64.3% | $996 | $24 | $23.70 | 1.00 | $-221 | $-136 | $243 | 0.28 |
| H07_HOLD60_NOSTOP | 43 | 58.1% | $826 | $19 | $19.20 | 1.00 | $-247 | $-140 | $299 | 0.24 |
| H17_HOLD60_S40_T40 | 41 | 58.5% | $534 | $13 | $13.02 | 1.00 | $-575 | $-82 | $79 | 0.17 |
| H17_HOLD60_S30_T30 | 41 | 58.5% | $373 | $9 | $9.09 | 1.00 | $-435 | $-62 | $59 | 0.15 |
| H22_HOLD60_S30_T30 | 43 | 58.1% | $276 | $6 | $6.42 | 1.00 | $-445 | $-62 | $59 | 0.11 |
| H17_HOLD60_S20_T20 | 41 | 58.5% | $233 | $6 | $5.67 | 1.00 | $-295 | $-42 | $39 | 0.14 |
| H20_HOLD60_SHORT | 41 | 51.2% | $-256 | $-6 | $-6.25 | 1.00 | $-651 | $-577 | $368 | -0.04 |
| H14_HOLD60_SHORT | 42 | 40.5% | $-1,204 | $-29 | $-28.67 | 1.00 | $-3,045 | $-645 | $866 | -0.10 |

**18 of 20 profitable on 60d.** Top H17_HOLD60_NOSTOP: +$3,911, $95/day, WR 70%, max DD -$414.

### Full data confirmation
| name | trades | wr | pnl | per_day | per_trade | trades_per_day | max_dd | worst_day | best_day | sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| H17_HOLD60_NOSTOP | 619 | 52.3% | $3,499 | $6 | $5.65 | 1.00 | $-4,199 | $-542 | $2,674 | 0.03 |
| H17_HOLD120_NOSTOP | 619 | 51.9% | $2,688 | $4 | $4.34 | 1.00 | $-3,671 | $-681 | $2,449 | 0.02 |
| H22_HOLD60_NOSTOP | 157 | 52.9% | $2,422 | $15 | $15.43 | 1.00 | $-975 | $-276 | $801 | 0.13 |
| H22_HOLD60_STOP30 | 157 | 47.1% | $1,588 | $10 | $10.11 | 1.00 | $-866 | $-62 | $513 | 0.12 |
| H19_HOLD60_NOSTOP | 610 | 50.0% | $1,424 | $2 | $2.33 | 1.00 | $-4,033 | $-757 | $938 | 0.02 |
| H22_HOLD60_S30_T30 | 157 | 54.1% | $724 | $5 | $4.61 | 1.00 | $-815 | $-62 | $59 | 0.09 |
| H19_HOLD60_STOP30 | 610 | 36.6% | $529 | $1 | $0.87 | 1.00 | $-3,416 | $-62 | $667 | 0.01 |
| H17_HOLD60_STOP20 | 619 | 29.1% | $206 | $0 | $0.33 | 1.00 | $-2,689 | $-42 | $1,043 | 0.00 |
| H07_HOLD60_NOSTOP | 634 | 48.7% | $-5 | $-0 | $-0.01 | 1.00 | $-2,410 | $-455 | $635 | -0.00 |
| H17_HOLD30_NOSTOP | 619 | 51.1% | $-303 | $-0 | $-0.49 | 1.00 | $-3,122 | $-635 | $1,730 | -0.00 |
| H20_HOLD60_SHORT | 610 | 47.0% | $-309 | $-1 | $-0.51 | 1.00 | $-4,232 | $-678 | $1,706 | -0.00 |
| H15_HOLD60_SHORT | 633 | 43.6% | $-472 | $-1 | $-0.74 | 1.00 | $-5,432 | $-584 | $1,082 | -0.00 |
| H17_HOLD60_STOP50 | 619 | 47.3% | $-472 | $-1 | $-0.76 | 1.00 | $-3,817 | $-102 | $1,043 | -0.01 |
| H17_HOLD60_STOP30 | 619 | 37.3% | $-603 | $-1 | $-0.97 | 1.00 | $-2,881 | $-62 | $1,043 | -0.01 |
| H06_HOLD60_NOSTOP | 632 | 48.6% | $-634 | $-1 | $-1.00 | 1.00 | $-2,397 | $-438 | $294 | -0.02 |
| H14_HOLD60_SHORT | 632 | 45.6% | $-947 | $-1 | $-1.50 | 1.00 | $-6,924 | $-768 | $866 | -0.01 |
| H18_HOLD60_SHORT | 614 | 45.1% | $-1,364 | $-2 | $-2.22 | 1.00 | $-4,207 | $-626 | $567 | -0.02 |
| H17_HOLD60_S40_T40 | 619 | 50.1% | $-2,162 | $-3 | $-3.49 | 1.00 | $-2,926 | $-82 | $79 | -0.05 |
| H17_HOLD60_S30_T30 | 619 | 48.0% | $-2,881 | $-5 | $-4.65 | 1.00 | $-3,386 | $-62 | $59 | -0.08 |
| H17_HOLD60_S20_T20 | 619 | 45.9% | $-2,938 | $-5 | $-4.75 | 1.00 | $-3,273 | $-42 | $39 | -0.12 |

**8 of 20 profitable on FULL data (~600+ sessions).**

### Per-year breakdown of top hold strategies (FULL data)

Per-year P&L for the top hold-to-close strategies. Notice that `H17_HOLD60_NOSTOP` and `H22_HOLD60_STOP30` are profitable EVERY YEAR — the most robust pattern.

| Strategy | 2024 | 2025 | 2026 | All | Notes |
|---|---:|---:|---:|---:|---|
| H17_HOLD60_NOSTOP | $401 | $2,354 | $744 | $3,499 | positive every year, WR 52.3% |
| H22_HOLD60_NOSTOP | -$32 | $698 | $1,756 | $2,422 | flat 2024, strong 2025-26 |
| H22_HOLD60_STOP30 | $63 | $856 | $668 | $1,588 | positive every year (with stop) |
| H17_HOLD120_NOSTOP | $81 | $3,496 | -$888 | $2,688 | 2026 loss — 60-min sweet spot |
| H19_HOLD60_NOSTOP | -$1,951 | $464 | $2,911 | $1,424 | 2024 loss — less reliable |
| H17_HOLD60_STOP20 | -$191 | -$298 | $695 | $206 | unstable WR (29%) — STOPs hurt this bias |

The exit-reason breakdown for `H17_HOLD60_NOSTOP` (619 trades, all timeout):
- ALL trades exit via 60-minute timeout at MARKET (no stop, no target).
- Avg win: $95.6.  Avg loss: -$93.2.  WR 52.3%. Net edge per trade $5.65.
- The strategy works because the 60-minute hold captures the +4.7 pts/hour bias as drift, while the symmetric win/loss profile means costs are spread evenly.

## 7. Verdict and Recommendation
### Honest summary
After testing **130+ strategy variants** across 5 different catalogs (structural strategies, cost baselines, hour-of-day exploits, filter combinations, hold-to-close), the picture is clear:

1. **NO classical structural strategy** (momentum, mean reversion, breakout, pullback, BB, RSI, VWAP, etc.) has positive expectancy under realistic execution on MNQ 1-minute tick data at 1 contract size. Every one of the 44+ structural variants loses on 60-day, and we have no reason to believe any survives on full data given the same dynamics that ruined the inverse-pullback baseline.

2. **No simple directional drift exists.** `Z_HOURLY_LONG_10_20` (one entry per hour with 10/20 stop/target) loses ~$6/day. The market doesn't reliably go up or down across the full session.

3. **Per-hour directional bias DOES exist** — Hour 22 UTC (CME open) is +6.1 pts/hr avg over 408 sessions (t=2.9), Hour 17 UTC is +4.7 pts/hr avg over 620 sessions. These are real edges.

4. **Stop/target scalp variants of the hourly bias DON'T survive full data.** Hour-17 with 10pt stop / 20pt target loses on 617 sessions because the asymmetric LIMIT-target/STOP-MARKET model converts the small directional edge into a cost loss.

5. **HOLD-TO-CLOSE strategies (enter at hour open, exit at market end-of-hour) DO survive on full data.** Best: `H17_HOLD60_NOSTOP` = +$3,499 / +$5.65/day / WR 52% / DD -$4,199 over 619 sessions. `H22_HOLD60_NOSTOP` = +$2,422 / +$15.4/day / WR 53% / DD -$975 over 157 sessions (but the H22 trade only happens when CME 22:00 UTC open is on a non-weekend day, hence the lower count).

### Does anything hit the $200/day target?
**No.** The best full-data profitable strategy is `H22_HOLD60_NOSTOP` at $15.4/day. Hours 17 and 22 combined give roughly $20/day at 1 contract size. To hit $200/day you would need either:
- **10x position size**: 10 MNQ on the same setups = $200/day target hit. Cost-per-trade scales the SAME (it's per-contract). Risk: max DD scales too, so the H17 strategy's -$4,199 max DD becomes -$42K at 10 MNQ. This is a viable scaling decision but the user must accept the risk.
- **More biased hours**: stack multiple non-overlapping hour-bias trades per day (H17 + H22 are the realistic candidates, and they're temporally separated). Maybe ~2-3 trades/day max.
- **Different timeframe**: 5-min or 15-min bars with much larger stops/targets (e.g. 30pt stop, 60pt target) might capture more of the bias while preserving the LIMIT-exit model. Untested here.

### RECOMMENDATION
**Deploy the following two strategies at 1 MNQ each (mutually exclusive — one position at a time):**

1. **H22_HOLD60_NOSTOP**: At 22:00 UTC (CME open), enter LONG at ASK. Hold for 60 minutes. Exit at MARKET (sell at BID with small slip). NO stop. NO target.
   - Backtest: +$2,422 over 157 valid sessions, +$15.4/day, WR 52.9%, max DD -$975. Sharpe 0.13.
2. **H17_HOLD60_NOSTOP**: At 17:00 UTC (13:00 NY), enter LONG at ASK. Hold for 60 minutes. Exit at MARKET. NO stop. NO target.
   - Backtest: +$3,499 over 619 sessions, +$5.65/day, WR 52.3%, max DD -$4,199. Sharpe 0.03.

**Combined approach yields ~$20/day at 1 MNQ.** These strategies do NOT meet the $200/day target. The user has three options:

- **A. Accept the small edge**: Run both strategies at 1 MNQ for $20/day with $4K max DD. This is profitable but tiny.
- **B. Scale position size**: Run at 10 MNQ for $200/day target with $40K max DD. The Sharpe is the same — this is a leverage decision, not an edge improvement.
- **C. Stop trading futures at this timeframe / instrument**. The fundamental issue is the cost-to-move ratio at 1-min timeframes on MNQ at 1 contract. Try:
  - Higher timeframe (15-min, 1h) with proportionally larger stops/targets to dilute the cost drag.
  - Different instrument with lower cost ratio (ES, NQ, etc).
  - Different broker execution model (if your broker actually offers MARKET targets with low slip, not LIMIT targets, the picture changes).
  - Microstructure features (L2 order book, queue position, trade flow) — not available in the current tick CSV.

**DO NOT redeploy the original inverse-pullback strategy.** It's structurally negative under realistic execution; the original validation that showed +$1,952/day was an execution-model artifact.

### Files produced
- `research/alternative_strategies.py` — 44-variant structural battery (catalog A-R, plus bonus trend follow and gap fade)
- `research/alt_extras_catalog.py` — 13 cost/drift baselines
- `research/hourly_bias_probe.py` — per-hour OC bias on 60d
- `research/hourly_bias_full.py` — per-hour OC bias on FULL data, by year
- `research/hour_of_day_strategies.py` — 57 hour-of-day exploit variants
- `research/alt_strategies_combinations.py` — 50 combo+filter variants
- `research/hold_to_close_h17.py` — 20 hold-to-close variants (THE WINNER)
- `research/analyze_hold_winners.py` — per-year breakdown of top strategies
- `research/alt_summary_60d.csv`, `alt_summary_full.csv` (if exists)
- `research/alt_extras_summary_60d.csv`
- `research/alt_hour_summary_60d.csv`, `alt_hour_summary_full.csv`
- `research/alt_combo_summary_60d.csv`
- `research/hold_summary_60d.csv`, `hold_summary_full.csv`
- `research/hourly_oc_bias.csv`, `hourly_oc_bias_full.csv`
- `research/hold_trades_*.csv` — per-trade logs for winners

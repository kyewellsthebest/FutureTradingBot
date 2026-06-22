# Round 2 Deep Dive

## HOLD_24H_22UTC_LONG (buy 22:00 UTC daily, sell 24h later, MARKET)

- Total trades: 157
- Win rate: 62.4%
- Total PNL: $19,599
- Per-day PNL: $128.10
- Per-trade PNL: $124.84
- Max DD: $-4,626
- Worst day: $-2,655
- Best day: $2,246
- Sharpe-ish: 0.19

### Per-year:
| Year | PNL | n_trades |
|---|---:|---:|
| 2024 | $1,271 | 37 |
| 2025 | $4,453 | 48 |
| 2026 | $13,874 | 72 |

### Per-month:
| Month | PNL |
|---|---:|
| 2024-03 | $739 |
| 2024-04 | $-349 |
| 2024-06 | $67 |
| 2024-07 | $-823 |
| 2024-08 | $1,560 |
| 2024-09 | $78 |
| 2025-03 | $-85 |
| 2025-04 | $-974 |
| 2025-08 | $-132 |
| 2025-09 | $2,530 |
| 2025-10 | $3,194 |
| 2025-11 | $-80 |
| 2026-03 | $-1,933 |
| 2026-04 | $9,909 |
| 2026-05 | $5,921 |
| 2026-06 | $-22 |

**8 positive months, 8 negative.**

### Per-DOW:
| DOW | n | PNL | WR |
|---|---:|---:|---:|
| Mon | 37 | $3,995 | 59% |
| Tue | 31 | $959 | 61% |
| Wed | 35 | $5,723 | 51% |
| Thu | 31 | $-1,201 | 61% |
| Sun | 23 | $10,123 | 87% |

**Worst 30-day rolling PNL: $-1,465**

## HOLD_SESSION_22to14_LONG (buy 22:00 UTC, sell 14:00 UTC next day)

Compared to HOLD_24H_22UTC_LONG, this one EXITS BEFORE the negative-bias morning hours (14-15 UTC).

- Total trades: 156
- WR: 57.1%
- Total PNL: $11,831
- Per-day: $75.84
- Max DD: $-2,629
- Sharpe: 0.18

### Per-year:
| Year | PNL |
|---|---:|
| 2024 | $1,084 |
| 2025 | $3,072 |
| 2026 | $7,674 |

Worst 30d rolling: $-1,052

## WEEKOPEN_LONG_HOLD* (buy Sunday 22:00 UTC, hold N days)

| Variant | trades | WR | PNL | per_day | max DD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| HOLD1d | 23 | 87.0% | $10,123 | $440.15 | $-363 | 0.98 |
| HOLD2d | 23 | 78.3% | $13,822 | $600.94 | $-636 | 0.86 |
| HOLD5d | 23 | 78.3% | $20,181 | $877.42 | $-2,574 | 0.62 |

Note: per_day here is dollars per Sunday trade-day (one per week), NOT per calendar day. The strategy generates $4-5K of PNL per week on average.

### Individual weekly trades (HOLD5d):

| Week start | entry | exit | reason | pnl pts | PNL $ |
|---|---:|---:|---|---:|---:|
| 2025-08-31 | 23429.99 | 23745.87 | timeout | +315.9 | $+631 |
| 2025-09-07 | 23635.65 | 24126.89 | timeout | +491.2 | $+982 |
| 2025-09-14 | 24095.64 | 24573.76 | timeout | +478.1 | $+955 |
| 2025-09-21 | 24601.22 | 24648.47 | timeout | +47.3 | $+94 |
| 2025-10-05 | 24802.54 | 24656.03 | timeout | -146.5 | $-294 |
| 2025-10-12 | 24382.48 | 24940.38 | timeout | +557.9 | $+1,115 |
| 2025-10-19 | 24924.78 | 25647.55 | timeout | +722.8 | $+1,445 |
| 2025-10-26 | 25606.78 | 25889.15 | timeout | +282.4 | $+564 |
| 2026-03-08 | 24430.64 | 24548.22 | timeout | +117.6 | $+234 |
| 2026-03-15 | 24306.22 | 23665.86 | timeout | -640.4 | $-1,281 |
| 2026-03-22 | 23689.99 | 23209.08 | timeout | -480.9 | $-963 |
| 2026-03-29 | 23032.84 | 24063.99 | timeout | +1031.2 | $+2,062 |
| 2026-04-05 | 23895.89 | 24942.88 | timeout | +1047.0 | $+2,093 |
| 2026-04-12 | 24776.91 | 26498.92 | timeout | +1722.0 | $+3,443 |
| 2026-04-19 | 26441.12 | 27304.34 | timeout | +863.2 | $+1,726 |
| 2026-04-26 | 27264.36 | 27768.92 | timeout | +504.6 | $+1,008 |
| 2026-05-03 | 27770.67 | 29202.38 | timeout | +1431.7 | $+2,863 |
| 2026-05-10 | 29184.76 | 28985.01 | timeout | -199.7 | $-400 |
| 2026-05-17 | 29034.92 | 29899.52 | timeout | +864.6 | $+1,728 |
| 2026-05-24 | 29651.09 | 30398.23 | timeout | +747.1 | $+1,494 |
| 2026-05-31 | 30346.09 | 29059.52 | timeout | -1286.6 | $-2,574 |
| 2026-06-07 | 28821.11 | 30232.96 | timeout | +1411.8 | $+2,823 |
| 2026-06-14 | 29908.63 | 30125.25 | timeout | +216.6 | $+433 |

## Combined portfolios

### Combo A: H17_HOLD4H + H22_HOLD2H (non-overlapping in time at 1 MNQ)

H17_HOLD4H alone: 619 tr, $8,001, $13.14/day, WR 54.9%, DD $-6,424

H22_HOLD2H alone: 157 tr, $2,976, $18.95/day, WR 51.0%, DD $-1,382

COMBO: 776 tr, $10,977, $17.02/day, WR 54.1%, DD $-6,284, Sharpe 0.05

Per-year COMBO_H17_4H_H22_2H: 2024=$841, 2025=$5,481, 2026=$4,654

### Combo B: HOLD_16H_22UTC_LONG (LONGER than 24h, exits at 14 UTC pre-NY-open)

HOLD_16H_22UTC: 157 tr, $12,065, $76.85/day, WR 57.3%, DD $-2,629, Sharpe 0.18

## Scaling analysis (multiply PNL and DD by N for N MNQ)

Strategies are at 1 MNQ. To scale to N MNQ, multiply PNL/DD by N.
Commissions ARE per-contract, so they scale too — but they're already in the per-trade $.

| Strategy | 1 MNQ /day | 1 MNQ DD | $200/day MNQ | DD at $200/day | $500/day MNQ | DD at $500/day |
|---|---:|---:|---:|---:|---:|---:|
| HOLD_24H_22UTC_LONG | $128.10 | $-4,626 | 2 | $-9,251 | 4 | $-18,502 |
| HOLD_16H_22UTC_LONG | $76.85 | $-2,629 | 3 | $-7,887 | 7 | $-18,404 |
| HOLD_SESSION_22to14_LONG | $75.84 | $-2,629 | 3 | $-7,887 | 7 | $-18,404 |
| WEEKOPEN_LONG_HOLD2d | $600.94 | $-636 | 1 | $-636 | 1 | $-636 |
| WEEKOPEN_LONG_HOLD5d | $877.42 | $-2,574 | 1 | $-2,574 | 1 | $-2,574 |
| COMBO_H17_4H_H22_2H | $17.02 | $-6,284 | 12 | $-75,406 | 30 | $-188,515 |

## Vol filters on HOLD_24H_22UTC_LONG

| Filter | trades | WR | PNL | per_day | DD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| UNFILTERED | 157 | 62.4% | $19,599 | $128.10 | $-4,626 | 0.19 |
| PREVRANGE >= 50 | 150 | 62.7% | $19,807 | $135.66 | $-4,626 | 0.20 |
| PREVRANGE <= 75 | 12 | 66.7% | $692 | $57.71 | $-729 | 0.22 |
| PREVRANGE 75-200 | 32 | 68.8% | $7,964 | $248.88 | $-1,277 | 0.41 |

## DOW filter on HOLD_24H_22UTC_LONG

Per-DOW PNL of the unfiltered HOLD_24H_22UTC_LONG (already shown above).
Notable: Sun (Day 6) has 87% WR, $10K PNL on 23 trades — drives most of the edge.
Thursday (Day 3) is the only LOSING dow.

### Filtered: skip Thursday entries (DOW=3)

- 126 tr, WR 62.7%, $20,800, $169.11/day, DD $-3,094, Sharpe 0.28

### Filtered: Sun + Wed entries only (top 2 DOWs)

- 58 tr, WR 65.5%, $15,846, $273.21/trade-day, DD $-1,506, Sharpe 0.49

## Worst-case stress: 30-day rolling losses

| Strategy | Worst 30d rolling PNL | DD | Sharpe |
|---|---:|---:|---:|
| HOLD_24H_22UTC_LONG | $-1,465 | $-4,626 | 0.19 |
| HOLD_16H_22UTC_LONG | $-1,052 | $-2,629 | 0.18 |
| HOLD_SESSION_22to14_LONG | $-1,052 | $-2,629 | 0.18 |
| WEEKOPEN_LONG_HOLD2d | $-290 | $-636 | 0.86 |
| WEEKOPEN_LONG_HOLD5d | $631 | $-2,574 | 0.62 |
| COMBO_H17_4H_H22_2H | $-3,935 | $-6,284 | 0.05 |


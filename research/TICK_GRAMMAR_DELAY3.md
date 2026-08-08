# Tick grammar: conditional behaviour of legs, eight NQ contracts

**ENTRY DELAYED 3 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

  R=4 NQH5: 2,671,656 legs [22s]
  R=4 NQH6: 2,427,366 legs [38s]
  R=4 NQM5: 3,156,190 legs [59s]
  R=4 NQM6: 3,096,643 legs [78s]
  R=4 NQU4: 2,218,222 legs [92s]
  R=4 NQU5: 1,376,298 legs [99s]
  R=4 NQZ4: 1,545,302 legs [110s]
  R=4 NQZ5: 2,312,309 legs [127s]
## R = 4 ticks -- 18,803,586 legs, 8 contracts

### horizon 50 price-changes -- population baseline train +0.02, holdout +0.03 ticks

146 cells passed the train screen (|t|>=3). **99% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 1) | 114,057/45,646 | +2.61 | +41.1 | +2.26 +/- 0.09 | 8/8 | 75% | $1.13 | fail fail |
| (1, 4, 2, 4, 2) | 725,130/311,838 | -0.82 | -37.2 | -0.63 +/- 0.03 | 8/8 | 67% | $0.32 | fail fail |
| (1, 4, 2, 4, 1) | 110,310/44,358 | +2.20 | +35.2 | +2.06 +/- 0.09 | 8/8 | 75% | $1.03 | fail fail |
| (-1, 3, 2, 4, 2) | 171,594/73,727 | -1.48 | -32.5 | -1.31 +/- 0.06 | 8/8 | 75% | $0.66 | fail fail |
| (-1, 4, 2, 4, 0) | 16,005/5,547 | +7.02 | +30.9 | +5.59 +/- 0.36 | 8/8 | 100% | $2.79 | PASS fail |
| (1, 4, 2, 4, 0) | 15,606/5,466 | +7.02 | +30.8 | +5.48 +/- 0.39 | 8/8 | 100% | $2.74 | PASS fail |
| (-1, 3, 2, 3, 2) | 142,574/64,863 | -1.35 | -28.8 | -1.22 +/- 0.06 | 8/8 | 80% | $0.61 | fail fail |
| (1, 3, 2, 4, 2) | 171,889/74,115 | -1.28 | -28.3 | -1.12 +/- 0.06 | 8/8 | 75% | $0.56 | fail fail |
| (-1, 4, 2, 4, 2) | 728,816/314,161 | -0.56 | -25.3 | -0.45 +/- 0.03 | 8/8 | 67% | $0.23 | fail fail |
| (1, 3, 2, 3, 2) | 142,432/64,515 | -1.11 | -23.8 | -1.08 +/- 0.06 | 8/8 | 80% | $0.54 | fail fail |
| (-1, 4, 2, 3, 1) | 49,999/19,999 | +2.13 | +22.5 | +1.87 +/- 0.14 | 8/8 | 80% | $0.93 | fail fail |
| (-1, 2, 1, 3, 2) | 83,685/35,336 | -1.39 | -22.5 | -1.22 +/- 0.09 | 8/8 | 100% | $0.61 | fail fail |
| (1, 4, 2, 3, 2) | 222,316/94,886 | -0.93 | -22.5 | -0.93 +/- 0.06 | 8/8 | 75% | $0.47 | fail fail |
| (-1, 3, 2, 2, 2) | 89,099/39,619 | -1.15 | -18.7 | -1.03 +/- 0.09 | 8/8 | 80% | $0.52 | fail fail |
| (-1, 4, 2, 3, 2) | 218,831/92,490 | -0.78 | -17.9 | -0.63 +/- 0.06 | 8/8 | 75% | $0.32 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train +0.03, holdout +0.03 ticks

152 cells passed the train screen (|t|>=3). **96% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 1) | 114,057/45,646 | +4.42 | +36.9 | +4.34 +/- 0.19 | 8/8 | 75% | $2.17 | PASS fail |
| (1, 4, 2, 4, 2) | 725,130/311,838 | -1.46 | -33.1 | -1.27 +/- 0.06 | 8/8 | 67% | $0.64 | fail fail |
| (-1, 3, 2, 4, 2) | 171,594/73,727 | -2.74 | -29.8 | -2.26 +/- 0.14 | 8/8 | 75% | $1.13 | fail fail |
| (-1, 3, 2, 3, 2) | 142,574/64,863 | -2.83 | -29.6 | -2.50 +/- 0.13 | 8/8 | 80% | $1.25 | fail fail |
| (1, 4, 2, 4, 1) | 110,310/44,358 | +3.59 | +29.0 | +3.09 +/- 0.19 | 8/8 | 75% | $1.55 | PASS fail |
| (-1, 4, 2, 4, 0) | 16,005/5,547 | +10.55 | +24.5 | +8.11 +/- 0.83 | 8/8 | 100% | $4.06 | PASS fail |
| (1, 3, 2, 4, 2) | 171,889/74,115 | -2.21 | -23.9 | -1.83 +/- 0.14 | 8/8 | 75% | $0.92 | fail fail |
| (-1, 2, 1, 3, 2) | 83,685/35,336 | -2.97 | -23.0 | -2.56 +/- 0.19 | 8/8 | 100% | $1.28 | fail fail |
| (1, 4, 2, 4, 0) | 15,606/5,466 | +10.28 | +22.7 | +8.40 +/- 0.86 | 8/8 | 100% | $4.20 | PASS fail |
| (-1, 4, 2, 3, 1) | 49,999/19,999 | +3.99 | +22.0 | +3.97 +/- 0.28 | 8/8 | 80% | $1.99 | PASS fail |
| (-1, 2, 1, 2, 2) | 70,186/28,926 | -2.98 | -19.4 | -2.42 +/- 0.26 | 7/8 | 100% | $1.21 | fail fail |
| (1, 3, 2, 3, 2) | 142,432/64,515 | -1.84 | -19.2 | -1.77 +/- 0.13 | 8/8 | 80% | $0.89 | fail fail |
| (1, 4, 2, 3, 2) | 222,316/94,886 | -1.58 | -19.2 | -1.74 +/- 0.13 | 8/8 | 75% | $0.87 | fail fail |
| (-1, 4, 2, 4, 2) | 728,816/314,161 | -0.76 | -17.5 | -0.68 +/- 0.06 | 7/8 | 67% | $0.34 | fail fail |
| (1, 4, 2, 3, 1) | 49,051/19,711 | +3.20 | +17.0 | +2.64 +/- 0.27 | 8/8 | 80% | $1.32 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train +0.03, holdout +0.03 ticks

123 cells passed the train screen (|t|>=3). **97% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 1) | 114,057/45,646 | +6.37 | +25.0 | +5.96 +/- 0.41 | 8/8 | 75% | $2.98 | PASS fail |
| (-1, 3, 2, 3, 2) | 142,574/64,863 | -5.05 | -23.4 | -4.23 +/- 0.31 | 8/8 | 80% | $2.12 | PASS fail |
| (1, 4, 2, 4, 2) | 725,130/311,838 | -2.22 | -22.8 | -2.30 +/- 0.14 | 8/8 | 67% | $1.15 | fail fail |
| (-1, 3, 2, 4, 2) | 171,594/73,727 | -4.07 | -19.7 | -3.33 +/- 0.32 | 8/8 | 75% | $1.67 | PASS fail |
| (-1, 4, 2, 4, 0) | 16,005/5,547 | +15.48 | +17.1 | +16.11 +/- 1.59 | 8/8 | 100% | $8.06 | PASS PASS |
| (-1, 2, 1, 3, 2) | 83,685/35,336 | -4.98 | -16.8 | -3.82 +/- 0.46 | 8/8 | 100% | $1.91 | PASS fail |
| (1, 4, 2, 4, 0) | 15,606/5,466 | +14.51 | +16.2 | +12.38 +/- 1.71 | 8/8 | 100% | $6.19 | PASS PASS |
| (-1, 4, 2, 3, 1) | 49,999/19,999 | +5.58 | +14.2 | +5.78 +/- 0.62 | 8/8 | 80% | $2.89 | PASS fail |
| (1, 1, 0, 1, 0) | 133,490/63,420 | +2.72 | +13.5 | +1.78 +/- 0.28 | 7/8 | 100% | $0.89 | fail fail |
| (1, 4, 2, 3, 2) | 222,316/94,886 | -2.41 | -13.4 | -3.26 +/- 0.28 | 8/8 | 67% | $1.63 | PASS fail |
| (-1, 3, 2, 2, 2) | 89,099/39,619 | -3.85 | -13.3 | -3.30 +/- 0.44 | 8/8 | 75% | $1.65 | PASS fail |
| (-1, 2, 1, 2, 2) | 70,186/28,926 | -4.42 | -12.9 | -2.10 +/- 0.61 | 7/8 | 100% | $1.05 | fail fail |
| (1, 4, 2, 4, 1) | 110,310/44,358 | +3.29 | +12.8 | +2.50 +/- 0.42 | 7/8 | 75% | $1.25 | fail fail |
| (-1, 3, 2, 4, 1) | 125,398/54,123 | +2.76 | +12.1 | +2.82 +/- 0.32 | 7/8 | 80% | $1.41 | fail fail |
| (-1, 3, 1, 3, 2) | 43,988/19,808 | -4.87 | -12.0 | -3.48 +/- 0.61 | 7/8 | 100% | $1.74 | PASS fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

wrote /home/user/FutureTradingBot/research/TICK_GRAMMAR.md

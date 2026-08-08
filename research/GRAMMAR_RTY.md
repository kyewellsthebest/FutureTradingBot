# Tick grammar: RTY -- 8 contracts, tick 0.1, $0.5/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 4 ticks -- 2,205,335 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.02, holdout -0.02 ticks

2 cells passed the train screen (|t|>=3). **50% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 3, 1, 2, 2) | 4,448/1,896 | +0.52 | +3.4 | -0.02 +/- 0.24 | 3/8 |  | $0.01 | fail fail |
| (-1, 2, 0, 3, 1) | 8,191/3,355 | +0.41 | +3.0 | +0.01 +/- 0.20 | 3/8 |  | $0.00 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train -0.02, holdout -0.02 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train -0.02, holdout -0.02 ticks

14 cells passed the train screen (|t|>=3). **79% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 1, 2, 0, 0) | 10,334/4,149 | +2.37 | +4.5 | -0.42 +/- 0.94 | 5/8 | 0% | $0.21 | fail fail |
| (1, 4, 2, 4, 1) | 5,209/2,160 | -3.53 | -4.1 | -2.07 +/- 1.44 | 5/8 |  | $1.03 | fail fail |
| (1, 1, 2, 1, 0) | 8,863/3,711 | -2.02 | -3.7 | -0.75 +/- 0.87 | 5/8 | 0% | $0.38 | fail fail |
| (-1, 2, 2, 0, 0) | 5,174/2,193 | +2.77 | +3.5 | +0.96 +/- 1.35 | 5/8 | 0% | $0.48 | fail fail |
| (1, 1, 2, 0, 0) | 10,450/4,587 | -1.73 | -3.3 | +0.99 +/- 0.86 | 3/8 | 0% | $0.49 | fail fail |
| (1, 3, 2, 3, 1) | 5,230/2,124 | -2.47 | -3.3 | -0.98 +/- 1.16 | 5/8 |  | $0.49 | fail fail |
| (-1, 4, 2, 4, 1) | 5,237/2,200 | +2.68 | +3.2 | +0.46 +/- 1.44 | 5/8 | 100% | $0.23 | fail fail |
| (1, 3, 2, 2, 0) | 3,758/1,588 | -3.31 | -3.2 | -1.63 +/- 1.70 | 4/8 | 100% | $0.82 | fail fail |
| (1, 2, 2, 3, 0) | 8,258/3,468 | -1.91 | -3.2 | -0.72 +/- 0.95 | 4/8 | 100% | $0.36 | fail fail |
| (-1, 4, 2, 4, 0) | 2,165/1,031 | +5.28 | +3.2 | +1.99 +/- 2.91 | 5/8 | 100% | $1.00 | fail fail |
| (-1, 2, 2, 3, 0) | 8,456/3,499 | +1.84 | +3.2 | -0.27 +/- 0.92 | 5/8 |  | $0.13 | fail fail |
| (1, 2, 2, 2, 0) | 7,244/2,939 | -2.28 | -3.1 | -0.07 +/- 1.12 | 5/8 | 100% | $0.03 | fail fail |
| (-1, 3, 2, 2, 2) | 2,963/1,346 | +2.99 | +3.1 | +2.43 +/- 1.45 | 5/8 |  | $1.21 | fail fail |
| (-1, 1, 2, 1, 0) | 8,746/3,789 | +1.66 | +3.0 | +1.39 +/- 0.89 | 4/8 | 0% | $0.69 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

## R = 8 ticks -- 698,099 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.09, holdout -0.09 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train -0.11, holdout -0.09 ticks

1 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 4, 2, 4, 1) | 1,711/699 | -2.68 | -3.1 | -0.69 +/- 1.48 | 4/8 |  | $0.34 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.11, holdout -0.09 ticks

4 cells passed the train screen (|t|>=3). **25% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 0, 2, 0, 1) | 2,135/999 | -4.77 | -3.7 | +0.80 +/- 2.22 | 5/8 |  | $0.40 | fail fail |
| (1, 4, 2, 4, 1) | 1,711/699 | -5.97 | -3.3 | +0.60 +/- 3.19 | 5/8 | 0% | $0.30 | fail fail |
| (1, 4, 2, 4, 0) | 820/424 | -10.20 | -3.1 | -5.70 +/- 4.49 | 4/8 | 0% | $2.85 | PASS fail |
| (-1, 0, 2, 0, 0) | 6,978/2,919 | +2.33 | +3.0 | -1.13 +/- 1.27 | 4/8 |  | $0.56 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

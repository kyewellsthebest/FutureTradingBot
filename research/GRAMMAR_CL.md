# Tick grammar: CL -- 8 contracts, tick 0.01, $1.0/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 4 ticks -- 538,158 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.02, holdout -0.03 ticks

2 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 3, 2, 1, 1) | 821/350 | +1.54 | +3.5 | +0.50 +/- 0.51 | 6/8 |  | $0.50 | fail fail |
| (1, 2, 2, 2, 0) | 1,752/747 | +1.05 | +3.1 | +0.24 +/- 0.50 | 3/8 |  | $0.24 | fail fail |

Shuffled control: **2 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train -0.02, holdout -0.03 ticks

3 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 2, 0) | 507/205 | -8.63 | -3.9 | -2.16 +/- 2.21 | 5/8 |  | $2.16 | PASS fail |
| (-1, 4, 2, 4, 2) | 3,585/1,526 | -1.42 | -3.2 | -0.99 +/- 0.58 | 5/8 |  | $0.99 | fail fail |
| (1, 1, 2, 0, 0) | 3,513/1,694 | +1.26 | +3.1 | +0.79 +/- 0.46 | 5/8 |  | $0.79 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.02, holdout -0.04 ticks

6 cells passed the train screen (|t|>=3). **67% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 2) | 3,585/1,526 | -4.27 | -4.0 | -1.13 +/- 1.28 | 4/8 |  | $1.13 | fail fail |
| (-1, 4, 2, 2, 0) | 507/205 | -16.49 | -3.9 | -3.60 +/- 4.33 | 5/8 |  | $3.60 | PASS fail |
| (-1, 4, 2, 4, 0) | 826/362 | -10.37 | -3.3 | -4.65 +/- 3.13 | 6/8 |  | $4.65 | PASS PASS |
| (1, 0, 0, 0, 0) | 1,450/491 | +7.74 | +3.1 | -2.01 +/- 2.99 | 2/8 |  | $2.01 | PASS fail |
| (-1, 2, 1, 2, 1) | 1,493/621 | +3.77 | +3.1 | +0.16 +/- 1.79 | 5/8 |  | $0.16 | fail fail |
| (-1, 2, 2, 1, 1) | 889/331 | +6.14 | +3.1 | -0.48 +/- 2.37 | 5/8 |  | $0.48 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

## R = 8 ticks -- 163,543 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.16, holdout -0.14 ticks

1 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 1, 2, 2, 0) | 917/415 | -1.36 | -3.0 | -0.17 +/- 0.57 | 6/8 |  | $0.17 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train -0.15, holdout -0.15 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train -0.14, holdout -0.14 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

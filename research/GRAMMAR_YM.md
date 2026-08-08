# Tick grammar: YM -- 8 contracts, tick 1.0, $0.5/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 4 ticks -- 2,522,476 legs, 8 contracts

### horizon 50 price-changes -- population baseline train +0.01, holdout +0.01 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train +0.01, holdout +0.01 ticks

3 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 2, 2, 2, 2) | 2,008/879 | +2.79 | +3.8 | +0.22 +/- 0.95 | 5/8 |  | $0.11 | fail fail |
| (-1, 0, 2, 0, 0) | 25,685/10,812 | +0.71 | +3.1 | +0.31 +/- 0.32 | 6/8 |  | $0.15 | fail fail |
| (1, 3, 2, 4, 0) | 3,385/1,364 | -2.01 | -3.1 | -0.87 +/- 0.92 | 5/8 |  | $0.44 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train +0.01, holdout +0.00 ticks

4 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 2) | 19,476/8,535 | +2.22 | +4.2 | +0.99 +/- 0.75 | 6/8 |  | $0.49 | fail fail |
| (1, 4, 2, 4, 2) | 18,771/7,916 | -1.98 | -3.6 | -3.12 +/- 0.81 | 6/8 |  | $1.56 | PASS fail |
| (-1, 3, 1, 4, 2) | 8,832/3,815 | +2.65 | +3.6 | +0.74 +/- 1.06 | 5/8 |  | $0.37 | fail fail |
| (-1, 2, 2, 0, 0) | 5,124/2,164 | +3.20 | +3.0 | +2.51 +/- 1.55 | 6/8 |  | $1.26 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

## R = 8 ticks -- 875,080 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.02, holdout -0.05 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train -0.03, holdout -0.05 ticks

2 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 1, 2, 1, 0) | 4,854/2,026 | +1.63 | +3.2 | +0.29 +/- 0.69 | 5/8 |  | $0.15 | fail fail |
| (1, 4, 2, 4, 0) | 818/449 | -6.54 | -3.1 | -6.99 +/- 3.06 | 5/8 |  | $3.50 | PASS fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.04, holdout -0.05 ticks

4 cells passed the train screen (|t|>=3). **50% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 1, 4, 2) | 12,402/5,253 | +2.59 | +3.7 | +0.52 +/- 0.97 | 5/8 |  | $0.26 | fail fail |
| (-1, 4, 1, 2, 2) | 1,551/592 | +7.20 | +3.6 | -2.60 +/- 2.93 | 4/8 |  | $1.30 | fail fail |
| (1, 4, 2, 4, 0) | 818/449 | -13.63 | -3.4 | -11.19 +/- 5.70 | 5/8 |  | $5.60 | PASS PASS |
| (-1, 2, 2, 2, 0) | 2,394/1,016 | +5.72 | +3.1 | -2.04 +/- 2.41 | 4/8 |  | $1.02 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

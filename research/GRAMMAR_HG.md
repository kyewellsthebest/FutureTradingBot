# Tick grammar: HG -- 3 contracts, tick 0.0005, $1.25/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 4 ticks -- 105,196 legs, 3 contracts

### horizon 50 price-changes -- population baseline train -0.06, holdout -0.05 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train -0.09, holdout -0.09 ticks

2 cells passed the train screen (|t|>=3). **50% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 0, 2, 0, 0) | 724/317 | -7.68 | -3.5 | +2.66 +/- 3.50 | 0/3 |  | $3.33 | PASS fail |
| (1, 1, 2, 1, 0) | 472/229 | -2.80 | -3.1 | -0.07 +/- 1.23 | 2/3 |  | $0.09 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.07, holdout -0.06 ticks

4 cells passed the train screen (|t|>=3). **50% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 0, 2, 0, 0) | 724/317 | -23.70 | -4.1 | +1.72 +/- 5.50 | 1/3 |  | $2.15 | PASS fail |
| (-1, 4, 0, 4, 2) | 1,646/666 | +8.89 | +3.9 | +3.05 +/- 3.61 | 3/3 |  | $3.81 | PASS fail |
| (1, 4, 0, 3, 2) | 512/176 | -6.47 | -3.1 | -1.29 +/- 4.24 | 1/2 |  | $1.61 | PASS fail |
| (1, 4, 1, 4, 2) | 1,438/636 | -9.48 | -3.1 | +4.43 +/- 3.25 | 0/3 |  | $5.53 | PASS PASS |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

## R = 8 ticks -- 31,273 legs, 3 contracts

### horizon 50 price-changes -- population baseline train -0.15, holdout -0.13 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train -0.15, holdout -0.20 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train -0.13, holdout -0.29 ticks

2 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 0, 4, 2) | 446/196 | +20.43 | +3.2 | +25.80 +/- 10.85 | 2/3 |  | $32.25 | PASS PASS |
| (1, 4, 0, 4, 2) | 523/192 | -20.48 | -3.2 | -11.54 +/- 7.06 | 2/3 |  | $14.42 | PASS PASS |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

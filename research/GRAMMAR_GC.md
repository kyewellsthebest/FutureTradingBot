# Tick grammar: GC -- 6 contracts, tick 0.1, $1.0/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 4 ticks -- 831,697 legs, 6 contracts

### horizon 50 price-changes -- population baseline train -0.01, holdout -0.07 ticks

1 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 3, 1, 1, 2) | 1,053/454 | -3.43 | -3.9 | -1.87 +/- 1.44 | 5/6 |  | $1.87 | PASS fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train -0.02, holdout -0.07 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train -0.03, holdout -0.03 ticks

3 cells passed the train screen (|t|>=3). **67% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 2, 0) | 541/183 | +40.12 | +4.5 | +16.38 +/- 16.39 | 4/4 |  | $16.38 | PASS PASS |
| (-1, 4, 0, 2, 2) | 1,768/756 | +15.33 | +3.2 | +1.29 +/- 10.94 | 4/6 |  | $1.29 | fail fail |
| (-1, 3, 0, 4, 1) | 2,171/904 | +13.09 | +3.1 | -3.24 +/- 8.06 | 2/6 |  | $3.24 | PASS fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

## R = 8 ticks -- 323,781 legs, 6 contracts

### horizon 50 price-changes -- population baseline train -0.11, holdout -0.20 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train -0.09, holdout -0.22 ticks

2 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 0, 2, 2) | 670/288 | +16.72 | +3.7 | +4.43 +/- 11.23 | 4/6 |  | $4.43 | PASS PASS |
| (-1, 2, 0, 1, 1) | 930/450 | +8.75 | +3.0 | +0.72 +/- 4.50 | 4/6 |  | $0.72 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.13, holdout -0.17 ticks

1 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 4, 2, 4, 2) | 1,753/848 | -32.70 | -3.4 | -22.41 +/- 11.74 | 5/6 |  | $22.41 | PASS PASS |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

# Tick grammar: FX-USDJPY -- 1 contracts, tick 0.001, $0.01/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 10 ticks -- 245,833 legs, 1 contracts

### horizon 50 price-changes -- population baseline train +0.13, holdout +0.23 ticks

1 cells passed the train screen (|t|>=3). **0% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 2, 0, 2, 2) | 741/389 | +2.43 | +3.4 | -0.65 +/- 1.01 | 0/1 |  | $0.01 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train +0.20, holdout +0.21 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train +0.23, holdout +0.24 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

## R = 20 ticks -- 85,346 legs, 1 contracts

### horizon 50 price-changes -- population baseline train +0.11, holdout +0.05 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train +0.14, holdout +0.02 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train +0.17, holdout +0.28 ticks

1 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 0, 4, 2) | 1,347/556 | +10.30 | +3.7 | +4.99 +/- 5.51 | 1/1 |  | $0.05 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

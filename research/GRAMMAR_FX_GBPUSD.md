# Tick grammar: FX-GBPUSD -- 1 contracts, tick 1e-05, $0.01/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 10 ticks -- 175,064 legs, 1 contracts

### horizon 50 price-changes -- population baseline train +0.20, holdout +0.17 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train +0.17, holdout +0.17 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train +0.13, holdout +0.13 ticks

1 cells passed the train screen (|t|>=3). **0% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 0, 2, 2, 0) | 1,040/390 | +17.33 | +3.2 | -2.86 +/- 3.76 | 0/1 |  | $0.03 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

## R = 20 ticks -- 55,624 legs, 1 contracts

### horizon 50 price-changes -- population baseline train +0.16, holdout -0.18 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train +0.14, holdout -0.25 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train +0.12, holdout -0.20 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

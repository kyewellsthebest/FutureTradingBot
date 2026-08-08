# Tick grammar: conditional behaviour of legs, eight NQ contracts

**SYNTHETIC RANDOM WALK** -- the null check. Anything that passes screening here is the engine's false-positive rate.

## R = 8 ticks -- 222,107 legs, 8 contracts

### horizon 50 price-changes -- population baseline train +0.00, holdout -0.02 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train -0.01, holdout -0.00 ticks

1 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 3, 2, 2, 1) | 474/217 | -2.53 | -4.0 | -0.15 +/- 0.95 | 4/8 |  | $0.07 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train +0.02, holdout -0.06 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, halved per side against the gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

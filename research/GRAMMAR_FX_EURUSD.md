# Tick grammar: FX-EURUSD -- 1 contracts, tick 1e-05, $0.01/tick

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 10 ticks -- 95,709 legs, 1 contracts

### horizon 50 price-changes -- population baseline train +0.02, holdout +0.04 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train +0.07, holdout +0.15 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train -0.00, holdout -0.03 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

## R = 20 ticks -- 29,685 legs, 1 contracts

### horizon 50 price-changes -- population baseline train +0.10, holdout -0.01 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 200 price-changes -- population baseline train +0.24, holdout +0.25 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

### horizon 1000 price-changes -- population baseline train -0.05, holdout +0.02 ticks

No cell reached |t|>=3 on train with enough data. Nothing to screen.

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

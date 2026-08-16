# LEVELRIDE-LADDER against real tick data

The strategy currently deployed and taking orders. It is structurally different from the fade in the way that matters: the fade died because ~3 points of entry error hit a **5-point stop**. LEVELRIDE's stop is **80 points**, so the same error is 3.75% of the risk instead of 60%. Its entry is also triggered BY the crossing in real time, so the level is where price actually is -- the fade computed its level from a finished bar, by which time price had left.

NQ, 8 quarters, 519 sessions, 1-second resolution (finer than the bot's ~2s polling), $1.50 round trip, $2/point, target +260 / stop -80, 4-hour timer, flat at 20:55, 3 concurrent maximum.

**Two ladders, because they are not the same strategy.** The deployed code runs 11 rungs at 0/+-25/+-50/+-75/+-100/+-150. The +$2,471/week backtest describes 3 rungs at 0/+-20.

| ladder | entry slip | side | trades/day | win % | target % | **$/trade** | **$/week** |
|---|---|---|---|---|---|---|---|
| deployed 11-rung | 0.25 pt | real | 7.7 | 37.7% | 9.0% | **$+3.33** | **$+127** |
| deployed 11-rung | 0.25 pt | RANDOM | 8.0 | 38.1% | 8.0% | $+0.29 | $+12 |
| deployed 11-rung | 1.00 pt | real | 7.7 | 36.9% | 8.7% | **$-1.12** | **$-43** |
| deployed 11-rung | 1.00 pt | RANDOM | 8.0 | 38.0% | 7.9% | $-2.37 | $-95 |
| deployed 11-rung | 2.00 pt | real | 7.8 | 36.1% | 8.6% | **$-3.98** | **$-156** |
| deployed 11-rung | 2.00 pt | RANDOM | 8.1 | 36.5% | 8.4% | $-4.30 | $-173 |
| dossier 3-rung | 0.25 pt | real | 4.4 | 36.4% | 9.5% | **$+2.25** | **$+49** |
| dossier 3-rung | 0.25 pt | RANDOM | 4.4 | 37.7% | 9.2% | $+4.29 | $+94 |
| dossier 3-rung | 1.00 pt | real | 4.4 | 35.8% | 9.4% | **$-0.39** | **$-9** |
| dossier 3-rung | 1.00 pt | RANDOM | 4.4 | 38.4% | 9.3% | $+4.28 | $+95 |
| dossier 3-rung | 2.00 pt | real | 4.4 | 35.2% | 9.4% | **$-3.70** | **$-81** |
| dossier 3-rung | 2.00 pt | RANDOM | 4.5 | 35.1% | 8.3% | $-9.62 | $-215 |

## Reading it

The claim is +$2,471/week at 63.9% wins. Compare the real rows with their RANDOM twin at the same ladder and slippage: a breakout system that cannot beat a coin flip on its own trigger events has no directional edge, only exposure. And compare the 0.25pt row with the 2pt row -- if they are close, the wide stop really has made this robust to fill error, which is the structural claim being made for it.


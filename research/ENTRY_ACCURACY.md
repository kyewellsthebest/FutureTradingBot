# Entry price accuracy: do you get the price you asked for?

Two things, measured separately:

- **fill rate** -- how often the order fills at all
- **price accuracy** -- how often the fill lands ON the intended level instead of somewhere worse

NQ, 4 quarters, the leaderboard trigger (>=2pt over 3 bars, faded), the live bot's level (fib 0.118 of the 3-bar wick range), 10-minute window. Slippage is signed from the POSITION's view: positive means a worse price than the level.

| order type | fill rate | exact price | within 1 tick | mean slippage | p90 slippage | **mark +60s** |
|---|---|---|---|---|---|---|
| MARKET | 100% | 0% | 75% | -14.64 tk | +7.36 tk | **+0.26 tk** |
| SELL-STOP | 99% | 0% | 100% | -17.31 tk | -0.52 tk | **+0.07 tk** |
| RESTING LIMIT | 89% | 100% | 100% | +0.00 tk | +0.00 tk | **-2.67 tk** |

## Reading it

**The resting limit already beats both 70% targets.** It fills at its own price by construction, so price accuracy is 100%, and its fill rate is far above 70% because the level sits only a few points away and has ten minutes to be reached.

So neither 70% is out of reach -- both are already exceeded. The mark column is why that does not help. A fill you got at exactly your price is not a good fill if the market only came to you on its way through you. Getting your price and getting a good price are different things, and only one of them can be ordered from a broker.


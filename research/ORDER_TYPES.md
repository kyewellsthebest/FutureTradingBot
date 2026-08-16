# Which entry order type is best, and does any of them save it?

Two different things get called "fill":

- **fill RATE** -- how often you get in
- **fill PRICE** -- what price you get when you do

They trade against each other and no order type maximises both. A market order takes every signal at the worst price; a resting limit gets the best price and misses most of them. That trade-off is what this table measures.

NQ, 8 quarters, 727 RTH sessions, range anchor, $1.33 round trip, 10-minute window, one position at a time, timeouts marked to market. Fill rate is each mode's trade count over MARKET's, since a market order takes essentially every signal.

| config | order type | fill rate | trades/day | target-hit % | $/trade | $/trade before ANY commission |
|---|---|---|---|---|---|---|
| 1 S2-WINNER | MARKET | 100% | 25 | 5.0% | **$-2.81** | $-1.48 |
| 1 S2-WINNER | STOP | 99% | 24 | 4.8% | **$-2.97** | $-1.64 |
| 1 S2-WINNER | RESTING LIMIT | 98% | 24 | 3.9% | **$-4.28** | $-2.95 |
| 1 S2-WINNER | AT-LEVEL (n/a) | 99% | 24 | 10.9% | **$+6.02** | $+7.35 |
| 4 T36-W3 | MARKET | 100% | 25 | 7.4% | **$-2.73** | $-1.40 |
| 4 T36-W3 | STOP | 99% | 24 | 7.1% | **$-2.83** | $-1.50 |
| 4 T36-W3 | RESTING LIMIT | 98% | 24 | 5.8% | **$-4.32** | $-2.99 |
| 4 T36-W3 | AT-LEVEL (n/a) | 99% | 24 | 15.0% | **$+5.92** | $+7.25 |
| - CANON live | MARKET | 100% | 24 | 26.3% | **$-2.79** | $-1.46 |
| - CANON live | STOP | 97% | 23 | 25.1% | **$-3.46** | $-2.13 |
| - CANON live | RESTING LIMIT | 99% | 23 | 18.5% | **$-8.35** | $-7.02 |
| - CANON live | AT-LEVEL (n/a) | 97% | 23 | 33.3% | **$+2.14** | $+3.47 |

## What this answers

**AT-LEVEL is not an order type.** 100% fill rate at the limit price is not something a broker declines to offer -- it is not a thing. It is in the table only to show what the assumption is worth, and the gap between its row and the other three is the entire result being claimed.

**The real orders bracket the truth.** MARKET is the most fills and the worst price; RESTING LIMIT is the best price and the fewest fills. Any real execution sits between them. If both ends lose, everything between them loses, and no smarter order routing changes that.

**The last column is the one that ends the argument.** It strips commission out completely -- free trading, no broker, no exchange fee. If a row is still negative there, then costs were never the problem and neither were fills.


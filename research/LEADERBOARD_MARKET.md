# The ~100% fill-rate version: market entry, no fill assumptions

The question was whether we can simply get a fill rate near 100%. We can: a market order does not wait for price to come to it. What you give up is the level price and the spread you cross.

That makes this the cleanest test of the family, because it removes the one thing the entire dispute is about. No resting limit, no trigger print, no argument about which side of the book the order sits on. The signal fires at the bar close, we are in at the next print, the bracket runs from there.

NQ, 8 quarters, 727 RTH sessions, range anchor, $1.33 round trip, 10-minute window, timeouts marked to market, one position at a time.

| config | mode | trades/day | target-hit % | $/trade | $/day |
|---|---|---|---|---|---|
| 1 S2-WINNER | at-level | 24 | 10.9% | $+6.02 | $+147 |
| 1 S2-WINNER | stop | 24 | 4.8% | $-2.97 | $-72 |
| 1 S2-WINNER | **MARKET** | 25 | 5.0% | **$-2.81** | $-69 |
| 4 T36-W3 | at-level | 24 | 15.0% | $+5.92 | $+144 |
| 4 T36-W3 | stop | 24 | 7.1% | $-2.83 | $-69 |
| 4 T36-W3 | **MARKET** | 25 | 7.4% | **$-2.73** | $-67 |
| 5 T30-LOWDD | at-level | 24 | 19.6% | $+5.85 | $+143 |
| 5 T30-LOWDD | stop | 24 | 9.6% | $-2.79 | $-68 |
| 5 T30-LOWDD | **MARKET** | 25 | 9.6% | **$-2.78** | $-68 |
| 6 CONSERV | at-level | 24 | 17.1% | $+2.81 | $+67 |
| 6 CONSERV | stop | 24 | 11.0% | $-2.80 | $-66 |
| 6 CONSERV | **MARKET** | 24 | 10.9% | **$-2.99** | $-73 |
| - CANON live | at-level | 23 | 33.3% | $+2.14 | $+49 |
| - CANON live | stop | 23 | 25.1% | $-3.46 | $-79 |
| - CANON live | **MARKET** | 24 | 26.3% | **$-2.79** | $-66 |

## What the MARKET rows settle

Whatever the right fill model is, it cannot be better than this one on selection: a market order takes EVERY signal, including the ones a resting limit would have skipped. A limit entry can beat it on price -- by at most the spread -- but only by giving up fills.

So the market row is the honest centre of the range. If it is negative, the family needs the fill model to be doing the work, and the fill model cannot do work a real order book will not do.


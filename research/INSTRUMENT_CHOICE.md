# Which instrument gives the most movement per unit of spread?

I recommended ES as the next data purchase because it quotes tighter than NQ. That was wrong, and the reasoning behind it is worth writing down because it is the kind of wrong that sounds right: a tighter spread IS cheaper per trade, in isolation.

What decides tradability is the spread relative to how far the instrument MOVES:

```
edge         = IC x sigma(horizon)
cost         ~ spread
tradability  ~ IC x [ sigma(horizon) / spread ]
```

The bracketed term belongs to the INSTRUMENT, not the signal. An instrument whose exchange-minimum tick is large relative to its own volatility is **tick-constrained**: its spread cannot narrow to reflect how little it moves, so every crossing eats a large share of the available range.

Sigma is measured from the trade tapes already on disk, RTH only, never differencing across a day break. The spread column is a one-tick FLOOR for every instrument except NQ, where four weeks of top of book gave a measured median of **3 ticks**.

| instrument | price | tick | sigma 1s | sigma 60s | **sigma1s / 1 tick** | **sigma60s / 1 tick** |
|---|---|---|---|---|---|---|
| NQ | 21,362 | 0.25 | 1.651 pt | 11.42 pt | **6.60** | **45.7** |
| GC | 4,691 | 0.1 | 0.572 pt | 2.72 pt | **5.72** | **27.2** |
| YM | 43,412 | 1.0 | 2.843 pt | 16.14 pt | **2.84** | **16.1** |
| RTY | 2,247 | 0.1 | 0.230 pt | 1.31 pt | **2.30** | **13.1** |
| ES | 5,968 | 0.25 | 0.364 pt | 2.43 pt | **1.45** | **9.7** |
| CL | 73 | 0.01 | 0.010 pt | 0.04 pt | **1.02** | **4.3** |

At the spreads that actually exist, NQ moves **2.20** of its own spread per second against ES's **1.45** -- and the ES figure is the friendliest possible assumption, a permanent one-tick quote. So the same IC buys **1.5x more** edge-per-cost on NQ than on ES.

That inverts the recommendation. ES top of book would have cost $20.71 to produce a WORSE answer than the one already bought.

## The part that matters more than the ranking

Instrument choice moves this ratio by a factor of order one. `BOOK_IC.md` measured the gap between the book's edge and NQ's spread at **12x**. Nothing in this table closes a 12x gap -- the best and worst instruments here differ by far less than that.

So the binding constraint is not which market we trade. It is that top-of-book imbalance, one of the most studied predictors in finance, is worth about 0.06 points against a 0.75-point spread. Choosing a different contract is optimising the wrong term.


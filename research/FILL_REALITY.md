# What actually fills: measured from the NQ trade tape

Measured 2026-08-02 on NQM5 (24.9M trades, 21 Mar – 19 Jun 2025, 77 trading
days, 456k contracts/day). Not modelled, not assumed — counted off the tape.

## The number

For every 5-minute bar, count the contracts that printed **at the bar's low**.
That price is exactly where a resting buy limit would have sat.

| contracts printed at the bar's low | share of bars |
|---|---|
| median | **2** |
| ≥ 5 | 14.0% |
| ≥ 25 | 0.5% |
| ≥ 100 | 0.0% |

15-minute bars are the same story (median 2, 15.1% ≥ 5, 0.5% ≥ 25). Average
trade size on NQ is 1.41 contracts; the median print is a single lot.

## Why this matters more than any strategy we have found

Every backtest in this project until now filled a resting limit whenever price
*touched* it. Two contracts trading at your price does not fill a 1-lot sitting
behind 20–50 contracts of queue. The touch happened; your order did not.

The size of the error is not marginal. In ZB the touch-fill convention was
worth **1.06 ticks per trade** — larger than any effect measured anywhere in
the dataset, across 11 billion configs and five independent search methods:

- touch-fill: **+0.386 ticks**  → trade-through required: **−0.671 ticks**
- bare touches earned +2.40t; the ones that traded through lost −0.67t
- break-even needs an **87% fill rate on bare touches** in ZB, 77% in ZN

Against a measured median of 2 contracts at the extreme, 87% is not close to
attainable. That single line explains why every limit-entry book in this
project looked profitable and every market-entry book did not — including the
June 2026 tick study, where 576 of 576 limit configs were profitable and 0 of
200 market configs were.

## The honest fill model

With trades but no book, the defensible rule is:

- price trades **through** the limit by ≥1 tick → **filled** (certain)
- price only **touches** the limit → **assume no fill**

Requiring 25 contracts at the price is equivalent in practice: only 0.5% of
bars clear it, so `minfill=25` and "must trade through" select nearly the same
episodes. A limit one tick above the low sees a median of 5 contracts trade
through it, so stepping the order one tick less aggressive buys a real fill at
the cost of one tick of edge.

## How the Tick MEGA campaign uses this

`stage1t.py` searches every limit config three times, at 0 / 5 / 25 contracts
required. That spans fantasy → optimistic → realistic, and pairing the runs
separates real edge from fill optimism per config.

**Read only the `mf=25` column.** `mf=0` is the convention that inflated every
prior campaign and `mf=5` still assumes something that happens in 14% of bars.
A config whose P&L barely moves from 0 to 25 has an edge that does not live in
the fill assumption — that is the only kind worth trading.

## Corollary for anything we do deploy

The one surviving candidate, MNQ15_fib_v1, earns ~23 ticks per trade, so a
one-tick fill convention is noise next to it (58 → 56 $/wk, −3%). That is why
it survived the trade-through test when nothing else did. Any future candidate
should be judged the same way: **edge per trade must be large relative to one
tick**, or the fill assumption is the strategy.

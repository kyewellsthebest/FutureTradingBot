# Can we be a maker on NQ, and what does it earn?

A taker round trip on MNQ is **0.87pt**; commission only, as a maker in and out, is **0.62pt**. At a 5-minute hold that is the difference between needing IC 0.174 and IC 0.124 -- the second is inside the range real book signals have been measured at, the first is not. So this is not a detail at the edges, it is the HFT lane's binding constraint.

`research/DEPTH.md` measured a **6.6% passive fill rate** on one week of MNQ order-by-order data. If that holds, maker strategies are unbuildable at any signal quality, because 93% of intended entries never happen.

We join the BACK of the best bid queue and advance only when volume TRADES against the bid. Cancels ahead of us would also advance us, but the tape cannot say whether a cancel sat in front of or behind our position, so none are counted -- that understates P(fill). A second containing both a fill and the level breaking is read as a break, for the same reason: the conservative reading is the one that does not flatter the case being tested.

## NQU6 (1,593,494 seconds with a live book)

The half-spread column is a MEDIAN: NQ's spread is heavy-tailed (median 3 ticks, max 434) and its mean is set by moments no order could have rested through. Drift is shown as median/mean, and the MEAN is the one that matters -- P&L adds, so the average is what the account accrues, while a median of 0.00 only says price usually sat still.

| wait allowed | attempts | filled | level left first | rallied away | no outcome | median wait | half-spread earned | drift +10s med/mean | +30s | +60s |
|---|---|---|---|---|---|---|---|---|---|---|
| 30s | 159,889 | **11.5%** | 77.3% | 11.2% | 0.0% | 2s | +2.000 tk | +0.00/+0.03 tk | +0.00/+0.10 tk | +0.50/+0.39 tk |
| 60s | 159,889 | **12.1%** | 80.1% | 7.8% | 0.0% | 2s | +2.000 tk | +0.00/+0.05 tk | +0.50/+0.14 tk | +0.50/+0.39 tk |
| 120s | 159,889 | **12.5%** | 81.9% | 5.6% | 0.0% | 3s | +2.000 tk | +0.50/+0.06 tk | +0.50/+0.22 tk | +0.50/+0.46 tk |

At a 120-second patience, **12.5%** of resting bids fill, in a median of 3 seconds.

A filled entry earns the half-spread it rested across -- median **+2.000 ticks** -- and then the market moves **+0.219 ticks on average** in the 30s after we are committed. That second number IS the adverse selection, and it is the half `DEPTH.md` could not measure. It is positive here, which is NOT the textbook direction and is a reason to distrust it before building on it.

Net of both, a filled maker entry is worth **+2.219 ticks = $+1.11** before the $1.24 commission a maker still pays, so the round trip stands at **$-0.13** before any signal is applied.

Two cautions that decide how much of this transfers:

1. **This is NQ, not MNQ.** We trade the micro. NQ rests 2 lots at the touch and quotes 3 ticks wide; MNQ has a deeper retail queue and a tighter spread, so neither the fill rate nor the half-spread carries over. `DEPTH.md`'s 6.6% came from MNQ order-by-order data and is the number that applies to our execution.
2. **Half-spread captured is not edge.** It is the compensation for providing liquidity, and it is exactly what is lost again when the exit has to cross. A maker in and out earns it twice and a maker-in/taker-out earns it once; neither is a prediction about direction.


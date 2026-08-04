# What we measured, and what it rules out

One session, 2026-08-04. Fifteen hypothesis families tested against a proper
null — a random-entry control, not zero. All fifteen came back empty. This is the record of what was tested, how,
and what the negatives are worth — so nobody spends another month re-digging
ground that has already been dug.

## The headline

**No mechanism in this study beats random entry out of sample.** Not on 5, 15,
60 or 240-minute bars; not on event bars built from 200 million raw trades; not
across 15 markets or 8 contracts or 4 different train/holdout boundaries.

The finding is not "we did not search hard enough". It is stronger and worse:
searching harder makes results *worse*. Configs selected for the best training
performance are consistently **below chance** in the holdout — 19–29% holdout
persistence where a coin flip is 50%. That is what overfitting looks like when
it is finally measured instead of assumed, and it means additional compute
actively selects more overfit configurations.

## The target, priced honestly

Goal was $1,000/week at ~500 trades/week, ≤$30 risk per trade, ≥40% win rate.

Measured on RTY 5-minute bars, best config **by training** at each speed, then
read off the holdout:

| trades/week | honest edge/trade | net at today's cost |
|---|---|---|
| 0–5 | +$2.74 | +$0.44 |
| 5–10 | +$1.37 | −$0.93 |
| 10–20 | −$0.12 | −$2.42 |
| 40–80 | −$0.89 | −$3.19 |
| 150–300 | −$0.91 | −$3.21 |
| 300–600 | −$0.78 | −$3.08 |

Edge does not merely fall below cost as speed rises — it goes **negative**
around 10–20 trades/week. Above that there is nothing to pay costs with. 500
trades/week from one strategy is not a search problem; it is absent from the
data.

## Information content, measured directly

Rather than searching for a strategy, measure whether the features predict
anything at all. Spearman IC against forward returns, 8 NQ contracts, ~200M
trades, train/holdout split by contract:

| feature | holdout IC | consistent across contracts |
|---|---|---|
| trade intensity | +0.0151 | 100% |
| bar range | +0.0142 | 88% |
| bar return (reversal) | −0.0117 | 100% |
| signed volume (delta) | +0.0078 | 100% |
| delta / volume | +0.0055 | 75% |
| cumulative delta | +0.0051 | 38% |
| big-trade share | +0.0025 | 62% |
| size skew at extremes | +0.0006 | 12% |
| **shuffled control** | **−0.0036** | — |

The order-flow features — the ones OHLC cannot express — are barely
distinguishable from the shuffled control. The only consistent signals are
volatility proxies (intensity, range) and weak short-term reversal.

**What that is worth in money:** an IC of 0.015 against a ~$70 payoff spread is
about **$1.06 per trade gross, against $2.30 of costs.** The information is
real and it is roughly *half the size of the transaction costs.* No strategy
design fixes a shortfall in the raw signal.

## Families tested and buried

impulse-pullback · mean reversion · VWAP reversion · opening-range break ·
range-compression break · overnight gap · volume spike · hour-of-day · weekday ·
weekday×hour · cross-market lead-lag · calendar · order-flow imbalance ·
trade-level microstructure (sweeps, absorption, run length, block size)

Markets, all on their own raw tape: NQ, ES, RTY, YM, CL, GC, HG — 39 contracts,
~240 million trades. No 5-minute data in the final round.

Timeframes: 5m, 15m, 60m, 240m, plus event bars (500 trades, 5,000 contracts,
15 points of range — no clock at all).

Impulse-pullback deserves a special note: **every prior campaign in this
project was built on it, and it earns −$2.21/trade out of sample on 5-minute
bars.** "No edge" had, until now, only ever meant "no edge in that one idea".

## Four findings that failed verification

Each looked real. Each died to a control. This is the most useful section here.

| finding | how it died |
|---|---|
| 85% holdout persistence | the sweep was contaminated — live edits gave the frictionless arm six mechanisms the others never saw |
| opening range at +$14.21/trade | the trading day was split at midnight UTC (7pm New York), so "the opening range" measured the middle of the overnight session |
| "edge is real, fees eat it" (the $1,499 case) | same contaminated sweep. Real persistence is 19–29% vs 50% chance — there is no edge for fees to eat |
| 60-minute VWAP reversion at +$22/trade | regime luck. Beat the control in 24 of 52 cells (p=0.76), and on RTY itself averages −$16.6 across split points. It was +$22 only at the one boundary first tried |
| Monday drift at t=10.18 | overlapping forward returns across 15 correlated markets. One independent observation per day gives t=1.04 |
| opening range on 500-trade bars, +$22.71 | 4 cells. At 32 cells: 4 of 9, p=0.75 |
| HG mean reversion, p=0.035 | ~30 tests were run; ~1.5 nominal hits are expected by chance. Corrected: 0.035 × 30 = 1.05 |

## Four defects in our own code

All four were caught by controls, none by a number looking implausible.

- **A clock 1000× wrong.** pandas 3 stores these timestamps in microseconds;
  dividing by 10⁹ compressed 2.5 years into 2 days. ORB saw 3 signals instead
  of ~950.
- **A gap trigger masked out.** Moving the day boundary to 22:00 UTC put the
  first bar of every day inside the maintenance-break mask, and gap fires only
  on the first bar.
- **A regression test that could not fail.** When every case is rejected in
  both versions, "0 mismatches" is true and tests nothing.
- **A contaminated experiment.** Four cost settings run sequentially while the
  engine was being edited between them.

## The methods that produced the negatives

These are the durable output of the session. Any future candidate must clear
all of them.

1. **Random-entry control.** Identical holds, stops, targets, costs, filters —
   entries at random times. Its holdout return is the bar to beat, *not zero*.
   Essential: in a holdout where RTY rose 116 ATRs, zero is not the null.
2. **Drift adjustment.** Each trade is charged the market's average per-bar
   move over its own split, times duration and side. A chronological holdout is
   one directional regime, so "worked out of sample" otherwise quietly means
   "was long during a rally".
3. **Many cells and a sign test.** 15 markets or 8 contracts × 4 split points.
   A real edge wins most cells; regime luck wins the cell it was found in.
4. **Select on train, report holdout.** The upper envelope of thousands of
   random configs is a noise ceiling.
5. **Test the engine before the hypothesis.** `control_mech.py` proves the
   impulse-pullback path is unchanged and every mechanism reaches a P&L book,
   and refuses to pass vacuously.

Tools: `robust.py`, `tick_robust.py`, `edge_curve.py`, `friction_paired.py`,
`calendar_scan.py`, `orderflow_ic.py`, `control_mech.py`, `tickbuild.py`.

## What would actually change the answer

Not more compute, and not more parameter search over this data — that is the
one thing measured to be counterproductive.

- **Different information.** Everything here is price and trade prints. Depth
  of book (order queue, cancellations, iceberg detection) is a genuinely
  different signal and is what the firms harvesting the ~$1/trade of available
  information actually use.
- ~~**Lower costs.**~~ Tested and ruled out. At $0.72 round turn — the
  cheapest tier available — the one real signal still loses to random entry
  (13 of 32 cells, p=0.89). See "statistical edge is not tradeable edge":
  commission was never the binding constraint.
- **A different question.** Longer horizons (multi-day), where the ratio of
  edge to cost is far better, are not ruled out by this study — nothing here
  tested holding periods beyond a few days.

## Costs, corrected

The commission figures used through most of this study were guesses, and
several were badly overstated. Built from components -- Tradovate broker per
side plus exchange, clearing and NFA:

| plan | broker/side | NQ ES RTY YM GC | HG | CL |
|---|---|---|---|---|
| free | $0.39 | $1.32 | $1.52 | $1.82 |
| $99/month | $0.29 | $1.12 | $1.32 | $1.62 |
| $1,499 lifetime | $0.09 | **$0.72** | $0.92 | $1.22 |

This changes none of the nulls: the random-entry control pays the same
commission, so cheaper trading cannot help a mechanism beat it.

## Statistical edge is not tradeable edge

The most useful thing learned here. Signed volume genuinely predicts forward
returns -- IC +0.0098, same sign in 8 of 8 contracts. Solid measurement.

Traded as a mechanism at $0.72 round turn, the cheapest commission obtainable,
it beats the random control in **13 of 32 cells (p=0.89)** and earns -$1.91 a
trade against the control's -$0.05.

Cheaper commission cannot rescue it, because commission was never the binding
constraint. Turning a 1% correlation into a position requires choosing an
entry price, a stop distance, a target and a time limit, and each of those
injects variance far larger than the signal. The edge does not get eaten by
fees; it gets eaten by **discretisation**.

Any future claim of the form "there is an edge, the costs are just too high"
should be checked against this. Lowering costs did not help.

## The one-line version

The data contains roughly half the edge needed to pay its own transaction
costs; the part that is real is too small to survive being turned into a
trade; and the search methods that appear to find more are measurably
selecting noise.

# What we measured, and what it rules out

One session, 2026-08-04. Thirteen hypothesis families tested against a proper
null. All thirteen came back empty. This is the record of what was tested, how,
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
weekday×hour · cross-market lead-lag · calendar · random control

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
- **Lower costs.** The measured signal is ~$1/trade against $2.30 of cost. That
  gap closes at market-maker economics, not retail — the lifetime commission
  plan halves the broker's slice but not enough to invert the sign.
- **A different question.** Longer horizons (multi-day), where the ratio of
  edge to cost is far better, are not ruled out by this study — nothing here
  tested holding periods beyond a few days.

## The one-line version

The data contains roughly half the edge needed to pay its own transaction
costs, and the search methods that appear to find more are measurably selecting
noise.

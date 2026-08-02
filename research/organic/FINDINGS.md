# Organic Behaviour Discovery — Campaign Result (2026-08-02)

8 explorers measured behaviour across the full framework. 21 findings produced.
21 independent adversarial verifiers attacked them. **19 killed, 2 survived —
and both survivors are kills of the incumbent premise, not new edges.**

## The decisive numbers (independently reproduced)

Resting a BUY limit 2 ticks below the close, TTL 6 bars, 12-bar horizon,
discovery split only:

| | ZB | ZN |
|---|---|---|
| Incumbent state (24-bar impulse >1.25xATR, calm vol) | +0.467 t | +0.627 t |
| **ALL BARS — no state at all** | **+0.386 t** | **+0.609 t** |
| Signal contribution | 17% | **3%** |
| Fill on TOUCH (our assumption) | +0.386 t | +0.609 t |
| Fill only on TRADE-THROUGH | **-0.671 t** | **-0.450 t** |
| Value of the fill convention | **1.06 t** | **1.06 t** |

Decomposed:

| | ZB | ZN |
|---|---|---|
| Bare-touch ("kiss") fills | 13,608 @ **+2.40 t** | 19,531 @ **+2.58 t** |
| Traded-through fills | 25,953 @ **-0.67 t** | 36,300 @ **-0.45 t** |
| Cost floor (commission + stop slip) | 0.294 t | 0.438 t |
| **Break-even fill rate on bare touches** | **87%** | **77%** |

## What this means

1. **The strategy contributes almost nothing.** In ZN the impulse/calm-vol
   condition adds 3% of the measured edge; in ZB, 17%. The rest is "rest a
   limit anywhere in this market". Three campaigns of signal search were
   optimising a rounding error.
2. **The entire edge lives inside the fill convention.** Whether a bare touch
   fills is worth 1.06 ticks — larger than every effect measured anywhere in
   this dataset, including the edge itself.
3. **The money is in exactly the fills you are least likely to get.** Bare
   touches (price kisses your price and leaves; you are at the back of the
   queue) earn +2.4 to +2.6 ticks. Fills where price traded through you —
   the ones you are guaranteed — LOSE 0.45 to 0.67 ticks.
4. **Post-fill directional drift is zero.** Confirmed independently. There is
   no prediction happening. This is a queue-position business.

## Verified kills of previously-believed results

- **Toxic 11:30-14:30 window** — reproduces, but matched on realized forward
  volatility the disadvantage vanishes and FLIPS positive. It was volatility.
- **"Fixed 2-3 tick natural target"** — an artefact of core.py's own
  `TIME_EXIT_SLIP_TICKS=1.0` placeholder. At slip=0 the curve is flat from
  3 to 8 ticks. It is also 1.25x ATR in disguise.
- **Provision clock (good/bad hours)** — anti-persistent: half-split hour-rank
  correlation ~0. Selecting hours on H1 and trading them on H2 loses money.
- **Penetration law** — reproduces in full on a driftless random walk. An OHLC
  accounting identity, not a market law.
- **Rates fade fast moves / fade after extremes** — bid-ask bounce and
  closing-print artefacts; removing the "fast move" filter changes the number
  by 0.01-0.03 t.
- **ES negative-excursion skew** — five crash days. One tariff-crash day is
  26.6% of the effect; dropping 10 of 417 days removes it entirely.
- **Compression / "calm predicts expansion"** — session confound (the calm
  bucket is 86% Asia). Within Asia the bottom three buckets are identical.
- **Deep down-spike asymmetry** — 82% of the gap is a directional long bias
  from the sample's bond rally, not a state effect.

## Measured and empty (do not re-run)

- Multi-bar formations carry no out-of-sample information beyond the last bar.
- Shape conditioning does not rescue a limit order (1,437 cells tested).
- Destinations are null: price does not seek prior-day levels, day open, round
  numbers or ATR multiples in ZB/ZN at 5-min resolution, versus a
  distance-matched baseline.
- State conditioning adds nothing to the touch curve (20 states swept).
- All four inversions of "buy pullbacks in calm vol" are also nothing.
- Systematic 2-axis scan across 4 rates markets x ~22 cells: nothing.
- 7 of 9 other affordable markets are cost-dead, purely on commission-per-tick.
- ES/GC limit fills are pure trend exposure, not provision.
- No up/down speed asymmetry in bonds.
- Two-sided quoting from one margin slot destroys ~2/3 of any edge.
- The no-stop policy maximises expectancy but risks -$2,723 on a $4,100 account.

## Corrections to our own tooling

- `ADVERSE_BUFFER_TICKS = 0.5` is too small by ~2x (measured gap between
  touch-fill and trade-through-by-1-tick is ~1 tick).
- `TIME_EXIT_SLIP_TICKS = 1.0` is a placeholder that manufactured a false
  "natural target" finding. Any result sensitive to it must be reported
  across the range.
- ZB is NOT temporally stable and should rank behind ZN despite better
  commission ratio (QUIET buy: H1 +0.762t, H2 +0.405t, degrading).

## The one experiment that settles it

Everything now rests on a single measurable quantity: **in live trading, what
fraction of bare touches actually fill?** ZB needs 87%, ZN needs 77%.

This is NOT answerable from OHLCV, and it is NOT answerable from the demo
account if Tradovate's simulator fills on touch (which would reproduce our
own assumption and tell us nothing). It is answerable by logging, for every
resting limit: did the bar touch our price, and did we fill?

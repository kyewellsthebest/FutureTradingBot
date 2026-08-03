# Portfolio preview — what stacking streams actually buys

Run 2026-08-03 while the full 228-job search was still going. Six markets
(NQ, ES, GC, CL, RTY, YM), 15-minute bars, depth 2, one shard of six — call it
a sixth of the resolution of the real thing. Trade-through fills only; every
bare-touch limit config was dropped before assembly.

## The book

| correlation cap | streams | trades/wk | holdout $/wk | holdout Sharpe | positive weeks |
|---|---|---|---|---|---|
| 0.35 | 29 | 116 | 1,220 | 1.52 | 97% |
| 0.55 | 54 | 230 | 2,281 | 1.68 | 97% |
| 0.75 | 72 | 272 | 2,557 | 1.69 | 100% |

Streams are chosen on 119 training weeks; the 30 holdout weeks were never used
to select. Mean pairwise correlation in the 0.55 book is **+0.084** — roughly
10 effective independent bets and a 2.2x variance reduction, so this is real
diversification rather than one trade held fifty-four times.

## Does selection actually work?

Yes, and this is the number that matters more than any dollar figure.
**Spearman(train $/wk, holdout $/wk) = +0.701** across 7,200 candidates,
monotone through every decile:

| decile by train $/wk | train | holdout |
|---|---|---|
| 1 (worst) | 6.4 | 5.6 |
| 5 | 18.0 | 24.6 |
| 9 | 53.2 | 77.2 |
| 10 (best) | 107.6 | **92.2** |

Decile 10 regressing downward is the healthy part: the very best in-sample
performers give some back out of sample, exactly as overfitting predicts.
A book built from them should be expected to land below its training figure.

An earlier read of this looked damning and was wrong, worth recording so it is
not repeated. Optimised books beat train by 1.20x out of sample and *randomly
chosen* books beat it by 1.19x, which looked like proof that selection adds
nothing. It is not: random books were drawn from an already-gated pool, so
that comparison cannot see selection skill at all. The ratio is equal because
the period effect is uniform, not because picking is worthless.

## Discount the dollars by about 18%

Holdout-week P&L dispersion across all candidates is **1.15x** the training
period, and mean candidate P&L is **1.18x**. Bigger moves, so everything
earned more — gated or not. Some of $1,220/wk is the window being kind rather
than edge, and a normal period should be expected to pay less.

## The blocker: one family, and therefore not enough trades

Median config fires **4.1 times a week**. Only 446 of 14,252 clear 20/week.
Screening the pool for frequency backfires outright:

- require >= 10 trades/wk -> book collapses to **4 streams**
- require >= 20 trades/wk -> **1 stream**

because the high-frequency configs are nearly all NQ/fib and correlated with
each other. The root cause:

**14,244 of 14,252 surviving candidates are `fib`.** Six are `vwaprev`, one
`momcont`, one `failbrk`. Every other family — brk, fade, mapull, orb,
squeeze, todmom, exhaust — dies at the gate.

Two consequences. Three hundred to five hundred trades a week cannot come from
filtering this pool, only from families that are not fib. And a book that is
99.9% one mechanism is one regime change from going to zero all at once,
however many streams and markets it is spread across.

That is the thing to fix next, and it is a search problem rather than an
assembly problem.

## Still unresolved

Peak concurrent margin. Twenty-nine to fifty-four live streams on a ~$4,100
account has not been checked, and the weekly P&L vectors cannot answer it —
they carry no trade timestamps. Needs per-trade data from an exact replay
before any of this is sized.

---

# Pivot log — 2026-08-03

Standing instruction from here: when something does not work, pivot without
waiting to be told. Record dead ends so they are not re-dug.

## DEAD: cross-market signals (`stage1x.py`)

Built on the theory that all 34 families collapse to one mechanism because
they all read the same market's own price history. Four new families using
*other* markets — beta-hedged spread reversion, lead-lag, divergence catch-up,
and breadth — single leg only, because a spread trade pays two round turns and
at the 2x-cost optimum the second leg eats the entire edge.

13 partners loaded, 1.59M configs, 404 gated. **1.0% holdout-positive.**
Out-of-sample losses of $1,967 to $11,249 per config. Tested both directions:
fading a stretched spread is 0.5% positive, following it 5.6%, and the "with"
direction mostly failed to clear the gate at all. Profit factors of 1.13-1.21
against fib's 1.5-2.2 -- edge too thin to survive selection from 1.59M
candidates. Closed.

## LIVE: short-lookback pullbacks (`stage1f.py`)

Anatomising the family that does work turned up the one lever that buys
frequency without costing edge. Grouping fib candidates by lookback:

| lookback | trades/wk | holdout $/wk | holdout-positive |
|---|---|---|---|
| 8 | 8.77 | 154 | 100% |
| 12 | 3.06 | 20.65 | 97% |
| 24 | 2.97 | 41.93 | 99% |
| 48 | 4.02 | -1.58 | 36% |

Five configs out of 3,353 sat at the 8-unit lookback; they fired 3.4x more
often than the median and were positive in every holdout week. The grid was
stepping over the best corner of the space.

A dense sweep of that corner — lookbacks 1-24, pullbacks out to 1.5 (past a
full retracement, which nothing had tested), stops down to 0.2 ATR, holds down
to 5 minutes — gives 5.6M configs, 23,902 gated, **100% holdout-positive**.
Best single config:

    lb 20, k 1.25, pb 1.00, stop 2.0 ATR, target 1.5R, trail 2.5
    19.96 trades/week | $2.90/trade | PF 1.31 | 2,196 trades | holdout +$2,751

$2.90 a trade is close to the $2.84 that maximises weekly Sharpe on MNQ, and
five times the frequency of the earlier survivors. The winner uses pb=1.00, a
full retracement — a value outside the original grid, so the broad search
could not have found it.

Caveat found in the same table: at 15-minute bars, `sb()` collapses lookbacks
of 1, 3 and 5 units onto a single bar, so the shortest lookbacks are simply
not expressible there. The 5-minute sweep is where that corner actually opens
up, and it is running.

## Commission is the frequency ceiling — but not for the reason predicted

The previous commit predicted that below some round turn the market-entry
variants would stop being unprofitable, since a market order fills every
signal and only loses a tick. **That prediction is wrong and the data is
unambiguous: zero market-entry configs survive at $1.42, zero at $0.90, zero
at $0.62.** Market entries are not a cost problem. They have no edge.

Cheaper commission does raise the ceiling, by a different route entirely —
fill rate.

| round turn | best trades/week | on-spec configs >= 90/wk |
|---|---|---|
| $1.42 | 65 | 0 |
| $0.90 | 118 | 1 |
| $0.62 | 118 | 7 |

The mechanism is visible in how pullback depth trades off against fill
frequency:

| pullback | trades/week | $/trade |
|---|---|---|
| 0.62 | 33.2 | 2.99 |
| 0.79 | 38.2 | 2.98 |
| 1.27 | 12.0 | 4.90 |
| 2.50 | 14.0 | 4.81 |

A shallow pullback is hit about three times as often but captures roughly half
as much. At $1.42 the shallow end cannot clear cost, so every survivor is a
rare deep pullback and frequency stalls near sixty a week. At $0.90 the whole
shallow end becomes viable and the ceiling nearly doubles. The benefit is
saturated by $0.90 -- $0.62 buys more qualifying configs but no more speed.

Best single strategy at $0.90, which meets every line of the spec:

    NQ 5-min, 2.5x impulse over 12 bars, limit at 62% retracement,
    stop 2.0 ATR, target 1.5R
    118 trades/wk | 47.5% win rate | 1:1.5 | $2.64/trade | $311/wk
    PF 1.36 | 84.5% of weeks profitable | worst drawdown -$395

Caveat that governs the whole result: $0.90 and $0.62 are estimates of the
broker's tiers, not verified figures. The defensible claim is that a ~35% cost
reduction roughly doubles achievable frequency; whether a given plan delivers
that has to be read off the actual account.

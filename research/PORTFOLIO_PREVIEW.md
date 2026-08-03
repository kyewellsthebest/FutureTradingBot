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

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

## The break-even round turn — what 500 trades a week actually costs

Every search until now gated on profitability at today's $1.42 round turn,
which deletes the high-frequency strategies before they can be measured. So
the search could never answer the only question that matters about them: what
would they need to cost to work? Running commission at zero and reporting
gross edge answers it directly, because gross edge IS the break-even round
turn.

NQ 5-min, 2.5x impulse over 12 bars, stop 2.0 ATR, target 1.5R. Only the
pullback depth varies. Note the grid previously started at 0.382, so the top
five rows had never been searched at all.

| pullback | trades/wk | gross $/trade | break-even round turn | net/wk @ $1.42 | net/wk @ $0.62 |
|---|---|---|---|---|---|
| 0.20 | 517 | 0.83 | **0.83** | -305 | +106 |
| 0.25 | 488 | 1.22 | **1.22** | -98 | +294 |
| 0.30 | 459 | 1.56 | **1.56** | +64 | +433 |
| 0.38 | 413 | 1.88 | 1.88 | +190 | +521 |
| 0.50 | 354 | 2.34 | 2.34 | +326 | +609 |
| 0.62 | 304 | 3.22 | 3.22 | +547 | +789 |

**A 500-trades-a-week strategy needs a round turn of $0.83 or better.** That
sits below the current $1.42 and above the ~$0.60-0.75 floor of exchange,
clearing and NFA fees, which is the part no plan can remove. So the target is
not blocked by the market. It is blocked by broker commission, and broker
commission is purchasable.

At the fee floor a single strategy runs 304 trades a week for $789, or 488 for
$294. Two uncorrelated strategies clear both halves of the spec inside the
four-strategy limit.

### Two caveats that govern this

The table is computed across all data, not split train and holdout. It was
built as a mechanical cost curve rather than a validated strategy: the shape,
frequency against break-even, is structural and trustworthy; the dollar
figures are not yet out-of-sample.

More seriously, the engine still exits stops at the stop line and charges no
slippage. A real stop is a market order and gives up about a tick. At 500
trades a week that is roughly $0.50 a trade, which would move the break-even
from $0.83 to about $0.33 — below the exchange floor, where no purchase helps.
**This single modelling gap can invalidate the whole table**, so it is the next
thing to fix, before any money is spent on plans.

## 1,000 trades a week: an arithmetic wall, and where it moves

A five-minute session holds about 1,380 bars a week. A thousand trades means
entering on 72% of them, which is not a strategy, it is a coin landing on its
edge. At one minute there are 6,900 bars a week and the same thousand trades
is 14% of them. **The bar interval, not the signal, is what makes the target
impossible or possible**, and no amount of searching five-minute data fixes it.

Economics of the target, for reference:

| round turn | gross needed per trade | in MNQ ticks |
|---|---|---|
| $1.42 today | $2.42 | 4.8 |
| ~$0.90 Lifetime | $1.90 | 3.8 |

An average one-minute MNQ bar spans roughly four to six ticks, so 3.8 ticks is
a large share of one bar's range -- but the hold does not have to be one
minute. Bar interval governs how often you can ENTER, nothing else. A signal
found on a one-minute bar can be held forty minutes.

Margin, which is the constraint that actually bites on a $4k account:

| average hold | positions open | peak | margin at peak |
|---|---|---|---|
| 10 min | 1.4 | ~4 | ~$435 |
| 20 min | 2.9 | ~9 | ~$870 |
| 30 min | 4.3 | ~13 | ~$1,300 |
| 60 min | 8.7 | ~26 | ~$2,600 |

Anything up to a thirty-minute average hold is affordable. An hour is not.

Note the one-minute series is shorter than the five-minute one -- 94 weeks
against 138 -- so its holdout is 19 weeks rather than 30, and results from it
carry correspondingly less weight.

## Finer bars are the wrong lever — measured, not argued

Same strategy, same clock-time parameters, only the bar interval changing:

| pullback | 5-min trades/wk | 5-min gross | 1-min trades/wk | 1-min gross |
|---|---|---|---|---|
| 0.20 | 517 | 0.83 | 566 | 0.09 |
| 0.30 | 459 | 1.56 | 431 | 0.22 |
| 0.50 | 354 | 2.34 | 249 | 0.06 |

Five times the bars buys nine percent more trades at 0.20 and *fewer* at 0.50,
because de-overlapping is enforced in clock time rather than bars: two signals
ninety seconds apart are the same trade whichever interval you view them
through. Slicing the clock thinner re-samples existing setups, it does not
create new ones.

Worse, gross edge collapses by roughly ten times. Finer sampling catches the
limit on brief spikes that immediately reverse, so you fill on the worst
instances of each setup. That is adverse selection, and fine bars maximise
exposure to it. Thirty-second bars should be expected to be worse again on
both counts.

Worth separating clearly: entering the same setup five times in ten minutes is
one trade at five times size, not five trades. That is leverage, and it makes
an equity curve rougher. Smoothness comes from independent trades, and the
supply of genuinely independent setups in one market is about 500-600 a week,
of which 300-450 carry positive edge. That is a property of the market, not of
the search.

## Frequency is uniform across markets; edge is not

Same shape (12-bar lookback, 2.5x impulse, pullback 0.62, stop 2 ATR,
target 1.5R) on each market:

| market | trades/wk | gross $/trade | net/wk @ $0.62 | net/wk @ $0.90 |
|---|---|---|---|---|
| NQ | 304 | 3.22 | +790 | +705 |
| GC | 292 | 1.76 | +332 | +251 |
| ES | 299 | 0.87 | +76 | -9 |
| RTY | 291 | 0.50 | -35 | -95 |
| CL | 293 | 0.40 | -63 | -122 |

Every market yields the same ~300 trades a week at this depth. Edge varies
eightfold. So a thousand trades a week is three or four markets at five
minutes, never finer bars on one -- and whether the third and fourth markets
pay depends entirely on the round turn.

NQ + GC alone is 596 trades a week and $1,122 at $0.62, or $956 at $0.90.
Adding ES reaches 895 trades and $1,198, but only at $0.62; at $0.90 ES is
negative.

Caveat: one config shape was tested per market rather than searching each
properly, so these are floors. And stop slippage is still uncharged.

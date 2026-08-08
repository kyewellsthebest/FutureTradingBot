# Engine V3: from parameter optimizer to tick-level behavioural discovery

## 1. Audit of the current engine — what it can and cannot see

What exists today (`fxbillions.py`, `fxmega.py`, `ticksim.py`):

- **Representation:** bars (tick-count and clock), then rolling-window features
  of CLOSES: momentum, reversion, range position, acceleration. Even the
  "tick" bar types collapse 200–10,000 prints into four numbers before any
  question is asked.
- **Hypothesis form:** `feature > threshold` ANDed 1–3 deep, hold N bars,
  fixed exits. Scored by matrix multiply; 1.38B configs/hour.
- **Truth machinery:** one chronological 70/30 split, random-entry controls,
  shuffled/shifted controls, signed-log selection curve.

What it is **fundamentally incapable of seeing** — the gaps, ranked:

1. **Path.** Two windows with the same close have identical features. The
   engine cannot distinguish +20→−5→+10 from +20→−15→+10. Every question in
   the form "impulse, then retracement of depth d, at speed v" is invisible.
2. **Event time.** Bars average away speed. "This 10-tick move took 40 prints
   in 2 seconds" vs "400 prints in 4 minutes" are the same bar. Velocity,
   acceleration, burst/drought structure: invisible.
3. **Confirmation-causal events.** Bar features are anchored to arbitrary bar
   edges, not to the moment a market event becomes *knowable* (a reversal is
   only known once price has come back R ticks). The engine has no concept of
   "the instant this pattern completed."
4. **Sequence/state.** Nothing conditions on the previous *event* (failed
   breakout #2, third test of a level). ANDs of simultaneous conditions are
   not state machines.
5. **Normalization.** Thresholds are absolute (pips, z of one window). The
   same behaviour at different volatility scales lands in different cells and
   is never pooled. Cross-market transfer is impossible by construction.
6. **Families vs champions.** The tally reports selection curves but has no
   neighbourhood concept: a cell that works while all its neighbours fail is
   indistinguishable from a stable region.
7. **Trade management.** Exits were swept once (13 rules) but never made
   conditional on post-entry behaviour.
8. **Negative information.** "Expected X, got nothing" is not representable:
   there is no expectation model to fail against.
9. **Memory of failures.** Nulls live in prose logs; nothing stops the next
   search from re-deriving them.

## 2. The new representation: the tick tape as a grammar of LEGS

Primary object: not a bar, not a tick — a **leg**, produced by a reversal
threshold R (in ticks): price runs in one direction until it retraces R ticks
from its extreme. Multi-scale: R ∈ {4, 8, 16} on NQ, and R can also be set
relative to recent volatility (scale invariance).

Causality rule, non-negotiable: a leg's completion is only KNOWN at the
**confirmation print** — the first print R ticks off the extreme. Every
conditioning feature uses data up to confirmation; every outcome is measured
FROM the confirmation price forward. No look-ahead, ever. (The user's-strategy
study earlier in this project manufactured a 50.6%-at-2:1 fantasy from exactly
this mistake; the grammar makes it structurally impossible.)

Each completed leg carries the attributes the questions need:

    dist      ticks from origin to extreme        (movement questions)
    nchg      price changes in the leg            (event counts, not clocks)
    dur       wall time origin→extreme            (speed)
    vel       dist/dur                            (velocity)
    vol       contracts traded in the leg         (volume/price relations)
    retr      dist / previous leg's dist          (retracement depth)
    conf_lag  prints from extreme to confirmation (how the reversal happened)

All normalized by the rolling median of the trailing 200 legs (shifted — the
current leg never normalizes itself). Normalized attributes make markets and
epochs comparable, which is what lets eight contracts vote on one behaviour.

A sequence of legs IS a path; conditioning on the last k legs IS a state
machine of depth k; "compression" is a run of small-dist legs; "exhaustion" is
a high-vel leg followed by a low-vel one; "failed breakout" is a leg whose
extreme exceeds the prior extreme by < e ticks and whose next leg confirms
against it. The 100 questions in the brief are queries against this one
representation — they do not need 100 engines.

## 3. The question form: conditional expectancy tables, not backtests

For every confirmation event, ask: **given the (binned, normalized) attributes
of the leg(s) just completed, what is the distribution of the signed forward
move over the next F price-changes?** (F ∈ {50, 200, 1000} — event horizons,
not clocks.) Sign convention: positive = continuation of the newly confirmed
direction.

Per cell: n, mean, t-stat, win rate — on TRAIN; the same on HOLDOUT, plus:

- **the event-population baseline.** After a peak confirmation the population
  itself drifts; a cell must beat the baseline of all events at its scale,
  not zero.
- **neighbourhood stability** (Part 29): share of ±1-bin neighbours with the
  same holdout sign. A cell whose neighbours disagree is a lottery ticket.
- **contract agreement**: the behaviour is pooled across 8 NQ contracts with
  per-contract normalization; report how many of the 8 hold the sign
  out-of-sample. Eight cells is a vote; one cell is a regime.
- **the cost gates**, applied at screening and not before: gross mean in
  ticks × $0.50 (MNQ) against $1.42 (commission-only) and $4.40 (the user's
  commission+slippage figure). Discovery measures gross behaviour; the gate
  decides what graduates.

Bin edges are computed on TRAIN ONLY and frozen. Shuffled-outcome control runs
alongside; a synthetic random-walk tape must produce nothing but the false
positive rate before the engine touches real data — the engine that cannot
find nothing in nothing cannot be trusted with something.

## 4. Pipeline hierarchy (Parts 27–28)

    DISCOVERY    grammar tables, gross, pooled, controls inline
    SCREENING    train t>=3, n>=400/150, neighbourhood >=60%, cost gates
    VALIDATION   held-out 30% + per-contract sign vote (>=6 of 8)
    ROBUSTNESS   parameter-neighbour perturbation (R±, bin±, F±), cost x2,
                 entry delayed by 1-3 prints
    OOS          untouched: the newest contract(s), never read until here
    ADVERSARIAL  bootstrap the trade sequence; random trade removal; the
                 existing random-entry machinery
    PORTFOLIO    correlation of surviving behaviours at trade/day/week level

## 5. The ledger (Part 26)

`research/HYPOTHESIS_LEDGER.md` — append-only. Every family ever searched,
its cell count, its verdict, its cost sensitivity. Seeded with the sixteen
null families, the 1.38B-config selection curve, the exit-rule sweep, and the
imbalance findings, so no future search rediscovers a corpse.

## 6. Honesty about the hurdle, stated before any result exists

The brief sets the hurdle at $4.40/trade ($1.40 commission + $3 slippage).
Facts already measured by this project that bear on it:

- Total information content in NQ trade prints was measured at ≈ $1.06/trade.
  A taker behaviour clearing $4.40 must be **4x larger than anything found in
  two years of tape** — possible only if event-space conditioning concentrates
  the diffuse $1.06 into rare, fat cells. That is precisely what this engine
  tests, and the test can fail.
- The $3 slippage figure is a taker assumption. For limit/confirmation
  entries (Part 8) the cost structure is different, which is why both gates
  are reported. If behaviour clears $1.42 but not $4.40, the finding is
  "real but only tradeable passively" — that routes to the maker work
  (mm_study), not to the bin.
- Meta-search (Part 25), regime clustering (Part 12), adaptive exits (Part 7)
  are Phases B/C — they only earn compute if Phase A's tables contain any
  cell that survives screening. Building them first would be building the
  penthouse before the ground floor bears weight.

## 7. Build order

    A  leg grammar + conditional expectancy tables       <- built now
    B  location features (session extremes, round numbers, prior pivots)
       and failed-expectation events (breakout-no-follow-through etc.)
       as additional conditioning columns
    C  depth-2/3 sequences (state machines), regime clustering as
       discovered conditioning columns
    D  conditional trade management (post-entry behaviour -> exit policy),
       searched ONLY on entries that survived A-C
    E  meta-search loop + ledger automation

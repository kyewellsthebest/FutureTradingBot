# How the researcher learns

Written for the person who has to decide whether to trust it.

---

## The one-sentence version

It used to be an **eliminator** — very good at proving ideas dead, and
that was all. It is now also a **cartographer** (it keeps a map of which
regions of the space pay), a **meta-analyst** (it combines every market's
answer into one verdict instead of asking each market separately), and a
**diagnostician** (when something fails it names *which* failure mode,
not just *that* it failed).

It is still not a **theorist**. See "What it still cannot do".

---

## 1. It asks each question once, of every market at once

**This is the biggest change, and it is both a statistical and a
scientific upgrade.**

Before: *"after a close near the low, go long"* was tested as twenty-three
separate hypotheses — once in MNQ, once in ES, once in ZB. That is one
idea being charged twenty-three times.

Two costs, and the second is worse than the first:

| | before | after |
|---|---|---|
| trials spent on 10,000 mechanisms | 230,000 | 10,000 |
| bar those trials imply | **5.79σ** | **4.87σ** |
| evidence behind each verdict | one market | up to 23 markets |

The multiplicity saving is real but secondary. The important part is
**power**. A genuine mechanism is usually *weak and broad* — 1.5σ in
fifteen markets, not 8σ in one. The old scheme could not see that at
all: every individual cell failed, and the idea was recorded as dead
twenty-three times over.

Meanwhile **8σ in exactly one market is the signature of an artifact**,
and the old leaderboard ranked it first. It literally had the ordering
backwards.

### How the pooling avoids lying

Three defences, all required, all tested (`researcher/pooled.py`):

- **Correlated markets are discounted.** ES/NQ/YM/RTY are one bet wearing
  four tickers. Treating them as four replications inflates z by up to
  1.5×. Measured in the self-test: four equity indices give 10.0σ if
  treated as independent, **6.6σ** in truth.
- **Disagreement is penalised.** If markets differ more than their own
  error bars allow, the pooled error absorbs the excess (random-effects
  meta-analysis). Self-test: one market at 40σ surrounded by seventeen
  saying nothing pools to **1.00σ**, not to a finding.
- **Sign agreement is required.** ≥65% of markets must point the same
  way. A single huge market cannot drag the mean positive on its own.

Self-tested both ways: pure noise across 20 markets gives p99 |z| =
**2.50**; a genuinely weak effect (1.8σ per market) is found at **7.6σ**
pooled. That second number is the whole point — that effect was
previously invisible.

**Only pre-stated mechanisms are pooled.** Footprints found in NQ's own
tape and features grown from NQ's own returns are market-specific by
construction; pooling them would be averaging different questions and
calling it an answer.

---

## 2. It keeps a map of the space, built from its own failures

`researcher/surrogate.py`

The ledger holds 200,000+ measurements and used them for exactly one
thing: refusing to repeat them. That is the most expensive asset the
project has, used as a blacklist.

Now an additive, shrunk model predicts a hypothesis's cost-normalised
edge **before** it is tested, from its attributes (hold length,
direction, exit style, shape, condition, market, tier), with an error
bar. Two uses:

**Ordering.** The same budget, spent on the most promising and the
*least understood* candidates first. 35% of every cycle deliberately
goes to the model's blind spots rather than its favourites.

> Nothing is skipped and nothing is cheapened. Every hypothesis tested
> still pays a full trial and faces the same rising bar and the same
> gauntlet. Only the order changes, and order is free.

**Saying what it has worked out.** This is new and it is the answer to
"is it actually learning?". Statements like:

> `hold = 0-90s` — **0.31 round trips per trade worse** than average,
> over 18,400 tests

That is a claim about *the market*, with a direction, a magnitude in a
comparable unit, and a sample size. It is checkable and arguable.
Everything the Learning tab showed before was a claim about the
*searcher* ("effort reduced here").

**Why an interpretable model when LightGBM is installed.** It would fit
better and explain nothing, and the second use above is at least as
valuable as the first.

**The risk, stated plainly:** ordering enriches the tested set toward
what looked good on this tape before. That cannot manufacture
significance — the bar counts trials spent, the vault is untouched, a
pooled mechanism must hold in markets it was not chosen from — but it
does concentrate attention where this particular history was kind. The
35% explore share bounds it.

---

## 3. It names the cause, not just the death

`researcher/diagnose.py`

`plausible.py` is a smoke alarm: it knows 96% win rates are impossible
and lists the usual suspects. It cannot say **which**.

But the suspects are *distinguishable*, because each responds
differently to a different perturbation:

| perturbation | a real edge | a timing leak | a drift |
|---|---|---|---|
| enter one bar later | mostly survives | **collapses** | survives |
| enter five bars later | decays slowly | already gone | survives |
| double the cost | shrinks by cost | irrelevant | shrinks |
| slide the signal +30 min | collapses | collapses | **survives** |

No single test is conclusive; the **pattern** is. The battery now runs
automatically on anything the delay control kills, and the diagnosis is
stored on the ledger row and shown on the leaderboard.

The last row is the one nobody thinks to run: an "edge" that survives
sliding its own signal half an hour into the future was never about the
signal.

---

## 4. It keeps a map of every KIND of strategy, and breeds from it

`researcher/archive.py`

Ranking by strength has a structural bias that no amount of care fixes:
significance grows with √n while profit grows with n, so a violent
twice-a-month cell will always outrank a modest daily one that is worth
far more. **The search was unable to find the thing actually wanted.**

Your arithmetic: $300/week on one micro needs ~3,000 trades/week at a
realistic +0.15 RT. A z-sorted leaderboard will never surface that.

So there is now a **grid over how a strategy behaves** — trading
frequency × hold length × exit style × direction, 240 cells — and the
best occupant of each is kept forever. That is MAP-Elites, and it buys
two things:

- **Coverage.** "The best thing we have that trades often enough to pay"
  becomes a question with an answer.
- **It never runs out.** Elites are a breeding pool: new candidates are
  crossed and mutated from occupants rather than drawn from nothing, so
  every niche improves at once. Random draw explores without improving;
  hill-climbing improves without exploring. This does both.

The first thing the map produced, on real data:

| band | best | trades | rate |
|---|---|---|---|
| <5/wk | +37.07 RT | 240 | 2/wk |
| 5–25/wk | +7.62 RT | 1,852 | 17/wk |
| 25–100/wk | +4.94 RT | 2,877 | 26/wk |
| 100–400/wk | +1.37 RT | 28,242 | 236/wk |
| 400–1500/wk | **−0.99 RT** | 44,254 | 402/wk |

**The best available edge decays monotonically with frequency and is
already negative by 400 trades/week.** That is the market answering the
question the account asks, and it was invisible before — you would only
ever have seen the +37 at 2/wk and thought you had found something.

**Nothing in the map is validated.** An elite is the best thing in its
niche and nothing more: no delay control, no null, no placebo, no vault.
And an elite is a *maximum*, so every number is biased high by
selection — which is exactly why the rare bands show the fattest ones.
The map is where to look, never what was found.

## 5. It runs in processes, because threads did nothing

`researcher/parallel.py`

Measured, four markets:

    sequential   5.11s
    4 threads    5.70s   0.90x   <- slower than no pool at all
    4 processes  1.69s   2.95x

The GIL made the thread pool decorative for its whole life. Workers now
get proxies that answer reads from a snapshot and buffer writes, so
`sweep()` is unchanged and the parent still owns the ledger — the trial
count that sets the bar is written in exactly one place, as before.

Verified equivalent: same trial count, and zero differing measurements
among hypotheses both paths tested.

## 6. It measures what it can actually SEE

`researcher/calibration.py`

The searcher reported a 5.79σ bar and treated that as controlling false
positives. That claim rests on normality, the overlap correction, the
empirical null and the bracket engine — **none of it ever checked end to
end.** And "240,000 tested, nothing found" is uninterpretable without
power.

So edges of known size are planted in **real tapes**, tradeable by
construction (a marker at bar *t* moves price only from *t+1*), and the
engine is asked to find them.

| | result |
|---|---|
| **Calibration** | exact — every planted increment recovers with **0.000 error** |
| **False alarms** | **zero** in 282 empty cells, worst \|z\| 2.55 |
| **Power** | **zero** — a +0.40 RT edge detected **0/10**, median z 0.4 |

The arithmetic behind the last row:

> 30-min hold noise = **113 RT**. A cell firing 166 times has SE 8.8 RT.
> To clear 5.79σ it needs **~9 round trips per trade** — nine times the
> entire cost of trading, i.e. bug territory.

**The searcher was blind to every edge worth finding. Its silence was
never evidence of absence.** That single measurement reframes the whole
project's history.

### What it takes instead

| edge | trades needed | one market @3k/wk | pooled over 20 |
|---|---|---|---|
| +0.15 RT | 657,000 | 219 weeks ❌ | **11 weeks** ✅ |

Noise scales as √hold, so required sample scales **linearly** with hold
length — 5 min needs 6.8M trades, 4 hours needs 380M. Short holds are
not a preference; they are the only arithmetically possible regime at
this cost. Tight brackets help too (113 RT → 40 RT at 0.5×/0.5×).

**Every result now carries its own `mde`** — the smallest edge it could
have detected — and the leaderboard says outright when a cell was blind.

## 7. It spends the budget where it can see

Measured on the draw as it stood: of 400 slate hypotheses, **0.8% could
have detected a +0.30 RT edge**, and the median could only have seen
+2.11 RT. Ninety-nine percent of the search was being spent where it
could not possibly succeed — and a wasted trial is not free, because the
bar rises for everyone.

The draw is now tilted by the **measured noise law**, not by taste:
weighting hold length by 1/√hold exactly cancels the √hold growth in
noise, so effort is spread evenly over *detectability* rather than over
octaves. Brackets are tilted toward the tight end for the same reason.

    median detectable edge   2.11 RT  ->  0.89 RT
    share that can see +0.50  5.5%    ->  16.5%

**A quarter of every draw ignores the tilt.** The noise law is a
measurement and could be wrong, the archive needs coverage of the slow
corner, and a search that only looks where it expects to see is not a
search.

Pooling is what closes the remaining gap:

| pooled over | detectable edge |
|---|---|
| 5 markets | 0.43 RT |
| 12 markets | 0.29 RT |
| **23 markets** | **0.21 RT** ✅ |

Only full-breadth pooling reaches the +0.10 to +0.30 RT range worth
hunting. That is why the cross-market test is the primary instrument and
not a nicety.

## What it still cannot do

Stated because the alternative is overclaiming, which is the failure
mode this whole project exists to guard against.

1. **It cannot form a hypothesis about *why*.** It can tell you a family
   died, and where an edge would have to live to pay for itself. It
   cannot propose a new mechanism from an understanding of how markets
   work. That still comes from a person.

2. **It cannot notice what nobody anticipated.** The tick-ordering bug
   that invalidated the entire deep tier was found by reasoning from an
   impossible number to its only possible cause. There was no rule for
   "is the data time-ordered", because nobody had thought to doubt it.
   The diagnosis battery mechanises the *known* differentials. Novel
   diagnosis is not in here.

3. **It cannot make a weak market strong.** 212,000 tested ideas and
   zero survivors is not a bug in the searcher. The shape of past price
   genuinely does not predict direction at these horizons, and the
   system is refusing to pretend otherwise. The pooled instrument makes
   it *possible* to see a weak broad effect if one exists — it does not
   promise one does.

---

## Where to look

| file | what it does |
|---|---|
| `pooled.py` | one mechanism, every market, one honest verdict |
| `surrogate.py` | the map of the space, and what it has learned |
| `diagnose.py` | differential diagnosis of a failure |
| `ledger.py` | trials, the rising bar, the sealed vault, epochs |
| `validate.py` | empirical null, period stability, stale placebo |
| `plausible.py` | encoded priors: numbers that cannot be true |
| `archive.py` | the map: an elite per behavioural niche, and breeding |
| `parallel.py` | sweeps in processes; proxies that account for trials |
| `calibration.py` | power, calibration, false-alarm rate — measured |
| `selftest_all.py` | **one command, 23 checks** — run this first |

```bash
python3 -m researcher.selftest_all
```

Every claim in this document is asserted by a test in that suite. If it
passes, the claims hold; if it fails, believe the test, not the
document.

# Every stream, both entry styles, one search

Each idea was previously tested in its own script and never together. `hunt.py` searched NQ price and flow, `edge.py` tested passive entry and sweeps, `regime.py` tested gamma. So a rule needing *heavy buy flow AND the index complex agreeing AND a long-gamma session* could not be expressed, let alone found — which is the entire premise, since watching several unrelated streams at once is the one advantage a bot has that a human cannot copy.

Streams: NQ price, NQ order flow, the index complex (ES/YM/RTY), the macro complex (CL/GC/HG), sweeps, and dealer gamma over 484 labelled sessions. Entries scored **both** crossing and resting a limit. Cost **$1.24** — commission plus one spread, which is what a taker actually pays.

| gate | rejected |
|---|---|
| −1 geometry, before any data | 950 |
| 0 frequency, outcome untouched | 169,626 |
| 1 win rate below what the bracket needs | 584,198 |
| 1b **below what RANDOM ENTRY earns** | 3,956 |
| 2 fully scored | 1,708 |

**Gate 1b is the one that matters.** NQ rose 8,492 points across this sample, so a long bracket makes money for no reason at all. Three separate findings today were exactly that, each surviving until someone asked what a random entry would have earned. Here it is a gate rather than a post-mortem.

`1,708` scored. `6` frequent enough, `48` paid enough, **`0` did both.** Selection ceiling **3.9σ**.

### Best $/week among 500+ trades/week

| trigger | entry | R:R | win% | random | **σ vs random** | tr/wk | $/trade | **$/week** | worst run $ |
|---|---|---|---|---|---|---|---|---|---|
| g_gex q0.3 | post | 2.0:1 | 35.5% | 33.2% | **+4.9σ** | 649 | $+0.62 | **$+399** | $499 |
| g_gex q0.3 | post | 1.0:1 | 52.4% | 50.0% | **+4.7σ** | 600 | $+0.60 | **$+361** | $439 |
| g_gex q0.3 | post | 1.0:1 | 52.0% | 49.8% | **+4.0σ** | 543 | $-0.07 | **$-37** | $475 |
| g_gex q0.3 | cross | 2.0:1 | 35.4% | 33.2% | **+4.8σ** | 650 | $-0.42 | **$-270** | $501 |
| g_gex q0.3 | cross | 1.0:1 | 52.3% | 50.0% | **+4.4σ** | 606 | $-0.49 | **$-295** | $441 |
| g_gex q0.3 | cross | 1.0:1 | 52.1% | 49.8% | **+4.1σ** | 545 | $-0.91 | **$-495** | $474 |

### Highest sigma over random entry, any frequency

| trigger | entry | R:R | win% | random | **σ vs random** | tr/wk | $/trade | **$/week** | worst run $ |
|---|---|---|---|---|---|---|---|---|---|
| g_gex q0.3 | post | 2.0:1 | 35.5% | 33.2% | **+4.9σ** | 649 | $+0.62 | **$+399** | $499 |
| g_gex q0.15 | post | 1.3:1 | 47.1% | 42.8% | **+4.9σ** | 207 | $+0.79 | **$+163** | $496 |
| g_regime q0.15 | post | 1.3:1 | 47.1% | 42.8% | **+4.9σ** | 207 | $+0.79 | **$+163** | $496 |
| g_gex q0.15 | cross | 1.3:1 | 47.0% | 42.8% | **+4.8σ** | 206 | $-0.05 | **$-10** | $497 |
| g_regime q0.15 | cross | 1.3:1 | 47.0% | 42.8% | **+4.8σ** | 206 | $-0.05 | **$-10** | $497 |
| g_gex q0.3 | post | 1.3:1 | 45.6% | 42.9% | **+4.8σ** | 484 | $+1.03 | **$+497** | $524 |
| g_gex q0.3 | cross | 2.0:1 | 35.4% | 33.2% | **+4.8σ** | 650 | $-0.42 | **$-270** | $501 |
| g_gex q0.3 | post | 1.0:1 | 52.4% | 50.0% | **+4.7σ** | 600 | $+0.60 | **$+361** | $439 |
| g_gex q0.3 | cross | 1.3:1 | 45.5% | 42.9% | **+4.6σ** | 484 | $+0.09 | **$+43** | $525 |
| g_gex q0.3 | cross | 1.3:1 | 45.5% | 42.8% | **+4.5σ** | 438 | $-0.63 | **$-276** | $562 |
| g_gex q0.3 | post | 1.0:1 | 53.1% | 50.2% | **+4.5σ** | 386 | $+1.53 | **$+592** | $550 |
| g_gex q0.3 | post | 1.3:1 | 45.5% | 42.8% | **+4.5σ** | 439 | $+0.16 | **$+72** | $562 |

_Ran 2.16 h._

---

## The persistence test, which is the only one that matters

All eight quarters, 1,708 configurations, zero clearing both gates.

> **8 families out of 337 appear in three or more quarters.** 329 appear in one
> or two.

A 2.4% survival rate on the most basic requirement there is — show up more than
once. That single number explains the whole day: four separate candidates
looked strong this morning and every one of them lived in a single quarter.

| family | quarters | median σ | trades/wk | $/week |
|---|---|---|---|---|
| `g_gex` | 3 | +3.15 | 228 | +$94 |
| `p_pos144` | 3 | +2.80 | 214 | −$28 |
| `p_chop55` | 3 | +2.77 | 182 | +$47 |
| `f_ofi21` | 3 | +2.57 | 226 | +$102 |
| `f_ofi89` | 4 | +2.56 | 194 | +$53 |
| `f_wcofi600 & f_ofi21` | 3 | +2.21 | 133 | **+$140** |

Nothing clears the **3.9σ** ceiling on a cross-quarter median. The best is
+3.15σ at $94 a week.

**`f_ofi` surfaces again**, in three forms across three and four quarters, all
positive. It is the only thing that has appeared in every search run today.
Median +$102 a week at 226 trades a week — not nothing, and not $1,000.

**`g_gex` tops the persistence list**, which is awkward given gamma was
declared dead this morning. Three quarters at +3.15σ against a 3.9σ bar, and
its dedicated 120-family study with permuted labels was a clean null. Read it
as noise until something proves otherwise, not as a revival.

**Where this leaves the target.** Best surviving candidate is $100–140 a week
at 130–230 trades a week on one contract, none of it statistically established.
Against $1,000 a week that is an order of magnitude short — the same order of
magnitude as this morning, before the new streams, the cost correction and the
fusion machinery.

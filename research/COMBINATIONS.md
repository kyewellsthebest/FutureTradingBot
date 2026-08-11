# Every way the six streams can be combined, and what each one claims

Six data types are on one clock. Until now they were searched almost entirely
*within* type — the previous pass ranked every condition together and paired
the best thirty, which were nearly all price features, so what actually got
tested was `p_chop55 & p_pos55` and `f_wcofi600 & f_ofi21`. Price against
price, flow against flow. The cross-type combinations that are the entire
reason for carrying six streams were barely touched.

This is the map of what there is to combine. It is not a wish list — the
search now generates every cell in it by construction.

## The six types

| tag | stream | what it knows that the others do not |
|---|---|---|
| `p_` | NQ price, shape, time-of-day | where NQ is in its own range, and when |
| `f_` | NQ order flow | which side is *initiating*, not just where price ended |
| `i_` | index complex ES / YM / RTY | whether the whole equity complex agrees |
| `m_` | macro complex CL / GC / HG | whether the move is risk-on or index-specific |
| `x_` | sweeps | that someone crossed the spread in size |
| `g_` | dealer gamma, 484 labelled sessions | whether hedging flow damps or amplifies today |

## The 15 cross-type pairs

Each row is a *family*. The search instantiates each one at 5 quantile
thresholds × 2 directions per leg — so one family below becomes roughly 144
concrete tested rules per quarter, per bar size.

| pair | the claim |
|---|---|
| `p_ × f_` | price at an extreme **and** flow still pushing it there — continuation, as opposed to price at an extreme on exhausted flow |
| `p_ × i_` | NQ at its range low **and** ES/YM/RTY not there — NQ-specific dislocation, the kind that mean-reverts |
| `p_ × m_` | NQ breaking out **and** gold/oil confirming risk appetite — separates a real risk move from an index rotation |
| `p_ × x_` | a sweep printing **at** a range extreme, rather than anywhere |
| `p_ × g_` | the same range position in long-gamma vs short-gamma sessions — the reversion trade should only work when dealers are damping |
| `f_ × i_` | NQ buy flow **and** the complex leading up — flow that the whole market is behind |
| `f_ × m_` | NQ flow **and** the macro complex disagreeing — flow with nothing behind it |
| `f_ × x_` | sustained one-sided flow **and** a sweep — accumulation finishing with an aggressive print |
| `f_ × g_` | order flow in short gamma, where dealer hedging amplifies whatever flow starts |
| `i_ × m_` | equity complex up **and** risk complex down — internal rotation, not a market move |
| `i_ × x_` | complex dispersion high **and** a sweep — someone trading the disagreement |
| `i_ × g_` | complex divergence conditioned on gamma regime |
| `m_ × x_` | macro moving **and** the sweep landing in NQ — where the transmission shows up |
| `m_ × g_` | macro stress in short gamma, the amplification case |
| `x_ × g_` | sweeps in long gamma get absorbed; in short gamma they run. Same print, opposite consequence |

## The 20 cross-type triples

Three distinct types at once, which is the thing no single-stream study could
ever express. Four legs per type are carried into triples, so each family
below becomes 64 concrete rules per quarter, per bar size.

`p·f·i` `p·f·m` `p·f·x` `p·f·g` `p·i·m` `p·i·x` `p·i·g` `p·m·x` `p·m·g`
`p·x·g` `f·i·m` `f·i·x` `f·i·g` `f·m·x` `f·m·g` `f·x·g` `i·m·x` `i·m·g`
`i·x·g` `m·x·g`

The one worth naming: **`f·i·g`** — heavy NQ buy flow, the index complex
agreeing, in a short-gamma session. That is "flow, confirmed, into a market
that has to chase." It is the strongest version of the premise, and it was
literally not expressible in any script in this repo before today.

## Past pairs and triples: arity, and the combiner

For an AND the **order of the legs is meaningless** — `C+B+D` and `B+C+D`
select the same bars. So what adds coverage is not permuting letters, it is
taking more of them at once: every 2-, 3-, 4-way set of distinct types, with
the legs per type shrinking as the set widens (6 types choose 4, at 12 legs
each, would be 311,040 sets on its own).

The bigger change is that **AND is no longer the only combiner**, and this is
the thing that was quietly boxing the search in. Every added AND condition cuts
how often a rule fires — which is exactly why the first pass scored 952
configurations and not one reached 500 trades a week, topping out at 241.
Stacking to four- and five-way ANDs alone would have made that *worse*.

| combiner | fires | uses all streams? |
|---|---|---|
| `AND` | rarest — every leg must agree | yes, but frequency collapses |
| `OR` | **more** often than any single leg | yes, and it *raises* trade count |
| `k-of-n` | tuned by k | **yes, and frequency is a dial** |

`k-of-n` is the one that resolves the conflict. "Four of these six streams
agree" reads every data type simultaneously — the actual premise — while `k`
tunes firing rate toward 500/week instead of letting it collapse. `2-of-5`
fires often; `4-of-5` rarely; both are genuine five-stream rules.

## Count

Per quarter, per bar size:

```
 4,823  distinct leg sets (2-way through 4-way, plus within-type controls)
13,020  scored variants once AND / OR / k-of-n are applied to each
```

Groups are interleaved round-robin, so if the wall clock cuts the run short
the cut falls evenly across all families rather than exhausting the
alphabetically-first ones.

## What this costs, and it is not free

Testing this many combinations raises the selection ceiling. The best of N
pure-noise draws sits at `sqrt(2 ln N)` sigma: at 1,708 configurations that was
3.9σ, and the report recomputes it against whatever this run actually scores.
Anything found here has to clear a *higher* bar than anything before it, purely
for having looked in more places. Breadth is not free and the report prices it.

Two degeneracies are now rejected rather than counted. A leg that fires more
than 90% of the time is not a condition, it is the tape — `g_regime` is a
binary ±1 label, so thresholding it at five quantiles produced the same
all-true mask five times, and four "triples" in the first pass scored
identically to the cent to the plain pair without gamma. And any combination
whose mask exactly repeats one already scored is dropped, since a triple that
selects precisely the pair's bars *is* the pair.

Every other gate stays exactly where it was: ≥500 trades/week, ≥$2.00/trade
net of the corrected $1.24 round turn, reward:risk between 1.0 and 2.5 with a
win rate between 35% and 65% *jointly*, worst expected losing run under 15% of
$4,100, and — the gate that has killed the most results — it must beat what
the identical bracket earns entered at random.

## What is still blocked

Fourteen of the seventeen execution ideas need the order book, and the DOM
recorder is not yet producing data. Queue position, book imbalance, depth
withdrawal, iceberg detection, and the true passive fill rate are all
unavailable, which is why the passive-entry edge still carries a 3.5×
uncertainty band. No amount of combinatorics over the streams already in hand
substitutes for that.

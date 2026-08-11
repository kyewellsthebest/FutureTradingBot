# The filtered hunt

Hard gates, cheapest first, so nothing below the bar costs time. Targets: **500 trades a week** and **$2.00 a trade net**.

| gate | what it checks | cost | rejected here |
|---|---|---|---|
| −1 geometry | `cost/(S+T)` — the edge over a coin flip the bracket needs before any win rate is known | **no data** | 665 |
| 0 frequency | fires often enough for 500 trades/week | **outcome untouched** | 4,675,306 |
| 1 win rate | one-sided 99% bound on 15% of the tape | a slice | 3,326,436 |
| 2 full | every bar, exact, non-overlapping | full | 558,267 scored |

**Gate −1 is the one worth understanding.** A bracket wins `S/(S+T)` of the time on a driftless walk by the reflection principle, and break-even needs `(S+c)/(S+T)`. The difference is `c/(S+T)` — the edge over pure chance the bracket demands — and it is known before a single bar is read. The largest edge over chance ever measured here is 2–4pp, so anything demanding more than 6pp is dead on arrival. For NQ at $1.99 that means stop and target must span at least 17 points together.

Pointed at what has **not** been measured: ES, RTY, YM and CL as the *traded* instrument rather than as features, three event clocks, and bracket exits on first touch. NQ price and flow at this frequency is already known — $0.13 a trade gross with costs switched off, against the ~$4.00 gross this asks for.

Unresolved trades are closed at the window's end, never dropped — dropping them flatters slow winners over fast losers and has faked an edge here before. Ties inside a bar go to the stop.

## Nothing cleared both gates

## How close anything came

`558,267` reached full scoring. `1,253` were frequent enough, `132,037` paid enough, `0` did both.

> **Every win rate is measured against the same bracket entered at EVERY bar, not against a coin flip.** NQ rose 8,492 points across this sample, so a long symmetric bracket beats 50% for no reason but the trend. Measured against a driftless flip, 94% of everything above +2σ was long — beta wearing a strategy's clothes. The `sigma vs drift` column is that correction.

> **Read sigma, not dollars.** It is how far a win rate sits above the rate its own bracket requires. Trying `558,267` configurations and keeping the best is a selection procedure, and the best of that many pure noise draws lands about **5.1σ** up by itself (`sqrt(2 ln N)`). So anything under 5.1σ here is consistent with having tried a lot of things, no matter how good the dollars look — and the dollars are what will tempt you.

### Best paying, among those firing 500+ a week

| market | clock | trigger | stop | target | win% | needed | same bracket, any bar | **sigma vs drift** | trades/wk | $/trade |
|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 500 | f_ofi21 q0.35 | 32 | 292 | 11.0% | 10.6% | 10.7% | **+0.9σ** | 505 | $+0.57 |
| NQ | 250 | f_ofi21 q0.65 | 22 | 315 | 7.6% | 7.3% | 7.1% | **+1.5σ** | 505 | $+0.48 |
| NQ | 500 | f_ofi89 q0.25 | 32 | 292 | 10.9% | 10.6% | 10.7% | **+0.7σ** | 530 | $+0.47 |
| NQ | 500 | f_ofi21 q0.25 | 32 | 292 | 10.9% | 10.6% | 10.7% | **+0.6σ** | 558 | $+0.38 |
| NQ | 500 | p_rev55 q0.35 | 32 | 292 | 10.9% | 10.6% | 10.7% | **+0.5σ** | 528 | $+0.34 |
| NQ | 250 | f_ofi5 q0.55 | 34 | 315 | 10.6% | 10.5% | 10.6% | **+0.3σ** | 508 | $+0.33 |
| NQ | 250 | f_int5 q0.25 | 45 | 315 | 13.3% | 13.2% | 13.7% | **-0.9σ** | 509 | $+0.28 |
| NQ | 250 | f_ofi89 q0.55 | 22 | 315 | 7.4% | 7.3% | 7.1% | **+1.1σ** | 522 | $+0.27 |
| NQ | 500 | p_rev21 q0.45 | 32 | 292 | 10.8% | 10.6% | 10.7% | **+0.3σ** | 521 | $+0.23 |
| NQ | 250 | f_ofi5 q0.15 | 45 | 315 | 13.3% | 13.2% | 13.7% | **-1.0σ** | 515 | $+0.23 |
| NQ | 500 | f_ofi1 q0.55 | 32 | 292 | 10.8% | 10.6% | 10.7% | **+0.3σ** | 505 | $+0.22 |
| NQ | 250 | f_int21 q0.55 | 34 | 315 | 10.5% | 10.5% | 10.6% | **-0.0σ** | 523 | $+0.19 |

### Most frequent, among those paying $2.00+

| market | clock | trigger | stop | target | win% | needed | same bracket, any bar | **sigma vs drift** | trades/wk | $/trade |
|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 500 | f_ofi89 q0.45 | 32 | 455 | 7.9% | 7.1% | 7.5% | **+1.2σ** | 290 | $+2.08 |
| NQ | 250 | f_ofi5 q0.65 | 68 | 315 | 19.4% | 18.4% | 19.4% | **+0.1σ** | 270 | $+2.00 |
| NQ | 250 | p_rng8 q0.55 | 315 | 90 | 79.4% | 78.4% | 78.8% | **+1.0σ** | 267 | $+2.06 |
| NQ | 250 | f_ofi5 q0.45 | 202 | 135 | 61.9% | 60.7% | 62.3% | **-0.6σ** | 256 | $+2.03 |
| NQ | 250 | f_ofi1 q0.85 | 68 | 315 | 19.5% | 18.4% | 19.4% | **+0.2σ** | 252 | $+2.18 |
| NQ | 500 | p_pos8 q0.35 | 49 | 455 | 11.2% | 10.2% | 11.1% | **+0.2σ** | 247 | $+2.41 |
| NQ | 500 | p_mom3 q0.45 | 49 | 455 | 11.2% | 10.2% | 11.1% | **+0.2σ** | 246 | $+2.39 |
| NQ | 250 | f_ofi5 q0.55 | 202 | 135 | 62.0% | 60.7% | 62.3% | **-0.4σ** | 242 | $+2.28 |
| NQ | 500 | f_ofi5 q0.35 | 292 | 98 | 76.7% | 75.5% | 76.3% | **+0.7σ** | 241 | $+2.42 |
| NQ | 500 | f_ofi5 q0.65 | 195 | 98 | 68.9% | 67.4% | 68.0% | **+1.2σ** | 241 | $+2.27 |
| NQ | 500 | p_mom8 q0.65 | 195 | 98 | 69.0% | 67.4% | 68.0% | **+1.3σ** | 240 | $+2.35 |
| NQ | 500 | f_ofi89 q0.35 | 49 | 455 | 11.1% | 10.2% | 11.1% | **-0.0σ** | 239 | $+2.12 |

A miss by thirty times and a miss by ten percent are different facts, and these two tables are what separates them. That is why a run finding nothing is still worth the hours.

_Ran 0.43 h._

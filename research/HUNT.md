# The filtered hunt

Hard gates, cheapest first, so nothing below the bar costs time. Targets: **500 trades a week** and **$2.00 a trade net**.

| gate | what it checks | cost | rejected here |
|---|---|---|---|
| −1 geometry | `cost/(S+T)` — the edge over a coin flip the bracket needs before any win rate is known | **no data** | 1,499 |
| 0 frequency | fires often enough for 500 trades/week | **outcome untouched** | 1,661,054 |
| 1 win rate | one-sided 99% bound on 15% of the tape | a slice | 1,990,073 |
| 2 full | every bar, exact, non-overlapping | full | 184,091 scored |

**Gate −1 is the one worth understanding.** A bracket wins `S/(S+T)` of the time on a driftless walk by the reflection principle, and break-even needs `(S+c)/(S+T)`. The difference is `c/(S+T)` — the edge over pure chance the bracket demands — and it is known before a single bar is read. The largest edge over chance ever measured here is 2–4pp, so anything demanding more than 6pp is dead on arrival. For NQ at $1.99 that means stop and target must span at least 17 points together.

Pointed at what has **not** been measured: ES, RTY, YM and CL as the *traded* instrument rather than as features, three event clocks, and bracket exits on first touch. NQ price and flow at this frequency is already known — $0.13 a trade gross with costs switched off, against the ~$4.00 gross this asks for.

Unresolved trades are closed at the window's end, never dropped — dropping them flatters slow winners over fast losers and has faked an edge here before. Ties inside a bar go to the stop.

## Nothing cleared both gates

## How close anything came

`184,091` reached full scoring. `108` were frequent enough, `41,938` paid enough, `0` did both.

> **Every win rate is measured against the same bracket entered at EVERY bar, not against a coin flip.** NQ rose 8,492 points across this sample, so a long symmetric bracket beats 50% for no reason but the trend. Measured against a driftless flip, 94% of everything above +2σ was long — beta wearing a strategy's clothes. The `sigma vs drift` column is that correction.

> **Read sigma, not dollars.** It is how far a win rate sits above the rate its own bracket requires. Trying `184,091` configurations and keeping the best is a selection procedure, and the best of that many pure noise draws lands about **4.9σ** up by itself (`sqrt(2 ln N)`). So anything under 4.9σ here is consistent with having tried a lot of things, no matter how good the dollars look — and the dollars are what will tempt you.

### Best paying, among those firing 500+ a week

| market | clock | trigger | stop | target | win% | needed | same bracket, any bar | **sigma vs drift** | trades/wk | $/trade |
|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 500 | f_ofi89 q0.3 | 32 | 292 | 11.0% | 11.1% | 10.7% | **+0.9σ** | 500 | $-0.15 |
| NQ | 250 | f_ofi5 q0.2 | 45 | 315 | 13.3% | 13.6% | 13.7% | **-0.9σ** | 503 | $-0.45 |
| NQ | 250 | f_ofi5 q0.5 | 34 | 315 | 10.6% | 10.9% | 10.6% | **+0.1σ** | 531 | $-0.51 |
| NQ | 250 | f_ofi89 q0.4 | 45 | 202 | 19.4% | 19.8% | 19.4% | **+0.1σ** | 528 | $-0.55 |
| NQ | 250 | f_ofi5 q0.6 | 45 | 202 | 19.3% | 19.8% | 19.4% | **-0.0σ** | 531 | $-0.61 |
| NQ | 250 | f_int89 q0.2 | 45 | 315 | 13.3% | 13.6% | 13.7% | **-1.2σ** | 514 | $-0.63 |
| NQ | 250 | p_rng3 q0.5 | 45 | 315 | 13.2% | 13.6% | 13.7% | **-1.2σ** | 504 | $-0.65 |
| NQ | 250 | p_rng8 q0.4 | 45 | 315 | 13.2% | 13.6% | 13.7% | **-1.2σ** | 505 | $-0.67 |
| NQ | 250 | p_chop21 q0.2 | 45 | 315 | 13.2% | 13.6% | 13.7% | **-1.3σ** | 515 | $-0.68 |
| NQ | 250 | f_ofi5 q0.2 | 68 | 202 | 26.1% | 26.7% | 26.7% | **-1.2σ** | 524 | $-0.72 |
| NQ | 250 | p_dow q0.4 | 45 | 202 | 19.2% | 19.8% | 19.4% | **-0.2σ** | 510 | $-0.72 |
| NQ | 250 | p_gap q0.2 | 45 | 315 | 13.2% | 13.6% | 13.7% | **-1.3σ** | 516 | $-0.72 |

### Most frequent, among those paying $2.00+

| market | clock | trigger | stop | target | win% | needed | same bracket, any bar | **sigma vs drift** | trades/wk | $/trade |
|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 250 | f_ofi21 q0.4 | 315 | 90 | 79.7% | 78.8% | 78.8% | **+1.5σ** | 237 | $+2.05 |
| NQ | 250 | f_ofi5 q0.6 | 202 | 135 | 62.6% | 61.1% | 62.3% | **+0.3σ** | 234 | $+2.45 |
| NQ | 500 | p_pos8 q0.4 | 49 | 455 | 11.3% | 10.5% | 11.1% | **+0.5σ** | 232 | $+2.02 |
| NQ | 250 | f_ofi5 q0.6 | 90 | 315 | 24.4% | 23.2% | 24.3% | **+0.1σ** | 223 | $+2.37 |
| NQ | 500 | f_ofi5 q0.5 | 292 | 98 | 76.9% | 75.9% | 76.3% | **+0.9σ** | 221 | $+2.04 |
| NQ | 500 | f_ofi21 q0.5 | 49 | 455 | 11.3% | 10.5% | 11.1% | **+0.5σ** | 221 | $+2.10 |
| NQ | 500 | p_mom3 q0.6 | 49 | 455 | 11.5% | 10.5% | 11.1% | **+0.7σ** | 216 | $+2.38 |
| NQ | 250 | f_ofi5 q0.7 | 90 | 315 | 24.5% | 23.2% | 24.3% | **+0.4σ** | 206 | $+2.72 |
| NQ | 500 | f_ofi5 q0.6 | 292 | 98 | 76.9% | 75.9% | 76.3% | **+0.9σ** | 203 | $+2.09 |
| NQ | 1000 | f_ofi1 q0.4 | 47 | 658 | 7.9% | 7.2% | 7.7% | **+0.3σ** | 199 | $+2.24 |
| NQ | 500 | p_mom3 q0.7 | 49 | 455 | 11.5% | 10.5% | 11.1% | **+0.8σ** | 197 | $+2.48 |
| NQ | 250 | p_pos21 q0.6 | 202 | 135 | 62.3% | 61.1% | 62.3% | **-0.0σ** | 196 | $+2.01 |

A miss by thirty times and a miss by ten percent are different facts, and these two tables are what separates them. That is why a run finding nothing is still worth the hours.

_Ran 0.23 h._

# Every candidate, pooled across all eight quarters

The hunt scored each quarter separately and nothing recurred in more than three of eight. Widening the search would not fix that — more configurations raises the noise ceiling faster than it raises the best draw. So the budget went on shrinking the error bar instead: eight quarters is ~8x the trades, so a win rate's standard error falls ~2.8x. A real 1–2 point edge reading +1.8σ on one quarter reads about +5σ pooled; a lucky quarter averages away.

**The trap this avoids.** The hunt only recorded a family on quarters where it PASSED. Pooling those rows would average its wins and ignore its losses — a positive result guaranteed by arithmetic. Every family below is re-scored on **every** quarter, including ones it never appeared in.

`184,091` configurations were tried, so the selection ceiling is **4.9σ** — the best of that many pure-noise draws. Every win rate is measured against the same bracket entered at every bar, so the 8,492-point market drift is already removed.

| market | clock | trigger | side | stop | target | pooled trades | win% | drift% | **σ vs drift** | quarters + | $/trade | trades/wk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 250 | p_dow>q0.5 & f_ofi5>q0.8 | long | 202 | 45 | 24,893 | 82.7% | 81.8% | +3.8σ | 1/8 | $-1.03 | 200 |
| NQ | 250 | p_dow>q0.4 & f_ofi21>q0.7 | long | 315 | 45 | 24,696 | 88.3% | 87.5% | +3.6σ | 1/8 | $-0.86 | 198 |
| NQ | 250 | p_dow>q0.4 & f_ofi5>q0.8 | long | 202 | 45 | 32,553 | 82.5% | 81.8% | +3.4σ | 1/8 | $-1.28 | 261 |
| NQ | 250 | p_dow>q0.5 & f_eff89>q0.8 | long | 294 | 294 | 2,459 | 52.0% | 48.6% | +3.4σ | 7/8 | $+6.69 | 20 |
| NQ | 250 | p_dow>q0.4 & f_ofi21>q0.7 | long | 315 | 68 | 17,927 | 83.2% | 82.4% | +2.9σ | 2/8 | $-0.56 | 144 |
| NQ | 250 | p_hour<q0.4 & p_pos144<q0.2 | short | 37 | 166 | 12,078 | 19.1% | 18.2% | +2.6σ | 1/8 | $-1.08 | 97 |
| ES | 250 | p_hour>q0.5 & p_rev144>q0.8 | long | 35 | 35 | 2,530 | 51.5% | 48.9% | +2.6σ | 1/6 | $-1.53 | 27 |
| NQ | 250 | f_ofi21>q0.7 & f_ofi89>q0.6 | long | 196 | 28 | 21,814 | 88.1% | 87.5% | +2.5σ | 2/8 | $-1.22 | 175 |
| NQ | 250 | f_eff89>q0.8 & p_rng144>q0.6 | long | 87 | 130 | 5,305 | 41.7% | 40.1% | +2.4σ | 4/8 | $+0.26 | 43 |
| NQ | 250 | f_eff89>q0.6 & p_rng144>q0.6 | long | 44 | 203 | 9,190 | 18.6% | 17.7% | +2.3σ | 3/8 | $-0.51 | 74 |
| NQ | 500 | f_ofi21 | short | 98 | 195 | 13,440 | 34.2% | 33.3% | +2.2σ | 2/8 | $-0.90 | 108 |
| NQ | 250 | p_pos144>q0.8 & f_ofi89>q0.5 | long | 135 | 68 | 12,429 | 67.4% | 66.4% | +2.2σ | 1/8 | $-1.30 | 100 |
| NQ | 250 | p_rng55>q0.7 & f_ofi21>q0.6 | long | 196 | 56 | 10,718 | 78.7% | 77.9% | +2.2σ | 2/8 | $-0.36 | 86 |
| NQ | 250 | p_hour<q0.5 & p_pos144<q0.2 | short | 37 | 166 | 13,270 | 18.9% | 18.2% | +2.2σ | 1/8 | $-1.28 | 107 |
| NQ | 250 | f_ofi89>q0.5 & f_ret5>q0.8 | long | 135 | 90 | 21,878 | 60.6% | 59.9% | +2.1σ | 1/8 | $-1.40 | 176 |
| NQ | 250 | f_ofi89>q0.6 & f_ret5>q0.8 | long | 135 | 90 | 18,063 | 60.6% | 59.9% | +2.1σ | 1/8 | $-1.31 | 145 |
| NQ | 250 | p_dow>q0.4 & f_ofi21>q0.7 | long | 202 | 68 | 23,322 | 75.5% | 75.0% | +2.1σ | 1/8 | $-1.31 | 187 |
| NQ | 250 | p_rng55>q0.7 & f_ofi21>q0.6 | long | 196 | 42 | 12,977 | 83.1% | 82.4% | +2.1σ | 2/8 | $-0.84 | 104 |
| ES | 500 | p_rng144>q0.7 & p_dow>q0.5 | long | 77 | 16 | 4,818 | 84.0% | 82.9% | +2.1σ | 1/6 | $-2.15 | 51 |
| NQ | 250 | f_ret89>q0.8 & p_rng144>q0.6 | long | 87 | 203 | 3,974 | 31.4% | 29.9% | +2.1σ | 5/8 | $+0.78 | 32 |
| NQ | 250 | f_eff89>q0.7 & p_rng144>q0.6 | long | 87 | 87 | 8,795 | 51.1% | 50.0% | +2.0σ | 2/8 | $-0.82 | 71 |
| ES | 500 | p_rng144>q0.7 & p_dow>q0.4 | long | 77 | 16 | 6,445 | 83.7% | 82.8% | +2.0σ | 1/6 | $-2.42 | 69 |
| NQ | 250 | p_hour<q0.6 & p_dow<q0.3 | short | 259 | 37 | 18,545 | 87.9% | 87.4% | +2.0σ | 1/8 | $-1.33 | 149 |
| NQ | 250 | p_hour<q0.6 & p_dow<q0.4 | short | 259 | 37 | 18,545 | 87.9% | 87.4% | +2.0σ | 1/8 | $-1.33 | 149 |
| NQ | 250 | p_pos144>q0.8 & f_ofi89>q0.5 | long | 68 | 315 | 6,260 | 18.6% | 17.6% | +2.0σ | 2/8 | $-0.24 | 50 |

**0** cleared everything: pooled sigma above the 4.9σ ceiling, positive dollars after cost, and positive in all but at most one quarter.

The best pooled result is **+3.8σ** against a **4.9σ** ceiling, positive in 1 of 8 quarters at $-1.03 a trade. Pooling multiplied the sample by eight and the sigma did not follow, which is what a real edge would have done and noise does not.

_Ran 74 min._

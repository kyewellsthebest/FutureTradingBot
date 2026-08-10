# Every candidate, pooled across all eight quarters

The hunt scored each quarter separately and nothing recurred in more than three of eight. Widening the search would not fix that — more configurations raises the noise ceiling faster than it raises the best draw. So the budget went on shrinking the error bar instead: eight quarters is ~8x the trades, so a win rate's standard error falls ~2.8x. A real 1–2 point edge reading +1.8σ on one quarter reads about +5σ pooled; a lucky quarter averages away.

**The trap this avoids.** The hunt only recorded a family on quarters where it PASSED. Pooling those rows would average its wins and ignore its losses — a positive result guaranteed by arithmetic. Every family below is re-scored on **every** quarter, including ones it never appeared in.

`184,091` configurations were tried, so the selection ceiling is **4.9σ** — the best of that many pure-noise draws. Every win rate is measured against the same bracket entered at every bar, so the 8,492-point market drift is already removed.

| market | clock | trigger | side | stop | target | pooled trades | win% | drift% | **σ vs drift** | quarters + | $/trade | trades/wk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NQ | 250 | f_ofi89>q0.5 & f_ret5>q0.8 | long | 135 | 90 | 21,878 | 60.6% | 59.9% | +2.1σ | 1/8 | $-1.40 | 176 |
| NQ | 250 | f_ofi89>q0.6 & f_ret5>q0.8 | long | 135 | 90 | 18,063 | 60.6% | 59.9% | +2.1σ | 1/8 | $-1.31 | 145 |
| NQ | 250 | f_eff89>q0.7 & p_rng144>q0.6 | long | 87 | 203 | 4,701 | 31.0% | 29.9% | +1.7σ | 4/8 | $-0.01 | 38 |
| NQ | 250 | f_ofi89>q0.5 & f_ret5>q0.8 | long | 90 | 90 | 24,975 | 50.3% | 49.8% | +1.6σ | 1/8 | $-1.70 | 200 |
| NQ | 1000 | p_pos144<q0.5 & p_hour<q0.6 | short | 38 | 152 | 27,050 | 20.3% | 19.9% | +1.5σ | 1/8 | $-1.80 | 217 |
| NQ | 250 | f_ofi21>q0.6 & f_ret5>q0.8 | long | 90 | 90 | 23,194 | 50.3% | 49.8% | +1.4σ | 1/8 | $-1.70 | 186 |
| NQ | 250 | f_ofi89>q0.6 & f_ret5>q0.8 | long | 90 | 90 | 20,490 | 50.3% | 49.8% | +1.4σ | 1/8 | $-1.70 | 164 |
| NQ | 1000 | p_pos144<q0.5 & p_hour<q0.6 | short | 57 | 152 | 20,985 | 27.4% | 27.1% | +1.0σ | 1/8 | $-1.84 | 168 |
| NQ | 500 | p_rng55 | long | 287 | 31 | 18,694 | 90.4% | 90.2% | +0.9σ | 2/8 | $-1.89 | 150 |
| NQ | 250 | f_ofi89>q0.5 & f_ret5>q0.8 | long | 68 | 135 | 21,872 | 33.5% | 33.2% | +0.9σ | 1/8 | $-1.76 | 176 |
| NQ | 250 | f_ofi89>q0.5 & f_ret5>q0.8 | long | 90 | 135 | 19,639 | 40.2% | 39.9% | +0.9σ | 1/8 | $-1.69 | 158 |
| ES | 250 | p_hour<q0.2 & f_int89<q0.2 | short | 49 | 49 | 2,841 | 49.4% | 48.6% | +0.8σ | 1/6 | $-3.91 | 30 |
| NQ | 1000 | p_mom144<q0.5 & p_pos55<q0.5 | short | 57 | 228 | 15,274 | 20.0% | 19.8% | +0.8σ | 1/8 | $-2.00 | 123 |
| NQ | 1000 | p_pos144<q0.6 & p_mom55<q0.5 | short | 38 | 228 | 23,349 | 14.3% | 14.1% | +0.7σ | 1/8 | $-1.95 | 187 |
| NQ | 250 | p_hour<q0.4 & p_mom144<q0.3 | short | 259 | 56 | 11,126 | 82.4% | 82.2% | +0.6σ | 1/8 | $-1.89 | 89 |
| NQ | 250 | p_hour<q0.5 & p_mom144<q0.3 | short | 259 | 56 | 12,102 | 82.4% | 82.2% | +0.5σ | 1/8 | $-1.90 | 97 |
| NQ | 1000 | p_mom55<q0.4 & p_pos55<q0.5 | short | 57 | 152 | 21,188 | 27.1% | 27.1% | +0.1σ | 1/8 | $-2.12 | 170 |
| NQ | 1000 | p_pos144<q0.5 & p_hour<q0.6 | short | 57 | 114 | 25,803 | 33.2% | 33.2% | +0.0σ | 1/8 | $-2.07 | 207 |
| NQ | 1000 | p_mom144<q0.5 & p_pos55<q0.5 | short | 57 | 152 | 20,971 | 27.0% | 27.1% | -0.3σ | 1/8 | $-2.27 | 168 |
| NQ | 1000 | p_mom144<q0.5 & p_pos144<q0.5 | short | 57 | 152 | 23,109 | 26.9% | 27.1% | -0.6σ | 1/8 | $-2.37 | 185 |

**0** cleared everything: pooled sigma above the 4.9σ ceiling, positive dollars after cost, and positive in all but at most one quarter.

The best pooled result is **+2.1σ** against a **4.9σ** ceiling, positive in 1 of 8 quarters at $-1.40 a trade. Pooling multiplied the sample by eight and the sigma did not follow, which is what a real edge would have done and noise does not.

_Ran 5 min._

# Split by dealer gamma: does anything work in one regime?

Every study here measured an **average over two years**. A rule that makes money when dealers are long gamma and loses when they are short averages to near zero — which is exactly what every study reported. The average was never evidence of no edge; it was evidence of not conditioning. This is the first dataset that classifies the *day* rather than describing the price, so it is the first time the question can be asked.

`484` sessions, **414 long-gamma / 70 short**, from option prices alone. Gamma sign is pre-specified — not fitted, no threshold to tune, zero is zero. The drift baseline is computed **within each regime**, because short-gamma days skew down and comparing against an all-days baseline would manufacture a result from that alone.

Two subgroups instead of one doubles the draws, so the selection ceiling is **5.1σ**. Splitting is not free.

**Shuffled-label floor: 1.70σ.** The day-to-regime map was permuted 5 times and the whole split recomputed; that is the regime gap random labelling produces. A real gap has to clear it.

| trigger | side | LONG gamma σ | $/trade | SHORT gamma σ | $/trade | **gap** |
|---|---|---|---|---|---|---|
| p_hour<q0.6 & p_dow<q0.3 | S | +1.6σ | $-1.72 | -1.5σ | $-1.22 | **+3.0** |
| p_hour<q0.6 & p_dow<q0.4 | S | +1.6σ | $-1.72 | -1.5σ | $-1.22 | **+3.0** |
| p_rng55>q0.7 & f_ofi21>q0.6 | L | -2.2σ | $-2.48 | +0.6σ | $-2.49 | **-2.8** |
| f_ofi89>q0.6 & f_ret5>q0.8 | L | +2.5σ | $-1.28 | -0.2σ | $-3.18 | **+2.7** |
| p_hour<q0.4 & p_pos144<q0.2 | S | +0.2σ | $-2.17 | +2.8σ | $+1.93 | **-2.6** |
| p_rng144>q0.7 & p_dow>q0.5 | L | +2.4σ | $-1.38 | -0.2σ | $-5.30 | **+2.5** |
| p_hour<q0.4 & p_pos144<q0.2 | S | +0.1σ | $-2.47 | +2.6σ | $+3.76 | **-2.5** |
| p_mom144<q0.5 & p_pos144<q0.5 | S | -1.7σ | $-2.90 | +0.6σ | $+0.40 | **-2.4** |
| f_ofi21>q0.6 & f_ret5>q0.8 | L | +1.9σ | $-1.42 | -0.4σ | $-3.43 | **+2.3** |
| p_mom144>q0.8 & p_rng144>q0.6 | L | -0.6σ | $-2.14 | +1.6σ | $-1.47 | **-2.2** |
| p_rng144>q0.7 & p_dow>q0.4 | L | +1.9σ | $-1.99 | -0.2σ | $-5.11 | **+2.1** |
| p_pos144<q0.2 & p_hour<q0.6 | S | -0.4σ | $-2.70 | +1.7σ | $+2.35 | **-2.1** |
| p_hour<q0.6 & p_pos144<q0.6 | S | -0.8σ | $-2.63 | +1.2σ | $+0.79 | **-2.1** |
| p_hour<q0.5 & p_pos144<q0.2 | S | -0.1σ | $-2.57 | +1.8σ | $+2.64 | **-2.0** |
| p_rng55 | L | +0.5σ | $-1.52 | +2.5σ | $-2.16 | **-2.0** |
| p_hour<q0.5 & p_pos144<q0.2 | S | -0.0σ | $-2.22 | +1.9σ | $+1.11 | **-1.9** |
| p_hour<q0.4 & p_mom144<q0.3 | S | -0.2σ | $-2.69 | +1.7σ | $+2.44 | **-1.9** |
| p_rng55 | L | -1.1σ | $-2.24 | +0.8σ | $-3.08 | **-1.9** |
| p_mom144<q0.5 & p_pos144<q0.6 | S | -1.3σ | $-2.75 | +0.6σ | $+0.35 | **-1.9** |
| p_hour<q0.4 & p_mom144<q0.2 | S | -0.7σ | $-2.46 | +1.2σ | $+1.32 | **-1.9** |
| p_hour<q0.6 & p_pos144<q0.6 | S | -0.6σ | $-2.54 | +1.3σ | $+0.01 | **-1.9** |
| p_rng144>q0.7 & p_dow>q0.5 | L | +2.2σ | $-2.11 | +0.3σ | $-4.31 | **+1.9** |
| f_ofi89>q0.5 & f_ret5>q0.8 | L | +2.0σ | $-1.44 | +0.1σ | $-3.07 | **+1.9** |
| p_hour<q0.4 & p_mom144<q0.3 | S | -0.1σ | $-2.87 | +1.7σ | $+4.53 | **-1.8** |
| p_hour<q0.6 & p_dow<q0.3 | S | +1.5σ | $-1.30 | -0.4σ | $-0.21 | **+1.8** |

Across all 120 families the median gap is **-0.64σ** and 39 of 120 lean the same way. A real regime effect shows up as the same sign across unrelated families, beyond the shuffled floor — one family flipping is noise with a story attached.

_Ran 26 min._

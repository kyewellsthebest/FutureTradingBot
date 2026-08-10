# Split by dealer gamma: does anything work in one regime?

Every study here measured an **average over two years**. A rule that makes money when dealers are long gamma and loses when they are short averages to near zero — which is exactly what every study reported. The average was never evidence of no edge; it was evidence of not conditioning. This is the first dataset that classifies the *day* rather than describing the price, so it is the first time the question can be asked.

`484` sessions, **414 long-gamma / 70 short**, from option prices alone. Gamma sign is pre-specified — not fitted, no threshold to tune, zero is zero. The drift baseline is computed **within each regime**, because short-gamma days skew down and comparing against an all-days baseline would manufacture a result from that alone.

Two subgroups instead of one doubles the draws, so the selection ceiling is **5.1σ**. Splitting is not free.

**Shuffled-label floor: 1.16σ.** The day-to-regime map was permuted 1 times and the whole split recomputed; that is the regime gap random labelling produces. A real gap has to clear it.

| trigger | side | LONG gamma σ | $/trade | SHORT gamma σ | $/trade | **gap** |
|---|---|---|---|---|---|---|
| p_pos144<q0.5 & p_hour<q0.6 | S | -0.5σ | $-2.53 | +1.2σ | $-0.02 | **-1.7** |
| f_ofi89>q0.5 & f_ret5>q0.8 | L | +2.2σ | $-0.91 | +0.5σ | $-3.54 | **+1.7** |
| f_ofi89>q0.6 & f_ret5>q0.8 | L | +2.5σ | $-0.70 | +0.9σ | $-3.10 | **+1.6** |
| p_pos144<q0.5 & p_hour<q0.6 | S | -0.5σ | $-2.52 | +1.0σ | $+0.64 | **-1.5** |
| f_ofi89>q0.5 & f_ret5>q0.8 | L | +1.8σ | $-1.38 | +0.4σ | $-3.11 | **+1.4** |
| p_mom144<q0.5 & p_pos55<q0.5 | S | -1.0σ | $-2.69 | -0.0σ | $-0.14 | -1.0 |
| p_pos144<q0.6 & p_mom55<q0.5 | S | +0.7σ | $-2.31 | -0.1σ | $+0.19 | +0.8 |
| p_mom144<q0.5 & p_pos55<q0.5 | S | +0.1σ | $-2.55 | +0.0σ | $+1.06 | +0.1 |

Across all 8 families the median gap is **+0.46σ** and 5 of 8 lean the same way. A real regime effect shows up as the same sign across unrelated families, beyond the shuffled floor — one family flipping is noise with a story attached.

_Ran 2 min._

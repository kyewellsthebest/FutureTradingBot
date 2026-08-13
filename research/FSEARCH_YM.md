# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| YMU4 | 194 | 791,806 | 596,664 | 393,253 | 64,012 | 785 |
| YMZ4 | 211 | 816,869 | 1,181,983 | 630,544 | 29,528 | 1,208 |
| YMH5 | 195 | 816,869 | 641,229 | 252,986 | 13,726 | 1,136 |
| YMM5 | 196 | 816,254 | 955,782 | 194,637 | 11,334 | 1,977 |
| YMU5 | 0 | 0 | 0 | 0 | 0 | 0 |
| YMZ5 | 197 | 815,639 | 890,719 | 371,227 | 41,039 | 1,390 |
| YMH6 | 199 | 815,639 | 1,080,410 | 404,134 | 44,118 | 1,340 |
| YMM6 | 198 | 816,254 | 920,118 | 368,909 | 74,054 | 1,274 |

**6,266,905 scanned → 2,615,690 cleared the train gate → 277,811 also paid on the held-out 40% → 5 survived every other quarter.**

| rule | side | home | train | test | **out of sample** | green | **$/wk oos** |
|---|---|---|---|---|---|---|---|
| 2of(`p_wceff120|rk55|hold8`, `r_res30|acc|hold8`) | S | YMM5 | $+10.35 | $+5.04 | **$+0.93** | 5/7 | **$+11** |
| 3of(`c_dom|raw|state`, `g_regime|z288|hold8`, `i_es_sz30|rk233) | S | YMH6 | $+5.47 | $+2.86 | **$+0.69** | 5/6 | **$+11** |
| 3of(`f_wcsz120|d89|hold8`, `g_regime|rk233|state`, `i_es_eff30) | L | YMH5 | $+3.75 | $+3.73 | **$+1.16** | 5/7 | **$+11** |
| 3of(`g_regime|raw|hold8`, `i_rty_ofi600|rk233|hold8`, `o_gapab) | L | YMU4 | $+6.39 | $+7.31 | **$+0.59** | 5/7 | **$+8** |
| 2of(`c_rth|d89|hold8`, `m_gc_vol30|rk233|hold8`, `p_mom21|rk23) | L | YMM6 | $+4.75 | $+3.04 | **$+0.93** | 6/7 | **$+7** |

_Ran 26.7 min on 4 workers._

## How far off were they?

`19,997` candidates reached cross-quarter validation.

| out-of-sample $/trade | candidates |
|---|---|
| -99.00 to -1.00 | 17,256 (86.3%) |
| -1.00 to -0.50 | 2,086 (10.4%) |
| -0.50 to +0.00 | 520 (2.6%) |
| +0.00 to +0.25 | 77 (0.4%) |
| +0.25 to +0.50 | 41 (0.2%) |
| +0.50 to +99.00 | 17 (0.1%) |

Best out-of-sample **$+1.16/trade**, median **$-1.53**. `135` were positive at all (0.7%), `39` were green in 5+ quarters.


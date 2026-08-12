# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 78 | 80,688 | 53,120 | 3,661 | 529 | 1,015 |
| NQZ4 | 75 | 138,650 | 59,934 | 8,257 | 1,695 | 916 |
| NQH5 | 73 | 138,650 | 71,671 | 2,813 | 258 | 958 |
| NQM5 | 67 | 138,650 | 46,694 | 1,764 | 84 | 727 |
| NQU5 | 75 | 138,650 | 80,029 | 14,857 | 1,944 | 1,112 |
| NQZ5 | 77 | 129,906 | 67,422 | 5,350 | 572 | 1,017 |
| NQH6 | 74 | 138,650 | 60,129 | 1,972 | 199 | 1,042 |
| NQM6 | 73 | 138,650 | 76,928 | 3,059 | 240 | 1,070 |

**515,927 scanned → 41,733 cleared the train gate → 5,521 also paid on the held-out 40% → 5 survived every other quarter.**

| rule | side | home | train | test | **out of sample** | green | **$/wk oos** |
|---|---|---|---|---|---|---|---|
| 3of(`f_wcofi600`, `g_gex`, `i_es_sz120`, `m_divCL120`, `x_swee) | S | NQH5 | $+3.79 | $+0.29 | **$+1.33** | 5/6 | **$+26** |
| 3of(`d_z144`, `m_gc_sz600`, `r_beta120`, `v_vr`) | S | NQZ4 | $+4.39 | $+2.00 | **$+1.41** | 6/7 | **$+18** |
| 3of(`d_z144`, `m_gc_sz120`, `r_beta120`, `v_vr`) | S | NQZ4 | $+4.45 | $+2.14 | **$+1.23** | 5/7 | **$+17** |
| 3of(`d_z55`, `f_ret89`, `i_es_ret600`, `m_hg_int600`, `x_sweep) | L | NQZ4 | $+3.89 | $+3.84 | **$+0.86** | 5/7 | **$+10** |
| 3of(`d_z55`, `f_ofi89`, `i_es_sz600`, `m_gc_sz120`, `v_vr`) | S | NQZ4 | $+5.39 | $+2.61 | **$+0.86** | 5/7 | **$+8** |

_Ran 7.9 min on 4 workers._

## How far off were they?

`5,448` candidates reached cross-quarter validation.

| out-of-sample $/trade | candidates |
|---|---|
| -99.00 to -1.00 | 4,207 (77.2%) |
| -1.00 to -0.50 | 892 (16.4%) |
| -0.50 to +0.00 | 264 (4.8%) |
| +0.00 to +0.25 | 48 (0.9%) |
| +0.25 to +0.50 | 12 (0.2%) |
| +0.50 to +99.00 | 25 (0.5%) |

Best out-of-sample **$+1.91/trade**, median **$-1.45**. `85` were positive at all (1.6%), `11` were green in 5+ quarters.


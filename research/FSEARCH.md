# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 122 | 82,670 | 66,975 | 11,308 | 1,260 | 634 |
| NQZ4 | 127 | 140,740 | 152,982 | 34,758 | 2,879 | 802 |
| NQH5 | 131 | 140,740 | 127,185 | 10,629 | 677 | 862 |
| NQM5 | 127 | 140,740 | 119,916 | 2,758 | 135 | 961 |
| NQU5 | 121 | 140,740 | 143,677 | 40,699 | 5,619 | 896 |
| NQZ5 | 130 | 131,942 | 123,388 | 15,122 | 2,111 | 938 |
| NQH6 | 132 | 140,740 | 146,561 | 4,921 | 437 | 1,355 |
| NQM6 | 128 | 140,740 | 122,658 | 7,020 | 213 | 1,003 |

**1,003,342 scanned → 127,215 cleared the train gate → 13,331 also paid on the held-out 40% → 35 survived every other quarter.**

| rule | side | home | train | test | **out of sample** | green | **$/wk oos** |
|---|---|---|---|---|---|---|---|
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `g_gex|raw|hold4) | S | NQZ4 | $+3.74 | $+0.70 | **$+1.12** | 5/7 | **$+28** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `g_gex|raw|hold4) | S | NQZ4 | $+3.79 | $+1.04 | **$+1.11** | 5/7 | **$+27** |
| 3of(`b_agree55|raw|hold4`, `g_regime|raw|state`, `m_hg_int5|ac) | L | NQZ4 | $+6.18 | $+1.02 | **$+1.25** | 5/7 | **$+23** |
| 3of(`b_agree55|raw|hold4`, `g_regime|raw|state`, `m_hg_int5|ac) | L | NQZ4 | $+6.18 | $+1.02 | **$+1.24** | 5/7 | **$+23** |
| 2of(`b_agree55|raw|hold4`, `m_hg_int5|acc|hold4`, `p_rng21|d21) | L | NQZ4 | $+4.73 | $+2.48 | **$+1.12** | 5/7 | **$+22** |
| 2of(`b_agree55|raw|hold4`, `m_hg_int5|acc|hold4`, `p_rng21|d21) | L | NQZ4 | $+4.73 | $+2.48 | **$+1.11** | 5/7 | **$+22** |
| 3of(`b_agree55|d21|hold4`, `d_z144|rk55|cross`, `f_ofi21|d21|h) | S | NQZ4 | $+4.11 | $+1.53 | **$+0.76** | 5/7 | **$+20** |
| 3of(`b_agree|raw|hold4`, `f_ofi21|d21|hold4`, `g_gex|raw|hold4) | S | NQZ4 | $+5.15 | $+4.68 | **$+1.25** | 5/7 | **$+20** |
| 3of(`b_agree55|d21|hold4`, `d_z144|rk55|cross`, `f_ofi21|d21|h) | S | NQZ4 | $+4.11 | $+1.81 | **$+0.75** | 5/7 | **$+20** |
| 3of(`b_agree|raw|hold4`, `f_ofi21|d21|hold4`, `g_gex|raw|hold4) | S | NQZ4 | $+5.78 | $+5.29 | **$+1.17** | 6/7 | **$+19** |
| 3of(`b_agree55|d21|hold4`, `f_ofi21|d21|hold4`, `g_gex|raw|hol) | S | NQZ4 | $+5.61 | $+4.59 | **$+1.24** | 6/7 | **$+18** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|hold4`, `i_rty_ret600|rk23) | S | NQZ4 | $+6.74 | $+0.25 | **$+1.01** | 5/7 | **$+18** |
| 3of(`b_agree55|d21|hold4`, `g_gex|raw|state`, `r_beta30|d89|st) | S | NQZ4 | $+3.40 | $+0.40 | **$+1.11** | 5/6 | **$+18** |
| 3of(`b_agree55|d21|hold4`, `g_gex|raw|hold4`, `r_beta30|d89|st) | S | NQZ4 | $+3.40 | $+0.65 | **$+1.06** | 5/6 | **$+17** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `g_gex|raw|state) | S | NQZ4 | $+3.96 | $+0.08 | **$+0.54** | 5/7 | **$+16** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `g_gex|raw|hold4) | S | NQZ4 | $+3.96 | $+0.17 | **$+0.54** | 5/7 | **$+16** |
| 3of(`g_gex|raw|hold4`, `i_lead600|rk55|hold4`, `r_beta30|d89|h) | S | NQZ4 | $+4.64 | $+1.17 | **$+0.78** | 7/7 | **$+15** |
| 3of(`f_ret89|rk233|hold4`, `g_gex|raw|hold4`, `i_divRTY120|d21) | S | NQZ5 | $+3.44 | $+0.33 | **$+0.77** | 6/7 | **$+14** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|state`, `i_rty_ret600|rk23) | S | NQZ4 | $+5.01 | $+2.09 | **$+0.59** | 5/7 | **$+14** |
| 3of(`d_z55|rk55|hold4`, `f_ofi89|raw|hold4`, `i_lead600|rk55|s) | L | NQZ4 | $+3.17 | $+3.41 | **$+1.12** | 5/7 | **$+14** |
| 3of(`f_ret89|rk233|hold4`, `g_gex|raw|state`, `i_divRTY120|d21) | S | NQZ5 | $+3.44 | $+0.16 | **$+0.76** | 5/7 | **$+14** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `f_ofi21|d21|hol) | S | NQZ4 | $+5.02 | $+2.71 | **$+0.55** | 5/7 | **$+14** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `f_ofi21|d21|hol) | S | NQZ4 | $+5.02 | $+2.90 | **$+0.55** | 5/7 | **$+14** |
| 3of(`b_agree55|d21|hold4`, `f_ofi21|d21|hold4`, `g_gex|raw|hol) | S | NQZ4 | $+4.11 | $+1.45 | **$+0.79** | 5/7 | **$+13** |
| 3of(`g_gex|raw|state`, `i_rty_ret600|rk233|hold4`, `m_hg_int5|) | S | NQZ4 | $+5.07 | $+0.44 | **$+0.76** | 6/7 | **$+13** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|hold4`, `i_rty_ret600|rk23) | S | NQZ4 | $+5.01 | $+1.86 | **$+0.56** | 5/7 | **$+13** |
| 3of(`g_gex|raw|hold4`, `i_rty_ret600|rk233|hold4`, `m_hg_int5|) | S | NQZ4 | $+5.07 | $+0.41 | **$+0.73** | 6/7 | **$+13** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|hold4`, `i_lead600|rk55|st) | S | NQZ4 | $+4.16 | $+1.85 | **$+0.57** | 5/7 | **$+12** |
| 3of(`b_agree|raw|hold4`, `f_ofi1|d89|hold4`, `g_gex|raw|state`) | S | NQZ4 | $+5.31 | $+0.43 | **$+0.58** | 6/7 | **$+12** |
| 3of(`b_agree|raw|hold4`, `f_ofi1|d89|hold4`, `g_gex|raw|hold4`) | S | NQZ4 | $+5.31 | $+0.43 | **$+0.58** | 6/7 | **$+12** |

_Ran 11.8 min on 4 workers._

## How far off were they?

`13,312` candidates reached cross-quarter validation.

| out-of-sample $/trade | candidates |
|---|---|
| -99.00 to -1.00 | 8,339 (62.6%) |
| -1.00 to -0.50 | 3,421 (25.7%) |
| -0.50 to +0.00 | 1,159 (8.7%) |
| +0.00 to +0.25 | 191 (1.4%) |
| +0.25 to +0.50 | 109 (0.8%) |
| +0.50 to +99.00 | 93 (0.7%) |

Best out-of-sample **$+1.25/trade**, median **$-1.16**. `393` were positive at all (3.0%), `106` were green in 5+ quarters.


# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 167 | 553,777 | 610,626 | 48,076 | 6,481 | 1,095 |
| NQZ4 | 178 | 813,242 | 1,033,188 | 183,585 | 10,911 | 1,002 |
| NQH5 | 182 | 813,809 | 873,804 | 58,727 | 4,841 | 1,122 |
| NQM5 | 173 | 813,242 | 920,113 | 14,600 | 1,045 | 1,277 |
| NQU5 | 171 | 813,242 | 963,091 | 200,139 | 33,000 | 1,124 |
| NQZ5 | 182 | 787,630 | 949,571 | 72,676 | 7,579 | 1,305 |
| NQH6 | 182 | 813,242 | 961,895 | 31,549 | 1,799 | 1,606 |
| NQM6 | 180 | 813,809 | 901,714 | 25,918 | 587 | 1,456 |

**7,214,002 scanned → 635,270 cleared the train gate → 66,243 also paid on the held-out 40% → 100 survived every other quarter.**

| rule | side | home | train | test | **out of sample** | green | **$/wk oos** |
|---|---|---|---|---|---|---|---|
| 3of(`g_gex|raw|hold4`, `v_vr|raw|hold4`, `w_fbreak|raw|hold4`,) | S | NQZ4 | $+5.36 | $+3.03 | **$+2.37** | 6/7 | **$+41** |
| 3of(`g_gex|raw|hold4`, `r_beta30|d89|hold4`, `v_vr|raw|hold4`,) | S | NQZ4 | $+4.33 | $+2.93 | **$+1.37** | 5/7 | **$+38** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|hold4`, `i_rty_ret600|rk23) | S | NQZ4 | $+6.11 | $+0.03 | **$+1.42** | 5/7 | **$+38** |
| 3of(`c_lunch|d89|state`, `g_gex|raw|hold4`, `i_lead600|rk55|st) | S | NQZ4 | $+5.04 | $+4.83 | **$+0.80** | 5/7 | **$+36** |
| 3of(`g_gex|raw|hold4`, `m_hg_int5|acc|hold4`, `v_vr|raw|hold4`) | S | NQZ4 | $+7.65 | $+0.52 | **$+2.54** | 5/7 | **$+35** |
| 2of(`c_lunch|d89|hold4`, `w_fbreak|d89|hold4`) | L | NQH5 | $+4.08 | $+1.64 | **$+0.65** | 5/7 | **$+35** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|state`, `v_vr|raw|hold4`, ) | S | NQZ4 | $+4.87 | $+2.11 | **$+1.22** | 5/7 | **$+34** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|hold4`, `v_vr|raw|hold4`, ) | S | NQZ4 | $+4.87 | $+1.81 | **$+1.21** | 5/7 | **$+34** |
| 2of(`c_lunch|d89|state`, `w_fbreak|d89|hold4`) | L | NQH5 | $+2.65 | $+2.76 | **$+0.59** | 5/7 | **$+32** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|state`, `v_vr|raw|hold4`, ) | S | NQZ4 | $+5.81 | $+3.51 | **$+1.12** | 6/7 | **$+32** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|hold4`, `v_vr|raw|hold4`, ) | S | NQZ4 | $+5.81 | $+3.21 | **$+1.11** | 6/7 | **$+31** |
| 3of(`g_gex|raw|hold4`, `i_rty_ret600|rk233|hold4`, `v_vr|raw|h) | S | NQZ4 | $+5.40 | $+2.11 | **$+1.03** | 5/7 | **$+29** |
| 3of(`g_gex|raw|hold4`, `r_beta30|d89|hold4`, `v_vr|raw|hold4`,) | S | NQZ4 | $+4.55 | $+4.35 | **$+1.00** | 5/7 | **$+28** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `g_gex|raw|hold4) | S | NQZ4 | $+3.74 | $+0.70 | **$+1.12** | 5/7 | **$+28** |
| 3of(`b_agree|raw|hold4`, `d_z144|rk55|cross`, `g_gex|raw|hold4) | S | NQZ4 | $+3.79 | $+1.04 | **$+1.11** | 5/7 | **$+27** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|hold4`, `m_hg_int5|acc|hol) | S | NQZ4 | $+4.29 | $+0.50 | **$+0.92** | 5/7 | **$+25** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|state`, `m_hg_int5|acc|hol) | S | NQZ4 | $+4.29 | $+0.44 | **$+0.90** | 5/7 | **$+25** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|hold4`, `i_rty_ret600|rk23) | S | NQZ4 | $+3.74 | $+1.30 | **$+1.01** | 6/7 | **$+24** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|hold4`, `v_vr|raw|hold4`, ) | S | NQZ4 | $+5.97 | $+5.82 | **$+1.31** | 5/7 | **$+24** |
| 3of(`d_ratio|raw|state`, `g_gex|raw|state`, `m_hg_int5|acc|hol) | S | NQZ4 | $+4.85 | $+0.03 | **$+1.33** | 5/6 | **$+23** |
| 3of(`f_ofi21|d21|hold4`, `g_gex|raw|hold4`, `v_vr|raw|hold4`, ) | S | NQZ4 | $+5.74 | $+2.78 | **$+1.26** | 6/7 | **$+23** |
| 3of(`b_agree55|raw|hold4`, `g_regime|raw|state`, `m_hg_int5|ac) | L | NQZ4 | $+6.18 | $+1.02 | **$+1.25** | 5/7 | **$+23** |
| 3of(`b_agree55|raw|hold4`, `g_regime|raw|state`, `m_hg_int5|ac) | L | NQZ4 | $+6.18 | $+1.02 | **$+1.24** | 5/7 | **$+23** |
| 3of(`b_agree55|raw|hold4`, `g_gex|raw|hold4`, `v_vr|raw|hold4`) | S | NQZ4 | $+3.05 | $+1.48 | **$+1.13** | 6/7 | **$+23** |
| 3of(`g_gex|raw|hold4`, `r_beta30|d89|hold4`, `v_vr|raw|hold4`,) | S | NQZ4 | $+5.16 | $+0.01 | **$+1.27** | 5/7 | **$+23** |
| 3of(`g_gex|raw|hold4`, `i_rty_ret600|rk233|hold4`, `v_vr|raw|h) | S | NQZ4 | $+6.31 | $+1.58 | **$+1.21** | 5/7 | **$+23** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|hold4`, `m_hg_int5|acc|hol) | S | NQZ4 | $+4.24 | $+0.19 | **$+0.81** | 5/7 | **$+22** |
| 3of(`g_gex|raw|hold4`, `r_beta30|d89|state`, `v_vr|raw|hold4`,) | S | NQZ4 | $+4.43 | $+3.89 | **$+0.76** | 5/7 | **$+22** |
| 2of(`b_agree55|raw|hold4`, `m_hg_int5|acc|hold4`, `p_rng21|d21) | L | NQZ4 | $+4.73 | $+2.48 | **$+1.12** | 5/7 | **$+22** |
| 3of(`d_z144|rk55|cross`, `g_gex|raw|state`, `m_hg_int5|acc|hol) | S | NQZ4 | $+4.24 | $+0.14 | **$+0.79** | 5/7 | **$+22** |

_Ran 44.0 min on 4 workers._

## How far off were they?

`66,220` candidates reached cross-quarter validation.

| out-of-sample $/trade | candidates |
|---|---|
| -99.00 to -1.00 | 45,854 (69.2%) |
| -1.00 to -0.50 | 14,520 (21.9%) |
| -0.50 to +0.00 | 4,486 (6.8%) |
| +0.00 to +0.25 | 722 (1.1%) |
| +0.25 to +0.50 | 355 (0.5%) |
| +0.50 to +99.00 | 283 (0.4%) |

Best out-of-sample **$+2.54/trade**, median **$-1.26**. `1,360` were positive at all (2.1%), `330` were green in 5+ quarters.


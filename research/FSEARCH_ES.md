# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| ESZ4 | 212 | 817,484 | 750,926 | 324,986 | 29,577 | 1,694 |
| ESH5 | 197 | 817,283 | 586,877 | 262,261 | 47,859 | 725 |
| ESU5 | 205 | 817,484 | 663,115 | 330,370 | 77,960 | 929 |
| ESZ5 | 209 | 791,806 | 657,045 | 281,326 | 22,065 | 1,234 |
| ESH6 | 203 | 817,283 | 590,065 | 308,285 | 22,642 | 489 |
| ESM6 | 207 | 817,484 | 591,323 | 332,621 | 36,182 | 504 |

**3,839,351 scanned → 1,839,849 cleared the train gate → 236,285 also paid on the held-out 40% → 139 survived every other quarter.**

| rule | side | home | train | test | **out of sample** | green | **$/wk oos** |
|---|---|---|---|---|---|---|---|
| 2of(`b_agree|raw|hold8`, `g_gex|z288|state`, `m_cl_int30|acc|h) | S | ESH5 | $+8.40 | $+1.29 | **$+5.42** | 4/4 | **$+33** |
| 2of(`b_agree|raw|hold8`, `g_gex|z288|hold4`, `m_cl_int30|acc|h) | S | ESH5 | $+7.87 | $+1.29 | **$+5.29** | 4/4 | **$+32** |
| 2of(`b_agree|raw|hold8`, `g_gex|z288|hold8`, `m_cl_int30|acc|h) | S | ESH5 | $+7.23 | $+1.32 | **$+4.89** | 4/4 | **$+29** |
| 2of(`b_agree|raw|hold8`, `g_gex|z288|state`, `m_cl_int30|acc|h) | S | ESH5 | $+6.05 | $+0.53 | **$+3.25** | 5/5 | **$+26** |
| 2of(`b_agree55|raw|state`, `i_nq_sz5|rk233|hold8`, `m_cl_int30) | S | ESH5 | $+5.19 | $+0.36 | **$+1.19** | 4/5 | **$+25** |
| 2of(`b_agree|raw|hold8`, `m_cl_int30|acc|hold8`, `t_gapmax|raw) | S | ESH5 | $+5.74 | $+0.58 | **$+1.35** | 5/5 | **$+25** |
| 2of(`b_agree55|raw|state`, `i_nq_sz5|rk233|hold8`, `m_cl_int30) | S | ESH5 | $+5.19 | $+0.37 | **$+1.15** | 4/5 | **$+24** |
| 2of(`b_agree|raw|hold8`, `d_secs|rk233|hold4`, `m_cl_int30|acc) | S | ESH5 | $+4.88 | $+0.43 | **$+0.97** | 4/5 | **$+23** |
| 2of(`g_gex|z288|state`, `i_nq_ret5|rk233|hold8`, `p_wceff30|rk) | S | ESH5 | $+3.99 | $+3.34 | **$+1.65** | 5/5 | **$+23** |
| 2of(`b_agree|raw|hold8`, `d_secs|rk233|hold8`, `m_cl_int30|acc) | S | ESH5 | $+5.54 | $+0.61 | **$+1.15** | 4/5 | **$+22** |
| 2of(`b_agree55|raw|hold8`, `i_nq_ret5|rk233|hold8`, `m_cl_int3) | S | ESH5 | $+3.38 | $+0.54 | **$+1.23** | 5/5 | **$+22** |
| 2of(`b_agree55|raw|hold8`, `i_nq_ret5|rk233|hold8`, `m_cl_int3) | S | ESH5 | $+3.18 | $+0.54 | **$+1.20** | 4/5 | **$+21** |
| 2of(`b_agree|raw|hold8`, `m_cl_int30|acc|hold8`, `t_gapmax|raw) | S | ESH5 | $+5.74 | $+0.67 | **$+1.15** | 5/5 | **$+21** |
| 2of(`g_gex|z288|hold4`, `i_nq_sz5|rk233|hold8`, `m_cl_int30|ac) | S | ESH5 | $+4.49 | $+0.63 | **$+3.03** | 4/5 | **$+20** |
| 2of(`b_agree55|raw|state`, `d_secs|rk233|hold8`, `m_cl_int30|a) | S | ESH5 | $+3.45 | $+0.34 | **$+0.66** | 4/5 | **$+20** |
| 2of(`d_ratio|rk55|hold8`, `i_lead5|rk233|hold8`, `p_wceff5|rk2) | S | ESM6 | $+4.06 | $+4.53 | **$+1.20** | 4/5 | **$+20** |
| 2of(`i_lead5|rk233|hold8`, `m_gc_ret5|rk233|hold8`, `o_gap|raw) | S | ESM6 | $+2.69 | $+2.64 | **$+0.62** | 4/5 | **$+20** |
| 2of(`b_agree55|raw|state`, `i_nq_ret5|rk233|hold8`, `m_cl_int3) | S | ESH5 | $+3.46 | $+0.50 | **$+0.89** | 4/5 | **$+20** |
| 2of(`b_agree55|raw|hold8`, `g_gex|z288|state`, `i_nq_ret5|rk23) | S | ESH5 | $+5.99 | $+2.91 | **$+1.35** | 4/5 | **$+20** |
| 2of(`b_agree55|raw|hold8`, `g_gex|z288|state`, `i_nq_sz5|rk233) | S | ESH5 | $+3.42 | $+2.65 | **$+1.30** | 5/5 | **$+19** |
| 2of(`b_agree55|raw|state`, `d_secs|rk233|hold8`, `m_cl_int30|a) | S | ESH5 | $+3.56 | $+0.32 | **$+0.62** | 4/5 | **$+19** |
| 2of(`b_agree55|raw|hold8`, `d_secs|rk233|hold8`, `g_gex|z288|h) | S | ESH5 | $+3.82 | $+2.30 | **$+0.95** | 4/5 | **$+19** |
| 2of(`g_gex|z288|state`, `i_nq_sz5|rk233|hold8`, `m_cl_int30|ac) | S | ESH5 | $+4.45 | $+0.67 | **$+2.76** | 4/5 | **$+19** |
| 2of(`g_gex|z288|hold8`, `i_nq_sz5|rk233|hold8`, `m_cl_int30|ac) | S | ESH5 | $+4.27 | $+0.66 | **$+2.86** | 4/5 | **$+19** |
| 2of(`b_agree|raw|hold8`, `d_secs|rk233|hold8`, `m_cl_int30|acc) | S | ESH5 | $+5.54 | $+0.70 | **$+0.97** | 4/5 | **$+19** |
| 2of(`b_agree55|raw|state`, `i_nq_ret5|rk233|hold8`, `m_cl_int3) | S | ESH5 | $+3.61 | $+0.49 | **$+0.84** | 4/5 | **$+19** |
| 2of(`b_agree55|raw|hold8`, `d_secs|rk233|hold8`, `g_gex|z288|h) | S | ESH5 | $+3.79 | $+2.37 | **$+0.89** | 4/5 | **$+18** |
| 2of(`i_lead5|rk233|hold8`, `m_gc_ret5|rk233|hold8`, `o_gap|raw) | S | ESM6 | $+2.69 | $+2.69 | **$+0.54** | 4/5 | **$+17** |
| 2of(`b_agree|raw|hold8`, `i_nq_sz5|rk233|hold8`, `m_cl_int30|a) | S | ESH5 | $+8.31 | $+0.69 | **$+0.95** | 4/5 | **$+17** |
| 2of(`b_agree55|raw|hold4`, `g_gex|z288|hold8`, `i_nq_ret5|rk23) | S | ESH5 | $+5.32 | $+2.98 | **$+1.14** | 4/5 | **$+17** |

_Ran 34.1 min on 4 workers._

## How far off were they?

`19,803` candidates reached cross-quarter validation.

| out-of-sample $/trade | candidates |
|---|---|
| -99.00 to -1.00 | 9,756 (49.3%) |
| -1.00 to -0.50 | 5,127 (25.9%) |
| -0.50 to +0.00 | 3,032 (15.3%) |
| +0.00 to +0.25 | 705 (3.6%) |
| +0.25 to +0.50 | 469 (2.4%) |
| +0.50 to +99.00 | 714 (3.6%) |

Best out-of-sample **$+5.42/trade**, median **$-0.99**. `1,888` were positive at all (9.5%), `284` were green in 4+ quarters.


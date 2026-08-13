# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 207 | 557,887 | 618,553 | 182,601 | 21,916 | 1,045 |
| NQZ4 | 207 | 817,484 | 1,063,151 | 327,788 | 22,338 | 5,632 |
| NQH5 | 211 | 817,484 | 884,121 | 106,727 | 7,367 | 1,732 |
| NQM5 | 202 | 817,484 | 890,841 | 13,695 | 1,458 | 2,143 |
| NQU5 | 207 | 817,484 | 805,457 | 239,574 | 54,347 | 2,258 |
| NQZ5 | 199 | 791,806 | 663,179 | 67,087 | 6,350 | 2,097 |
| NQH6 | 209 | 817,484 | 759,700 | 55,916 | 3,266 | 2,484 |
| NQM6 | 205 | 817,484 | 951,830 | 25,129 | 682 | 2,410 |

**6,636,832 scanned → 1,018,517 cleared the train gate → 117,724 also paid on the held-out 40% → 2 survived every other quarter.**

| rule | side | home | train | test | **out of sample** | green | **$/wk oos** |
|---|---|---|---|---|---|---|---|
| 3of(`d_z144|d21|state`, `f_wcint30|d21|hold4`, `i_ym_vol30|d21) | S | NQU5 | $+3.37 | $+7.38 | **$+0.73** | 5/7 | **$+16** |
| 3of(`b_agree55|raw|hold4`, `f_ret89|z288|hold8`, `g_gex|z288|h) | S | NQZ5 | $+4.93 | $+2.01 | **$+0.54** | 5/7 | **$+10** |

_Ran 5.1 min on 4 workers._

## How far off were they?

`19,999` candidates reached cross-quarter validation.

| out-of-sample $/trade | candidates |
|---|---|
| -99.00 to -1.00 | 16,885 (84.4%) |
| -1.00 to -0.50 | 2,472 (12.4%) |
| -0.50 to +0.00 | 517 (2.6%) |
| +0.00 to +0.25 | 67 (0.3%) |
| +0.25 to +0.50 | 45 (0.2%) |
| +0.50 to +99.00 | 13 (0.1%) |

Best out-of-sample **$+2.05/trade**, median **$-1.37**. `125` were positive at all (0.6%), `31` were green in 5+ quarters.


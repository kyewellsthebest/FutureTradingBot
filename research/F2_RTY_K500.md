# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| RTYU4 | 200 | 557,887 | 290,409 | 185,104 | 0 | 362 |
| RTYZ4 | 208 | 817,484 | 430,551 | 179,966 | 0 | 551 |
| RTYH5 | 202 | 817,484 | 343,276 | 148,675 | 0 | 569 |
| RTYM5 | 208 | 817,484 | 184,839 | 130,175 | 0 | 278 |
| RTYU5 | 205 | 817,484 | 247,190 | 173,443 | 0 | 352 |
| RTYZ5 | 211 | 817,484 | 378,281 | 166,524 | 0 | 552 |
| RTYH6 | 204 | 817,484 | 309,367 | 157,646 | 0 | 451 |
| RTYM6 | 210 | 817,484 | 468,497 | 415,129 | 0 | 305 |

**2,652,410 scanned → 1,556,662 cleared the train gate → 0 also paid on the held-out 40% → 0 survived every other quarter.**

**Nothing survived out of sample** — but this time the search actually looked at the data.

_Ran 39.0 min on 4 workers._

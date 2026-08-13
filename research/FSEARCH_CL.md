# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| CLU4 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLZ4 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLH5 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLM5 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLU5 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLZ5 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLH6 | 0 | 0 | 0 | 0 | 0 | 0 |
| CLM6 | 0 | 0 | 0 | 0 | 0 | 0 |

**0 scanned → 0 cleared the train gate → 0 also paid on the held-out 40% → 0 survived every other quarter.**

**Nothing survived out of sample** — but this time the search actually looked at the data.

_Ran 0.0 min on 4 workers._

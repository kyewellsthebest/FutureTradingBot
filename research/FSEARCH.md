# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 70 | 4,000 | 2,494 | 130 | 23 | 286 |
| NQZ4 | 69 | 4,000 | 2,414 | 127 | 16 | 139 |
| NQH5 | 68 | 4,000 | 2,668 | 133 | 21 | 113 |
| NQM5 | 58 | 4,000 | 2,468 | 80 | 5 | 19 |
| NQU5 | 69 | 4,000 | 2,867 | 355 | 43 | 23 |
| NQZ5 | 69 | 4,000 | 2,833 | 111 | 10 | 18 |
| NQH6 | 64 | 4,000 | 2,728 | 55 | 1 | 19 |
| NQM6 | 67 | 4,000 | 2,917 | 47 | 7 | 25 |

**21,389 scanned → 1,038 cleared the train gate → 126 also paid on the held-out 40% → 0 survived every other quarter.**

**Nothing survived out of sample** — but this time the search actually looked at the data.

_Ran 4.2 min on 4 workers._

# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 78 | 80,688 | 53,120 | 3,661 | 529 | 1,102 |
| NQZ4 | 75 | 138,650 | 59,934 | 8,257 | 1,695 | 961 |
| NQH5 | 73 | 138,650 | 71,671 | 2,813 | 258 | 1,026 |
| NQM5 | 67 | 138,650 | 46,694 | 1,764 | 84 | 772 |
| NQU5 | 75 | 138,650 | 80,029 | 14,857 | 1,944 | 1,125 |
| NQZ5 | 77 | 129,906 | 67,422 | 5,350 | 572 | 1,033 |
| NQH6 | 74 | 138,650 | 60,129 | 1,972 | 199 | 1,066 |
| NQM6 | 73 | 138,650 | 76,928 | 3,059 | 240 | 1,087 |

**515,927 scanned → 41,733 cleared the train gate → 5,521 also paid on the held-out 40% → 0 survived every other quarter.**

**Nothing survived out of sample** — but this time the search actually looked at the data.

_Ran 2.6 min on 4 workers._

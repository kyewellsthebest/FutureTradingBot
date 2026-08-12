# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| NQU4 | 122 | 82,670 | 66,975 | 11,308 | 1,260 | 631 |
| NQZ4 | 127 | 140,740 | 152,982 | 34,758 | 2,879 | 804 |
| NQH5 | 131 | 140,740 | 127,185 | 10,629 | 677 | 876 |
| NQM5 | 127 | 140,740 | 119,916 | 2,758 | 135 | 975 |
| NQU5 | 121 | 140,740 | 143,677 | 40,699 | 5,619 | 871 |
| NQZ5 | 130 | 131,942 | 123,388 | 15,122 | 2,111 | 937 |
| NQH6 | 132 | 140,740 | 146,561 | 4,921 | 437 | 1,395 |
| NQM6 | 128 | 140,740 | 122,658 | 7,020 | 213 | 1,003 |

**1,003,342 scanned → 127,215 cleared the train gate → 13,331 also paid on the held-out 40% → 0 survived every other quarter.**

**Nothing survived out of sample** — but this time the search actually looked at the data.

_Ran 10.7 min on 4 workers._

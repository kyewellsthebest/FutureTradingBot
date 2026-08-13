# Fast validated search

The previous run searched **10 features out of 196** — legs were appended alphabetically, ten per feature, then each data type's list was truncated to the first ten, so the alphabetically first feature consumed the whole quota. Order flow contributed one feature out of forty. That, not the rarity of edge, is why it found nothing.

Legs are now scored and the best per type kept, capped at three thresholds per feature so one feature cannot crowd out the rest.

| quarter | features | combos | scanned | cleared train gate | + held-out test | combos/sec |
|---|---|---|---|---|---|---|
| RTYU4 | 200 | 557,887 | 614,451 | 450,438 | 65,046 | 799 |
| RTYZ4 | 208 | 817,484 | 967,747 | 560,139 | 33,988 | 1,013 |
| RTYH5 | 202 | 817,484 | 816,326 | 450,849 | 27,435 | 1,087 |
| RTYM5 | 208 | 817,484 | 689,913 | 526,308 | 79,866 | 687 |
| RTYU5 | 205 | 817,484 | 662,876 | 522,549 | 138,452 | 3,424 |
| RTYZ5 | 211 | 817,484 | 830,052 | 462,474 | 48,161 | 4,304 |
| RTYH6 | 204 | 817,484 | 739,184 | 478,155 | 32,375 | 2,243 |
| RTYM6 | 210 | 817,484 | 1,087,493 | 965,072 | 227,621 | 1,479 |

**6,408,042 scanned → 4,415,984 cleared the train gate → 652,944 also paid on the held-out 40% → 0 survived every other quarter.**

**Nothing survived out of sample** — but this time the search actually looked at the data.

_Ran 12.5 min on 4 workers._

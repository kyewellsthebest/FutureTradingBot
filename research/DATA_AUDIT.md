# Is the tick data itself correct?

Every result in this project rests on the parquet tapes in `data/tick/raw`. If those are wrong, everything built on them is wrong the same way, and internal cross-checking would never reveal it -- every test inherits the same fault and agrees with the others.

This is not hypothetical. Ledger hypothesis #21 was **retracted as an unsorted-tape artifact**: the raw parquets were 86-88% out of time order and produced a completely fictional result that passed a synthetic null. A data bug in this repo has already manufactured a finding once.

So this compares the tapes against an **independent vendor** -- Polygon 5-minute bars, 184,935 rows, 2023-12-15 to 2026-07-30. Two vendors, two pipelines, two clocks.

| contract | days both | close match | median |diff| | p99 |diff| | tape range / poly range | out-of-order rows |
|---|---|---|---|---|---|---|
| NQU4 | 78 | 99.7% | 0.00 | 0.00 | 1.000 | 0.0% |
| NQZ4 | 78 | 99.7% | 0.00 | 0.25 | 1.000 | 0.0% |
| NQH5 | 78 | 99.6% | 0.00 | 0.25 | 1.000 | 0.0% |
| NQM5 | 77 | 99.5% | 0.00 | 0.25 | 1.000 | 0.0% |
| NQU5 | 78 | 99.6% | 0.00 | 0.25 | 1.000 | 0.0% |
| NQZ5 | 78 | 99.6% | 0.00 | 0.25 | 1.000 | 0.0% |
| NQH6 | 78 | 99.4% | 0.00 | 0.25 | 1.000 | 0.0% |
| NQM6 | 78 | 99.4% | 0.00 | 0.25 | 1.000 | 0.0% |

`close match` is the share of 5-minute bars whose closes agree within one tick. `tape range / poly range` is the ratio of total high-low range: **below 1.0 means the tape is missing prints**, which would make every stop look less likely to be hit and every backtest in this repo look better than reality. `out-of-order rows` is the #21 failure mode measured directly on each raw file, before any sorting.

Worst close agreement: **NQM6 at 99.4%**. Range ratio spans 1.000 to 1.000.

**Verdict: the tapes agree with an independent vendor.** The foundation is sound and the negative results stand on it.


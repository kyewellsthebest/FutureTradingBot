# Four data types at once — does any of them carry information?

Every search so far read one stream: the NQ price path. Its ceiling measured zero. That is a fact about **that stream**, not about the market. This loads three more and asks the question that has to come first — is there anything in here at all — before another configuration is enumerated.

`366,189` tick-event bars of 500 prints (~588 bars/day, 623 trading days, 8 sequential NQ quarters — two continuous years). `242` features. Foreign tapes are read as of **bar close minus 250 ms**, so nothing contemporaneous can leak in through them.

## Stream coverage

| NQ quarter | ES | YM | RTY | CL | GC | HG |
|---|---|---|---|---|---|---|
| NQU4 | 0% | 100% | 100% | 100% | 0% | 0% |
| NQZ4 | 100% | 100% | 100% | 100% | 100% | 100% |
| NQH5 | 100% | 100% | 100% | 100% | 0% | 0% |
| NQM5 | 0% | 100% | 100% | 100% | 0% | 0% |
| NQU5 | 100% | 100% | 100% | 100% | 0% | 0% |
| NQZ5 | 100% | 100% | 100% | 100% | 0% | 100% |
| NQH6 | 100% | 100% | 100% | 100% | 0% | 0% |
| NQM6 | 100% | 100% | 100% | 100% | 100% | 0% |

GC and HG only have dense tape in a few quarters — thin contracts are rejected by a 5,000-prints-a-day floor rather than silently averaged in, because a name-based pick once grabbed a 22,805-print stub and invented a market that traded 161 ticks a day.

## The ceiling of each data set

IC is the out-of-sample correlation between what the model predicted and what happened. The shuffled column is the identical model on scrambled outcomes — that is what a boosted tree invents from nothing. Only the difference is real.

### 1 bar ahead (~2 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 30 | +0.0079 | +0.0013 | **+0.0066** | 159 | $+14 | **$-1,510** |
| + NQ order flow | 54 | +0.0095 | -0.0006 | **+0.0101** | 162 | $+19 | **$-1,516** |
| + index complex (ES/YM/RTY) | 130 | +0.0064 | +0.0016 | +0.0048 | 153 | $+11 | **$-1,465** |
| + macro complex (CL/GC/HG) | 118 | +0.0053 | -0.0004 | **+0.0057** | 143 | $+12 | **$-1,362** |
| all four types | 242 | +0.0067 | -0.0031 | **+0.0098** | 153 | $+13 | **$-1,456** |
| everything EXCEPT price path | 212 | +0.0052 | +0.0020 | +0.0031 | 156 | $+11 | **$-1,500** |

Noise floor at this sample size is ±0.0055 (3 standard errors on 292,945 out-of-sample bars); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

### 5 bars ahead (~12 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 30 | +0.0149 | +0.0008 | **+0.0141** | 102 | $+60 | **$-719** |
| + NQ order flow | 54 | +0.0104 | +0.0004 | **+0.0100** | 100 | $+49 | **$-751** |
| + index complex (ES/YM/RTY) | 130 | +0.0125 | +0.0003 | **+0.0122** | 89 | $+55 | **$-608** |
| + macro complex (CL/GC/HG) | 118 | +0.0060 | -0.0022 | **+0.0082** | 85 | $+28 | **$-700** |
| all four types | 242 | +0.0057 | +0.0008 | +0.0048 | 85 | $+26 | **$-714** |
| everything EXCEPT price path | 212 | +0.0058 | -0.0009 | **+0.0067** | 87 | $+22 | **$-759** |

Noise floor at this sample size is ±0.0055 (3 standard errors on 292,920 out-of-sample bars); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

### 20 bars ahead (~49 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 30 | +0.0121 | -0.0005 | **+0.0126** | 74 | $+108 | **$-196** |
| + NQ order flow | 54 | +0.0089 | -0.0009 | **+0.0098** | 76 | $+141 | **$-50** |
| + index complex (ES/YM/RTY) | 130 | +0.0133 | +0.0001 | **+0.0132** | 65 | $+136 | **$+30** |
| + macro complex (CL/GC/HG) | 118 | +0.0032 | +0.0006 | +0.0026 | 60 | $+62 | **$-283** |
| all four types | 242 | +0.0115 | +0.0017 | **+0.0098** | 63 | $+110 | **$-76** |
| everything EXCEPT price path | 212 | +0.0072 | +0.0010 | **+0.0062** | 65 | $+43 | **$-430** |

Noise floor at this sample size is ±0.0055 (3 standard errors on 292,824 out-of-sample bars); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

## The stream-shift control

The foreign tapes are slid 11.5 days along the calendar and rejoined to the same NQ bars. Their volatility, their flow, their autocorrelation are all untouched — only the alignment with NQ is destroyed. A real cross-market effect has to die here. Anything that survives was never cross-market information and is a bug in the join.

| data | horizon | real − shuffled | **shifted − shuffled** | verdict |
|---|---|---|---|---|
| + index complex (ES/YM/RTY) | 1 | +0.0048 | +0.0025 | nothing to kill (below the ±0.0055 noise floor) |
| + index complex (ES/YM/RTY) | 5 | +0.0122 | +0.0083 | **SURVIVES THE SHIFT — leak, do not trade** |
| + index complex (ES/YM/RTY) | 20 | +0.0132 | +0.0113 | **SURVIVES THE SHIFT — leak, do not trade** |
| + macro complex (CL/GC/HG) | 1 | +0.0057 | +0.0073 | **SURVIVES THE SHIFT — leak, do not trade** |
| + macro complex (CL/GC/HG) | 5 | +0.0082 | +0.0131 | **SURVIVES THE SHIFT — leak, do not trade** |
| + macro complex (CL/GC/HG) | 20 | +0.0026 | +0.0086 | nothing to kill (below the ±0.0055 noise floor) |
| all four types | 1 | +0.0098 | +0.0076 | **SURVIVES THE SHIFT — leak, do not trade** |
| all four types | 5 | +0.0048 | +0.0027 | nothing to kill (below the ±0.0055 noise floor) |
| all four types | 20 | +0.0098 | +0.0126 | **SURVIVES THE SHIFT — leak, do not trade** |
| everything EXCEPT price path | 1 | +0.0031 | -0.0005 | nothing to kill (below the ±0.0055 noise floor) |
| everything EXCEPT price path | 5 | +0.0067 | +0.0041 | **SURVIVES THE SHIFT — leak, do not trade** |
| everything EXCEPT price path | 20 | +0.0062 | +0.0126 | **SURVIVES THE SHIFT — leak, do not trade** |

## What this decides

A round turn costs **$1.99** and the model trades a continuous position, so cost is charged on how much the position CHANGES, not once per opinion. At 588 bars a day, $0.10/bar would be $294 a week — so the net column is the whole answer, and any set whose real−shuffled gap sits at zero is a stream that cannot be searched profitably no matter how many configurations are thrown at it.

Data types 5 and 6 — order book and options — are stubbed in `fuse.py` behind `load_book()` and `load_options()`. They drop into the same clock, the same lag rail and the same ablation the moment the files exist; see TODO_FOR_USER.md for the exact format.

_Ran in 28 min._

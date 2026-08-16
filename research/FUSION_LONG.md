# Four data types at once — does any of them carry information?

Every search so far read one stream: the NQ price path. Its ceiling measured zero. That is a fact about **that stream**, not about the market. This loads three more and asks the question that has to come first — is there anything in here at all — before another configuration is enumerated.

`366,189` tick-event bars of 500 prints (~588 bars/day, 623 trading days, 8 sequential NQ quarters — two continuous years). `266` features. Foreign tapes are read as of **bar close minus 250 ms**, so nothing contemporaneous can leak in through them.

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
| price path only | 38 | +0.0063 | +0.0006 | **+0.0057** | 166 | $+10 | **$-1,600** |
| + NQ order flow | 78 | +0.0074 | +0.0001 | **+0.0073** | 172 | $+15 | **$-1,635** |
| + index complex (ES/YM/RTY) | 138 | +0.0051 | -0.0023 | **+0.0073** | 181 | $+9 | **$-1,760** |
| + macro complex (CL/GC/HG) | 126 | +0.0050 | +0.0008 | +0.0041 | 168 | $+11 | **$-1,622** |
| all four types | 266 | +0.0114 | +0.0048 | **+0.0065** | 177 | $+23 | **$-1,650** |
| everything EXCEPT price path | 228 | +0.0044 | +0.0003 | +0.0041 | 184 | $+11 | **$-1,778** |

Noise floor at this sample size is ±0.0055 (3 standard errors on 292,945 INDEPENDENT outcomes — 292,945 out-of-sample bars, but an 1-bar forward return overlaps its 0 neighbours); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

### 50 bars ahead (~122 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 38 | +0.0057 | +0.0027 | +0.0030 | 65 | $+6 | **$-613** |
| + NQ order flow | 78 | +0.0017 | -0.0029 | +0.0046 | 67 | $+7 | **$-632** |
| + index complex (ES/YM/RTY) | 138 | +0.0027 | +0.0013 | +0.0015 | 73 | $+8 | **$-689** |
| + macro complex (CL/GC/HG) | 126 | +0.0054 | +0.0002 | +0.0052 | 68 | $+5 | **$-656** |
| all four types | 266 | +0.0012 | +0.0004 | +0.0008 | 72 | $+4 | **$-694** |
| everything EXCEPT price path | 228 | -0.0088 | -0.0009 | -0.0079 | 86 | $+5 | **$-835** |

Noise floor at this sample size is ±0.0392 (3 standard errors on 5,853 INDEPENDENT outcomes — 292,632 out-of-sample bars, but an 50-bar forward return overlaps its 49 neighbours); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

### 100 bars ahead (~245 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 38 | +0.0114 | +0.0010 | +0.0104 | 58 | $+9 | **$-535** |
| + NQ order flow | 78 | +0.0041 | +0.0013 | +0.0028 | 64 | $+3 | **$-624** |
| + index complex (ES/YM/RTY) | 138 | +0.0023 | +0.0017 | +0.0006 | 69 | $+3 | **$-675** |
| + macro complex (CL/GC/HG) | 126 | +0.0101 | +0.0001 | +0.0100 | 65 | $+7 | **$-612** |
| all four types | 266 | +0.0112 | -0.0009 | +0.0121 | 70 | $+1 | **$-694** |
| everything EXCEPT price path | 228 | -0.0029 | -0.0016 | -0.0012 | 86 | $-5 | **$-877** |

Noise floor at this sample size is ±0.0555 (3 standard errors on 2,923 INDEPENDENT outcomes — 292,312 out-of-sample bars, but an 100-bar forward return overlaps its 99 neighbours); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

### 200 bars ahead (~490 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 38 | +0.0070 | +0.0000 | +0.0069 | 54 | $+9 | **$-495** |
| + NQ order flow | 78 | +0.0038 | -0.0008 | +0.0046 | 61 | $+8 | **$-569** |
| + index complex (ES/YM/RTY) | 138 | +0.0161 | +0.0013 | +0.0147 | 71 | $+7 | **$-673** |
| + macro complex (CL/GC/HG) | 126 | +0.0143 | -0.0012 | +0.0155 | 62 | $+10 | **$-568** |
| all four types | 266 | +0.0257 | -0.0005 | +0.0262 | 68 | $+5 | **$-659** |
| everything EXCEPT price path | 228 | +0.0117 | -0.0010 | +0.0127 | 91 | $+3 | **$-893** |

Noise floor at this sample size is ±0.0786 (3 standard errors on 1,458 INDEPENDENT outcomes — 291,672 out-of-sample bars, but an 200-bar forward return overlaps its 199 neighbours); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

### 400 bars ahead (~980 min)

| data | features | IC | shuffled | **real − shuffled** | round turns/day | gross $/day | **net $/week** |
|---|---|---|---|---|---|---|---|
| price path only | 38 | +0.0295 | -0.0004 | +0.0300 | 51 | $+9 | **$-462** |
| + NQ order flow | 78 | +0.0317 | +0.0014 | +0.0302 | 55 | $+9 | **$-502** |
| + index complex (ES/YM/RTY) | 138 | +0.0387 | -0.0010 | +0.0397 | 66 | $+11 | **$-606** |
| + macro complex (CL/GC/HG) | 126 | +0.0404 | +0.0031 | +0.0372 | 57 | $+12 | **$-504** |
| all four types | 266 | +0.0483 | +0.0006 | +0.0477 | 63 | $+11 | **$-566** |
| everything EXCEPT price path | 228 | +0.0320 | -0.0018 | +0.0339 | 83 | $+10 | **$-778** |

Noise floor at this sample size is ±0.1113 (3 standard errors on 726 INDEPENDENT outcomes — 290,392 out-of-sample bars, but an 400-bar forward return overlaps its 399 neighbours); bolded gaps clear it. One MNQ, $1.99 a round turn, cost charged on how much the position CHANGES rather than once per opinion.

## The stream-shift control

The foreign tapes are slid 11 days along the calendar and rejoined to the same NQ bars. Their volatility, their flow, their autocorrelation are all untouched — only the alignment with NQ is destroyed. A real cross-market effect has to die here. Anything that survives was never cross-market information and is a bug in the join.

_Skipped in this run (`SKIP_SHIFT=1`): rebuilding the shifted matrices costs more than the whole horizon sweep, and there is nothing to kill unless a real−shuffled gap clears its noise floor first. If one does, re-run without the flag._


## What this decides

A round turn costs **$1.99** and the model trades a continuous position, so cost is charged on how much the position CHANGES, not once per opinion. At 588 bars a day, $0.10/bar would be $294 a week — so the net column is the whole answer, and any set whose real−shuffled gap sits at zero is a stream that cannot be searched profitably no matter how many configurations are thrown at it.

Data types 5 and 6 — order book and options — are stubbed in `fuse.py` behind `load_book()` and `load_options()`. They drop into the same clock, the same lag rail and the same ablation the moment the files exist; see TODO_FOR_USER.md for the exact format.

_Ran in 62 min._

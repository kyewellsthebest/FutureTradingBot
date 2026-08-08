Resumed: 2,515,791,632 evaluated, 8 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- NQ K=6500 `NQH5.parquet`: 3,819 bars, 606 conditions, **296,725,880** distinct [93s, total 2,812,517,512 eval / 566,574,910 scored]
- NQ K=4000 `NQH6.parquet`: 5,354 bars, 624 conditions, **323,960,000** distinct [239s, total 3,136,477,512 eval / 632,691,192 scored]
- NQ K=4000 `NQM5.parquet`: 6,305 bars, 623 conditions, **322,404,992** distinct [430s, total 3,458,882,504 eval / 698,564,384 scored]
- ES K=6500 `ESH6.parquet`: 4,488 bars, 602 conditions, **290,888,808** distinct [534s, total 3,749,771,312 eval / 748,401,120 scored]
- GC K=1000 `GCM6.parquet`: 3,911 bars, 607 conditions, **298,197,248** distinct [614s, total 4,047,968,560 eval / 792,649,714 scored]
- CL K=650 `CLH5.parquet`: 4,100 bars, 612 conditions, **305,627,088** distinct [702s, total 4,353,595,648 eval / 841,196,632 scored]
- CL K=400 `CLH6.parquet`: 6,850 bars, 621 conditions, **319,309,920** distinct [933s, total 4,672,905,568 eval / 918,530,310 scored]
- RTY K=1000 `RTYH6.parquet`: 6,514 bars, 617 conditions, **313,179,328** distinct [1133s, total 4,986,084,896 eval / 991,455,436 scored]
- RTY K=1600 `RTYH6.parquet`: 4,071 bars, 605 conditions, **295,259,360** distinct [1208s, total 5,281,344,256 eval / 1,037,910,330 scored]
- YM K=1000 `YMH6.parquet`: 4,713 bars, 620 conditions, **317,769,840** distinct [1307s, total 5,599,114,096 eval / 1,089,917,504 scored]
- EURUSD K=150 `EURUSD_202512.parquet`: 3,757 bars, 610 conditions, **302,640,520** distinct [1372s, total 5,901,754,616 eval / 1,136,007,584 scored]
- GBPUSD K=100 `GBPUSD_202508.parquet`: 6,477 bars, 621 conditions, **319,309,920** distinct [1567s, total 6,221,064,536 eval / 1,212,843,172 scored]
- AUDUSD K=150 `AUDUSD_202508.parquet`: 6,214 bars, 619 conditions, **316,234,720** distinct [1744s, total 6,537,299,256 eval / 1,287,151,708 scored]

## 6,537,299,256 distinct configurations evaluated; **1,287,151,708 scored** (met the sample-size gate) in 0.48 h

Null: 6,537,299,256 evaluated, 1,287,151,708 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 41 | **34.1%** | **$-4.2796** | 28.3% | $-57.0299 |
| top 1e-05% | >= $+384.677 | 125 | **45.6%** | **$-1.6104** | 32.5% | $-49.3644 |
| top 0.0001% | >= $+338.000 | 1,250 | **22.0%** | **$-9.1214** | 38.2% | $-30.4387 |
| top 0.001% | >= $+232.691 | 12,721 | **44.9%** | **$+6.1792** | 49.5% | $-1.1137 |
| top 0.01% | >= $+165.002 | 126,694 | **50.8%** | **$+8.6216** | 52.7% | $+8.7470 |
| top 0.1% | >= $+104.214 | 1,281,658 | **47.8%** | **$-0.6479** | 56.2% | $+12.3903 |
| top 1% | >= $+47.813 | 12,849,739 | **43.4%** | **$-9.0659** | 53.4% | $+6.7344 |
| top 10% | >= $+8.574 | 128,392,613 | **48.6%** | **$-2.5182** | 49.0% | $+0.9883 |
| top 100% | >= $-402.429 | 1,287,151,708 | **50.0%** | **$+0.0000** | 50.0% | $-0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market

| market | scored configs | avg train $ | avg holdout $ | NULL holdout $ |
|---|---|---|---|---|
| NQ | 239,205,882 | $+0.0000 | $+0.0000 | $+0.0000 |
| CL | 204,301,506 | $+0.0000 | $+0.0000 | $+0.0000 |
| RTY | 181,798,504 | $+0.0000 | $+0.0000 | $+0.0000 |
| EURUSD | 115,897,078 | $+0.0000 | $+0.0000 | $+0.0000 |
| GC | 114,055,202 | $+0.0000 | $+0.0000 | $+0.0000 |
| YM | 105,856,600 | $+0.0000 | $+0.0000 | $+0.0000 |
| ES | 105,141,914 | $+0.0000 | $+0.0000 | $+0.0000 |
| GBPUSD | 76,835,588 | $+0.0000 | $+0.0000 | $+0.0000 |
| AUDUSD | 74,308,536 | $+0.0000 | $+0.0000 | $+0.0000 |
| HG | 69,750,898 | $+0.0000 | $+0.0000 | $+0.0000 |

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 1,287,151,708 | **265,567,884** | 20.632% |
| shifted null | 1,287,151,708 | 267,207,363 | 20.760% |

Lift over chance: **0.99x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+285.067** | $+289.359 | $+285.067 | NQ K=4000 h=21 NQH6.parquet | `L exp89>0.67 & vpp89<-0.67 & run89<-0.0` |
| **$+269.335** | $+269.335 | $+345.051 | NQ K=4000 h=21 NQH6.parquet | `L mom89<-1.35 & vpp89<-0.0 & vwapd<-1.35` |
| **$+268.027** | $+291.668 | $+268.027 | NQ K=4000 h=21 NQH6.parquet | `L exp89>0.67 & vpp89<-0.67 & vdir89<-0.0` |
| **$+266.721** | $+266.721 | $+329.945 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & mom89<-0.67 & vwapd<-1.35` |
| **$+264.703** | $+264.703 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & upl34<-0.0 & vwapd<-1.35` |
| **$+262.781** | $+275.012 | $+262.781 | GC K=1000 h=21 GCM6.parquet | `L dnh34<-0.0 & vpp34<-0.0 & vwapd<-0.67` |
| **$+262.469** | $+262.469 | $+328.544 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & eff89<-0.67 & vwapd<-1.35` |
| **$+262.392** | $+262.392 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & bdn34>0.0 & vwapd<-1.35` |
| **$+262.019** | $+263.348 | $+262.019 | GC K=1000 h=21 GCM6.parquet | `L bdn34>0.0 & vpp34<-0.0 & vwapd<-0.67` |
| **$+261.227** | $+261.227 | $+313.727 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & rev89>0.67 & vwapd<-1.35` |
| **$+261.035** | $+266.896 | $+261.035 | GC K=1000 h=21 GCM6.parquet | `L rev89>0.0 & vpp89<-0.0 & vwapd<-0.67` |
| **$+260.916** | $+260.916 | $+262.019 | GC K=1000 h=21 GCM6.parquet | `L upl34<-0.0 & vpp34<-0.0 & vwapd<-0.67` |
| **$+260.027** | $+260.027 | $+299.792 | NQ K=4000 h=21 NQH6.parquet | `L mom34<-1.35 & acc89<-0.0 & vwapd<-1.35` |
| **$+259.739** | $+259.739 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & brk34<-0.0 & vwapd<-1.35` |
| **$+259.160** | $+259.160 | $+315.818 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & vmom89<-0.67 & vwapd<-1.35` |
| **$+258.344** | $+258.344 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & upl89<-0.67 & vwapd<-1.35` |
| **$+258.344** | $+258.344 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & bdn89>0.67 & vwapd<-1.35` |
| **$+257.769** | $+257.769 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L pos34<-0.0 & chop34<-0.0 & vwapd<-1.35` |
| **$+257.594** | $+257.594 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L mom34<-0.0 & chop34<-0.0 & vwapd<-1.35` |
| **$+257.475** | $+257.475 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L rev34>0.0 & chop34<-0.0 & vwapd<-1.35` |
| **$+256.604** | $+256.604 | $+261.464 | NQ K=4000 h=21 NQH6.parquet | `L mom34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+256.421** | $+256.421 | $+321.963 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & vdir89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L vmom34<-0.0 & chop34<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L eff34<-0.0 & chop34<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & vwapd<-0.67 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & vwapd<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & vmom89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & upl89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & rev89>0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & pos89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & mom89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & fail89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & fail34<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & eff89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & dnh89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & brk89<-0.0 & vwapd<-1.35` |
| **$+256.238** | $+256.238 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & bdn89>0.0 & vwapd<-1.35` |
| **$+255.878** | $+255.878 | $+345.928 | NQ K=4000 h=21 NQH6.parquet | `L acc89<-0.0 & barups>0.67 & vwapd<-1.35` |
| **$+255.681** | $+255.681 | $+265.022 | NQ K=4000 h=21 NQH6.parquet | `L rev34>0.0 & mom89<-1.35 & barups>0.67` |
| **$+255.578** | $+255.578 | $+321.963 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & run89<-0.0 & vwapd<-1.35` |
| **$+255.565** | $+272.540 | $+255.565 | GC K=1000 h=21 GCM6.parquet | `L rev34>0.0 & vpp34<-0.0 & vwapd<-0.67` |
| **$+254.829** | $+254.829 | $+259.043 | NQ K=4000 h=21 NQH6.parquet | `L dnh34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+254.542** | $+254.542 | $+261.464 | NQ K=4000 h=21 NQH6.parquet | `L vmom34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+254.542** | $+254.542 | $+261.464 | NQ K=4000 h=21 NQH6.parquet | `L eff34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.879** | $+253.879 | $+260.777 | NQ K=4000 h=21 NQH6.parquet | `L brk34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.527** | $+253.527 | $+343.597 | NQ K=4000 h=21 NQH6.parquet | `L aeff89>0.0 & barups>0.67 & vwapd<-1.35` |
| **$+253.352** | $+253.352 | $+304.100 | NQ K=4000 h=21 NQH6.parquet | `L mom34<-1.35 & run89<-0.67 & vwapd<-1.35` |
| **$+253.347** | $+253.347 | $+271.755 | NQ K=4000 h=21 NQH6.parquet | `L upl34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.347** | $+253.347 | $+263.820 | NQ K=4000 h=21 NQH6.parquet | `L bdn34>0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.091** | $+259.622 | $+253.091 | NQ K=4000 h=21 NQH6.parquet | `L vpp13<-0.67 & mom34<-0.67 & vel89<-0.0` |
| **$+252.660** | $+252.660 | $+259.320 | NQ K=4000 h=21 NQH6.parquet | `L pos34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+251.991** | $+251.991 | $+316.568 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & pos89<-0.67 & vwapd<-1.35` |
| **$+251.742** | $+261.667 | $+251.742 | GC K=1000 h=21 GCM6.parquet | `L brk34<-0.0 & vpp34<-0.0 & vwapd<-0.67` |
| **$+251.215** | $+251.215 | $+318.223 | NQ K=4000 h=21 NQH6.parquet | `L fail13<-0.0 & chop34<-0.0 & vwapd<-1.35` |
| **$+251.152** | $+258.023 | $+251.152 | GC K=1000 h=21 GCM6.parquet | `L fail13<-0.0 & vpp89<-0.0 & vwapd<-0.67` |
| **$+251.105** | $+294.952 | $+251.105 | NQ K=4000 h=21 NQH6.parquet | `L vpp34<-0.67 & exp89>0.67 & run89<-0.67` |
| **$+251.105** | $+290.956 | $+251.105 | NQ K=4000 h=21 NQH6.parquet | `L vpp34<-0.67 & exp89>0.67 & vdir89<-0.67` |
| **$+251.008** | $+251.008 | $+338.656 | NQ K=4000 h=21 NQH6.parquet | `L aeff34>0.0 & mom89<-1.35 & vwapd<-1.35` |
| **$+250.668** | $+250.668 | $+311.764 | NQ K=4000 h=21 NQH6.parquet | `L mom34<-1.35 & vdir89<-0.67 & vwapd<-1.35` |

### The best training scores, and what each did out of sample

| train $/trade | HOLDOUT $/trade | rule |
|---|---|---|
| $+444.856 | $-106.433 | `L aeff34<-0.67 & aeff89<-0.0 & cmp<-0.67` |
| $+434.305 | $+21.188 | `L eff34<-1.35 & vpp34<-0.0 & vdir34<-0.67` |
| $+432.587 | $-22.668 | `L aeff34>0.67 & vdir34<-0.67 & barpath>0.0` |
| $+427.640 | $-1.276 | `L eff34<-1.35 & vdir34<-0.67 & barups>0.0` |
| $+424.013 | $+21.188 | `L eff34<-1.35 & vpp34<-0.0 & run34<-0.67` |
| $+421.991 | $-6.371 | `L aeff34>0.67 & run34<-0.67 & barpath>0.0` |
| $+421.476 | $-9.404 | `L faild13<-0.0 & aeff34>1.35 & vdir34<-0.67` |
| $+421.476 | $-9.404 | `L aeff34>1.35 & faild34<-0.0 & vdir34<-0.67` |
| $+418.363 | $-17.240 | `L faild5<-0.0 & aeff34>1.35 & vdir34<-0.67` |
| $+418.026 | $+18.988 | `L vmom13<-0.0 & eff34<-1.35 & vpp34<-0.0` |
| $+418.026 | $+18.988 | `L mom13<-0.0 & eff34<-1.35 & vpp34<-0.0` |
| $+418.026 | $+18.988 | `L eff13<-0.0 & eff34<-1.35 & vpp34<-0.0` |
| $+417.308 | $-9.404 | `L aeff34>1.35 & vdir34<-0.67 & faild89<-0.0` |
| $+416.061 | $-18.968 | `L aeff13>0.0 & aeff34>1.35 & vdir34<-0.67` |
| $+415.072 | $+5.006 | `L aeff34>0.67 & run34<-0.67 & barups>0.67` |
| $+414.961 | $-12.404 | `L faild5<-0.0 & aeff34>1.35 & run34<-0.67` |
| $+413.555 | $-6.559 | `L faild13<-0.0 & aeff34>1.35 & run34<-0.67` |
| $+413.555 | $-6.559 | `L aeff34>1.35 & faild34<-0.0 & run34<-0.67` |
| $+411.741 | $-22.948 | `L eff13<-0.67 & aeff34>1.35 & vdir34<-0.67` |
| $+411.692 | $-14.389 | `L aeff13>0.0 & aeff34>1.35 & run34<-0.67` |
| $+409.758 | $-35.621 | `L vdir13<-0.67 & aeff34>1.35 & run34<-0.67` |
| $+409.702 | $-6.559 | `L aeff34>1.35 & run34<-0.67 & faild89<-0.0` |
| $+407.624 | $+0.596 | `L eff34<-1.35 & run34<-0.67 & barups>0.0` |
| $+407.543 | $-20.646 | `L eff13<-0.67 & aeff34>1.35 & run34<-0.67` |
| $+407.077 | $-29.919 | `L vmom13<-0.0 & aeff34>1.35 & vdir34<-0.67` |
| $+407.077 | $-29.919 | `L mom13<-0.0 & aeff34>1.35 & vdir34<-0.67` |
| $+407.077 | $-29.919 | `L eff13<-0.0 & aeff34>1.35 & vdir34<-0.67` |
| $+405.998 | $+31.106 | `L vpp5<-0.0 & chop13<-0.0 & eff34<-1.35` |
| $+405.660 | $-46.533 | `L run13<-0.67 & aeff34>1.35 & vdir34<-0.67` |
| $+405.059 | $+20.577 | `L eff34<-1.35 & upl34<-0.67 & vpp34<-0.0` |
| $+404.554 | $+7.443 | `L aeff34>1.35 & vel34>0.0 & vdir34<-0.67` |
| $+404.554 | $+10.793 | `L aeff34>1.35 & vel34>0.0 & run34<-0.67` |
| $+403.631 | $-27.882 | `L vmom13<-0.0 & aeff34>1.35 & run34<-0.67` |
| $+403.631 | $-27.882 | `L mom13<-0.0 & aeff34>1.35 & run34<-0.67` |
| $+403.631 | $-27.882 | `L eff13<-0.0 & aeff34>1.35 & run34<-0.67` |
| $+403.091 | $+177.485 | `L vpp5<-0.0 & vpp13<-0.0 & chop34>1.35` |
| $+402.992 | $-121.878 | `S vdir34<-0.67 & vpp89>0.0 & pthz89>0.67` |
| $+402.903 | $+190.663 | `L fail13<-0.0 & vpp13<-0.0 & chop34>1.35` |
| $+402.694 | $-32.614 | `L vmom13<-0.67 & aeff34>1.35 & vdir34<-0.67` |
| $+402.101 | $+20.577 | `L eff34<-1.35 & bdn34>0.67 & vpp34<-0.0` |

Conditions per cell: 602-624 (median 617).

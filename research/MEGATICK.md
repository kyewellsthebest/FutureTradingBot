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
- NZDUSD K=100 `NZDUSD_202508.parquet`: 6,984 bars, 623 conditions, **322,404,992** distinct [1951s, total 6,859,704,248 eval / 1,364,801,234 scored]
- USDCAD K=100 `USDCAD_202508.parquet`: 6,494 bars, 621 conditions, **319,309,920** distinct [2149s, total 7,179,014,168 eval / 1,444,776,280 scored]
- USDCHF K=100 `USDCHF_202508.parquet`: 3,951 bars, 604 conditions, **293,797,680** distinct [2218s, total 7,472,811,848 eval / 1,489,307,900 scored]
- USDJPY K=100 `USDJPY_202508.parquet`: 6,201 bars, 618 conditions, **314,704,552** distinct [2394s, total 7,787,516,400 eval / 1,557,366,584 scored]
- USDJPY K=150 `USDJPY_202508.parquet`: 4,134 bars, 615 conditions, **310,143,680** distinct [2469s, total 8,097,660,080 eval / 1,600,439,324 scored]
- XAUUSD K=650 `XAUUSD_202508.parquet`: 4,446 bars, 612 conditions, **305,627,088** distinct [2556s, total 8,403,287,168 eval / 1,652,772,384 scored]
- NQ K=6500 `NQM5.parquet`: 3,880 bars, 597 conditions, **283,700,768** distinct [2627s, total 8,686,987,936 eval / 1,692,698,662 scored]
- NQ K=4000 `NQM6.parquet`: 6,185 bars, 617 conditions, **313,179,328** distinct [2801s, total 9,000,167,264 eval / 1,765,998,458 scored]
- NQ K=6500 `NQM6.parquet`: 3,806 bars, 603 conditions, **292,340,832** distinct [2868s, total 9,292,508,096 eval / 1,810,924,506 scored]
- NQ K=4000 `NQU4.parquet`: 6,297 bars, 623 conditions, **322,404,992** distinct [3051s, total 9,614,913,088 eval / 1,885,427,684 scored]
- ES K=6500 `ESM6.parquet`: 4,808 bars, 606 conditions, **296,725,880** distinct [3156s, total 9,911,638,968 eval / 1,941,269,096 scored]
- ES K=4000 `ESU5.parquet`: 5,341 bars, 607 conditions, **298,197,248** distinct [3280s, total 10,209,836,216 eval / 2,004,817,684 scored]
- GC K=1000 `GCZ4.parquet`: 4,556 bars, 620 conditions, **317,769,840** distinct [3367s, total 10,527,606,056 eval / 2,061,485,916 scored]
- CL K=650 `CLH6.parquet`: 4,215 bars, 606 conditions, **296,725,880** distinct [3443s, total 10,824,331,936 eval / 2,110,631,310 scored]
- CL K=400 `CLM5.parquet`: 6,425 bars, 618 conditions, **314,704,552** distinct [3626s, total 11,139,036,488 eval / 2,181,718,796 scored]
- CL K=650 `CLM5.parquet`: 3,953 bars, 605 conditions, **295,259,360** distinct [3690s, total 11,434,295,848 eval / 2,224,554,228 scored]

## 11,434,295,848 distinct configurations evaluated; **2,224,554,228 scored** (met the sample-size gate) in 1.02 h

Null: 11,434,295,848 evaluated, 2,224,554,228 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 108 | **26.9%** | **$-31.4134** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+386.998 | 210 | **38.6%** | **$-29.6761** | - | - |
| top 0.0001% | >= $+339.018 | 2,183 | **18.6%** | **$-51.2195** | 58.4% | $+11.9952 |
| top 0.001% | >= $+244.918 | 21,917 | **27.4%** | **$-54.7564** | 57.7% | $+20.5558 |
| top 0.01% | >= $+168.525 | 221,098 | **36.6%** | **$-32.9404** | 58.7% | $+33.7425 |
| top 0.1% | >= $+104.214 | 2,198,123 | **40.5%** | **$-21.3221** | 57.2% | $+29.9955 |
| top 1% | >= $+46.087 | 22,175,805 | **42.3%** | **$-13.5560** | 50.3% | $+10.3461 |
| top 10% | >= $+9.166 | 221,802,566 | **53.5%** | **$-1.6002** | 51.2% | $+1.8163 |
| top 100% | >= $-402.429 | 2,224,554,228 | **50.0%** | **$-0.0000** | 50.0% | $-0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market

| market | scored configs | avg train $ | avg holdout $ | NULL holdout $ |
|---|---|---|---|---|
| NQ | 471,861,182 | $+0.0000 | $+0.0000 | $+0.0000 |
| CL | 367,369,818 | $+0.0000 | $+0.0000 | $+0.0000 |
| ES | 224,531,914 | $+0.0000 | $+0.0000 | $+0.0000 |
| RTY | 181,798,504 | $+0.0000 | $+0.0000 | $+0.0000 |
| GC | 170,723,434 | $+0.0000 | $+0.0000 | $+0.0000 |
| EURUSD | 115,897,078 | $+0.0000 | $+0.0000 | $+0.0000 |
| USDJPY | 111,131,424 | $+0.0000 | $+0.0000 | $+0.0000 |
| YM | 105,856,600 | $+0.0000 | $+0.0000 | $+0.0000 |
| USDCAD | 79,975,046 | $+0.0000 | $+0.0000 | $+0.0000 |
| NZDUSD | 77,649,526 | $+0.0000 | $+0.0000 | $+0.0000 |
| GBPUSD | 76,835,588 | $+0.0000 | $+0.0000 | $+0.0000 |
| AUDUSD | 74,308,536 | $+0.0000 | $+0.0000 | $+0.0000 |
| HG | 69,750,898 | $+0.0000 | $+0.0000 | $+0.0000 |
| XAUUSD | 52,333,060 | $+0.0000 | $+0.0000 | $+0.0000 |
| USDCHF | 44,531,620 | $+0.0000 | $+0.0000 | $+0.0000 |

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 2,224,554,228 | **615,604,729** | 27.673% |
| shifted null | 2,224,554,228 | 595,181,332 | 26.755% |

Lift over chance: **1.03x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+288.262** | $+292.898 | $+288.262 | NQ K=6500 h=21 NQM5.parquet | `S eff89<-0.0 & cmp<-0.67 & vratio>0.0` |
| **$+285.067** | $+289.359 | $+285.067 | NQ K=4000 h=21 NQH6.parquet | `L exp89>0.67 & vpp89<-0.67 & run89<-0.0` |
| **$+284.035** | $+284.035 | $+353.322 | NQ K=6500 h=21 NQM6.parquet | `S vmom89>0.0 & acc89>0.0 & exp89<-0.67` |
| **$+282.056** | $+292.898 | $+282.056 | NQ K=6500 h=21 NQM5.parquet | `S mom89<-0.0 & cmp<-0.67 & vratio>0.0` |
| **$+274.308** | $+295.271 | $+274.308 | NQ K=6500 h=21 NQM5.parquet | `S vmom89<-0.0 & cmp<-0.67 & vratio>0.0` |
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
| **$+255.582** | $+293.880 | $+255.582 | NQ K=6500 h=21 NQM5.parquet | `L chop34<-0.67 & upl89<-0.0 & vratio<-0.0` |
| **$+255.582** | $+287.613 | $+255.582 | NQ K=6500 h=21 NQM5.parquet | `L chop34<-0.67 & bdn89>0.0 & vratio<-0.0` |
| **$+255.578** | $+255.578 | $+321.963 | NQ K=4000 h=21 NQH6.parquet | `L chop34<-0.0 & run89<-0.0 & vwapd<-1.35` |
| **$+255.565** | $+272.540 | $+255.565 | GC K=1000 h=21 GCM6.parquet | `L rev34>0.0 & vpp34<-0.0 & vwapd<-0.67` |
| **$+254.829** | $+254.829 | $+259.043 | NQ K=4000 h=21 NQH6.parquet | `L dnh34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+254.542** | $+254.542 | $+261.464 | NQ K=4000 h=21 NQH6.parquet | `L vmom34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+254.542** | $+254.542 | $+261.464 | NQ K=4000 h=21 NQH6.parquet | `L eff34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.946** | $+258.961 | $+253.946 | NQ K=6500 h=21 NQM5.parquet | `S vel34<-0.0 & exp89>0.0 & cmp<-0.67` |
| **$+253.879** | $+253.879 | $+260.777 | NQ K=4000 h=21 NQH6.parquet | `L brk34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.527** | $+253.527 | $+343.597 | NQ K=4000 h=21 NQH6.parquet | `L aeff89>0.0 & barups>0.67 & vwapd<-1.35` |
| **$+253.352** | $+253.352 | $+304.100 | NQ K=4000 h=21 NQH6.parquet | `L mom34<-1.35 & run89<-0.67 & vwapd<-1.35` |
| **$+253.347** | $+253.347 | $+271.755 | NQ K=4000 h=21 NQH6.parquet | `L upl34<-0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.347** | $+253.347 | $+263.820 | NQ K=4000 h=21 NQH6.parquet | `L bdn34>0.0 & mom89<-1.35 & barups>0.67` |
| **$+253.091** | $+259.622 | $+253.091 | NQ K=4000 h=21 NQH6.parquet | `L vpp13<-0.67 & mom34<-0.67 & vel89<-0.0` |
| **$+252.761** | $+252.761 | $+282.930 | NQ K=4000 h=21 NQM6.parquet | `L vmom34<-0.67 & vpp89<-0.0 & dratio>0.67` |
| **$+252.721** | $+252.721 | $+278.458 | NQ K=6500 h=21 NQM5.parquet | `L chop13<-0.0 & chop34<-0.67 & pos89<-0.67` |

### The best training scores, and what each did out of sample

| train $/trade | HOLDOUT $/trade | rule |
|---|---|---|
| $+536.519 | $-31.873 | `L exp34<-0.0 & run34>0.0 & chop89>0.67` |
| $+529.876 | $-119.428 | `L aeff34<-0.0 & chop89>0.67 & exp89<-0.67` |
| $+523.777 | $-31.873 | `L exp34<-0.0 & vdir34>0.0 & chop89>0.67` |
| $+512.309 | $+34.396 | `L exp34<-0.0 & pos89>0.0 & vwapd<-0.0` |
| $+507.721 | $-65.585 | `L vdir34>0.0 & aeff89<-0.0 & chop89>0.67` |
| $+483.577 | $-49.747 | `L aeff13<-0.0 & aeff89<-0.67 & chop89>0.67` |
| $+482.356 | $-33.615 | `L aeff13<-0.0 & run34>0.0 & chop89>0.67` |
| $+481.623 | $+48.991 | `L pos89>0.0 & cmp<-0.0 & vwapd<-0.0` |
| $+481.130 | $+111.954 | `L dnh89>0.0 & cmp<-0.0 & vwapd<-0.0` |
| $+475.214 | $+71.453 | `L vpp13<-0.0 & vdir34>0.0 & chop89>0.67` |
| $+475.214 | $+71.453 | `L vpp13<-0.0 & run34>0.0 & chop89>0.67` |
| $+472.243 | $-33.615 | `L aeff13<-0.0 & vdir34>0.0 & chop89>0.67` |
| $+468.854 | $+90.181 | `L exp34<-0.0 & dnh89>0.0 & vwapd<-0.0` |
| $+464.181 | $-91.149 | `L run34>0.0 & chop89>0.67 & volst<-0.0` |
| $+463.802 | $-105.647 | `L vel13<-0.0 & run34>0.0 & chop89>0.67` |
| $+461.234 | $-48.063 | `L chop34>0.0 & aeff89<-0.67 & chop89>0.67` |
| $+457.953 | $-105.647 | `L vel13<-0.0 & vdir34>0.0 & chop89>0.67` |
| $+457.382 | $-84.949 | `L run34>0.0 & chop89>0.67 & vel89>0.0` |
| $+455.600 | $+11.937 | `L exp34<-0.0 & aeff89<-0.67 & vratio<-0.0` |
| $+454.889 | $+61.833 | `L vpp5<-0.0 & vdir34>0.0 & chop89>0.67` |
| $+454.889 | $+61.833 | `L vpp5<-0.0 & run34>0.0 & chop89>0.67` |
| $+454.391 | $-91.149 | `L vdir34>0.0 & chop89>0.67 & volst<-0.0` |
| $+451.958 | $-177.927 | `L run34>0.0 & chop89>0.67 & exp89<-0.0` |
| $+451.639 | $-84.949 | `L vdir34>0.0 & chop89>0.67 & vel89>0.0` |
| $+446.498 | $+90.181 | `L exp34<-0.0 & brk89>0.0 & vwapd<-0.0` |
| $+444.856 | $-106.433 | `L aeff34<-0.67 & aeff89<-0.0 & cmp<-0.67` |
| $+441.344 | $-32.380 | `L chop34>0.0 & vdir34>0.0 & chop89>0.67` |
| $+441.344 | $-32.380 | `L chop34>0.0 & run34>0.0 & chop89>0.67` |
| $+441.049 | $-177.927 | `L vdir34>0.0 & chop89>0.67 & exp89<-0.0` |
| $+439.642 | $-64.708 | `L run34>0.0 & chop89>0.67 & cmp<-0.0` |
| $+437.918 | $-114.158 | `L run34>0.0 & chop89>0.67 & dratio<-0.0` |
| $+436.630 | $-57.015 | `L vdir34>0.0 & chop89>0.67 & pthz89<-0.0` |
| $+436.630 | $-57.015 | `L run34>0.0 & chop89>0.67 & pthz89<-0.0` |
| $+436.203 | $-35.235 | `L run34>0.0 & chop89>0.67 & barvel>0.0` |
| $+434.305 | $+21.188 | `L eff34<-1.35 & vpp34<-0.0 & vdir34<-0.67` |
| $+434.223 | $-68.414 | `L rev89<-0.0 & cmp<-0.0 & vwapd<-0.0` |
| $+433.149 | $-142.126 | `L aeff89<-0.0 & chop89>0.67 & exp89<-0.67` |
| $+432.587 | $-22.668 | `L aeff34>0.67 & vdir34<-0.67 & barpath>0.0` |
| $+432.558 | $-114.158 | `L vdir34>0.0 & chop89>0.67 & dratio<-0.0` |
| $+430.940 | $-35.235 | `L vdir34>0.0 & chop89>0.67 & barvel>0.0` |

Conditions per cell: 597-624 (median 615).

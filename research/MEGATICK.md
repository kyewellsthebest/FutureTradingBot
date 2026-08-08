Resumed: 11,434,295,848 evaluated, 37 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- RTY K=1600 `RTYM5.parquet`: 4,611 bars, 607 conditions, **298,197,248** distinct [97s, total 11,732,493,096 eval / 2,273,533,348 scored]
- RTY K=1000 `RTYM6.parquet`: 6,707 bars, 613 conditions, **307,127,712** distinct [317s, total 12,039,620,808 eval / 2,350,430,884 scored]
- RTY K=1600 `RTYM6.parquet`: 4,192 bars, 601 conditions, **289,441,600** distinct [397s, total 12,329,062,408 eval / 2,399,095,684 scored]
- YM K=1000 `YMM5.parquet`: 4,631 bars, 612 conditions, **305,627,088** distinct [495s, total 12,634,689,496 eval / 2,449,770,978 scored]
- YM K=650 `YMM6.parquet`: 6,820 bars, 621 conditions, **319,309,920** distinct [715s, total 12,953,999,416 eval / 2,532,005,672 scored]
- HG K=400 `HGZ4.parquet`: 3,614 bars, 601 conditions, **289,441,600** distinct [779s, total 13,243,441,016 eval / 2,574,139,664 scored]
- EURUSD K=150 `EURUSD_202602.parquet`: 4,936 bars, 618 conditions, **314,704,552** distinct [892s, total 13,558,145,568 eval / 2,637,138,404 scored]
- EURUSD K=150 `EURUSD_202603.parquet`: 6,041 bars, 623 conditions, **322,404,992** distinct [1069s, total 13,880,550,560 eval / 2,707,877,972 scored]
- GBPUSD K=150 `GBPUSD_202508.parquet`: 4,318 bars, 610 conditions, **302,640,520** distinct [1159s, total 14,183,191,080 eval / 2,759,595,744 scored]
- AUDUSD K=250 `AUDUSD_202508.parquet`: 3,728 bars, 601 conditions, **289,441,600** distinct [1229s, total 14,472,632,680 eval / 2,804,414,480 scored]
- NZDUSD K=150 `NZDUSD_202508.parquet`: 4,656 bars, 612 conditions, **305,627,088** distinct [1331s, total 14,778,259,768 eval / 2,858,188,478 scored]
- USDCAD K=150 `USDCAD_202508.parquet`: 4,329 bars, 611 conditions, **304,131,360** distinct [1415s, total 15,082,391,128 eval / 2,911,550,864 scored]
- USDCHF K=100 `USDCHF_202509.parquet`: 5,260 bars, 616 conditions, **311,659,040** distinct [1531s, total 15,394,050,168 eval / 2,972,474,794 scored]
- USDJPY K=150 `USDJPY_202509.parquet`: 5,623 bars, 620 conditions, **317,769,840** distinct [1677s, total 15,711,820,008 eval / 3,037,272,428 scored]
- USDJPY K=250 `USDJPY_202510.parquet`: 5,496 bars, 615 conditions, **310,143,680** distinct [1800s, total 16,021,963,688 eval / 3,097,260,512 scored]

## 16,021,963,688 distinct configurations evaluated; **3,097,260,512 scored** (met the sample-size gate) in 0.50 h

Null: 16,021,963,688 evaluated, 3,097,260,512 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 108 | **26.9%** | **$-31.4134** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+381.221 | 301 | **33.2%** | **$-31.6584** | - | - |
| top 0.0001% | >= $+328.969 | 3,040 | **17.3%** | **$-52.2411** | 56.9% | $+9.9662 |
| top 0.001% | >= $+233.393 | 30,957 | **27.8%** | **$-55.3678** | 58.6% | $+23.5492 |
| top 0.01% | >= $+158.653 | 305,264 | **37.7%** | **$-29.8200** | 58.3% | $+33.2835 |
| top 0.1% | >= $+95.448 | 3,071,116 | **40.4%** | **$-21.1282** | 56.8% | $+28.2877 |
| top 1% | >= $+39.407 | 30,961,035 | **42.9%** | **$-11.7361** | 49.3% | $+7.9099 |
| top 10% | >= $+7.440 | 309,671,046 | **53.8%** | **$-0.9535** | 50.8% | $+1.1326 |
| top 100% | >= $-402.429 | 3,097,260,512 | **50.0%** | **$+0.0000** | 50.0% | $-0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market — is the pooled number hiding one live market?

Mean dollars per market is identically zero by construction: every configuration is scored alongside its short mirror, so the two cancel. The informative per-market number is the survivor rate against that market's OWN shifted null, because a single market with real structure would show a lift here even when the pooled figure sits at 1.0.

| market | scored (this run) | made money both halves | rate | NULL rate | lift |
|---|---|---|---|---|---|
| RTY | 174,541,456 | 55,060,007 | 31.546% | 27.801% | **1.135x** |
| EURUSD | 133,738,308 | 54,496,870 | 40.749% | 38.951% | **1.046x** |
| YM | 132,909,988 | 38,718,794 | 29.132% | 26.503% | **1.099x** |
| USDJPY | 124,785,718 | 48,176,312 | 38.607% | 33.819% | **1.142x** |
| USDCHF | 60,923,930 | 29,719,404 | 48.781% | 49.704% | **0.981x** |
| NZDUSD | 53,773,998 | 26,082,110 | 48.503% | 48.362% | **1.003x** |
| USDCAD | 53,362,386 | 26,383,012 | 49.441% | 49.627% | **0.996x** |
| GBPUSD | 51,717,772 | 22,807,160 | 44.099% | 46.425% | **0.950x** |
| AUDUSD | 44,818,736 | 21,331,984 | 47.596% | 44.028% | **1.081x** |
| HG | 42,133,992 | 13,478,614 | 31.990% | 36.112% | **0.886x** |

Counts here begin from the run that added this table, so they cover the later cells rather than the whole campaign; the lift ratio is unaffected because both columns cover the same cells.

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 3,097,260,512 | **336,254,267** | 10.857% |
| shifted null | 3,097,260,512 | 319,769,323 | 10.324% |

Lift over chance: **1.05x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+108.729** | $+108.729 | $+141.741 | YM K=1000 h=21 YMM5.parquet | `L chop34<-0.0 & pos89<-0.67 & exp89<-0.0` |
| **$+108.677** | $+108.677 | $+112.605 | YM K=1000 h=21 YMM5.parquet | `L chop34<-0.67 & upl34<-0.0 & exp89<-0.0` |
| **$+108.677** | $+108.677 | $+112.605 | YM K=1000 h=21 YMM5.parquet | `L chop34<-0.67 & bdn34>0.0 & exp89<-0.0` |
| **$+108.658** | $+108.658 | $+109.657 | RTY K=1000 h=21 RTYM6.parquet | `L fail34<-0.0 & vmom89<-1.35 & barups>0.67` |
| **$+107.937** | $+107.937 | $+111.615 | RTY K=1000 h=21 RTYM6.parquet | `L fail13<-0.0 & vmom89<-1.35 & barups>0.67` |
| **$+107.933** | $+107.933 | $+110.357 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & upsz89>0.0 & barups>0.67` |
| **$+107.933** | $+107.933 | $+109.314 | RTY K=1000 h=21 RTYM6.parquet | `L mom89<-0.67 & vmom89<-1.35 & barups>0.67` |
| **$+107.601** | $+107.907 | $+107.601 | YM K=1000 h=21 YMM5.parquet | `L aeff89<-0.67 & chop89<-0.0 & exp89<-0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & pos89<-0.0 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & fail89<-0.0 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & eff89<-0.67 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & eff89<-0.0 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & dnh89<-0.0 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & brk89<-0.0 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & barups>0.0 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-0.67 & vmom89<-1.35 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-0.0 & vmom89<-1.35 & barups>0.67` |
| **$+107.041** | $+107.933 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L mom89<-0.0 & vmom89<-1.35 & barups>0.67` |
| **$+107.041** | $+107.849 | $+107.041 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & run89<-0.0 & barups>0.67` |
| **$+104.353** | $+109.220 | $+104.353 | RTY K=1000 h=21 RTYM6.parquet | `L upsz34>0.0 & vmom89<-1.35 & barups>0.67` |
| **$+104.251** | $+110.445 | $+104.251 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & brk89<-0.67 & barups>0.67` |
| **$+101.992** | $+105.494 | $+101.992 | YM K=1000 h=21 YMM5.parquet | `L chop34<-0.0 & bdn34>0.67 & exp89<-0.0` |
| **$+101.441** | $+101.441 | $+105.063 | RTY K=1000 h=21 RTYM6.parquet | `L aeff89>0.0 & brk89<-0.67 & barups>0.67` |
| **$+98.591** | $+100.310 | $+98.591 | RTY K=1600 h=21 RTYM6.parquet | `L vmom89<-0.67 & barpath>0.67 & dratio>0.0` |
| **$+97.532** | $+97.532 | $+124.536 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & upl89<-0.0 & barpath>0.67` |
| **$+97.532** | $+97.532 | $+122.164 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & bdn89>0.0 & barpath>0.67` |
| **$+97.419** | $+97.419 | $+100.514 | RTY K=1600 h=21 RTYM6.parquet | `L vmom89<-0.67 & vel89<-0.0 & barpath>0.67` |
| **$+97.199** | $+97.199 | $+116.685 | YM K=1000 h=21 YMM5.parquet | `L rev34>0.0 & chop34<-0.67 & exp89<-0.0` |
| **$+97.157** | $+99.148 | $+97.157 | YM K=1000 h=21 YMM5.parquet | `L exp34<-0.0 & acc89>0.67 & aeff89<-0.0` |
| **$+97.148** | $+97.148 | $+104.084 | RTY K=1600 h=21 RTYM6.parquet | `L fail13<-0.0 & eff89<-0.67 & barpath>0.67` |
| **$+97.117** | $+97.117 | $+100.134 | RTY K=1600 h=21 RTYM6.parquet | `L mom89<-0.67 & eff89<-0.67 & barpath>0.67` |
| **$+96.895** | $+96.895 | $+103.657 | RTY K=1600 h=21 RTYM6.parquet | `L pthz34>0.0 & eff89<-0.67 & barpath>0.67` |
| **$+96.814** | $+96.814 | $+97.636 | RTY K=1600 h=21 RTYM6.parquet | `L vmom89<-0.67 & barvel<-0.0 & barpath>0.67` |
| **$+96.602** | $+98.219 | $+96.602 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-0.67 & aeff89>0.0 & barups>0.67` |
| **$+96.602** | $+98.219 | $+96.602 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-0.0 & aeff89>0.0 & barups>0.67` |
| **$+96.602** | $+98.219 | $+96.602 | RTY K=1000 h=21 RTYM6.parquet | `L mom89<-0.67 & aeff89>0.0 & barups>0.67` |
| **$+96.602** | $+98.219 | $+96.602 | RTY K=1000 h=21 RTYM6.parquet | `L mom89<-0.0 & aeff89>0.0 & barups>0.67` |
| **$+96.602** | $+98.219 | $+96.602 | RTY K=1000 h=21 RTYM6.parquet | `L eff89<-0.67 & aeff89>0.0 & barups>0.67` |
| **$+96.602** | $+98.219 | $+96.602 | RTY K=1000 h=21 RTYM6.parquet | `L eff89<-0.0 & aeff89>0.0 & barups>0.67` |
| **$+95.668** | $+95.668 | $+118.626 | RTY K=1600 h=21 RTYM6.parquet | `L pos89<-0.0 & eff89<-0.67 & barpath>0.67` |
| **$+95.480** | $+98.219 | $+95.480 | RTY K=1000 h=21 RTYM6.parquet | `L pos89<-0.0 & aeff89>0.0 & barups>0.67` |
| **$+95.443** | $+99.655 | $+95.443 | YM K=1000 h=21 YMM5.parquet | `L chop34<-0.0 & upl34<-0.67 & exp89<-0.0` |
| **$+95.399** | $+97.333 | $+95.399 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & barpath>0.0 & cmp>0.0` |
| **$+95.179** | $+95.179 | $+112.376 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & brk89<-0.0 & barpath>0.67` |
| **$+94.772** | $+106.318 | $+94.772 | RTY K=1000 h=21 RTYM6.parquet | `L vmom89<-1.35 & bdn89>0.67 & upsz89>0.67` |
| **$+94.761** | $+94.761 | $+101.187 | YM K=1000 h=21 YMM5.parquet | `L vmom34<-0.67 & chop34<-0.0 & exp89<-0.0` |
| **$+94.697** | $+94.697 | $+102.891 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & upsz89>0.0 & barpath>0.67` |
| **$+94.533** | $+94.533 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & barpath>0.67 & barups>0.0` |
| **$+94.385** | $+97.886 | $+94.385 | RTY K=1000 h=21 RTYM6.parquet | `L aeff89>0.0 & dnh89<-0.0 & barups>0.67` |
| **$+94.385** | $+97.886 | $+94.385 | RTY K=1000 h=21 RTYM6.parquet | `L aeff89>0.0 & brk89<-0.0 & barups>0.67` |
| **$+94.356** | $+95.602 | $+94.356 | RTY K=1600 h=21 RTYM6.parquet | `L vmom34<-0.67 & eff89<-0.67 & barpath>0.0` |
| **$+94.326** | $+94.326 | $+103.658 | RTY K=1600 h=21 RTYM6.parquet | `L fail34<-0.0 & eff89<-0.67 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+101.141 | RTY K=1600 h=21 RTYM6.parquet | `L upsz34>0.0 & eff89<-0.67 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L vmom89<-0.67 & eff89<-0.67 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L vmom89<-0.0 & eff89<-0.67 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L mom89<-0.0 & eff89<-0.67 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & pthz89>0.0 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & fail89<-0.0 & barpath>0.67` |
| **$+94.326** | $+94.326 | $+99.577 | RTY K=1600 h=21 RTYM6.parquet | `L eff89<-0.67 & barpath>0.67` |

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

Conditions per cell: 601-623 (median 612).

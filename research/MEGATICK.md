Resumed: 16,936,068,408 evaluated, 55 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- NQ K=4000 `NQZ4.parquet`: 5,044 bars, 617 conditions, **313,179,328** distinct [203s, total 17,249,247,736 eval / 3,325,098,822 scored]
- NQ K=4000 `NQZ5.parquet`: 5,950 bars, 620 conditions, **317,769,840** distinct [533s, total 17,567,017,576 eval / 3,398,522,224 scored]
- ES K=4000 `ESZ4.parquet`: 5,721 bars, 615 conditions, **310,143,680** distinct [850s, total 17,877,161,256 eval / 3,464,594,854 scored]
- ES K=6500 `ESZ4.parquet`: 3,521 bars, 592 conditions, **276,632,128** distinct [916s, total 18,153,793,384 eval / 3,503,551,968 scored]
- CL K=650 `CLM6.parquet`: 5,998 bars, 619 conditions, **316,234,720** distinct [1098s, total 18,470,028,104 eval / 3,573,408,544 scored]
- CL K=1000 `CLM6.parquet`: 3,898 bars, 607 conditions, **298,197,248** distinct [1175s, total 18,768,225,352 eval / 3,619,118,530 scored]
- CL K=650 `CLU4.parquet`: 4,803 bars, 618 conditions, **314,704,552** distinct [1286s, total 19,082,929,904 eval / 3,673,923,290 scored]
- RTY K=1000 `RTYU4.parquet`: 6,168 bars, 617 conditions, **313,179,328** distinct [1476s, total 19,396,109,232 eval / 3,746,675,028 scored]
- RTY K=1600 `RTYU4.parquet`: 3,855 bars, 606 conditions, **296,725,880** distinct [1558s, total 19,692,835,112 eval / 3,792,698,380 scored]
- RTY K=1000 `RTYU5.parquet`: 5,278 bars, 612 conditions, **305,627,088** distinct [1692s, total 19,998,462,200 eval / 3,854,906,632 scored]
- YM K=1000 `YMM6.parquet`: 4,433 bars, 614 conditions, **308,633,240** distinct [1796s, total 20,307,095,440 eval / 3,911,228,892 scored]
- YM K=1000 `YMU4.parquet`: 5,685 bars, 621 conditions, **319,309,920** distinct [1968s, total 20,626,405,360 eval / 3,980,815,058 scored]
- HG K=150 `HGZ5.parquet`: 6,805 bars, 621 conditions, **319,309,920** distinct [2199s, total 20,945,715,280 eval / 4,057,053,062 scored]
- EURUSD K=250 `EURUSD_202603.parquet`: 3,624 bars, 605 conditions, **295,259,360** distinct [2267s, total 21,240,974,640 eval / 4,097,590,410 scored]
- EURUSD K=100 `EURUSD_202604.parquet`: 6,179 bars, 620 conditions, **317,769,840** distinct [2488s, total 21,558,744,480 eval / 4,169,796,522 scored]
- GBPUSD K=150 `GBPUSD_202509.parquet`: 4,813 bars, 612 conditions, **305,627,088** distinct [2602s, total 21,864,371,568 eval / 4,227,772,490 scored]
- AUDUSD K=100 `AUDUSD_202509.parquet`: 3,566 bars, 599 conditions, **286,561,600** distinct [2670s, total 22,150,933,168 eval / 4,270,332,590 scored]
- NZDUSD K=100 `NZDUSD_202509.parquet`: 4,707 bars, 612 conditions, **305,627,088** distinct [2777s, total 22,456,560,256 eval / 4,326,022,246 scored]
- USDCAD K=250 `USDCAD_202509.parquet`: 4,513 bars, 613 conditions, **307,127,712** distinct [2880s, total 22,763,687,968 eval / 4,378,176,210 scored]
- USDCHF K=150 `USDCHF_202509.parquet`: 3,506 bars, 599 conditions, **286,561,600** distinct [2941s, total 23,050,249,568 eval / 4,418,807,274 scored]
- USDJPY K=150 `USDJPY_202511.parquet`: 6,796 bars, 623 conditions, **322,404,992** distinct [3153s, total 23,372,654,560 eval / 4,498,027,576 scored]
- USDJPY K=250 `USDJPY_202511.parquet`: 4,077 bars, 605 conditions, **295,259,360** distinct [3240s, total 23,667,913,920 eval / 4,546,632,134 scored]
- XAUUSD K=1000 `XAUUSD_202510.parquet`: 5,841 bars, 622 conditions, **320,854,968** distinct [3409s, total 23,988,768,888 eval / 4,610,775,672 scored]
- NQ K=6500 `NQZ5.parquet`: 3,661 bars, 606 conditions, **296,725,880** distinct [3487s, total 24,285,494,768 eval / 4,654,218,034 scored]
- ES K=6500 `ESZ5.parquet`: 4,848 bars, 603 conditions, **292,340,832** distinct [3618s, total 24,577,835,600 eval / 4,709,876,628 scored]
- CL K=400 `CLU5.parquet`: 5,265 bars, 615 conditions, **310,143,680** distinct [3755s, total 24,887,979,280 eval / 4,768,617,940 scored]
- CL K=650 `CLZ4.parquet`: 4,720 bars, 613 conditions, **307,127,712** distinct [3867s, total 25,195,106,992 eval / 4,822,435,414 scored]
- CL K=400 `CLZ5.parquet`: 5,967 bars, 617 conditions, **313,179,328** distinct [4042s, total 25,508,286,320 eval / 4,890,883,936 scored]
- RTY K=1000 `RTYZ4.parquet`: 4,831 bars, 612 conditions, **305,627,088** distinct [4153s, total 25,813,913,408 eval / 4,950,325,896 scored]
- RTY K=1000 `RTYZ5.parquet`: 6,577 bars, 620 conditions, **317,769,840** distinct [4354s, total 26,131,683,248 eval / 5,025,339,076 scored]

## 26,131,683,248 distinct configurations evaluated; **5,025,339,076 scored** (met the sample-size gate) in 1.21 h

Null: 26,131,683,248 evaluated, 5,025,339,076 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 115 | **31.3%** | **$-22.2332** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+372.157 | 502 | **31.5%** | **$-35.4781** | 58.2% | $+18.6639 |
| top 0.0001% | >= $+305.127 | 4,977 | **23.1%** | **$-49.5899** | 58.1% | $+13.8719 |
| top 0.001% | >= $+219.743 | 49,929 | **31.4%** | **$-47.0186** | 59.0% | $+27.2832 |
| top 0.01% | >= $+149.807 | 498,733 | **42.9%** | **$-18.5042** | 58.0% | $+32.6556 |
| top 0.1% | >= $+88.747 | 4,996,293 | **42.7%** | **$-16.7873** | 53.6% | $+20.7964 |
| top 1% | >= $+36.600 | 49,988,175 | **43.8%** | **$-10.0585** | 48.1% | $+4.6762 |
| top 10% | >= $+7.829 | 502,047,665 | **57.1%** | **$+0.3427** | 54.7% | $+1.9342 |
| top 100% | >= $-402.429 | 5,025,339,076 | **50.0%** | **$-0.0000** | 50.0% | $+0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market — is the pooled number hiding one live market?

Mean dollars per market is identically zero by construction: every configuration is scored alongside its short mirror, so the two cancel. The informative per-market number is the survivor rate against that market's OWN shifted null, because a single market with real structure would show a lift here even when the pooled figure sits at 1.0.

| market | scored (this run) | made money both halves | rate | NULL rate | lift |
|---|---|---|---|---|---|
| CL | 351,378,630 | 129,542,162 | 36.867% | 33.485% | **1.101x** |
| RTY | 315,438,482 | 100,994,241 | 32.017% | 32.401% | **0.988x** |
| NQ | 177,002,602 | 43,165,503 | 24.387% | 26.796% | **0.910x** |
| ES | 160,688,338 | 51,593,214 | 32.108% | 31.710% | **1.013x** |
| USDJPY | 127,824,860 | 53,861,488 | 42.137% | 41.685% | **1.011x** |
| YM | 125,908,426 | 39,592,306 | 31.445% | 29.386% | **1.070x** |
| EURUSD | 112,743,460 | 47,079,627 | 41.758% | 40.442% | **1.033x** |
| HG | 76,238,004 | 28,030,021 | 36.766% | 34.261% | **1.073x** |
| XAUUSD | 64,143,538 | 25,738,127 | 40.126% | 43.269% | **0.927x** |
| GBPUSD | 57,975,968 | 26,033,975 | 44.905% | 40.030% | **1.122x** |
| NZDUSD | 55,689,656 | 27,538,497 | 49.450% | 47.565% | **1.040x** |
| USDCAD | 52,153,964 | 25,545,182 | 48.980% | 47.887% | **1.023x** |
| AUDUSD | 42,560,100 | 20,800,944 | 48.874% | 49.491% | **0.988x** |
| USDCHF | 40,631,064 | 19,550,142 | 48.116% | 48.599% | **0.990x** |

Counts here begin from the run that added this table, so they cover the later cells rather than the whole campaign; the lift ratio is unaffected because both columns cover the same cells.

**The effective sample size is CELLS, not configurations.** Inside one cell, hundreds of millions of configurations share the same bars and heavily overlapping conditions, so they are nowhere near independent tests. A market-level lift of 1.14 means nothing unless the cells inside that market agree. The spread below is the honest error bar.

| market | cells | mean per-cell lift | worst cell | best cell |
|---|---|---|---|---|
| CL | 6 | **1.109x** | 1.009x | 1.228x |
| RTY | 5 | **1.001x** | 0.883x | 1.072x |
| NQ | 3 | **0.909x** | 0.884x | 0.940x |
| ES | 3 | **1.027x** | 0.939x | 1.108x |
| YM | 2 | **1.070x** | 1.069x | 1.071x |
| EURUSD | 2 | **1.072x** | 0.975x | 1.169x |
| USDJPY | 2 | **1.012x** | 1.006x | 1.019x |
| HG | 1 | **1.073x** | 1.073x | 1.073x |
| GBPUSD | 1 | **1.122x** | 1.122x | 1.122x |
| AUDUSD | 1 | **0.988x** | 0.988x | 0.988x |
| NZDUSD | 1 | **1.040x** | 1.040x | 1.040x |
| USDCAD | 1 | **1.023x** | 1.023x | 1.023x |
| USDCHF | 1 | **0.990x** | 0.990x | 0.990x |
| XAUUSD | 1 | **0.927x** | 0.927x | 0.927x |

Across all 30 cells: mean lift **1.031x**, spread 0.883x to 1.228x, and 20/30 cells above 1.0 (a coin would give 15). If the count of cells above 1.0 is near half and the spread straddles 1.0, the market-level numbers above are cell noise, not structure.

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 5,025,339,076 | **639,065,429** | 12.717% |
| shifted null | 5,025,339,076 | 623,481,862 | 12.407% |

Lift over chance: **1.02x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+253.449** | $+257.710 | $+253.449 | NQ K=6500 h=21 NQZ5.parquet | `L mom89<-0.0 & acc89>0.0 & chop89<-0.0` |
| **$+236.701** | $+240.090 | $+236.701 | NQ K=6500 h=21 NQZ5.parquet | `L mom89<-0.0 & acc89>0.0 & bdn89>0.0` |
| **$+236.701** | $+239.547 | $+236.701 | NQ K=6500 h=21 NQZ5.parquet | `L mom89<-0.0 & acc89>0.0 & upl89<-0.0` |
| **$+234.070** | $+234.070 | $+238.763 | NQ K=6500 h=21 NQZ5.parquet | `L faild5<-0.0 & acc89>0.0 & vwapd<-0.67` |
| **$+233.734** | $+261.136 | $+233.734 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & acc89<-0.0 & vwapd<-0.67` |
| **$+233.331** | $+233.331 | $+274.915 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.0 & pos89<-0.0 & acc89>0.0` |
| **$+228.692** | $+235.029 | $+228.692 | NQ K=6500 h=21 NQZ5.parquet | `L acc89>0.0 & eff89<-0.0 & vwapd<-0.67` |
| **$+227.397** | $+246.478 | $+227.397 | NQ K=6500 h=21 NQZ5.parquet | `L vmom89<-0.0 & acc89>0.0 & vwapd<-0.67` |
| **$+226.613** | $+226.613 | $+252.081 | NQ K=6500 h=21 NQZ5.parquet | `L faild13<-0.0 & acc89>0.0 & vwapd<-0.67` |
| **$+225.480** | $+256.526 | $+225.480 | NQ K=6500 h=21 NQZ5.parquet | `L mom89<-0.0 & acc89>0.0 & vwapd<-0.67` |
| **$+221.368** | $+221.368 | $+246.843 | NQ K=6500 h=21 NQZ5.parquet | `L faild34<-0.0 & acc89>0.0 & vwapd<-0.67` |
| **$+219.774** | $+265.853 | $+219.774 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.0 & acc89>0.0 & bdn89>0.0` |
| **$+218.881** | $+262.599 | $+218.881 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.0 & acc89>0.0 & upl89<-0.0` |
| **$+218.769** | $+218.769 | $+264.664 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.0 & rev89>0.0 & acc89>0.0` |
| **$+218.591** | $+218.591 | $+228.635 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.67 & run34<-0.0 & acc89>0.0` |
| **$+212.426** | $+212.426 | $+261.893 | NQ K=6500 h=21 NQZ5.parquet | `L mom89<-0.0 & pos89<-0.0 & acc89>0.0` |
| **$+211.707** | $+211.707 | $+224.268 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.67 & vdir34<-0.0 & acc89>0.0` |
| **$+211.213** | $+213.824 | $+211.213 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & pos89<-0.67 & vwapd<-0.67` |
| **$+206.626** | $+206.626 | $+212.566 | NQ K=6500 h=21 NQZ5.parquet | `L dnh13>0.0 & rev89>0.0 & exp89<-0.0` |
| **$+206.153** | $+235.718 | $+206.153 | NQ K=6500 h=21 NQZ5.parquet | `L vmom89<-0.0 & acc89>0.0 & bdn89>0.0` |
| **$+206.153** | $+235.230 | $+206.153 | NQ K=6500 h=21 NQZ5.parquet | `L vmom89<-0.0 & acc89>0.0 & upl89<-0.0` |
| **$+204.490** | $+204.490 | $+283.584 | NQ K=6500 h=21 NQZ5.parquet | `L run13>0.0 & run34<-0.0 & acc89>0.0` |
| **$+204.490** | $+204.490 | $+279.064 | NQ K=6500 h=21 NQZ5.parquet | `L vdir13>0.0 & run34<-0.0 & acc89>0.0` |
| **$+204.401** | $+236.930 | $+204.401 | NQ K=6500 h=21 NQZ5.parquet | `L acc89>0.0 & eff89<-0.0 & chop89<-0.0` |
| **$+203.870** | $+203.870 | $+233.470 | NQ K=6500 h=21 NQZ5.parquet | `L vmom89<-0.0 & pos89<-0.0 & acc89>0.0` |
| **$+201.993** | $+201.993 | $+229.450 | NQ K=6500 h=21 NQZ5.parquet | `L mom89<-0.0 & rev89>0.0 & acc89>0.0` |
| **$+200.751** | $+222.598 | $+200.751 | NQ K=6500 h=21 NQZ5.parquet | `L acc89>0.0 & barvel>0.0 & vwapd<-0.67` |
| **$+200.326** | $+229.044 | $+200.326 | NQ K=6500 h=21 NQZ5.parquet | `L acc89>0.0 & eff89<-0.0 & bdn89>0.0` |
| **$+200.326** | $+228.614 | $+200.326 | NQ K=6500 h=21 NQZ5.parquet | `L acc89>0.0 & eff89<-0.0 & upl89<-0.0` |
| **$+199.993** | $+199.993 | $+249.914 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & acc89<-0.0 & exp89>0.0` |
| **$+199.440** | $+199.440 | $+234.621 | NQ K=6500 h=21 NQZ5.parquet | `L pos89<-0.0 & acc89>0.0 & eff89<-0.0` |
| **$+198.749** | $+207.635 | $+198.749 | NQ K=6500 h=21 NQZ5.parquet | `L brk13>0.0 & rev89>0.0 & exp89<-0.0` |
| **$+198.628** | $+243.379 | $+198.628 | NQ K=6500 h=21 NQZ5.parquet | `L vmom89<-0.0 & acc89>0.0 & chop89<-0.0` |
| **$+198.297** | $+205.708 | $+198.297 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & bdn89>0.67 & vwapd<-0.67` |
| **$+198.297** | $+199.869 | $+198.297 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & upl89<-0.67 & vwapd<-0.67` |
| **$+197.171** | $+215.869 | $+197.171 | NQ K=4000 h=21 NQZ5.parquet | `L acc34<-0.0 & exp34>0.0 & vwapd<-1.35` |
| **$+197.017** | $+197.017 | $+199.430 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & rev89>0.0 & vwapd<-0.67` |
| **$+196.960** | $+196.960 | $+228.430 | NQ K=6500 h=21 NQZ5.parquet | `L pos13>0.0 & rev89>0.0 & exp89<-0.0` |
| **$+196.761** | $+196.761 | $+199.792 | NQ K=6500 h=21 NQZ5.parquet | `L bdn13<-0.0 & rev89>0.0 & exp89<-0.0` |
| **$+196.408** | $+196.408 | $+196.744 | NQ K=6500 h=21 NQZ5.parquet | `L upl13>0.0 & rev89>0.0 & exp89<-0.0` |
| **$+193.499** | $+193.499 | $+248.741 | NQ K=6500 h=21 NQZ5.parquet | `L exp89<-0.0 & dratio<-0.0 & vwapd<-0.67` |
| **$+193.051** | $+193.051 | $+351.373 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.0 & mom89<-0.0 & acc89>0.0` |
| **$+192.376** | $+192.376 | $+199.077 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vratio<-0.67 & vwapd<-0.67` |
| **$+192.366** | $+198.787 | $+192.366 | NQ K=6500 h=21 NQZ5.parquet | `L chop13>0.0 & run34<-0.0 & acc89>0.0` |
| **$+191.441** | $+191.441 | $+230.249 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & mom89<-0.67 & vwapd<-0.67` |
| **$+191.047** | $+191.047 | $+200.586 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & upl89<-0.0 & vwapd<-0.67` |
| **$+191.047** | $+191.047 | $+200.586 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & bdn89>0.0 & vwapd<-0.67` |
| **$+191.047** | $+191.047 | $+199.430 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & pos89<-0.0 & vwapd<-0.67` |
| **$+191.047** | $+191.047 | $+199.430 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & dnh89<-0.0 & vwapd<-0.67` |
| **$+191.047** | $+191.047 | $+199.430 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & brk89<-0.0 & vwapd<-0.67` |
| **$+190.948** | $+190.948 | $+313.316 | NQ K=6500 h=21 NQZ5.parquet | `L acc13>0.0 & vmom89<-0.0 & acc89>0.0` |
| **$+190.550** | $+220.329 | $+190.550 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & exp89>0.0 & vwapd<-0.67` |
| **$+189.514** | $+189.514 | $+201.325 | NQ K=6500 h=21 NQZ5.parquet | `L vmom89<-0.0 & rev89>0.0 & acc89>0.0` |
| **$+188.726** | $+188.726 | $+195.394 | NQ K=6500 h=21 NQZ5.parquet | `L faild5<-0.0 & exp89<-0.0 & vwapd<-0.67` |
| **$+188.113** | $+219.126 | $+188.113 | NQ K=6500 h=21 NQZ5.parquet | `S vpp13<-0.0 & exp34<-0.67 & aeff89>0.0` |
| **$+187.259** | $+195.077 | $+187.259 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & vmom89<-0.67 & vwapd<-0.67` |
| **$+186.773** | $+186.773 | $+263.134 | NQ K=6500 h=21 NQZ5.parquet | `L acc89>0.0 & faild89<-0.0 & vwapd<-0.67` |
| **$+186.073** | $+186.073 | $+193.161 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & acc89<-0.0 & eff89<-0.67` |
| **$+184.946** | $+184.946 | $+215.798 | NQ K=6500 h=21 NQZ5.parquet | `S exp34<-0.67 & aeff89>0.0 & barups>0.0` |
| **$+184.630** | $+184.630 | $+279.302 | NQ K=6500 h=21 NQZ5.parquet | `L dnh13>0.0 & acc89>0.0 & eff89<-0.0` |

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

Conditions per cell: 592-623 (median 613).

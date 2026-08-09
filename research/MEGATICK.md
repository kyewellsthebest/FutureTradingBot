Resumed: 16,936,068,408 evaluated, 55 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- NQ K=4000 `NQZ4.parquet`: 5,044 bars, 617 conditions, **313,179,328** distinct [203s, total 17,249,247,736 eval / 3,325,098,822 scored]

## 17,249,247,736 distinct configurations evaluated; **3,325,098,822 scored** (met the sample-size gate) in 0.06 h

Null: 17,249,247,736 evaluated, 3,325,098,822 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 115 | **31.3%** | **$-22.2332** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+380.076 | 332 | **34.3%** | **$-28.0079** | - | - |
| top 0.0001% | >= $+326.013 | 3,291 | **18.3%** | **$-51.2835** | 57.4% | $+11.3076 |
| top 0.001% | >= $+232.691 | 32,860 | **29.6%** | **$-51.1728** | 58.8% | $+24.4480 |
| top 0.01% | >= $+160.580 | 327,733 | **41.2%** | **$-22.0657** | 59.1% | $+34.9122 |
| top 0.1% | >= $+96.905 | 3,324,744 | **43.0%** | **$-16.4198** | 55.1% | $+24.8205 |
| top 1% | >= $+40.637 | 33,141,898 | **43.6%** | **$-10.5910** | 48.5% | $+6.4405 |
| top 10% | >= $+8.516 | 332,007,907 | **56.8%** | **$+0.0164** | 54.8% | $+2.2812 |
| top 100% | >= $-402.429 | 3,325,098,822 | **50.0%** | **$+0.0000** | 50.0% | $-0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market — is the pooled number hiding one live market?

Mean dollars per market is identically zero by construction: every configuration is scored alongside its short mirror, so the two cancel. The informative per-market number is the survivor rate against that market's OWN shifted null, because a single market with real structure would show a lift here even when the pooled figure sits at 1.0.

| market | scored (this run) | made money both halves | rate | NULL rate | lift |
|---|---|---|---|---|---|
| NQ | 60,136,838 | 15,770,058 | 26.224% | 29.680% | **0.884x** |

Counts here begin from the run that added this table, so they cover the later cells rather than the whole campaign; the lift ratio is unaffected because both columns cover the same cells.

**The effective sample size is CELLS, not configurations.** Inside one cell, hundreds of millions of configurations share the same bars and heavily overlapping conditions, so they are nowhere near independent tests. A market-level lift of 1.14 means nothing unless the cells inside that market agree. The spread below is the honest error bar.

| market | cells | mean per-cell lift | worst cell | best cell |
|---|---|---|---|---|
| NQ | 1 | **0.884x** | 0.884x | 0.884x |

Across all 1 cells: mean lift **0.884x**, spread 0.884x to 0.884x, and 0/1 cells above 1.0 (a coin would give 0). If the count of cells above 1.0 is near half and the spread straddles 1.0, the market-level numbers above are cell noise, not structure.

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 3,325,098,822 | **15,770,058** | 0.474% |
| shifted null | 3,325,098,822 | 17,848,720 | 0.537% |

Lift over chance: **0.88x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+152.617** | $+161.274 | $+152.617 | NQ K=4000 h=21 NQZ4.parquet | `L bdn13<-0.0 & aeff34<-0.0 & chop34>1.35` |
| **$+142.366** | $+142.995 | $+142.366 | NQ K=4000 h=21 NQZ4.parquet | `L aeff34<-0.0 & chop34>1.35 & exp34<-0.0` |
| **$+140.193** | $+158.039 | $+140.193 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & aeff34<-0.0 & chop34>1.35` |
| **$+138.140** | $+160.148 | $+138.140 | NQ K=4000 h=21 NQZ4.parquet | `L pos13>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+137.458** | $+137.458 | $+280.183 | NQ K=4000 h=21 NQZ4.parquet | `S dnh13<-0.0 & exp89>0.0 & dratio>0.67` |
| **$+136.561** | $+152.022 | $+136.561 | NQ K=4000 h=21 NQZ4.parquet | `L dnh13>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+136.306** | $+155.924 | $+136.306 | NQ K=4000 h=21 NQZ4.parquet | `L bdn13<-0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+135.382** | $+147.091 | $+135.382 | NQ K=4000 h=21 NQZ4.parquet | `L chop89>0.0 & upl89>0.67 & exp89<-0.67` |
| **$+135.349** | $+135.349 | $+153.126 | NQ K=4000 h=21 NQZ4.parquet | `S aeff34>0.0 & exp89>0.0 & vratio<-0.67` |
| **$+134.894** | $+157.868 | $+134.894 | NQ K=4000 h=21 NQZ4.parquet | `L upl13>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+134.791** | $+155.562 | $+134.791 | NQ K=4000 h=21 NQZ4.parquet | `L brk13>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+133.489** | $+167.155 | $+133.489 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+133.306** | $+148.831 | $+133.306 | NQ K=4000 h=21 NQZ4.parquet | `L brk5>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+133.200** | $+133.200 | $+284.480 | NQ K=4000 h=21 NQZ4.parquet | `S brk13<-0.0 & exp89>0.0 & dratio>0.67` |
| **$+133.016** | $+133.016 | $+137.176 | NQ K=4000 h=21 NQZ4.parquet | `L dnh5>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+131.752** | $+144.810 | $+131.752 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & bdn13<-0.0 & chop34>1.35` |
| **$+131.133** | $+131.133 | $+162.669 | NQ K=4000 h=21 NQZ4.parquet | `S aeff34>0.0 & exp89>0.0 & dratio>0.67` |
| **$+130.594** | $+130.594 | $+143.541 | NQ K=4000 h=21 NQZ4.parquet | `L vel13<-0.0 & chop34>1.35 & vel34<-0.0` |
| **$+130.449** | $+131.241 | $+130.449 | NQ K=4000 h=21 NQZ4.parquet | `L rev13<-0.0 & acc13>0.0 & chop34>1.35` |
| **$+130.257** | $+145.168 | $+130.257 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & upl13>0.0 & chop34>1.35` |
| **$+129.338** | $+129.338 | $+168.132 | NQ K=4000 h=21 NQZ4.parquet | `S exp34>0.0 & exp89>0.0 & vel89<-0.67` |
| **$+128.787** | $+129.532 | $+128.787 | NQ K=4000 h=21 NQZ4.parquet | `L chop34>0.67 & run34<-0.0 & vratio>0.67` |
| **$+128.254** | $+128.254 | $+137.244 | NQ K=4000 h=21 NQZ4.parquet | `S exp89>0.0 & cmp>0.0 & dratio>1.35` |
| **$+127.892** | $+147.719 | $+127.892 | NQ K=4000 h=21 NQZ4.parquet | `L chop89>0.0 & exp89<-0.67 & bdn89<-0.67` |
| **$+127.545** | $+136.713 | $+127.545 | NQ K=4000 h=21 NQZ4.parquet | `L chop34>1.35 & exp34<-0.0 & fail34<-0.0` |
| **$+127.244** | $+145.624 | $+127.244 | NQ K=4000 h=21 NQZ4.parquet | `L pos13>0.0 & acc13>0.0 & chop34>1.35` |
| **$+126.661** | $+126.661 | $+134.962 | NQ K=4000 h=21 NQZ4.parquet | `S chop34<-0.0 & run34>0.0 & barvol<-0.67` |
| **$+126.237** | $+128.268 | $+126.237 | NQ K=4000 h=21 NQZ4.parquet | `L mom5>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+126.208** | $+126.208 | $+130.769 | NQ K=4000 h=21 NQZ4.parquet | `S eff34<-0.67 & aeff89>0.0 & vratio<-0.0` |
| **$+126.038** | $+140.831 | $+126.038 | NQ K=4000 h=21 NQZ4.parquet | `L chop34>1.35 & exp34<-0.0 & fail89<-0.0` |
| **$+125.921** | $+137.053 | $+125.921 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & dnh13>0.0 & chop34>1.35` |
| **$+125.893** | $+125.893 | $+166.493 | NQ K=4000 h=21 NQZ4.parquet | `S acc13<-0.0 & exp89>0.0 & vel89<-0.67` |
| **$+125.787** | $+125.787 | $+159.603 | NQ K=4000 h=21 NQZ4.parquet | `S exp34>0.0 & exp89>0.0 & dratio>0.67` |
| **$+125.768** | $+134.960 | $+125.768 | NQ K=4000 h=21 NQZ4.parquet | `L eff5>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+125.768** | $+127.988 | $+125.768 | NQ K=4000 h=21 NQZ4.parquet | `L vmom5>0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+125.552** | $+125.552 | $+235.016 | NQ K=4000 h=21 NQZ4.parquet | `S pos13<-0.0 & exp89>0.0 & barvel<-0.67` |
| **$+124.240** | $+124.240 | $+168.745 | NQ K=4000 h=21 NQZ4.parquet | `S exp34>0.0 & exp89>0.0 & vel89<-0.0` |
| **$+124.154** | $+129.101 | $+124.154 | NQ K=4000 h=21 NQZ4.parquet | `L upl13>0.0 & chop34>0.67 & run34<-0.0` |
| **$+124.089** | $+132.192 | $+124.089 | NQ K=4000 h=21 NQZ4.parquet | `S rev34<-0.0 & run89>0.67 & pthz89>0.0` |
| **$+123.753** | $+154.320 | $+123.753 | NQ K=4000 h=21 NQZ4.parquet | `L rev13<-0.0 & chop34>1.35 & aeff89<-0.0` |
| **$+123.075** | $+123.075 | $+198.754 | NQ K=4000 h=21 NQZ4.parquet | `S exp89>0.0 & barups>0.0 & dratio>1.35` |
| **$+122.851** | $+122.851 | $+127.791 | NQ K=4000 h=21 NQZ4.parquet | `L eff13>0.0 & chop34>1.35 & fail34<-0.0` |
| **$+122.752** | $+124.413 | $+122.752 | NQ K=4000 h=21 NQZ4.parquet | `S exp89>0.0 & pthz89>0.0 & dratio>1.35` |
| **$+122.658** | $+122.658 | $+181.491 | NQ K=4000 h=21 NQZ4.parquet | `S dnh13<-0.0 & exp89>0.0 & vel89<-0.67` |
| **$+122.491** | $+122.491 | $+147.010 | NQ K=4000 h=21 NQZ4.parquet | `S exp89>0.0 & vratio<-0.67 & dratio>1.35` |
| **$+122.247** | $+122.247 | $+168.132 | NQ K=4000 h=21 NQZ4.parquet | `S exp34>0.0 & exp89>0.0 & dratio>0.0` |
| **$+121.852** | $+124.356 | $+121.852 | NQ K=4000 h=21 NQZ4.parquet | `L bdn13<-0.0 & chop34>0.67 & run34<-0.0` |
| **$+121.612** | $+121.612 | $+194.696 | NQ K=4000 h=21 NQZ4.parquet | `S brk5<-0.0 & exp89>0.0 & dratio>0.67` |
| **$+121.555** | $+132.033 | $+121.555 | NQ K=4000 h=21 NQZ4.parquet | `L vpp89>0.0 & cmp<-0.0 & vwapd<-0.67` |
| **$+121.449** | $+131.055 | $+121.449 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & eff13>0.0 & chop34>1.35` |
| **$+121.261** | $+121.261 | $+129.763 | NQ K=4000 h=21 NQZ4.parquet | `L faild13<-0.0 & chop34>1.35 & vel34<-0.0` |
| **$+120.995** | $+120.995 | $+251.411 | NQ K=4000 h=21 NQZ4.parquet | `S pos5<-0.0 & exp89>0.0 & dratio>0.67` |
| **$+120.788** | $+131.816 | $+120.788 | NQ K=4000 h=21 NQZ4.parquet | `L vmom13>0.0 & acc13>0.0 & chop34>1.35` |
| **$+120.788** | $+131.816 | $+120.788 | NQ K=4000 h=21 NQZ4.parquet | `L mom13>0.0 & acc13>0.0 & chop34>1.35` |
| **$+120.633** | $+140.295 | $+120.633 | NQ K=4000 h=21 NQZ4.parquet | `L acc13>0.0 & brk13>0.0 & chop34>1.35` |
| **$+120.121** | $+120.121 | $+135.186 | NQ K=4000 h=21 NQZ4.parquet | `S exp89>0.0 & absb89<-0.67 & dratio>1.35` |
| **$+120.059** | $+120.059 | $+325.533 | NQ K=4000 h=21 NQZ4.parquet | `S mom13<-0.0 & exp89>0.0 & dratio>0.67` |
| **$+119.991** | $+122.448 | $+119.991 | NQ K=4000 h=21 NQZ4.parquet | `S eff34>0.67 & chop34<-0.0 & vpp34<-0.0` |
| **$+119.833** | $+119.833 | $+179.429 | NQ K=4000 h=21 NQZ4.parquet | `S exp34>0.0 & exp89>0.0 & barvel<-0.0` |
| **$+119.780** | $+119.780 | $+129.763 | NQ K=4000 h=21 NQZ4.parquet | `L chop34>1.35 & vel34<-0.0 & faild89<-0.0` |

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

Conditions per cell: 617-617 (median 617).

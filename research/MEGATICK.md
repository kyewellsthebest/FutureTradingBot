Resumed: 16,021,963,688 evaluated, 52 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- XAUUSD K=400 `XAUUSD_202509.parquet`: 4,977 bars, 617 conditions, **313,179,328** distinct [117s, total 16,335,143,016 eval / 3,160,093,794 scored]
- NQ K=6500 `NQU4.parquet`: 3,875 bars, 604 conditions, **293,797,680** distinct [181s, total 16,628,940,696 eval / 3,207,274,740 scored]
- NQ K=4000 `NQU5.parquet`: 4,680 bars, 613 conditions, **307,127,712** distinct [261s, total 16,936,068,408 eval / 3,264,961,984 scored]

## 16,936,068,408 distinct configurations evaluated; **3,264,961,984 scored** (met the sample-size gate) in 0.07 h

Null: 16,936,068,408 evaluated, 3,264,961,984 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 115 | **31.3%** | **$-22.2332** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+381.221 | 312 | **35.6%** | **$-26.3898** | - | - |
| top 0.0001% | >= $+326.996 | 3,227 | **18.2%** | **$-51.2872** | 57.3% | $+11.0021 |
| top 0.001% | >= $+233.393 | 32,135 | **29.5%** | **$-51.5913** | 58.8% | $+24.1050 |
| top 0.01% | >= $+161.065 | 322,149 | **41.2%** | **$-22.1831** | 59.1% | $+34.9747 |
| top 0.1% | >= $+97.494 | 3,235,412 | **43.0%** | **$-16.4233** | 55.2% | $+24.9984 |
| top 1% | >= $+40.637 | 32,465,191 | **43.6%** | **$-10.5302** | 48.5% | $+6.5145 |
| top 10% | >= $+8.403 | 326,471,664 | **57.0%** | **$+0.1642** | 54.7% | $+2.2676 |
| top 100% | >= $-402.429 | 3,264,961,984 | **50.0%** | **$+0.0000** | 50.0% | $-0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market — is the pooled number hiding one live market?

Mean dollars per market is identically zero by construction: every configuration is scored alongside its short mirror, so the two cancel. The informative per-market number is the survivor rate against that market's OWN shifted null, because a single market with real structure would show a lift here even when the pooled figure sits at 1.0.

| market | scored (this run) | made money both halves | rate | NULL rate | lift |
|---|---|---|---|---|---|
| NQ | 104,868,190 | 28,252,043 | 26.941% | 25.346% | **1.063x** |
| XAUUSD | 62,833,282 | 29,904,557 | 47.593% | 48.898% | **0.973x** |

Counts here begin from the run that added this table, so they cover the later cells rather than the whole campaign; the lift ratio is unaffected because both columns cover the same cells.

**The effective sample size is CELLS, not configurations.** Inside one cell, hundreds of millions of configurations share the same bars and heavily overlapping conditions, so they are nowhere near independent tests. A market-level lift of 1.14 means nothing unless the cells inside that market agree. The spread below is the honest error bar.

| market | cells | mean per-cell lift | worst cell | best cell |
|---|---|---|---|---|
| NQ | 2 | **1.081x** | 0.994x | 1.168x |
| XAUUSD | 1 | **0.973x** | 0.973x | 0.973x |

Across all 3 cells: mean lift **1.045x**, spread 0.973x to 1.168x, and 1/3 cells above 1.0 (a coin would give 2). If the count of cells above 1.0 is near half and the spread straddles 1.0, the market-level numbers above are cell noise, not structure.

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 3,264,961,984 | **58,156,600** | 1.781% |
| shifted null | 3,264,961,984 | 57,303,930 | 1.755% |

Lift over chance: **1.01x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+234.049** | $+234.049 | $+275.444 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & mom34<-0.67 & chop89>0.67` |
| **$+233.707** | $+240.843 | $+233.707 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.0 & dnh34>0.0 & vpp89<-0.67` |
| **$+233.133** | $+242.622 | $+233.133 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.0 & brk34>0.0 & vpp89<-0.67` |
| **$+232.775** | $+232.775 | $+250.451 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.67 & exp89<-0.67 & fail89<-0.0` |
| **$+232.168** | $+232.168 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S vmom13<-0.67 & rev89>1.35 & chop89>0.67` |
| **$+230.495** | $+230.495 | $+254.230 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & chop89>0.67 & brk89<-0.67` |
| **$+230.383** | $+230.383 | $+242.029 | NQ K=6500 h=21 NQU4.parquet | `S mom13<-0.67 & pos89<-1.35 & chop89>0.67` |
| **$+230.016** | $+230.016 | $+241.279 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.67 & exp89<-0.67` |
| **$+230.016** | $+230.016 | $+241.279 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.67 & exp89<-0.0 & exp89<-0.67` |
| **$+230.016** | $+230.016 | $+241.279 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.0 & chop34>0.67 & exp89<-0.67` |
| **$+229.889** | $+229.889 | $+239.710 | NQ K=6500 h=21 NQU4.parquet | `L vpp5<-0.67 & chop13<-0.67 & aeff34<-0.0` |
| **$+229.699** | $+229.699 | $+241.279 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.67 & exp89<-0.67 & faild89<-0.0` |
| **$+229.165** | $+229.165 | $+254.230 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & rev89>0.67 & chop89>0.67` |
| **$+229.003** | $+229.003 | $+249.024 | NQ K=6500 h=21 NQU4.parquet | `S exp13<-0.0 & chop34>0.0 & run89<-0.67` |
| **$+228.733** | $+228.733 | $+261.320 | NQ K=6500 h=21 NQU4.parquet | `S eff13<-0.67 & rev89>1.35 & chop89>0.67` |
| **$+228.376** | $+228.376 | $+275.372 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & eff34<-0.67 & chop89>0.67` |
| **$+228.087** | $+228.087 | $+268.290 | NQ K=6500 h=21 NQU4.parquet | `S eff34<-0.67 & rev89>1.35 & chop89>0.67` |
| **$+228.059** | $+228.059 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S mom34<-0.67 & rev89>1.35 & chop89>0.67` |
| **$+226.867** | $+226.867 | $+266.647 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.0 & exp89<-0.67 & barpath>0.0` |
| **$+226.728** | $+226.728 | $+232.670 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.67 & faild34<-0.0 & exp89<-0.67` |
| **$+225.932** | $+225.932 | $+256.045 | NQ K=6500 h=21 NQU4.parquet | `L chop34<-0.0 & barpath>0.67 & volst>0.0` |
| **$+225.886** | $+225.886 | $+232.324 | NQ K=6500 h=21 NQU4.parquet | `S pos34>0.0 & chop34>0.0 & vpp89<-0.67` |
| **$+225.835** | $+225.835 | $+254.230 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & pos89<-0.67 & chop89>0.67` |
| **$+225.835** | $+225.835 | $+254.230 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & chop89>0.67 & upl89<-0.67` |
| **$+225.835** | $+225.835 | $+254.230 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & chop89>0.67 & bdn89>0.67` |
| **$+224.003** | $+228.717 | $+224.003 | NQ K=6500 h=21 NQU4.parquet | `S chop13>0.67 & chop34>0.67 & exp89<-0.0` |
| **$+223.363** | $+227.390 | $+223.363 | NQ K=6500 h=21 NQU4.parquet | `L chop13<-0.0 & vpp89<-0.0 & cmp>0.67` |
| **$+222.949** | $+222.949 | $+254.230 | NQ K=6500 h=21 NQU4.parquet | `S aeff13>0.67 & chop89>0.67 & dnh89<-0.67` |
| **$+222.362** | $+222.362 | $+252.540 | NQ K=6500 h=21 NQU4.parquet | `L rev13>0.0 & chop34<-0.0 & barpath>0.67` |
| **$+221.810** | $+221.810 | $+256.029 | NQ K=6500 h=21 NQU4.parquet | `S pos5<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+221.665** | $+221.665 | $+241.243 | NQ K=6500 h=21 NQU4.parquet | `S exp13<-0.0 & chop34>0.0 & brk89<-0.67` |
| **$+221.521** | $+221.521 | $+229.195 | NQ K=6500 h=21 NQU4.parquet | `S mom13<-0.67 & aeff34>0.0 & chop89>0.67` |
| **$+221.213** | $+221.213 | $+253.370 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & vdir89<-0.0` |
| **$+221.213** | $+221.213 | $+253.370 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & run89<-0.0` |
| **$+221.188** | $+221.188 | $+259.912 | NQ K=6500 h=21 NQU4.parquet | `S acc34<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+220.951** | $+220.951 | $+256.029 | NQ K=6500 h=21 NQU4.parquet | `S dnh5<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+220.069** | $+220.069 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S vmom34<-0.67 & rev89>1.35 & chop89>0.67` |
| **$+219.849** | $+238.515 | $+219.849 | NQ K=6500 h=21 NQU4.parquet | `L aeff34<-0.0 & chop34<-0.0 & barpath>0.67` |
| **$+218.828** | $+218.828 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S fail5<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+218.774** | $+218.774 | $+230.083 | NQ K=6500 h=21 NQU4.parquet | `S chop34>0.67 & pthz34>0.0 & eff89<-0.0` |
| **$+218.665** | $+218.665 | $+289.711 | NQ K=6500 h=21 NQU4.parquet | `L vpp5<-0.67 & dnh34<-0.0 & chop89<-0.0` |
| **$+218.607** | $+218.607 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & vwapd<-0.0` |
| **$+218.540** | $+218.540 | $+264.745 | NQ K=6500 h=21 NQU4.parquet | `S mom89<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S vmom89<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S vmom34<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S vmom13<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S upl34<-0.67 & rev89>1.35 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S upl34<-0.0 & rev89>1.35 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & pos89<-0.67 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & pos89<-0.0 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & eff89<-0.0 & chop89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & upl89<-0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & upl89<-0.0` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & fail89<-0.0` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & dnh89<-0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & dnh89<-0.0` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & brk89<-0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & brk89<-0.0` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & bdn89>0.67` |
| **$+218.540** | $+218.540 | $+257.692 | NQ K=6500 h=21 NQU4.parquet | `S rev89>1.35 & chop89>0.67 & bdn89>0.0` |

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

Conditions per cell: 604-617 (median 613).

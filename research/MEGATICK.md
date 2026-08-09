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

## 21,240,974,640 distinct configurations evaluated; **4,097,590,410 scored** (met the sample-size gate) in 0.63 h

Null: 21,240,974,640 evaluated, 4,097,590,410 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 115 | **31.3%** | **$-22.2332** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+377.797 | 379 | **31.9%** | **$-31.5497** | 55.6% | $+18.3832 |
| top 0.0001% | >= $+315.398 | 4,042 | **19.9%** | **$-52.2002** | 57.5% | $+12.1655 |
| top 0.001% | >= $+225.784 | 40,923 | **30.7%** | **$-49.0020** | 58.7% | $+25.3936 |
| top 0.01% | >= $+154.867 | 408,391 | **42.2%** | **$-19.9037** | 58.3% | $+33.5687 |
| top 0.1% | >= $+92.878 | 4,079,552 | **43.0%** | **$-16.4432** | 53.8% | $+21.9301 |
| top 1% | >= $+38.805 | 40,954,354 | **44.1%** | **$-9.9003** | 47.5% | $+4.5873 |
| top 10% | >= $+8.431 | 409,153,619 | **55.9%** | **$-0.1252** | 53.1% | $+1.3290 |
| top 100% | >= $-402.429 | 4,097,590,410 | **50.0%** | **$-0.0000** | 50.0% | $+0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market — is the pooled number hiding one live market?

Mean dollars per market is identically zero by construction: every configuration is scored alongside its short mirror, so the two cancel. The informative per-market number is the survivor rate against that market's OWN shifted null, because a single market with real structure would show a lift here even when the pooled figure sits at 1.0.

| market | scored (this run) | made money both halves | rate | NULL rate | lift |
|---|---|---|---|---|---|
| RTY | 180,983,342 | 58,914,389 | 32.552% | 32.117% | **1.014x** |
| CL | 170,371,322 | 56,690,447 | 33.275% | 30.539% | **1.090x** |
| NQ | 133,560,240 | 33,249,178 | 24.895% | 27.285% | **0.912x** |
| YM | 125,908,426 | 39,592,306 | 31.445% | 29.386% | **1.070x** |
| ES | 105,029,744 | 34,486,020 | 32.835% | 33.809% | **0.971x** |
| HG | 76,238,004 | 28,030,021 | 36.766% | 34.261% | **1.073x** |
| EURUSD | 40,537,348 | 15,813,261 | 39.009% | 33.380% | **1.169x** |

Counts here begin from the run that added this table, so they cover the later cells rather than the whole campaign; the lift ratio is unaffected because both columns cover the same cells.

**The effective sample size is CELLS, not configurations.** Inside one cell, hundreds of millions of configurations share the same bars and heavily overlapping conditions, so they are nowhere near independent tests. A market-level lift of 1.14 means nothing unless the cells inside that market agree. The spread below is the honest error bar.

| market | cells | mean per-cell lift | worst cell | best cell |
|---|---|---|---|---|
| CL | 3 | **1.112x** | 1.009x | 1.228x |
| RTY | 3 | **1.020x** | 0.954x | 1.072x |
| NQ | 2 | **0.912x** | 0.884x | 0.940x |
| ES | 2 | **0.986x** | 0.939x | 1.034x |
| YM | 2 | **1.070x** | 1.069x | 1.071x |
| HG | 1 | **1.073x** | 1.073x | 1.073x |
| EURUSD | 1 | **1.169x** | 1.169x | 1.169x |

Across all 14 cells: mean lift **1.041x**, spread 0.884x to 1.228x, and 10/14 cells above 1.0 (a coin would give 7). If the count of cells above 1.0 is near half and the spread straddles 1.0, the market-level numbers above are cell noise, not structure.

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 4,097,590,410 | **266,775,622** | 6.511% |
| shifted null | 4,097,590,410 | 258,758,885 | 6.315% |

Lift over chance: **1.03x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+197.171** | $+215.869 | $+197.171 | NQ K=4000 h=21 NQZ5.parquet | `L acc34<-0.0 & exp34>0.0 & vwapd<-1.35` |
| **$+192.376** | $+192.376 | $+199.077 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vratio<-0.67 & vwapd<-0.67` |
| **$+183.211** | $+188.141 | $+183.211 | NQ K=4000 h=21 NQZ5.parquet | `L vmom34<-0.67 & exp34>0.0 & vwapd<-1.35` |
| **$+176.778** | $+225.340 | $+176.778 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & mom89<-0.0 & vel89<-1.35` |
| **$+176.778** | $+222.485 | $+176.778 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & vmom89<-0.0 & vel89<-1.35` |
| **$+174.490** | $+198.089 | $+174.490 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & acc89<-0.0 & vel89<-1.35` |
| **$+171.742** | $+171.742 | $+192.851 | CL K=1000 h=21 CLM6.parquet | `S acc34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+171.018** | $+178.702 | $+171.018 | CL K=1000 h=21 CLM6.parquet | `S eff34<-0.67 & exp34>0.67 & volst>0.0` |
| **$+170.496** | $+214.803 | $+170.496 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & mom89<-0.0 & vel89<-1.35` |
| **$+170.496** | $+211.605 | $+170.496 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & vmom89<-0.0 & vel89<-1.35` |
| **$+168.962** | $+174.994 | $+168.962 | CL K=1000 h=21 CLM6.parquet | `S mom34<-0.67 & rev89>1.35 & chop89>0.0` |
| **$+168.022** | $+178.715 | $+168.022 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & mom89<-0.0 & dratio>1.35` |
| **$+168.022** | $+176.641 | $+168.022 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & vmom89<-0.0 & dratio>1.35` |
| **$+168.013** | $+169.414 | $+168.013 | NQ K=4000 h=21 NQZ5.parquet | `S aeff13<-0.0 & cmp>1.35 & dratio>0.0` |
| **$+167.459** | $+171.301 | $+167.459 | NQ K=4000 h=21 NQZ5.parquet | `S acc89<-0.0 & barups>0.67 & dratio>1.35` |
| **$+167.138** | $+180.831 | $+167.138 | NQ K=4000 h=21 NQZ5.parquet | `S chop89>0.0 & barvel<-0.0 & cmp>1.35` |
| **$+165.265** | $+174.009 | $+165.265 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & eff89<-0.0 & dratio>1.35` |
| **$+163.945** | $+165.321 | $+163.945 | CL K=1000 h=21 CLM6.parquet | `S pos34<-0.67 & rev89>1.35 & chop89>0.0` |
| **$+163.766** | $+171.901 | $+163.766 | NQ K=4000 h=21 NQZ5.parquet | `S acc89<-0.0 & vel89<-1.35 & barvol<-0.67` |
| **$+163.587** | $+163.587 | $+209.048 | CL K=1000 h=21 CLM6.parquet | `L acc34>0.0 & vpp89<-0.67 & vwapd<-0.0` |
| **$+163.567** | $+163.567 | $+163.754 | CL K=1000 h=21 CLM6.parquet | `S exp34>0.67 & rev89>0.67 & volst>0.0` |
| **$+162.989** | $+168.922 | $+162.989 | NQ K=4000 h=21 NQZ5.parquet | `S vmom34>0.0 & chop34>0.67 & vratio<-0.67` |
| **$+162.057** | $+162.057 | $+174.182 | NQ K=4000 h=21 NQZ5.parquet | `S vel34<-0.67 & eff89<-0.67 & vel89<-0.67` |
| **$+161.968** | $+222.057 | $+161.968 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & mom89<-0.0 & dratio>1.35` |
| **$+161.968** | $+217.461 | $+161.968 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & vmom89<-0.0 & dratio>1.35` |
| **$+161.646** | $+161.646 | $+163.945 | CL K=1000 h=21 CLM6.parquet | `S upl34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+161.521** | $+161.521 | $+194.429 | NQ K=4000 h=21 NQZ5.parquet | `S exp34>0.0 & exp89<-0.67 & barvel<-0.0` |
| **$+161.209** | $+161.646 | $+161.209 | CL K=1000 h=21 CLM6.parquet | `S bdn34>0.0 & rev89>1.35 & chop89>0.0` |
| **$+161.086** | $+165.198 | $+161.086 | CL K=1000 h=21 CLM6.parquet | `S pos13<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S vmom89<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S vmom34<-0.67 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S vmom34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & pos89<-0.0 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & eff89<-0.0 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & chop89>0.0 & upl89<-0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & chop89>0.0 & fail89<-0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & chop89>0.0 & dnh89<-0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & chop89>0.0 & brk89<-0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & chop89>0.0 & bdn89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>0.67 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev34>0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S pos34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S mom34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S fail34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S fail13<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S eff34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S dnh34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+168.045 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S brk34<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+166.928 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev34>0.67 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+166.327 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S brk13<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+165.631 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S dnh13<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+160.233** | $+161.646 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S rev89>1.35 & pos89<-0.67 & chop89>0.0` |
| **$+160.233** | $+161.646 | $+160.233 | CL K=1000 h=21 CLM6.parquet | `S mom89<-0.0 & rev89>1.35 & chop89>0.0` |
| **$+159.388** | $+170.512 | $+159.388 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & acc89<-0.0 & dratio>1.35` |
| **$+159.363** | $+159.363 | $+185.368 | NQ K=4000 h=21 NQZ5.parquet | `S aeff13<-0.0 & barvel<-0.0 & cmp>1.35` |
| **$+159.320** | $+178.884 | $+159.320 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & barvel<-0.0 & cmp>1.35` |
| **$+158.860** | $+163.243 | $+158.860 | NQ K=4000 h=21 NQZ5.parquet | `S aeff13<-0.0 & vel89<-0.0 & cmp>1.35` |
| **$+158.534** | $+170.690 | $+158.534 | NQ K=4000 h=21 NQZ5.parquet | `S eff34>0.0 & chop34>0.67 & vratio<-0.67` |

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

Conditions per cell: 592-621 (median 616).

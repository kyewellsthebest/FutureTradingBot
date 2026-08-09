Resumed: 16,936,068,408 evaluated, 55 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- NQ K=4000 `NQZ4.parquet`: 5,044 bars, 617 conditions, **313,179,328** distinct [203s, total 17,249,247,736 eval / 3,325,098,822 scored]
- NQ K=4000 `NQZ5.parquet`: 5,950 bars, 620 conditions, **317,769,840** distinct [533s, total 17,567,017,576 eval / 3,398,522,224 scored]
- ES K=4000 `ESZ4.parquet`: 5,721 bars, 615 conditions, **310,143,680** distinct [850s, total 17,877,161,256 eval / 3,464,594,854 scored]
- ES K=6500 `ESZ4.parquet`: 3,521 bars, 592 conditions, **276,632,128** distinct [916s, total 18,153,793,384 eval / 3,503,551,968 scored]

## 18,153,793,384 distinct configurations evaluated; **3,503,551,968 scored** (met the sample-size gate) in 0.25 h

Null: 18,153,793,384 evaluated, 3,503,551,968 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 115 | **31.3%** | **$-22.2332** | 54.2% | $+15.0841 |
| top 1e-05% | >= $+380.076 | 332 | **34.3%** | **$-28.0079** | - | - |
| top 0.0001% | >= $+324.057 | 3,438 | **18.3%** | **$-51.9727** | 57.4% | $+11.1232 |
| top 0.001% | >= $+231.293 | 34,545 | **29.9%** | **$-50.5724** | 58.9% | $+24.7029 |
| top 0.01% | >= $+159.613 | 344,856 | **41.6%** | **$-21.3962** | 59.0% | $+34.7309 |
| top 0.1% | >= $+96.905 | 3,476,510 | **42.9%** | **$-16.8169** | 54.9% | $+24.1178 |
| top 1% | >= $+41.014 | 34,996,134 | **43.0%** | **$-11.5085** | 48.4% | $+6.0169 |
| top 10% | >= $+8.689 | 350,313,389 | **55.7%** | **$-0.5337** | 54.2% | $+1.9967 |
| top 100% | >= $-402.429 | 3,503,551,968 | **50.0%** | **$-0.0000** | 50.0% | $+0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market — is the pooled number hiding one live market?

Mean dollars per market is identically zero by construction: every configuration is scored alongside its short mirror, so the two cancel. The informative per-market number is the survivor rate against that market's OWN shifted null, because a single market with real structure would show a lift here even when the pooled figure sits at 1.0.

| market | scored (this run) | made money both halves | rate | NULL rate | lift |
|---|---|---|---|---|---|
| NQ | 133,560,240 | 33,249,178 | 24.895% | 27.285% | **0.912x** |
| ES | 105,029,744 | 34,486,020 | 32.835% | 33.809% | **0.971x** |

Counts here begin from the run that added this table, so they cover the later cells rather than the whole campaign; the lift ratio is unaffected because both columns cover the same cells.

**The effective sample size is CELLS, not configurations.** Inside one cell, hundreds of millions of configurations share the same bars and heavily overlapping conditions, so they are nowhere near independent tests. A market-level lift of 1.14 means nothing unless the cells inside that market agree. The spread below is the honest error bar.

| market | cells | mean per-cell lift | worst cell | best cell |
|---|---|---|---|---|
| NQ | 2 | **0.912x** | 0.884x | 0.940x |
| ES | 2 | **0.986x** | 0.939x | 1.034x |

Across all 4 cells: mean lift **0.949x**, spread 0.884x to 1.034x, and 1/4 cells above 1.0 (a coin would give 2). If the count of cells above 1.0 is near half and the spread straddles 1.0, the market-level numbers above are cell noise, not structure.

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 3,503,551,968 | **67,735,198** | 1.933% |
| shifted null | 3,503,551,968 | 71,951,502 | 2.054% |

Lift over chance: **0.94x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+197.171** | $+215.869 | $+197.171 | NQ K=4000 h=21 NQZ5.parquet | `L acc34<-0.0 & exp34>0.0 & vwapd<-1.35` |
| **$+192.376** | $+192.376 | $+199.077 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vratio<-0.67 & vwapd<-0.67` |
| **$+183.211** | $+188.141 | $+183.211 | NQ K=4000 h=21 NQZ5.parquet | `L vmom34<-0.67 & exp34>0.0 & vwapd<-1.35` |
| **$+176.778** | $+225.340 | $+176.778 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & mom89<-0.0 & vel89<-1.35` |
| **$+176.778** | $+222.485 | $+176.778 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & vmom89<-0.0 & vel89<-1.35` |
| **$+174.490** | $+198.089 | $+174.490 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & acc89<-0.0 & vel89<-1.35` |
| **$+170.496** | $+214.803 | $+170.496 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & mom89<-0.0 & vel89<-1.35` |
| **$+170.496** | $+211.605 | $+170.496 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & vmom89<-0.0 & vel89<-1.35` |
| **$+168.022** | $+178.715 | $+168.022 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & mom89<-0.0 & dratio>1.35` |
| **$+168.022** | $+176.641 | $+168.022 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & vmom89<-0.0 & dratio>1.35` |
| **$+168.013** | $+169.414 | $+168.013 | NQ K=4000 h=21 NQZ5.parquet | `S aeff13<-0.0 & cmp>1.35 & dratio>0.0` |
| **$+167.459** | $+171.301 | $+167.459 | NQ K=4000 h=21 NQZ5.parquet | `S acc89<-0.0 & barups>0.67 & dratio>1.35` |
| **$+167.138** | $+180.831 | $+167.138 | NQ K=4000 h=21 NQZ5.parquet | `S chop89>0.0 & barvel<-0.0 & cmp>1.35` |
| **$+165.265** | $+174.009 | $+165.265 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & eff89<-0.0 & dratio>1.35` |
| **$+163.766** | $+171.901 | $+163.766 | NQ K=4000 h=21 NQZ5.parquet | `S acc89<-0.0 & vel89<-1.35 & barvol<-0.67` |
| **$+162.989** | $+168.922 | $+162.989 | NQ K=4000 h=21 NQZ5.parquet | `S vmom34>0.0 & chop34>0.67 & vratio<-0.67` |
| **$+162.057** | $+162.057 | $+174.182 | NQ K=4000 h=21 NQZ5.parquet | `S vel34<-0.67 & eff89<-0.67 & vel89<-0.67` |
| **$+161.968** | $+222.057 | $+161.968 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & mom89<-0.0 & dratio>1.35` |
| **$+161.968** | $+217.461 | $+161.968 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & vmom89<-0.0 & dratio>1.35` |
| **$+161.521** | $+161.521 | $+194.429 | NQ K=4000 h=21 NQZ5.parquet | `S exp34>0.0 & exp89<-0.67 & barvel<-0.0` |
| **$+159.388** | $+170.512 | $+159.388 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & acc89<-0.0 & dratio>1.35` |
| **$+159.363** | $+159.363 | $+185.368 | NQ K=4000 h=21 NQZ5.parquet | `S aeff13<-0.0 & barvel<-0.0 & cmp>1.35` |
| **$+159.320** | $+178.884 | $+159.320 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & barvel<-0.0 & cmp>1.35` |
| **$+158.860** | $+163.243 | $+158.860 | NQ K=4000 h=21 NQZ5.parquet | `S aeff13<-0.0 & vel89<-0.0 & cmp>1.35` |
| **$+158.534** | $+170.690 | $+158.534 | NQ K=4000 h=21 NQZ5.parquet | `S eff34>0.0 & chop34>0.67 & vratio<-0.67` |
| **$+158.435** | $+219.393 | $+158.435 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & mom89<-0.0 & vel89<-1.35` |
| **$+158.435** | $+217.513 | $+158.435 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vmom89<-0.0 & vel89<-1.35` |
| **$+158.022** | $+158.146 | $+158.022 | NQ K=4000 h=21 NQZ5.parquet | `S chop89>0.0 & cmp>1.35 & dratio>0.0` |
| **$+157.989** | $+165.220 | $+157.989 | NQ K=4000 h=21 NQZ5.parquet | `S vpp5<-0.0 & acc89<-0.0 & vel89<-1.35` |
| **$+157.682** | $+184.051 | $+157.682 | NQ K=4000 h=21 NQZ5.parquet | `S rev89<-0.0 & exp89<-0.67 & vratio<-0.67` |
| **$+155.317** | $+226.556 | $+155.317 | NQ K=4000 h=21 NQZ5.parquet | `S chop13>0.0 & eff89<-0.0 & vel89<-1.35` |
| **$+154.394** | $+154.394 | $+186.911 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.67 & exp34>0.0 & exp89<-0.67` |
| **$+154.346** | $+154.346 | $+164.510 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & mom89<-0.0 & dratio>1.35` |
| **$+154.042** | $+164.240 | $+154.042 | NQ K=4000 h=21 NQZ5.parquet | `S pos89<-0.0 & acc89<-0.0 & vel89<-1.35` |
| **$+153.844** | $+239.254 | $+153.844 | NQ K=4000 h=21 NQZ5.parquet | `L mom34<-1.35 & dnh89<-0.67 & vwapd<-1.35` |
| **$+153.844** | $+239.254 | $+153.844 | NQ K=4000 h=21 NQZ5.parquet | `L mom34<-1.35 & brk89<-0.67 & vwapd<-1.35` |
| **$+153.703** | $+155.391 | $+153.703 | NQ K=4000 h=21 NQZ5.parquet | `S acc34>0.0 & eff89<-0.67 & barpath>0.67` |
| **$+153.262** | $+161.509 | $+153.262 | NQ K=4000 h=21 NQZ5.parquet | `L exp34>0.0 & brk34<-0.67 & vwapd<-1.35` |
| **$+153.119** | $+153.119 | $+153.839 | NQ K=4000 h=21 NQZ5.parquet | `S vel13>0.0 & eff89>0.0 & vdir89<-0.0` |
| **$+152.647** | $+213.068 | $+152.647 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & eff89<-0.0 & vel89<-1.35` |
| **$+152.617** | $+161.274 | $+152.617 | NQ K=4000 h=21 NQZ4.parquet | `L bdn13<-0.0 & aeff34<-0.0 & chop34>1.35` |
| **$+152.521** | $+179.455 | $+152.521 | NQ K=4000 h=21 NQZ5.parquet | `S vel34<-0.67 & vmom89<-0.67 & vel89<-0.67` |
| **$+152.069** | $+152.069 | $+157.926 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & mom89<-0.0 & dratio>1.35` |
| **$+152.058** | $+164.420 | $+152.058 | NQ K=4000 h=21 NQZ5.parquet | `S pos89>0.0 & exp89<-0.67 & vratio<-0.67` |
| **$+151.686** | $+151.686 | $+153.858 | NQ K=4000 h=21 NQZ5.parquet | `S eff89<-0.67 & vel89<-0.67 & run89<-0.67` |
| **$+151.527** | $+151.527 | $+164.510 | NQ K=4000 h=21 NQZ5.parquet | `S chop5>0.0 & vmom89<-0.0 & dratio>1.35` |
| **$+151.090** | $+151.090 | $+165.646 | NQ K=4000 h=21 NQZ5.parquet | `S absb34<-0.67 & acc89<-0.0 & vel89<-1.35` |
| **$+151.058** | $+155.297 | $+151.058 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & run89<-0.67 & barvol<-0.67` |
| **$+150.914** | $+150.914 | $+161.090 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & cmp>1.35 & dratio>0.0` |
| **$+150.819** | $+150.819 | $+154.457 | NQ K=4000 h=21 NQZ5.parquet | `S absb34<-0.67 & mom89<-0.0 & dratio>1.35` |
| **$+150.792** | $+191.561 | $+150.792 | NQ K=4000 h=21 NQZ5.parquet | `S chop34>0.0 & cmp>1.35 & dratio>0.0` |
| **$+150.652** | $+150.652 | $+157.926 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vmom89<-0.0 & dratio>1.35` |
| **$+150.350** | $+177.115 | $+150.350 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & mom89<-0.0 & barvel<-1.35` |
| **$+149.845** | $+149.845 | $+152.457 | NQ K=4000 h=21 NQZ5.parquet | `S volz34<-0.67 & acc89<-0.0 & vel89<-1.35` |
| **$+149.755** | $+149.755 | $+156.978 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vel89<-0.0 & cmp>1.35` |
| **$+149.656** | $+179.268 | $+149.656 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & volz89<-0.67 & vwapd<-0.67` |
| **$+149.647** | $+149.647 | $+161.538 | NQ K=4000 h=21 NQZ5.parquet | `S acc89<-0.0 & vel89<-1.35 & absb89<-0.67` |
| **$+149.371** | $+194.838 | $+149.371 | NQ K=4000 h=21 NQZ5.parquet | `L mom34<-0.67 & exp34>0.0 & vwapd<-1.35` |
| **$+149.215** | $+149.215 | $+167.246 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & barvel<-0.0 & cmp>1.35` |
| **$+148.796** | $+175.306 | $+148.796 | NQ K=4000 h=21 NQZ5.parquet | `S aeff34<-0.0 & vmom89<-0.0 & barvel<-1.35` |

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

Conditions per cell: 592-620 (median 616).

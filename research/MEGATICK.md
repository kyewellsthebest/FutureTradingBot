# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- NQ K=4000 `NQH5.parquet`: 6,206 bars, 623 conditions, **322,404,992** distinct [244s, total 322,404,992 eval / 67,260,794 scored]
- ES K=6500 `ESH5.parquet`: 5,273 bars, 601 conditions, **289,441,600** distinct [433s, total 611,846,592 eval / 122,565,972 scored]
- GC K=650 `GCM6.parquet`: 6,017 bars, 624 conditions, **323,960,000** distinct [708s, total 935,806,592 eval / 192,372,580 scored]
- CL K=400 `CLH5.parquet`: 6,663 bars, 626 conditions, **327,085,000** distinct [986s, total 1,262,891,592 eval / 270,793,490 scored]
- RTY K=1000 `RTYH5.parquet`: 5,590 bars, 612 conditions, **305,627,088** distinct [1140s, total 1,568,518,680 eval / 333,211,974 scored]
- YM K=1000 `YMH5.parquet`: 4,919 bars, 614 conditions, **308,633,240** distinct [1251s, total 1,877,151,920 eval / 387,061,400 scored]
- HG K=250 `HGZ4.parquet`: 5,783 bars, 619 conditions, **316,234,720** distinct [1431s, total 2,193,386,640 eval / 456,812,298 scored]
- EURUSD K=100 `EURUSD_202512.parquet`: 5,636 bars, 623 conditions, **322,404,992** distinct [1593s, total 2,515,791,632 eval / 526,619,296 scored]

## 2,515,791,632 distinct configurations evaluated; **526,619,296 scored** (met the sample-size gate) in 0.44 h

Null: 2,515,791,632 evaluated, 526,619,296 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 37 | **32.4%** | **$-8.5217** | 6.4% | $-112.9628 |
| top 1e-05% | >= $+394.045 | 52 | **36.5%** | **$-6.2735** | 5.9% | $-114.0461 |
| top 0.0001% | >= $+357.884 | 526 | **22.6%** | **$-10.5574** | 13.7% | $-101.6491 |
| top 0.001% | >= $+253.933 | 5,237 | **40.5%** | **$+1.2081** | 27.3% | $-60.8689 |
| top 0.01% | >= $+166.001 | 52,526 | **54.5%** | **$+7.4794** | 32.6% | $-43.7180 |
| top 0.1% | >= $+102.959 | 524,285 | **49.3%** | **$-3.8707** | 39.9% | $-20.6903 |
| top 1% | >= $+43.880 | 5,260,028 | **44.0%** | **$-9.3529** | 42.4% | $-10.0896 |
| top 10% | >= $+8.318 | 52,479,559 | **47.0%** | **$-3.5652** | 42.3% | $-4.6265 |
| top 100% | >= $-402.429 | 526,619,296 | **50.0%** | **$+0.0000** | 50.0% | $-0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market

| market | scored configs | avg train $ | avg holdout $ | NULL holdout $ |
|---|---|---|---|---|
| CL | 78,420,910 | $+0.0000 | $+0.0000 | $+0.0000 |
| EURUSD | 69,806,998 | $+0.0000 | $+0.0000 | $+0.0000 |
| GC | 69,806,608 | $+0.0000 | $+0.0000 | $+0.0000 |
| HG | 69,750,898 | $+0.0000 | $+0.0000 | $+0.0000 |
| NQ | 67,260,794 | $+0.0000 | $+0.0000 | $+0.0000 |
| RTY | 62,418,484 | $+0.0000 | $+0.0000 | $+0.0000 |
| ES | 55,305,178 | $+0.0000 | $+0.0000 | $+0.0000 |
| YM | 53,849,426 | $+0.0000 | $+0.0000 | $+0.0000 |

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 526,619,296 | **177,290,080** | 33.666% |
| shifted null | 526,619,296 | 169,169,872 | 32.124% |

Lift over chance: **1.05x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+211.954** | $+211.954 | $+223.540 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & vpp89<-0.0 & vwapd<-0.67` |
| **$+203.549** | $+203.549 | $+216.717 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & vpp34<-0.0 & vwapd<-0.67` |
| **$+203.426** | $+203.743 | $+203.426 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & vpp34<-0.0 & mom89<-0.67` |
| **$+193.008** | $+193.008 | $+238.009 | GC K=650 h=21 GCM6.parquet | `S vpp13>0.67 & chop34>0.0 & run89>0.0` |
| **$+192.784** | $+204.757 | $+192.784 | GC K=650 h=21 GCM6.parquet | `L mom34<-0.67 & exp34>0.67 & vpp34<-0.0` |
| **$+192.158** | $+192.158 | $+201.931 | GC K=650 h=21 GCM6.parquet | `S chop34>0.0 & aeff89>0.67 & vwapd>0.0` |
| **$+190.557** | $+213.551 | $+190.557 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & pos89<-0.67 & vpp89<-0.0` |
| **$+189.418** | $+189.418 | $+206.196 | GC K=650 h=21 GCM6.parquet | `L vmom34<-0.0 & chop34>0.0 & vpp34<-0.67` |
| **$+188.969** | $+188.969 | $+203.243 | GC K=650 h=21 GCM6.parquet | `L mom34<-0.0 & chop34>0.0 & vpp34<-0.67` |
| **$+188.523** | $+188.523 | $+209.537 | GC K=650 h=21 GCM6.parquet | `S vpp13>0.67 & chop34>0.0 & vdir89>0.0` |
| **$+188.196** | $+188.196 | $+201.931 | GC K=650 h=21 GCM6.parquet | `S chop34>0.0 & aeff89>0.67 & bdn89<-0.0` |
| **$+187.865** | $+265.648 | $+187.865 | GC K=650 h=21 GCM6.parquet | `L vpp34<-0.67 & chop89>0.0 & vwapd<-0.0` |
| **$+187.755** | $+187.755 | $+199.154 | GC K=650 h=21 GCM6.parquet | `L eff34<-0.0 & chop34>0.0 & vpp34<-0.67` |
| **$+187.542** | $+197.741 | $+187.542 | GC K=650 h=21 GCM6.parquet | `L aeff34>0.0 & exp34>1.35 & mom89<-0.67` |
| **$+186.869** | $+191.538 | $+186.869 | GC K=650 h=21 GCM6.parquet | `L chop34>0.0 & bdn89>0.67 & cmp>0.67` |
| **$+186.869** | $+187.903 | $+186.869 | GC K=650 h=21 GCM6.parquet | `L chop34>0.0 & upl89<-0.67 & cmp>0.67` |
| **$+186.298** | $+186.298 | $+201.931 | GC K=650 h=21 GCM6.parquet | `S chop34>0.0 & aeff89>0.67 & upl89>0.0` |
| **$+186.118** | $+186.118 | $+234.416 | GC K=650 h=21 GCM6.parquet | `S vpp13>0.67 & chop89>0.0 & run89>0.0` |
| **$+185.860** | $+185.860 | $+202.796 | GC K=650 h=21 GCM6.parquet | `S exp13>0.0 & run89>0.0 & barvel<-0.67` |
| **$+185.827** | $+188.744 | $+185.827 | GC K=650 h=21 GCM6.parquet | `L absb13<-0.0 & exp34>0.67 & mom89<-0.67` |
| **$+185.522** | $+202.935 | $+185.522 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & rev89>0.67 & vpp89<-0.0` |
| **$+185.412** | $+200.858 | $+185.412 | GC K=650 h=21 GCM6.parquet | `L chop34>0.0 & vpp34<-0.67 & vwapd<-0.0` |
| **$+185.335** | $+185.335 | $+185.615 | GC K=650 h=21 GCM6.parquet | `L vpp34<-0.67 & pthz89>0.0 & vwapd<-0.0` |
| **$+185.323** | $+185.323 | $+213.004 | GC K=650 h=21 GCM6.parquet | `S vpp13>0.67 & vdir89>0.0 & dratio>0.67` |
| **$+185.172** | $+197.789 | $+185.172 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & mom89<-0.67 & absb89<-0.0` |
| **$+184.357** | $+184.357 | $+246.696 | GC K=650 h=21 GCM6.parquet | `S vpp13>0.67 & run89>0.0 & dratio>0.67` |
| **$+183.895** | $+183.895 | $+195.043 | GC K=650 h=21 GCM6.parquet | `S vpp13>0.67 & chop89>0.0 & vdir89>0.0` |
| **$+182.817** | $+221.520 | $+182.817 | GC K=650 h=21 GCM6.parquet | `S pthz34>0.0 & vmom89>0.67 & dratio>0.67` |
| **$+182.230** | $+243.842 | $+182.230 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & brk89<-0.67 & vpp89<-0.0` |
| **$+182.230** | $+241.859 | $+182.230 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & dnh89<-0.67 & vpp89<-0.0` |
| **$+181.130** | $+207.322 | $+181.130 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & vpp89<-0.0 & vwapd<-0.0` |
| **$+180.096** | $+229.142 | $+180.096 | GC K=650 h=21 GCM6.parquet | `L eff34<-0.67 & chop34>0.0 & cmp>0.67` |
| **$+179.940** | $+179.940 | $+201.110 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & absb34<-0.0 & mom89<-0.67` |
| **$+179.732** | $+179.732 | $+201.931 | GC K=650 h=21 GCM6.parquet | `S chop34>0.0 & rev89<-0.0 & aeff89>0.67` |
| **$+179.560** | $+191.610 | $+179.560 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & volz34<-0.0 & mom89<-0.67` |
| **$+179.538** | $+179.538 | $+209.759 | GC K=650 h=21 GCM6.parquet | `S vpp34>0.0 & vdir89>0.0 & dratio>1.35` |
| **$+178.666** | $+181.751 | $+178.666 | GC K=650 h=21 GCM6.parquet | `L chop34>0.0 & vpp34<-0.67 & mom89<-0.0` |
| **$+178.328** | $+184.282 | $+178.328 | GC K=650 h=21 GCM6.parquet | `L chop34>0.0 & vpp34<-0.67 & vmom89<-0.0` |
| **$+178.328** | $+181.751 | $+178.328 | GC K=650 h=21 GCM6.parquet | `L chop34>0.0 & vpp34<-0.67 & eff89<-0.0` |
| **$+177.959** | $+237.925 | $+177.959 | GC K=650 h=21 GCM6.parquet | `L exp34>0.67 & vmom89<-0.67 & vpp89<-0.0` |
| **$+177.906** | $+196.299 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L vmom34<-0.67 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+193.602 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & vmom89<-0.67` |
| **$+177.906** | $+192.518 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L eff34<-0.67 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+190.757 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & vwapd<-0.0` |
| **$+177.906** | $+186.599 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L fail13<-0.0 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L vmom34<-0.0 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L rev34>0.0 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L pos34<-0.0 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L mom34<-0.0 & exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & vmom89<-0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & rev89>0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & rev89>0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & pos89<-0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & fail89<-0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & eff89<-0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & dnh89<-0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67 & brk89<-0.0` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & mom89<-0.0 & mom89<-0.67` |
| **$+177.906** | $+182.507 | $+177.906 | GC K=650 h=21 GCM6.parquet | `L exp34>1.35 & fail34<-0.0 & mom89<-0.67` |

### The best training scores, and what each did out of sample

| train $/trade | HOLDOUT $/trade | rule |
|---|---|---|
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
| $+402.694 | $-32.614 | `L vmom13<-0.67 & aeff34>1.35 & vdir34<-0.67` |
| $+402.101 | $+20.577 | `L eff34<-1.35 & bdn34>0.67 & vpp34<-0.0` |
| $+401.493 | $-37.768 | `L run13<-0.67 & aeff34>1.35 & run34<-0.67` |
| $+400.856 | $+21.188 | `L eff34<-1.35 & vpp34<-0.0 & vdir34<-0.0` |
| $+400.856 | $+21.188 | `L eff34<-1.35 & vpp34<-0.0 & run34<-0.0` |
| $+400.746 | $-28.066 | `L vdir13<-0.0 & aeff34>1.35 & vdir34<-0.67` |

Conditions per cell: 601-626 (median 621).

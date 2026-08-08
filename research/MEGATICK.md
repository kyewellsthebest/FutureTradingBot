Resumed: 2,515,791,632 evaluated, 8 cells done.
# MEGATICK — five billion distinct configurations in tick-event space

Bars close every K price prints; the clock is never a bar rule. Outcomes are de-drifted per split, charged real costs, and measured in **net dollars per trade on one micro contract**. The floor is the identical search run on a circularly-shifted outcome series — same autocorrelation, same sample sizes, no alignment with the signal.

Vocabulary: 4 event-horizons x ~24 behavioural families + 18 bar-local questions, each asked at 3 strengths in 2 directions. Holds: [1, 3, 8, 21] bars. 193 (contract x bar-size) cells available, visited round-robin across markets so breadth arrives before depth.

Sizing: one micro futures contract per market. FX at $1 per pip (10k notional), gold at 10 oz — FX and gold are research-only, since the account cannot trade them; they exist here to test whether a behaviour transfers across markets.

- NQ K=6500 `NQH5.parquet`: 3,819 bars, 606 conditions, **296,725,880** distinct [93s, total 2,812,517,512 eval / 566,574,910 scored]

## 2,812,517,512 distinct configurations evaluated; **566,574,910 scored** (met the sample-size gate) in 0.03 h

Null: 2,812,517,512 evaluated, 566,574,910 scored — the identical search on circularly-shifted outcomes, so the columns below are directly comparable.

### What the whole population did, and what the null did

| selection | train cut | kept | % that made money OOS | avg OOS $/trade | NULL % | NULL avg $ |
|---|---|---|---|---|---|---|
| top 1e-07% | >= $+401.220 | 37 | **32.4%** | **$-8.5217** | 6.4% | $-112.9628 |
| top 1e-05% | >= $+394.045 | 52 | **36.5%** | **$-6.2735** | 5.4% | $-116.6370 |
| top 0.0001% | >= $+354.669 | 565 | **24.4%** | **$-7.5375** | 15.8% | $-98.0878 |
| top 0.001% | >= $+250.892 | 5,660 | **41.0%** | **$+1.3332** | 27.3% | $-58.4704 |
| top 0.01% | >= $+168.017 | 56,534 | **53.9%** | **$+7.7503** | 35.8% | $-33.1916 |
| top 0.1% | >= $+107.094 | 564,434 | **48.5%** | **$-3.0845** | 47.0% | $-8.2091 |
| top 1% | >= $+48.254 | 5,645,393 | **42.6%** | **$-10.4055** | 47.0% | $-3.2409 |
| top 10% | >= $+9.105 | 56,581,907 | **45.5%** | **$-4.5497** | 43.6% | $-3.3895 |
| top 100% | >= $-402.429 | 566,574,910 | **50.0%** | **$-0.0000** | 50.0% | $+0.0000 |

Read the last two columns first. If the real search cannot beat the shifted one, the pattern is the calendar and not the market.

### Per market

| market | scored configs | avg train $ | avg holdout $ | NULL holdout $ |
|---|---|---|---|---|
| NQ | 107,216,408 | $+0.0000 | $+0.0000 | $+0.0000 |
| CL | 78,420,910 | $+0.0000 | $+0.0000 | $+0.0000 |
| EURUSD | 69,806,998 | $+0.0000 | $+0.0000 | $+0.0000 |
| GC | 69,806,608 | $+0.0000 | $+0.0000 | $+0.0000 |
| HG | 69,750,898 | $+0.0000 | $+0.0000 | $+0.0000 |
| RTY | 62,418,484 | $+0.0000 | $+0.0000 | $+0.0000 |
| ES | 55,305,178 | $+0.0000 | $+0.0000 | $+0.0000 |
| YM | 53,849,426 | $+0.0000 | $+0.0000 | $+0.0000 |

### The screen that actually matters: profitable on BOTH halves

| | configs scored | made money on both halves | rate |
|---|---|---|---|
| **real search** | 566,574,910 | **9,405,791** | 1.660% |
| shifted null | 566,574,910 | 9,954,568 | 1.757% |

Lift over chance: **0.94x**. A lift near 1.0 means the survivors are what shuffling produces anyway — that is the honest reading of a long list of profitable-looking rules, and it is why the count alone is never the answer.

Survivors ranked by their WORSE half, so nothing qualifies on one good split:

| worse half $/trade | train $ | holdout $ | market / bar / hold | rule |
|---|---|---|---|---|
| **$+210.078** | $+217.019 | $+210.078 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & bdn89>0.67 & vel89>0.0` |
| **$+210.078** | $+213.090 | $+210.078 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & upl89<-0.67 & vel89>0.0` |
| **$+202.932** | $+204.720 | $+202.932 | NQ K=6500 h=21 NQH5.parquet | `L vmom34<-0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+202.932** | $+204.720 | $+202.932 | NQ K=6500 h=21 NQH5.parquet | `L eff34<-0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+201.344** | $+201.344 | $+213.683 | NQ K=6500 h=21 NQH5.parquet | `S upl13<-0.67 & chop89<-0.0 & dratio>0.0` |
| **$+195.735** | $+198.522 | $+195.735 | NQ K=6500 h=21 NQH5.parquet | `L eff89<-1.35 & bdn89>0.67 & dratio<-0.0` |
| **$+195.735** | $+197.000 | $+195.735 | NQ K=6500 h=21 NQH5.parquet | `L pos89<-0.67 & eff89<-1.35 & dratio<-0.0` |
| **$+195.468** | $+195.468 | $+217.973 | NQ K=6500 h=21 NQH5.parquet | `L rev89>0.67 & eff89<-1.35 & dratio<-0.0` |
| **$+195.283** | $+195.283 | $+195.735 | NQ K=6500 h=21 NQH5.parquet | `L eff89<-1.35 & upl89<-0.67 & dratio<-0.0` |
| **$+194.850** | $+194.850 | $+211.095 | NQ K=6500 h=21 NQH5.parquet | `L mom34<-0.0 & mom89<-1.35 & vel89>0.0` |
| **$+191.411** | $+191.411 | $+192.589 | NQ K=6500 h=21 NQH5.parquet | `L vpp13<-0.0 & mom89<-1.35 & rev89>0.67` |
| **$+191.045** | $+191.045 | $+212.518 | NQ K=6500 h=21 NQH5.parquet | `L bdn34>0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+190.856** | $+202.040 | $+190.856 | NQ K=6500 h=21 NQH5.parquet | `L mom34<-0.0 & vpp34<-0.67 & vwapd<-0.67` |
| **$+190.773** | $+190.773 | $+210.078 | NQ K=6500 h=21 NQH5.parquet | `L vmom34<-0.0 & mom89<-1.35 & vel89>0.0` |
| **$+190.773** | $+190.773 | $+210.078 | NQ K=6500 h=21 NQH5.parquet | `L eff34<-0.0 & mom89<-1.35 & vel89>0.0` |
| **$+190.259** | $+200.297 | $+190.259 | NQ K=6500 h=21 NQH5.parquet | `L eff34<-0.0 & vpp34<-0.67 & vwapd<-0.67` |
| **$+189.972** | $+189.972 | $+202.932 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & dnh89<-0.0 & dratio<-0.0` |
| **$+189.657** | $+189.657 | $+196.952 | NQ K=6500 h=21 NQH5.parquet | `S bdn5>0.67 & chop89<-0.0 & vel89<-0.0` |
| **$+189.541** | $+189.541 | $+209.818 | NQ K=6500 h=21 NQH5.parquet | `L pos34<-0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+187.857** | $+187.857 | $+195.154 | NQ K=6500 h=21 NQH5.parquet | `L vpp13<-0.0 & vmom34<-0.67 & mom89<-1.35` |
| **$+187.000** | $+187.000 | $+212.518 | NQ K=6500 h=21 NQH5.parquet | `L upl34<-0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+186.421** | $+193.417 | $+186.421 | NQ K=6500 h=21 NQH5.parquet | `S pos13<-0.67 & chop89<-0.0 & dratio>0.0` |
| **$+185.906** | $+185.906 | $+202.932 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & brk89<-0.0 & dratio<-0.0` |
| **$+185.672** | $+185.672 | $+220.419 | NQ K=6500 h=21 NQH5.parquet | `L eff89<-1.35 & bdn89>0.67 & vel89>0.0` |
| **$+184.933** | $+184.933 | $+237.967 | NQ K=6500 h=21 NQH5.parquet | `S bdn5>0.67 & chop89<-0.0 & dratio>0.0` |
| **$+184.874** | $+185.510 | $+184.874 | NQ K=6500 h=21 NQH5.parquet | `L vmom34<-0.67 & mom89<-1.35 & vwapd<-0.67` |
| **$+184.150** | $+200.297 | $+184.150 | NQ K=6500 h=21 NQH5.parquet | `L vmom34<-0.0 & vpp34<-0.67 & vwapd<-0.67` |
| **$+183.970** | $+183.970 | $+213.587 | NQ K=6500 h=21 NQH5.parquet | `L vdir34<-0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+182.925** | $+182.925 | $+220.419 | NQ K=6500 h=21 NQH5.parquet | `L pos89<-0.67 & eff89<-1.35 & vel89>0.0` |
| **$+182.745** | $+182.745 | $+220.419 | NQ K=6500 h=21 NQH5.parquet | `L eff89<-1.35 & upl89<-0.67 & vel89>0.0` |
| **$+181.634** | $+181.634 | $+210.122 | NQ K=6500 h=21 NQH5.parquet | `L run34<-0.0 & mom89<-1.35 & dratio<-0.0` |
| **$+181.260** | $+181.260 | $+219.734 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & barups>0.0 & dratio<-0.0` |
| **$+179.762** | $+179.762 | $+227.503 | NQ K=6500 h=21 NQH5.parquet | `S eff5<-0.67 & chop89<-0.0 & vel89<-0.0` |
| **$+179.585** | $+179.585 | $+197.224 | NQ K=6500 h=21 NQH5.parquet | `L mom34<-0.0 & eff89<-1.35 & dratio<-0.0` |
| **$+178.743** | $+178.743 | $+197.412 | NQ K=6500 h=21 NQH5.parquet | `S rev13>0.67 & chop89<-0.0 & vel89<-0.0` |
| **$+177.866** | $+177.866 | $+210.078 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & dnh89<-0.0 & vel89>0.0` |
| **$+177.639** | $+177.639 | $+217.236 | NQ K=6500 h=21 NQH5.parquet | `L bdn34>0.0 & mom89<-1.35 & vel89>0.0` |
| **$+177.453** | $+177.453 | $+187.770 | NQ K=6500 h=21 NQH5.parquet | `S bdn5>0.67 & chop34<-0.0 & dratio>0.0` |
| **$+176.956** | $+195.802 | $+176.956 | NQ K=6500 h=21 NQH5.parquet | `L eff34<-0.67 & mom89<-1.35 & vwapd<-0.67` |
| **$+176.757** | $+176.757 | $+219.935 | NQ K=6500 h=21 NQH5.parquet | `L eff89<-1.35 & bdn89>0.67 & barvel>0.0` |
| **$+176.724** | $+176.724 | $+177.834 | NQ K=6500 h=21 NQH5.parquet | `S exp34<-0.0 & dratio>0.67 & volst>0.0` |
| **$+176.617** | $+176.617 | $+215.880 | NQ K=6500 h=21 NQH5.parquet | `L pos34<-0.0 & mom89<-1.35 & vel89>0.0` |
| **$+176.104** | $+176.104 | $+195.735 | NQ K=6500 h=21 NQH5.parquet | `L eff34<-0.0 & eff89<-1.35 & dratio<-0.0` |
| **$+175.959** | $+191.098 | $+175.959 | NQ K=6500 h=21 NQH5.parquet | `L faild5<-0.0 & vmom34<-0.67 & mom89<-1.35` |
| **$+175.926** | $+184.033 | $+175.926 | NQ K=6500 h=21 NQH5.parquet | `L bdn34>0.0 & vpp34<-0.67 & vwapd<-0.67` |
| **$+175.874** | $+188.748 | $+175.874 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & rev89>0.67 & vwapd<-0.67` |
| **$+175.811** | $+191.961 | $+175.811 | NQ K=6500 h=21 NQH5.parquet | `L vpp13<-0.0 & mom89<-1.35 & acc89<-0.67` |
| **$+175.429** | $+175.429 | $+203.626 | NQ K=6500 h=21 NQH5.parquet | `S pos5<-0.67 & chop89<-0.0 & dratio>0.0` |
| **$+175.331** | $+175.331 | $+219.914 | NQ K=6500 h=21 NQH5.parquet | `L brk34<-0.0 & mom89<-1.35 & vel89>0.0` |
| **$+174.642** | $+186.482 | $+174.642 | NQ K=6500 h=21 NQH5.parquet | `L upl34<-0.0 & vpp34<-0.67 & vwapd<-0.67` |
| **$+174.363** | $+174.363 | $+186.469 | NQ K=6500 h=21 NQH5.parquet | `S aeff34<-0.0 & exp34<-0.67 & run89<-0.67` |
| **$+174.363** | $+174.363 | $+184.004 | NQ K=6500 h=21 NQH5.parquet | `S aeff34<-0.0 & exp34<-0.67 & vdir89<-0.67` |
| **$+174.358** | $+174.358 | $+177.561 | NQ K=6500 h=21 NQH5.parquet | `L vpp13<-0.0 & vpp34<-0.0 & vwapd<-1.35` |
| **$+174.093** | $+174.093 | $+217.236 | NQ K=6500 h=21 NQH5.parquet | `L upl34<-0.0 & mom89<-1.35 & vel89>0.0` |
| **$+174.061** | $+174.061 | $+210.078 | NQ K=6500 h=21 NQH5.parquet | `L mom89<-1.35 & brk89<-0.0 & vel89>0.0` |
| **$+174.038** | $+201.236 | $+174.038 | NQ K=6500 h=21 NQH5.parquet | `L mom34<-0.67 & mom89<-1.35 & vwapd<-0.67` |
| **$+173.985** | $+173.985 | $+184.246 | NQ K=6500 h=21 NQH5.parquet | `S exp89<-0.0 & vratio<-0.67 & volst>0.0` |
| **$+173.817** | $+173.817 | $+219.935 | NQ K=6500 h=21 NQH5.parquet | `L pos89<-0.67 & eff89<-1.35 & barvel>0.0` |
| **$+173.812** | $+173.812 | $+191.857 | NQ K=6500 h=21 NQH5.parquet | `L vpp34<-0.0 & eff89<-1.35 & dratio<-0.0` |
| **$+173.767** | $+173.767 | $+219.935 | NQ K=6500 h=21 NQH5.parquet | `L eff89<-1.35 & upl89<-0.67 & barvel>0.0` |

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

Conditions per cell: 606-606 (median 606).

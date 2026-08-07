# FX mega search

Every family, every parameter, on data where a buy pays the ask and a sell pays the bid. Selection on train, reported on holdout, always.

## EURUSD -- 5,607,145 ticks, median spread 0.30 pips

- `tick_500`: 11,214 bars, 33 features, 1,896 configurations scored [2s]
- `tick_2000`: 2,803 bars, 33 features, 1,208 configurations scored [2s]
- `tick_10000`: 560 bars, 33 features, 0 configurations scored [2s]
- `time_600`: 10,871 bars, 33 features, 2,064 configurations scored [3s]

## GBPUSD -- 8,734,162 ticks, median spread 0.70 pips

- `tick_500`: 17,468 bars, 33 features, 2,168 configurations scored [5s]
- `tick_2000`: 4,367 bars, 33 features, 1,179 configurations scored [6s]
- `tick_10000`: 873 bars, 33 features, 0 configurations scored [6s]
- `time_600`: 14,219 bars, 33 features, 2,128 configurations scored [6s]

## USDJPY -- 10,129,402 ticks, median spread 0.40 pips

- `tick_500`: 20,258 bars, 33 features, 2,344 configurations scored [9s]
- `tick_2000`: 5,064 bars, 33 features, 1,352 configurations scored [9s]
- `tick_10000`: 1,012 bars, 33 features, 0 configurations scored [9s]
- `time_600`: 15,191 bars, 33 features, 2,216 configurations scored [10s]

## XAUUSD -- 44,750,796 ticks, median spread 6.70 pips

- `tick_500`: 89,501 bars, 33 features, 2,632 configurations scored [33s]
- `tick_2000`: 22,375 bars, 33 features, 2,352 configurations scored [35s]
- `tick_10000`: 4,475 bars, 33 features, 1,216 configurations scored [36s]
- `time_600`: 17,353 bars, 33 features, 2,183 configurations scored [41s]

**24,938 configurations scored across 4 symbols and 4 bar types, in 41s.**

## Select on train, report holdout

| picked by train | n | median holdout | share positive | best holdout |
|---|---|---|---|---|
| top 0.1% (train >= +134.826) | 25 | -207.6624 | 8.0% | +39.8412 |
| top 1.0% (train >= +50.290) | 253 | -126.8995 | 7.5% | +49.2381 |
| top 5.0% (train >= +7.443) | 1,249 | -32.4616 | 17.5% | +54.0112 |
| top 50.0% (train >= -1.014) | 12,469 | -0.7944 | 20.3% | +165.2245 |

Everything, for reference: median holdout -1.0440 pips, 24.0% positive, 24,938 configurations.

If selection worked, the share positive would climb as the cut gets tighter. In every previous run in this project it fell BELOW the 50% a coin gives -- picking the best training configs picked worse than random ones.

## The 25 best training configurations, and what they did next

| sym | bars | feature | z | dir | hold | n train | n hold | train pips | HOLDOUT pips | $/wk @1 micro |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | tick_10000 | mom100 | 0.75 | -1 | 34 | 379 | 395 | +228.4900 | -11.1345 | -29.32 |
| XAUUSD | tick_10000 | mom100 | 1.0 | -1 | 34 | 306 | 217 | +195.0491 | -45.6586 | -66.05 |
| XAUUSD | tick_10000 | rev5 | 0.75 | +1 | 34 | 819 | 435 | +183.1396 | -181.8453 | -527.35 |
| XAUUSD | tick_10000 | mom200 | 0.25 | +1 | 34 | 1,984 | 202 | +175.2874 | -366.9079 | -494.10 |
| XAUUSD | tick_10000 | vmom200 | 0.25 | +1 | 34 | 2,063 | 295 | +174.6503 | -399.6197 | -785.92 |
| XAUUSD | tick_10000 | rev100 | 1.0 | +1 | 13 | 326 | 331 | +172.6708 | +21.8739 | +48.27 |
| XAUUSD | tick_10000 | rev5 | 1.0 | +1 | 34 | 621 | 323 | +172.4480 | -173.4911 | -373.58 |
| XAUUSD | tick_10000 | rev5 | 0.25 | +1 | 34 | 1,229 | 634 | +163.7274 | -210.8635 | -891.25 |
| XAUUSD | tick_10000 | mom100 | 0.25 | +1 | 34 | 1,647 | 228 | +163.6313 | -181.3426 | -275.64 |
| XAUUSD | tick_10000 | vmom50 | 0.25 | +1 | 34 | 1,734 | 386 | +161.4176 | -404.6158 | -1041.21 |
| XAUUSD | tick_10000 | mom100 | 0.75 | -1 | 21 | 379 | 395 | +160.1830 | -8.3816 | -22.07 |
| XAUUSD | tick_10000 | rev100 | 1.0 | +1 | 21 | 326 | 324 | +159.5100 | +39.8412 | +86.06 |
| XAUUSD | tick_10000 | rev5 | 0.5 | +1 | 34 | 1,025 | 535 | +159.1640 | -196.6675 | -701.45 |
| XAUUSD | tick_10000 | vmom200 | 0.5 | +1 | 34 | 1,908 | 203 | +158.5450 | -425.4495 | -575.77 |
| XAUUSD | tick_10000 | rev10 | 1.0 | +1 | 34 | 526 | 297 | +157.5586 | -124.1677 | -245.85 |
| XAUUSD | tick_10000 | vmom100 | 0.25 | +1 | 34 | 1,814 | 263 | +154.8191 | -260.2559 | -456.32 |
| XAUUSD | tick_10000 | mom100 | 0.5 | +1 | 34 | 1,360 | 141 | +154.8176 | -190.1021 | -178.70 |
| XAUUSD | tick_10000 | vmom10 | 0.25 | +1 | 34 | 1,549 | 496 | +151.5973 | -264.8607 | -875.81 |
| XAUUSD | tick_10000 | vmom5 | 0.25 | +1 | 34 | 1,498 | 486 | +150.6797 | -231.2131 | -749.13 |
| XAUUSD | tick_10000 | rev200 | 0.25 | +1 | 34 | 680 | 790 | +150.0524 | -135.6753 | -714.56 |
| XAUUSD | tick_10000 | vmom100 | 0.5 | +1 | 34 | 1,574 | 211 | +149.5681 | -207.6624 | -292.11 |
| XAUUSD | tick_10000 | gap | 0.75 | +1 | 34 | 213 | 105 | +146.5230 | -217.1078 | -151.98 |
| XAUUSD | tick_10000 | vmom50 | 0.5 | +1 | 34 | 1,539 | 294 | +145.3684 | -360.7907 | -707.15 |
| XAUUSD | tick_10000 | vmom50 | 1.0 | +1 | 34 | 926 | 155 | +143.2822 | -217.9821 | -225.25 |
| XAUUSD | tick_10000 | vmom20 | 0.25 | +1 | 34 | 1,616 | 480 | +140.3301 | -284.3474 | -909.91 |

The last column is the one that matters and it is deliberately generous: it assumes the holdout result repeats, one micro lot, and no slippage beyond the spread already paid.

wrote /home/user/FutureTradingBot/research/FX_MEGA.md

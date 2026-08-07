# FX mega search

Every family, every parameter, on data where a buy pays the ask and a sell pays the bid. Selection on train, reported on holdout, always.

## EURUSD -- 5,607,145 ticks, median spread 0.30 pips

- `tick_1000`: 5,607 bars, 33 features, 1,432 configurations scored [7s]

**1,432 configurations scored across 1 symbols and 1 bar types, in 7s.**

## Select on train, report holdout

| picked by train | n | median holdout | share positive | best holdout |
|---|---|---|---|---|
| top 0.1% (train >= +8.196) | 2 | -6.6452 | 0.0% | -3.4063 |
| top 1.0% (train >= +4.760) | 15 | -6.0484 | 13.3% | +1.7051 |
| top 5.0% (train >= +2.239) | 76 | -1.7672 | 36.8% | +14.1911 |
| top 50.0% (train >= -0.370) | 716 | -0.8940 | 16.6% | +14.1911 |

Everything, for reference: median holdout -0.3938 pips, 31.8% positive, 1,432 configurations.

If selection worked, the share positive would climb as the cut gets tighter. In every previous run in this project it fell BELOW the 50% a coin gives -- picking the best training configs picked worse than random ones.

## The 8 best training configurations, and what they did next

| sym | bars | feature | z | dir | hold | n train | n hold | train pips | HOLDOUT pips | $/wk @1 micro |
|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | tick_1000 | mom200 | 1.5 | -1 | 34 | 340 | 147 | +9.9632 | -9.8840 | -9.69 |
| EURUSD | tick_1000 | mom200 | 1.0 | -1 | 34 | 528 | 345 | +8.2446 | -3.4063 | -7.83 |
| EURUSD | tick_1000 | mom100 | 1.5 | -1 | 34 | 229 | 216 | +8.1315 | -6.1620 | -8.87 |
| EURUSD | tick_1000 | mom20 | 1.0 | +1 | 21 | 406 | 122 | +7.1544 | -5.1213 | -4.17 |
| EURUSD | tick_1000 | mom200 | 1.5 | -1 | 21 | 340 | 147 | +6.9678 | -6.7112 | -6.58 |
| EURUSD | tick_1000 | mom100 | 1.0 | -1 | 34 | 441 | 292 | +6.8952 | -4.2025 | -8.18 |
| EURUSD | tick_1000 | mom20 | 1.0 | +1 | 34 | 406 | 122 | +6.8732 | -6.0484 | -4.92 |
| EURUSD | tick_1000 | mom20 | 1.0 | +1 | 13 | 406 | 122 | +6.5647 | -5.4537 | -4.44 |

The last column is the one that matters and it is deliberately generous: it assumes the holdout result repeats, one micro lot, and no slippage beyond the spread already paid.

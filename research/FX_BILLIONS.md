# FX search, at scale

Every family, crossed with every other family, on data where a buy pays the ask and a sell pays the bid. Selection on train, always reported on holdout.

- EURUSD `tick_2000`: 2,803 bars, 373 conditions, **2,138,142** configurations [10s, running total 2,138,142]

## 2,138,142 configurations scored in 10 seconds

## Select on train, look at holdout

| training cut | score cut | configs kept | share positive out of sample | mean holdout |
|---|---|---|---|---|
| top 1e-05% | >= +12.19 pips | 1 | **100.0%** | +2.7874 pips |
| top 0.0001% | >= +12.14 pips | 2 | **100.0%** | +4.6351 pips |
| top 0.001% | >= +10.75 pips | 21 | **71.4%** | +1.8587 pips |
| top 0.01% | >= +9.54 pips | 165 | **35.8%** | -0.7040 pips |
| top 0.1% | >= +7.64 pips | 2,120 | **24.0%** | -1.5731 pips |
| top 1% | >= +4.96 pips | 21,169 | **33.8%** | -1.5668 pips |
| top 10% | >= +2.50 pips | 212,890 | **41.0%** | -0.9736 pips |
| top 50% | >= +0.00 pips | 1,069,071 | **42.1%** | -0.5740 pips |
| top 100% | >= -1095.63 pips | 2,138,142 | **50.0%** | -0.0000 pips |

A coin gives 50%. Anything below that means selecting the best training configurations selected WORSE than picking at random.

## The best configurations by training score, and what they did next

| train pips | HOLDOUT pips | rule |
|---|---|---|
| +12.283 | +2.787 | `SHORT pos13>0.0 AND rng34<-0.0 AND vmom233>0.5` |
| +12.186 | +6.483 | `SHORT pos34>0.0 AND rng34<-0.0 AND vmom233>0.5` |
| +12.122 | +4.052 | `SHORT rev21<-0.0 AND rng34<-0.0 AND vmom233>0.5` |
| +11.954 | +1.810 | `SHORT rev13<-0.0 AND rng34<-0.0 AND vmom233>0.5` |

## Per cell, so one symbol cannot carry the answer

| symbol / bars | configs | share positive in top 0.01% |
|---|---|---|
| EURUSD `tick_2000` | 2,138,142 | 35.8% |

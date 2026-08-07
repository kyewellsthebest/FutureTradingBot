# FX search, at scale

Every family, crossed with every other family, on data where a buy pays the ask and a sell pays the bid. Selection on train, always reported on holdout.

- EURUSD `tick_2000`: 2,803 bars, 373 conditions, **32,893** configurations [3s, running total 32,893]

## 32,893 configurations scored in 3 seconds

## Select on train, look at holdout

| training cut | score cut | configs kept | share positive out of sample | mean holdout |
|---|---|---|---|---|
| top 0.01% | >= +8.25 pips | 3 | **0.0%** | -4.7958 pips |
| top 0.1% | >= +7.00 pips | 25 | **32.0%** | -4.2336 pips |
| top 1% | >= +4.50 pips | 281 | **18.1%** | -4.0356 pips |
| top 10% | >= +2.00 pips | 2,903 | **21.7%** | -2.8422 pips |
| top 50% | >= +0.00 pips | 15,247 | **19.6%** | -2.0380 pips |
| top 100% | >= -inf pips | 32,893 | **29.0%** | -1.4113 pips |

A coin gives 50%. Anything below that means selecting the best training configurations selected WORSE than picking at random.

## The best configurations by training score, and what they did next

| train pips | HOLDOUT pips | rule |
|---|---|---|
| +8.798 | -1.450 | `rng34>0.0 AND acc34>0.5` |
| +8.786 | -7.650 | `rev34<-1.0 AND acc34>0.5` |
| +8.647 | -5.287 | `mom13>0.5 AND acc34>0.5` |

## Per cell, so one symbol cannot carry the answer

| symbol / bars | configs | share positive in top 0.01% |
|---|---|---|
| EURUSD `tick_2000` | 32,893 | 0.0% |

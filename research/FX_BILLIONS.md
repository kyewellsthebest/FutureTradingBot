# FX search, at scale

Every family, crossed with every other family, on data where a buy pays the ask and a sell pays the bid. Selection on train, always reported on holdout.

- EURUSD `tick_200`: 28,035 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- EURUSD `tick_500`: 11,214 bars, 507 conditions, **195,506,514** configurations [235s, running total 195,506,514]
- EURUSD `tick_2000`: 2,803 bars, 373 conditions, **51,216,444** configurations [263s, running total 246,722,958]
- EURUSD `time_60`: 108,298 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- EURUSD `time_600`: 10,871 bars, 516 conditions, **179,320,710** configurations [491s, running total 426,043,668]
- GBPUSD `tick_200`: 43,670 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- GBPUSD `tick_500`: 17,468 bars, 523 conditions, **221,790,768** configurations [878s, running total 647,834,436]
- GBPUSD `tick_2000`: 4,367 bars, 427 conditions, **82,979,916** configurations [936s, running total 730,814,352]
- GBPUSD `tick_10000`: 873 bars, 217 conditions, **1,176,600** configurations [937s, running total 731,990,952]
- GBPUSD `time_60`: 141,378 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- GBPUSD `time_600`: 14,219 bars, 520 conditions, **198,266,076** configurations [1241s, running total 930,257,028]
- USDJPY `tick_200`: 50,647 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- USDJPY `tick_500`: 20,258 bars, 525 conditions, **227,968,152** configurations [1715s, running total 1,158,225,180]
- USDJPY `tick_2000`: 5,064 bars, 430 conditions, **90,452,478** configurations [1787s, running total 1,248,677,658]
- USDJPY `tick_10000`: 1,012 bars, 242 conditions, **7,945,146** configurations [1789s, running total 1,256,622,804]
- USDJPY `time_60`: 151,356 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- USDJPY `time_600`: 15,191 bars, 508 conditions, **174,990,666** configurations [2098s, running total 1,431,613,470]
- XAUUSD `tick_200`: 223,753 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- XAUUSD `tick_500`: 89,501 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- XAUUSD `tick_2000`: 22,375 bars, 577 conditions, **299,260,512** configurations [2984s, running total 1,730,873,982]
- XAUUSD `tick_10000`: 4,475 bars, 440 conditions, **63,556,032** configurations [3043s, running total 1,794,430,014]
- XAUUSD `time_60`: 173,485 bars exceeds the 26,000 cap, SKIPPED (not silently truncated)
- XAUUSD `time_600`: 17,353 bars, 562 conditions, **242,695,326** configurations [3530s, running total 2,037,125,340]

## 2,037,125,340 configurations scored in 3530 seconds

## Select on train, look at holdout

| training cut | score cut | configs kept | share positive out of sample | mean holdout |
|---|---|---|---|---|
| top 1e-05% | >= +12.00 pips | 144,499,011 | **38.9%** | -22.9100 pips |
| top 10% | >= +8.25 pips | 199,353,381 | **44.5%** | -16.5972 pips |
| top 50% | >= +0.25 pips | 919,947,750 | **57.8%** | -3.2118 pips |
| top 100% | >= -inf pips | 2,037,125,340 | **50.0%** | +0.0000 pips |

A coin gives 50%. Anything below that means selecting the best training configurations selected WORSE than picking at random.

## The best configurations by training score, and what they did next

| train pips | HOLDOUT pips | rule |
|---|---|---|
| +953.963 | -124.202 | `LONG vmom233<-0.0 AND rev233>0.0 AND rng144<-0.0` |
| +953.963 | -124.202 | `LONG rng144<-0.0 AND vmom233<-0.0 AND rev233>0.0` |
| +953.963 | -124.202 | `LONG rng144<-0.0 AND rev233>0.0 AND vmom233<-0.0` |
| +953.963 | -124.202 | `LONG rng144<-0.0 AND rev233>0.0 AND mom233<-0.0` |
| +953.963 | -124.202 | `LONG rng144<-0.0 AND mom233<-0.0 AND rev233>0.0` |
| +953.963 | -124.202 | `LONG mom233<-0.0 AND rev233>0.0 AND rng144<-0.0` |
| +950.418 | -368.917 | `LONG acc89>0.0 AND acc144<-0.0 AND acc34<-0.5` |
| +950.418 | -368.917 | `LONG acc34<-0.5 AND acc89>0.0 AND acc144<-0.0` |
| +950.418 | -368.917 | `LONG acc34<-0.5 AND acc144<-0.0 AND acc89>0.0` |
| +942.446 | -118.990 | `LONG rng144<-0.0 AND pos233<-0.0 AND pos144<-0.5` |
| +942.446 | -118.990 | `LONG pos144<-0.5 AND rng144<-0.0 AND pos233<-0.0` |
| +942.446 | -118.990 | `LONG pos144<-0.5 AND pos233<-0.0 AND rng144<-0.0` |
| +937.387 | -124.150 | `LONG rng144<-0.0 AND pos233<-0.0 AND rev144>0.0` |
| +937.387 | -124.150 | `LONG rev144>0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +937.387 | -124.150 | `LONG rev144>0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +925.655 | -604.527 | `LONG acc89>0.5 AND acc144<-0.0 AND acc34<-0.0` |
| +925.655 | -604.527 | `LONG acc34<-0.0 AND acc89>0.5 AND acc144<-0.0` |
| +925.655 | -604.527 | `LONG acc34<-0.0 AND acc144<-0.0 AND acc89>0.5` |
| +884.837 | -29.167 | `LONG rng144>0.0 AND rng233<-0.0 AND acc89>0.5` |
| +884.837 | -29.167 | `LONG acc89>0.5 AND rng233<-0.0 AND rng144>0.0` |
| +884.837 | -29.167 | `LONG acc89>0.5 AND rng144>0.0 AND rng233<-0.0` |
| +874.883 | -51.316 | `LONG vmom34<-0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +874.883 | -51.316 | `LONG vmom34<-0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +874.883 | -51.316 | `LONG rng144<-0.0 AND pos233<-0.0 AND vmom34<-0.0` |
| +874.883 | -51.316 | `LONG rng144<-0.0 AND pos233<-0.0 AND mom34<-0.0` |
| +874.883 | -51.316 | `LONG mom34<-0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +874.883 | -51.316 | `LONG mom34<-0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +874.608 | -548.939 | `LONG rev34>0.0 AND acc89>0.0 AND acc144<-0.0` |
| +874.608 | -548.939 | `LONG rev34>0.0 AND acc144<-0.0 AND acc89>0.0` |
| +874.608 | -548.939 | `LONG acc89>0.0 AND acc144<-0.0 AND rev34>0.0` |
| +871.517 | +39.064 | `LONG rng144<-0.0 AND pos233<-0.0 AND rev55>0.0` |
| +871.517 | +39.064 | `LONG rev55>0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +871.517 | +39.064 | `LONG rev55>0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +870.208 | -124.964 | `LONG rng144<-0.0 AND pos233<-0.0 AND pos144<-0.0` |
| +870.208 | -124.964 | `LONG pos144<-0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +870.208 | -124.964 | `LONG pos144<-0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +862.951 | -53.417 | `LONG rng144<-0.0 AND pos233<-0.0 AND pos89<-0.0` |
| +862.951 | -53.417 | `LONG pos89<-0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +862.951 | -53.417 | `LONG pos89<-0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +862.448 | -52.775 | `LONG rng144<-0.0 AND pos233<-0.0 AND rev89>0.0` |
| +862.448 | -52.775 | `LONG rev89>0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +862.448 | -52.775 | `LONG rev89>0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +859.572 | -94.680 | `LONG vmom21<-0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +859.572 | -94.680 | `LONG vmom21<-0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +859.572 | -94.680 | `LONG rng144<-0.0 AND pos233<-0.0 AND vmom21<-0.0` |
| +859.572 | -94.680 | `LONG rng144<-0.0 AND pos233<-0.0 AND mom21<-0.0` |
| +859.572 | -94.680 | `LONG mom21<-0.0 AND rng144<-0.0 AND pos233<-0.0` |
| +859.572 | -94.680 | `LONG mom21<-0.0 AND pos233<-0.0 AND rng144<-0.0` |
| +855.212 | -511.186 | `LONG pos34<-0.0 AND acc89>0.0 AND acc144<-0.0` |
| +855.212 | -511.186 | `LONG pos34<-0.0 AND acc144<-0.0 AND acc89>0.0` |
| +855.212 | -511.186 | `LONG acc89>0.0 AND acc144<-0.0 AND pos34<-0.0` |
| +855.191 | -230.439 | `LONG rng55<-0.0 AND acc233<-0.5 AND acc34<-0.0` |
| +855.191 | -230.439 | `LONG acc34<-0.0 AND rng55<-0.0 AND acc233<-0.5` |
| +855.191 | -230.439 | `LONG acc34<-0.0 AND acc233<-0.5 AND rng55<-0.0` |
| +853.417 | -591.427 | `LONG acc89>0.5 AND acc233<-0.0 AND acc34<-0.0` |
| +853.417 | -591.427 | `LONG acc34<-0.0 AND acc89>0.5 AND acc233<-0.0` |
| +853.417 | -591.427 | `LONG acc34<-0.0 AND acc233<-0.0 AND acc89>0.5` |
| +852.511 | -182.029 | `LONG rng144<-0.0 AND rev233>0.0 AND rev144>0.0` |
| +852.511 | -182.029 | `LONG rev144>0.0 AND rng144<-0.0 AND rev233>0.0` |
| +852.511 | -182.029 | `LONG rev144>0.0 AND rev233>0.0 AND rng144<-0.0` |

## Per cell, so one symbol cannot carry the answer

| symbol / bars | configs | share positive in top 0.01% |
|---|---|---|

wrote /home/user/FutureTradingBot/research/FX_BILLIONS.md

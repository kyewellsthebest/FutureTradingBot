# A2: does the order book predict forward returns?

`2,235,601` seconds of top of book across 1 symbol(s) and 5 weeks, 71% of them carrying at least one event. Forward returns are invalidated across feed holes -- a 30-second return computed over the maintenance halt is an overnight return wearing a 30-second label, and it is the easiest way to manufacture an IC here.

`shift floor` is the standard deviation of the same IC with the forward return slid by 0.5-4 hours in both directions. Both series keep their autocorrelation and only the alignment dies, so it measures what this pipeline produces from nothing at THIS sample's dependence structure. A naive 3/sqrt(n) on a million overlapping seconds would quote a precision the data does not have.

## 1s ahead (sigma = 1.36 pt)

| feature | IC | shift floor | IC/floor | weeks same sign | edge = IC x sigma | vs 0.87pt cost |
|---|---|---|---|---|---|---|
| imb | +0.0425 | 0.0010 | 44.3 | 100% | 0.058 pt | below |
| d_imb | +0.0299 | 0.0005 | 61.6 | 100% | 0.041 pt | below |
| micro_dev | +0.0427 | 0.0010 | 43.1 | 100% | 0.058 pt | below |
| spread | -0.0006 | 0.0005 | 1.2 | 40% | 0.001 pt | below |
| qrate | -0.0021 | 0.0009 | 2.3 | 80% | 0.003 pt | below |
| depl_skew | -0.0040 | 0.0004 | 10.0 | 100% | 0.005 pt | below |
| tt_press | -0.0072 | 0.0004 | 18.1 | 100% | 0.010 pt | below |
| add_skew | +0.0015 | 0.0005 | 3.3 | 60% | 0.002 pt | below |
| ofi | -0.0021 | 0.0007 | 3.2 | 60% | 0.003 pt | below |
| shuffled | +0.0020 | 0.0007 | 2.9 | 80% | 0.003 pt | below |

## 5s ahead (sigma = 3.03 pt)

| feature | IC | shift floor | IC/floor | weeks same sign | edge = IC x sigma | vs 0.87pt cost |
|---|---|---|---|---|---|---|
| imb | +0.0200 | 0.0008 | 25.5 | 100% | 0.061 pt | below |
| d_imb | +0.0126 | 0.0004 | 33.2 | 100% | 0.038 pt | below |
| micro_dev | +0.0203 | 0.0008 | 26.8 | 100% | 0.062 pt | below |
| spread | -0.0026 | 0.0020 | 1.3 | 80% | 0.008 pt | below |
| qrate | -0.0023 | 0.0010 | 2.2 | 80% | 0.007 pt | below |
| depl_skew | -0.0022 | 0.0010 | 2.2 | 80% | 0.007 pt | below |
| tt_press | -0.0052 | 0.0008 | 6.1 | 100% | 0.016 pt | below |
| add_skew | +0.0018 | 0.0013 | 1.4 | 60% | 0.006 pt | below |
| ofi | -0.0003 | 0.0010 | 0.3 | 40% | 0.001 pt | below |
| shuffled | +0.0005 | 0.0007 | 0.7 | 80% | 0.001 pt | below |

## 30s ahead (sigma = 7.35 pt)

| feature | IC | shift floor | IC/floor | weeks same sign | edge = IC x sigma | vs 0.87pt cost |
|---|---|---|---|---|---|---|
| imb | +0.0082 | 0.0012 | 6.9 | 100% | 0.060 pt | below |
| d_imb | +0.0047 | 0.0002 | 21.4 | 100% | 0.034 pt | below |
| micro_dev | +0.0083 | 0.0012 | 7.0 | 100% | 0.061 pt | below |
| spread | -0.0038 | 0.0048 | 0.8 | 40% | 0.028 pt | below |
| qrate | +0.0009 | 0.0017 | 0.5 | 40% | 0.007 pt | below |
| depl_skew | +0.0019 | 0.0012 | 1.6 | 60% | 0.014 pt | below |
| tt_press | -0.0058 | 0.0011 | 5.3 | 100% | 0.042 pt | below |
| add_skew | -0.0037 | 0.0015 | 2.4 | 80% | 0.027 pt | below |
| ofi | -0.0015 | 0.0014 | 1.1 | 80% | 0.011 pt | below |
| shuffled | +0.0004 | 0.0006 | 0.7 | 60% | 0.003 pt | below |

## 60s ahead (sigma = 10.24 pt)

| feature | IC | shift floor | IC/floor | weeks same sign | edge = IC x sigma | vs 0.87pt cost |
|---|---|---|---|---|---|---|
| imb | +0.0065 | 0.0016 | 4.0 | 100% | 0.066 pt | below |
| d_imb | +0.0034 | 0.0002 | 20.2 | 100% | 0.035 pt | below |
| micro_dev | +0.0063 | 0.0016 | 3.8 | 100% | 0.064 pt | below |
| spread | -0.0049 | 0.0073 | 0.7 | 40% | 0.050 pt | below |
| qrate | +0.0029 | 0.0026 | 1.1 | 60% | 0.030 pt | below |
| depl_skew | +0.0027 | 0.0013 | 2.0 | 40% | 0.027 pt | below |
| tt_press | -0.0038 | 0.0010 | 3.6 | 100% | 0.039 pt | below |
| add_skew | -0.0028 | 0.0013 | 2.2 | 80% | 0.029 pt | below |
| ofi | -0.0003 | 0.0009 | 0.3 | 80% | 0.003 pt | below |
| shuffled | -0.0003 | 0.0005 | 0.7 | 40% | 0.003 pt | below |

## 300s ahead (sigma = 22.78 pt)

| feature | IC | shift floor | IC/floor | weeks same sign | edge = IC x sigma | vs 0.87pt cost |
|---|---|---|---|---|---|---|
| imb | +0.0005 | 0.0043 | 0.1 | 80% | 0.011 pt | below |
| d_imb | +0.0012 | 0.0002 | 5.7 | 100% | 0.028 pt | below |
| micro_dev | +0.0001 | 0.0044 | 0.0 | 60% | 0.003 pt | below |
| spread | -0.0024 | 0.0130 | 0.2 | 20% | 0.056 pt | below |
| qrate | +0.0078 | 0.0053 | 1.5 | 80% | 0.177 pt | below |
| depl_skew | +0.0090 | 0.0031 | 2.9 | 80% | 0.205 pt | below |
| tt_press | +0.0004 | 0.0004 | 0.9 | 40% | 0.009 pt | below |
| add_skew | -0.0045 | 0.0027 | 1.6 | 80% | 0.102 pt | below |
| ofi | +0.0027 | 0.0013 | 2.1 | 80% | 0.061 pt | below |
| shuffled | -0.0018 | 0.0005 | 3.2 | 100% | 0.040 pt | below |

## 1800s ahead (sigma = 58.25 pt)

| feature | IC | shift floor | IC/floor | weeks same sign | edge = IC x sigma | vs 0.87pt cost |
|---|---|---|---|---|---|---|
| imb | -0.0023 | 0.0088 | 0.3 | 80% | 0.132 pt | below |
| d_imb | +0.0006 | 0.0002 | 2.5 | 100% | 0.033 pt | below |
| micro_dev | -0.0024 | 0.0095 | 0.3 | 80% | 0.142 pt | below |
| spread | -0.0101 | 0.0338 | 0.3 | 40% | 0.586 pt | below |
| qrate | -0.0011 | 0.0126 | 0.1 | 40% | 0.061 pt | below |
| depl_skew | +0.0103 | 0.0110 | 0.9 | 80% | 0.601 pt | below |
| tt_press | -0.0006 | 0.0014 | 0.5 | 60% | 0.036 pt | below |
| add_skew | -0.0065 | 0.0136 | 0.5 | 60% | 0.380 pt | below |
| ofi | +0.0020 | 0.0042 | 0.5 | 80% | 0.117 pt | below |
| shuffled | -0.0001 | 0.0005 | 0.2 | 60% | 0.007 pt | below |

## Verdict against the gates fixed before the run

`|IC| >= 0.03`, `|IC| >= 3x the shift floor`, sign holds in >= 75% of weeks.

**2 combinations pass.**

| feature | horizon | IC | edge | tradable alone? |
|---|---|---|---|---|
| micro_dev | 1s | +0.0427 | 0.058 pt | NO -- filter only |
| imb | 1s | +0.0425 | 0.058 pt | NO -- filter only |

Every survivor is real but too small to pay its own way: none reaches the 0.87pt round-trip cost of an MNQ taker at its horizon. That does not make them worthless -- it makes them **filters** on a longer-horizon strategy, which is what Track B is for. It does mean none of them is a standalone system.

## The decay shape — and a correction to the line above

The closing sentence of the verdict is generated before the horizon sweep is read, and this run's own numbers contradict it. Routing these features to Track B as *filters on a longer-horizon strategy* assumes the information survives to a longer horizon. It does not.

| horizon | imb IC | sigma | IC/floor | weeks same sign | edge |
|---|---|---|---|---|---|
| 1s | +0.0425 | 1.36 pt | 44.3 | 100% | **0.058 pt** |
| 5s | +0.0200 | 3.03 pt | 25.5 | 100% | **0.061 pt** |
| 30s | +0.0082 | 7.35 pt | 6.9 | 100% | **0.060 pt** |
| 60s | +0.0065 | 10.24 pt | 4.0 | 100% | **0.066 pt** |
| 300s | +0.0005 | 22.78 pt | 0.1 | 80% | **0.011 pt** |
| 1800s | -0.0023 | 58.25 pt | 0.3 | 80% | **0.132 pt** |

Two things are visible and both matter more than the gate result.

**The edge is constant from 1s to 60s.** IC falls at almost exactly 1/sqrt(t) while sigma grows at sqrt(t), so their product does not move: 0.058 -> 0.061 -> 0.060 -> 0.066 pt across a sixtyfold change in horizon. The book carries a FIXED amount of information, worth about 0.06 points, and holding longer does not accumulate more of it.

**Past 60s it is gone**, not merely flat: by 300s the IC sits at 0.1x its own noise floor. So there is no long-horizon strategy for these to filter, and the Track B premise -- that a fixed per-trade cost is eventually outrun because opportunity grows with sqrt(time) -- is false for this signal class. That premise only holds if IC decays SLOWER than 1/sqrt(t). Here it decays at exactly 1/sqrt(t).

**The scale that ends it:** NQ's spread is 3 ticks = 0.75 pt (52.6% of RTH seconds; 1-tick spreads occur 0.7% of the time). The signal is **one twelfth of the spread it would have to cross**, before commission is mentioned at all. This is not a near miss that better execution or a cheaper broker closes.

What the purchase did settle, and it was worth $32.51 to know:

- top-of-book imbalance genuinely predicts direction -- IC +0.0425 at 44x the measured noise floor, same sign in 100% of weeks, independently confirmed by microprice deviation at +0.0427. The pilot could not answer this on one week; four weeks answers it clearly.
- **the pilot's two headline signals did not survive.** Quote rate went -0.084 -> -0.0021 (2.3x floor) and spread -0.056 -> -0.0006 (1.2x floor). Both were one-week artifacts. They were cited in the research plan as the strongest NQ evidence available; they were noise.

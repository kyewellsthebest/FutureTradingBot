# How fast does cross-market information die?

The index complex leads NQ on a scale of **milliseconds**. A 2.7-minute bar cannot see that, so this measures the decay curve directly with no model in the way.

`L` is **total latency** — everything between a foreign print existing and our order resting in the book. The foreign window ends at `t − L`; the NQ outcome starts at `t`. Nothing in the predictor is contemporaneous with what it predicts. `L = 0` is physically impossible and is here only as the ceiling of the curve.

NQ prints sampled every 40, 3 quarters, a 1000 ms foreign look-back window. `$/trade` takes a full MNQ position in the direction the foreign tape just moved; a round turn costs **$1.99**.

**One caveat on the sample.** Consecutive samples overlap — at a 30 s outcome window, thousands of them share the same stretch of tape. That leaves the point estimates unbiased but makes their standard errors far smaller than they look, so do not read a small number as significant just because it sits on millions of rows. The shifted control, not the row count, is what makes a number here trustworthy.

## NQ order flow → NQ price

| total latency | IC @ 100ms | IC @ 1000ms | IC @ 5000ms | IC @ 30000ms | $/trade @ 100ms | $/trade @ 1000ms | $/trade @ 5000ms | $/trade @ 30000ms |
|---|---|---|---|---|---|---|---|---|
| 0 ms | +0.0225 | +0.0113 | +0.0024 | +0.0019 | $+0.008 | $+0.010 | $+0.003 | $+0.009 |
| 1 ms | +0.0005 | +0.0057 | +0.0002 | +0.0013 | $+0.000 | $+0.005 | $-0.002 | $+0.004 |
| 5 ms | -0.0004 | +0.0053 | +0.0000 | +0.0013 | $-0.000 | $+0.004 | $-0.002 | $+0.004 |
| 10 ms | -0.0007 | +0.0052 | -0.0001 | +0.0013 | $-0.000 | $+0.004 | $-0.001 | $+0.005 |
| 25 ms | -0.0008 | +0.0051 | +0.0000 | +0.0017 | $-0.000 | $+0.004 | $-0.001 | $+0.006 |
| 50 ms | -0.0007 | +0.0048 | -0.0003 | +0.0015 | $-0.001 | $+0.004 | $-0.002 | $+0.005 |
| 100 ms | -0.0002 | +0.0044 | -0.0002 | +0.0019 | $-0.000 | $+0.003 | $-0.001 | $+0.007 |
| 250 ms | -0.0013 | +0.0032 | -0.0008 | +0.0014 | $-0.001 | $+0.002 | $-0.003 | $+0.006 |
| 500 ms | -0.0026 | +0.0007 | -0.0016 | +0.0004 | $-0.001 | $+0.000 | $-0.004 | $+0.007 |
| 1 s | -0.0037 | -0.0023 | -0.0030 | +0.0003 | $-0.002 | $-0.004 | $-0.008 | $+0.002 |
| **2 s ← this bot today** | -0.0040 | -0.0016 | -0.0016 | -0.0005 | $-0.001 | $-0.002 | $-0.003 | $+0.004 |
| **5 s** | -0.0014 | -0.0009 | -0.0005 | -0.0005 | $-0.000 | $-0.001 | $-0.000 | $+0.001 |

| shifted control | -0.0025 | -0.0007 | -0.0003 | +0.0008 | $-0.001 | $-0.000 | $+0.000 | $+0.006 |

The control slides the NQ order flow tape 11 days along the calendar and repeats the L=0 row — same tape, wrong times. Almost any bug produces a number in the real row; only the shifted row separates information from arithmetic.

## ES → NQ

| total latency | IC @ 100ms | IC @ 1000ms | IC @ 5000ms | IC @ 30000ms | $/trade @ 100ms | $/trade @ 1000ms | $/trade @ 5000ms | $/trade @ 30000ms |
|---|---|---|---|---|---|---|---|---|
| 0 ms | +0.0499 | +0.0305 | +0.0053 | +0.0019 | $+0.007 | $+0.016 | $-0.006 | $-0.009 |
| 1 ms | +0.0378 | +0.0241 | +0.0015 | +0.0006 | $+0.002 | $+0.011 | $-0.011 | $-0.014 |
| 5 ms | +0.0312 | +0.0215 | +0.0005 | -0.0000 | $+0.001 | $+0.010 | $-0.012 | $-0.016 |
| 10 ms | +0.0279 | +0.0204 | +0.0006 | -0.0001 | $+0.000 | $+0.009 | $-0.013 | $-0.016 |
| 25 ms | +0.0228 | +0.0167 | -0.0008 | -0.0005 | $-0.001 | $+0.009 | $-0.014 | $-0.019 |
| 50 ms | +0.0197 | +0.0141 | -0.0019 | -0.0000 | $-0.001 | $+0.008 | $-0.015 | $-0.014 |
| 100 ms | +0.0146 | +0.0110 | -0.0036 | -0.0002 | $-0.002 | $+0.007 | $-0.016 | $-0.014 |
| 250 ms | +0.0111 | +0.0071 | -0.0048 | -0.0031 | $-0.002 | $+0.005 | $-0.014 | $-0.015 |
| 500 ms | -0.0120 | -0.0077 | -0.0108 | -0.0065 | $-0.002 | $+0.001 | $-0.018 | $-0.020 |
| 1 s | -0.0158 | -0.0100 | -0.0096 | -0.0061 | $-0.004 | $-0.007 | $-0.019 | $-0.014 |
| **2 s ← this bot today** | -0.0075 | -0.0018 | -0.0031 | -0.0051 | $-0.004 | $-0.004 | $-0.017 | $-0.024 |
| **5 s** | +0.0021 | -0.0020 | -0.0116 | -0.0065 | $-0.001 | $-0.002 | $-0.005 | $-0.017 |

| shifted control | -0.0099 | -0.0029 | +0.0023 | +0.0031 | $-0.000 | $-0.000 | $+0.005 | $+0.016 |

The control slides the ES tape 11 days along the calendar and repeats the L=0 row — same tape, wrong times. Almost any bug produces a number in the real row; only the shifted row separates information from arithmetic.

## YM → NQ

| total latency | IC @ 100ms | IC @ 1000ms | IC @ 5000ms | IC @ 30000ms | $/trade @ 100ms | $/trade @ 1000ms | $/trade @ 5000ms | $/trade @ 30000ms |
|---|---|---|---|---|---|---|---|---|
| 0 ms | +0.0284 | +0.0174 | +0.0013 | -0.0005 | $+0.002 | $+0.008 | $-0.007 | $-0.016 |
| 1 ms | +0.0243 | +0.0159 | +0.0003 | -0.0010 | $+0.000 | $+0.006 | $-0.009 | $-0.018 |
| 5 ms | +0.0219 | +0.0148 | +0.0003 | -0.0010 | $-0.001 | $+0.006 | $-0.009 | $-0.019 |
| 10 ms | +0.0191 | +0.0128 | -0.0003 | -0.0014 | $-0.001 | $+0.005 | $-0.009 | $-0.019 |
| 25 ms | +0.0165 | +0.0104 | -0.0011 | -0.0018 | $-0.002 | $+0.004 | $-0.010 | $-0.019 |
| 50 ms | +0.0131 | +0.0092 | -0.0015 | -0.0009 | $-0.002 | $+0.004 | $-0.010 | $-0.016 |
| 100 ms | +0.0103 | +0.0066 | -0.0024 | -0.0010 | $-0.002 | $+0.002 | $-0.010 | $-0.016 |
| 250 ms | +0.0078 | +0.0039 | -0.0025 | -0.0033 | $-0.002 | $+0.002 | $-0.009 | $-0.019 |
| 500 ms | -0.0096 | -0.0069 | -0.0073 | -0.0059 | $-0.002 | $-0.000 | $-0.013 | $-0.021 |
| 1 s | -0.0091 | -0.0064 | -0.0047 | -0.0048 | $-0.002 | $-0.005 | $-0.014 | $-0.016 |
| **2 s ← this bot today** | -0.0072 | -0.0020 | -0.0002 | -0.0045 | $-0.003 | $-0.003 | $-0.010 | $-0.012 |
| **5 s** | +0.0023 | -0.0032 | -0.0087 | -0.0065 | $-0.001 | $-0.003 | $-0.005 | $-0.017 |

| shifted control | -0.0020 | -0.0004 | +0.0041 | +0.0075 | $-0.000 | $+0.001 | $+0.005 | $+0.012 |

The control slides the YM tape 11 days along the calendar and repeats the L=0 row — same tape, wrong times. Almost any bug produces a number in the real row; only the shifted row separates information from arithmetic.

## RTY → NQ

| total latency | IC @ 100ms | IC @ 1000ms | IC @ 5000ms | IC @ 30000ms | $/trade @ 100ms | $/trade @ 1000ms | $/trade @ 5000ms | $/trade @ 30000ms |
|---|---|---|---|---|---|---|---|---|
| 0 ms | +0.0314 | +0.0168 | +0.0041 | +0.0022 | $+0.002 | $+0.009 | $-0.008 | $-0.025 |
| 1 ms | +0.0288 | +0.0155 | +0.0029 | +0.0018 | $+0.001 | $+0.008 | $-0.010 | $-0.027 |
| 5 ms | +0.0269 | +0.0147 | +0.0024 | +0.0015 | $-0.000 | $+0.007 | $-0.010 | $-0.026 |
| 10 ms | +0.0245 | +0.0134 | +0.0018 | +0.0014 | $-0.000 | $+0.006 | $-0.011 | $-0.028 |
| 25 ms | +0.0211 | +0.0114 | +0.0008 | +0.0012 | $-0.001 | $+0.006 | $-0.011 | $-0.025 |
| 50 ms | +0.0197 | +0.0094 | +0.0001 | +0.0014 | $-0.001 | $+0.005 | $-0.011 | $-0.024 |
| 100 ms | +0.0140 | +0.0069 | -0.0007 | +0.0016 | $-0.001 | $+0.005 | $-0.008 | $-0.020 |
| 250 ms | +0.0113 | +0.0039 | -0.0015 | +0.0007 | $-0.001 | $+0.004 | $-0.011 | $-0.018 |
| 500 ms | -0.0073 | -0.0031 | -0.0055 | -0.0033 | $-0.001 | $+0.000 | $-0.015 | $-0.024 |
| 1 s | -0.0088 | -0.0007 | -0.0028 | -0.0001 | $-0.002 | $-0.005 | $-0.014 | $-0.013 |
| **2 s ← this bot today** | -0.0050 | -0.0042 | -0.0042 | -0.0019 | $-0.002 | $-0.005 | $-0.014 | $-0.018 |
| **5 s** | +0.0029 | -0.0065 | -0.0041 | -0.0046 | $-0.001 | $-0.004 | $-0.006 | $-0.020 |

| shifted control | -0.0060 | -0.0090 | -0.0003 | +0.0026 | $-0.001 | $-0.003 | $+0.000 | $+0.013 |

The control slides the RTY tape 11 days along the calendar and repeats the L=0 row — same tape, wrong times. Almost any bug produces a number in the real row; only the shifted row separates information from arithmetic.

## What the curve decides

This bot's measured entry latency is about **2 seconds**. Read the 2 s row, not the 0 ms row. The gap between them is exactly what execution engineering is worth — if the 0 ms row clears $1.99 and the 2 s row does not, the edge is real and unreachable at current speed, and the fix is the bot rather than the search. If both rows sit at zero, cross-market speed is not the answer and no colocation would change that.

_Ran in 3 min._

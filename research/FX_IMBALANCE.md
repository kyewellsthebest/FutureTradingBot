# Quote imbalance on FX ticks

Top-of-book size on the bid against top-of-book size on the ask, measured the same way the NASDAQ order book was. Everything in pips, against a spread that was measured and not modelled.

## EURUSD

5,607,145 ticks. Median spread **0.30 pips**, so crossing costs **0.15 pips** each way. Imbalance sigma 0.361.

| horizon | feature | train IC | holdout IC | sign held |
|---|---|---|---|---|
| 1 ticks | imbalance | +0.1194 | +0.1305 | yes |
| 1 ticks | shuffled | -0.0001 | +0.0014 | no |
| 1 ticks | shifted | -0.0002 | +0.0006 | no |
| 5 ticks | imbalance | +0.0493 | +0.0577 | yes |
| 5 ticks | shuffled | -0.0001 | +0.0001 | no |
| 5 ticks | shifted | +0.0002 | +0.0007 | yes |
| 20 ticks | imbalance | +0.0244 | +0.0281 | yes |
| 20 ticks | shuffled | -0.0010 | +0.0009 | no |
| 20 ticks | shifted | +0.0009 | +0.0002 | yes |
| 100 ticks | imbalance | +0.0120 | +0.0144 | yes |
| 100 ticks | shuffled | +0.0001 | +0.0000 | yes |
| 100 ticks | shifted | -0.0010 | -0.0005 | yes |

| horizon | holdout IC | net of control | fwd sigma | worth | vs half-spread |
|---|---|---|---|---|---|
| 1 ticks | +0.1305 | +0.1299 | 0.198 pips | 0.0257 pips | 0.17x |
| 5 ticks | +0.0577 | +0.0569 | 0.476 pips | 0.0271 pips | 0.18x |
| 20 ticks | +0.0281 | +0.0280 | 0.973 pips | 0.0272 pips | 0.18x |
| 100 ticks | +0.0144 | +0.0139 | 2.187 pips | 0.0305 pips | 0.20x |

**Best: +0.1305 at 1 ticks ahead**, against a time-shifted control of +0.0006. Forward move sigma 0.20 pips.

- net of the control, worth about **0.026 pips** a trade
- crossing costs **0.15 pips** each way
- **as a taker: does NOT clear the spread**

| imbalance decile | mean move over 1 ticks | n |
|---|---|---|
| 0 | -0.0243 pips | 187,913 |
| 1 | -0.0167 pips | 230,559 |
| 2 | -0.0065 pips | 94,039 |
| 3 | +0.0003 pips | 611,829 |
| 4 | +0.0080 pips | 85,057 |
| 5 | +0.0161 pips | 237,971 |
| 6 | +0.0167 pips | 109,037 |
| 7 | +0.0190 pips | 125,738 |

**Top decile minus bottom: +0.0433 pips +/- 0.0005 (89.8 sigma).** One side of that is about +0.0217 pips against 0.15 pips to cross.

## GBPUSD

8,734,162 ticks. Median spread **0.70 pips**, so crossing costs **0.35 pips** each way. Imbalance sigma 0.350.

| horizon | feature | train IC | holdout IC | sign held |
|---|---|---|---|---|
| 1 ticks | imbalance | +0.1263 | +0.1039 | yes |
| 1 ticks | shuffled | +0.0010 | -0.0000 | no |
| 1 ticks | shifted | -0.0005 | +0.0003 | no |
| 5 ticks | imbalance | +0.0651 | +0.0529 | yes |
| 5 ticks | shuffled | -0.0002 | -0.0005 | yes |
| 5 ticks | shifted | -0.0010 | -0.0004 | yes |
| 20 ticks | imbalance | +0.0358 | +0.0274 | yes |
| 20 ticks | shuffled | -0.0001 | -0.0001 | yes |
| 20 ticks | shifted | +0.0003 | -0.0004 | no |
| 100 ticks | imbalance | +0.0195 | +0.0158 | yes |
| 100 ticks | shuffled | +0.0000 | -0.0004 | no |
| 100 ticks | shifted | -0.0003 | +0.0006 | no |

| horizon | holdout IC | net of control | fwd sigma | worth | vs half-spread |
|---|---|---|---|---|---|
| 1 ticks | +0.1039 | +0.1036 | 0.269 pips | 0.0278 pips | 0.08x |
| 5 ticks | +0.0529 | +0.0525 | 0.620 pips | 0.0326 pips | 0.09x |
| 20 ticks | +0.0274 | +0.0269 | 1.254 pips | 0.0338 pips | 0.10x |
| 100 ticks | +0.0158 | +0.0152 | 2.811 pips | 0.0427 pips | 0.12x |

**Best: +0.1039 at 1 ticks ahead**, against a time-shifted control of +0.0003. Forward move sigma 0.27 pips.

- net of the control, worth about **0.028 pips** a trade
- crossing costs **0.35 pips** each way
- **as a taker: does NOT clear the spread**

| imbalance decile | mean move over 1 ticks | n |
|---|---|---|
| 0 | -0.0164 pips | 285,240 |
| 1 | -0.0184 pips | 425,963 |
| 2 | -0.0089 pips | 110,569 |
| 3 | +0.0007 pips | 839,465 |
| 4 | +0.0174 pips | 499,428 |
| 5 | +0.0151 pips | 209,917 |
| 6 | +0.0039 pips | 249,666 |

**Top decile minus bottom: +0.0203 pips +/- 0.0004 (46.1 sigma).** One side of that is about +0.0102 pips against 0.35 pips to cross.

## USDJPY

10,129,402 ticks. Median spread **0.40 pips**, so crossing costs **0.20 pips** each way. Imbalance sigma 0.247.

| horizon | feature | train IC | holdout IC | sign held |
|---|---|---|---|---|
| 1 ticks | imbalance | +0.0941 | +0.0480 | yes |
| 1 ticks | shuffled | -0.0003 | +0.0001 | no |
| 1 ticks | shifted | -0.0002 | +0.0010 | no |
| 5 ticks | imbalance | +0.0466 | +0.0229 | yes |
| 5 ticks | shuffled | -0.0005 | +0.0009 | no |
| 5 ticks | shifted | -0.0008 | +0.0016 | no |
| 20 ticks | imbalance | +0.0276 | +0.0085 | yes |
| 20 ticks | shuffled | -0.0003 | +0.0004 | no |
| 20 ticks | shifted | -0.0012 | +0.0013 | no |
| 100 ticks | imbalance | +0.0163 | +0.0034 | yes |
| 100 ticks | shuffled | +0.0005 | +0.0006 | yes |
| 100 ticks | shifted | -0.0006 | +0.0033 | no |

| horizon | holdout IC | net of control | fwd sigma | worth | vs half-spread |
|---|---|---|---|---|---|
| 1 ticks | +0.0480 | +0.0470 | 0.335 pips | 0.0157 pips | 0.08x |
| 5 ticks | +0.0229 | +0.0213 | 0.784 pips | 0.0167 pips | 0.08x |
| 20 ticks | +0.0085 | +0.0072 | 1.595 pips | 0.0114 pips | 0.06x |
| 100 ticks | +0.0034 | +0.0001 | 3.575 pips | 0.0004 pips | 0.00x |

**Best: +0.0480 at 1 ticks ahead**, against a time-shifted control of +0.0010. Forward move sigma 0.33 pips.

- net of the control, worth about **0.016 pips** a trade
- crossing costs **0.20 pips** each way
- **as a taker: does NOT clear the spread**

| imbalance decile | mean move over 1 ticks | n |
|---|---|---|
| 0 | -0.0045 pips | 305,183 |
| 1 | -0.0153 pips | 372,593 |
| 2 | +0.0002 pips | 1,362,730 |
| 3 | -0.0015 pips | 91,826 |
| 4 | +0.0185 pips | 337,851 |
| 5 | +0.0063 pips | 264,899 |
| 6 | -0.0022 pips | 303,738 |

**Top decile minus bottom: +0.0023 pips +/- 0.0005 (4.5 sigma).** One side of that is about +0.0011 pips against 0.20 pips to cross.

## XAUUSD

44,750,796 ticks. Median spread **6.70 pips**, so crossing costs **3.35 pips** each way. Imbalance sigma 0.201.

| horizon | feature | train IC | holdout IC | sign held |
|---|---|---|---|---|
| 1 ticks | imbalance | +0.0686 | +0.0795 | yes |
| 1 ticks | shuffled | -0.0002 | -0.0000 | yes |
| 1 ticks | shifted | -0.0001 | -0.0004 | yes |
| 5 ticks | imbalance | +0.0361 | +0.0487 | yes |
| 5 ticks | shuffled | -0.0003 | -0.0003 | yes |
| 5 ticks | shifted | -0.0001 | -0.0006 | yes |
| 20 ticks | imbalance | +0.0065 | +0.0248 | yes |
| 20 ticks | shuffled | -0.0003 | -0.0003 | yes |
| 20 ticks | shifted | +0.0000 | -0.0002 | no |
| 100 ticks | imbalance | -0.0107 | +0.0113 | no |
| 100 ticks | shuffled | -0.0002 | -0.0008 | yes |
| 100 ticks | shifted | -0.0000 | -0.0003 | yes |

| horizon | holdout IC | net of control | fwd sigma | worth | vs half-spread |
|---|---|---|---|---|---|
| 1 ticks | +0.0795 | +0.0791 | 1.650 pips | 0.1304 pips | 0.04x |
| 5 ticks | +0.0487 | +0.0481 | 3.744 pips | 0.1801 pips | 0.05x |
| 20 ticks | +0.0248 | +0.0246 | 7.518 pips | 0.1849 pips | 0.06x |
| 100 ticks | +0.0113 | +0.0111 | 16.768 pips | 0.1853 pips | 0.06x |

**Best: +0.0795 at 1 ticks ahead**, against a time-shifted control of -0.0004. Forward move sigma 1.65 pips.

- net of the control, worth about **0.130 pips** a trade
- crossing costs **3.35 pips** each way
- **as a taker: does NOT clear the spread**

| imbalance decile | mean move over 1 ticks | n |
|---|---|---|
| 0 | -0.0169 pips | 12,614,348 |
| 1 | +0.2533 pips | 810,890 |

**Top decile minus bottom: +0.2703 pips +/- 0.0017 (157.4 sigma).** One side of that is about +0.1351 pips against 3.35 pips to cross.


wrote /home/user/FutureTradingBot/research/FX_IMBALANCE.md

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


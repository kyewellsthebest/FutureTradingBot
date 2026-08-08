# Tick grammar: conditional behaviour of legs, eight NQ contracts

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

  R=4 NQH5: 2,671,656 legs [22s]
  R=4 NQH6: 2,427,366 legs [38s]
  R=4 NQM5: 3,156,190 legs [59s]
  R=4 NQM6: 3,096,643 legs [77s]
  R=4 NQU4: 2,218,222 legs [91s]
  R=4 NQU5: 1,376,299 legs [99s]
  R=4 NQZ4: 1,545,303 legs [111s]
  R=4 NQZ5: 2,312,309 legs [130s]
## R = 4 ticks -- 18,803,588 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.01, holdout -0.00 ticks

121 cells passed the train screen (|t|>=3). **99% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 1) | 87,582/71,772 | +2.53 | +35.9 | +2.96 +/- 0.08 | 3/3 | 75% | $1.48 | PASS fail |
| (1, 4, 2, 4, 2) | 602,559/447,825 | -0.80 | -34.0 | -0.82 +/- 0.03 | 3/3 | 67% | $0.41 | fail fail |
| (-1, 3, 2, 4, 2) | 162,507/107,220 | -1.38 | -32.5 | -1.78 +/- 0.06 | 3/3 | 75% | $0.89 | fail fail |
| (1, 4, 2, 4, 1) | 83,747/70,628 | +2.08 | +30.9 | +2.76 +/- 0.08 | 3/3 | 75% | $1.38 | fail fail |
| (-1, 4, 2, 4, 0) | 11,576/10,558 | +6.71 | +27.9 | +7.99 +/- 0.29 | 3/3 | 100% | $4.00 | PASS fail |
| (1, 3, 2, 4, 2) | 159,721/110,654 | -1.10 | -25.6 | -1.64 +/- 0.06 | 3/3 | 75% | $0.82 | fail fail |
| (-1, 3, 2, 3, 2) | 114,245/71,156 | -1.28 | -25.5 | -1.61 +/- 0.07 | 3/3 | 80% | $0.81 | fail fail |
| (1, 4, 2, 4, 0) | 11,015/10,575 | +6.40 | +23.3 | +8.30 +/- 0.27 | 3/3 | 100% | $4.15 | PASS fail |
| (1, 3, 2, 3, 2) | 112,070/72,823 | -1.07 | -21.0 | -1.50 +/- 0.07 | 3/3 | 80% | $0.75 | fail fail |
| (-1, 4, 2, 3, 1) | 38,129/29,698 | +2.08 | +20.7 | +2.33 +/- 0.12 | 3/3 | 80% | $1.16 | fail fail |
| (-1, 2, 1, 3, 2) | 66,087/45,799 | -1.35 | -20.2 | -1.56 +/- 0.08 | 3/3 | 80% | $0.78 | fail fail |
| (-1, 4, 2, 4, 2) | 609,381/446,783 | -0.46 | -19.9 | -0.74 +/- 0.03 | 3/3 | 67% | $0.37 | fail fail |
| (1, 4, 2, 3, 2) | 179,618/126,172 | -0.82 | -18.4 | -1.17 +/- 0.05 | 3/3 | 75% | $0.59 | fail fail |
| (-1, 3, 2, 2, 2) | 78,655/50,769 | -1.17 | -18.4 | -1.31 +/- 0.08 | 3/3 | 80% | $0.65 | fail fail |
| (-1, 4, 2, 3, 0) | 6,702/5,634 | +5.71 | +17.5 | +6.18 +/- 0.42 | 3/3 | 100% | $3.09 | PASS fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train -0.01, holdout +0.00 ticks

133 cells passed the train screen (|t|>=3). **99% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 1) | 87,582/71,772 | +4.31 | +32.8 | +5.08 +/- 0.16 | 3/3 | 75% | $2.54 | PASS fail |
| (1, 4, 2, 4, 2) | 602,559/447,825 | -1.49 | -31.9 | -1.42 +/- 0.06 | 3/3 | 67% | $0.71 | fail fail |
| (-1, 3, 2, 4, 2) | 162,507/107,220 | -2.51 | -28.6 | -3.17 +/- 0.12 | 3/3 | 75% | $1.59 | PASS fail |
| (-1, 3, 2, 3, 2) | 114,245/71,156 | -2.66 | -25.9 | -3.03 +/- 0.14 | 3/3 | 80% | $1.52 | PASS fail |
| (1, 4, 2, 4, 1) | 83,747/70,628 | +3.29 | +22.7 | +4.14 +/- 0.15 | 3/3 | 75% | $2.07 | PASS fail |
| (1, 3, 2, 4, 2) | 159,721/110,654 | -2.00 | -21.8 | -2.45 +/- 0.11 | 3/3 | 75% | $1.23 | fail fail |
| (-1, 2, 1, 3, 2) | 66,087/45,799 | -2.79 | -20.0 | -3.19 +/- 0.18 | 3/3 | 80% | $1.60 | PASS fail |
| (-1, 4, 2, 4, 0) | 11,576/10,558 | +9.60 | +19.5 | +11.83 +/- 0.59 | 3/3 | 100% | $5.92 | PASS PASS |
| (-1, 4, 2, 3, 1) | 38,129/29,698 | +3.81 | +19.3 | +4.49 +/- 0.24 | 3/3 | 80% | $2.25 | PASS fail |
| (1, 4, 2, 4, 0) | 11,015/10,575 | +9.41 | +17.9 | +11.54 +/- 0.59 | 3/3 | 100% | $5.77 | PASS PASS |
| (1, 3, 2, 3, 2) | 112,070/72,823 | -1.76 | -16.6 | -2.31 +/- 0.14 | 3/3 | 80% | $1.16 | fail fail |
| (1, 4, 2, 3, 2) | 179,618/126,172 | -1.49 | -16.5 | -1.92 +/- 0.11 | 3/3 | 75% | $0.96 | fail fail |
| (-1, 3, 2, 4, 1) | 119,561/82,214 | +1.49 | +15.6 | +1.91 +/- 0.13 | 3/3 | 80% | $0.96 | fail fail |
| (-1, 3, 1, 3, 2) | 39,311/24,120 | -2.72 | -15.3 | -3.16 +/- 0.24 | 3/3 | 100% | $1.58 | PASS fail |
| (-1, 3, 2, 2, 2) | 78,655/50,769 | -2.02 | -15.0 | -2.21 +/- 0.17 | 3/3 | 75% | $1.10 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.01, holdout +0.00 ticks

120 cells passed the train screen (|t|>=3). **100% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (1, 4, 2, 4, 2) | 602,559/447,825 | -2.56 | -24.8 | -1.99 +/- 0.13 | 3/3 | 67% | $1.00 | fail fail |
| (-1, 4, 2, 4, 1) | 87,582/71,772 | +6.53 | +22.9 | +6.58 +/- 0.34 | 3/3 | 100% | $3.29 | PASS fail |
| (-1, 3, 2, 3, 2) | 114,245/71,156 | -4.63 | -19.7 | -4.80 +/- 0.32 | 3/3 | 80% | $2.40 | PASS fail |
| (-1, 3, 2, 4, 2) | 162,507/107,220 | -3.89 | -19.1 | -4.72 +/- 0.27 | 3/3 | 67% | $2.36 | PASS fail |
| (-1, 4, 2, 4, 0) | 11,576/10,558 | +15.09 | +14.4 | +17.72 +/- 1.15 | 3/3 | 100% | $8.86 | PASS PASS |
| (-1, 2, 1, 3, 2) | 66,087/45,799 | -4.68 | -14.3 | -4.91 +/- 0.41 | 3/3 | 100% | $2.46 | PASS fail |
| (1, 4, 2, 3, 2) | 179,618/126,172 | -2.79 | -14.0 | -2.50 +/- 0.25 | 3/3 | 75% | $1.25 | fail fail |
| (1, 0, 0, 0, 0) | 319,578/273,158 | -2.08 | -13.5 | -1.16 +/- 0.17 | 3/3 | 100% | $0.58 | fail fail |
| (-1, 3, 2, 4, 1) | 119,561/82,214 | +2.78 | +13.0 | +2.20 +/- 0.29 | 3/3 | 80% | $1.10 | fail fail |
| (-1, 4, 2, 3, 1) | 38,129/29,698 | +5.58 | +12.9 | +6.00 +/- 0.52 | 3/3 | 80% | $3.00 | PASS fail |
| (-1, 3, 2, 2, 2) | 78,655/50,769 | -3.84 | -12.7 | -3.64 +/- 0.40 | 3/3 | 75% | $1.82 | PASS fail |
| (1, 1, 0, 1, 0) | 127,138/70,031 | +2.45 | +12.4 | +2.48 +/- 0.30 | 3/3 | 100% | $1.24 | fail fail |
| (1, 1, 1, 2, 0) | 24,817/8,763 | +6.33 | +12.3 | +6.44 +/- 1.04 | 3/3 | 100% | $3.22 | PASS fail |
| (1, 4, 2, 4, 0) | 11,015/10,575 | +12.76 | +11.8 | +16.25 +/- 1.14 | 3/3 | 100% | $8.13 | PASS PASS |
| (1, 3, 2, 4, 2) | 159,721/110,654 | -2.37 | -11.6 | -2.43 +/- 0.26 | 3/3 | 75% | $1.21 | fail fail |

Shuffled control: **0 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

wrote /home/user/FutureTradingBot/research/TICK_GRAMMAR.md

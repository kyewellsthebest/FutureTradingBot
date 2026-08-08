# Tick grammar: conditional behaviour of legs, eight NQ contracts

**ENTRY DELAYED 1 price change(s) past confirmation** -- the bid-ask bounce test. Bounce dies at the first change; behaviour survives it.

## R = 4 ticks -- 19,595,569 legs, 8 contracts

### horizon 50 price-changes -- population baseline train -0.04, holdout -0.04 ticks

15 cells passed the train screen (|t|>=3). **80% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 0) | 17,805/13,782 | +1.52 | +7.3 | +1.64 +/- 0.21 | 3/3 |  | $0.82 | fail fail |
| (1, 4, 2, 4, 0) | 16,453/13,238 | +1.18 | +4.7 | +1.39 +/- 0.22 | 3/3 | 0% | $0.70 | fail fail |
| (-1, 3, 2, 3, 0) | 28,738/17,421 | -0.49 | -4.6 | -0.23 +/- 0.18 | 3/3 |  | $0.11 | fail fail |
| (-1, 0, 2, 0, 2) | 25,608/25,187 | +0.69 | +4.5 | +0.00 +/- 0.14 | 2/3 | 0% | $0.00 | fail fail |
| (1, 3, 2, 4, 0) | 25,625/19,095 | -0.56 | -4.4 | -0.36 +/- 0.17 | 2/3 | 50% | $0.18 | fail fail |
| (-1, 0, 2, 0, 1) | 65,585/52,669 | +0.34 | +3.8 | -0.04 +/- 0.09 | 2/3 | 0% | $0.02 | fail fail |
| (-1, 4, 2, 3, 2) | 25,327/18,194 | -0.47 | -3.7 | -0.34 +/- 0.15 | 2/3 |  | $0.17 | fail fail |
| (1, 4, 2, 3, 0) | 7,121/5,133 | -1.29 | -3.6 | -1.62 +/- 0.43 | 3/3 | 67% | $0.81 | fail fail |
| (-1, 0, 0, 3, 2) | 1,742/1,553 | -2.49 | -3.6 | +1.09 +/- 0.63 | 1/3 |  | $0.54 | fail fail |
| (1, 3, 2, 3, 0) | 26,846/16,768 | -0.38 | -3.5 | -0.45 +/- 0.15 | 3/3 | 100% | $0.23 | fail fail |
| (1, 1, 0, 2, 0) | 33,046/18,614 | +0.31 | +3.3 | +0.16 +/- 0.14 | 3/3 |  | $0.08 | fail fail |
| (1, 4, 2, 3, 1) | 11,617/8,726 | -0.70 | -3.2 | -0.77 +/- 0.23 | 3/3 | 100% | $0.39 | fail fail |
| (-1, 4, 0, 2, 0) | 713/621 | +3.47 | +3.1 | +0.20 +/- 0.99 | 2/3 |  | $0.10 | fail fail |
| (1, 0, 0, 1, 0) | 53,442/43,022 | +0.24 | +3.0 | -0.01 +/- 0.09 | 1/3 |  | $0.01 | fail fail |
| (1, 2, 0, 0, 1) | 28,373/22,464 | +0.32 | +3.0 | +0.22 +/- 0.13 | 3/3 |  | $0.11 | fail fail |

Shuffled control: **1 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 200 price-changes -- population baseline train -0.04, holdout -0.04 ticks

6 cells passed the train screen (|t|>=3). **83% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 0) | 17,805/13,782 | +1.48 | +3.8 | +2.12 +/- 0.40 | 3/3 |  | $1.06 | fail fail |
| (-1, 1, 2, 3, 0) | 41,888/29,741 | +0.61 | +3.8 | +0.32 +/- 0.22 | 3/3 |  | $0.16 | fail fail |
| (-1, 4, 2, 4, 2) | 110,198/78,047 | +0.41 | +3.5 | +0.83 +/- 0.14 | 3/3 | 100% | $0.41 | fail fail |
| (-1, 0, 2, 0, 1) | 65,585/52,669 | +0.62 | +3.5 | -0.11 +/- 0.18 | 1/3 |  | $0.06 | fail fail |
| (-1, 4, 1, 4, 2) | 255,419/187,445 | +0.21 | +3.2 | +0.05 +/- 0.09 | 1/3 | 100% | $0.02 | fail fail |
| (1, 1, 1, 3, 1) | 18,815/13,587 | -0.68 | -3.0 | -0.04 +/- 0.30 | 2/3 |  | $0.02 | fail fail |

Shuffled control: **2 cells** pass the same screen on permuted outcomes (the false-positive floor).

### horizon 1000 price-changes -- population baseline train -0.04, holdout -0.04 ticks

9 cells passed the train screen (|t|>=3). **78% held their sign out of sample** (coin: 50%). Shuffled control below.

| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | HOLDOUT +/- se | vote | nbhd | $ gross | gates |
|---|---|---|---|---|---|---|---|---|
| (-1, 4, 2, 4, 0) | 17,805/13,782 | +3.15 | +4.1 | +3.81 +/- 0.83 | 3/3 |  | $1.91 | PASS fail |
| (-1, 4, 2, 4, 2) | 110,198/78,047 | +0.99 | +3.9 | +1.57 +/- 0.30 | 3/3 |  | $0.78 | fail fail |
| (-1, 4, 0, 2, 0) | 713/621 | +16.77 | +3.7 | +8.02 +/- 4.43 | 3/3 |  | $4.01 | PASS fail |
| (1, 4, 2, 4, 0) | 16,453/13,238 | +2.71 | +3.4 | -0.33 +/- 0.90 | 2/3 |  | $0.16 | fail fail |
| (1, 0, 2, 0, 1) | 68,117/55,084 | -1.21 | -3.2 | -1.66 +/- 0.39 | 3/3 |  | $0.83 | fail fail |
| (-1, 2, 0, 4, 2) | 8,738/9,009 | +3.93 | +3.2 | -0.57 +/- 1.03 | 1/3 | 0% | $0.29 | fail fail |
| (-1, 2, 0, 2, 1) | 50,075/34,743 | +1.18 | +3.2 | +0.02 +/- 0.43 | 2/3 |  | $0.01 | fail fail |
| (-1, 2, 0, 3, 2) | 38,712/25,913 | +1.22 | +3.1 | +0.73 +/- 0.50 | 3/3 | 0% | $0.37 | fail fail |
| (-1, 1, 2, 1, 0) | 68,088/34,325 | +0.83 | +3.1 | +1.34 +/- 0.42 | 3/3 |  | $0.67 | fail fail |

Shuffled control: **2 cells** pass the same screen on permuted outcomes (the false-positive floor).

---
Gates: $1.42 commission-only and $4.40 with the $3 slippage figure, against the FULL gross cell mean at $0.50/tick. 'vote' is contracts agreeing with the train sign, out of sample. Cells are judged against the event-population baseline at their horizon, never against zero.

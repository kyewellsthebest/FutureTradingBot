  NQH5: 2,784,919 legs, drift -0.3596 ticks per 1000 price-changes
  NQH6: 2,530,740 legs, drift -0.2032 ticks per 1000 price-changes
  NQM5: 3,296,551 legs, drift +0.3620 ticks per 1000 price-changes
  NQM6: 3,246,581 legs, drift +1.1652 ticks per 1000 price-changes
  NQU4: 2,309,009 legs, drift -0.0571 ticks per 1000 price-changes
  NQU5: 1,427,028 legs, drift +0.8028 ticks per 1000 price-changes
  NQZ4: 1,598,856 legs, drift +0.2983 ticks per 1000 price-changes
  NQZ5: 2,402,285 legs, drift +0.0643 ticks per 1000 price-changes

# Drift audit: is the NQ cell a behaviour, or is it NQ going up?

Every number is the cell's mean forward move MINUS a baseline, in ticks. The baselines absorb progressively more drift. A real behaviour survives column D; drift dies at column B, because B is the drift subtraction.

Contract drift (ticks per 1000 price-changes): NQH5 -0.360, NQH6 -0.203, NQM5 +0.362, NQM6 +1.165, NQU4 -0.057, NQU5 +0.803, NQZ4 +0.298, NQZ5 +0.064

5 of 8 contracts drifted UP. That is the bias a direction-signed cell can rent without predicting anything.

## (-1,4,2,4,0) LONG after thin down-spike

31,587 legs total, 13,782 in the held-out contracts.

| horizon | split | A global | B dir-matched | C dir x contract | D dir x contract x volume | D in $ |
|---|---|---|---|---|---|---|
| 50 | train | +1.519 | +1.505 | +1.506 | **+1.516** | **$+0.76** |
| 50 | HOLDOUT | +1.636 | +1.603 | +1.599 | **+1.608** | **$+0.80** |
| 200 | train | +1.482 | +1.408 | +1.407 | **+1.402** | **$+0.70** |
| 200 | HOLDOUT | +2.124 | +1.980 | +1.966 | **+1.946** | **$+0.97** |
| 1000 | train | +3.147 | +2.810 | +2.799 | **+2.795** | **$+1.40** |
| 1000 | HOLDOUT | +3.814 | +3.189 | +3.116 | **+3.035** | **$+1.52** |

Per contract at horizon 1000, baseline D, against that contract's own drift:

| contract | legs | edge (ticks) | contract drift/1000 | held? |
|---|---|---|---|---|
| NQH5 | 4,515 | +4.642 | -0.360 | yes |
| NQH6 | 4,070 | +1.955 | -0.203 | yes |
| NQM5 | 5,758 | +2.389 | +0.362 | yes |
| NQM6 | 6,157 | +5.072 | +1.165 | yes |
| NQU4 | 3,113 | +4.146 | -0.057 | yes |
| NQU5 | 2,302 | +0.802 | +0.803 | yes |
| NQZ4 | 2,117 | +0.136 | +0.298 | yes |
| NQZ5 | 3,555 | +0.742 | +0.064 | yes |

**8/8 contracts positive** under the strictest baseline (coin: 4.0).

## (1,4,2,4,0) SHORT after thin up-spike

29,691 legs total, 13,238 in the held-out contracts.

| horizon | split | A global | B dir-matched | C dir x contract | D dir x contract x volume | D in $ |
|---|---|---|---|---|---|---|
| 50 | train | +1.179 | +1.193 | +1.192 | **+1.198** | **$+0.60** |
| 50 | HOLDOUT | +1.393 | +1.426 | +1.429 | **+1.435** | **$+0.72** |
| 200 | train | +1.192 | +1.266 | +1.269 | **+1.281** | **$+0.64** |
| 200 | HOLDOUT | -0.064 | +0.080 | +0.092 | **+0.099** | **$+0.05** |
| 1000 | train | +2.713 | +3.050 | +3.068 | **+3.004** | **$+1.50** |
| 1000 | HOLDOUT | -0.325 | +0.300 | +0.361 | **+0.289** | **$+0.14** |

Per contract at horizon 1000, baseline D, against that contract's own drift:

| contract | legs | edge (ticks) | contract drift/1000 | held? |
|---|---|---|---|---|
| NQH5 | 4,089 | +1.232 | -0.360 | yes |
| NQH6 | 3,902 | +2.727 | -0.203 | yes |
| NQM5 | 5,736 | +6.902 | +0.362 | yes |
| NQM6 | 5,803 | -1.485 | +1.165 | NO |
| NQU4 | 2,769 | -0.515 | -0.057 | NO |
| NQU5 | 2,111 | +0.540 | +0.803 | yes |
| NQZ4 | 1,748 | +2.910 | +0.298 | yes |
| NQZ5 | 3,533 | +0.509 | +0.064 | yes |

**6/8 contracts positive** under the strictest baseline (coin: 4.0).

---
Reading it: column A is what the original study reported. If B is much smaller than A, the original number was mostly the market rising. If D is still positive and most contracts agree, there is a behaviour left, and its size in dollars is the last column -- to be compared against $1.75 all-in per round turn, not against zero.

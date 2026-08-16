# Where does 70% accuracy live, and is it worth anything?

A win rate is a property of the BRACKET, not of a strategy. For a driftless random walk the chance of touching +T before -S is exactly `S/(S+T)`, so any accuracy you want is available by choosing the geometry -- risk 20 to make 10 and you win 66.7% of the time knowing nothing at all.

The only quantity carrying information is the **gap**: measured target-first minus `S/(S+T)`. The same gap is worth the same money whether it appears as 35% on a 1:2 or 70% on a 2:1.

NQ, 4 quarters, market entry at the bar close (no fill assumption), 10-minute horizon, sampled every 5 RTH minutes. `needed` is `(S+cost)/(S+T)` at $1.33.

## UNCOND entries

| stop | target | measured | random walk | **gap vs random** | needed to pay | **shortfall** |
|---|---|---|---|---|---|---|
| 2 | 44 | 2.2% | 4.3% | **-2.12%** | 5.8% | **+3.57%** |
| 2 | 30 | 4.5% | 6.2% | **-1.71%** | 8.3% | **+3.79%** |
| 30 | 2 | 92.0% | 93.8% | **-1.75%** | 95.8% | **+3.83%** |
| 2 | 20 | 8.0% | 9.1% | **-1.12%** | 12.1% | **+4.14%** |
| 20 | 2 | 89.8% | 90.9% | **-1.13%** | 93.9% | **+4.16%** |
| 44 | 2 | 92.8% | 95.7% | **-2.82%** | 97.1% | **+4.26%** |
| 20 | 3 | 85.4% | 87.0% | **-1.59%** | 89.8% | **+4.48%** |
| 2 | 15 | 11.0% | 11.8% | **-0.77%** | 15.7% | **+4.68%** |
| 30 | 3 | 88.2% | 90.9% | **-2.73%** | 92.9% | **+4.74%** |
| 3 | 44 | 3.0% | 6.4% | **-3.42%** | 7.8% | **+4.83%** |
| 15 | 2 | 87.3% | 88.2% | **-0.95%** | 92.1% | **+4.86%** |
| 3 | 30 | 6.2% | 9.1% | **-2.85%** | 11.1% | **+4.87%** |
| 15 | 3 | 82.2% | 83.3% | **-1.18%** | 87.0% | **+4.88%** |
| 3 | 20 | 11.0% | 13.0% | **-2.00%** | 15.9% | **+4.90%** |

Geometries that clear the cost bar: **0 of 64**

Closest to a 70% win rate:

- risk 5 / make 2: **70.2%** measured, but a coin flip in that same bracket gives 71.4% and you need 80.9% to pay -- so the 70% is -1.25% of actual skill.
- risk 15 / make 5: **72.9%** measured, but a coin flip in that same bracket gives 75.0% and you need 78.3% to pay -- so the 70% is -2.06% of actual skill.
- risk 44 / make 10: **65.6%** measured, but a coin flip in that same bracket gives 81.5% and you need 82.7% to pay -- so the 70% is -15.93% of actual skill.

## IMPULSE entries

| stop | target | measured | random walk | **gap vs random** | needed to pay | **shortfall** |
|---|---|---|---|---|---|---|
| 2 | 44 | 2.3% | 4.3% | **-2.03%** | 5.8% | **+3.48%** |
| 30 | 2 | 92.2% | 93.8% | **-1.53%** | 95.8% | **+3.61%** |
| 2 | 30 | 4.5% | 6.2% | **-1.72%** | 8.3% | **+3.80%** |
| 44 | 2 | 93.1% | 95.7% | **-2.55%** | 97.1% | **+4.00%** |
| 2 | 20 | 8.1% | 9.1% | **-0.98%** | 12.1% | **+4.01%** |
| 20 | 2 | 89.9% | 90.9% | **-1.00%** | 93.9% | **+4.02%** |
| 20 | 3 | 85.8% | 87.0% | **-1.15%** | 89.8% | **+4.04%** |
| 30 | 3 | 88.7% | 90.9% | **-2.22%** | 92.9% | **+4.24%** |
| 3 | 20 | 11.7% | 13.0% | **-1.37%** | 15.9% | **+4.26%** |
| 15 | 3 | 82.7% | 83.3% | **-0.66%** | 87.0% | **+4.35%** |
| 3 | 15 | 15.9% | 16.7% | **-0.76%** | 20.4% | **+4.45%** |
| 2 | 15 | 11.2% | 11.8% | **-0.55%** | 15.7% | **+4.46%** |
| 3 | 30 | 6.6% | 9.1% | **-2.45%** | 11.1% | **+4.47%** |
| 3 | 44 | 3.3% | 6.4% | **-3.07%** | 7.8% | **+4.49%** |

Geometries that clear the cost bar: **0 of 64**

Closest to a 70% win rate:

- risk 5 / make 2: **69.3%** measured, but a coin flip in that same bracket gives 71.4% and you need 80.9% to pay -- so the 70% is -2.09% of actual skill.
- risk 44 / make 10: **67.0%** measured, but a coin flip in that same bracket gives 81.5% and you need 82.7% to pay -- so the 70% is -14.46% of actual skill.
- risk 15 / make 5: **73.8%** measured, but a coin flip in that same bracket gives 75.0% and you need 78.3% to pay -- so the 70% is -1.23% of actual skill.

## How to read this

Find the row nearest 70% measured. Then look at its random-walk column: that is what the same 70% would be worth with no information whatsoever. The gap between those two columns is the only thing any amount of research can move, and the shortfall column is how far it has to go.


## CORRECTION -- the negative gaps are the horizon, not the signal

Every gap above is negative, including the UNCONDITIONAL ones. That is
not negative skill: `S/(S+T)` is the hitting probability for a walk with
UNLIMITED time, while this measures a 10-minute window and counts a
trade that reaches neither barrier as "not target". Wide brackets time
out often, so every measured rate is biased down. Reporting the impulse
rows against `S/(S+T)` alone would have claimed the signal is worse than
a coin flip, which the baseline shows is false.

The honest comparison is IMPULSE minus UNCONDITIONAL, since both carry
the identical bias:

  bracket   impulse gap   baseline gap   signal worth
   3 / 20     -1.37%        -2.00%         +0.63 pp
  15 /  3     -0.66%        -1.18%         +0.52 pp
  30 /  3     -2.22%        -2.73%         +0.51 pp
  20 /  3     -1.15%        -1.59%         +0.44 pp
   3 / 30     -2.45%        -2.85%         +0.40 pp
   3 / 44     -3.07%        -3.42%         +0.35 pp
  44 /  2     -2.55%        -2.82%         +0.27 pp
   2 / 15     -0.55%        -0.77%         +0.22 pp
  30 /  2     -1.53%        -1.75%         +0.22 pp
   5 /  2     (70.3%)       (70.2%)        -0.90 pp

So the impulse signal IS worth something -- roughly +0.3 percentage
points against entering at a random minute, positive in most geometries.
The shortfall column says +3.5 to +4.9 points are needed. Short by about
10x.

That is the fourth independent route to the same multiple: book
imbalance 12x (BOOK_IC.md), order flow 4-8x (HFT_IC.md), the cost
arithmetic 11x, and now pure barrier geometry 10x. Different data,
different mathematics, same wall.

On the 70% question specifically: risk 5 to make 2 measures 70.2%
accuracy. A coin flip in that bracket gives 71.4% and you need 80.9% to
pay. The 70% is real and worth nothing, because it was bought with the
bracket rather than with information.

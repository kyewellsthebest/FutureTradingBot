# Are prior swing highs and lows actually attractors?

Every bracket tested before this used a fixed target and stop. This does not: the stop sits at the swing extreme just made and the target sits at a prior swing high overhead, so the distance — and the risk:reward — is different on every trade, set by structure rather than chosen.

**Each trade is judged against its own geometry.** On a random walk a trade wins `S/(S+T)` of the time however T and S were picked, so long as the future was not consulted. The column `above geometry` is the observed hit rate minus that per-trade rate, averaged. Zero means levels are just distances. Positive means price genuinely seeks them.

First touch on the real tick path across 3 held-out NQ contracts, 53,622,094 price changes.

## Swing structure at 8 points

| target | trades | median R:R | % better than 1:1 | hit rate | geometry rate | **above geometry** | $/trade gross | net of $1.99 |
|---|---|---|---|---|---|---|---|---|
| 1st level | 268,012 | 0.72:1 | 37% | 56.46% | 59.02% | **-2.56 pp** | $-0.791 | $-2.78 |
| 2nd level | 257,874 | 1.19:1 | 56% | 47.36% | 49.26% | **-1.89 pp** | $-0.732 | $-2.72 |
| 3rd level | 250,191 | 1.55:1 | 66% | 42.37% | 44.00% | **-1.63 pp** | $-0.727 | $-2.72 |

### Filtering by risk:reward — 1st level, 8-point structure

| keep trades with R:R at least | trades kept | hit rate | geometry rate | above geometry | $/trade | net |
|---|---|---|---|---|---|---|
| 0.00:1 | 268,012 | 56.46% | 59.02% | **-2.56 pp** | $-0.791 | $-2.78 |
| 0.75:1 | 130,029 | 38.81% | 40.08% | **-1.27 pp** | $-0.603 | $-2.59 |
| 1.00:1 | 102,266 | 35.11% | 36.34% | **-1.22 pp** | $-0.627 | $-2.62 |
| 1.50:1 | 62,242 | 29.39% | 30.57% | **-1.18 pp** | $-0.698 | $-2.69 |
| 2.00:1 | 37,830 | 25.53% | 26.47% | **-0.94 pp** | $-0.670 | $-2.66 |
| 3.00:1 | 13,436 | 19.83% | 20.79% | **-0.96 pp** | $-0.903 | $-2.89 |

If `above geometry` stays near zero as the filter tightens, then dropping the low-R:R setups is not improving selection — it is just changing the shape of the bet, and the hit rate falls to match exactly as geometry says it must.

## Swing structure at 12 points

| target | trades | median R:R | % better than 1:1 | hit rate | geometry rate | **above geometry** | $/trade gross | net of $1.99 |
|---|---|---|---|---|---|---|---|---|
| 1st level | 125,349 | 0.69:1 | 36% | 57.18% | 59.54% | **-2.36 pp** | $-1.134 | $-3.12 |
| 2nd level | 120,329 | 1.16:1 | 56% | 47.90% | 49.67% | **-1.77 pp** | $-1.079 | $-3.07 |
| 3rd level | 116,663 | 1.51:1 | 65% | 42.88% | 44.54% | **-1.66 pp** | $-1.144 | $-3.13 |

### Filtering by risk:reward — 1st level, 12-point structure

| keep trades with R:R at least | trades kept | hit rate | geometry rate | above geometry | $/trade | net |
|---|---|---|---|---|---|---|
| 0.00:1 | 125,349 | 57.18% | 59.54% | **-2.36 pp** | $-1.134 | $-3.12 |
| 0.75:1 | 59,757 | 38.95% | 40.35% | **-1.40 pp** | $-1.071 | $-3.06 |
| 1.00:1 | 46,612 | 35.08% | 36.56% | **-1.48 pp** | $-1.209 | $-3.20 |
| 1.50:1 | 27,842 | 29.08% | 30.73% | **-1.65 pp** | $-1.519 | $-3.51 |
| 2.00:1 | 16,575 | 25.01% | 26.54% | **-1.54 pp** | $-1.698 | $-3.69 |
| 3.00:1 | 5,669 | 18.36% | 20.78% | **-2.41 pp** | $-3.136 | $-5.13 |

If `above geometry` stays near zero as the filter tightens, then dropping the low-R:R setups is not improving selection — it is just changing the shape of the bet, and the hit rate falls to match exactly as geometry says it must.

## Swing structure at 20 points

| target | trades | median R:R | % better than 1:1 | hit rate | geometry rate | **above geometry** | $/trade gross | net of $1.99 |
|---|---|---|---|---|---|---|---|---|
| 1st level | 46,180 | 0.67:1 | 35% | 57.86% | 60.11% | **-2.25 pp** | $-1.983 | $-3.97 |
| 2nd level | 43,996 | 1.12:1 | 54% | 48.17% | 50.28% | **-2.11 pp** | $-2.533 | $-4.52 |
| 3rd level | 42,227 | 1.44:1 | 64% | 42.90% | 45.28% | **-2.38 pp** | $-3.552 | $-5.54 |

### Filtering by risk:reward — 1st level, 20-point structure

| keep trades with R:R at least | trades kept | hit rate | geometry rate | above geometry | $/trade | net |
|---|---|---|---|---|---|---|
| 0.00:1 | 46,180 | 57.86% | 60.11% | **-2.25 pp** | $-1.983 | $-3.97 |
| 0.75:1 | 21,267 | 38.50% | 40.50% | **-2.00 pp** | $-2.594 | $-4.58 |
| 1.00:1 | 16,468 | 34.49% | 36.66% | **-2.17 pp** | $-3.002 | $-4.99 |
| 1.50:1 | 9,769 | 28.20% | 30.84% | **-2.64 pp** | $-4.080 | $-6.07 |
| 2.00:1 | 5,691 | 23.62% | 26.54% | **-2.92 pp** | $-5.134 | $-7.12 |
| 3.00:1 | 1,917 | 16.59% | 20.65% | **-4.07 pp** | $-8.898 | $-10.89 |

If `above geometry` stays near zero as the filter tightens, then dropping the low-R:R setups is not improving selection — it is just changing the shape of the bet, and the hit rate falls to match exactly as geometry says it must.

---
Entry at confirmation, stop at the swing extreme just made, target at a prior swing extreme overhead. First touch resolved on the real tick sequence. Trades unresolved inside the forward horizon are dropped rather than guessed. Held-out contracts only.

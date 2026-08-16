# STEELMAN: the strategy under best-case honest assumptions

5-min setup expiry, **10-min hold from ENTRY** (earlier tests wrongly shared one 10-min window between waiting and holding), entries and targets fill on a TOUCH, stops require a print strictly THROUGH the level, and **zero commission, zero slippage**. Resting limits still require the tape to reach them from the correct side.

| w | retr | dir | anchor | n | target first | stop | neither | **EV/trade (zero cost)** |
|---|---|---|---|---|---|---|---|---|
| 4 | 0.236 | cont | close | 118,702 | 28.46% | 61.13% | 10.41% | **$-0.84** |
| 4 | 0.236 | cont | range | 117,393 | 28.43% | 61.14% | 10.43% | **$-0.86** |
| 4 | 0.236 | fade | close | 118,702 | 27.92% | 61.94% | 10.13% | **$-1.22** |
| 4 | 0.236 | fade | range | 117,393 | 27.91% | 61.65% | 10.44% | **$-1.17** |
| 4 | 0.382 | cont | close | 105,039 | 28.35% | 61.37% | 10.28% | **$-0.94** |
| 4 | 0.382 | cont | range | 107,238 | 28.27% | 61.42% | 10.31% | **$-0.98** |
| 4 | 0.382 | fade | close | 105,039 | 28.06% | 61.91% | 10.02% | **$-1.16** |
| 4 | 0.382 | fade | range | 107,238 | 28.01% | 61.81% | 10.17% | **$-1.16** |
| 4 | 0.5 | cont | close | 95,028 | 28.93% | 60.85% | 10.22% | **$-0.60** |
| 4 | 0.5 | cont | range | 94,374 | 28.89% | 60.98% | 10.13% | **$-0.64** |
| 4 | 0.5 | fade | close | 95,028 | 28.22% | 61.92% | 9.85% | **$-1.10** |
| 4 | 0.5 | fade | range | 94,374 | 28.03% | 61.98% | 9.99% | **$-1.18** |
| 4 | 0.618 | cont | close | 85,122 | 28.55% | 61.56% | 9.89% | **$-0.89** |
| 4 | 0.618 | cont | range | 79,418 | 28.68% | 61.35% | 9.97% | **$-0.80** |
| 4 | 0.618 | fade | close | 85,122 | 28.21% | 62.12% | 9.67% | **$-1.14** |
| 4 | 0.618 | fade | range | 79,418 | 27.92% | 62.37% | 9.71% | **$-1.31** |
| 6 | 0.236 | cont | close | 121,999 | 27.93% | 60.98% | 11.09% | **$-1.02** |
| 6 | 0.236 | cont | range | 119,751 | 28.05% | 60.78% | 11.18% | **$-0.94** |
| 6 | 0.236 | fade | close | 121,999 | 27.76% | 61.40% | 10.83% | **$-1.18** |
| 6 | 0.236 | fade | range | 119,751 | 27.60% | 61.24% | 11.16% | **$-1.21** |
| 6 | 0.382 | cont | close | 105,511 | 27.97% | 61.05% | 10.98% | **$-1.02** |
| 6 | 0.382 | cont | range | 107,460 | 27.62% | 61.21% | 11.17% | **$-1.19** |
| 6 | 0.382 | fade | close | 105,511 | 27.79% | 61.64% | 10.57% | **$-1.21** |
| 6 | 0.382 | fade | range | 107,460 | 27.93% | 61.19% | 10.88% | **$-1.07** |
| 6 | 0.5 | cont | close | 93,627 | 28.47% | 60.72% | 10.81% | **$-0.76** |
| 6 | 0.5 | cont | range | 92,361 | 28.25% | 60.83% | 10.92% | **$-0.87** |
| 6 | 0.5 | fade | close | 93,627 | 27.83% | 61.78% | 10.39% | **$-1.22** |
| 6 | 0.5 | fade | range | 92,361 | 27.88% | 61.50% | 10.62% | **$-1.15** |
| 6 | 0.618 | cont | close | 82,338 | 28.28% | 61.36% | 10.36% | **$-0.96** |
| 6 | 0.618 | cont | range | 75,142 | 28.29% | 61.10% | 10.62% | **$-0.91** |
| 6 | 0.618 | fade | close | 82,338 | 27.95% | 62.02% | 10.03% | **$-1.22** |
| 6 | 0.618 | fade | range | 75,142 | 27.83% | 61.93% | 10.24% | **$-1.26** |

Best: cont w=4 retr=0.5 anchor=close -> **$-0.60/trade** at zero cost (28.93% target-first, 95,028 trades).

A positive row here is a real candidate and gets the full validation. Every row negative means no cost structure or execution quality can make this family profitable.


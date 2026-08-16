# Is the range-anchored FADE edge real, or wrong-side fills?

NQ, 8 quarters, FADE direction, bracket 10/20, breakeven **35.2%** target-first.

- **matrix** = what the premise matrix measured (instant fill at the level when the tape prints past it)
- **ABOVE** = level on the far side of the market: a resting limit is legitimate, and must be reached by an actual trade
- **BELOW** = level already behind the market: market order, entry at the triggering print

| w | retr | case | n | target first | EV/trade |
|---|---|---|---|---|---|
| 6 | 0.236 | matrix | 139,387 | 37.22% | $+3.39 |
| 6 | 0.236 | ABOVE | 53,176 | 26.23% | $-3.03 |
| 6 | 0.236 | BELOW | 75,240 | 25.88% | $-3.23 |
| 4 | 0.236 | matrix | 132,474 | 35.90% | $+2.40 |
| 4 | 0.236 | ABOVE | 49,805 | 27.01% | $-2.94 |
| 4 | 0.236 | BELOW | 74,481 | 26.30% | $-3.16 |
| 6 | 0.382 | matrix | 123,489 | 31.42% | $+0.27 |
| 6 | 0.382 | ABOVE | 26,933 | 27.71% | $-2.65 |
| 6 | 0.382 | BELOW | 92,404 | 25.08% | $-3.30 |
| 6 | 0.618 | matrix | 93,652 | 25.80% | $-2.30 |
| 6 | 0.618 | ABOVE | 4,953 | 28.67% | $-3.01 |
| 6 | 0.618 | BELOW | 88,250 | 23.59% | $-3.64 |


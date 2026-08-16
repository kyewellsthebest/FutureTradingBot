# The strategy's premise, measured without my engine

NQ, 8 quarters, impulse >= 5pt over 6 bars, retracement 0.618, bracket 10/20, 10-min horizon. No windows, no lockout, no position management -- just: from the tick that touches the level, which side of the bracket does price reach first?

| set | n | target first | stop first | neither | EV/trade |
|---|---|---|---|---|---|
| **SIGNAL** (0.618 pullback) | 99,492 | 24.63% | 56.46% | 18.91% | $-3.06 |
| BASELINE (random RTH ticks) | 99,492 | 30.04% | 62.88% | 7.08% | $-2.15 |

- random-walk expectation for a 10/20 bracket: **33.3%**
- breakeven with \$1.24 commission + 1 tick stop slip: **35.2%**
- measured edge of signal over random ticks: **-5.41 percentage points**

**The signal does not clear breakeven; it is at or below random-tick selection but not by enough to pay the cost stack.**


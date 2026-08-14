# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.5 | 6 | 0.618 | 3.0 | 6.0 | cont | +7,295 | **+5,976** | 4250 | 136 | 6/6 |
| 1.5 | 6 | 0.5 | 3.0 | 6.0 | cont | +6,282 | **+794** | 4378 | 140 | 3/6 |
| 2.4 | 6 | 0.618 | 3.0 | 6.0 | cont | +4,613 | **+5,411** | 3668 | 118 | 5/6 |
| 1.5 | 6 | 0.618 | 1.7999999999999998 | 6.0 | cont | +4,365 | **+2,922** | 4250 | 136 | 6/6 |
| 2.4 | 6 | 0.5 | 3.0 | 6.0 | cont | +4,234 | **+3,242** | 3848 | 123 | 5/6 |
| 1.5 | 6 | 0.618 | 3.0 | 3.5999999999999996 | cont | +4,145 | **+2,814** | 4250 | 136 | 6/6 |
| 1.5 | 6 | 0.5 | 3.0 | 3.5999999999999996 | cont | +3,385 | **+236** | 4378 | 140 | 4/6 |
| 2.4 | 4 | 0.618 | 3.0 | 6.0 | cont | +3,201 | **+4,532** | 3614 | 116 | 5/6 |
| 1.5 | 6 | 0.5 | 1.7999999999999998 | 6.0 | cont | +3,131 | **-1,376** | 4378 | 140 | 2/6 |
| 2.4 | 6 | 0.5 | 3.0 | 3.5999999999999996 | cont | +2,761 | **+1,431** | 3848 | 123 | 5/6 |

Top-by-train cell held-out: **$+5,976** over 4250 trades (136/wk). Per quarter:

- ESZ4: $+534 on 655
- ESH5: $+1,490 on 724
- ESU5: $+345 on 665
- ESZ5: $+1,293 on 728
- ESH6: $+1,408 on 761
- ESM6: $+907 on 717

## Anatomy (held-out, top cell)

- outcomes: target 24%, stop 35%, timeout 41%
- win rate 46.7%, avg win $+18.95, avg loss $-13.96
- 161 trading days: 65% green, best $+329, worst $-194
- **max drawdown $340** (8.3% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


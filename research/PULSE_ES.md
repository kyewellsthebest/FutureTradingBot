# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.5 | 6 | 0.618 | 3.0 | 6.0 | cont | +8,766 | **+7,385** | 4250 | 136 | 6/6 |
| 1.5 | 6 | 0.5 | 3.0 | 6.0 | cont | +7,255 | **+1,827** | 4378 | 140 | 4/6 |
| 1.5 | 6 | 0.618 | 1.7999999999999998 | 6.0 | cont | +6,300 | **+4,756** | 4250 | 136 | 6/6 |
| 2.4 | 6 | 0.618 | 3.0 | 6.0 | cont | +6,045 | **+6,599** | 3668 | 118 | 6/6 |
| 1.5 | 6 | 0.5 | 1.7999999999999998 | 6.0 | cont | +5,739 | **+910** | 4378 | 140 | 3/6 |
| 1.5 | 6 | 0.618 | 3.0 | 3.5999999999999996 | cont | +5,523 | **+4,060** | 4250 | 136 | 6/6 |
| 2.4 | 6 | 0.5 | 3.0 | 6.0 | cont | +5,109 | **+4,066** | 3848 | 123 | 5/6 |
| 2.4 | 4 | 0.618 | 3.0 | 6.0 | cont | +4,688 | **+5,941** | 3614 | 116 | 5/6 |
| 1.5 | 6 | 0.5 | 3.0 | 3.5999999999999996 | cont | +4,291 | **+1,134** | 4378 | 140 | 4/6 |
| 2.4 | 6 | 0.618 | 1.7999999999999998 | 6.0 | cont | +4,026 | **+4,253** | 3668 | 118 | 6/6 |

Top-by-train cell held-out: **$+7,385** over 4250 trades (136/wk). Per quarter:

- ESZ4: $+655 on 655
- ESH5: $+1,768 on 724
- ESU5: $+492 on 665
- ESZ5: $+1,526 on 728
- ESH6: $+1,708 on 761
- ESM6: $+1,235 on 717

## Anatomy (held-out, top cell)

- outcomes: target 24%, stop 35%, timeout 41%
- win rate 46.7%, avg win $+18.95, avg loss $-13.34
- 161 trading days: 68% green, best $+334, worst $-186
- **max drawdown $318** (7.8% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 5.0 | 6 | 0.618 | 10.0 | 20.0 | cont | +36,919 | **+23,561** | 5908 | 142 | 8/8 |
| 8.0 | 6 | 0.618 | 10.0 | 20.0 | cont | +35,604 | **+23,146** | 5529 | 133 | 8/8 |
| 5.0 | 4 | 0.618 | 10.0 | 20.0 | cont | +30,951 | **+18,457** | 6049 | 145 | 8/8 |
| 8.0 | 6 | 0.5 | 10.0 | 20.0 | cont | +30,558 | **+20,500** | 5766 | 139 | 8/8 |
| 8.0 | 4 | 0.618 | 10.0 | 20.0 | cont | +30,400 | **+19,472** | 5575 | 134 | 8/8 |
| 5.0 | 6 | 0.5 | 10.0 | 20.0 | cont | +28,621 | **+19,100** | 6099 | 147 | 8/8 |
| 5.0 | 6 | 0.618 | 6.0 | 20.0 | cont | +28,102 | **+17,806** | 5908 | 142 | 8/8 |
| 8.0 | 4 | 0.5 | 10.0 | 20.0 | cont | +27,306 | **+17,806** | 5752 | 138 | 8/8 |
| 8.0 | 6 | 0.618 | 6.0 | 20.0 | cont | +26,290 | **+16,172** | 5529 | 133 | 8/8 |
| 5.0 | 4 | 0.5 | 10.0 | 20.0 | cont | +25,079 | **+12,626** | 6178 | 149 | 8/8 |

Top-by-train cell held-out: **$+23,561** over 5908 trades (142/wk). Per quarter:

- NQU4: $+2,868 on 745
- NQZ4: $+3,053 on 725
- NQH5: $+3,723 on 756
- NQM5: $+2,203 on 725
- NQU5: $+2,341 on 704
- NQZ5: $+3,273 on 743
- NQH6: $+3,172 on 772
- NQM6: $+2,929 on 738

## Anatomy (held-out, top cell)

- outcomes: target 31%, stop 44%, timeout 25%
- win rate 47.1%, avg win $+29.99, avg loss $-19.20
- 215 trading days: 75% green, best $+536, worst $-221
- **max drawdown $280** (6.8% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


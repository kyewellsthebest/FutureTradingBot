# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 5.0 | 6 | 0.618 | 10.0 | 20.0 | cont | +33,555 | **+20,701** | 5908 | 142 | 8/8 |
| 8.0 | 6 | 0.618 | 10.0 | 20.0 | cont | +32,414 | **+20,503** | 5529 | 133 | 8/8 |
| 8.0 | 6 | 0.5 | 10.0 | 20.0 | cont | +27,630 | **+17,985** | 5766 | 139 | 8/8 |
| 5.0 | 4 | 0.618 | 10.0 | 20.0 | cont | +27,340 | **+15,530** | 6049 | 145 | 8/8 |
| 8.0 | 4 | 0.618 | 10.0 | 20.0 | cont | +27,193 | **+16,596** | 5575 | 134 | 8/8 |
| 5.0 | 6 | 0.5 | 10.0 | 20.0 | cont | +25,519 | **+16,537** | 6099 | 147 | 8/8 |
| 8.0 | 4 | 0.5 | 10.0 | 20.0 | cont | +24,336 | **+15,163** | 5752 | 138 | 8/8 |
| 5.0 | 6 | 0.618 | 6.0 | 20.0 | cont | +23,915 | **+14,304** | 5908 | 142 | 8/8 |
| 8.0 | 6 | 0.618 | 6.0 | 20.0 | cont | +22,409 | **+12,835** | 5529 | 133 | 8/8 |
| 5.0 | 6 | 0.618 | 10.0 | 12.0 | cont | +22,101 | **+11,926** | 5908 | 142 | 8/8 |

Top-by-train cell held-out: **$+20,701** over 5908 trades (142/wk). Per quarter:

- NQU4: $+2,590 on 745
- NQZ4: $+2,841 on 725
- NQH5: $+3,355 on 756
- NQM5: $+1,832 on 725
- NQU5: $+2,086 on 704
- NQZ5: $+2,945 on 743
- NQH6: $+2,662 on 772
- NQM6: $+2,391 on 738

## Anatomy (held-out, top cell)

- outcomes: target 31%, stop 44%, timeout 25%
- win rate 47.1%, avg win $+29.99, avg loss $-20.11
- 215 trading days: 72% green, best $+521, worst $-250
- **max drawdown $393** (9.6% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


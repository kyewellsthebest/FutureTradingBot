# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 5.0 | 6 | 0.618 | 10.0 | 20.0 | FADE | +144,468 | **+101,119** | 5281 | 127 | 8/8 |
| 5.0 | 6 | 0.618 | 10.0 | 20.0 | cont | -421,819 | **-319,669** | 5281 | 127 | 0/8 |

Top-by-train cell held-out: **$+101,119** over 5281 trades (127/wk). Per quarter:

- NQU4: $+11,637 on 649
- NQZ4: $+11,681 on 644
- NQH5: $+13,371 on 676
- NQM5: $+11,127 on 647
- NQU5: $+10,850 on 636
- NQZ5: $+13,658 on 671
- NQH6: $+15,030 on 693
- NQM6: $+13,765 on 665

## Anatomy (held-out, top cell)

- outcomes: target 62%, stop 24%, timeout 14%
- win rate 69.8%, avg win $+35.83, avg loss $-19.41
- 215 trading days: 99% green, best $+795, worst $-23
- **max drawdown $23** (0.6% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


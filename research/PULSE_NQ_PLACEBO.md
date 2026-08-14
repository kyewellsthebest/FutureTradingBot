# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 5.0 | 4 | 0.5 | 6.0 | 20.0 | FADE | +161,319 | **+116,966** | 5516 | 133 | 8/8 |
| 5.0 | 4 | 0.618 | 6.0 | 20.0 | FADE | +157,477 | **+114,625** | 5473 | 132 | 8/8 |
| 5.0 | 4 | 0.5 | 10.0 | 20.0 | FADE | +157,351 | **+115,133** | 5516 | 133 | 8/8 |
| 5.0 | 4 | 0.618 | 10.0 | 20.0 | FADE | +154,308 | **+112,082** | 5473 | 132 | 8/8 |
| 5.0 | 6 | 0.5 | 6.0 | 20.0 | FADE | +150,706 | **+107,182** | 5347 | 129 | 8/8 |
| 5.0 | 6 | 0.5 | 10.0 | 20.0 | FADE | +147,657 | **+105,434** | 5347 | 129 | 8/8 |
| 5.0 | 6 | 0.618 | 6.0 | 20.0 | FADE | +147,021 | **+103,806** | 5281 | 127 | 8/8 |
| 5.0 | 6 | 0.618 | 10.0 | 20.0 | FADE | +144,468 | **+101,119** | 5281 | 127 | 8/8 |
| 8.0 | 4 | 0.5 | 6.0 | 20.0 | FADE | +141,817 | **+102,277** | 4992 | 120 | 8/8 |
| 8.0 | 4 | 0.618 | 6.0 | 20.0 | FADE | +137,782 | **+100,139** | 4934 | 119 | 8/8 |

Top-by-train cell held-out: **$+116,966** over 5516 trades (133/wk). Per quarter:

- NQU4: $+13,742 on 684
- NQZ4: $+13,858 on 668
- NQH5: $+16,340 on 708
- NQM5: $+13,452 on 668
- NQU5: $+12,222 on 665
- NQZ5: $+15,466 on 701
- NQH6: $+16,483 on 726
- NQM6: $+15,404 on 696

## Anatomy (held-out, top cell)

- outcomes: target 64%, stop 28%, timeout 8%
- win rate 69.4%, avg win $+36.63, avg loss $-13.75
- 215 trading days: 100% green, best $+909, worst $+7
- **max drawdown $0** (0.0% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


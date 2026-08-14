# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.88 | 6 | 0.618 | 1.1 | 2.2 | cont | -6,602 | **-4,803** | 5657 | 136 | 0/8 |
| 0.88 | 4 | 0.618 | 1.1 | 2.2 | cont | -7,270 | **-6,217** | 5753 | 138 | 0/8 |
| 0.55 | 6 | 0.618 | 1.1 | 2.2 | cont | -7,284 | **-5,560** | 5922 | 142 | 0/8 |
| 0.55 | 4 | 0.618 | 1.1 | 2.2 | cont | -7,436 | **-6,980** | 6088 | 146 | 0/8 |
| 0.88 | 6 | 0.5 | 1.1 | 2.2 | cont | -8,218 | **-6,599** | 5864 | 141 | 0/8 |
| 0.88 | 6 | 0.618 | 1.1 | 1.32 | cont | -8,523 | **-6,315** | 5657 | 136 | 0/8 |
| 0.55 | 6 | 0.5 | 1.1 | 2.2 | cont | -9,025 | **-7,843** | 6092 | 147 | 0/8 |
| 0.55 | 6 | 0.618 | 1.1 | 1.32 | cont | -9,267 | **-6,734** | 5922 | 142 | 0/8 |
| 0.88 | 4 | 0.618 | 1.1 | 1.32 | cont | -9,298 | **-7,904** | 5753 | 138 | 0/8 |
| 0.88 | 4 | 0.5 | 1.1 | 2.2 | cont | -9,310 | **-7,932** | 5917 | 142 | 0/8 |

Top-by-train cell held-out: **$-4,803** over 5657 trades (136/wk). Per quarter:

- RTYU4: $-449 on 708
- RTYZ4: $-336 on 703
- RTYH5: $-634 on 717
- RTYM5: $-532 on 668
- RTYU5: $-1,153 on 681
- RTYZ5: $-697 on 709
- RTYH6: $-522 on 752
- RTYM6: $-481 on 719

## Anatomy (held-out, top cell)

- outcomes: target 32%, stop 45%, timeout 23%
- win rate 41.5%, avg win $+8.18, avg loss $-7.26
- 215 trading days: 26% green, best $+109, worst $-137
- **max drawdown $4,818** (117.5% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


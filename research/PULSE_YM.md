# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 16.0 | 6 | 0.618 | 20.0 | 40.0 | cont | +6,104 | **+3,212** | 5192 | 125 | 7/8 |
| 10.0 | 6 | 0.618 | 20.0 | 40.0 | cont | +5,214 | **+3,874** | 5771 | 139 | 6/8 |
| 10.0 | 4 | 0.618 | 20.0 | 40.0 | cont | +4,528 | **+98** | 5868 | 141 | 3/8 |
| 16.0 | 4 | 0.618 | 20.0 | 40.0 | cont | +4,055 | **+1,113** | 5167 | 124 | 6/8 |
| 16.0 | 6 | 0.5 | 20.0 | 40.0 | cont | +3,520 | **+1,035** | 5414 | 130 | 5/8 |
| 16.0 | 4 | 0.5 | 20.0 | 40.0 | cont | +3,189 | **-339** | 5372 | 129 | 3/8 |
| 10.0 | 6 | 0.5 | 20.0 | 40.0 | cont | +3,012 | **+1,422** | 5959 | 143 | 5/8 |
| 16.0 | 6 | 0.618 | 20.0 | 24.0 | cont | +2,780 | **+125** | 5192 | 125 | 4/8 |
| 16.0 | 6 | 0.618 | 12.0 | 40.0 | cont | +2,471 | **+1,386** | 5192 | 125 | 5/8 |
| 10.0 | 6 | 0.618 | 12.0 | 40.0 | cont | +1,814 | **+2,043** | 5771 | 139 | 5/8 |

Top-by-train cell held-out: **$+3,212** over 5192 trades (125/wk). Per quarter:

- YMU4: $+387 on 639
- YMZ4: $+28 on 594
- YMH5: $+644 on 673
- YMM5: $+39 on 642
- YMU5: $-36 on 611
- YMZ5: $+1,037 on 650
- YMH6: $+971 on 714
- YMM6: $+143 on 669

## Anatomy (held-out, top cell)

- outcomes: target 24%, stop 36%, timeout 40%
- win rate 45.8%, avg win $+12.71, avg loss $-9.60
- 215 trading days: 56% green, best $+184, worst $-145
- **max drawdown $398** (9.7% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


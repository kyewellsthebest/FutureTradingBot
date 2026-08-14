# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 16.0 | 6 | 0.618 | 20.0 | 40.0 | cont | +8,209 | **+4,688** | 5192 | 125 | 8/8 |
| 10.0 | 6 | 0.618 | 20.0 | 40.0 | cont | +7,560 | **+5,520** | 5771 | 139 | 8/8 |
| 10.0 | 4 | 0.618 | 20.0 | 40.0 | cont | +6,886 | **+1,802** | 5868 | 141 | 6/8 |
| 16.0 | 4 | 0.618 | 20.0 | 40.0 | cont | +6,113 | **+2,594** | 5167 | 124 | 7/8 |
| 16.0 | 6 | 0.5 | 20.0 | 40.0 | cont | +5,733 | **+2,587** | 5414 | 130 | 6/8 |
| 10.0 | 6 | 0.5 | 20.0 | 40.0 | cont | +5,440 | **+3,134** | 5959 | 143 | 7/8 |
| 16.0 | 4 | 0.5 | 20.0 | 40.0 | cont | +5,323 | **+1,205** | 5372 | 129 | 5/8 |
| 16.0 | 6 | 0.618 | 12.0 | 40.0 | cont | +4,688 | **+2,939** | 5192 | 125 | 7/8 |
| 16.0 | 6 | 0.618 | 20.0 | 24.0 | cont | +4,400 | **+1,284** | 5192 | 125 | 5/8 |
| 10.0 | 6 | 0.618 | 12.0 | 40.0 | cont | +4,285 | **+3,769** | 5771 | 139 | 8/8 |

Top-by-train cell held-out: **$+4,688** over 5192 trades (125/wk). Per quarter:

- YMU4: $+575 on 639
- YMZ4: $+214 on 594
- YMH5: $+817 on 673
- YMM5: $+235 on 642
- YMU5: $+157 on 611
- YMZ5: $+1,207 on 650
- YMH6: $+1,151 on 714
- YMM6: $+333 on 669

## Anatomy (held-out, top cell)

- outcomes: target 24%, stop 36%, timeout 40%
- win rate 46.6%, avg win $+12.66, avg loss $-9.37
- 215 trading days: 61% green, best $+190, worst $-136
- **max drawdown $300** (7.3% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


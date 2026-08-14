# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 4.0 | 6 | 0.618 | 14.0 | 28.0 | cont | +47,999 | **+28,365** | 6003 | 144 | 8/8 |
| 4.0 | 6 | 0.618 | 12.0 | 28.0 | cont | +46,433 | **+25,734** | 6003 | 144 | 8/8 |
| 5.0 | 6 | 0.618 | 14.0 | 28.0 | cont | +45,871 | **+30,872** | 5908 | 142 | 8/8 |
| 5.0 | 6 | 0.618 | 12.0 | 28.0 | cont | +44,753 | **+28,779** | 5908 | 142 | 8/8 |
| 8.0 | 6 | 0.618 | 14.0 | 28.0 | cont | +44,205 | **+29,742** | 5529 | 133 | 8/8 |
| 4.0 | 6 | 0.786 | 14.0 | 28.0 | cont | +44,118 | **+28,185** | 5771 | 139 | 8/8 |
| 6.5 | 6 | 0.618 | 14.0 | 28.0 | cont | +44,044 | **+28,813** | 5734 | 138 | 8/8 |
| 4.0 | 6 | 0.618 | 14.0 | 24.0 | cont | +43,642 | **+24,291** | 6003 | 144 | 8/8 |
| 6.5 | 6 | 0.786 | 14.0 | 28.0 | cont | +43,447 | **+29,529** | 5444 | 131 | 8/8 |
| 5.0 | 6 | 0.786 | 14.0 | 28.0 | cont | +43,131 | **+30,236** | 5645 | 136 | 8/8 |

Top-by-train cell held-out: **$+28,365** over 6003 trades (144/wk). Per quarter:

- NQU4: $+3,271 on 762
- NQZ4: $+2,518 on 737
- NQH5: $+4,597 on 768
- NQM5: $+2,412 on 732
- NQU5: $+2,335 on 724
- NQZ5: $+4,492 on 755
- NQH6: $+4,702 on 780
- NQM6: $+4,038 on 745

## Anatomy (held-out, top cell)

- outcomes: target 24%, stop 36%, timeout 40%
- win rate 49.1%, avg win $+35.42, avg loss $-24.88
- 215 trading days: 77% green, best $+733, worst $-334
- **max drawdown $469** (11.4% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


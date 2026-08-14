# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.03 | 6 | 0.618 | 0.06 | 0.12 | cont | -2,480 | **-1,946** | 1447 | 138 | 0/3 |
| 0.048 | 6 | 0.618 | 0.06 | 0.12 | cont | -2,513 | **-1,682** | 1363 | 130 | 0/3 |
| 0.048 | 6 | 0.5 | 0.06 | 0.12 | cont | -2,936 | **-2,230** | 1413 | 135 | 0/3 |
| 0.048 | 6 | 0.5 | 0.036000000000000004 | 0.12 | cont | -3,074 | **-2,858** | 1413 | 135 | 0/3 |
| 0.03 | 6 | 0.618 | 0.036000000000000004 | 0.12 | cont | -3,114 | **-2,707** | 1447 | 138 | 0/3 |
| 0.048 | 6 | 0.618 | 0.036000000000000004 | 0.12 | cont | -3,155 | **-2,501** | 1363 | 130 | 0/3 |
| 0.048 | 4 | 0.618 | 0.06 | 0.12 | cont | -3,161 | **-2,023** | 1376 | 131 | 0/3 |
| 0.048 | 6 | 0.618 | 0.06 | 0.07200000000000001 | cont | -3,165 | **-2,029** | 1363 | 130 | 0/3 |
| 0.048 | 6 | 0.5 | 0.06 | 0.07200000000000001 | cont | -3,286 | **-2,458** | 1413 | 135 | 0/3 |
| 0.03 | 6 | 0.618 | 0.06 | 0.07200000000000001 | cont | -3,321 | **-2,308** | 1447 | 138 | 0/3 |

Top-by-train cell held-out: **$-1,946** over 1447 trades (138/wk). Per quarter:

- CLU4: $-471 on 469
- CLZ4: $-647 on 504
- CLM6: $-828 on 474

## Anatomy (held-out, top cell)

- outcomes: target 30%, stop 48%, timeout 22%
- win rate 39.9%, avg win $+8.90, avg loss $-8.14
- 52 trading days: 23% green, best $+76, worst $-182
- **max drawdown $2,089** (50.9% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


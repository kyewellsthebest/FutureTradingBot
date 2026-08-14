# Pullback-after-impulse, tick-true, both directions

The 2025 ship's family (impulse -> retracement limit -> bracket) with honest fills: entry only when the tape trades through the limit, one tick slippage on stops, strict penetration on targets, $1.24/side commission. 64 cells, 8 NQ quarters.

| imp | w | retr | S | T | dir | train $ | **held-out $** | ho trades | ho tr/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|
| 16.0 | 6 | 0.618 | 20.0 | 40.0 | cont | -140,106 | **-97,439** | 4517 | 109 | 0/8 |

Top-by-train cell held-out: **$-97,439** over 4517 trades (109/wk). Per quarter:

- YMU4: $-10,349 on 535
- YMZ4: $-8,077 on 532
- YMH5: $-15,003 on 578
- YMM5: $-9,112 on 532
- YMU5: $-8,739 on 544
- YMZ5: $-12,709 on 563
- YMH6: $-19,679 on 648
- YMM6: $-13,771 on 585

## Anatomy (held-out, top cell)

- outcomes: target 10%, stop 72%, timeout 19%
- win rate 20.2%, avg win $+12.02, avg loss $-30.09
- 215 trading days: 0% green, best $-18, worst $-1,288
- **max drawdown $97,211** (2371.0% of the $4,100 account)

Random-walk baseline for a 10/20 bracket is 33.3% target-first; the bar above breakeven-with-costs is ~35.5%. The measured rate against those two numbers IS the edge.


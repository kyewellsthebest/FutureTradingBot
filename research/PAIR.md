# NQ-ES pair reconvergence, validated

Rolling-beta spread z-score, enter |z| at threshold, exit at 0 / stop / timeout. Both legs charged taker costs ($5.98/round trip). Grid of 16 cells; train 60% / test 40% per quarter; the cell is chosen on TRAIN totals only.

| W | Z | z-in | train $ | train n | **test $** | test n | test green q |
|---|---|---|---|---|---|---|---|
| 120 | 240 | 3.5 | -1,891 | 169 | **-2,421** | 127 | 2/6 **<-** |
| 120 | 240 | 2.5 | -2,890 | 382 | **-1,780** | 243 | 2/6 |
| 120 | 240 | 3.0 | -2,947 | 264 | **-1,457** | 181 | 3/6 |
| 120 | 120 | 3.5 | -3,087 | 318 | **-3,084** | 220 | 1/6 |
| 240 | 240 | 3.5 | -3,603 | 328 | **-2,485** | 224 | 2/6 |
| 120 | 120 | 3.0 | -4,895 | 478 | **-2,386** | 321 | 1/6 |
| 120 | 240 | 2.0 | -5,022 | 537 | **-3,351** | 359 | 1/6 |
| 240 | 240 | 3.0 | -5,843 | 421 | **-4,953** | 293 | 1/6 |

Chosen on train: W=120 Z=240 zin=3.5 -> test **$-2,421** over 127 trades ($-19.06/trade), green in 2/6 quarters.

Per-quarter test P&L of the chosen cell:

- NQZ4: $-441 on 26 trades
- NQH5: $+588 on 17 trades
- NQU5: $+203 on 18 trades
- NQZ5: $-700 on 25 trades
- NQH6: $-681 on 18 trades
- NQM6: $-1,388 on 23 trades

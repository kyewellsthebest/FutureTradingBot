# Trade replay of the discovered cell -- R=4, hold 200 price changes

47,059 non-overlapping trades over 623 trading days (2024-06-21 to 2026-06-18). Signals during an open trade were skipped, entry one price change after confirmation, bins from the five training contracts only.

## HELD-OUT ERA (Dec 2025 - Jun 2026, never trained on) -- cost $1.75/trade

| metric | value |
|---|---|
| trades | 20,724 (88.6/day) |
| win rate | 46.4% |
| avg winner / avg loser | $+14.71 / $-15.50 |
| expectancy per trade | $-1.47 |
| avg MAE (worst moment in a trade) | -27.9 ticks ($-13.94) |
| **average day** | **$-130.20** |
| positive days | 64/234 (27%) |
| average winning day / losing day | $+81.38 / $-209.85 |
| best day / WORST day | $+533.75 / **$-1456.25** |
| **average week** | **$-761.67** |
| positive weeks | 2/40 (5%) |
| avg winning week / losing week | $+84.62 / $-806.22 |
| best week / WORST week | $+134.25 / **$-2496.75** |
| max drawdown (equity, 1 micro) | $-30792.75 |
| longest losing streak | 17 trades |

## training era (mid-2024 - late-2025) -- cost $1.75/trade

| metric | value |
|---|---|
| trades | 26,335 (67.7/day) |
| win rate | 46.2% |
| avg winner / avg loser | $+14.21 / $-14.37 |
| expectancy per trade | $-1.17 |
| avg MAE (worst moment in a trade) | -26.0 ticks ($-13.00) |
| **average day** | **$-79.36** |
| positive days | 108/389 (28%) |
| average winning day / losing day | $+86.31 / $-143.03 |
| best day / WORST day | $+889.00 / **$-1103.00** |
| **average week** | **$-467.72** |
| positive weeks | 6/66 (9%) |
| avg winning week / losing week | $+225.08 / $-537.00 |
| best week / WORST week | $+987.25 / **$-1905.25** |
| max drawdown (equity, 1 micro) | $-31152.75 |
| longest losing streak | 15 trades |

## HELD-OUT ERA (Dec 2025 - Jun 2026, never trained on) -- cost $4.40/trade

| metric | value |
|---|---|
| trades | 20,724 (88.6/day) |
| win rate | 40.7% |
| avg winner / avg loser | $+13.95 / $-16.54 |
| expectancy per trade | $-4.12 |
| avg MAE (worst moment in a trade) | -27.9 ticks ($-13.94) |
| **average day** | **$-364.90** |
| positive days | 24/234 (10%) |
| average winning day / losing day | $+58.65 / $-413.30 |
| best day / WORST day | $+357.30 / **$-2137.30** |
| **average week** | **$-2134.64** |
| positive weeks | 0/40 (0%) |
| avg winning week / losing week | $+nan / $-2134.64 |
| best week / WORST week | $-65.70 / **$-6755.30** |
| max drawdown (equity, 1 micro) | $-85647.50 |
| longest losing streak | 24 trades |

## training era (mid-2024 - late-2025) -- cost $4.40/trade

| metric | value |
|---|---|
| trades | 26,335 (67.7/day) |
| win rate | 39.9% |
| avg winner / avg loser | $+13.62 / $-15.38 |
| expectancy per trade | $-3.82 |
| avg MAE (worst moment in a trade) | -26.0 ticks ($-13.00) |
| **average day** | **$-258.76** |
| positive days | 41/389 (11%) |
| average winning day / losing day | $+56.91 / $-295.95 |
| best day / WORST day | $+592.20 / **$-2195.90** |
| **average week** | **$-1525.11** |
| positive weeks | 1/66 (2%) |
| avg winning week / losing week | $+5.50 / $-1548.65 |
| best week / WORST week | $+5.50 / **$-8395.10** |
| max drawdown (equity, 1 micro) | $-100827.00 |
| longest losing streak | 21 trades |

Day boundaries are UTC dates; MAE is the lowest point inside the trade before exit. One micro contract throughout. Costs are round-turn, charged once per trade.

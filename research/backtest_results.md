# Comprehensive Backtest Battery — MNQ Inverse-Fade Pullback Bot
Generated: 2026-06-22T09:16:20.946217
Strategy: INVERSE pullback fade (STRAT_INVERT=1), 1 MNQ, marketable LIMIT entries, stop-MARKET exits (0.5pt slip), LIMIT targets (exact fill), 10s cooldown, $0.74 round-trip commission.
## 60-day subset results
| Variant | Trades | WR | P&L $ | $/day | $/trade | Trades/day | Max DD | Worst day | Best day | Sharpe-ish |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HTF_k60 | 2,455 | 36.0% | $-8,426 | $-176 | $-3.43 | 51.1 | $-9,130 | $-844 | $323 | -0.75 |
| NY_SESSION_CB3 | 2,090 | 33.3% | $-8,894 | $-212 | $-4.26 | 49.8 | $-9,185 | $-597 | $199 | -1.15 |
| CB_daily_dd200 | 2,916 | 37.7% | $-9,927 | $-191 | $-3.40 | 56.1 | $-9,934 | $-230 | $-0 | -3.45 |
| DDSTOP_AVOID_LUNCH | 2,912 | 37.7% | $-9,935 | $-191 | $-3.41 | 56.0 | $-9,941 | $-230 | $-0 | -3.45 |
| HTF_k30_ATR_min5_NY | 2,655 | 33.6% | $-10,382 | $-247 | $-3.91 | 63.2 | $-10,456 | $-1,298 | $69 | -1.03 |
| HTF_k30_CB3 | 4,252 | 35.9% | $-15,702 | $-308 | $-3.69 | 83.4 | $-15,825 | $-1,037 | $37 | -1.24 |
| NY_SESSION_ONLY | 4,915 | 33.3% | $-20,475 | $-487 | $-4.17 | 117.0 | $-20,571 | $-1,814 | $172 | -1.24 |
| ATR_min5_SKIP_OPEN_CB3 | 5,633 | 35.6% | $-21,683 | $-417 | $-3.85 | 108.3 | $-21,754 | $-1,456 | $230 | -1.17 |
| STRICT_LIMIT | 11,659 | 35.1% | $-22,057 | $-424 | $-1.89 | 224.2 | $-22,330 | $-2,483 | $699 | -0.73 |
| SKIP_OPEN_CB3 | 5,895 | 35.8% | $-22,782 | $-438 | $-3.86 | 113.4 | $-22,853 | $-1,456 | $210 | -1.21 |
| ATR_min5_CB3 | 5,751 | 35.3% | $-23,157 | $-445 | $-4.03 | 110.6 | $-23,216 | $-1,456 | $200 | -1.26 |
| CB_4losses_60min | 5,567 | 35.3% | $-23,579 | $-453 | $-4.24 | 107.1 | $-23,569 | $-1,441 | $41 | -1.36 |
| CB_3losses_30min | 6,010 | 35.5% | $-24,261 | $-467 | $-4.04 | 115.6 | $-24,320 | $-1,456 | $180 | -1.28 |
| HTF_k30 | 6,784 | 35.5% | $-25,742 | $-505 | $-3.79 | 133.0 | $-25,882 | $-2,297 | $123 | -1.12 |
| ATR_range8to20 | 6,561 | 33.7% | $-27,976 | $-538 | $-4.26 | 126.2 | $-28,032 | $-2,191 | $169 | -1.06 |
| HTF_k15 | 7,398 | 35.0% | $-29,544 | $-568 | $-3.99 | 142.3 | $-29,658 | $-2,384 | $72 | -1.14 |
| PULL_050 | 8,566 | 34.1% | $-38,812 | $-746 | $-4.53 | 164.7 | $-38,914 | $-2,664 | $33 | -1.38 |
| ATR_max25 | 9,797 | 34.9% | $-40,642 | $-782 | $-4.15 | 188.4 | $-40,714 | $-2,403 | $30 | -1.31 |
| ATR_min8 | 9,475 | 33.4% | $-41,525 | $-799 | $-4.38 | 182.2 | $-41,581 | $-3,422 | $73 | -0.99 |
| PULL_0382 | 9,907 | 34.6% | $-42,440 | $-816 | $-4.28 | 190.5 | $-42,501 | $-2,768 | $226 | -1.24 |
| ATR_min5_AVOID_LUNCH | 10,612 | 34.4% | $-45,112 | $-868 | $-4.25 | 204.1 | $-45,184 | $-3,159 | $30 | -1.17 |
| AVOID_LUNCH | 10,994 | 34.8% | $-46,065 | $-886 | $-4.19 | 211.4 | $-46,137 | $-3,159 | $30 | -1.18 |
| IMPULSE_8 | 10,823 | 34.1% | $-47,172 | $-907 | $-4.36 | 208.1 | $-47,228 | $-3,221 | $63 | -1.22 |
| SKIP_OPEN | 11,418 | 34.7% | $-47,226 | $-908 | $-4.14 | 219.6 | $-47,379 | $-3,422 | $94 | -1.12 |
| STOP_12_TARGET_18 | 11,154 | 39.9% | $-47,753 | $-918 | $-4.28 | 214.5 | $-47,749 | $-2,992 | $-15 | -1.29 |
| STOP_8_TARGET_24 | 12,182 | 28.3% | $-48,145 | $-926 | $-3.95 | 234.3 | $-48,237 | $-3,519 | $9 | -1.25 |
| ATR_min5 | 11,272 | 34.3% | $-48,301 | $-929 | $-4.29 | 216.8 | $-48,372 | $-3,446 | $30 | -1.16 |
| BASELINE | 11,659 | 34.6% | $-49,331 | $-949 | $-4.23 | 224.2 | $-49,403 | $-3,446 | $30 | -1.18 |
| SKIP_CLOSE | 11,659 | 34.6% | $-49,331 | $-949 | $-4.23 | 224.2 | $-49,403 | $-3,446 | $30 | -1.18 |
| NO_ARMING | 12,078 | 36.2% | $-59,491 | $-1,144 | $-4.93 | 232.3 | $-59,577 | $-4,540 | $27 | -1.15 |

### Per-variant behaviour
- **HTF_k60**: 2,455 trades, WR 36.0%, $-176/day, $-3.43/trade, trades/day 51.1, max DD $-9,130, worst day $-844, best day $323, Sharpe-ish -0.75. vs baseline: pnl +40,906$ (-17% rel.), trades -9,204 (-79%), WR +1.4pp. 
- **NY_SESSION_CB3**: 2,090 trades, WR 33.3%, $-212/day, $-4.26/trade, trades/day 49.8, max DD $-9,185, worst day $-597, best day $199, Sharpe-ish -1.15. vs baseline: pnl +40,437$ (-18% rel.), trades -9,569 (-82%), WR -1.3pp. 
- **CB_daily_dd200**: 2,916 trades, WR 37.7%, $-191/day, $-3.40/trade, trades/day 56.1, max DD $-9,934, worst day $-230, best day $-0, Sharpe-ish -3.45. vs baseline: pnl +39,404$ (-20% rel.), trades -8,743 (-75%), WR +3.1pp. 
- **DDSTOP_AVOID_LUNCH**: 2,912 trades, WR 37.7%, $-191/day, $-3.41/trade, trades/day 56.0, max DD $-9,941, worst day $-230, best day $-0, Sharpe-ish -3.45. vs baseline: pnl +39,396$ (-20% rel.), trades -8,747 (-75%), WR +3.1pp. 
- **HTF_k30_ATR_min5_NY**: 2,655 trades, WR 33.6%, $-247/day, $-3.91/trade, trades/day 63.2, max DD $-10,456, worst day $-1,298, best day $69, Sharpe-ish -1.03. vs baseline: pnl +38,949$ (-21% rel.), trades -9,004 (-77%), WR -1.0pp. 
- **HTF_k30_CB3**: 4,252 trades, WR 35.9%, $-308/day, $-3.69/trade, trades/day 83.4, max DD $-15,825, worst day $-1,037, best day $37, Sharpe-ish -1.24. vs baseline: pnl +33,629$ (-32% rel.), trades -7,407 (-64%), WR +1.3pp. 
- **NY_SESSION_ONLY**: 4,915 trades, WR 33.3%, $-487/day, $-4.17/trade, trades/day 117.0, max DD $-20,571, worst day $-1,814, best day $172, Sharpe-ish -1.24. vs baseline: pnl +28,856$ (-42% rel.), trades -6,744 (-58%), WR -1.3pp. 
- **ATR_min5_SKIP_OPEN_CB3**: 5,633 trades, WR 35.6%, $-417/day, $-3.85/trade, trades/day 108.3, max DD $-21,754, worst day $-1,456, best day $230, Sharpe-ish -1.17. vs baseline: pnl +27,648$ (-44% rel.), trades -6,026 (-52%), WR +1.0pp. 
- **STRICT_LIMIT**: 11,659 trades, WR 35.1%, $-424/day, $-1.89/trade, trades/day 224.2, max DD $-22,330, worst day $-2,483, best day $699, Sharpe-ish -0.73. vs baseline: pnl +27,274$ (-45% rel.), trades +0 (+0%), WR +0.5pp. 
- **SKIP_OPEN_CB3**: 5,895 trades, WR 35.8%, $-438/day, $-3.86/trade, trades/day 113.4, max DD $-22,853, worst day $-1,456, best day $210, Sharpe-ish -1.21. vs baseline: pnl +26,549$ (-46% rel.), trades -5,764 (-49%), WR +1.2pp. 
- **ATR_min5_CB3**: 5,751 trades, WR 35.3%, $-445/day, $-4.03/trade, trades/day 110.6, max DD $-23,216, worst day $-1,456, best day $200, Sharpe-ish -1.26. vs baseline: pnl +26,174$ (-47% rel.), trades -5,908 (-51%), WR +0.7pp. 
- **CB_4losses_60min**: 5,567 trades, WR 35.3%, $-453/day, $-4.24/trade, trades/day 107.1, max DD $-23,569, worst day $-1,441, best day $41, Sharpe-ish -1.36. vs baseline: pnl +25,752$ (-48% rel.), trades -6,092 (-52%), WR +0.7pp. 
- **CB_3losses_30min**: 6,010 trades, WR 35.5%, $-467/day, $-4.04/trade, trades/day 115.6, max DD $-24,320, worst day $-1,456, best day $180, Sharpe-ish -1.28. vs baseline: pnl +25,070$ (-49% rel.), trades -5,649 (-48%), WR +0.9pp. 
- **HTF_k30**: 6,784 trades, WR 35.5%, $-505/day, $-3.79/trade, trades/day 133.0, max DD $-25,882, worst day $-2,297, best day $123, Sharpe-ish -1.12. vs baseline: pnl +23,589$ (-52% rel.), trades -4,875 (-42%), WR +0.9pp. 
- **ATR_range8to20**: 6,561 trades, WR 33.7%, $-538/day, $-4.26/trade, trades/day 126.2, max DD $-28,032, worst day $-2,191, best day $169, Sharpe-ish -1.06. vs baseline: pnl +21,355$ (-57% rel.), trades -5,098 (-44%), WR -0.9pp. 
- **HTF_k15**: 7,398 trades, WR 35.0%, $-568/day, $-3.99/trade, trades/day 142.3, max DD $-29,658, worst day $-2,384, best day $72, Sharpe-ish -1.14. vs baseline: pnl +19,787$ (-60% rel.), trades -4,261 (-37%), WR +0.4pp. 
- **PULL_050**: 8,566 trades, WR 34.1%, $-746/day, $-4.53/trade, trades/day 164.7, max DD $-38,914, worst day $-2,664, best day $33, Sharpe-ish -1.38. vs baseline: pnl +10,519$ (-79% rel.), trades -3,093 (-27%), WR -0.5pp. 
- **ATR_max25**: 9,797 trades, WR 34.9%, $-782/day, $-4.15/trade, trades/day 188.4, max DD $-40,714, worst day $-2,403, best day $30, Sharpe-ish -1.31. vs baseline: pnl +8,689$ (-82% rel.), trades -1,862 (-16%), WR +0.3pp. 
- **ATR_min8**: 9,475 trades, WR 33.4%, $-799/day, $-4.38/trade, trades/day 182.2, max DD $-41,581, worst day $-3,422, best day $73, Sharpe-ish -0.99. vs baseline: pnl +7,806$ (-84% rel.), trades -2,184 (-19%), WR -1.2pp. 
- **PULL_0382**: 9,907 trades, WR 34.6%, $-816/day, $-4.28/trade, trades/day 190.5, max DD $-42,501, worst day $-2,768, best day $226, Sharpe-ish -1.24. vs baseline: pnl +6,891$ (-86% rel.), trades -1,752 (-15%), WR -0.0pp. 
- **ATR_min5_AVOID_LUNCH**: 10,612 trades, WR 34.4%, $-868/day, $-4.25/trade, trades/day 204.1, max DD $-45,184, worst day $-3,159, best day $30, Sharpe-ish -1.17. vs baseline: pnl +4,219$ (-91% rel.), trades -1,047 (-9%), WR -0.2pp. 
- **AVOID_LUNCH**: 10,994 trades, WR 34.8%, $-886/day, $-4.19/trade, trades/day 211.4, max DD $-46,137, worst day $-3,159, best day $30, Sharpe-ish -1.18. vs baseline: pnl +3,266$ (-93% rel.), trades -665 (-6%), WR +0.2pp. 
- **IMPULSE_8**: 10,823 trades, WR 34.1%, $-907/day, $-4.36/trade, trades/day 208.1, max DD $-47,228, worst day $-3,221, best day $63, Sharpe-ish -1.22. vs baseline: pnl +2,159$ (-96% rel.), trades -836 (-7%), WR -0.5pp. 
- **SKIP_OPEN**: 11,418 trades, WR 34.7%, $-908/day, $-4.14/trade, trades/day 219.6, max DD $-47,379, worst day $-3,422, best day $94, Sharpe-ish -1.12. vs baseline: pnl +2,105$ (-96% rel.), trades -241 (-2%), WR +0.1pp. 
- **STOP_12_TARGET_18**: 11,154 trades, WR 39.9%, $-918/day, $-4.28/trade, trades/day 214.5, max DD $-47,749, worst day $-2,992, best day $-15, Sharpe-ish -1.29. vs baseline: pnl +1,579$ (-97% rel.), trades -505 (-4%), WR +5.3pp. 
- **STOP_8_TARGET_24**: 12,182 trades, WR 28.3%, $-926/day, $-3.95/trade, trades/day 234.3, max DD $-48,237, worst day $-3,519, best day $9, Sharpe-ish -1.25. vs baseline: pnl +1,186$ (-98% rel.), trades +523 (+4%), WR -6.3pp. 
- **ATR_min5**: 11,272 trades, WR 34.3%, $-929/day, $-4.29/trade, trades/day 216.8, max DD $-48,372, worst day $-3,446, best day $30, Sharpe-ish -1.16. vs baseline: pnl +1,031$ (-98% rel.), trades -387 (-3%), WR -0.3pp. 
- **BASELINE**: 11,659 trades, WR 34.6%, $-949/day, $-4.23/trade, trades/day 224.2, max DD $-49,403, worst day $-3,446, best day $30, Sharpe-ish -1.18. vs baseline: pnl +0$ (-100% rel.), trades +0 (+0%), WR +0.0pp. 
- **SKIP_CLOSE**: 11,659 trades, WR 34.6%, $-949/day, $-4.23/trade, trades/day 224.2, max DD $-49,403, worst day $-3,446, best day $30, Sharpe-ish -1.18. vs baseline: pnl +0$ (-100% rel.), trades +0 (+0%), WR +0.0pp. 
- **NO_ARMING**: 12,078 trades, WR 36.2%, $-1,144/day, $-4.93/trade, trades/day 232.3, max DD $-59,577, worst day $-4,540, best day $27, Sharpe-ish -1.15. vs baseline: pnl -10,160$ (-121% rel.), trades +419 (+4%), WR +1.6pp. 

## Recommendation
_Source: 60-day subset_

**Baseline (current live config)**: 11,659 trades, $-49,331 P&L, $-949/day, WR 34.6%, 224.2 trades/day.

**Top 5 by P&L**:

1. **HTF_k60** — $-8,426 (vs baseline +40,906$), 2,455 trades (-9,204 vs baseline), $-176/day, WR 36.0%, 51.1 tr/day, max DD $-9,130
1. **NY_SESSION_CB3** — $-8,894 (vs baseline +40,437$), 2,090 trades (-9,569 vs baseline), $-212/day, WR 33.3%, 49.8 tr/day, max DD $-9,185
1. **CB_daily_dd200** — $-9,927 (vs baseline +39,404$), 2,916 trades (-8,743 vs baseline), $-191/day, WR 37.7%, 56.1 tr/day, max DD $-9,934
1. **DDSTOP_AVOID_LUNCH** — $-9,935 (vs baseline +39,396$), 2,912 trades (-8,747 vs baseline), $-191/day, WR 37.7%, 56.0 tr/day, max DD $-9,941
1. **HTF_k30_ATR_min5_NY** — $-10,382 (vs baseline +38,949$), 2,655 trades (-9,004 vs baseline), $-247/day, WR 33.6%, 63.2 tr/day, max DD $-10,456

**HONEST VERDICT — STOP TRADING**: Every single variant tested loses money over the test window, including the current live BASELINE config. The original validation that showed +$1,952/day was on tick data WITHOUT arming (phantom fires inflated the win rate), and likely also used optimistic exit modelling (bar-high target wicks fill paper but never fill the real broker LIMIT).

With arming + marketable LIMIT exec + STOP-MARKET slip + tight LIMIT target requirements (broker reality), the strategy has a structural NEGATIVE edge:

  - BASELINE:           $-949/day  (224 tr/day, WR 34.6%)
  - Best variant (HTF_k60): $-176/day  (51 tr/day, WR 36.0%)

The filters reduce the bleed by trading less, but the per-trade expectancy is negative on every config — you cannot filter your way out of a negative edge.

**Recommended actions:**

1. PAUSE the live bot. It is currently losing money in real time and the backtest confirms this is the expected behaviour, not bad luck.
2. Investigate why the original validated +$1,952/day config doesn't reproduce. The two biggest suspects are (a) the OOS-validation period (Dec'25-Feb'26) was a specific bear-volatility regime not present in the full data; (b) the arming-vs-phantom and marketable-LIMIT exec fixes (correct as of June '26) remove the implicit edge that older paper accounting was double-counting.
3. Re-validate on the original Dec'25-Feb'26 window with the CURRENT execution model. If P&L is still positive there but negative on the full 766-day data, the strategy is a regime-specific bet, not a persistent edge.
4. Consider whether the strategy needs a fundamental redesign — the bake-off catalogue in research/ has many alternatives (cumdelta, large-print fade, ORB, SMC sweep, etc.) that may have a real edge.

**If forced to keep trading right now**: the HTF_k60 variant loses the LEAST money ($-176/day vs baseline $-949/day) but cuts trade volume to 51/day (-79% vs baseline). It is a damage-control mode, not a winning strategy.

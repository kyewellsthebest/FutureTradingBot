# EXACT bot simulation -- Friday 2026-08-14

The live executor's real code (fixed build: mirror engine, 1pt fire drift gate, 60s cooldown, RTH gate) driven tick-by-tick over the session's 924,338 real MNQU6 ticks.

| entry | exit | side | entry px | reason | hold s | paper P&L | broker fill? | broker P&L |
|---|---|---|---|---|---|---|---|---|
| 13:31:01 | 13:31:04 | SHORT | 30251.75 | stop | 2 | -20.74 | yes | -21.24 |
| 13:46:52 | 13:47:00 | LONG | 30238.0 | target | 7 | 39.76 | yes | 39.01 |
| 14:02:24 | 14:02:27 | SHORT | 30233.0 | stop | 3 | -20.74 | yes | -21.24 |
| 14:26:36 | 14:27:29 | SHORT | 30168.25 | target | 53 | 39.76 | yes | 39.01 |
| 14:40:29 | 14:41:03 | LONG | 30151.5 | stop | 34 | -20.74 | yes | -21.24 |
| 14:49:18 | 14:50:00 | LONG | 30148.25 | timeout | 41 | 2.26 | yes | 1.76 |
| 14:52:19 | 14:55:11 | LONG | 30150.0 | stop | 172 | -21.74 | yes | -22.24 |
| 15:11:06 | 15:14:25 | SHORT | 30111.75 | target | 198 | 39.76 | yes | 39.01 |
| 15:21:16 | 15:21:20 | LONG | 30093.75 | stop | 3 | -23.74 | yes | -24.24 |
| 15:33:13 | 15:37:13 | LONG | 30048.75 | stop | 240 | -21.74 | yes | -22.24 |
| 15:44:16 | 15:45:22 | SHORT | 30045.0 | stop | 65 | -21.74 | yes | -22.24 |
| 16:03:09 | 16:08:57 | LONG | 30066.75 | stop | 347 | -21.24 | yes | -21.74 |
| 16:19:20 | 16:26:08 | LONG | 30078.5 | target | 408 | 39.76 | yes | 39.01 |
| 16:30:37 | 16:31:19 | LONG | 30094.0 | stop | 42 | -20.74 | yes | -21.24 |
| 16:41:03 | 16:41:25 | LONG | 30075.25 | stop | 22 | -27.24 | yes | -27.74 |
| 16:53:14 | 17:03:00 | SHORT | 30063.25 | timeout | 585 | 16.26 | yes | 15.76 |
| 17:08:14 | 17:18:00 | LONG | 30065.0 | timeout | 585 | 4.76 | yes | 4.26 |
| 17:23:51 | 17:24:33 | LONG | 30063.75 | stop | 41 | -21.74 | yes | -22.24 |
| 17:35:01 | 17:37:39 | LONG | 30064.75 | stop | 157 | -20.74 | yes | -21.24 |
| 17:49:50 | 17:54:11 | LONG | 30056.5 | target | 261 | 39.76 | yes | 39.01 |
| 18:00:48 | 18:10:00 | LONG | 30076.75 | timeout | 552 | 23.26 | yes | 22.76 |
| 18:14:30 | 18:23:00 | LONG | 30081.75 | timeout | 510 | 9.76 | yes | 9.26 |
| 18:26:02 | 18:29:00 | SHORT | 30085.25 | target | 177 | 39.76 | yes | 39.01 |
| 18:46:50 | 18:51:08 | LONG | 30079.5 | target | 258 | 39.76 | yes | 39.01 |
| 18:58:20 | 19:00:54 | LONG | 30089.0 | stop | 153 | -20.74 | yes | -21.24 |
| 19:10:38 | 19:18:07 | LONG | 30088.5 | stop | 449 | -22.74 | yes | -23.24 |
| 19:22:24 | 19:26:01 | SHORT | 30084.5 | stop | 216 | -21.74 | yes | -22.24 |
| 19:37:53 | 19:47:00 | LONG | 30100.0 | timeout | 546 | 3.26 | yes | 2.76 |
| 19:55:22 | 19:59:31 | LONG | 30116.75 | target | 249 | 39.76 | yes | 39.01 |

## PAPER book (dashboard's view): **$+49.54** on 29 trades, 14/29 wins ($0.74/RT)
## BROKER truth: **$+33.04** -- 29/29 entries actually fill the resting LIMIT ($1.24/RT, target exits pay half-spread)

Unfilled entries are paper-only: the tape never traded through the limit while the trade was alive, so the broker order would have been cancelled at paper exit (orphan path).


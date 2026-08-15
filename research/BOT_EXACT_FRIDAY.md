# EXACT bot simulation -- Friday 2026-08-14

The live executor's real code (fixed build: mirror engine, 1pt fire drift gate, 60s cooldown, RTH gate) driven tick-by-tick over the session's 924,338 real MNQU6 ticks.

| entry | exit | side | entry px | reason | hold s | paper P&L | broker fill? | broker P&L |
|---|---|---|---|---|---|---|---|---|
| 13:30:09 | 13:30:13 | SHORT | 30252.0 | stop | 3 | -21.24 | yes | -21.74 |
| 13:49:27 | 13:50:00 | LONG | 30246.25 | target | 32 | 39.76 | yes | 39.01 |
| 13:51:01 | 13:51:14 | LONG | 30237.75 | stop | 12 | -21.24 | yes | -21.74 |
| 13:53:04 | 13:53:16 | LONG | 30241.5 | stop | 12 | -21.24 | yes | -21.74 |
| 14:08:49 | 14:09:00 | LONG | 30239.75 | target | 10 | 39.76 | yes | 39.01 |
| 14:10:42 | 14:11:27 | LONG | 30228.0 | stop | 45 | -21.24 | yes | -21.74 |
| 14:40:30 | 14:41:00 | LONG | 30148.5 | target | 29 | 39.76 | yes | 39.01 |
| 14:42:00 | 14:45:33 | LONG | 30154.75 | stop | 213 | -21.24 | yes | -21.74 |
| 14:49:15 | 14:55:11 | LONG | 30151.5 | stop | 355 | -21.24 | yes | -21.74 |
| 15:21:05 | 15:21:20 | LONG | 30097.75 | stop | 14 | -21.24 | yes | -21.74 |
| 15:31:25 | 15:37:13 | LONG | 30048.5 | stop | 348 | -21.24 | yes | -21.74 |
| 15:48:32 | 15:48:54 | LONG | 30044.75 | stop | 22 | -21.24 | yes | -21.74 |
| 15:49:54 | 15:50:00 | LONG | 30043.75 | stop | 5 | -21.24 | yes | -21.74 |
| 16:05:25 | 16:06:45 | LONG | 30071.75 | stop | 80 | -21.24 | yes | -21.74 |
| 16:07:47 | 16:08:07 | LONG | 30072.0 | stop | 19 | -21.24 | yes | -21.74 |
| 16:19:50 | 16:25:59 | LONG | 30076.75 | target | 368 | 39.76 | yes | 39.01 |
| 16:36:51 | 16:41:13 | SHORT | 30088.5 | target | 262 | 39.76 | yes | 39.01 |
| 16:47:42 | 16:57:43 | SHORT | 30071.75 | timeout | 600 | 10.76 | yes | 10.26 |
| 17:11:01 | 17:21:01 | LONG | 30064.75 | timeout | 600 | 7.76 | yes | 7.26 |
| 17:23:18 | 17:24:30 | LONG | 30065.0 | stop | 72 | -21.24 | yes | -21.74 |
| 17:37:14 | 17:37:45 | LONG | 30062.75 | stop | 30 | -21.24 | yes | -21.74 |
| 17:38:45 | 17:38:45 | LONG | 30062.0 | stop | 0 | -21.24 | yes | -21.74 |
| 17:39:45 | 17:40:00 | LONG | 30062.75 | stop | 14 | -21.24 | yes | -21.74 |
| 17:49:49 | 17:54:11 | LONG | 30056.75 | target | 261 | 39.76 | yes | 39.01 |
| 18:15:27 | 18:25:27 | SHORT | 30085.5 | timeout | 600 | 3.26 | yes | 2.76 |
| 18:34:56 | 18:40:53 | SHORT | 30071.5 | stop | 357 | -21.24 | yes | -21.74 |
| 19:02:27 | 19:12:27 | SHORT | 30086.5 | timeout | 600 | -1.24 | yes | -1.74 |
| 19:18:34 | 19:28:28 | SHORT | 30088.75 | stop | 593 | -21.24 | yes | -21.74 |
| 19:31:24 | 19:40:45 | LONG | 30092.25 | target | 561 | 39.76 | yes | 39.01 |
| 19:45:13 | 19:50:00 | LONG | 30103.5 | target | 286 | 39.76 | yes | 39.01 |
| 19:55:16 | 19:59:32 | LONG | 30117.5 | target | 255 | 39.76 | yes | 39.01 |

## PAPER book (dashboard's view): **$-3.94** on 31 trades, 12/31 wins ($0.74/RT)
## BROKER truth: **$-21.69** -- 31/31 entries actually fill the resting LIMIT ($1.24/RT, target exits pay half-spread)

Unfilled entries are paper-only: the tape never traded through the limit while the trade was alive, so the broker order would have been cancelled at paper exit (orphan path).


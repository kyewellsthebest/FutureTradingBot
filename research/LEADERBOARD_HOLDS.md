# Can 161 trades/day and a 44-point target both be true?

The leaderboard claims ~161 trades/day per MNQ with a 44-point target hit 10-17% of the time. The same parameters through the validated engine, one position with the live bot's lockout, give 24 trades/day. Only two things close a 6.7x gap: a much SHORTER HOLD, or OVERLAPPING positions -- and if it is overlap, "1 MNQ" is not one contract, because P&L accrues to every open position while commission is charged once per signal.

NQ, 4 quarters, 364 RTH sessions, config #1 (impulse 2, window 3, pull 0.118, stop 5, target 44), honest stop-entry fills, $1.33 round trip.

`lockout=window` is one position at a time -- the live bot's actual behaviour. `lockout=none` lets windows overlap, which is the only way to reach the claimed trade rate.

| hold | lockout | trades/day | target-hit % | $/trade | $/day |
|---|---|---|---|---|---|
| 60s | window | 122 | 0.3% | $-2.73 | $-332 |
| 60s | none | 224 | 0.3% | $-2.73 | $-611 |
| 90s | window | 84 | 0.7% | $-2.67 | $-225 |
| 90s | none | 226 | 0.7% | $-2.71 | $-613 |
| 120s | window | 84 | 1.0% | $-2.69 | $-227 |
| 120s | none | 227 | 1.0% | $-2.71 | $-617 |
| 300s | window | 44 | 3.0% | $-2.84 | $-124 |
| 300s | none | 231 | 2.9% | $-2.79 | $-642 |
| 600s | window | 24 | 4.8% | $-2.98 | $-73 |
| 600s | none | 232 | 5.0% | $-2.82 | $-654 |

## Reading this

Find the row whose trade rate is near 161. Then read its target-hit column and compare it with the claimed 10-17%, and read its lockout column to see whether that rate required overlapping positions. The claim needs a single row where the trade rate, the hit rate and one contract are all true at once.


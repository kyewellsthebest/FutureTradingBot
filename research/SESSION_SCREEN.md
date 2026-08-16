# C1: is there directional skill outside US cash hours?

Every prior search in this repo filtered to RTH 13:30-20:00 UTC. This runs the same signal families and market entries across all four sessions. NQ, 8 quarters.

`EV half` charges a half-tick crossing (RTH-like); `EV full` charges a full tick (overnight-realistic). Both include $1.24 commission.

**A trade that reaches neither barrier is closed at the market when the clock runs out, and booked at that price.** The first version of this screen booked those at zero, which hides every loser that drifted against us without travelling the full stop distance. With a 20-point stop in a thin overnight session that is most of them: it made the 20/10 bracket look profitable in ASIA and EUROPE and, decisively, made the RANDOM control profitable too. The `timeout` column below is how big that bucket is, so the same thing cannot hide twice.

| session | signal | bracket | n | trades/day | target first | timeout | EV half | EV full |
|---|---|---|---|---|---|---|---|---|
| US_EXT | mom10_fade | 20/10 | 17,833 | 34 | 49.83% | 31% | $-0.07 | $-0.32 |
| US_EXT | mom10_fade | 20/40 | 17,833 | 34 | 8.23% | 65% | $-0.22 | $-0.47 |
| US_EXT | band_fade | 20/10 | 10,773 | 21 | 45.60% | 37% | $-0.34 | $-0.59 |
| US_EXT | mom10_fade | 10/20 | 17,833 | 34 | 19.42% | 33% | $-0.49 | $-0.74 |
| US_EXT | band_fade | 20/40 | 10,773 | 21 | 7.00% | 69% | $-0.69 | $-0.94 |
| US_EXT | mom3_fade | 20/10 | 24,917 | 48 | 44.73% | 39% | $-0.74 | $-0.99 |
| US_EXT | mom10_fade | 5/10 | 17,833 | 34 | 30.25% | 11% | $-0.76 | $-1.01 |
| US_EXT | band_fade | 10/20 | 10,773 | 21 | 17.37% | 40% | $-0.81 | $-1.06 |
| US_EXT | band_fade | 5/10 | 10,773 | 21 | 28.67% | 16% | $-0.94 | $-1.19 |
| US_EXT | streak3_fade | 20/10 | 8,417 | 16 | 40.89% | 45% | $-0.96 | $-1.21 |
| US_EXT | mom3_fade | 20/40 | 24,917 | 48 | 6.86% | 70% | $-0.96 | $-1.21 |
| ASIA | band_cont | 20/40 | 73,556 | 141 | 3.73% | 84% | $-1.08 | $-1.33 |
| US_RTH | vspike_cont | 20/40 | 16,871 | 33 | 24.17% | 21% | $-1.13 | $-1.38 |
| US_EXT | mom3_fade | 5/10 | 24,917 | 48 | 27.80% | 15% | $-1.19 | $-1.44 |
| US_RTH | band_fade | 20/10 | 63,681 | 123 | 61.38% | 11% | $-1.19 | $-1.44 |
| US_EXT | ext30_fade | 5/10 | 24,045 | 46 | 10.73% | 67% | $-1.19 | $-1.44 |
| EUROPE | ext30_fade | 20/10 | 50,387 | 97 | 40.53% | 45% | $-1.20 | $-1.45 |
| EUROPE | ext30_fade | 20/40 | 50,387 | 97 | 3.56% | 78% | $-1.21 | $-1.46 |
| ASIA | band_cont | 10/20 | 73,556 | 141 | 11.64% | 57% | $-1.21 | $-1.46 |
| US_RTH | streak3_cont | 20/10 | 45,915 | 88 | 60.44% | 13% | $-1.21 | $-1.46 |
| ASIA | band_cont | 20/10 | 73,556 | 141 | 33.63% | 57% | $-1.22 | $-1.47 |
| US_RTH | streak3_cont | 20/40 | 45,915 | 88 | 15.03% | 43% | $-1.22 | $-1.47 |
| US_RTH | vspike_cont | 5/10 | 16,871 | 33 | 34.05% | 0% | $-1.22 | $-1.47 |
| EUROPE | streak3_fade | 20/10 | 50,066 | 96 | 44.02% | 40% | $-1.24 | $-1.49 |
| ASIA | vspike_cont | 5/10 | 26,146 | 50 | 25.66% | 19% | $-1.26 | $-1.51 |
| US_EXT | mom3_fade | 10/20 | 24,917 | 48 | 16.99% | 40% | $-1.26 | $-1.51 |
| ASIA | streak3_cont | 10/20 | 44,706 | 86 | 10.88% | 57% | $-1.28 | $-1.53 |
| ASIA | vspike_cont | 10/20 | 26,146 | 50 | 12.35% | 53% | $-1.28 | $-1.53 |
| US_EXT | streak3_fade | 5/10 | 8,417 | 16 | 25.97% | 18% | $-1.29 | $-1.54 |
| EUROPE | mom10_fade | 20/10 | 97,160 | 187 | 50.57% | 30% | $-1.29 | $-1.54 |

## Per-session summary (best cell vs RANDOM in the SAME bracket)

The control has to be read at the bracket the winner used. Comparing a 20/10 winner against a 10/20 RANDOM compares two different geometries and tells you nothing -- that mistake is what let the timeout artifact through the first time.

| session | best signal | best target-first | best EV full | RANDOM (same bracket) EV | verdict |
|---|---|---|---|---|---|
| ASIA | band_cont 20/40 | 3.73% | $-1.33 | $-1.79 | beats random, still loses money |
| EUROPE | ext30_fade 20/10 | 40.53% | $-1.45 | $-1.64 | no better than random |
| US_RTH | vspike_cont 20/40 | 24.17% | $-1.38 | $-1.72 | beats random, still loses money |
| US_EXT | mom10_fade 20/10 | 49.83% | $-0.32 | $-1.60 | beats random, still loses money |

**Cells positive at full-tick cost AND beating the RANDOM control in their own session and bracket by at least $0.25: 0 of 200**



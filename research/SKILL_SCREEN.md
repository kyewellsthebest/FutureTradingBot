# Skill screen: does any signal family predict direction?

Entry at the MARKET on the signal bar's close (no limit orders, no fill assumptions), 10-min horizon, half-tick spread + $1.24 commission. NQ, 8 quarters.

Target for $300/week: **~38-40%** target-first on a 1:2 bracket. Zero-cost breakeven: **33.3%**.

| signal | bracket | n | target first | EV/trade |
|---|---|---|---|---|
| vwapdev_fade | 20/10 | 129,839 | 57.67% | $+0.06 |
| openbreak_fade | 20/10 | 126,100 | 58.57% | $-0.05 |
| compress_cont | 20/10 | 1,101 | 58.76% | $-0.16 |
| streak3_cont | 20/10 | 45,915 | 60.44% | $-0.19 |
| mom3_cont | 20/10 | 158,578 | 60.78% | $-0.47 |
| openbreak_cont | 20/10 | 126,100 | 57.98% | $-0.48 |
| mom3_fade | 20/10 | 158,578 | 60.95% | $-0.50 |
| vwapdev_cont | 20/10 | 129,839 | 56.67% | $-0.53 |
| mom10_cont | 20/10 | 128,903 | 62.21% | $-0.54 |
| streak3_fade | 20/10 | 45,915 | 60.07% | $-0.59 |
| RANDOM | 20/10 | 71,091 | 41.42% | $-0.66 |
| mom10_fade | 20/10 | 128,903 | 62.02% | $-0.75 |
| volspike_cont | 20/10 | 16,871 | 64.50% | $-0.98 |
| volspike_cont | 10/5 | 16,871 | 67.61% | $-1.12 |
| ext30_fade | 20/10 | 127,546 | 19.50% | $-1.12 |
| ext30_cont | 20/10 | 127,546 | 19.30% | $-1.12 |
| vwapdev_fade | 10/5 | 129,839 | 64.95% | $-1.21 |
| openbreak_fade | 10/5 | 126,100 | 65.64% | $-1.23 |
| volspike_cont | 5/10 | 16,871 | 34.05% | $-1.24 |
| compress_cont | 10/5 | 1,101 | 65.76% | $-1.24 |
| compress_cont | 10/20 | 1,101 | 28.07% | $-1.27 |
| volspike_fade | 20/10 | 16,871 | 64.33% | $-1.31 |
| streak3_cont | 10/5 | 45,915 | 66.48% | $-1.32 |
| openbreak_fade | 5/10 | 126,100 | 32.78% | $-1.37 |
| vwapdev_fade | 5/10 | 129,839 | 32.38% | $-1.37 |
| RANDOM | 10/5 | 71,091 | 46.07% | $-1.38 |
| mom3_cont | 10/5 | 158,578 | 66.28% | $-1.43 |
| mom10_cont | 10/5 | 128,903 | 66.44% | $-1.44 |

**Positive-EV combinations: 1 of 80**

- vwapdev_fade 20/10: 57.67% target-first, $+0.06/trade over 129,839 signals


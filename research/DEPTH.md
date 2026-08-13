# The maker edge, measured instead of assumed

~$55 of Databento credit bought MNQU6 order-by-order (mbo) plus top-of-book
(mbp-1) for Jul 27–31 2026 — the exact contract the bot trades. The
simulation joined the back of the best-bid queue once a minute through five
RTH sessions and asked, from the real order flow: did enough volume trade
at our price to fill us before the level broke?

## The week, day by day

| day | joins | filled before level broke | median queue ahead |
|---|---|---|---|
| Mon Jul 27 | 415 | 22 (5%) | 4 |
| Tue Jul 28 | 419 | 30 (7%) | 3 |
| Wed Jul 29 | 419 | 27 (6%) | 3 |
| Thu Jul 30 | 419 | 30 (7%) | 3 (Databento flags this day "degraded") |
| Fri Jul 31 | 419 | 29 (7%) | 3 |
| **week** | **2,091** | **138 (6.6%)** | **3** |

## What this settles

**The +$0.355/trade maker credit is dead.** The model behind it assumed a
resting order at the touch fills reliably; measured, a passive join at the
best bid fills within two minutes only **~6.6% of the time**. The
surprising part is WHY: the queue ahead is tiny (median 3 contracts — the
MNQ book is thin, as the earlier queue model correctly said), but the
LEVEL does not live long enough for even three contracts to trade at it.
Queue position was never the binding constraint; level lifetime is.

In practice a bot that rests at the touch spends its life waiting, and
mostly ends up either crossing the spread anyway (taker) or getting filled
in the moment the level gives way (adverse selection). Taker pricing —
which the multi-market sweeps already use — is the honest execution model.

## What it does to the validated NQ book

The 10-core ensemble (+$196/wk at 202 trades/wk) credited +$0.355 on every
trade. Repriced at taker (pay the half-to-full spread instead of earning
it), the swing is roughly $0.85/trade, i.e. about **$170/wk** — the book's
realistic expectation drops to near **+$25/wk** unless entries are
re-engineered. Two honest ways forward:

1. **conditional resting** — rest only when the book says the level is
   fresh and the queue short (the mbo data can measure exactly when P(fill)
   is 3-4x its average), cross otherwise; recovers part of the credit on a
   measured subset of trades;
2. **taker-priced selection** — what the ES/YM/RTY/CL sweeps already do:
   only edges that survive paying the spread get believed.

## Data quality verdict

Excellent where it matters: every individual order with nanosecond
timestamps, order-ids that make queue position exact rather than modeled,
and honest quality flags (Databento itself marks Jul 30 "degraded"). ~$48
of the $125 credit remains; the natural next purchases are a second MNQ
week (regime check, ~$55) or ESU6 mbo July (~$29) when needed.

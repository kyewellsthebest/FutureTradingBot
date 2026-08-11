# What resting a limit is actually worth

A taker buys the offer and sells the bid, so a round trip costs one full tick plus commission — **$1.24 on MNQ**. A maker rests instead and *earns* that tick. The swing is two ticks, **$1.00 a trade**, $500 a week at 500 trades, and it predicts nothing. For scale, the entire directional search run at **zero** cost topped out at $97 a week.

It is not free: a resting bid fills when someone sells into it, and people sell into it when price is about to fall. Fill the bad ones, miss the good ones. Modelling that needs a rule for when a limit fills, and three rules in this repo gave **+$0.88**, **+$0.25** and **−$0.066** a trade — a 3.5× band on the biggest lever available, produced entirely by an assumption nobody measured.

Touch and trade-through are both stand-ins for the real question: **how many contracts were ahead of you in the queue?** The book would say directly and is not recording yet, but the tape carries trade sizes — so assume `Q` ahead, fill once `Q+1` contracts trade at your price (or instantly if price sweeps straight through), and the answer becomes a curve instead of a point.

`33,464` signals across `8` quarters, `623` sessions, both directions, 30s to fill. Commission $0.74; the spread is modelled by the fill price, not charged as a constant.

**Taker baseline: $-1.557 a trade** over 33,464 trades — the same signals, crossing the spread, filled every time.

| contracts ahead of you | fill rate | $/trade **on fills** | $/trade **per signal** | vs taker | $/week @500 signals |
|---|---|---|---|---|---|
| 0 | 95% | $-1.266 | $-1.202 | **+0.355** | $-601 |
| 2 | 93% | $-1.608 | $-1.493 | **+0.064** | $-747 |
| 5 | 92% | $-1.716 | $-1.576 | -0.019 | $-788 |
| 10 | 91% | $-1.787 | $-1.632 | -0.075 | $-816 |
| 25 | 91% | $-1.817 | $-1.654 | -0.097 | $-827 |
| 50 | 91% | $-1.823 | $-1.659 | -0.102 | $-829 |
| 100 | 91% | $-1.822 | $-1.658 | -0.101 | $-829 |
| 200 | 91% | $-1.822 | $-1.658 | -0.101 | $-829 |

Best case in the sweep is **0 contracts ahead**: fills 95% of signals at **$-1.266** on the ones it gets, **$-1.202** averaged over every signal including the misses. Against a taker at $-1.557, that is **$+177 a week** at 500 signals.

**Read the two dollar columns against each other.** A maker can beat a taker on the trades it gets and still lose on the week, because the taker gets every signal and the maker only gets the ones the market came back for — which are disproportionately the losers. Where *on fills* is strong and *per signal* is weak, adverse selection is eating the edge and no amount of queue luck fixes it.

_Ran 2 min._

## Where the break-even sits, and what it means

Resting beats crossing only at the very front of the queue. Break-even is
between **2 and 5 contracts ahead**, and past 50 the curve is flat — being 200
deep is no worse than being 50 deep, because by then the only fills you get
are the ones where the market ran you over.

So the theoretical two-tick swing of $1.00 a trade delivers **$0.355 in the
physically impossible best case** and turns negative almost immediately.
Adverse selection takes 65% of it before the queue takes the rest.

This does not settle the question so much as reduce it to one measurement.
**Is the median queue at top of book more or less than about four contracts?**
Everything about passive entry now hangs on that single number, and the DOM
recorder answers it for free the day it runs.

## Two limitations, stated rather than buried

**Units.** The tape is full-size NQ, so queue depths here are counted in NQ
lots while P&L is denominated in MNQ ticks. MNQ has its own book with its own
depth. The shape of the curve holds either way, but the exact break-even
should be re-measured against MNQ's own book once depth is recording.

**How thin this is.** The first version of this study concluded the opposite —
that resting was worse than crossing at every queue depth. It had the taker's
stop exiting at the stop price while the maker's paid a tick to cross it, a
$0.50 handicap on the side under test. Correcting it moved the front-of-queue
result from −$0.05 to +$0.355. Same data, same tape; the conclusion turned on
a half-dollar of bookkeeping. Any future change to the exit model should be
expected to move this number just as much.

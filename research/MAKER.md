# What resting a limit is actually worth

A taker buys the offer and sells the bid, so a round trip costs one full tick plus commission — **$1.24 on MNQ**. A maker rests instead and *earns* that tick. The swing is two ticks, **$1.00 a trade**, $500 a week at 500 trades, and it predicts nothing. For scale, the entire directional search run at **zero** cost topped out at $97 a week.

It is not free: a resting bid fills when someone sells into it, and people sell into it when price is about to fall. Fill the bad ones, miss the good ones. Modelling that needs a rule for when a limit fills, and three rules in this repo gave **+$0.88**, **+$0.25** and **−$0.066** a trade — a 3.5× band on the biggest lever available, produced entirely by an assumption nobody measured.

Touch and trade-through are both stand-ins for the real question: **how many contracts were ahead of you in the queue?** The book would say directly and is not recording yet, but the tape carries trade sizes — so assume `Q` ahead, fill once `Q+1` contracts trade at your price (or instantly if price sweeps straight through), and the answer becomes a curve instead of a point.

`33,464` signals across `8` quarters, `623` sessions, both directions, 30s to fill. Commission $0.74; the spread is modelled by the fill price, not charged as a constant.

**Taker baseline: $-1.557 a trade** over 33,464 trades — the same signals, crossing the spread, filled every time.

## The full spec sheet, per queue depth

Every row is the SAME signals and the SAME bracket — 46x46 ticks, 1:1 — differing only in how the entry is executed. `hybrid` rests a limit and crosses the spread if the market never comes to it, so it never skips a trade.

| execution | fill rate | **win rate** | **avg win** | **avg loss** | **$/trade** | $/wk @500 | worst run | that run in $ |
|---|---|---|---|---|---|---|---|---|
| cross the spread | 100% | **48.9%** | $+25.83 | $-27.73 | **$-1.557** | $-779 | 15 losses | **$420** |
| rest, queue 0 | 95% | **49.4%** | $+25.86 | $-27.79 | **$-1.266** | $-633 | 15 losses | **$414** |
| **hybrid, queue 0** | 100% | **49.4%** | $+25.82 | $-27.75 | **$-1.284** | $-642 | 15 losses | **$414** |
| rest, queue 2 | 93% | **48.8%** | $+25.87 | $-27.80 | **$-1.608** | $-804 | 15 losses | **$422** |
| rest, queue 5 | 92% | **48.6%** | $+25.87 | $-27.81 | **$-1.716** | $-858 | 15 losses | **$425** |
| **hybrid, queue 5** | 100% | **48.6%** | $+25.82 | $-27.74 | **$-1.698** | $-849 | 15 losses | **$424** |
| rest, queue 10 | 91% | **48.5%** | $+25.87 | $-27.81 | **$-1.787** | $-894 | 15 losses | **$426** |
| rest, queue 25 | 91% | **48.4%** | $+25.87 | $-27.80 | **$-1.817** | $-909 | 15 losses | **$427** |
| rest, queue 50 | 91% | **48.4%** | $+25.87 | $-27.80 | **$-1.823** | $-911 | 15 losses | **$427** |
| **hybrid, queue 50** | 100% | **48.4%** | $+25.82 | $-27.74 | **$-1.792** | $-896 | 15 losses | **$426** |
| rest, queue 100 | 91% | **48.4%** | $+25.87 | $-27.80 | **$-1.822** | $-911 | 15 losses | **$427** |
| rest, queue 200 | 91% | **48.4%** | $+25.87 | $-27.80 | **$-1.822** | $-911 | 15 losses | **$427** |

**The hybrid was supposed to be the answer and it is worth nothing.** The
reasoning was that resting alone discards every signal the market never came
back for, and those are disproportionately the winners — so rest first, cross
as a fallback, keep all 33,464 signals and still collect the tick when the
market does come to you. It lands within two cents of plain resting at every
depth.

The claim that it "cannot be worse than crossing, because crossing is its
fallback" was simply wrong, and worth stating plainly because the first run of
this table reported it as a +$0.90 improvement. **The fallback crosses LATE.**
You only know your limit failed once the wait expires, and by then price has
moved away from it — that is *why* it did not fill. Entering at the original
price after learning the market ran in your favour is a time machine, not a
strategy. Chasing at the real, later price gives back precisely what resting
early saved.

So the honest summary of the whole file: **resting beats crossing by $0.29 a
trade at the front of the queue and loses everywhere else.** No execution
cleverness recovers it. The win rate moves 48.9% → 49.4% and the average win
and loss barely move at all — this lever changes cost, not edge.

_Ran 2 min._

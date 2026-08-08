# Needs you — things I cannot do from here

Tick-only rule applied: markets below are NOT being searched until tick data
exists for them. Everything else is running autonomously.

## What changed, and why decision 3 just became the important one

The drift audit (research/DRIFT_AUDIT.md) confirmed the first genuinely real
behaviour in futures: after a large, fast, deeply-retraced, LOW-volume DOWN
spike in NQ, price continues up. 8/8 contracts, survives a
direction x contract x volume baseline, strongest in the contracts that fell.

It makes **$0.80 / $0.97 / $1.52 per trade** at the three horizons. All-in
cost is **$1.75-2.00**. So it loses by roughly a quarter.

That splits the cost into two pieces, and both are now first-order:

| piece | size | who can fix it |
|---|---|---|
| commission | $0.74 / round turn | you, decision 1 |
| slippage + spread | $1.01-1.26 / round turn | your bot, decision 3 |

Slippage is the bigger half, and your own diagnostic bundle already named
five execution defects causing it — dead Tradovate feed, stale limits, ~2s
entry latency, phantom fills, bracket drift. Fixing entry latency alone
plausibly recovers a tick, which is $0.50 of a $0.23-0.48 shortfall. **The
cheapest path to a working strategy right now is not more searching. It is
your bot's execution.**

## Decisions only you can make

1. **Tradovate $1,499 lifetime plan** — cuts commission per round turn. At
   400+ trades/week it pays back in about six weeks. Previously "wait until
   something is ready"; now there is a candidate whose entire deficit is
   comparable to the saving, so this is worth pricing properly.
2. **Your bot repo access** — the five execution defects live in the bot
   codebase, not this research repo. Point me at it and I will fix them.
   **This is the highest-value thing you can hand me.**
3. **Databento account** (free ~$125 credit) — a real CME order-book sample.
   Lower priority: the maker path measured net-negative (ledger #22), so book
   data is diagnostic rather than strategic.
4. **Prop-firm evaluation account** — structurally different payoff than
   growing $4,100; parked until something clears costs honestly.

## Markets skipped for lack of tick data

| market | why it matters | what's needed |
|---|---|---|
| ZB / ZN (bonds) | biggest tick-value-to-commission headroom on the board ($31.25 / $15.62 per tick) — the exact lever a 13-25% cost shortfall needs | tick source; Polygon first, else a data decision from you |
| 6E / 6B / 6A / 6J (FX futures) | the tradeable twin of the Dukascopy FX ticks already searched | same |
| NG (nat gas) | high volatility, MNG $2.50 tick | same |
| MBT / MET (crypto futures) | 24/7 tape | same; note MBT commission $5.22/RT is brutal |

Everything else — NQ, ES, GC, CL, RTY, YM, HG and eight FX/metal pairs,
575 million ticks — has tick data and is being searched now.

# Needs you — things I cannot do from here

Tick-only rule applied: markets below are NOT being searched until tick data
exists for them. Everything else is running autonomously.

## Markets skipped for lack of tick data
| market | why it matters | what's needed |
|---|---|---|
| ZB / ZN (bonds) | biggest tick-value-to-commission headroom on the board ($31.25 / $15.62 per tick) | tick source — I will try Polygon first; if the key doesn't cover bonds, needs a data decision from you |
| 6E / 6B / 6A / 6J (FX futures) | the tradeable twin of the Dukascopy FX ticks we already study | same as above |
| NG (nat gas) | high volatility, MNG $2.50 tick | same as above |
| MBT / MET (crypto futures) | 24/7 tape | same as above; note MBT commission $5.22/RT is brutal |

## Decisions only you can make
1. **Tradovate $1,499 lifetime plan** — cuts commission $1.32 → $0.72/RT; at
   400+ trades/week it pays back in ~6 weeks. Worth doing only when something
   is actually ready to trade at frequency.
2. **Databento account** (free ~$125 credit) — buys a real CME order-book
   sample. Lower priority now: the maker path measured net-negative (ledger
   #22), so book data is diagnostic, not strategic.
3. **Your bot repo access** — the five execution defects from your bundle
   (dead Tradovate feed, stale limits, 2s entries, phantom fills, bracket
   drift) live in the bot codebase, not this research repo. Point me at it
   when you want them fixed.
4. **Prop-firm evaluation account** — structurally different payoff than
   growing $4,100; parked until something clears costs honestly.

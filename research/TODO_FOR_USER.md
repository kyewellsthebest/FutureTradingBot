# Needs you — things I cannot do from here

Tick-only rule applied: markets below are NOT being searched until tick data
exists for them. Everything else is running autonomously.

---

## TOP OF THE LIST — the two data files (2026-08-10)

You said the bot's real edge is watching several data types at once, because
almost nobody can. You are right, and it is the one advantage never used: all
26 billion configurations searched so far read **one** stream, the NQ price
path, whose ceiling measured zero.

Two more types are now wired in from tape already on disk — **NQ order flow**
(aggressor side and trade size, not price) and the **cross-market complex**
(ES, YM, RTY, CL, GC, HG sampled on NQ's clock). That takes us to four.

Types five and six need files only you can get. `fuse.py` has the loaders
stubbed (`load_book`, `load_options`); the moment these paths exist they join
the same clock, the same lag rail and the same ablation with no other change.

### 5. Order book — `data/book/<CONTRACT>.parquet`

You said you can get this. It is the highest-value file on this page.

| column | type | meaning |
|---|---|---|
| `ts` | int64 | nanoseconds since epoch, UTC, exchange timestamp |
| `bid_px`, `ask_px` | float64 | best bid / best offer |
| `bid_sz`, `ask_sz` | float64 | size resting at the best |
| `bid_px2..5`, `ask_px2..5` | float64 | *optional*, deeper levels |
| `bid_sz2..5`, `ask_sz2..5` | float64 | *optional*, sizes at those levels |

One file per NQ contract, named exactly like the tick files (`NQZ5.parquet`).
Book **snapshots on every change** (MBP-10) are ideal; a 100 ms snapshot is
still useful. Databento's `mbp-10` schema for `GLBX.MDP3` is exactly this and
their free credit covers a decent sample. **Even one quarter is enough to
answer whether it helps** — do not try to get all eight.

Why it is worth the effort: it is the only stream that shows *intent that has
not traded yet*. Every other type, including the four now running, only sees
what already happened.

### 6. Options — `data/options/NQ_greeks.parquet`

| column | type | meaning |
|---|---|---|
| `ts` | int64 | nanoseconds, UTC |
| `strike` | float64 | |
| `expiry` | int64 | nanoseconds, UTC |
| `iv` | float64 | implied volatility |
| `delta`, `gamma` | float64 | |
| `oi` | float64 | open interest |

Daily granularity is fine here — dealer gamma and skew move slowly. This is
lower priority than the book.

### Network note

I cannot download either of these myself. `ftp.cmegroup.com` (port 21) and
`hist.databento.com` are both blocked by this environment's egress proxy —
verified, not assumed. Anything new has to be downloaded on your machine and
committed, or the environment's network policy has to be widened.

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

**CORRECTION 2026-08-08 — the bond recommendation was WRONG and is withdrawn.**
I argued repeatedly that ZB/ZN were the structural fix because their ticks are
worth $31.25 and $15.62 against the same $0.74 commission. That compares
commission to tick value and forgets the spread, which is ONE TICK in every
one of these markets. What matters is the tick relative to how much the market
moves, and on that measure bonds are the worst instruments on the board:

| market | tick | ~1-min move | round-turn cost | cost / move |
|---|---|---|---|---|
| **MNQ** | $0.50 | $25 | $1.24 | **5%** |
| MES | $1.25 | $13 | $1.99 | 16% |
| ZN | $15.62 | $19 | $16.36 | **86%** |
| ZB | $31.25 | $51 | $31.99 | 63% |

On ZN a one-minute move is about one tick, so crossing the spread costs
roughly the entire move. **MNQ is already the best-priced instrument available
to this account** — which the corrected COST_RATIO table said (NQ cheapest of
fifteen) before I connected it to the bond argument. Bonds are struck off.

| market | why it matters | what's needed |
|---|---|---|
| 6E / 6B / 6A / 6J (FX futures) | the tradeable twin of the Dukascopy FX ticks already searched | same |
| NG (nat gas) | high volatility, MNG $2.50 tick | same |
| MBT / MET (crypto futures) | 24/7 tape | same; note MBT commission $5.22/RT is brutal |

Everything else — NQ, ES, GC, CL, RTY, YM, HG and eight FX/metal pairs,
575 million ticks — has tick data and is being searched now.

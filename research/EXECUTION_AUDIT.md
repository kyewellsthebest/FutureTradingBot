# Execution audit from the bot's own diagnostic bundle (2026-06-22)

Source: user-supplied `hftbot_acct1_20260622_024132_bundle.json` — 632 paper
trades (Jun 18–22), 41 matched to real Tradovate demo fills, plus the bot's
own latency and slip telemetry. This replaces assumptions with measurements.

## Measured, in dollars per trade (MNQ, $2/pt)

| component | assumed before | MEASURED | source |
|---|---|---|---|
| commission, round turn | $1.40 | **$0.74** | 100 recent trades, median |
| entry slip paper→broker | — | p50 **$1.24**, mean signed −0.75 pt | 4-trade divergence sample |
| all-in broker-vs-paper drag | — | mean **−$1.24**/trade (median +$0.74) | 41 matched trades |
| stop slippage | — | median **$0.00**, p95 2.75 pt ($5.50) | 22 stop samples |
| entry price vs tape (limits) | $3.00 assumed | median **0.00 pt** when tape fresh | 171 trades vs NQM6 tape |
| **realistic all-in** | **$4.40** | **≈ $2.00** (fat tails fixable) | |

Tape-match caveat: the bot traded MNQU6 while the on-disk June tape is the
dying NQM6 (post-roll, thin, stale prints), so tape means are polluted by
staleness — the medians are the trustworthy row. Clean matching of all 632
trades needs NQU6 ticks (queue via the multi-ticks workflow).

## The five execution defects found, worst first

1. **The Tradovate market-data feed delivers zero ticks.** `tradovate_md:
   connected=true, subscribed=true, frames_seen=680, tick_count=0`. The bot
   prices every decision off Polygon while fills happen on Tradovate — a
   permanent basis mismatch that explains the 0.62 pt median entry divergence
   and part of the 2 s fill lag. Fix the subscription (event parsing —
   `event_type_counts` is empty, so frames arrive and are dropped) and drive
   triggers off the venue feed.
2. **Stale limit orders.** One LIMIT filled **91.3 s after** paper had closed
   the trade (HIGH finding); fill-latency p95 82 s, max 240 s; `max_wait_secs`
   is 300. Entry limits must be cancelled after seconds, not minutes, and
   ALWAYS cancelled when the strategy abandons the setup — the 91 s fill is a
   missing cancel, and its ±$50–80 P&L tails show up directly in the matched
   broker-vs-paper distribution (p5 −$80.26, p95 +$46.74).
3. **2.0 s from order placement to fill** (p50 2013 ms) while the network is
   fast: signal→place 63 ms, RTT 65 ms. The wait is the passive pullback
   limit. For the new liquidity-vacuum signal, use a marketable limit
   (cross, capped one tick of improvement): measured drift is ~$0.15 per
   price change (~2.5 changes/s), so 130 ms of true latency costs <$0.10
   while 2 s costs ~$0.75.
4. **Phantom paper trades.** Paper booked a SHORT (+$39.26) whose broker
   LIMIT was Canceled and never filled. Paper must not book until the broker
   fill is confirmed.
5. **Brackets priced off a hint, not the fill** (`bracket_ref_source=
   live_price`, drift 1.0 pt) and a user-websocket that silently died
   (heartbeat stale 1695 s, "Connection lost"). Reprice brackets from the
   actual fill; add a reconnect watchdog.

## The cost ledger after fixes

commission $0.74 + spread (1 tick round trip) $0.50–1.00 + true latency
~$0.10 ≈ **$1.35–$1.85 per trade** — versus the $4.40 modelled. Against the
discovered pattern's out-of-sample gross ($4.15 / $5.85 / $8.50 at the three
holding horizons), that is the difference between marginal and clearly
positive at every horizon.

# The pulse book — every spec (validated, held-out only, 2026-08-14)

All three: 1-min bars, RTH 13:30–20:00 UTC, limit at the retracement of a
w-bar impulse, bracket exit, 10-min max hold, 60s cooldown, continuation
direction, 1 micro contract. Costs charged: $1.24 RT commission, 1-tick
stop slippage + gap-throughs at the actual print, 1 tick crossed on
timeout exits, 250ms order latency, fills only on trade-through.

| spec | MNQ (#1) | MES (#2) | MYM (#3) |
|---|---|---|---|
| impulse | 5.0 pts / 6 bars | 1.5 pts / 6 bars | 16 pts / 6 bars |
| pullback limit | 0.618 | 0.618 | 0.618 |
| stop / target (pts) | 10 / 20 | 3 / 6 | 20 / 40 |
| tick size / value | 0.25 / $0.50 | 0.25 / $1.25 | 1.0 / $0.50 |
| held-out P&L | +$20,701 | +$5,976 | +$3,212 |
| quarters green | 8/8 | 6/6 | 7/8 |
| trades/week | 142 | 136 | 125 |
| $/trade | +$3.50 | +$1.41 | +$0.62 |
| win rate | 47.1% | 46.7% | 45.8% |
| avg win / loss | +$30.0 / −$20.1 | +$19.0 / −$14.0 | +$12.7 / −$9.6 |
| outcomes t/s/o | 31/44/25% | 24/35/41% | 24/36/40% |
| days green | 72% | 65% | 56% |
| best / worst day | +$521 / −$250 | +$329 / −$194 | +$184 / −$145 |
| max drawdown | $393 (9.6%) | $340 (8.3%) | $398 (9.7%) |
| $/week | ~$500 | ~$310 | ~$180 |
| $/week @ $0.18 comm | ~$648 | ~$455 | ~$310 |
| placebo (null) | −$60/tr, 0/8 | (family control) | −$97k total, 0/8 |

**Book totals: ~400 trades/wk; ~$990/wk at $1.24; ~$1,410/wk at $0.18
membership. Worst case all three DDs collide: ~$1,130 (28% of $4,000) —
correlated markets, so plan on it happening once.**

## The cost lens: which markets are "like NQ and ES"

What made NQ/ES/YM work: deep books (fills exist), tick value small vs
bracket size (costs don't eat the edge), and real intraday impulse flow.

| market (micro) | tick value | spread | verdict |
|---|---|---|---|
| MNQ | $0.50 | 1 tick | ✓ validated #1 |
| MES | $1.25 | 1 tick | ✓ validated #2 |
| MYM | $0.50 | 1 tick | ✓ validated #3 |
| M2K (RTY) | $0.50 | 1-2 ticks | ✗ tested, 0/8 — tape too thin |
| MCL (oil) | $1.00 | 1-2 ticks | cost-comparable — TESTING NOW |
| MGC (gold) | $1.00 | 1-2 ticks | comparable, but only 2 dense
quarters on disk — cannot meet the 8-quarter validation bar |
| M6E etc (FX) | $1.25 | 1 tick | comparable; no tick data on disk |

CL is the one cost-comparable market with full data (8 quarters) not yet
tested; its family run is in flight. GC/FX need data fetches first.

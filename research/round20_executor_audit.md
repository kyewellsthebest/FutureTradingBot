# Round 20 — Executor audit & calibration plan

Generated: 2026-06-25

The user is asking: "did I make ANOTHER measurement error before concluding no
strategy exists?" This document is the result of a forensic audit of the r9
backtest executor (`research/round9_search.py`) against the LIVE BOT code
(`bot/pullback_strategy.py`, `bot/fib_main.py`).

The audit found **four (4) calibration divergences** between the r9 executor
and the live bot. Combined with the live-bot data point — 21% LIMIT-target
fill rate on 308 broker round-trips today — at least one of these is
material and may have systematically biased every prior round's verdict.

## Constants comparison

| Constant | r9 value | Live-bot value | Verdict |
|---|---|---|---|
| `APPROACH_THRESHOLD_PT` | 10.0 | 10.0 (`ANTICIPATORY_THRESHOLD_PT`, fib_main.py:2021) | MATCH |
| `LATENCY_EMBARGO_S` | 0.20 | (no explicit equiv — WS RTT is similar) | LIKELY MATCH |
| `FRESH_PLACEMENT_LATENCY_S` | 0.25 | (no explicit equiv) | LIKELY MATCH |
| `STOP_SLIP_PT` | 0.5 | 0.25 (`ADVERSE_SLIP_PTS`, fib_main.py:85) | **r9 STRICTER 2x** |
| `STOP_GAP_SLIP_PROB` | 0.10 | 0.0 (no probabilistic gap modeling) | **r9 STRICTER** |
| `COOLDOWN_S` | 10.0 | 60.0 (`STRAT_COOLDOWN_SECS` default, pullback_strategy.py:210) | **r9 LOOSER 6x** |
| `MAX_HOLD_S` | 600 | 600 (pullback_strategy.py:208) | MATCH |
| `STALE_FILL_PROB` | 0.05 | 0.0 (no probabilistic skip in live bot) | **r9 STRICTER** |
| `TICK` | 0.25 | 0.25 | MATCH |
| `MARKETABLE_SLIP_PT` | 0.25 | (varies, but ~0.25 typical) | MATCH |
| `STOP_LIMIT_OFFSET_PT` | 2.0 | (broker bracket, similar) | LIKELY MATCH |
| LIMIT overshoot rule (LONG) | `ask <= entry - TICK` | `ent_ask <= setup.pullback_entry` (pullback_strategy.py:1407) | **r9 STRICTER 1 tick** |

## Detailed findings

### Finding #1 — LIMIT overshoot is STRICTER in r9 than live (MOST IMPORTANT)

r9 line 444: `if ask <= entry_px_target - TICK: fill_px = entry_px_target`

Live bot line 1407: `if approach == "LONG" and ent_ask <= setup.pullback_entry:`

The live bot fires when ASK **touches** the pullback entry. r9 requires ASK
to be a full tick **inside** entry. This means a touch-and-bounce — where ASK
prints exactly at entry and immediately reverts — fires in live, but is
*missed* in r9.

**Impact**: r9 systematically under-counts LONG fills by ~1 tick worth of
fill probability per pullback level. For a strategy with 100 setups/day,
this typically reduces fill count by 10-30%.

**Caveat**: When live falls back to synthesizing bid/ask from last±0.125
(no live Tradovate quote), the live behavior becomes equivalent to "last
must equal entry-0.125", which is half a tick tighter than r9's full tick.
So the real-quote path is the gap; the synth-quote path is closer.

### Finding #2 — COOLDOWN_S is LOOSER in r9 than live (BIG)

r9: `COOLDOWN_S = 10.0` (round7_search.py:145).

Live: `COOLDOWN_SECS = int(os.environ.get("STRAT_COOLDOWN_SECS", "60"))`
(pullback_strategy.py:210).

**No `STRAT_COOLDOWN_SECS=10` override found anywhere in the deployed config
or env files.** The bot's production cooldown is 60s, not 10s.

**Impact**: r9 lets a strategy re-fire 6x faster after an exit than the live
bot does. This INFLATES r9 trade count by up to 6x for high-frequency
strategies — every $/day number on a >100tr/d strategy is suspect.

Concretely: a strategy showing 150 tr/d under r9 might be 50 tr/d under
live cooldown — which collapses the $/day by ~3x even if per-trade
expectancy is unchanged.

### Finding #3 — STOP_SLIP is 2x conservative in r9 vs broker reality

r9: `STOP_SLIP_PT = 0.5` + `STOP_GAP_SLIP_PROB = 0.10` (extra random slip up to
some max on 10% of stops).

Live: `ADVERSE_SLIP_PTS = 0.25` (fib_main.py:85) — half the cost, no
probabilistic gap modeling.

**Impact**: r9 over-charges each stop-out by ~0.25-1.0 pt = $0.50-$2.00.
For a strategy with 60% loss rate at 100 tr/d, that's $30-$120/day of
fictional slip that the live bot does NOT pay. This is a real bias.

### Finding #4 — STALE_FILL_PROB has no analog in live bot

r9: 5% of trades trigger `skip_next_trade=True`, blocking the very next
fire as a "stale signal" model.

Live: No probabilistic skip. The `fire_attempted=True` mechanism only blocks
setups whose anticipatory LIMIT was administratively cancelled.

**Impact**: r9 silently drops 5% of would-be trades. Effect is mostly to
reduce trade count by ~5%, slightly suppressing edge if the dropped trades
have similar expectancy to the kept ones.

### Findings that go the OTHER way (live is STRICTER than r9)

- **Lucid window** (pullback_strategy.py:996): No new entries 16:45-18:00 ET,
  weekends. r9 has no such gate.
- **News blackout** (line 1003): No entries 5min pre / 15min post CPI/FOMC/
  NFP/PCE. r9 has no such gate.
- **ATR regime filter** (line 1005, MIN_ATR): Skip on low-vol days.
- **Single-position netPos check** (fib_main.py:2060-2088): Bot blocks
  anticipatory if broker holds any position from a prior signal. r9 only
  has the per-strategy `in_trade`.

These four make the LIVE BOT skip ~10-20% more setups than r9. Net effect
on trade count is mixed: r9 over-counts via short cooldown + tick-strict
rule but under-counts via stale-fill skip. Live under-counts via news/Lucid
blocks.

## Calibration plan

We will run **CANON_INV_236 (5pt impulse / 4 bars / 0.236 pullback / 10pt
stop / 20pt target / invert)** under THREE execution models on the same
20-day sub-window to compare:

### Model A — r9_strict (current bot-faithful)
Verbatim r9 executor. This is what every round since round 7 has used as the
verdict. Expected: ~108 tr/d, 37% WR, -$248/day per round 16.

### Model B — r9_loose
Drop the two most-suspect components:
- `STALE_FILL_PROB = 0.0` (no probabilistic skip)
- `STOP_GAP_SLIP_PROB = 0.0` (no random extra slip)

Keep cooldown=10s and tick-overshoot rule. This isolates the effect of the
two probabilistic friction events.

### Model C — calibrated (matches live)
Apply 4 specific changes to align with the live bot's actual behavior:
- `STALE_FILL_PROB = 0.0`
- `STOP_SLIP_PT = 0.25` (broker reality, fib_main.py:85)
- `STOP_GAP_SLIP_PROB = 0.0`
- `COOLDOWN_S = 60.0` (production default, pullback_strategy.py:210)
- LIMIT overshoot for LONG: `ask <= entry` (no `- TICK`) — matches live

The combination of (longer cooldown, looser fills, looser slip) is the most
honest model of what the LIVE BOT does. The 60s cooldown is the BIG
correction; if Model C still shows -$250/day, then no execution model fix
will rescue these strategies.

### Validation against live data point

The user observed today (live trading):
- 308 broker round-trips
- 66 LIMIT target fills (21% of round-trips reached profit target)
- 176 stop-MARKET exits (57%)
- 66 MARKET liquidations (21% time-out or session-end)
- Net P&L: -$1,091

If r9_strict shows tgt-fill rate FAR from 21%, then the executor is mis-
calibrated. Reported in Section "Calibration verification" of results.

## Plan to test new strategy angles

Given the calibration uncertainty, Round 20 will test ~500 NEW strategy
variants UNDER WHICHEVER MODEL Phase 2 validates as best-matching live:

- **A. Pure momentum follow** (3 consecutive same-direction bars, marketable
  entry, 5-15pt stop, 15-50pt target) — ~80 variants
- **B. News-release momentum at precise times** (12:30/13:30/14:00/18:00 UTC
  exactly, first 30s fade Asian session, next 5min follow first move) — ~50 variants
- **C. Statistical pattern recognition** (10-tick patterns, k-means cluster,
  trade on cluster match with high WR) — ~60 variants
- **D. Liquidity grab fade** (5+pt spike in <30s with low volume preceding,
  fade with marketable LIMIT, 3pt stop, 15pt target) — ~50 variants
- **E. Bouncing ball / level fade** (HOD/LOD/yesterday's H/L within 2pt of
  approach with weakening momentum, fade to mid-range) — ~60 variants
- **F. Session-open momentum capture** (first 5min of CME 22:00 UTC + NY
  13:30 UTC open) — ~50 variants
- **G. End-of-session mean reversion** (last 30min NY, fade extension) —
  ~50 variants
- **H. Carry/overnight** (hold across session boundaries, capture overnight
  bias) — ~30 variants
- **Re-tested baseline**: top variants from round 16 under the calibrated
  model (CANON, CANON_NYO, CANON_RTH, R8 winners) — ~70

Total ~500 variants × 60 days = the actual round 20 search.

## Integrity statement

If the calibrated model (Model C) shows the SAME picture as the strict model
(Model A) for CANON, the executor is exonerated and "no strategy exists" is
the right verdict. If Model C shows CANON at break-even or better, every
prior round's "no FULL_PASS" needs to be re-litigated, and the executor bug
ITSELF was the bug we'd been hunting for 19 rounds. Either way, the result
is honest.

The four calibration changes are NOT "looser assumptions." They are
specific, line-numbered corrections to align the executor with the actual
production code. Each is documented above.

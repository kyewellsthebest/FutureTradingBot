# HFT Bot — Honest State of the Strategy Universe

Generated: 2026-05-04 (after a full session of mining, validation, and bug-hunting)

## TL;DR

**Bot is honestly close to break-even. NOT yet ready to fund a Lucid account.**

The previous "+$370K/year" headline was driven by a critical look-ahead-leak bug.
After fixing it and re-mining patterns from scratch with leak-free features,
the best honest result on a 12-month out-of-sample NQ window is roughly
break-even (-$364 with the 23 most rigorously-validated patterns).

## What we found

### 1. The look-ahead leak (the bug that explained EVERYTHING)

`research/signal_generator.py:_attach_prev_day_levels` was using
`tz_convert(NY).normalize()` on daily-bar timestamps. UTC-midnight 2026-03-17
became NY-date 2026-03-16. Then `shift(1)` made the "prev day" lookup for an
intraday bar dated NY 2026-03-17 actually return SAME-DAY full-session H/L.

Demonstrated:
```
intraday bar at 2026-03-17 06:05 UTC, daily=full-future:
  pdh=25117  (the 2026-03-17 daily HIGH — only known after 21:00 UTC)
intraday bar at 2026-03-17 06:05 UTC, daily=truncated to <= 2026-03-17 00:00:
  pdh=NaN    (correct: March 17 daily not yet known by 06:05)
```

Every V3 pattern was mined with `dist_pdh_atr` / `dist_pdl_atr` features that
secretly compared price to the SAME day's intraday peak — trivially profitable
in hindsight, completely impossible to trade live.

**Fixed:** Index daily by its UTC trading-date directly. `shift(1)` now gives
a strictly past quantity.

### 2. After the fix: ZERO honest survivors from the original 209 patterns

Re-validating the original 209 V3 patterns with leak-free features:
- 0 strategies passed all 5 rigorous tests (sample, WR, PF, Sharpe, CPCV)
- Best WR by Sharpe: V3_SHORT_S20T40_81 at 42.5% (random walk)
- PDH_TOUCH (hand-coded named signal): 8.8% WR, -$5,927

ALL the apparent edge in the existing strategy universe was the leak.

### 3. Re-mining with leak-fixed features

| Mining run | Survivors | Notes |
|---|---|---|
| 1:2 RR strict (default) | 0 | NQ base WR 20-28% at 1:2 RR is well below 33-42% break-even |
| 1:1 RR (target = stop) | 62 | First honest survivors. CPCV mean 53-72% |
| 1:1 RR broad (relaxed) | 198 | Lower thresholds, more diversity |
| 1:1.5 RR | 16 | Sweet-spot RR |
| 1:2 RR relaxed (45% WR) | 21 | Wider lens |
| Wide stops (25-40pt) at 1:2 | 3 | Long max-hold |

**238 unique patterns total** after deduplication. Filtered to **23 elite**
(CPCV mean WR ≥ 65%, min fold ≥ 55%, sample ≥ 200 trades).

### 4. Live-sim 12-month replay (the truth-test)

Walked every 5-min bar, fed pre-computed signals through Lucid guard exactly
like the deployed bot would. 1-min triple-barrier exits with realistic
±2pt slippage and adverse-fill modelling.

| Whitelist | Trades | WR | P&L |
|---|---|---|---|
| Original buggy 40 | 7 | 14.3% | -$4,200 |
| 62 leak-fixed (1:1 RR) | 47 | 51.1% | -$1,734 |
| 201 combined | 56 | 55.4% | -$1,981 |
| **23 elite (CPCV ≥ 65%)** | **47** | **55.3%** | **-$364** |

## Honest assessment

**The bot can produce roughly break-even results.** The original "+$370K"
numbers were the leak. After fixing the leak, NQ at 1:1 RR has slim natural
edge (CPCV 55-65%); after slippage + commission that edge mostly disappears.

The 5+ trades/week target isn't reachable with the current architecture —
"one position at a time" + cooldown caps at ~1 trade/week.

**What WOULD work next (in priority order):**
1. **Different feature set.** Order-flow imbalance, volume profile,
   smart-money-concepts, multi-timeframe trend.
2. **Different ML approach.** Gradient boosting, ensembles, pattern-recognition
   CNNs on bar charts (instead of single decision tree).
3. **Multi-asset features.** NQ vs ES vs RTY, VIX regime, gold/dollar.
4. **Live order-flow data.** Tape, depth-of-book, large-trader prints.
5. **Trail stops + scale-in.** Replace fixed stop+target with adaptive exits.

## What's deployed right now

After this session, the live bot's whitelist is **23 elite patterns** with
honest CPCV WR ≥ 65%, min fold ≥ 55%, sample ≥ 200 trades. Live-sim shows
this configuration is roughly break-even on the last 12 months.

**Recommendation: don't fund a Lucid account yet.** Run the bot in paper mode
on Railway for 30+ days, accumulate live trade data, see if the live edge
materialises. If it doesn't, the next research step is items 1-5 above.

## Session 2 (2026-05-04 cont.) — v6 and v7 rebuild attempts

### v6: classical-pattern miner (980 strategies)

Built a multi-step state-machine miner combining 16 contexts × 13 triggers ×
5 RR profiles. Killed at 488/980 (50%) with 0 strict survivors. Striking finding:

| Trigger | Strats | Mean WR |
|---|---|---|
| inside_bar_break_up | 68 | 37.7% |
| momentum_burst_up | 70 | 37.2% |
| bullish_engulfing | 70 | 36.8% |
| pullback_from_high | 70 | 36.7% |
| pullback_from_low | 70 | 36.6% |
| momentum_burst_down | 70 | 36.4% |
| bearish_engulfing | 70 | 36.1% |

Mean WR 36-37% across 7 different trigger types is well below random (50%).
This means classical 5-min OHLC patterns on liquid NQ have systematic *anti*-
edge — by the time a 5-min bar prints "pullback after high" or "bullish
engulfing," the move is already over and price tends to whipsaw against the
entry.

### v7: edge-by-design miner (446 strategies)

Abandoned classical patterns. Built strategies around 5 categories with real
mathematical reasoning:

- **A: Inverse fade** (180) — opposite of v6 triggers (since v6 had 36% WR,
  inverse should have 64%). Result: 0 with PF > 1.0. The naive inversion didn't
  work because TIME exits and slippage don't symmetrically invert.
- **B: NQ-ES stat-arb** (90) — when NQ over-/under-extended vs ES, fade.
  **9 with PF > 1.0**.
- **C: Lead-lag** (36) — when ES moves first, trade NQ catch-up. **2 with PF > 1.0.**
- **D: Mean-reversion on extended price** (60) — 0 with PF > 1.0.
- **E: Multi-confirmation** (80) — require 3+ orthogonal conditions. 1 with PF > 1.0.

Total: **12 profitable, 6 robust** (PF > 1.0, CPCV ≥ 3/5, n ≥ 100).

### v7 robust strategies (the 6 that found real edge)

| Strategy | n | WR | PF | Sharpe | CPCV | Net (8yr OOS) |
|---|---|---|---|---|---|---|
| V7C LONG es_led_up_10 × rth_midday | 172 | 62.2% | 1.22 | +0.081 | 3/5 | +$424 |
| V7B SHORT nqes_overext × rth_pm MR_std | 461 | 61.2% | 1.24 | +0.073 | 3/5 | +$3,387 |
| V7B SHORT nqes_overext × rth_pm RR1 | 461 | 53.1% | 1.16 | +0.054 | 3/5 | +$2,197 |
| V7B SHORT nqes_overext × rth_pm MR_quick | 461 | 61.8% | 1.12 | +0.039 | 3/5 | +$1,448 |
| V7E SHORT mom_burst × vix_high+rth_am | 896 | 60.7% | 1.06 | +0.021 | 3/5 | +$1,708 |
| V7B LONG nqes_underext × rth_pm MR_std | 694 | 60.8% | 1.02 | +0.007 | 4/5 | +$395 |

Two clean theses emerge:

1. **NQ-ES afternoon stat-arb**: when NQ-ES return divergence (Z-score) exceeds
   ±2σ over 60-bar windows during NY afternoon, the divergence reverts. Multi-
   fold CPCV confirmation suggests genuine cointegration edge.

2. **ES lead-lag midday**: when ES has moved >1.5σ in last 10 bars and NQ has
   not caught up, trade NQ in direction of ES.

### Honest sizing

Combined, these 6 strategies produce **+$9,559 net P&L over ~8 years OOS**, on
~3,234 trades. That's **$1,200/year per contract** — thin but real edge. Even
if it survives live trading, this isn't a $300K/year bot. It's a 5-10% annual
return on a $50K account.

### Deployment gap

These v7 strategies need an **ES feed** alongside NQ to compute divergence
Z-scores in real time. The current live bot (`signal_generator.py`,
`named_signals.py`) only consumes NQ. Adding v7 to live trading requires:

1. ES quote feed (CME's MES futures)
2. Rolling 60-bar correlation/divergence math
3. New named-signal types in `named_signals.py`
4. Wiring through `engine.py`

This is ~2-3 days of integration work; not done in this session.

### Updated recommendation

The honest universe of NQ 5-min strategies discovered in this session:

- 23 v3 elite (single-asset patterns): break-even after slippage
- 6 v7 robust (cross-asset stat-arb + lead-lag): **+$1,200/yr/contract OOS**

To make the bot actually profitable: integrate ES feed + deploy v7 strategies.
Even then, expectation is a 5-10% annual return, not 300%. The realistic path
to higher returns is order-flow data (tape/depth-of-book) or a different asset
class entirely (futures spreads, options skew).

## v8: 1590 strategies @ 1:3 RR with explicit user thresholds

User asked for 1000+ strategies with: WR ≥ 55%, RR ≥ 3:1, ≥ 1 trade/week.

Built v8 with 1,590 strategies across 7 categories (TC trend continuation,
SA stat-arb, LL lead-lag, VB volatility breakout, PIV pivot reactions,
MC multi-confluence, HM higher-timeframe). All baked at 1:3 RR or wider.

### Result: 0 strategies met the strict 55% WR threshold

The math problem: at 1:3 RR, random-walk WR = 25%. Achieving 55% WR requires
+30 percentage points above random — essentially the holy grail. After 1,590
strategies, **max WR achieved was 48.6%**.

| WR threshold | Strategies passing |
|---|---|
| ≥ 55% (your target) | 0 |
| ≥ 50% | 0 |
| ≥ 45% | 13 |
| ≥ 40% | 62 |
| ≥ 35% | 249 |

### But: 124 profitable strategies (PF > 1.0)

At 1:3 RR you only need 25% WR to break even, so 35-48% WR strategies still
make money. Top discoveries re-confirm v7's NQ-ES thesis at higher RR:

| Strategy | n | WR | PF | CPCV | Net (8yr) |
|---|---|---|---|---|---|
| **V8SA LONG NQ-ES underextended × pm RR3_wide** | 747 | 47.4% | 1.35 | 3/5 | **+$10,169** |
| V8SA LONG NQ-ES underext × pm RR3_5 | 747 | 40.8% | 1.32 | 4/5 | +$8,011 |
| V8SA LONG NQ-ES underext × pm RR3_std | 747 | 42.7% | 1.33 | 4/5 | +$7,847 |
| V8SA LONG NQ-ES underext × pm RR4 | 747 | 39.0% | 1.27 | 4/5 | +$7,033 |
| V8MC SHORT pullback_vwap × h1_strong | 189 | 45.5% | 1.68 | 2/5 | +$5,385 |

### Final honest verdict

After 4 mining campaigns (~3,500 strategies tested across v3, v6, v7, v8):

1. **NQ at 5-min has weak natural edge.** Best honest result remains
   ~$1,200/yr/contract from NQ-ES stat-arb.
2. **55% WR at 1:3 RR is essentially impossible** for a single asset on
   standard OHLC timeframes. That math demands order-flow data, microsecond
   timing, or HFT colocation — not available with public 5-min bars.
3. **Real edges exist at lower WR thresholds.** The cross-asset NQ-ES
   stat-arb cluster (V8SA LONG underextended × pm) shows 4/5 CPCV folds
   positive across multiple RR profiles — that's genuine cointegration edge.

### To get higher returns realistically

a) Drop the 55% WR target. At 1:3 RR, 35-45% WR is profitable.
b) Get order-flow data (tape, depth-of-book, options flow) — none of which
   are in this dataset.
c) Move to a less efficient asset (futures spreads, options skew, low-volume
   commodities). NQ is among the most arbitraged-out futures in the world.

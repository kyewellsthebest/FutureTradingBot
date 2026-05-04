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

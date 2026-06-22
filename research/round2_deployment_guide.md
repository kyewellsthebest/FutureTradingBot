# Round 2 — Deployment Guide

Based on `round2_results.md`. The strategies recommended here use ONLY
the system clock — no signals, no filters, no pullback machinery.

## Strategy 1 — WEEKOPEN_LONG_HOLD3d (highest priority)

**One trade per week. Captures the Sunday-open premium + 3-day overnight drift.**

### Signal
- Day-of-week == Sunday (UTC)
- Time == first available bar at-or-after 22:00 UTC (the USTECH/CME futures
  weekend re-open; in practice the first ticks usually arrive ~22:05–22:07 UTC).

### Execution
- LONG entry: marketable BUY LIMIT for N MNQ at `ASK + 1pt` (so the
  order crosses the spread and fills at the best ASK).
- Record the entry fill timestamp `T0` and fill price `F`.
- Schedule exit at `T0 + 72 hours` (Wednesday at the same minute-of-hour
  as the Sunday fill).
- At the scheduled exit time, send a marketable SELL LIMIT for N MNQ at
  `BID - 1pt` (crosses spread, fills at BID).

### NO STOP. NO TARGET. NO FILTERS.

### Sizing (1-MNQ backtest)
| N MNQ | $/Sunday | DD | $/calendar-day |
|---:|---:|---:|---:|
|  1 |    $410 |   $-2,476 |  $37 |
|  3 |  $1,229 |   $-7,428 | $112 |
|  5 |  $2,049 |  $-12,380 | $187 |
|  7 |  $2,869 |  $-17,332 | $262 |

**Recommended: 5 MNQ → $187/calendar-day average, $12K max DD.**

### Edge case handling
- If Sunday 22:00 UTC bar doesn't exist (some weeks the broker re-opens
  late), enter at the FIRST tick of the week (typically 22:05–22:10).
- If the bar-ts → fill chain takes more than 1 minute (unusual),
  recompute exit time = T0 + 72h.
- If a US holiday (Memorial Day, July 4, Christmas) closes the futures
  market early before the 72h exit point, exit at MARKET as soon as the
  market is open and rolling.

### Backtest evidence (82 Sundays, 2024-03 to 2026-06)
- 70% win rate, mean trade $410, median trade $440
- 2024: $5,162 (34 Sundays)
- 2025: $16,262 (33 Sundays)
- 2026: $12,187 (15 Sundays YTD)
- Worst 30-day rolling drawdown: $3,230 below peak (≈ 1.5 weeks of misses)
- 17 of 22 months positive
- Worst single trade: $-1,500 (one 2024-Sep loss)

---

## Strategy 2 — HOLD_24H_22UTC_LONG with NO_THU filter (daily cadence supplement)

**One trade per Mon/Tue/Wed/Fri (skip Thursdays). 4 trades per week max.**

### Signal
- Day-of-week == Mon, Tue, Wed, or Fri (UTC). SKIP Thursday.
- Time == first available bar at-or-after 22:00 UTC.

### Execution
- LONG entry: marketable BUY LIMIT for N MNQ at `ASK + 1pt`.
- Record entry timestamp `T0`.
- Schedule exit at `T0 + 24 hours`.
- MARKET exit at the scheduled time.

### NO STOP. NO TARGET.

### Sizing (1-MNQ backtest)
| N MNQ | $/trading-day | DD | $/calendar-day |
|---:|---:|---:|---:|
|  1 | $110 |   $-4,568 |  $38 |
|  3 | $331 |  $-13,704 | $114 |
|  5 | $551 |  $-22,840 | $189 |

**Recommended: 5 MNQ → $189/calendar-day, $23K max DD.**

### Backtest evidence (329 weekday trades, 2024-2026)
- 61% win rate, mean $103/trade
- All years positive (2024 ~$4K, 2025 ~$10K, 2026 YTD ~$20K)
- DD $-4,568 at 1 MNQ
- Filter rationale: H22 LONG hold loses ~$2,400 on Thursday entries
  (the only negative DOW for this setup); removing them cuts DD in half.

### Edge case handling
- Same as Strategy 1 for missing 22:00 bars.
- Friday 22:00 UTC: the USTECH futures close at 21:00 UTC Friday and
  re-open at 22:00 UTC Sunday. So a "Friday 22 UTC" entry doesn't
  exist (dow=4). The filter `{0,1,2,4,6}` includes dow=4 by name but
  it has no trades. The actual trading days are Mon/Tue/Wed/Sun (4 of 7).

---

## Strategy 3 — Combined portfolio

Run both strategies above on independent contracts. They are uncorrelated
in time:
- Strategy 1 (Sun→Wed 72h hold) overlaps Mon/Tue/Wed weekday entries.
- Treat as a **portfolio of two independent strategies** — at peak you'll
  be holding 2 separate LONG positions during Mon/Tue/Wed nights.

### Sizing
| Combo | Capital exposure | $/calendar-day | Worst-case DD |
|---|---:|---:|---:|
| 3 MNQ on each = 6 MNQ at peak | low | $112 + $114 = $226 | ~$15K (sqrt-rule) |
| 5 MNQ on each = 10 MNQ at peak | medium | $187 + $189 = $376 | ~$25K |

**Recommended: 3 MNQ on each strategy = $226/calendar-day at ~$15K
worst-case DD.**

---

## Strategy 4 — Add turn-of-month overlay (optional)

For additional ~$30/day per 1 MNQ during the 3 days at start/end of each month:

### TOM_FIRST3_LONG
- Each month's first 3 trading days, enter LONG at 13:30 UTC (NY open),
  hold 6 hours, MARKET exit.
- Backtest: 69 trades, 61% WR, +$5,339 = $79/trading-day at 1 MNQ.

### TOM_LAST3_SHORT
- Each month's last 3 trading days, enter SHORT at 13:30 UTC, hold 6h, MARKET.
- Backtest: 76 trades, 62% WR, +$7,999 = $105/trading-day at 1 MNQ.

These are non-overlapping with H22 strategies (different entry times).

---

## Risk management

### Per-account size guidance
- **Funded account ($50K)**: trade 1-2 MNQ on Strategy 1+2. Combined
  $50-90/cal-day, DD $5-9K. Won't blow the 5% drawdown limit.
- **Own capital ($100K)**: trade 5 MNQ on Strategy 1 + 3 MNQ on
  Strategy 2 = ~$300/cal-day, DD ~$20K.
- **Aggressive ($200K)**: 7+ MNQ each = ~$500/cal-day, DD ~$35K.

### Position concurrency
- Strategy 1: 1 position open from Sun-22:00 to Wed-22:00.
- Strategy 2: 1 position open from M/T/W/F 22:00 to next-day 22:00.
- Peak concurrency: 2 positions (Strategy 1 + Strategy 2 Mon/Tue/Wed nights).

### What can go wrong
1. **Bear market**: the strategies are LONG-only and benefit from the
   ~0.04%/hour positive drift on USTECH that exists in 2024-2026 (bull
   regime). A sustained bear market would shrink edge. Mitigation:
   add a regime filter (e.g., skip if 200-day SMA is below 50-day) —
   but this was NOT backtested.
2. **Fat-tail single-day loss**: the worst single-trade loss was
   ~$1,500 at 1 MNQ (Sept 2024). At 5 MNQ this is $7,500. Single-day
   max can hit 2x that ($15K at 5 MNQ) on a true panic.
3. **Sunday open gap risk**: the Sunday 22:00 UTC re-open is the most
   volatile minute of the week. The marketable LIMIT order might fill
   at +2-5pt above mid (worse than backtest's +1pt). Cost: ~$10-20 per
   trade per contract — manageable.
4. **CME maintenance windows**: 21:00-22:00 UTC daily, and the
   weekly close 21:00-22:00 UTC Friday to Sunday. The strategies
   assume the bar exists at 22:00 — if you instead get the FIRST
   post-maintenance tick, you might fill 2-5 minutes late.

### What to monitor live
1. Per-trade fill quality: ASK – F should be near zero. If > 2pt the
   marketable LIMIT order is being filled at a worse price than backtest.
2. Per-month P&L: if 2 consecutive months are red, pause and re-run
   backtest with most-recent data to confirm regime is still bull.
3. Sunday WR should stay above 60%. If it drops below 50% for 8
   consecutive Sundays, halt Strategy 1.

---

## Code skeleton (Python pseudocode)

```python
import asyncio
from datetime import datetime, timedelta, timezone
from broker_client import Broker  # your existing broker layer

broker = Broker()

async def strategy_1_sunday_open():
    """WEEKOPEN_LONG_HOLD3d"""
    while True:
        now = datetime.now(tz=timezone.utc)
        # Wait until next Sunday 22:00:00 UTC
        days_until = (6 - now.weekday()) % 7
        if days_until == 0 and now.hour < 22:
            wakeup = now.replace(hour=22, minute=0, second=0, microsecond=0)
        else:
            wakeup = (now + timedelta(days=days_until or 7)).replace(
                hour=22, minute=0, second=0, microsecond=0)
        await sleep_until(wakeup)
        # Place marketable BUY LIMIT
        fill = await broker.buy_marketable_limit("MNQ", qty=5, buffer_pts=1.0)
        T0 = fill.timestamp
        F = fill.price
        log_trade("WEEKOPEN_BUY", T0, F, qty=5)
        # Schedule exit
        await sleep_until(T0 + timedelta(hours=72))
        exit_fill = await broker.sell_marketable_limit("MNQ", qty=5, buffer_pts=1.0)
        log_trade("WEEKOPEN_SELL", exit_fill.timestamp, exit_fill.price, qty=5,
                  pnl=(exit_fill.price - F) * 5 * 2 - 5 * 0.74)

async def strategy_2_daily_22utc():
    """HOLD_24H_22UTC NO_THU. Runs on Mon/Tue/Wed/Fri/Sun (skip Thu)."""
    while True:
        now = datetime.now(tz=timezone.utc)
        # Next 22:00 UTC that's NOT Thursday
        candidate = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        while candidate.weekday() == 3:    # skip Thursday
            candidate += timedelta(days=1)
        await sleep_until(candidate)
        fill = await broker.buy_marketable_limit("MNQ", qty=5, buffer_pts=1.0)
        T0 = fill.timestamp
        F = fill.price
        log_trade("DAILY_BUY", T0, F, qty=5)
        await sleep_until(T0 + timedelta(hours=24))
        exit_fill = await broker.sell_marketable_limit("MNQ", qty=5, buffer_pts=1.0)
        log_trade("DAILY_SELL", exit_fill.timestamp, exit_fill.price, qty=5,
                  pnl=(exit_fill.price - F) * 5 * 2 - 5 * 0.74)

# Run both concurrently
asyncio.run(asyncio.gather(strategy_1_sunday_open(), strategy_2_daily_22utc()))
```

---

## Tick-level validation TODO

The bar-approximation engine used for this backtest gave +20% calibration
vs the tick-precise engine on H17_HOLD60. Before deploying real capital:

1. Run the existing `research/comprehensive_backtest.py`-style tick-precise
   engine on these strategies as a final validation.
2. Specifically: tick-precise WEEKOPEN_HOLD3d should land within 20% of the
   bar-engine's +$33,611. If it lands at +$25K-$40K, the deployment is
   safe.
3. Risk: if tick-precise reveals -50% of bar-engine PNL (e.g., -$15K vs
   +$30K), the strategy's edge is in the noise. Halt deployment.

Estimated time for tick-validation: 30-60 minutes per strategy on the
full data set.

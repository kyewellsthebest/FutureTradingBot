# HFT Edge Discovery — Final Research Report

**Date:** 2026-08-05 · **Branch:** `claude/hft-edge-discovery-h2drwe`
**Mandate:** discover new, independent high-frequency statistical edges in futures that
survive $1.40 commission + $3.00 slippage per round trip, with smooth-equity priorities.

---

## 0. Data reality check (read first)

**This repository contains no tick data.** The download scripts exist
(`research/download_nq_ticks.py`) but no Polygon API key is available in this
environment, and no tick files are on disk. The finest data available:

| Series | Resolution | Coverage |
|---|---|---|
| NQ continuous front month | 1-min OHLCV | 2018-02 → 2026-04 (2.83M bars) |
| ES continuous | 1-min | 2023-12 → 2026-02 |
| RTY continuous | 1-min | 2024-02 → 2026-02 |
| VIX | 1-min | multi-year |
| 25 futures (ZN, 6E, CL, …) | 5-min | ~2023-10 → 2026-07 |

Consequence: millisecond/second-scale edges (queue position, order-flow imbalance,
absorption, hidden liquidity, burst detection at the book level) are **untestable
here**. Those families were not skipped out of neglect — they cannot be honestly
evaluated on 1-minute bars. Everything from ~1-minute holding periods upward was
tested. Getting CME MBO/tick data (Databento, ~$100s) is the single highest-value
next step if the true HFT space is the goal.

**Data corruption found and fixed** (all results below are post-fix):
1. Garbage prints (e.g. NQ printing 611.25 on a Saturday, 2024-01-20) — removed via
   session-hygiene + rolling-median filters.
2. **Roll seams**: the continuous series switches contracts at midnight of the roll
   date with no back-adjustment. From 2022-12 onward each quarterly roll also spans a
   13–14 h data gap, so +133 to +495 phantom points landed inside single trading
   days. Fixed by panama back-adjustment + the simulator never holds across >2 h
   data gaps.
3. **Lookahead in overnight levels**: "overnight high/low" originally included the
   16:00–17:00 post-close session — future data at RTH signal time. This alone
   fabricated a fake edge with t-stat 10+ (see graveyard §3).

## 1. Methodology

- Signal on bar *t* close → entry at bar *t+1* open. Stops assumed to fill before
  targets when both touch in one bar. Costs: **$4.40/round trip** ($1.40 commission
  + $3.00 slippage), stress-tested to $8.40.
- **In-sample (IS): 2018–2023. Out-of-sample (OOS): 2024–2026.** Selection only on
  IS; OOS touched once per candidate.
- Every hypothesis tested long and short separately, with 4–6 exit philosophies
  (time exits 5–90 min, ATR stop/target, trailing, EOD flat, overnight holds).
- Survival bar: IS after-cost positive with meaningful t-stat → OOS confirmation →
  parameter-plateau check → cost stress → +1/+3-min entry-delay stress → ES
  cross-market confirmation → Monte Carlo drawdown profile.
- Controls run throughout: random-entry baselines (long and short) to separate
  "edge" from NQ's upward drift; falling-knife/acceptance controls to separate
  pattern from proximity effects. Two fake edges were caught this way.

Roughly **600 strategy variants across ~25 behavior families** were tested.

## 2. Survivors (2 validated + 1 watch-list)

### Sleeve A — Overnight-gap-down fade ("GAP")

**Behavior:** when the overnight session leaves the 9:29 price ≥ 0.25 × 14-day
average daily range *below* yesterday's RTH close, buy the 9:30 open; stop and
target 8 × 1-min-ATR away (rarely hit — effectively an intraday hold), flat 15:55.

**Why it should exist:** overnight down-moves are driven by thin Globex liquidity,
margin-forced liquidation, and risk-limited overnight market makers. Deep RTH
liquidity arriving at 9:30 reprices the overshoot. The opposite side (panicked
overnight sellers, gap-momentum shorts) accepts a bad price for immediacy. This is
a liquidity-provision premium — it persists because holding this trade through 2022
required absorbing a -$14K year, which is exactly the risk being compensated.

| Metric (1 NQ contract) | IS 2018-23 | OOS 2024-26 | Full 8.1y |
|---|---|---|---|
| Trades/week | 1.2 | 1.2 | 1.2 |
| Win rate | 55% | 55% | 55% |
| **$/week before costs** | **$168** | **$371** | **$170** |
| $/week after commission only ($1.40) | $166 | $369 | $168 |
| **$/week after commission+slippage** | **$156** | **$359** | **$165** |
| Avg net/trade | $99 | $229 | $132 |
| t-stat (net) | 1.7 | 1.4 | 2.2 |
| Years positive | 4/6 | 3/3 | 7/9 |
| Worst day / worst week | | | -$5,483 / -$5,117 |
| Avg losing week / max DD | | | -$1,186 / -$16,849 |

Robustness: positive across the whole threshold grid k ∈ {0.15…0.75} and all
3 exit styles OOS; survives $8.40 costs (avg/trade barely moves — it's a
1.2-trade/week strategy); survives +1-min entry delay ($81→$154 IS/OOS); ES
confirmation positive (k=0.15: +$71/trade, 4/4 years). Weakness: 2019 -$1.4K,
2022 -$14.4K — it bleeds in sustained bear regimes; per-trade variance is large
(this is a risk-premium harvest, not an arbitrage).

### Sleeve B — Weak-day close-imbalance short ("PWR")

**Behavior:** at 14:59, if the day-so-far return (9:30 open → 14:59) is ≤ -0.25 ×
14-day average daily range, sell short; exit 15:59 (before the cash close).

**Why it should exist:** on down days, leveraged/inverse ETFs must rebalance in the
same direction as the day's move into the close (documented, mechanical, calendar-
guaranteed flow), joined by MOC sell imbalances and margin-driven de-risking. The
counterparty is anyone required to provide immediacy at 15:00–16:00 on a red day.
It persists because the flow is *mandated* — leveraged ETF rebalancing cannot be
deferred.

| Metric (1 NQ contract) | IS 2018-23 | OOS 2024-26 | Full 8.1y |
|---|---|---|---|
| Trades/week | 1.4 | 1.5 | 1.4 |
| Win rate | 57% | 53% | 56% |
| **$/week before costs** | **$413** | **$133** | **$273** |
| $/week after commission only | $411 | $131 | $271 |
| **$/week after commission+slippage** | **$405** | **$125** | **$267** |
| Avg net/trade | $236 | $71 | $199 |
| t-stat (net) | 4.5 | 0.6 | 4.0 |
| Years positive | 5/6 | 2/3 | 7/9 |
| Worst day / worst week | | | -$4,824 / -$4,824 |
| Avg losing week / max DD | | | -$916 / -$17,825 |

Robustness: plateau across k ∈ {0.1…0.6} IS; insensitive to $8.40 costs and to
+3-min delay in-sample; ES confirmation +$39/trade, 4/4 years positive. Weakness:
the edge has **decayed** OOS (t=0.6; 2026 YTD negative). Both hours matter: moving
entry to 15:14 kills it OOS. Deploy small, monitor for continued decay, kill on a
-$8K rolling-6-month drawdown.

### Watch-list (NOT validated) — Opening-drive continuation ("DRIVE")

Direction of the 9:30–9:34 move (≥0.1 × daily range) continues to 10:00.
2024–2026: both sides independently positive (long +$281/trade net, short
+$314/trade net, each t≈2.2, 3/3 years, ~2.3 trades/week combined, ≈$955/week net
OOS). **But it made nothing in 2018–2023**, so it fails the "selected in-sample,
confirmed out-of-sample" rule — it is a *recent-regime* effect (plausibly 0DTE-era
opening flows). Trade it only as an explicitly regime-conditional sleeve with a
fast kill switch, or paper-trade it until it has its own live track record.

## 3. The graveyard (what was tested and killed — this is the main product)

| Family (variants) | Verdict |
|---|---|
| Single-bar shock fade / continuation, ±vol-split (60+) | Gross edge exists IS on the short side only; **collapses OOS** — pure 2018-22 bear-regime artifact. |
| Multi-minute cascade fade (16) | Same regime artifact; dead after costs. |
| Absorption bars (high vol, no range) (24) | No edge either direction. |
| Volume-climax-after-run fade (12) | Dead OOS. |
| Run-length continuation & reversion (32) | Nothing survives costs. |
| Compression → expansion breakout (24) | Losers after costs both directions. |
| VWAP-deviation fade (40) | Consistently **negative** after costs at every threshold/exit. |
| Big-bar gap fade (24) | Dead. |
| Opening-range breakout + ORB *failure* (28) | Sign-inconsistent IS vs OOS; ORB-failure-short was an overfit (IS + / OOS strongly −). |
| Overnight risk premium (buy 18:00→9:29 etc.) (10) | Positive gross but ≈ unconditional drift; t < 1; not an edge over baseline. |
| Lunch-hour fade, settlement-hour fade (8) | Dead OOS / sign flips. |
| First-30-min → last-hour momentum (IMOM) (6) | Noise. |
| Econ-release (8:30/10:00) spike continuation & fade (8) | IS 6/6 years for 8:30-continuation, but flat OOS → killed. |
| Prior-day H/L, overnight H/L sweep-reversals (32) | The spectacular version (t=10, 80% WR) was **100% lookahead artifact** (§0.3). After fix: dead OOS. |
| PDH/PDL acceptance continuation (6) | Dead OOS. |
| Round numbers (NQ 100-pt cross/fade) (8) | Nothing. |
| Settlement magnet 15:00 (4) | IS + / OOS − → killed. |
| ES→NQ 1-min lead-lag, NQ/ES 30-min spread reversion, joint→RTY lag (48) | All t < 1.1 and half-sample inconsistent — this space belongs to colocated HFT; at 1-min + $4.40 nothing is left. |
| Time-of-day drift atlas (46 anchors × 2 holds × 2 sides) | Best IS anchors flip OOS; nothing passes multiple-testing bar. |
| Consecutive-down-days, big-down-day next-day/overnight bounce, weekend hold (10) | IS/OOS sign flips everywhere; BIGDN's OOS was one lucky year (2025) → killed. |

Honest summary: **on 1-minute bars, after $4.40 and conservative fills, essentially
every "fast" microstructure family is dead.** What survives are slower structural
flows (overnight-liquidity repricing, close rebalancing) that happen to be
executable at specific minutes of the day.

## 4. Two-sleeve portfolio (GAP + PWR, 1 NQ contract each)

Daily P&L correlation GAP↔PWR: **-0.006** (they trade different hours, different
conditions — genuinely independent).

| Portfolio (net of all costs) | IS | OOS | Full |
|---|---|---|---|
| $/week | $475 | $404 | $455 |
| Weekly std | $1,735 | $2,949 | $2,146 |
| % positive weeks | 60% | 50% | 57% |
| Worst day | -$4,669 | -$6,914 | -$6,914 |
| Worst week | -$5,850 | -$7,652 | -$7,652 |
| Avg losing week | -$984 | -$1,875 | -$1,277 |
| Max drawdown | -$12,743 | -$17,371 | -$19,582 |
| Years positive | 5/6 | 3/3 | 8/9 (2019 -$8.8K) |

Monte Carlo (weekly bootstrap, 5k paths): median max-DD ≈ -$13-16K per sleeve;
plan capital for a -$30K left-tail on the pair at full NQ size. **On MNQ (÷10
size) the pair nets ≈ $33/week** after the same $4.40 costs (costs eat ~10× more
of the edge) with max-DD ≈ -$2K — the strategies survive micro-sizing, which many
do not.

## 5. What this research did *not* find, and what would change that

The user's priority list (smoothness, tiny drawdowns, high frequency) describes a
market-making/order-anticipation profile. That profile is **not extractable from
1-minute OHLCV** — it lives in queue dynamics, book imbalance, and sub-second
events. Concretely:
1. **Buy tick + MBP-10 data** (Databento CME bundle) for NQ/MNQ, 2019-present.
2. Re-run the batch-1 families at native resolution (they were all costed to death
   at 1-min but several had real gross structure).
3. The harness here (`harness.py`, numba-JIT, ~30 ms per 8-year backtest) ports
   directly — only the bar loader changes.

## 6. Files

| File | Purpose |
|---|---|
| `research/edge_discovery/harness.py` | Data loading, features, JIT trade simulator, stats, IS/OOS |
| `research/edge_discovery/clean.py` | Session hygiene, bad prints, roll back-adjustment |
| `research/edge_discovery/batch1_shock.py` | Shock/microstructure families (216 variants) |
| `research/edge_discovery/batch2_session.py` | Session-structure families (106) |
| `research/edge_discovery/batch3_levels.py` | Level/sweep/round-number families (50) |
| `research/edge_discovery/batch3b_crossmarket.py` | Cross-market lead-lag (48) |
| `research/edge_discovery/destroy.py` | Destruction battery for finalists |

Reproduce: `python3 research/edge_discovery/clean.py nq es rty`, then any batch
script, then `destroy.py`.

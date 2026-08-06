# HFT Edge Discovery — Final Research Report

**Date:** 2026-08-05 · **Branch:** `claude/hft-edge-discovery-h2drwe`
**Part I:** 1-minute bars, NQ 2018–2026 (§0–§6). **Part II:** true tick data,
NQ Sep 2023–Jun 2026 (§7–§10) — added after locating the per-contract tick
parquets on the `nq-ticks-raw` GitHub release.
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

---

# Part II — Tick-level research (270M trades, Sep 2023 – Jun 2026)

## 7. Tick data foundation

12 per-contract Polygon trade files (NQU3→NQM6) from the `nq-ticks-raw`
release: **270M trades / ~2.9 years**. Schema is trade-only (ns timestamp,
price, size) — **no quotes**, so aggressor side is inferred with the tick rule;
spread/queue-position/hidden-liquidity families remain untestable even here.
Processing: per-contract sort + dedupe (files are checkpoint-shuffled),
front-month roll windows, session hygiene, bad-print filter, panama seam
adjustment → 33.4M one-second bars with per-second OHLCV, trade count, signed
(tick-rule) volume, large-lot (≥10) counts and signed large-lot flow.

Splits: **IS = Sep 2023–Feb 2025, OOS = Mar 2025–Jun 2026.** Important honesty
note: both halves are bull-regime; there is no bear year in the tick sample.
Every long-side candidate was therefore benchmarked against random-entry and
direction-blind controls (which showed random ≈ –costs, so drift itself is
negligible at second-to-minute holds — but event-conditioned drift is not, see
BURST below).

## 8. Tick-level graveyard (~190 variants)

| Family | Verdict |
|---|---|
| OFI: tick-rule order-flow imbalance (60s/300s), momentum & reversal | Dead — no cell clears costs. |
| OFI divergence / absorption (flow vs price) | Dead both directions. |
| BIG25 / BIGFLOW: large-lot prints & cumulative institutional footprint, 10s–10m | **Systematically negative after costs** at 140–380 trades/wk — this flow is fully arbitraged; chasing it pays the spread for nothing. |
| BURST: trade-rate explosion + direction, 30s–10m | The apparent edge (+$23 IS/+$36 OOS long) is exposed by the direction-blind control: long-after-ANY-burst earns +$35 OOS vs +$5 IS. It is post-volatility upward drift of 2025–26, not signal. Killed. |
| SHK 10/30/60s return-shock fade & momentum, flow-split | Long-side dip-buying only (bull sample), shorts negative; stop/target variants strongly negative (t≈–8 to –11). Killed. |
| QUIET: liquidity-vacuum then first move | Nothing. |
| CASC: cascade-stall absorption reversal | IS +, OOS – → killed. |
| VBAR: volume-bar (event-time) 3-bar momentum & reversal | Dead; reversal variants strongly negative. |
| SWEEPT: tick-scale stop-run failure at rolling 30-min extremes | Flat zero — the "liquidity sweep" story does not pay at trade-data resolution either. |
| ECONS: 8:30 econ print, first-3-seconds continuation | IS t=1.6, OOS t=0.3 → killed. |

## 9. Tick-level survivor: OPENS — opening-auction drive continuation

**Rule:** at 9:30:05, if price is ≥2 pts above the 9:30:00 open → buy at
~9:30:06; ≥2 pts below → sell. Exit 10:00:00. No stop (max adverse excursions
are absorbed within the 30-min window; a 20-pt disaster stop changes little).

**Why it should exist:** the opening auction leaves one side short of
inventory; 0DTE option flows and delta-hedgers amplify the initial imbalance
for tens of minutes. The first 5 seconds reveal which side is chasing. The
counterparty is the opening-print fader providing immediacy against the
imbalance. This behavior existed weakly in 2018–2023 (Part I's DRIVE family,
same story at 1-min resolution) and has strengthened sharply in the 0DTE era.

| Metric (1 NQ, L+S combined, k=2, exit 10:00) | IS Sep23–Feb25 | OOS Mar25–Jun26 | Full 2.9y |
|---|---|---|---|
| Trades/week | 3.5 | 4.0 | 3.6 |
| **$/week before costs** | **$490** | **$1,525** | **$795** |
| $/week after commission only ($1.40) | $485 | $1,519 | $790 |
| **$/week after commission+slippage ($4.40)** | **$474** | **$1,509** | **$779** |
| Avg net per trade (long / short) | $178 / $58 | $344 / $337 | $230 blended |
| Positive quarters | | | 11 of 13 |
| Weekly std / % positive weeks | | | $3,734 / 61% |
| Worst day / worst week | | | –$9,094 / –$12,837 |
| Realized max DD / MC median / MC 5% | | | –$15.9K / –$24K / –$45K |

**Destruction-test results:** positive at every threshold k∈{1,2,3,5,8} on both
sides in both periods (20 of 20 cells at the 10:00 exit); exit-time plateau
(9:35 weaker, 10:00–10:30 best); survives $14.40/RT costs untouched.
**Latency stress (the critical one):** measuring the signal at +10s instead of
+5s roughly halves the edge; at +30s the in-sample long side is gone. The
tabled numbers assume order entry ~1 second after the 9:30:05 signal —
automated execution only. **Regime concentration:** ≈$50/trade in 2023–24 vs
≈$370/trade in 2025–26; the behavior is 3-years consistent but the magnitude is
recent — size accordingly and attach a kill switch (e.g. stop trading after a
rolling-26-week net < 0).

OPENS subsumes Part I's DRIVE watch-list entry (same behavior, sharper
measurement); DRIVE at 1-min is no longer a separate sleeve.

## 10. Final book (all validated sleeves, 1 contract each)

| Sleeve | Data proof | Trades/wk | $/wk gross | $/wk net ($4.40) | Character |
|---|---|---|---|---|---|
| GAP overnight-gap-down fade (long, 9:30→15:55) | 8.1y, 7/9 yrs+ | 1.2 | $170 | $165 | Liquidity-provision premium; bleeds in bears |
| PWR weak-day close-imbalance short (15:00→16:00) | 8.1y, 7/9 yrs+ | 1.4 | $273 | $267 | Mandated rebalancing flow; decaying, monitor |
| OPENS opening-drive continuation (9:30:06→10:00, L+S) | 2.9y ticks, 11/13 qtrs+ | 3.6 | $795 | $779 | Auction imbalance / 0DTE era; latency-sensitive, regime-concentrated |

GAP↔PWR daily correlation −0.006; OPENS trades a different window than both
(first half-hour) — the three sleeves are structurally independent (no shared
entry hour, no shared condition). Combined full-sample net ≈ **$1,200/week on
1-lot NQ** (≈$120/week on MNQ after the same absolute costs), with the honest
caveat that ~60% of that rate comes from OPENS's 2025–26 regime component.

**Ranked next steps:** (1) run OPENS live-paper for 4+ weeks to verify the
9:30:06 fill assumption against real latency; (2) quote data (MBP-10) would
unlock the spread/queue families that trade-only data cannot test; (3) extend
the tick history backward (Polygon has 2019+) to get a bear-regime read on
OPENS and the tick families.

---

# Part III — The 500+ trades/week mandate (HF scalping study)

**Mandate tested:** ≥500 trades/week on NQ, net ≥$500–1,000/week after $4.40/RT,
any win-rate/R:R structure. Verdict up front: **no such strategy exists in this
data under honest execution assumptions, and the result is provable, not a
search failure.**

## 11. The arithmetic that governs everything

At 500 trades/wk, costs are $2,200/wk; netting $750 needs **+1.2 ticks/trade
gross**. A market-order (taker) scalper also crosses the 1-tick spread twice →
true hurdle ≈ **2.2 ticks/trade**. A limit-order (maker) scalper pays ~$1.40 →
hurdle ≈ **0.3 ticks/trade** plus whatever adverse selection its fills carry.

## 12. Signal atlas (what edge exists at all at this frequency)

Conditional forward returns measured over 38 second-scale states (IS only,
Sep 2023–Feb 2025). The strongest high-frequency effect on NQ is **5–15 second
overshoot reversion**: after a ≥2-pt drop in 5s, E[+30s] = +0.26 ticks
(t = 15.6), symmetric on the up side (−0.23t), stronger PM (±0.42t, t ≈ 15),
scaling to ~+0.5t for the deepest displacements. **The best predictive signal
available at ≥1,500 events/week is 0.3–0.5 ticks** — real, hugely significant,
and 4–7× too small for the taker hurdle.

## 13. The maker route, bracketed by two fill models

~430 passive-scalp configurations (bid 1–3 ticks under the overshoot; targets
2–6t; stops 6–40t and no-stop; holds 60–600s; stall-conditioned and flow-
conditioned variants; both sides):

| Fill model | Meaning | Gross/trade across all configs |
|---|---|---|
| Strict trade-through (conservative) | fill only if price trades 1 tick past the limit | **−$8 to −$13** |
| Touch (optimistic, unattainable) | every touch of the limit fills | **−$2.20 to −$6.23** |

Real queue fills lie strictly between the bounds → **gross P&L is negative
under every attainable fill assumption, before any commission**. Even the 89%
win-rate no-stop variants lose gross: the ~11% of fills taken while a cascade
runs through the level carry more loss than all winners combined. This is
adverse selection — the exact toll that makes the 0.3–0.5 tick reversion edge
exist in the first place. It is the market maker's compensation, and
collecting it requires queue-position management and sub-second cancels,
which neither this dataset (no book/quote data) nor a $4.40-cost retail stack
can provide.

## 14. What would change the answer

1. **MBP-10 / order-book data + maker-rebate economics + sub-ms infrastructure**
   — the actual cost of entry to this frequency band. With queue-position
   modeling, fills at touch *without* trade-through become partially
   capturable, which is precisely the gap between −$2 and breakeven.
2. **Dropping the frequency constraint** — the validated book (Part I + II:
   GAP, PWR, OPENS) already nets ≈ $1,200/wk on 1-lot NQ at ~6 trades/wk.
   The user's *dollar* goal is achievable today; the *frequency* goal is what
   physics forbids at these costs.
3. A wider-tick, wider-spread instrument where displacement reversion measured
   in ticks is large relative to a fixed cost — worth a dedicated study only
   with book data in hand.

Scripts: `hf_atlas.py` (signal physics), `hf_sim.py` (bracketed fill models),
`hf_grid.py` (config sweep).

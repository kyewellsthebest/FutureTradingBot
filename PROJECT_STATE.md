# FUTURES TRADING BOT — COMPLETE PROJECT STATE
**As of 2026-08-02** · Account: Tradovate DEMO 46293485 · Capital ~$4,100 · Never traded live

---

## 1. WHAT THE BOT IS

A systematic futures bot running on Railway, polling 5-minute bars, placing **resting limit
entries with server-side OCO brackets** (stop + target) at the CME matching engine. It
manages multiple independent "sleeves" (mini-strategies) simultaneously.

**Currently live on demo:** `ratesActive6` — 6 fib-pullback sleeves, 3 on ZB (30-yr Treasury
bonds) + 3 on ZN (10-yr Treasury notes).

**Safety rails (all active):**
- Day trailing breaker: −$600 from the day's peak → flat + 2-hour pause, then re-arms
- Day floor: −$1,000 on the day → done until tomorrow
- Weekly trailing breaker: −$1,500 from the week's peak → flat until Monday
- Kill switch: −$2,000 cumulative from the $4,000 baseline
- Margin cap $3,500, max 6 concurrent filled positions
- Reject circuit breaker: 5 consecutive order rejections on a root halts that root for the day
- EOD flatten before 4:45pm ET; contract rolls handled (physical-delivery roll on the 25th)

**Repo:** `claude/hello-vc2ivo` (research) → `claude/transfer-trading-bot-GiNxs` (Railway deploys)

---

## 2. EVERYTHING WE HAVE TESTED

### Campaign history

| Campaign | Scale | Result |
|---|---|---|
| Early books (book6, book12, book17, calm12) | ~35k configs | **All invalidated** by the same-bar fill bug |
| MEGA1 (rebuilt, pessimistic) | ~460k configs, 13 markets × 3 timeframes | Only US rates survived |
| MEGA2 wide + deep | **2.9 billion** configs, 22 markets, 13 families | Rates only; everything else zero |
| MEGA3 | **4.1 billion** configs, 34 families, 14 markets | 21 new families → **zero** survivors |
| Organic behaviour discovery | 42 methods → 8 explorers → 21 findings → 21 adversarial verifiers | **19 of 21 killed** |
| 1–8 hour holds, market orders | 280 market×signal×horizon combos | **Fewer hits than chance** |
| Overnight vs intraday sessions | 6 markets | Mostly beta; inconsistent across markets |
| MNQ (best-economics market) | 54M configs | **1 of 215 survivors = below chance rate** |

**Total: ~11 billion configurations across 24 markets.**

### Markets tested
ES (S&P), NQ/MNQ (Nasdaq), RTY (Russell), YM (Dow), ZB/ZN/ZF/ZT (US rates), GC (gold),
SI (silver), HG (copper), CL (crude), NG (nat gas), HO/RB (refined), 6E/6B/6A/6J
(currencies), MBT/ETH (crypto), ZC/ZW/ZS (grains).

### Strategy families tested (34)
Fib pullback, fade/mean-reversion, MA pullback, breakout, failed breakout, opening range,
VWAP reversion, VWAP trend, volatility squeeze, time-of-day momentum, gap fade/continuation,
momentum continuation, trend exhaustion, RSI extremes, Bollinger touch + breakout, Keltner,
MACD cross, stochastic extremes, CCI z-score, engulfing, hammer/star, inside-bar breakout,
wide-bar fade, prior-day high/low fade + break, floor pivots, day-open reversion, overnight
bias (cont + rev), first-hour bias (cont + rev), close-location persistence, wick-ratio fade,
volume climax, multi-timeframe aligned pullback, scale-free formation alphabet (organic).

### Exit/management axes tested
Fixed ATR stops (0.5–3×), R:R ratios (0.5–3), trailing stops, break-even stop moves,
adaptive targets learned from rolling median MFE, time exits (6–96 bars), TTL on entries
(1–12 bars), partial/scaling ladders, dead-zone scratch exits, Kaplan-Meier hazard-derived
max-age exits.

### Context/filter axes tested
Session (Asia/EU/US), volatility regime, VIX regime, higher-timeframe trend, daily bias
(above/below day open), day of week, hour of day, minute of hour, position in day range —
up to **972 filter combinations over 128 context cells** per base config.

---

## 3. WHAT WE FOUND OUT — THE BUGS AND DISCOVERIES

### 3.1 Same-bar fill optimism (the first catastrophe)
The original engine allowed a trade to enter AND hit its target within the same 5-minute bar.
Within one bar, the order of events is unknowable. This awarded free wins on 79% of trades
and 85% of all winners. Live win rate came in at 50% against a simulated 73% (p≈0.001).
**Result:** all prior research invalidated, engine rebuilt with same-bar targets denied and
same-bar stops allowed. Discovered by the user's challenge: *"there's obviously a bug."*

### 3.2 Stop slippage was never charged
Every backtest filled stops at exactly the trigger price. A triggered stop becomes a market
order and does not fill there. **Worth $200–400/week** on the STEADY-7 book. Now fixed.

### 3.3 The touch-vs-trade-through fill convention (the second catastrophe)
Our engine assumes that if price touches your limit, you fill. Measured on ZB:

| | Fill on touch (our assumption) | Fill only on trade-through |
|---|---|---|
| ZB 12-bar drift from fill | **+0.386 ticks** | **−0.671 ticks** |
| ZN | **+0.609 ticks** | **−0.450 ticks** |

**The fill convention is worth 1.06 ticks — larger than every effect measured anywhere in
the entire dataset, including the edge itself.** Decomposed: bare-touch fills earn +2.40
ticks (ZB) / +2.58 (ZN); traded-through fills lose −0.67 / −0.45. Break-even needs **87%
fill on bare touches in ZB, 77% in ZN**, and that number is not knowable from OHLCV.

### 3.4 The "strategy" contributes almost nothing
Resting a buy limit 2 ticks below the close at **every single bar, no logic whatsoever**:

| | With the impulse/calm-vol signal | With no signal at all | Signal's contribution |
|---|---|---|---|
| ZB | +0.467 t | +0.386 t | **17%** |
| ZN | +0.627 t | +0.609 t | **3%** |

Three campaigns optimised the 3–17%. The limit order was doing the work.

### 3.5 Post-fill directional drift is zero
Independently confirmed. There is no prediction happening in any of our books. Whatever
edge exists is **liquidity provision** (getting paid the spread), not forecasting.

### 3.6 We searched the worst possible market
Cost ratio = average 5-min move ÷ round-turn cost:

| Contract | Tick $ | Cost/RT | 5-min move | Ratio |
|---|---|---|---|---|
| **MNQ (Nasdaq)** | $0.50 | $1.92 | $19.66 | **10.2x** |
| MGC (gold) | $1.00 | $2.42 | $16.53 | 6.8x |
| MES (S&P) | $1.25 | $2.67 | $9.84 | 3.7x |
| **ZB (what we traded)** | $31.25 | $35.53 | $32.34 | **0.9x** |

ZB's average 5-minute move does not even cover a round trip. Nasdaq was excluded on day one
and never searched until 2026-08-02.

### 3.7 We never held overnight — not once
EOD flatten is hardcoded in the engine and was inherited by every backtest. Maximum holding
period across all 11 billion configurations: 8 hours. The daily horizon — where the cost
ratio is 55–88x instead of 10x — has never been tested.

### 3.8 The frequency tax
At 200 trades/week you pay **$18,668/year** in costs on a $4,100 account. To net $1,000/week
you need **13.6 MNQ ticks of gross edge per trade**, which requires:

| Holding period | Must capture |
|---|---|
| 5 minutes | 34.6% of the average move — implausible |
| 1 hour | 9.5% — plausible |
| 4 hours | 4.5% — very plausible |

**Any strategy targeting $1,000/wk at 200 trades/wk must hold ≥30 minutes.** Scalping cannot
reach it.

### 3.9 Other confirmed findings
- Break-even stop moves are real but **redundant** with trailing stops (changed STEADY-7 by $2/wk)
- Adaptive MFE-learned targets **lose** to fixed targets
- Multi-bar formations carry **no** out-of-sample information beyond the last bar
- Price does **not** seek prior-day levels, day open, round numbers or ATR multiples (vs a
  distance-matched baseline)
- Compression predicts expansion but produces the **smallest** absolute moves
- 7 of 9 affordable non-rates markets are cost-dead purely on commission-per-tick
- Two-sided quoting from one margin slot destroys ~2/3 of any edge
- ZB is not temporally stable and ranks behind ZN despite better commission ratio

---

## 4. BOOKS BUILT (and their honest status)

| Book | Claimed | Status |
|---|---|---|
| calm12 | $2–4k/wk | **Dead** — same-bar bug |
| ratesCalm5 | ~$1.2k/wk | Superseded |
| **ratesActive6** | $1,879/wk, 267 tr/wk | **LIVE on demo** — depends on the fill assumption |
| balanced12 | $2,483/wk | Never deployed |
| Final-14 | $4,094/wk | Never deployed |
| **STEADY-7** | $1,580/wk, 88% pos weeks, maxDD −$1,037 | Built + engine-ready, **never deployed** — its edge is 97% unconditional and fill-dependent |
| MNQ survivor | $32/wk train | **Noise** (see §6) |

Every one of these rests on touch = fill.

---

## 5. WHY THE PAPER NUMBERS AREN'T REACHABLE — THE ACTUAL BLOCKERS

**Blocker 1 — The fill convention (dominant).**
Backtests assume a touch fills you. In reality a bare touch means price printed at your price
and left; you're at the back of the queue. 67% of our simulated fills are zero-penetration
touches, and those carry the entire apparent edge. Value of this assumption: 1.06 ticks, more
than any measured effect. **This single unknown determines whether the book makes $288/week
or loses catastrophically.**

**Blocker 2 — Demo cannot validate it.**
Tradovate's simulator very likely fills on touch — the same assumption. Our 13/13 perfect
fills on day one are consistent both with "our model is right" and "demo shares our error."

**Blocker 3 — Cost vs timescale.**
At 5-minute horizons, costs are 10–70% of the average move depending on market. We spent the
project at the timescale where friction dominates, in the market where it dominates most.

**Blocker 4 — Data ceiling.**
5-minute OHLCV only. No order book, no tick data, no quotes, no options chains. Queue position
— the thing that decides everything — is invisible. Only 2.3 years of history, which is thin
for daily-horizon testing.

**Blocker 5 — Capital.**
$4,100 supports 4–5 concurrent micro lots. Real diversification and full-size contracts need
$25k+. Overnight margin (~$1,200–2,600/contract) allows 1–2 positions.

**Blocker 6 — Structural competition.**
The bare-touch fills that earn +2.40 ticks are exactly what colocated market makers capture.
They pay $0.10–0.30/contract vs our $1.42–4.28 and sit microseconds from the matching engine.
We measured their edge and confirmed we cannot reach it.

---

## 6. THE MNQ SURVIVOR — FULL SPEC

**Config:** `{"fam":"brk","etype":"S","N":24,"buf":0.0,"dir":"up","ttl":3,"H":24,"sp":3.0,"rr":2.0,"trail":0.0,"f_sess":"asia"}`

| Field | Value |
|---|---|
| Market | MNQ (Micro Nasdaq-100), 5-min bars |
| Session | Asia only, 00:00–07:00 UTC (10am–5pm Sydney) |
| Entry | BUY STOP at the 24-bar high (prior 2 hours' high), no buffer |
| Order life | 3 bars (15 min), then cancel |
| Stop | 3.0 × ATR below entry |
| Target | 6.0 × ATR above entry (1:2 reward:risk) |
| Trailing | none |
| Max hold | 24 bars = 2 hours |
| Filters | none |
| Direction | LONG only |

| Metric | Train (2023-12 → 2025-05) | OOS (2025-06 → 2025-12) |
|---|---|---|
| $/week | $32.40 | $276.00 |
| Trades | 1,083 (8.6/wk) | 93 |
| EV/trade | $3.77 | — |
| Win rate | 49% | — |
| Profit factor | 1.157 | — |
| Positive weeks | 56% | 64% |

**Risk:** Sharpe 0.139 · maxDD −$1,063 · worst week −$553 · worst day −$365

**Why it is noise, not an edge:**
1. **1 survivor out of 215 exact replays** — chance alone produces ~11 at a 5% false-positive rate
2. **Only 25% of neighbouring parameters are profitable** (2 of 8) — a textbook parameter cliff
3. **Sharpe 0.139** — indistinguishable from zero
4. **Monte Carlo 5th-percentile year: −$878**
5. **Walk-forward folds [$156, $29, $2,060, $1,839]** — two dead periods, not consistency
6. Shuffled-order maxDD p95 = −$2,409, i.e. 59% of the account
7. OOS 8× train is instability, not improvement

**Verdict: do not trade this.**

---

## 7. WHAT HAS BEEN FIXED

- Same-bar target fills → denied (same-bar stops still allowed = pessimistic)
- Stop slippage → now charged
- Touch-conditioning → `touch_conditional()` measures P(touch) and outcome-given-fill separately
- Effective N → de-overlapped episodes, not bars
- Trailing stops → implemented in the live engine (broker-side modify, never loosens)
- Calm-volatility gate → implemented (1-month ATR EMA, survives restarts)
- **Stop-limit exits** → implemented 2026-08-02. Limit sits N ticks beyond the stop; caps
  slippage at ~0.3 ticks vs ~1.5. Gap rescue market-flattens if the stop-limit is skipped.
  Worth $61/wk at 200 trades and a **17% lower break-even bar** (3.59 → 2.98 ticks)
- Temporal splits with embargo, misalignment nulls, matched-random-entry controls
- Nasdaq re-admitted to the searchable universe

---

## 8. WHAT IS ACTUALLY LEFT

**1. Measure the live fill rate.** Free. One week. Log, for every resting limit: did price
reach it, and did we fill? Answers Blocker 1 and 2. **Highest value item in the project.**

**2. Buy Level 2 / depth-of-market data (~$10–30/month).** Currently on Level 1 (top of book
only). Level 2 shows the size resting at each price = fill probability, directly. Cheapest
meaningful upgrade available.

**3. Fetch 15–20 years of daily bars.** Free, one workflow run. Turns the only
economically-viable horizon (55–88x cost ratio) from untestable (585 samples) into testable
(4,000+ samples).

**Do NOT buy:** the Tradovate $1,499 Lifetime plan. You are on demo — it currently saves $0,
and whether it pays back depends on whether we end up high or low frequency. The $99/month
plan needs 165 full-size round turns per month to break even.

---

## 9. HONEST BOTTOM LINE

Five independent methods have now returned null on this dataset: 11 billion template configs,
organic behaviour discovery with adversarial verification, hour-scale market-order holds,
session/overnight splits, and the best-economics market. The one apparent edge that survived
everything turned out to be a fill-convention artifact whose value exceeds the effect itself.

**2.3 years of 5-minute OHLCV, at retail costs, does not contain an accessible directional
edge.** More configuration search will not change this.

What is NOT ruled out: the liquidity-provision business (if we genuinely get filled on bare
touches — measurable, unresolved), and the daily horizon (never tested with adequate data).
Those two are the entire remaining opportunity set, and both are cheap to resolve.

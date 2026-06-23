# Round 8 Strategy Search — Final Report

**Status: ZERO strategies meet hard requirements on either 14-day or 60-day window.**

## Setup

- 337 strategies tested across 4 categories (filter-gated MTF, ML-style feature
  gated CANON pullback, microstructure tweaks, NEW indicator strategies, session
  intersections)
- 14-day window: offset 8,300,000,000, 3,647,192 ticks, 14 day buckets
- 60-day window: offset 7,820,974,790, ~15,800,000 ticks, 53 day buckets
- Bot-faithful execution: $1.91/RT, queue overshoot=1 tick (limit), marketable
  +1tick, stop-entry +1tick, 200ms latency embargo, 10pt approach threshold,
  single-LIMIT lock, stop-MARKET slip, 10s cooldown, 600s max hold

## Hard Requirements (unchanged)

- 300+ trades/day average
- 45%+ win rate
- $1000+ net daily P&L
- Max DD <= $5000

## Result

| Window | FULL_PASS | Top $/day | Top WR with n>=200 |
|--------|----------:|----------:|-------------------:|
| 14-day | **0**     | E01_CANON_OVR_INV_236 — $60/day at 18.8 tr/d, 43.3% WR | Same |
| 60-day | **0**     | B04_CANON_bal_n300_t30 — $3/day at 5.3 tr/d, 41.3% WR | All losing |

## Top 14-day candidates — 60-day reality check

Round 8's top-10 by 14-day $/day, with their 60-day reality:

| Strategy | 14d $/day | 14d WR% | 60d $/day | 60d WR% | 60d DD |
|----------|----------:|--------:|----------:|--------:|-------:|
| E01_CANON_OVR_INV_236  | $60 | 43.3 | **$-24** | 35.8 | $2,214 |
| B05_CANON_winNYO       | $48 | 43.3 | **$-17** | 35.8 | $1,722 |
| B05_CANON_winOVR       | $41 | 41.7 | **$-23** | 35.9 | $2,286 |
| B02_CANON_velmin5      | $41 | 40.3 | **$-134**| 36.2 | $7,589 |
| E01_CANON_NYO_INV_236  | $37 | 42.0 | **$-15** | 36.2 | $1,695 |
| C04_MTF_early_imp4_b3  | $29 | 35.3 | **$-54** | 33.0 | $2,967 |
| E01_CANON_RTH_INV_236  | $26 | 39.6 | **$-85** | 35.9 | $5,439 |
| B05_CANON_winRTH       | $26 | 39.6 | **$-82** | 36.0 | $5,283 |
| B04_CANON_bal_n300_t30 | $14 | 42.9 | **+$3**  | 41.3 | $472   |
| A01_MTF_atr_a50-99     | $10 | 28.6 | **$-51** | 25.8 | $2,749 |

**Key observation**: Every strategy that looked promising on the 14-day test
fell ~3-5pt on WR over the 60-day window. The 43.3% WR for E01_CANON_OVR_INV_236
collapsed to 35.8% on 60-day — exactly the same WR ceiling that plagued all of
round 7's signals. The 14-day window appears to have contained a favorable
regime for inverse-pullback signals; this regime did NOT persist over 60 days.

## What worked structurally vs. what didn't

### Worked (in 14-day window, broke in 60-day)
- Session windowing (NYO/RTH/OVR) on CANON_INV_236 pullback — lifted 14d WR to
  41-43%, dropped to 35-36% on 60d.
- Tick-velocity filter (velmin=5) generated 63 tr/d at 40.3% WR (14d) but
  collapsed to 36.2% on 60d.
- ATR percentile gate (ap70+) added volume but no WR benefit.

### Did NOT generate trades
- Spread compression gates (A03/A04): 0 trades — quotes never compressed enough
  during this dataset.
- Tick-balance gate (n200_t20, n500_t50): 0 trades — the dataset doesn't have
  the directional persistence the gate requires.
- SRR-recent gate: 0 trades — sweep patterns rare.
- Triple-gate combinations (A09): 0 trades.

### Indicator strategies — uniformly weak
- Hurst-gated (D09): generated 4,700+ trades (most volume of any strategy) but
  WR was 17-22%, net -$200/day on 14d.
- Choppiness, DeMarker, CCI, Williams %R, Kaufman ER, Aroon, StochRSI,
  RangeFilter, PSAR, TRIX, HA3, ForceIndex, CMO, Entropy, Ulcer: all either
  too few trades or negative $/day.

## Why this happened — structural finding

Round 7 already showed: at execution friction levels (queue + latency +
$1.91/RT), high-volume signals collapse to ~30% WR and high-WR signals can't
reach 300/day.

Round 8 added selectivity gates. They worked **in-sample** (14d) but did not
generalize (60d). The 14-day window happened to be a regime where the inverse
pullback signal had a positive edge AT THE SESSION WINDOWS we tested. Over
the full 60-day window — which spans multiple regime shifts — that edge
disappears.

**Conclusion**: We have not found a strategy. We have found a 14-day fluke that
melts under longer testing. This is no different from rounds 1-7.

## Closest-to-passing candidate

**B04_CANON_bal_n300_t30**: 5.3 tr/d, 41.3% WR, +$3/day, DD $472, Sharpe 0.07
on the 60-day window. Tick-balance-aligned CANON pullback. The only strategy
that survived the 60-day test with positive P&L — but it's NOT a passer:
volume is 56x below the 300/day requirement.

## Round 9 proposal

The 1,500+ variants tested across rounds 1-8 have systematically ruled out:
- All standard signal types under bot-faithful execution
- All filter/gate combinations on the best base signals
- All standard indicators (RSI, CCI, Williams %R, DeMarker, etc.)
- All session windows and time-of-day intersections
- All ML-style 2-feature AND-gates on CANON pullback
- All microstructure tweaks (spread compression, off-touch, OCO ladder)

If the strategy IS in the space, it requires one or more of:

### R9-A. Execution model relaxation (test prop-firm pricing)
- $0.74 commission only (no exchange fees — some prop firms rebate)
- 50ms latency embargo (colocated execution)
- Re-test round 8 top candidates under this lighter friction. If E01_CANON_OVR
  becomes profitable on 60d under $0.74/RT, this is the answer: the venue
  matters more than the signal.

### R9-B. Walk-forward parameter optimization
- Split data into 4 contiguous 15-day blocks. For each block, find best CANON
  pullback params. Then apply the prior block's params to the next.
- If walk-forward beats fixed params on aggregate, we have a working
  regime-aware strategy even if no single param-set passes all windows.

### R9-C. Regime-switching meta-strategy
- Compute rolling Hurst / Choppiness / ATR every hour. Route to one of 3-5
  base strategies based on regime label.
- Tests whether the SAME signals work in different regimes when the GATE
  itself is a regime classifier (rather than a static parameter).

### R9-D. NQ (not MNQ) with 5-contract equivalent sizing
- NQ has 4x the point value ($20 vs $5) but same commission/exchange fees
- $1.91/RT becomes 0.4% of NQ's per-point edge instead of 1% of MNQ's
- Test top round 8 candidates with NQ economics — if profitable, the
  instrument matters.

### R9-E. Larger window (90d / 180d)
- 60-day window may itself be unrepresentative
- Test on 90 or 180 days if data permits

### R9-F. Different instrument family
- Try ES (E-mini S&P) — different microstructure, comparable liquidity
- Try CL (Crude) — higher volatility, may absorb fees better
- Same harness, different data file

### R9-G. STOP this line and switch to different OBJECTIVE
- Drop the 300/day requirement; pursue 50-100/day at 50%+ WR which is achievable
- B04_CANON_bal_n300_t30 came close to a $/tr profitable strategy — scale it.
- Hard constraint relaxation may be the path forward.

## Files

- /home/user/HFTBot/research/round8_search.py — full 337-variant harness
- /home/user/HFTBot/research/round8_supervisor.sh — auto-restart supervisor
- /home/user/HFTBot/research/round8_60d_retest.py — 60-day re-test harness
- /home/user/HFTBot/research/round8_extract_candidates.py — candidate extractor
- /home/user/HFTBot/research/round8_results.md — full 14-day search results
- /home/user/HFTBot/research/round8_summary.csv — 337-row 14-day summary
- /home/user/HFTBot/research/round8_60d_results.md — 60-day re-test results

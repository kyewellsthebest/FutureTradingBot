# Round 14 — TRACK A queue sensitivity + TRACK B/C deep learning

Generated: 2026-06-24T10:51:08.317773
Period: 53 calendar-day buckets from offset 7,820,974,790 (max-days=60)
Pass-1 tick stream: 15,896,413 lines processed in 10.8 min

## TL;DR — BREAKTHROUGH

**A PASSING STRATEGY WAS FOUND under bot-faithful PESSIMISTIC execution.**

The round-4 winner `INV_pp118_s3t9_imp3` (impulse_pts=3.0, impulse_bars=4,
pull_pct=0.118, stop=3pt, target=9pt, invert=True) — re-evaluated under all
three queue models — passes ALL FOUR hard requirements on a 53-day window:

| Metric | Required | Achieved (pessimistic queue) |
|---|---:|---:|
| Trades/day | >= 300 | **650.1** |
| Win rate | >= 45% | **47.9%** |
| Net $/day (MNQ, $1.91/RT) | >= $1,000 | **$2,243** |
| Max DD | <= $5,000 | **$396** |
| Sharpe (daily) | — | **1.45** |

Result is robust across queue models (realistic_mid: $2,140, presubmit: $2,173).
Total trades = 34,453 over 53 days. Net = ~$118,900. **This is the deployment
candidate.**

Why was it missed since round 4? It was in the round-4 PASS list (`INV_pp118_s3t9_imp3`
— rank 22 by $/day in round 4, $2,601/day) but subsequent rounds focused on
larger stops/targets and other avenues. Re-confirming it under the harder
round-7+ queue model is round 14's deliverable.

DL (TRACK B): The pure-numpy MLP shows mild predictive lift over baseline
(35% precision @ threshold 0.6 vs 28% base rate) but is not strong enough as
a standalone signal nor as a filter on CANON to meet hard requirements in
the 10-day OOS window (all DL strategies negative). Possibly useful in
ensemble; see Round 15.

AE (TRACK C): Anomaly detection shows weak LONG lift (1.19x) and slight
negative SHORT lift (0.94x). Not deployable alone.

## Hard requirements
- 300+ trades/day average
- 45%+ WR
- $1,000+ $/day
- maxDD <= $5,000

## TRACK A — Queue model sensitivity

Goal: determine how round-4 idealized winners perform under three different LIMIT-fill queue models. The bot-faithful executor since round 7 has assumed PESSIMISTIC queue position (LIMIT fills only on >=1-tick overshoot). If a more realistic model shows $1k+/day, that's a deployment candidate.

Models:
- **pessimistic**: requires bid/ask to OVERSHOOT entry by >=1 tick.
- **realistic_mid**: 100% on overshoot, 50% probability on touch.
- **presubmit**: 100% on overshoot; on touch — 80% if order has been ARMED >= 30s (anticipatory queue priority), else 30%.

### Per-strategy results

| Strategy | Queue model | Trades | Tr/day | WR% | $/day | DD | Sharpe | PASS? |
|---|---|---:|---:|---:|---:|---:|---:|:---:|
| CANON_INV_236_s10t20 | pessimistic | 13,128 | 247.7 | 40.3 | $189 | $2,538 | 0.25 | no |
| R4_INV_pp118_s5t20_imp3 | pessimistic | 19,962 | 376.6 | 30.8 | $813 | $1,101 | 0.66 | no |
| R4_INV_pp118_s4t16_imp3 | pessimistic | 24,311 | 458.7 | 32.7 | $1,122 | $660 | 0.83 | no |
| R4_INV_pp118_s3t12_imp3 | pessimistic | 30,341 | 572.5 | 37.2 | $1,669 | $393 | 1.13 | no |
| R4_INV_pp118_s3t9_imp3 | pessimistic | 34,453 | 650.1 | 47.9 | $2,243 | $396 | 1.45 | YES |
| R4_INV_pp236_s5t20_imp3 | pessimistic | 18,074 | 341.0 | 28.4 | $318 | $2,575 | 0.41 | no |
| CANON_INV_236_s10t20 | realistic_mid | 13,250 | 250.0 | 39.8 | $124 | $3,472 | 0.17 | no |
| R4_INV_pp118_s5t20_imp3 | realistic_mid | 20,220 | 381.5 | 30.4 | $748 | $1,222 | 0.63 | no |
| R4_INV_pp118_s4t16_imp3 | realistic_mid | 24,657 | 465.2 | 32.1 | $1,038 | $786 | 0.78 | no |
| R4_INV_pp118_s3t12_imp3 | realistic_mid | 30,704 | 579.3 | 36.6 | $1,576 | $491 | 1.10 | no |
| R4_INV_pp118_s3t9_imp3 | realistic_mid | 34,813 | 656.8 | 47.1 | $2,140 | $408 | 1.42 | YES |
| R4_INV_pp236_s5t20_imp3 | realistic_mid | 18,369 | 346.6 | 28.0 | $236 | $3,680 | 0.31 | no |
| CANON_INV_236_s10t20 | presubmit | 13,239 | 249.8 | 39.8 | $125 | $3,332 | 0.17 | no |
| R4_INV_pp118_s5t20_imp3 | presubmit | 20,176 | 380.7 | 30.5 | $767 | $1,132 | 0.63 | no |
| R4_INV_pp118_s4t16_imp3 | presubmit | 24,548 | 463.2 | 32.2 | $1,053 | $828 | 0.79 | no |
| R4_INV_pp118_s3t12_imp3 | presubmit | 30,640 | 578.1 | 36.8 | $1,607 | $435 | 1.11 | no |
| R4_INV_pp118_s3t9_imp3 | presubmit | 34,737 | 655.4 | 47.3 | $2,173 | $416 | 1.42 | YES |
| R4_INV_pp236_s5t20_imp3 | presubmit | 18,336 | 346.0 | 28.0 | $245 | $3,286 | 0.32 | no |

### Best per model

- **pessimistic**: best=A_PESS_R4_INV_pp118_s3t9_imp3 $2,243/day, 650.1 tr/day, WR=47.9%, DD=$396
- **realistic_mid**: best=A_REAL_R4_INV_pp118_s3t9_imp3 $2,140/day, 656.8 tr/day, WR=47.1%, DD=$408
- **presubmit**: best=A_PRES_R4_INV_pp118_s3t9_imp3 $2,173/day, 655.4 tr/day, WR=47.3%, DD=$416

**3 TRACK A passers found!**
- A_PESS_R4_INV_pp118_s3t9_imp3 (queue=pessimistic): $2,243/day 47.9%WR
- A_REAL_R4_INV_pp118_s3t9_imp3 (queue=realistic_mid): $2,140/day 47.1%WR
- A_PRES_R4_INV_pp118_s3t9_imp3 (queue=presubmit): $2,173/day 47.3%WR

### DEPLOYMENT CONFIGURATION

The single-MNQ deployment candidate from round 14 is:

```python
PullbackStrategy(
    name="DEPLOY_INV_pp118_s3t9_imp3",
    impulse_pts=3.0,        # 3-pt impulse over 4 bars triggers a setup
    impulse_bars=4,         # require 4-bar window
    pull_pct=0.118,         # entry sits 11.8% retracement off impulse end
    stop_pts=3,             # 3-pt stop
    target_pts=9,           # 9-pt target (3:1 reward:risk)
    invert=True,            # FADE the impulse (fire opposite-direction trade)
    cooldown_s=10,          # 10s cooldown post-exit
    # default: 600s max hold, no session filter, no atr filter
)
```

Bot-faithful execution (same as round 11): LIMIT fill mode (default), 200ms
latency embargo, 10pt approach threshold, multi-setup lock, 0.5pt stop slip
+ 10% gap risk, 10s cooldown, 600s max hold.

Expected statistics on 53-day window:
- 34,453 trades total (650/day)
- 47.9% win rate
- Net $118,924 (under $1.91/RT)
- Worst single day: included in DD = $396 max
- Sharpe ratio 1.45 (daily)

## TRACK B — Deep learning (pure-numpy MLP)

PyTorch was unavailable (proxy + disk), so the model is a pure-numpy MLP with Adam optimizer: **50-D input → 96-ReLU → 64-ReLU → 2-sigmoid (LONG, SHORT)**.

### Feature engineering (50-D)

- Price action (15): last 5 1-min returns, last 5 HL ranges, bar position, SMA divergence, ATR(5)/ATR(20)/ratio.
- Microstructure (15): spread, 1-min avg spread + trend, tick velocity 10/30/60s, signed-tick balance, persistence, bid-hits/ask-lifts ratio, 60-bar percentile, VWAP gap, tick jumpiness.
- Volatility regime (10): realized vol 5/15/60min + ratio, Hurst proxy, range expansion percentile, vol z-score, body/range ratio, up-bar fraction, vol-of-vol.
- Time (10): hour sin/cos, minute sin/cos, DoW, time since open, time to close, time since big move, RTH indicator.

### Training protocol

- Train days 0..39, validate 40..49, test 50..59 (out-of-sample)
- Adam optimizer, lr=1e-3, batch size 256, dropout 0.2
- Up to 30 epochs with early-stopping on val loss
- Class weighting to handle imbalance
- Sample count: train=24517, val=6157, test=1561

### MLP out-of-sample results

- Test BCE loss: **0.7632**
- Test accuracy LONG: 43.88%
- Test accuracy SHORT: 41.19%
- Precision @ p>=0.6 LONG: 35.48% (coverage 27.80%)
- Precision @ p>=0.6 SHORT: 37.47% (coverage 48.05%)

### TRACK B — Deployment backtest (days 50+ OOS, ~10 days)

Bot-faithful execution with 1 MNQ, $1.91/RT, 200ms latency, 10s cooldown, 5pt stop slip rules.

| Strategy | Trades | Tr/day | WR% | $/day | DD | Sharpe | PASS? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| B_DLFLT_canon_ft60 | 191 | 19.1 | 36.6 | $-34 | $517 | -0.34 | no |
| B_DLFLT_canon_ft55 | 195 | 19.5 | 35.9 | $-45 | $578 | -0.57 | no |
| B_DLFLT_canon_ft50 | 226 | 22.6 | 35.4 | $-53 | $568 | -0.59 | no |
| B_DL_th65_s5t15 | 190 | 19.0 | 23.2 | $-67 | $811 | -0.72 | no |
| B_DL_th65_s4t12 | 203 | 20.3 | 23.2 | $-69 | $747 | -0.90 | no |
| B_DL_th65_s3t9 | 216 | 21.6 | 21.3 | $-80 | $850 | -1.61 | no |
| B_DL_th60_s5t15 | 284 | 28.4 | 22.9 | $-102 | $1,251 | -1.41 | no |
| B_DL_th60_s4t12 | 325 | 32.5 | 21.8 | $-125 | $1,359 | -3.29 | no |
| B_DL_th60_s3t9 | 348 | 34.8 | 20.1 | $-139 | $1,446 | -3.26 | no |
| B_DL_th55_s5t15 | 412 | 41.2 | 21.6 | $-173 | $1,832 | -1.11 | no |
| B_DL_th55_s4t12 | 452 | 45.2 | 20.4 | $-196 | $1,960 | -3.23 | no |
| B_DL_th55_s3t9 | 497 | 49.7 | 17.7 | $-229 | $2,288 | -2.50 | no |

## TRACK C — Autoencoder anomaly detection

Trained a 50→32→16→32→50 autoencoder on training features. High reconstruction error indicates outlier market state. Question: do outliers predict next-60s 5pt moves?

- Reconstruction-error p90 threshold (test): 2.5361
- Above-threshold LONG-profitable rate: **36.94%** vs baseline **30.98%**
- Above-threshold SHORT-profitable rate: **30.57%** vs baseline **32.55%**

Anomaly lift: LONG 1.19x, SHORT 0.94x.
Anomalies do not show strong predictive lift on their own.

## Section X — Round 15 directions

We have a passing strategy. Priority for round 15 is **out-of-sample validation
and live-paper testing**, NOT yet another variant sweep.

### Validation priorities (do FIRST)
1. **Walk-forward validation on a non-overlapping 60-day window** —
   pick a different offset and re-test `INV_pp118_s3t9_imp3`. The
   round-4 selection was on this exact window; we need ground-truth
   that it generalizes.
2. **Day-by-day P&L decomposition** — confirm the 53-day result isn't
   driven by 2-3 outlier days. Sharpe 1.45 + max DD $396 suggests
   it is NOT, but verify with a daily series chart and concentration
   of returns metric (top-5-days % of total).
3. **Robustness to seed shifts** — vary the impulse threshold by
   ±0.5pt, stop by ±0.5pt, target by ±2pt, pull_pct by ±0.05.
   If the strategy survives small perturbations, it is robust.
4. **Sim-replay against a higher-fidelity executor** — verify that
   the LIMIT-fill assumption (pessimistic queue) holds in production
   reconciliation. The MarketablePullback variant ($1.91/RT, marketable
   fills) gives a worst-case bound.
5. **Live demo account testing** — paper trade for 5-10 days to detect
   slippage that the sim doesn't model (broker reject, hot-key latency,
   exchange throttling).

### Enhancement directions (after validation succeeds)
6. **Install PyTorch on a machine with more disk** — train a true
   LSTM/Transformer/TCN. The numpy MLP only sees the engineered
   feature vector at single timesteps; sequence models can find
   richer structure.
7. **MLP as confidence-gate on the deploy strategy** — INV_pp118_s3t9
   fires 650 times/day. If MLP can filter for the WORST 100 of those
   without sacrificing more than 50 of the winners, $/day could
   increase materially.
8. **Sample more densely** — currently 30s sample period. Try 5s or 1s
   to get 6-30x more training data for the next MLP training run.
9. **Multi-horizon labels** — predict 30s, 60s, 120s, 300s forward
   returns simultaneously (multi-task).
10. **Reinforcement learning on exit policy** — Bellman-optimal stop
    placement; reward = pt-PnL after fee.

### If validation FAILS (round 14 winner doesn't generalize)
- Re-do the round-4 sweep over a fresh 60-day window (different offset)
  with the bot-faithful executor. Round 4 used a touch-based executor;
  the bot-faithful PESSIMISTIC executor in round 14 is what we deploy
  against, so re-confirming the rank ordering is essential.
- Pursue MLP/LSTM/Transformer with a real GPU + PyTorch.
- Try NQ ($20/pt) instead of MNQ ($2/pt) — same strategy, 10x P&L
  per trade, only need 100 wins/day instead of 650.

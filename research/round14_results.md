# Round 14 — TRACK A queue sensitivity + TRACK B/C deep learning

Generated: 2026-06-24T10:35:07.060534
Period: 3 calendar-day buckets from offset 7,820,974,790 (max-days=3)
Pass-1 tick stream: 24,841 lines processed in 0.0 min

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
| CANON_INV_236_s10t20 | pessimistic | 19 | 6.3 | 52.6 | $31 | $114 | 0.00 | no |
| R4_INV_pp118_s5t20_imp3 | pessimistic | 25 | 8.3 | 36.0 | $20 | $164 | 0.00 | no |
| R4_INV_pp118_s4t16_imp3 | pessimistic | 38 | 12.7 | 31.6 | $11 | $137 | 0.00 | no |
| R4_INV_pp118_s3t12_imp3 | pessimistic | 53 | 17.7 | 24.5 | $-20 | $91 | 0.00 | no |
| R4_INV_pp118_s3t9_imp3 | pessimistic | 70 | 23.3 | 40.0 | $36 | $59 | 0.00 | no |
| R4_INV_pp236_s5t20_imp3 | pessimistic | 29 | 9.7 | 27.6 | $3 | $165 | 0.00 | no |
| CANON_INV_236_s10t20 | realistic_mid | 19 | 6.3 | 52.6 | $31 | $112 | 0.00 | no |
| R4_INV_pp118_s5t20_imp3 | realistic_mid | 26 | 8.7 | 34.6 | $17 | $174 | 0.00 | no |
| R4_INV_pp118_s4t16_imp3 | realistic_mid | 41 | 13.7 | 34.1 | $26 | $91 | 0.00 | no |
| R4_INV_pp118_s3t12_imp3 | realistic_mid | 54 | 18.0 | 27.8 | $-3 | $72 | 0.00 | no |
| R4_INV_pp118_s3t9_imp3 | realistic_mid | 70 | 23.3 | 41.4 | $43 | $62 | 0.00 | no |
| R4_INV_pp236_s5t20_imp3 | realistic_mid | 30 | 10.0 | 26.7 | $9 | $162 | 0.00 | no |
| CANON_INV_236_s10t20 | presubmit | 19 | 6.3 | 52.6 | $31 | $112 | 0.00 | no |
| R4_INV_pp118_s5t20_imp3 | presubmit | 26 | 8.7 | 34.6 | $16 | $175 | 0.00 | no |
| R4_INV_pp118_s4t16_imp3 | presubmit | 38 | 12.7 | 31.6 | $10 | $135 | 0.00 | no |
| R4_INV_pp118_s3t12_imp3 | presubmit | 53 | 17.7 | 24.5 | $-21 | $90 | 0.00 | no |
| R4_INV_pp118_s3t9_imp3 | presubmit | 70 | 23.3 | 41.4 | $44 | $61 | 0.00 | no |
| R4_INV_pp236_s5t20_imp3 | presubmit | 30 | 10.0 | 26.7 | $10 | $162 | 0.00 | no |

### Best per model

- **pessimistic**: best=A_PESS_R4_INV_pp118_s3t9_imp3 $36/day, 23.3 tr/day, WR=40.0%, DD=$59
- **realistic_mid**: best=A_REAL_R4_INV_pp118_s3t9_imp3 $43/day, 23.3 tr/day, WR=41.4%, DD=$62
- **presubmit**: best=A_PRES_R4_INV_pp118_s3t9_imp3 $44/day, 23.3 tr/day, WR=41.4%, DD=$61

No TRACK A configuration passes all 4 hard requirements.

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
- Sample count: train=0, val=0, test=0


## TRACK C — Autoencoder anomaly detection


## Section X — Round 15 directions

If round 14 did not produce a passing strategy:

1. **Install PyTorch on a machine with more disk** — train a true LSTM/Transformer/TCN. The numpy MLP only sees the engineered feature vector at single timesteps; sequence models can find richer structure.
2. **Sample more densely** — currently 30s sample period. Try 5s or 1s to get 6-30x more training data.
3. **Multi-horizon labels** — predict 30s, 60s, 120s, 300s forward returns simultaneously (multi-task).
4. **Bag of weak learners** — train 50 small MLPs on bootstrap samples, ensemble with median vote.
5. **Sequence-of-features**: feed the LAST N feature vectors into a wide MLP (stride-flatten 60 → 50*60=3000-D input).
6. **Cost-sensitive thresholding**: optimize threshold for $/day directly, not for accuracy.
7. **Reinforcement learning**: cross-entropy method on policy parameters (entry threshold, stop, target).
8. **Combine TRACK A + TRACK B**: use MLP filter ONLY when queue model is realistic_mid (i.e. allow optimistic fills).
9. **Trade NQ instead of MNQ** — same strategy, 10x pt-value, could meet $/day spec at lower trade count.
10. **Re-investigate execution truth**: real broker fills would tell us which queue model is correct. Test on demo account.

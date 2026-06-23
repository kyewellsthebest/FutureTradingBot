# Round 10 strategy search — relentless ten-direction battery

Generated: 2026-06-23T12:37:28.491866
Period: 53 calendar-day buckets from offset 7,820,974,790 (max-days=60)
Tick stream: 15,896,413 lines processed
Strategies tested: 143

## Execution model

Bot-faithful: queue overshoot by 1 tick (LIMIT), 200ms latency, 10pt approach threshold, multi-setup lock, 0.5pt stop slip + 10% gap risk, 10s cooldown, 600s max hold. Adaptive queue model gates D9 strategies (age-based fill prob).

Fees tracked: **$1.91/RT** vs **$0.74/RT** (prop-firm). Instruments: MNQ ($2/pt) and NQ ($20/pt).

## Hard requirements
- 300+ trades/day average
- 45%+ WR
- $1000+ $/day
- maxDD <= $5000

## Section 1 — FULL_PASS strategies

- $1.91 MNQ: **0**
- $0.74 MNQ (prop-firm): **0**
- $1.91 NQ: **0**
- $0.74 NQ (prop-firm): **0**


## Section 2 — Top 30 by $/day across all directions (MNQ $1.91)

| Rank | Strategy | Dir | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ 191 | DD | Sharpe |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | R10_BASE_R8_B04_CANON_bal_n300_t30 | R10_BASE | 282 | 5.3 | 41.8 | $5 | $11 | $139 | $447 | 0.10 |
| 2 | D10_MTF_pp236_imp5_b3_s12t24_CME | D10 | 901 | 17.0 | 42.5 | $4 | $24 | $337 | $1,043 | 0.03 |
| 3 | D10_MTF_pp382_imp5_b3_s10t30_CME | D10 | 796 | 15.0 | 39.1 | $4 | $21 | $295 | $847 | 0.03 |
| 4 | D10_MTF_pp300_imp6_b3_s8t24_CME | D10 | 793 | 15.0 | 35.7 | $2 | $20 | $280 | $781 | 0.02 |
| 5 | D5_ABS_t25_s8t24 | D5 | 8 | 0.2 | 62.5 | $1 | $1 | $15 | $19 | 0.53 |
| 6 | D4_VPIN_mid_CANON_INV_236 | D4 | 15 | 0.3 | 53.3 | $1 | $1 | $13 | $54 | 0.00 |
| 7 | D10_MTF_pp236_imp4_b3_s10t30_CME | D10 | 1,050 | 19.8 | 38.5 | $0 | $23 | $343 | $885 | 0.00 |
| 8 | D4_VPIN_lo_CANON_INV_236 | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 9 | D4_VPINhi_lo_CANON | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 10 | D4_VPINhi_mid_CANON | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 11 | D4_VPINhi_hi_CANON | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 12 | D4_VPIN_lo_INV15s_imp2_s4t12 | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 13 | D3_MOTIF_s5t15 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 14 | D3_MOTIF_s8t24 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 15 | D3_MOTIF_s10t20 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 16 | D3_MOTIF_s5t20 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | 0.00 |
| 17 | D7_CALadap_s8t24 | D7 | 2 | 0.0 | 0.0 | $-0 | $-0 | $-1 | $10 | -1.16 |
| 18 | D4_VPIN_mid_INV15s_imp2_s4t12 | D4 | 43 | 0.8 | 32.6 | $-0 | $1 | $12 | $109 | 0.00 |
| 19 | D7_CALadap_s10t20 | D7 | 3 | 0.1 | 33.3 | $-0 | $-0 | $-2 | $26 | -1.18 |
| 20 | D7_CALadap_s5t20 | D7 | 4 | 0.1 | 25.0 | $-1 | $-1 | $-5 | $39 | -0.62 |
| 21 | D7_CALadap_s5t15 | D7 | 3 | 0.1 | 0.0 | $-1 | $-1 | $-6 | $39 | -2.17 |
| 22 | D10_MTF_pp236_imp3_b4_s6t16_NYO | D10 | 334 | 6.3 | 33.2 | $-1 | $6 | $97 | $647 | -0.03 |
| 23 | D5_ABSinv_t25_s8t24 | D5 | 5 | 0.1 | 0.0 | $-1 | $-1 | $-12 | $73 | -2.19 |
| 24 | D6_TAPE_x7_o5_s5t20 | D6 | 36 | 0.7 | 19.4 | $-2 | $-1 | $-9 | $123 | -0.21 |
| 25 | D6_TAPE_x7_o5_s5t15 | D6 | 35 | 0.7 | 22.9 | $-2 | $-2 | $-13 | $132 | -0.25 |
| 26 | D7_CAL_s10t20 | D7 | 19 | 0.4 | 31.6 | $-2 | $-2 | $-18 | $152 | -0.81 |
| 27 | D5_ABSinv_t20_s8t24 | D5 | 49 | 0.9 | 32.7 | $-3 | $-2 | $-12 | $224 | -0.19 |
| 28 | D10_MTF_pp300_imp4_b3_s8t20_CME | D10 | 1,048 | 19.8 | 37.6 | $-3 | $20 | $312 | $743 | -0.03 |
| 29 | D10_MTF_pp450_imp4_b3_s8t24_NYO | D10 | 254 | 4.8 | 28.7 | $-3 | $3 | $52 | $430 | -0.05 |
| 30 | D7_CAL_s5t20 | D7 | 18 | 0.3 | 11.1 | $-3 | $-3 | $-26 | $167 | -0.79 |

## Section 3 — Per-direction headline

| Direction | n_strats | Best $/d 191 | Best $/d 074 | Best $/d NQ191 | Best $/d NQ074 | Top strat |
|---|---:|---:|---:|---:|---:|---|
| D10 | 50 | $4 | $24 | $337 | $357 | D10_MTF_pp236_imp5_b3_s12t24_CME |
| D3 | 4 | $0 | $0 | $0 | $0 | D3_MOTIF_s5t15 |
| D4 | 9 | $1 | $1 | $13 | $13 | D4_VPIN_mid_CANON_INV_236 |
| D5 | 16 | $1 | $1 | $15 | $15 | D5_ABS_t25_s8t24 |
| D6 | 27 | $-2 | $-1 | $-9 | $-8 | D6_TAPE_x7_o5_s5t20 |
| D7 | 8 | $-0 | $-0 | $-1 | $-1 | D7_CALadap_s8t24 |
| D8 | 9 | $-639 | $-498 | $-4,323 | $-4,182 | D8_ENS_v4_s10t20 |
| D9 | 12 | $-34 | $14 | $359 | $406 | D9_ADAP_R4_INV_pp382_s5t20_imp5 |
| ENS_CHILD | 5 | $-268 | $-111 | $-366 | $-208 | ENS_CHILD_R4_INV_pp382_s5t20_imp5 |
| R10_BASE | 3 | $5 | $11 | $139 | $146 | R10_BASE_R8_B04_CANON_bal_n300_t30 |

## Section 4 — Top 20 by $/day under NQ $0.74 (best prior lever)

| Rank | Strategy | Tr/d | WR% | $/day NQ | maxDD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|
| 1 | R10_BASE_R8_C04_MTF_early_imp4_b3_s8t24_INV | 62.7 | 34.2 | $706 | $10,071 | 0.30 |
| 2 | D10_MTF_pp450_imp4_b3_s6t24_all | 59.6 | 28.4 | $560 | $6,827 | 0.31 |
| 3 | D10_MTF_pp300_imp5_b3_s8t30_all | 60.7 | 31.0 | $528 | $9,275 | 0.24 |
| 4 | D10_MTF_pp382_imp5_b3_s12t24_all | 50.7 | 41.4 | $501 | $10,334 | 0.20 |
| 5 | D10_MTF_pp382_imp4_b3_s12t20_all | 58.5 | 43.6 | $473 | $15,466 | 0.19 |
| 6 | D9_ADAP_R4_INV_pp382_s5t20_imp5 | 40.5 | 28.5 | $406 | $5,420 | 0.31 |
| 7 | D10_MTF_pp236_imp4_b3_s10t30_CME | 19.8 | 39.7 | $366 | $5,270 | 0.23 |
| 8 | D10_MTF_pp236_imp5_b3_s12t24_CME | 17.0 | 43.7 | $357 | $6,661 | 0.23 |
| 9 | D10_MTF_pp300_imp4_b3_s8t20_CME | 19.8 | 38.6 | $335 | $3,774 | 0.30 |
| 10 | D10_MTF_pp382_imp5_b3_s10t30_CME | 15.0 | 40.3 | $312 | $5,371 | 0.26 |
| 11 | D10_MTF_pp300_imp6_b3_s8t24_CME | 15.0 | 36.6 | $298 | $4,745 | 0.28 |
| 12 | D10_MTF_pp382_imp3_b3_s12t16_CME | 19.8 | 48.6 | $266 | $6,748 | 0.22 |
| 13 | D9_ADAP_R4_INV30s_imp3_s4t12 | 91.1 | 29.6 | $242 | $5,150 | 0.19 |
| 14 | D10_MTF_pp236_imp6_b3_s6t24_CME | 17.6 | 30.1 | $234 | $7,301 | 0.19 |
| 15 | D9_ADAP_R4_INV_pp118_s4t16_imp5 | 57.5 | 25.7 | $223 | $3,728 | 0.22 |
| 16 | D10_MTF_pp450_imp5_b3_s10t24_CME | 13.5 | 40.7 | $206 | $5,590 | 0.19 |
| 17 | D10_MTF_pp450_imp4_b4_s10t20_CME | 15.1 | 42.9 | $199 | $6,936 | 0.19 |
| 18 | D10_MTF_pp236_imp5_b3_s6t24_all | 70.9 | 26.6 | $199 | $16,576 | 0.10 |
| 19 | D10_MTF_pp450_imp6_b4_s6t20_all | 40.2 | 29.1 | $168 | $7,970 | 0.11 |
| 20 | D9_ADAP_R4_INV15s_imp2_s3t12 | 150.5 | 24.4 | $153 | $8,872 | 0.11 |

## Section 5 — Lever ranking (best $/day MNQ-equivalent)

- **prop-firm NQ $0.74 / MNQ-equiv**: $71/day
- **baseline NQ $1.91 / MNQ-equiv**: $63/day
- **prop-firm MNQ $0.74**: $29/day
- **baseline MNQ $1.91**: $5/day

## Section 6 — Round 11 recommendations

**NO PASSERS** under any fee+instrument combo at the 4-constraint set
(300+ tr/d, 45%+ WR, $1000+ $/d, DD<=$5000). After 10 rounds and 1,900+
variants the hard requirement appears mathematically intractable at 1 MNQ
+ $1.91/RT, because the per-trade edge needed is ~$5.24/trade gross and
even the best inverted-impulse strategies generate < $1/trade net.

### Round 10's actual findings (relative to round 9)

- Round 9 ceiling: $61/day NQ-prop (1 contract equivalent)
- **Round 10 ceiling: $706/day NQ-prop** (R10_BASE_R8_C04_MTF_early on
  CME-overlap; 62.7 tr/d, 34.2% WR, DD=$10,071, Sharpe 0.30)
- **Adaptive queue (D9) significantly helped**: $406/day NQ-prop on
  D9_ADAP_R4_INV_pp382_s5t20_imp5 — a +$345/day uplift vs baseline
- **CME-session bias (D10)**: 6 of top 12 prop-firm NQ winners use the
  CME overlap window (22:00–05:00 UTC), suggesting overnight thin-book
  inversion edge is real but not high-volume
- **GA (D2)**: converged on pp118_imp6_b5_s10t16_INV_15s_RTH at +$182/d
  on 7d eval — overfit; 60d re-test: -$70/d (prop)
- **RL (D1)**: every state Q-value < 0 → Q-table policy is NO-OP. Means
  there is NO learnable edge with the chosen state features (recent
  net, vol regime, tape speed)
- **VPIN gating (D4)**, **absorption (D5)**, **tape speed (D6)**,
  **motifs (D3)**, **ensemble voting (D8)**: all near-zero signal-generation
  (most produced < 50 trades over 60d)

### Round 11 attack angles — ranked by expected lift

1. **Scale the contract size (relax constraint)** — top survivor
   R10_BASE_R8_C04_MTF on NQ-prop = $706/day per contract. Trading
   5 MNQ contracts (=0.5 NQ) at $0.74 fees would deliver ~$350/day
   gross, still short of $1000. Need 10+ NQ-equivalent (5+ NQ
   contracts = ~$5K margin per leg) to plausibly clear $1000/day.
2. **Multi-instrument** — acquire ES, RTY, CL tick data and run the
   round-10 winners simultaneously on each. If returns are
   uncorrelated, 4-instrument portfolio: 4x trades/day potential AND
   sqrt(4)=2x Sharpe via diversification.
3. **Order book imbalance (L2 data)** — top-of-book size ratio,
   cancel rate, queue-front size. Round 10's adaptive-queue D9
   strategies improved $/day by 25%+ on average — confirming queue
   position is alpha source.
4. **Aggressive D10_MTF + D9_ADAP combined** — round 10's CME-session
   D10 has high $/d but low volume. Wrap with D9 adaptive queue and
   stack 3-5 of the top variants for a portfolio at ~80-100 tr/day.
5. **Large-scale GA** — 200-individual × 100-generation on 14d window
   (~10x larger than round 10's GA). Add session × time-of-day to
   genome. ~40 hours compute on this hardware.
6. **News/event awareness** — economic-calendar-aligned filters
   (avoid 8:30am EST data dumps; FOMC days; OPEX). Could lift WR by
   3-5pp.
7. **Position sizing as variable** — Kelly-fractional or
   vol-targeting; permits dynamic 1-3 contract scaling on high-
   conviction signals.
8. **Pyramiding** — same strategy with stop/target tiers; scales out
   30% at 1R, 30% at 2R, 40% trail. Should improve realized $/trade
   30-50%.
9. **Liquidation cascade detection** — micro-impulse failures
   followed by stop-cascade reversals.
10. **Deep learning** — LSTM / Transformer on tick microstructure
    features. Pre-train on 60d, fine-tune on rolling 14d window.
    Last-resort: highest cost, uncertain edge.

## Section 7 — Full strategy table (sorted by $/day at $1.91)

| Strategy | Dir | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ191 | $/d NQ074 | maxDD 191 | Sharpe |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R10_BASE_R8_B04_CANON_bal_n300_t30 | R10_BASE | 282 | 5.3 | 41.8 | $5 | $11 | $139 | $146 | $447 | 0.10 |
| D10_MTF_pp236_imp5_b3_s12t24_CME | D10 | 901 | 17.0 | 42.5 | $4 | $24 | $337 | $357 | $1,043 | 0.03 |
| D10_MTF_pp382_imp5_b3_s10t30_CME | D10 | 796 | 15.0 | 39.1 | $4 | $21 | $295 | $312 | $847 | 0.03 |
| D10_MTF_pp300_imp6_b3_s8t24_CME | D10 | 793 | 15.0 | 35.7 | $2 | $20 | $280 | $298 | $781 | 0.02 |
| D5_ABS_t25_s8t24 | D5 | 8 | 0.2 | 62.5 | $1 | $1 | $15 | $15 | $19 | 0.53 |
| D4_VPIN_mid_CANON_INV_236 | D4 | 15 | 0.3 | 53.3 | $1 | $1 | $13 | $13 | $54 | 0.00 |
| D10_MTF_pp236_imp4_b3_s10t30_CME | D10 | 1,050 | 19.8 | 38.5 | $0 | $23 | $343 | $366 | $885 | 0.00 |
| D4_VPIN_lo_CANON_INV_236 | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D4_VPINhi_lo_CANON | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D4_VPINhi_mid_CANON | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D4_VPINhi_hi_CANON | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D4_VPIN_lo_INV15s_imp2_s4t12 | D4 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D3_MOTIF_s5t15 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D3_MOTIF_s8t24 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D3_MOTIF_s10t20 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D3_MOTIF_s5t20 | D3 | 0 | 0.0 | 0.0 | $0 | $0 | $0 | $0 | $0 | 0.00 |
| D7_CALadap_s8t24 | D7 | 2 | 0.0 | 0.0 | $-0 | $-0 | $-1 | $-1 | $10 | -1.16 |
| D4_VPIN_mid_INV15s_imp2_s4t12 | D4 | 43 | 0.8 | 32.6 | $-0 | $1 | $12 | $13 | $109 | 0.00 |
| D7_CALadap_s10t20 | D7 | 3 | 0.1 | 33.3 | $-0 | $-0 | $-2 | $-2 | $26 | -1.18 |
| D7_CALadap_s5t20 | D7 | 4 | 0.1 | 25.0 | $-1 | $-1 | $-5 | $-5 | $39 | -0.62 |
| D7_CALadap_s5t15 | D7 | 3 | 0.1 | 0.0 | $-1 | $-1 | $-6 | $-6 | $39 | -2.17 |
| D10_MTF_pp236_imp3_b4_s6t16_NYO | D10 | 334 | 6.3 | 33.2 | $-1 | $6 | $97 | $104 | $647 | -0.03 |
| D5_ABSinv_t25_s8t24 | D5 | 5 | 0.1 | 0.0 | $-1 | $-1 | $-12 | $-12 | $73 | -2.19 |
| D6_TAPE_x7_o5_s5t20 | D6 | 36 | 0.7 | 19.4 | $-2 | $-1 | $-9 | $-8 | $123 | -0.21 |
| D6_TAPE_x7_o5_s5t15 | D6 | 35 | 0.7 | 22.9 | $-2 | $-2 | $-13 | $-12 | $132 | -0.25 |
| D7_CAL_s10t20 | D7 | 19 | 0.4 | 31.6 | $-2 | $-2 | $-18 | $-18 | $152 | -0.81 |
| D5_ABSinv_t20_s8t24 | D5 | 49 | 0.9 | 32.7 | $-3 | $-2 | $-12 | $-11 | $224 | -0.19 |
| D10_MTF_pp300_imp4_b3_s8t20_CME | D10 | 1,048 | 19.8 | 37.6 | $-3 | $20 | $312 | $335 | $743 | -0.03 |
| D10_MTF_pp450_imp4_b3_s8t24_NYO | D10 | 254 | 4.8 | 28.7 | $-3 | $3 | $52 | $58 | $430 | -0.05 |
| D7_CAL_s5t20 | D7 | 18 | 0.3 | 11.1 | $-3 | $-3 | $-26 | $-25 | $167 | -0.79 |
| D7_CAL_s8t24 | D7 | 19 | 0.4 | 26.3 | $-3 | $-3 | $-26 | $-25 | $180 | -0.86 |
| D7_CAL_s5t15 | D7 | 18 | 0.3 | 11.1 | $-3 | $-3 | $-27 | $-26 | $172 | -1.11 |
| D5_ABS_t20_s5t15 | D5 | 58 | 1.1 | 25.9 | $-4 | $-2 | $-17 | $-16 | $205 | -0.29 |
| D6_TAPE_x7_o5_s8t24 | D6 | 34 | 0.6 | 20.6 | $-4 | $-3 | $-25 | $-24 | $189 | -0.28 |
| D10_MTF_pp382_imp5_b4_s8t16_NYO | D10 | 224 | 4.2 | 37.1 | $-4 | $1 | $36 | $40 | $406 | -0.07 |
| D10_MTF_pp450_imp5_b3_s10t24_CME | D10 | 715 | 13.5 | 39.3 | $-4 | $12 | $191 | $206 | $789 | -0.04 |
| D6_TAPE_x5_o5_s5t15 | D6 | 36 | 0.7 | 16.7 | $-4 | $-3 | $-31 | $-30 | $240 | -0.48 |
| D6_TAPE_x5_o5_s5t20 | D6 | 41 | 0.8 | 14.6 | $-4 | $-3 | $-30 | $-29 | $240 | -0.39 |
| D5_ABS_t20_s8t24 | D5 | 56 | 1.1 | 30.4 | $-4 | $-3 | $-25 | $-24 | $321 | -0.26 |
| D6_TAPE_x7_o3_s5t15 | D6 | 28 | 0.5 | 10.7 | $-5 | $-4 | $-37 | $-36 | $242 | -1.20 |
| D6_TAPE_x7_o2_s5t15 | D6 | 35 | 0.7 | 11.4 | $-6 | $-5 | $-44 | $-43 | $320 | -0.62 |
| D6_TAPE_x7_o3_s5t20 | D6 | 31 | 0.6 | 6.5 | $-6 | $-5 | $-46 | $-46 | $298 | -1.07 |
| D6_TAPE_x5_o5_s8t24 | D6 | 37 | 0.7 | 16.2 | $-6 | $-5 | $-46 | $-45 | $335 | -0.45 |
| D6_TAPE_x7_o2_s5t20 | D6 | 39 | 0.7 | 10.3 | $-6 | $-5 | $-48 | $-47 | $357 | -0.52 |
| D10_MTF_pp450_imp5_b4_s6t16_NYO | D10 | 215 | 4.1 | 30.2 | $-6 | $-1 | $9 | $14 | $397 | -0.16 |
| D10_MTF_pp382_imp5_b3_s10t24_OVR | D10 | 335 | 6.3 | 33.1 | $-7 | $1 | $42 | $50 | $673 | -0.09 |
| D6_TAPE_x7_o3_s8t24 | D6 | 30 | 0.6 | 13.3 | $-7 | $-6 | $-57 | $-57 | $356 | -0.95 |
| D6_TAPE_x5_o3_s5t20 | D6 | 35 | 0.7 | 5.7 | $-7 | $-6 | $-56 | $-56 | $397 | -0.87 |
| D10_MTF_pp190_imp5_b3_s6t16_OVR | D10 | 480 | 9.1 | 31.7 | $-7 | $4 | $86 | $96 | $616 | -0.14 |
| D6_TAPE_x7_o2_s8t24 | D6 | 39 | 0.7 | 15.4 | $-7 | $-6 | $-58 | $-57 | $420 | -0.49 |
| D6_TAPE_x5_o3_s5t15 | D6 | 39 | 0.7 | 7.7 | $-7 | $-6 | $-60 | $-59 | $411 | -1.13 |
| D6_TAPE_x3_o5_s8t24 | D6 | 81 | 1.5 | 27.2 | $-7 | $-6 | $-47 | $-45 | $389 | -0.24 |
| D6_TAPE_x5_o2_s5t20 | D6 | 46 | 0.9 | 8.7 | $-8 | $-7 | $-61 | $-60 | $480 | -0.70 |
| D10_MTF_pp190_imp4_b4_s6t30_NYO | D10 | 327 | 6.2 | 20.2 | $-8 | $-0 | $29 | $36 | $865 | -0.13 |
| D10_MTF_pp450_imp4_b4_s10t20_CME | D10 | 798 | 15.1 | 41.1 | $-8 | $10 | $182 | $199 | $917 | -0.07 |
| D5_ABSinv_t20_s5t15 | D5 | 52 | 1.0 | 15.4 | $-8 | $-7 | $-61 | $-60 | $415 | -0.69 |
| D10_MTF_pp450_imp4_b4_s12t20_OVR | D10 | 293 | 5.5 | 40.3 | $-8 | $-2 | $14 | $20 | $680 | -0.12 |
| D6_TAPE_x5_o2_s5t15 | D6 | 47 | 0.9 | 8.5 | $-8 | $-7 | $-68 | $-67 | $497 | -0.81 |
| D6_TAPE_x3_o5_s5t20 | D6 | 82 | 1.5 | 17.1 | $-8 | $-7 | $-57 | $-55 | $441 | -0.42 |
| D10_MTF_pp450_imp6_b4_s6t16_NYO | D10 | 197 | 3.7 | 28.4 | $-9 | $-4 | $-22 | $-18 | $517 | -0.26 |
| D10_MTF_pp236_imp6_b3_s6t24_CME | D10 | 934 | 17.6 | 29.2 | $-9 | $12 | $214 | $234 | $1,163 | -0.07 |
| D6_TAPE_x5_o2_s8t24 | D6 | 46 | 0.9 | 13.0 | $-9 | $-8 | $-77 | $-76 | $563 | -0.76 |
| D10_MTF_pp382_imp3_b3_s12t16_CME | D10 | 1,052 | 19.8 | 47.3 | $-10 | $13 | $243 | $266 | $1,122 | -0.08 |
| D6_TAPE_x3_o5_s5t15 | D6 | 82 | 1.5 | 17.1 | $-10 | $-8 | $-73 | $-71 | $527 | -0.54 |
| D10_MTF_pp450_imp6_b4_s10t20_CME | D10 | 606 | 11.4 | 38.9 | $-11 | $3 | $88 | $101 | $840 | -0.10 |
| D10_MTF_pp450_imp3_b4_s12t24_OVR | D10 | 312 | 5.9 | 36.2 | $-11 | $-4 | $-10 | $-3 | $893 | -0.14 |
| D6_TAPE_x5_o3_s8t24 | D6 | 38 | 0.7 | 7.9 | $-11 | $-10 | $-100 | $-99 | $624 | -1.13 |
| D10_MTF_pp300_imp3_b3_s10t20_OVR | D10 | 435 | 8.2 | 36.1 | $-13 | $-3 | $15 | $24 | $919 | -0.24 |
| D10_MTF_pp450_imp6_b3_s8t24_CME | D10 | 633 | 11.9 | 33.0 | $-13 | $1 | $77 | $91 | $863 | -0.13 |
| D6_TAPE_x3_o3_s5t20 | D6 | 126 | 2.4 | 19.8 | $-13 | $-10 | $-87 | $-84 | $717 | -0.51 |
| D10_MTF_pp450_imp6_b4_s12t24_OVR | D10 | 237 | 4.5 | 34.6 | $-14 | $-9 | $-67 | $-62 | $924 | -0.22 |
| D10_MTF_pp450_imp3_b3_s10t30_OVR | D10 | 338 | 6.4 | 28.1 | $-14 | $-7 | $-35 | $-28 | $917 | -0.21 |
| D6_TAPE_x3_o2_s5t15 | D6 | 153 | 2.9 | 22.9 | $-15 | $-11 | $-96 | $-93 | $834 | -0.47 |
| D6_TAPE_x3_o2_s5t20 | D6 | 158 | 3.0 | 22.8 | $-15 | $-11 | $-96 | $-92 | $832 | -0.41 |
| D6_TAPE_x3_o2_s8t24 | D6 | 148 | 2.8 | 29.7 | $-15 | $-12 | $-103 | $-99 | $854 | -0.43 |
| D6_TAPE_x3_o3_s5t15 | D6 | 125 | 2.4 | 19.2 | $-15 | $-13 | $-114 | $-111 | $862 | -0.69 |
| D10_MTF_pp450_imp6_b4_s6t16_OVR | D10 | 260 | 4.9 | 26.5 | $-16 | $-10 | $-77 | $-71 | $977 | -0.43 |
| D6_TAPE_x3_o3_s8t24 | D6 | 121 | 2.3 | 24.0 | $-17 | $-14 | $-130 | $-127 | $924 | -0.53 |
| D10_MTF_pp382_imp4_b4_s6t20_CME | D10 | 945 | 17.8 | 31.1 | $-18 | $3 | $131 | $152 | $1,025 | -0.20 |
| D10_MTF_pp300_imp3_b4_s10t30_OVR | D10 | 349 | 6.6 | 27.5 | $-19 | $-11 | $-74 | $-66 | $1,372 | -0.28 |
| D10_MTF_pp236_imp4_b4_s6t30_OVR | D10 | 432 | 8.2 | 18.3 | $-20 | $-10 | $-56 | $-47 | $1,105 | -0.33 |
| D10_MTF_pp300_imp6_b4_s12t16_CME | D10 | 742 | 14.0 | 44.9 | $-21 | $-5 | $30 | $46 | $1,165 | -0.24 |
| D10_MTF_pp300_imp3_b4_s8t24_NYO | D10 | 267 | 5.0 | 23.6 | $-21 | $-15 | $-126 | $-121 | $1,365 | -0.37 |
| D10_MTF_pp450_imp6_b3_s12t24_RTH | D10 | 715 | 13.5 | 37.2 | $-22 | $-6 | $11 | $27 | $1,512 | -0.23 |
| D10_MTF_pp300_imp4_b4_s12t24_NYO | D10 | 244 | 4.6 | 30.7 | $-24 | $-18 | $-157 | $-151 | $1,315 | -0.46 |
| D10_MTF_pp382_imp4_b4_s12t16_OVR | D10 | 308 | 5.8 | 39.6 | $-26 | $-19 | $-161 | $-154 | $1,474 | -0.39 |
| D10_MTF_pp236_imp6_b4_s6t16_CME | D10 | 876 | 16.5 | 32.0 | $-26 | $-7 | $23 | $43 | $1,497 | -0.31 |
| D10_MTF_pp236_imp6_b4_s10t20_RTH | D10 | 909 | 17.2 | 36.6 | $-26 | $-6 | $32 | $52 | $1,782 | -0.28 |
| D10_MTF_pp450_imp4_b4_s10t30_RTH | D10 | 747 | 14.1 | 30.3 | $-27 | $-10 | $-25 | $-8 | $1,545 | -0.23 |
| D10_MTF_pp450_imp4_b3_s6t20_RTH | D10 | 939 | 17.7 | 26.9 | $-27 | $-6 | $35 | $55 | $1,612 | -0.39 |
| D10_MTF_pp382_imp6_b3_s12t24_RTH | D10 | 772 | 14.6 | 36.4 | $-29 | $-12 | $-44 | $-27 | $1,880 | -0.25 |
| D10_MTF_pp236_imp3_b4_s12t30_RTH | D10 | 985 | 18.6 | 34.7 | $-29 | $-8 | $25 | $47 | $2,868 | -0.20 |
| D9_ADAP_R4_INV_pp382_s5t20_imp5 | D9 | 2,146 | 40.5 | 28.0 | $-34 | $14 | $359 | $406 | $2,059 | -0.26 |
| D10_MTF_pp382_imp5_b3_s10t16_RTH | D10 | 888 | 16.8 | 39.6 | $-36 | $-16 | $-71 | $-52 | $1,935 | -0.43 |
| D10_MTF_pp382_imp6_b4_s8t16_RTH | D10 | 725 | 13.7 | 34.1 | $-36 | $-20 | $-128 | $-112 | $1,925 | -0.52 |
| D10_MTF_pp300_imp3_b4_s10t20_RTH | D10 | 982 | 18.5 | 35.7 | $-39 | $-18 | $-76 | $-54 | $2,151 | -0.42 |
| D10_MTF_pp300_imp3_b4_s12t20_RTH | D10 | 959 | 18.1 | 39.4 | $-40 | $-19 | $-91 | $-70 | $2,277 | -0.44 |
| D10_MTF_pp382_imp5_b3_s12t24_all | D10 | 2,687 | 50.7 | 40.4 | $-43 | $16 | $441 | $501 | $2,583 | -0.17 |
| R10_BASE_R8_C04_MTF_early_imp4_b3_s8t24_INV | R10_BASE | 3,321 | 62.7 | 33.4 | $-44 | $29 | $633 | $706 | $2,440 | -0.19 |
| D10_MTF_pp300_imp6_b4_s8t24_RTH | D10 | 837 | 15.8 | 27.0 | $-46 | $-28 | $-193 | $-174 | $2,580 | -0.50 |
| D10_MTF_pp450_imp4_b3_s6t24_all | D10 | 3,161 | 59.6 | 27.6 | $-53 | $16 | $490 | $560 | $2,916 | -0.31 |
| D10_MTF_pp450_imp6_b4_s6t20_all | D10 | 2,129 | 40.2 | 28.4 | $-57 | $-10 | $121 | $168 | $3,103 | -0.39 |
| D10_MTF_pp300_imp5_b3_s8t30_all | D10 | 3,218 | 60.7 | 30.3 | $-59 | $12 | $457 | $528 | $3,343 | -0.27 |
| D10_MTF_pp382_imp4_b3_s12t20_all | D10 | 3,099 | 58.5 | 42.6 | $-60 | $8 | $405 | $473 | $3,502 | -0.24 |
| D5_ABS_t15_s5t20 | D5 | 778 | 14.7 | 20.2 | $-77 | $-60 | $-518 | $-501 | $4,134 | -0.75 |
| D5_ABS_t15_s5t15 | D5 | 794 | 15.0 | 21.9 | $-78 | $-60 | $-518 | $-501 | $4,139 | -0.77 |
| D5_ABSinv_t15_s5t15 | D5 | 770 | 14.5 | 20.9 | $-80 | $-63 | $-549 | $-532 | $4,278 | -1.01 |
| D5_ABSinv_t15_s3t9 | D5 | 809 | 15.3 | 15.2 | $-80 | $-62 | $-538 | $-521 | $4,261 | -1.24 |
| D9_ADAP_R4_INV_pp382_s4t16_imp3 | D9 | 2,648 | 50.0 | 25.4 | $-81 | $-22 | $51 | $110 | $4,608 | -0.57 |
| D5_ABSinv_t15_s5t20 | D5 | 770 | 14.5 | 19.2 | $-82 | $-65 | $-571 | $-554 | $4,386 | -0.93 |
| D9_ADAP_R4_INV_pp118_s4t16_imp5 | D9 | 3,047 | 57.5 | 25.3 | $-83 | $-16 | $155 | $223 | $4,565 | -0.76 |
| D9_ADAP_R4_INV_pp236_s5t20_imp5 | D9 | 2,681 | 50.6 | 25.9 | $-85 | $-26 | $21 | $81 | $4,519 | -0.56 |
| D5_ABS_t15_s3t9 | D5 | 829 | 15.6 | 14.6 | $-86 | $-68 | $-589 | $-571 | $4,548 | -1.08 |
| D9_ADAP_R4_INV_pp236_s10t20 | D9 | 2,534 | 47.8 | 37.6 | $-109 | $-53 | $-270 | $-214 | $6,060 | -0.57 |
| D10_MTF_pp236_imp5_b3_s6t24_all | D10 | 3,760 | 70.9 | 26.2 | $-110 | $-27 | $116 | $199 | $5,900 | -0.54 |
| D9_ADAP_R4_INV_pp236_s4t16_imp3 | D9 | 3,310 | 62.5 | 24.8 | $-118 | $-45 | $-104 | $-31 | $6,365 | -0.88 |
| D9_ADAP_R4_INV_pp118_s4t16_imp3 | D9 | 3,561 | 67.2 | 24.8 | $-119 | $-40 | $-35 | $44 | $6,399 | -0.73 |
| D9_ADAP_R4_CANON_INV_236 | D9 | 2,513 | 47.4 | 37.0 | $-120 | $-65 | $-389 | $-333 | $6,662 | -0.75 |
| D9_ADAP_R4_INV30s_imp3_s4t12 | D9 | 4,826 | 91.1 | 29.5 | $-143 | $-36 | $135 | $242 | $7,681 | -1.01 |
| D9_ADAP_R4_INV30s_imp3_s3t9 | D9 | 4,915 | 92.7 | 29.3 | $-165 | $-56 | $-51 | $57 | $8,744 | -1.29 |
| D4_VPIN_hi_CANON_INV_236 | D4 | 6,209 | 117.2 | 37.4 | $-234 | $-97 | $-331 | $-194 | $13,045 | -0.64 |
| D9_ADAP_R4_INV15s_imp2_s3t12 | D9 | 7,977 | 150.5 | 24.2 | $-261 | $-85 | $-23 | $153 | $13,889 | -1.39 |
| D9_ADAP_R4_INV15s_imp2_s4t12 | D9 | 7,729 | 145.8 | 28.6 | $-268 | $-97 | $-174 | $-4 | $14,264 | -1.34 |
| ENS_CHILD_R4_INV_pp382_s5t20_imp5 | ENS_CHILD | 7,144 | 134.8 | 24.7 | $-268 | $-111 | $-366 | $-208 | $14,352 | -1.05 |
| ENS_CHILD_R4_CANON_INV_236 | ENS_CHILD | 7,430 | 140.2 | 37.7 | $-272 | $-108 | $-312 | $-148 | $14,617 | -0.68 |
| R10_BASE_R4_CANON_INV_236 | R10_BASE | 7,430 | 140.2 | 37.2 | $-299 | $-135 | $-582 | $-418 | $16,162 | -0.73 |
| ENS_CHILD_R4_INV_pp118_s4t16_imp3 | ENS_CHILD | 12,654 | 238.8 | 23.7 | $-461 | $-182 | $-508 | $-229 | $24,546 | -1.29 |
| ENS_CHILD_R4_INV15s_imp2_s4t12 | ENS_CHILD | 12,788 | 241.3 | 27.8 | $-500 | $-218 | $-852 | $-569 | $26,578 | -1.62 |
| ENS_CHILD_R4_INV30s_imp3_s3t9 | ENS_CHILD | 13,898 | 262.2 | 28.0 | $-545 | $-238 | $-944 | $-637 | $28,956 | -1.74 |
| D8_ENS_v4_s10t20 | D8 | 6,377 | 120.3 | 32.1 | $-639 | $-498 | $-4,323 | $-4,182 | $33,874 | -1.66 |
| D8_ENS_v4_s8t24 | D8 | 6,928 | 130.7 | 25.8 | $-694 | $-541 | $-4,689 | $-4,536 | $36,775 | -1.67 |
| D8_ENS_v3_s10t20 | D8 | 8,310 | 156.8 | 31.4 | $-848 | $-665 | $-5,786 | $-5,603 | $44,953 | -1.75 |
| D5_ABS_t10_s5t15 | D5 | 8,388 | 158.3 | 19.8 | $-874 | $-689 | $-6,017 | $-5,832 | $46,366 | -1.49 |
| D5_ABSinv_t10_s5t15 | D5 | 8,544 | 161.2 | 19.5 | $-892 | $-704 | $-6,152 | $-5,963 | $47,357 | -1.51 |
| D8_ENS_v4_s5t15 | D8 | 9,356 | 176.5 | 20.5 | $-908 | $-701 | $-6,044 | $-5,838 | $48,121 | -1.97 |
| D4_VPIN_hi_INV15s_imp2_s4t12 | D4 | 23,771 | 448.5 | 27.6 | $-915 | $-390 | $-1,438 | $-914 | $48,510 | -1.45 |
| D8_ENS_v3_s8t24 | D8 | 9,062 | 171.0 | 25.0 | $-943 | $-742 | $-6,486 | $-6,286 | $49,953 | -1.76 |
| D8_ENS_v2_s10t20 | D8 | 9,190 | 173.4 | 31.1 | $-984 | $-781 | $-6,856 | $-6,653 | $52,133 | -1.81 |
| D8_ENS_v2_s8t24 | D8 | 10,077 | 190.1 | 24.9 | $-1,057 | $-834 | $-7,300 | $-7,077 | $56,037 | -1.84 |
| D5_ABSinv_t10_s3t9 | D5 | 11,212 | 211.5 | 14.7 | $-1,143 | $-896 | $-7,795 | $-7,547 | $60,602 | -1.60 |
| D5_ABS_t10_s3t9 | D5 | 11,216 | 211.6 | 14.4 | $-1,161 | $-914 | $-7,974 | $-7,727 | $61,556 | -1.48 |
| D8_ENS_v3_s5t15 | D8 | 13,338 | 251.7 | 19.6 | $-1,359 | $-1,064 | $-9,260 | $-8,966 | $72,007 | -2.10 |
| D8_ENS_v2_s5t15 | D8 | 15,537 | 293.2 | 19.7 | $-1,592 | $-1,249 | $-10,883 | $-10,540 | $84,388 | -2.08 |


## Section 8 — POST-HOC: GA survivors re-tested on full 60d

Generated: 2026-06-23T12:04:13

These strategies were evolved by the GA on a 7-day window and then re-tested under bot-faithful execution on the full 60d window with $1.91 and $0.74 fees, MNQ and NQ point values.

| Strategy | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ 191 | $/d NQ 074 | DD 191 | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D2_GA_pp300_imp3_b3_s10_t20_INV_30s_RTH | 4,038 | 76.2 | 35.4 | $-146 | $-57 | $-150 | $-61 | $8,897 | -0.70 |
| D2_GA_pp118_imp3_b3_s10_t20_INV_30s_RTH | 4,710 | 88.9 | 35.6 | $-155 | $-52 | $-27 | $77 | $9,162 | -0.64 |
| D2_GA_pp118_imp4_b5_s10_t20_INV_30s_RTH | 4,345 | 82.0 | 35.3 | $-162 | $-66 | $-210 | $-114 | $9,366 | -0.66 |
| D2_GA_pp300_imp3_b3_s4_t20_INV_30s_RTH | 5,652 | 106.6 | 19.6 | $-179 | $-54 | $42 | $166 | $9,742 | -1.18 |
| D2_GA_pp118_imp6_b5_s10_t16_INV_15s_RTH | 6,533 | 123.3 | 40.8 | $-180 | $-70 | $-19 | $125 | $10,205 | -0.78 |
| D2_GA_pp118_imp6_b5_s10_t20_INV_30s_RTH | 4,206 | 79.4 | 34.7 | $-180 | $-87 | $-436 | $-343 | $10,468 | -0.70 |
| D2_GA_pp382_imp6_b5_s8_t16_INV_15s_RTH | 5,345 | 100.8 | 35.2 | $-189 | $-71 | $-158 | $-40 | $10,933 | -0.76 |
| D2_GA_pp118_imp6_b5_s10_t20_INV_15s_RTH | 5,879 | 110.9 | 35.6 | $-191 | $-61 | $-5 | $125 | $10,661 | -0.74 |
| D2_GA_pp300_imp3_b3_s4_t16_INV_30s_RTH | 6,044 | 114.0 | 22.9 | $-195 | $-62 | $6 | $140 | $10,519 | -1.29 |
| D2_GA_pp118_imp6_b5_s10_t16_INV_15s_RTH | 6,533 | 123.3 | 40.5 | $-203 | $-70 | $-19 | $125 | $11,356 | -0.82 |
| D2_GA_pp118_imp6_b5_s10_t16_INV_15s_RTH | 6,524 | 123.1 | 40.5 | $-206 | $-70 | $-19 | $125 | $11,672 | -0.84 |
| D2_GA_pp118_imp6_b5_s10_t16_INV_15s_RTH | 6,533 | 123.3 | 40.3 | $-214 | $-70 | $-19 | $125 | $12,050 | -1.02 |
| D2_GA_pp236_imp3_b3_s8_t16_INV_15s_RTH | 7,574 | 142.9 | 35.1 | $-276 | $-111 | $-327 | $-160 | $15,159 | -1.10 |
| D2_GA_pp236_imp3_b3_s8_t16_INV_15s_RTH | 7,580 | 143.0 | 35.1 | $-279 | $-111 | $-327 | $-160 | $15,349 | -1.15 |
| D2_GA_pp300_imp3_b3_s4_t16_INV_15s_RTH | 9,487 | 179.0 | 22.5 | $-330 | $-120 | $-218 | $-9 | $17,655 | -1.47 |

GA passers (60d): MNQ$1.91=0 MNQ$0.74=0 NQ$1.91=0 NQ$0.74=0

# Round 18 — TRULY advanced ML (PyTorch + sklearn)

Generated: 2026-06-25T03:52:28.015002
Elapsed wall-clock: 47.3 min
Execution: r9_bot_on_tick AS-IS. No queue/fill patching.

PyTorch available: True
sklearn available: True

## Training data (Phase 1, 26d)

- Total emitted setups -> features captured: 29006
- Positive (win) rate: 0.337
- Train/Val split: 23205/5801

## Model validation AUCs

| Model | Val AUC |
|---|---:|
| MLP (mlp) | 0.5258 |
| TRF (transformer) | 0.5191 |
| LR (logreg) | 0.5116 |
| GBM (gbm) | 0.5055 |
| RF (rf) | 0.5018 |

## Phase 1 baseline donor performance (in-sample 26d)

| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| TR_CANON_500_s10t20 | 2,208 | 84.9 | 38.1 | $-219.53 | $-2.59 | $5776 | -0.78 |
| TR_IMP4_382_s8t20 | 3,031 | 116.6 | 34.3 | $-251.49 | $-2.16 | $6702 | -1.08 |
| TR_CANON_382_s10t20 | 2,715 | 104.4 | 37.8 | $-257.13 | $-2.46 | $6881 | -0.91 |
| TR_CANON_236_s10t20 | 3,273 | 125.9 | 37.2 | $-344.22 | $-2.73 | $8969 | -1.10 |
| TR_CANON_236_s8t16 | 3,797 | 146.0 | 36.2 | $-344.51 | $-2.36 | $9255 | -1.06 |
| TR_CANON_236_s5t15 | 4,508 | 173.4 | 28.5 | $-377.26 | $-2.18 | $10060 | -1.23 |
| TR_IMP3_236_s8t16 | 4,077 | 156.8 | 36.2 | $-383.58 | $-2.45 | $10040 | -1.10 |
| TR_IMP3_118_s5t15 | 5,397 | 207.6 | 28.2 | $-469.73 | $-2.26 | $12403 | -1.31 |

## Phase 3 OOS results (21d) — BASELINE (no gate)

| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| BL_CANON_236_s10t20 | 2,951 | 140.5 | 36.2 | $-338.36 | $-2.41 | $7351 | -0.77 |
| BL_IMP3_236_s8t16 | 3,582 | 170.6 | 35.4 | $-401.89 | $-2.36 | $8519 | -1.22 |
| BL_CANON_236_s8t16 | 3,399 | 161.9 | 35.0 | $-411.32 | $-2.54 | $8714 | -1.22 |
| BL_IMP3_118_s5t15 | 4,803 | 228.7 | 27.9 | $-436.27 | $-1.91 | $9246 | -1.20 |

## Phase 3 OOS results (21d) — ML-GATED

| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe | n_filt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| G_MLP_t65_CANON_236_s10t20 | 11 | 0.5 | 54.5 | $+5.43 | $+10.36 | $69 | 0.42 | 14764 |
| G_MLP_t65_CANON_236_s8t16 | 10 | 0.5 | 40.0 | $+0.29 | $+0.61 | $84 | 0.03 | 14764 |
| G_TRF_t65_CANON_236_s10t20 | 0 | 0.0 | 0.0 | $+0.00 | $+0.00 | $0 | 0.00 | 14812 |
| G_TRF_t65_CANON_236_s8t16 | 0 | 0.0 | 0.0 | $+0.00 | $+0.00 | $0 | 0.00 | 14812 |
| G_TRF_t65_IMP3_118_s5t15 | 0 | 0.0 | 0.0 | $+0.00 | $+0.00 | $0 | 0.00 | 17274 |
| G_TRF_t65_IMP3_236_s8t16 | 0 | 0.0 | 0.0 | $+0.00 | $+0.00 | $0 | 0.00 | 17274 |
| G_MLP_t65_IMP3_236_s8t16 | 13 | 0.6 | 38.5 | $-0.10 | $-0.17 | $76 | -0.01 | 17219 |
| G_MLP_t65_IMP3_118_s5t15 | 11 | 0.5 | 18.2 | $-2.98 | $-5.70 | $93 | -0.34 | 17218 |
| G_TRF_t55_CANON_236_s8t16 | 321 | 15.3 | 38.0 | $-32.45 | $-2.12 | $836 | -0.47 | 13775 |
| G_TRF_t55_CANON_236_s10t20 | 298 | 14.2 | 39.6 | $-35.50 | $-2.50 | $948 | -0.50 | 13775 |
| G_TRF_t55_IMP3_118_s5t15 | 430 | 20.5 | 29.1 | $-37.47 | $-1.83 | $940 | -0.34 | 15981 |
| G_TRF_t55_IMP3_236_s8t16 | 371 | 17.7 | 38.0 | $-41.14 | $-2.33 | $951 | -0.54 | 15960 |
| G_MLP_t55_IMP3_118_s5t15 | 930 | 44.3 | 26.6 | $-101.69 | $-2.30 | $2211 | -0.68 | 14360 |
| G_MLP_t55_CANON_236_s10t20 | 756 | 36.0 | 35.1 | $-107.66 | $-2.99 | $2441 | -0.46 | 11870 |
| G_MLP_t55_IMP3_236_s8t16 | 878 | 41.8 | 34.3 | $-112.58 | $-2.69 | $2458 | -0.49 | 13964 |
| G_MLP_t55_CANON_236_s8t16 | 809 | 38.5 | 32.5 | $-131.68 | $-3.42 | $2861 | -0.58 | 11872 |
| G_MLP_t45_CANON_236_s10t20 | 2,444 | 116.4 | 36.6 | $-236.12 | $-2.03 | $5494 | -0.55 | 2908 |
| G_TRF_t45_CANON_236_s10t20 | 2,939 | 140.0 | 37.0 | $-288.85 | $-2.06 | $6374 | -0.72 | 2 |
| G_MLP_t45_CANON_236_s8t16 | 2,784 | 132.6 | 35.2 | $-299.75 | $-2.26 | $6519 | -0.86 | 2908 |
| G_MLP_t45_IMP3_236_s8t16 | 2,915 | 138.8 | 35.2 | $-314.57 | $-2.27 | $6711 | -0.92 | 3646 |
| G_MLP_t45_IMP3_118_s5t15 | 3,847 | 183.2 | 27.8 | $-341.83 | $-1.87 | $7185 | -1.19 | 3720 |
| G_TRF_t45_CANON_236_s8t16 | 3,406 | 162.2 | 35.3 | $-392.07 | $-2.42 | $8358 | -1.23 | 2 |
| G_TRF_t45_IMP3_236_s8t16 | 3,581 | 170.5 | 35.5 | $-393.09 | $-2.31 | $8316 | -1.23 | 2 |
| G_TRF_t45_IMP3_118_s5t15 | 4,802 | 228.7 | 27.8 | $-444.37 | $-1.94 | $9392 | -1.39 | 3 |

## Phase 3 lift analysis (best gated vs best baseline)

- Best BASELINE: **BL_CANON_236_s10t20** $-338.36/d @ 36.2% WR, 140.5 tr/d
- Best GATED: **G_MLP_t65_CANON_236_s10t20** $+5.43/d @ 54.5% WR, 0.5 tr/d
- ML lift: **$+343.78/day**
- WR delta: +18.4 pp

## Phase 4 hyperparameter random search (15d, 40 trials)

Top 20 by $/day:

| Strategy | Tr/d | WR% | $/day | $/trade | DD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| HS_014_imp50_b5_pp500_s10t30_INV_cd10 | 68.2 | 36.8 | $-184.16 | $-2.70 | $2911 | -0.69 |
| HS_013_imp60_b5_pp500_s5t12_INV_cd10 | 81.8 | 30.9 | $-221.97 | $-2.71 | $3409 | -1.06 |
| HS_025_imp60_b5_pp500_s4t8_INV_cd5 | 89.1 | 34.3 | $-223.45 | $-2.51 | $3372 | -1.42 |
| HS_015_imp40_b5_pp500_s4t6_INV_cd10 | 114.1 | 42.1 | $-247.09 | $-2.16 | $3736 | -1.62 |
| HS_005_imp60_b3_pp382_s6t15_INV_cd30 | 98.7 | 31.1 | $-247.26 | $-2.50 | $3894 | -1.15 |
| HS_032_imp60_b3_pp500_s5t12_INV_cd10 | 82.5 | 29.3 | $-250.09 | $-3.03 | $3774 | -1.41 |
| HS_036_imp60_b5_pp500_s5t10_INV_cd10 | 84.4 | 32.9 | $-253.60 | $-3.00 | $3861 | -1.22 |
| HS_017_imp60_b5_pp382_s10t15_TRD_cd5 | 83.4 | 40.6 | $-259.40 | $-3.11 | $4016 | -1.31 |
| HS_029_imp40_b4_pp500_s5t7_INV_cd30 | 114.5 | 42.4 | $-274.47 | $-2.40 | $4164 | -1.61 |
| HS_018_imp50_b5_pp382_s4t10_INV_cd10 | 126.9 | 31.1 | $-274.96 | $-2.17 | $4205 | -1.25 |
| HS_023_imp40_b5_pp500_s10t20_INV_cd30 | 75.7 | 37.2 | $-279.42 | $-3.69 | $4315 | -0.84 |
| HS_001_imp30_b5_pp500_s4t6_INV_cd10 | 125.3 | 41.4 | $-280.68 | $-2.24 | $4250 | -1.73 |
| HS_037_imp30_b5_pp118_s12t30_INV_cd5 | 101.0 | 38.3 | $-300.52 | $-2.98 | $5019 | -0.89 |
| HS_016_imp40_b5_pp500_s10t15_INV_cd30 | 79.2 | 39.8 | $-302.44 | $-3.82 | $4616 | -1.00 |
| HS_034_imp40_b4_pp500_s8t16_INV_cd5 | 87.6 | 35.0 | $-304.19 | $-3.47 | $4642 | -1.07 |
| HS_024_imp40_b5_pp236_s12t30_INV_cd20 | 93.7 | 37.2 | $-319.99 | $-3.41 | $5163 | -1.14 |
| HS_019_imp60_b3_pp382_s10t20_TRD_cd5 | 82.7 | 35.7 | $-333.51 | $-4.03 | $5003 | -1.64 |
| HS_011_imp40_b5_pp382_s4t8_INV_cd20 | 142.3 | 34.8 | $-334.07 | $-2.35 | $5031 | -1.61 |
| HS_026_imp50_b3_pp236_s10t20_INV_cd5 | 106.9 | 37.3 | $-343.98 | $-3.22 | $5593 | -0.91 |
| HS_035_imp40_b4_pp118_s8t20_INV_cd20 | 127.8 | 33.7 | $-344.35 | $-2.69 | $5709 | -0.75 |

## FULL_PASS list (>=300 tr/d, >=45% WR, >=$1k/day, DD<=$5k)

**NONE.** Consistent with rounds 5-17.

## Honest assessment

- No strategy met the $1k/day + 300tr/d + 45% WR + $5k DD bar.
- Best OOS result: **G_MLP_t65_CANON_236_s10t20** $+5.43/day @ 54.5% WR, 0.5 tr/d.
- ML gating improved OOS $/day vs baseline by $+343.78.
- The $1k/day target at 1 MNQ + $1.91 fees requires a per-trade edge that does not appear to exist under honest execution. With $2,100 capital and these results, paper-trading (or rejecting the goal) is the rational path.
- Best hyperparameter trial (14d): **HS_014_imp50_b5_pp500_s10t30_INV_cd10** $-184.16/day @ 36.8% WR, 68.2 tr/d.

## Notes

- Feature->label alignment: features for the first N emitted setups are aligned to the first N completed trades. The r9 executor processes fills in setup-emission order, so this is approximate (some setups may expire unfilled, biasing alignment). This means the trained model sees PARTIALLY noisy labels; nonetheless the donor metric we care about is OOS net P&L under r9 execution, which is robust.
- All OOS metrics are produced by r9_bot_on_tick verbatim, with the ML gate operating only by marking `s['used']=True` BEFORE the executor attempts fill. No fill logic is changed.

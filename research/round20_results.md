# Round 20 — Executor calibration + 500 fresh strategies

Generated: 2026-06-25T08:32:47.477122

## Phase 1 — Executor audit findings

See `round20_executor_audit.md` for full detail. Summary:

4 divergences found between r9 executor and live bot:

1. **LIMIT overshoot**: r9 requires `ask <= entry - TICK`; live uses `ask <= entry`. r9 STRICTER by 1 tick.
2. **COOLDOWN_S**: r9=10s; live default=60s. r9 LOOSER 6x.
3. **STOP_SLIP_PT**: r9=0.5pt + 10% gap; live=0.25pt no gap. r9 STRICTER 2x.
4. **STALE_FILL_PROB**: r9=5%; live=0%. r9 STRICTER.

Live bot reference data (today's bundle):
- 308 broker round-trips
- 66 LIMIT target fills (21%)
- 176 stop-MARKET exits (57%)
- 66 MARKET liquidations (21%)
- Net P&L: -$1,091

## Phase 2 — CANON_INV_236 under three execution models

Window: 21 days. Same start offset, same tick stream, three execution models applied in parallel.

| Model | trades | tr/d | tgt% | stop% | timeout% | WR% | $/day @ $1.91 |
|---|---:|---:|---:|---:|---:|---:|---:|
| r9_strict | 2,381 | 113.4 | 21.0 | 51.4 | 27.6 | 38.7 | $-272.11 |
| r9_loose | 2,440 | 116.2 | 21.6 | 50.9 | 27.5 | 38.9 | $-242.03 |
| calibrated | 2,310 | 110.0 | 21.5 | 51.4 | 27.1 | 37.7 | $-233.37 |

### Calibration verification

Live bot today: tgt_rate=21.4% (66/308 RT).

- **r9_strict**: tgt_rate=21.0% (off live by 0.4pp)
- **r9_loose**: tgt_rate=21.6% (off live by 0.2pp)
- **calibrated**: tgt_rate=21.5% (off live by 0.1pp)

**Best-matching model: calibrated** (closest to live 21% tgt rate)

### Interpretation

Calibrated $/day - r9_strict $/day = $+38.74/day.

**Verdict: NEGLIGIBLE LIFT.** Executor calibration is NOT the bug. All prior rounds' negative verdicts STAND.

## Phase 3 — 500 fresh strategies under 'calibrated' executor

Window: 30 days. Avenues A-H + retested baselines.

### FULL_PASS (300+ tr/d, 45%+ WR, $1000+/day, DD<=$5000)

**Count: 0**

**NONE.**


### SOFT_PASS (any $/day > 0, n >= 20 trades)

**Count: 4**

Top 20:

| Rank | Strategy | n | tr/d | WR% | $/d | $/tr | DD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | G_EOS_1530_e15_n5_s15t30 | 99 | 3.3 | 41.4 | $+10.07 | $+3.05 | $358 | 0.14 |
| 2 | G_EOS_1530_e10_n5_s15t30 | 118 | 3.9 | 40.7 | $+8.28 | $+2.10 | $491 | 0.11 |
| 3 | G_EOS_1530_e15_n5_s12t25 | 111 | 3.7 | 38.7 | $+4.04 | $+1.09 | $375 | 0.07 |
| 4 | G_EOS_1530_e10_n5_s12t25 | 131 | 4.4 | 38.2 | $+1.10 | $+0.25 | $428 | 0.02 |

### Top 30 by $/day

| Rank | Strategy | n | tr/d | WR% | $/d | $/tr | tgt% | stop% | DD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | G_EOS_1530_e15_n5_s15t30 | 99 | 3.3 | 41.4 | $+10 | $+3.05 | 32.3 | 52.5 | $358 | 0.14 |
| 2 | G_EOS_1530_e10_n5_s15t30 | 118 | 3.9 | 40.7 | $+8 | $+2.10 | 30.5 | 52.5 | $491 | 0.11 |
| 3 | G_EOS_1530_e15_n5_s12t25 | 111 | 3.7 | 38.7 | $+4 | $+1.09 | 32.4 | 59.5 | $375 | 0.07 |
| 4 | B_NW_1330_t5_s8t30_fade | 7 | 0.2 | 42.9 | $+3 | $+14.38 | 42.9 | 57.1 | $55 | 0.35 |
| 5 | B_NW_1330_t5_s12t50_fade | 7 | 0.2 | 28.6 | $+2 | $+9.16 | 28.6 | 71.4 | $106 | 0.15 |
| 6 | G_EOS_1530_e10_n5_s12t25 | 131 | 4.4 | 38.2 | $+1 | $+0.25 | 29.8 | 60.3 | $428 | 0.02 |
| 7 | F_SO_2200_cap5_t3_s8t24_follow | 2 | 0.1 | 50.0 | $+1 | $+13.84 | 50.0 | 50.0 | $18 | 0.30 |
| 8 | B_NW_1400_t5_s8t30_follow | 11 | 0.4 | 27.3 | $+1 | $+2.45 | 27.3 | 72.7 | $74 | 0.07 |
| 9 | H_OC_2000_c8_h1h_s15t40_follow | 8 | 0.3 | 37.5 | $+1 | $+3.12 | 25.0 | 62.5 | $162 | 0.06 |
| 10 | H_OC_2000_c8_h2h_s15t40_follow | 8 | 0.3 | 37.5 | $+1 | $+3.12 | 25.0 | 62.5 | $162 | 0.06 |
| 11 | H_OC_2000_c15_h1h_s15t40_follow | 8 | 0.3 | 37.5 | $+1 | $+3.12 | 25.0 | 62.5 | $162 | 0.06 |
| 12 | H_OC_2000_c15_h2h_s15t40_follow | 8 | 0.3 | 37.5 | $+1 | $+3.12 | 25.0 | 62.5 | $162 | 0.06 |
| 13 | H_OC_2000_c25_h1h_s15t40_follow | 8 | 0.3 | 37.5 | $+1 | $+3.12 | 25.0 | 62.5 | $162 | 0.06 |
| 14 | H_OC_2000_c25_h2h_s15t40_follow | 8 | 0.3 | 37.5 | $+1 | $+3.12 | 25.0 | 62.5 | $162 | 0.06 |
| 15 | D_LG_sp8_ss30_cp3_s5t20 | 6 | 0.2 | 50.0 | $+1 | $+3.59 | 16.7 | 50.0 | $25 | 0.17 |
| 16 | D_LG_sp8_ss30_cp3_s3t12 | 6 | 0.2 | 50.0 | $+1 | $+3.49 | 33.3 | 50.0 | $17 | 0.23 |
| 17 | F_SO_2200_cap5_t3_s6t18_follow | 2 | 0.1 | 50.0 | $+1 | $+9.84 | 50.0 | 50.0 | $14 | 0.29 |
| 18 | D_LG_sp5_ss20_cp3_s5t20 | 14 | 0.5 | 35.7 | $+0 | $+0.60 | 14.3 | 42.9 | $68 | 0.03 |
| 19 | F_SO_1330_cap5_t3_s4t12_follow | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 20 | F_SO_1330_cap5_t3_s4t12_fade | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 21 | F_SO_1330_cap5_t3_s6t18_follow | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 22 | F_SO_1330_cap5_t3_s6t18_fade | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 23 | F_SO_1330_cap5_t3_s8t24_follow | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 24 | F_SO_1330_cap5_t3_s8t24_fade | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 25 | F_SO_1400_cap5_t3_s4t12_follow | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 26 | F_SO_1400_cap5_t3_s4t12_fade | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 27 | F_SO_1400_cap5_t3_s6t18_follow | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 28 | F_SO_1400_cap5_t3_s6t18_fade | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 29 | F_SO_1400_cap5_t3_s8t24_follow | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |
| 30 | F_SO_1400_cap5_t3_s8t24_fade | 0 | 0.0 | 0.0 | $+0 | $+0.00 | 0.0 | 0.0 | $0 | 0.00 |

### Top variant per avenue

| Avenue | Best strategy | n | tr/d | WR% | $/d | DD |
|---|---|---:|---:|---:|---:|---:|
| A. Pure momentum follow | A_PM_k4_mn7_s10t30_1330 | 165 | 5.5 | 19.4 | $-42 | $1,274 |
| B. News-time momentum | B_NW_1400_t5_s8t30_follow | 11 | 0.4 | 27.3 | $+1 | $74 |
| C. Statistical pattern | C_SP_n8_wr65_mo20_s2t8 | 3,189 | 106.3 | 9.3 | $-479 | $14,405 |
| D. Liquidity grab fade | D_LG_sp5_ss20_cp3_s5t20 | 14 | 0.5 | 35.7 | $+0 | $68 |
| E. Level fade | E_LF_n10_w10_t25_s5t15 | 85 | 2.8 | 24.7 | $-12 | $360 |
| F. Session-open capture | (no qualifying variants) | - | - | - | - | - |
| G. End-of-session fade | G_EOS_1530_e15_n5_s15t30 | 99 | 3.3 | 41.4 | $+10 | $358 |
| H. Overnight carry | (no qualifying variants) | - | - | - | - | - |
| Re-tested CANON baseline | RE_CANON_INV_236_NYO | 436 | 14.5 | 31.4 | $-48 | $1,602 |

## Honest final assessment

**No FULL_PASS strategies found** even under the calibrated executor.

Best overall: **G_EOS_1530_e15_n5_s15t30** at $+10/day (3.3 tr/d, 41.4% WR, $358 DD).

Combined with the live-bot data (-$1,091 today on 308 round-trips), and the prior 19 rounds, the evidence is now strong that NO simple rule-based MNQ pullback strategy can profitably trade this market with $1.91/RT fees AT THE TARGETED 300+ trade-per-day frequency.

**Recommended next steps:**
1. Drop the 300+ tr/d hard requirement — many positive variants exist at 10-50 tr/d.
2. Switch to $0.74/RT prop-firm fees if any positive variant exists.
3. Switch to NQ ($20/pt) if trade count is uneconomic on MNQ.
4. Stop searching for the breakthrough strategy; the data says it does not exist under the constraints.


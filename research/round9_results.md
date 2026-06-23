# Round 9 strategy search — five-angle attack

Generated: 2026-06-23T11:32:46.869698
Period: 53 calendar-day buckets from offset 7,820,974,790 (max-days=60)
Tick stream: 15,896,413 lines processed
Strategies tested: 91
Walk-forward families: 12

## Execution model

Bot-faithful: queue overshoot by 1 tick (LIMIT), 200ms latency, 10pt approach threshold, multi-setup lock, 0.5pt stop slip + 10% gap risk, 10s cooldown, 600s max hold.

Fees tracked: **$1.91/RT** (commission $0.74 + exchange $1.17) vs **$0.74/RT** (prop-firm: exchange rebated).

Instruments: MNQ ($2/pt) and NQ ($20/pt — for D-analysis).

## Hard requirements
- 300+ trades/day average
- 45%+ win rate
- $1000+ net daily P&L
- Max DD <= $5000

## Section 7 — Strategies meeting ALL hard reqs (60d, MNQ)

### Under $1.91/RT fees: **0** strategies

**NONE.** Same as rounds 5-8.

### Under $0.74/RT fees (prop-firm Apex/TopstepX/Tradeify/Bulenox): **0** strategies

**NONE.** Fee reduction alone does not lift any variant.

### NQ (10x point value, same fee model)

- Under $1.91/RT NQ: 0 pass
- Under $0.74/RT NQ: 0 pass


## Section 1 — Top 20 by $/day under $1.91 fees (baseline MNQ)

| Rank | Strategy | Tr | Tr/d | WR% | $/day | $/tr | maxDD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | R8_B04_CANON_bal_n300_t30 | 291 | 5.5 | 41.2 | $3 | $0.49 | $493 | 0.06 |
| 2 | R8_B04_CANON_bal_n500_t50 | 75 | 1.4 | 37.3 | $-2 | $-1.38 | $319 | -0.07 |
| 3 | R7_VRP_v1-3_s5t15 | 337 | 6.4 | 37.1 | $-11 | $-1.70 | $799 | -0.30 |
| 4 | R7_SRR_lk20_sw8_s5t20 | 151 | 2.8 | 17.2 | $-12 | $-4.24 | $690 | -0.47 |
| 5 | R8_B04_CANON_bal_n200_t20 | 667 | 12.6 | 37.0 | $-21 | $-1.70 | $1,606 | -0.25 |
| 6 | R8_E01_CANON_NYO_INV_236 | 755 | 14.2 | 35.4 | $-22 | $-1.53 | $1,814 | -0.22 |
| 7 | R8_B05_CANON_winOVR | 972 | 18.3 | 36.0 | $-23 | $-1.23 | $2,204 | -0.20 |
| 8 | R8_B05_CANON_winNYO | 746 | 14.1 | 35.0 | $-25 | $-1.78 | $2,118 | -0.24 |
| 9 | R8_E01_CANON_OVR_INV_236 | 954 | 18.0 | 35.5 | $-25 | $-1.41 | $2,131 | -0.23 |
| 10 | R7_MTF_imp6_pp382_s5t20_INV | 2,501 | 47.2 | 25.9 | $-54 | $-1.14 | $2,938 | -0.43 |
| 11 | R8_C04_MTF_early_imp4_b3_s8t24_INV | 3,330 | 62.8 | 33.1 | $-55 | $-0.87 | $3,018 | -0.24 |
| 12 | R8_E01_CANON_RTH_INV_236 | 2,435 | 45.9 | 35.7 | $-87 | $-1.89 | $5,495 | -0.49 |
| 13 | R8_B02_CANON_velmin5 | 4,010 | 75.7 | 35.8 | $-152 | $-2.01 | $8,574 | -0.50 |
| 14 | WF_INV_pp382_imp6_s8t20 | 5,933 | 111.9 | 33.8 | $-207 | $-1.85 | $11,165 | -0.83 |
| 15 | WF_INV_pp382_imp6_s8t24 | 5,789 | 109.2 | 31.7 | $-218 | $-1.99 | $11,754 | -0.85 |
| 16 | WF_INV_pp382_imp6_s6t18 | 6,496 | 122.6 | 29.7 | $-220 | $-1.79 | $11,857 | -0.90 |
| 17 | WF_INV_pp382_imp6_s5t20 | 6,635 | 125.2 | 24.9 | $-228 | $-1.82 | $12,197 | -0.94 |
| 18 | R4_INV_pp382_s5t20_imp5 | 7,099 | 133.9 | 25.2 | $-236 | $-1.76 | $12,576 | -0.95 |
| 19 | WF_CANON_INV_236_s12t20 | 7,020 | 132.5 | 40.8 | $-258 | $-1.95 | $14,165 | -0.63 |
| 20 | WF_INV_pp382_imp6_s5t15 | 6,990 | 131.9 | 28.3 | $-265 | $-2.01 | $14,155 | -1.23 |

## Section 2 — Top 20 by $/day under $0.74 fees (prop-firm MNQ)

| Rank | Strategy | Tr | Tr/d | WR% | $/day | $/tr | maxDD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | R8_C04_MTF_early_imp4_b3_s8t24_INV | 3,330 | 62.8 | 33.6 | $19 | $0.30 | $1,127 | 0.08 |
| 2 | R8_B04_CANON_bal_n300_t30 | 291 | 5.5 | 41.2 | $9 | $1.66 | $427 | 0.19 |
| 3 | R7_MTF_imp6_pp382_s5t20_INV | 2,501 | 47.2 | 26.1 | $2 | $0.03 | $1,101 | 0.01 |
| 4 | R8_B04_CANON_bal_n500_t50 | 75 | 1.4 | 37.3 | $-0 | $-0.21 | $244 | -0.01 |
| 5 | R8_B05_CANON_winOVR | 972 | 18.3 | 36.1 | $-1 | $-0.06 | $1,582 | -0.01 |
| 6 | R7_VRP_v1-3_s5t15 | 337 | 6.4 | 38.6 | $-3 | $-0.53 | $484 | -0.10 |
| 7 | R8_E01_CANON_OVR_INV_236 | 954 | 18.0 | 35.6 | $-4 | $-0.24 | $1,608 | -0.04 |
| 8 | R8_E01_CANON_NYO_INV_236 | 755 | 14.2 | 35.4 | $-5 | $-0.36 | $1,349 | -0.05 |
| 9 | R8_B04_CANON_bal_n200_t20 | 667 | 12.6 | 37.0 | $-7 | $-0.53 | $976 | -0.08 |
| 10 | R8_B05_CANON_winNYO | 746 | 14.1 | 35.0 | $-9 | $-0.61 | $1,657 | -0.08 |
| 11 | R7_SRR_lk20_sw8_s5t20 | 151 | 2.8 | 17.2 | $-9 | $-3.07 | $525 | -0.34 |
| 12 | R8_E01_CANON_RTH_INV_236 | 2,435 | 45.9 | 35.9 | $-33 | $-0.72 | $3,809 | -0.19 |
| 13 | R8_B02_CANON_velmin5 | 4,010 | 75.7 | 35.9 | $-63 | $-0.84 | $4,561 | -0.22 |
| 14 | WF_INV_pp382_imp6_s8t20 | 5,933 | 111.9 | 34.2 | $-76 | $-0.68 | $4,373 | -0.32 |
| 15 | WF_INV_pp382_imp6_s6t18 | 6,496 | 122.6 | 29.9 | $-76 | $-0.62 | $4,354 | -0.34 |
| 16 | R4_INV_pp382_s5t20_imp5 | 7,099 | 133.9 | 25.4 | $-79 | $-0.59 | $4,910 | -0.34 |
| 17 | WF_INV_pp382_imp6_s5t20 | 6,635 | 125.2 | 25.1 | $-82 | $-0.65 | $4,609 | -0.36 |
| 18 | WF_INV_pp382_imp6_s8t24 | 5,789 | 109.2 | 32.1 | $-90 | $-0.82 | $5,117 | -0.38 |
| 19 | WF_CANON_INV_236_s12t20 | 7,020 | 132.5 | 41.6 | $-103 | $-0.78 | $7,679 | -0.26 |
| 20 | WF_INV_pp236_imp6_s10t20 | 7,133 | 134.6 | 37.8 | $-110 | $-0.82 | $7,046 | -0.31 |

### Fee-reduction lift: $/day at $0.74 - $/day at $1.91 (top 20 by lift)

| Strategy | $1.91 $/d | $0.74 $/d | Lift | Tr/d | WR% | maxDD |
|---|---:|---:|---:|---:|---:|---:|
| R4_INV15s_imp2_s2t8 | $-1,565 | $-636 | $929 | 793.9 | 24.1 | $82,961 |
| WF_INV15s_imp2_s2t8 | $-1,564 | $-636 | $928 | 792.9 | 24.1 | $82,921 |
| R4_INV15s_imp2_s2t10 | $-1,447 | $-586 | $862 | 736.5 | 20.4 | $76,795 |
| WF_INV15s_imp2_s2t10 | $-1,413 | $-552 | $861 | 735.7 | 20.6 | $74,956 |
| WF_INV15s_imp2_s2t12 | $-1,296 | $-491 | $804 | 687.5 | 18.0 | $68,686 |
| WF_INV15s_imp2_s3t9 | $-1,301 | $-514 | $788 | 673.2 | 28.5 | $69,010 |
| R4_INV15s_imp2_s3t9 | $-1,329 | $-542 | $787 | 673.0 | 28.3 | $70,502 |
| R4_INV15s_imp2_s3t12 | $-1,153 | $-451 | $701 | 599.5 | 23.3 | $61,162 |
| WF_INV15s_imp2_s3t12 | $-1,155 | $-454 | $701 | 599.1 | 23.2 | $61,305 |
| WF_INV15s_imp2_s3t15 | $-1,057 | $-418 | $638 | 545.6 | 19.9 | $56,057 |
| WF_INV15s_imp2_s4t12 | $-1,042 | $-417 | $624 | 533.6 | 27.9 | $55,386 |
| R4_INV15s_imp2_s4t12 | $-1,042 | $-418 | $624 | 533.2 | 27.9 | $55,358 |
| WF_INV30s_imp3_s2t8 | $-941 | $-371 | $570 | 487.3 | 24.3 | $49,897 |
| WF_INV30s_imp3_s2t10 | $-901 | $-355 | $545 | 466.0 | 20.5 | $47,728 |
| WF_INV15s_imp2_s4t16 | $-871 | $-326 | $545 | 465.6 | 23.4 | $46,296 |
| R4_INV30s_imp3_s2t10 | $-901 | $-357 | $544 | 465.1 | 20.5 | $47,748 |
| WF_INV30s_imp3_s3t9 | $-837 | $-324 | $513 | 438.4 | 28.6 | $44,370 |
| R4_INV30s_imp3_s3t9 | $-871 | $-359 | $512 | 437.4 | 28.3 | $46,154 |
| WF_INV15s_imp2_s5t15 | $-795 | $-288 | $507 | 433.6 | 28.2 | $42,332 |
| R4_INV30s_imp3_s3t12 | $-732 | $-260 | $472 | 403.7 | 23.7 | $38,843 |

## Section 3 — Walk-forward parameter optimization

Blocks: B0 d0-14, B1 d15-29, B2 d30-44, B3 d45-60


### Walk-forward under $1.91/RT fees

| Family | Fixed-best | Fixed full $ | WF total test $ | WF beats fixed? |
|---|---|---:|---:|:---:|
| INV_15s_pp236 | R4_INV15s_imp2_s4t12 | $-55,224 | $-44,877 | YES |
| INV_1m_pp118 | R4_INV_pp118_s4t16_imp5 | $-22,476 | $-17,987 | YES |
| INV_1m_pp236 | R4_INV_pp236_s10t20 | $-15,734 | $-11,229 | YES |
| INV_1m_pp382 | R4_INV_pp382_s5t20_imp5 | $-12,506 | $-8,554 | YES |
| INV_30s_pp236 | R4_INV30s_imp3_s4t12 | $-36,897 | $-28,528 | YES |
| R7_cands | R7_VRP_v1-3_s5t15 | $-572 | $-316 | YES |
| R8_winners | R8_B04_CANON_bal_n300_t30 | $143 | $472 | YES |
| WF_CANON_INV_236 | WF_CANON_INV_236_s12t20 | $-13,695 | $-10,996 | YES |
| WF_INV15s_imp2 | WF_INV15s_imp2_s5t20 | $-33,349 | $-26,043 | YES |
| WF_INV30s_imp3 | WF_INV30s_imp3_s5t20 | $-27,707 | $-20,644 | YES |
| WF_INV_pp236_byimp | WF_INV_pp236_imp6_s10t20 | $-14,179 | $-10,338 | YES |
| WF_INV_pp382_imp6 | WF_INV_pp382_imp6_s8t20 | $-10,972 | $-8,084 | YES |

#### Walk-forward per-block detail under $1.91

**INV_15s_pp236** -- fixed_best=R4_INV15s_imp2_s4t12, WF_total=-44,877, Fixed_total=-55,224
- B1: picked **R4_INV15s_imp2_s4t12** (prior block $-10,347), test block $-19,370 on 9416 trades
- B2: picked **R4_INV15s_imp2_s4t12** (prior block $-19,370), test block $-16,487 on 7762 trades
- B3: picked **R4_INV15s_imp2_s4t12** (prior block $-16,487), test block $-9,021 on 4993 trades

**INV_1m_pp118** -- fixed_best=R4_INV_pp118_s4t16_imp5, WF_total=-17,987, Fixed_total=-22,476
- B1: picked **R4_INV_pp118_s5t20_imp5** (prior block $-5,506), test block $-8,022 on 3347 trades
- B2: picked **R4_INV_pp118_s4t16_imp5** (prior block $-7,206), test block $-7,942 on 3528 trades
- B3: picked **R4_INV_pp118_s4t16_imp3** (prior block $-7,548), test block $-2,023 on 1893 trades

**INV_1m_pp236** -- fixed_best=R4_INV_pp236_s10t20, WF_total=-11,229, Fixed_total=-15,734
- B1: picked **R4_INV_pp236_s10t20** (prior block $-4,504), test block $-6,383 on 2346 trades
- B2: picked **R4_INV_pp236_s10t20** (prior block $-6,383), test block $-4,382 on 2162 trades
- B3: picked **R4_INV_pp236_s10t20** (prior block $-4,382), test block $-464 on 1221 trades

**INV_1m_pp382** -- fixed_best=R4_INV_pp382_s5t20_imp5, WF_total=-8,554, Fixed_total=-12,506
- B1: picked **R4_INV_pp382_s5t20_imp5** (prior block $-3,952), test block $-3,678 on 2176 trades
- B2: picked **R4_INV_pp382_s5t20_imp5** (prior block $-3,678), test block $-3,907 on 2060 trades
- B3: picked **R4_INV_pp382_s5t20_imp5** (prior block $-3,907), test block $-969 on 1066 trades

**INV_30s_pp236** -- fixed_best=R4_INV30s_imp3_s4t12, WF_total=-28,528, Fixed_total=-36,897
- B1: picked **R4_INV30s_imp3_s4t12** (prior block $-8,369), test block $-11,479 on 6379 trades
- B2: picked **R4_INV30s_imp3_s4t12** (prior block $-11,479), test block $-10,849 on 5561 trades
- B3: picked **R4_INV30s_imp3_s4t12** (prior block $-10,849), test block $-6,200 on 3134 trades

**R7_cands** -- fixed_best=R7_VRP_v1-3_s5t15, WF_total=-316, Fixed_total=-572
- B1: picked **R7_SRR_lk20_sw8_s5t20** (prior block $-199), test block $-217 on 52 trades
- B2: picked **R7_VRP_v1-3_s5t15** (prior block $-167), test block $-22 on 69 trades
- B3: picked **R7_VRP_v1-3_s5t15** (prior block $-22), test block $-78 on 6 trades

**R8_winners** -- fixed_best=R8_B04_CANON_bal_n300_t30, WF_total=472, Fixed_total=143
- B1: picked **R8_B04_CANON_bal_n500_t50** (prior block $-171), test block $-15 on 19 trades
- B2: picked **R8_B04_CANON_bal_n300_t30** (prior block $136), test block $272 on 79 trades
- B3: picked **R8_B05_CANON_winOVR** (prior block $455), test block $215 on 122 trades

**WF_CANON_INV_236** -- fixed_best=WF_CANON_INV_236_s12t20, WF_total=-10,996, Fixed_total=-13,695
- B1: picked **WF_CANON_INV_236_s10t30** (prior block $-3,193), test block $-6,196 on 2129 trades
- B2: picked **WF_CANON_INV_236_s10t30** (prior block $-6,196), test block $-4,957 on 1960 trades
- B3: picked **WF_CANON_INV_236_s12t20** (prior block $-3,727), test block $158 on 1153 trades

**WF_INV15s_imp2** -- fixed_best=WF_INV15s_imp2_s5t20, WF_total=-26,043, Fixed_total=-33,349
- B1: picked **WF_INV15s_imp2_s5t20** (prior block $-7,305), test block $-10,302 on 6597 trades
- B2: picked **WF_INV15s_imp2_s5t20** (prior block $-10,302), test block $-10,283 on 5350 trades
- B3: picked **WF_INV15s_imp2_s5t20** (prior block $-10,283), test block $-5,458 on 3790 trades

**WF_INV30s_imp3** -- fixed_best=WF_INV30s_imp3_s5t20, WF_total=-20,644, Fixed_total=-27,707
- B1: picked **WF_INV30s_imp3_s4t16** (prior block $-7,463), test block $-10,089 on 5749 trades
- B2: picked **WF_INV30s_imp3_s5t20** (prior block $-8,597), test block $-7,754 on 4181 trades
- B3: picked **WF_INV30s_imp3_s5t20** (prior block $-7,754), test block $-2,800 on 2528 trades

**WF_INV_pp236_byimp** -- fixed_best=WF_INV_pp236_imp6_s10t20, WF_total=-10,338, Fixed_total=-14,179
- B1: picked **WF_INV_pp236_imp5_s10t20** (prior block $-3,913), test block $-6,293 on 2343 trades
- B2: picked **WF_INV_pp236_imp6_s10t20** (prior block $-6,182), test block $-3,225 on 2093 trades
- B3: picked **WF_INV_pp236_imp6_s10t20** (prior block $-3,225), test block $-820 on 1167 trades

**WF_INV_pp382_imp6** -- fixed_best=WF_INV_pp382_imp6_s8t20, WF_total=-8,084, Fixed_total=-10,972
- B1: picked **WF_INV_pp382_imp6_s8t24** (prior block $-3,299), test block $-2,844 on 1790 trades
- B2: picked **WF_INV_pp382_imp6_s6t18** (prior block $-2,675), test block $-3,910 on 1885 trades
- B3: picked **WF_INV_pp382_imp6_s8t20** (prior block $-3,141), test block $-1,331 on 929 trades

### Walk-forward under $0.74/RT fees

| Family | Fixed-best | Fixed full $ | WF total test $ | WF beats fixed? |
|---|---|---:|---:|:---:|
| INV_15s_pp236 | R4_INV15s_imp2_s4t12 | $-22,163 | $-18,937 | YES |
| INV_1m_pp118 | R4_INV_pp118_s4t16_imp3 | $-8,671 | $-5,804 | YES |
| INV_1m_pp236 | R4_INV_pp236_s10t20 | $-7,008 | $-6,196 | YES |
| INV_1m_pp382 | R4_INV_pp382_s5t20_imp5 | $-4,200 | $-4,290 | no |
| INV_30s_pp236 | R4_INV30s_imp3_s3t12 | $-13,759 | $-11,064 | YES |
| R7_cands | R7_MTF_imp6_pp382_s5t20_INV | $84 | $406 | YES |
| R8_winners | R8_C04_MTF_early_imp4_b3_s8t24_INV | $986 | $812 | no |
| WF_CANON_INV_236 | WF_CANON_INV_236_s12t20 | $-5,482 | $-4,509 | YES |
| WF_INV15s_imp2 | WF_INV15s_imp2_s5t20 | $-10,031 | $-7,631 | YES |
| WF_INV30s_imp3 | WF_INV30s_imp3_s5t20 | $-10,238 | $-6,068 | YES |
| WF_INV_pp236_byimp | WF_INV_pp236_imp6_s10t20 | $-5,834 | $-4,478 | YES |
| WF_INV_pp382_imp6 | WF_INV_pp382_imp6_s8t20 | $-4,031 | $-2,698 | YES |

#### Walk-forward per-block detail under $0.74

**INV_15s_pp236** -- fixed_best=R4_INV15s_imp2_s4t12, WF_total=-18,937, Fixed_total=-22,163
- B1: picked **R4_INV15s_imp2_s4t12** (prior block $-3,226), test block $-8,353 on 9416 trades
- B2: picked **R4_INV15s_imp2_s4t12** (prior block $-8,353), test block $-7,405 on 7762 trades
- B3: picked **R4_INV15s_imp2_s4t12** (prior block $-7,405), test block $-3,179 on 4993 trades

**INV_1m_pp118** -- fixed_best=R4_INV_pp118_s4t16_imp3, WF_total=-5,804, Fixed_total=-8,671
- B1: picked **R4_INV_pp118_s4t16_imp5** (prior block $-2,449), test block $-2,846 on 3726 trades
- B2: picked **R4_INV_pp118_s4t16_imp3** (prior block $-2,565), test block $-3,149 on 3760 trades
- B3: picked **R4_INV_pp118_s4t16_imp3** (prior block $-3,149), test block $192 on 1893 trades

**INV_1m_pp236** -- fixed_best=R4_INV_pp236_s10t20, WF_total=-6,196, Fixed_total=-7,008
- B1: picked **R4_INV_pp236_s5t20_imp5** (prior block $-2,274), test block $-4,103 on 2980 trades
- B2: picked **R4_INV_pp236_s4t16_imp5** (prior block $-3,049), test block $-3,058 on 3106 trades
- B3: picked **R4_INV_pp236_s10t20** (prior block $-1,852), test block $964 on 1221 trades

**INV_1m_pp382** -- fixed_best=R4_INV_pp382_s5t20_imp5, WF_total=-4,290, Fixed_total=-4,200
- B1: picked **R4_INV_pp382_s5t20_imp5** (prior block $-1,849), test block $-1,132 on 2176 trades
- B2: picked **R4_INV_pp382_s5t20_imp5** (prior block $-1,132), test block $-1,497 on 2060 trades
- B3: picked **R4_INV_pp382_s4t16_imp3** (prior block $-1,459), test block $-1,661 on 1298 trades

**INV_30s_pp236** -- fixed_best=R4_INV30s_imp3_s3t12, WF_total=-11,064, Fixed_total=-13,759
- B1: picked **R4_INV30s_imp3_s4t12** (prior block $-3,071), test block $-4,016 on 6379 trades
- B2: picked **R4_INV30s_imp3_s3t12** (prior block $-3,440), test block $-4,515 on 6128 trades
- B3: picked **R4_INV30s_imp3_s4t12** (prior block $-4,343), test block $-2,533 on 3134 trades

**R7_cands** -- fixed_best=R7_MTF_imp6_pp382_s5t20_INV, WF_total=406, Fixed_total=84
- B1: picked **R7_VRP_v1-3_s5t15** (prior block $-73), test block $-92 on 64 trades
- B2: picked **R7_MTF_imp6_pp382_s5t20_INV** (prior block $477), test block $604 on 725 trades
- B3: picked **R7_MTF_imp6_pp382_s5t20_INV** (prior block $604), test block $-106 on 376 trades

**R8_winners** -- fixed_best=R8_C04_MTF_early_imp4_b3_s8t24_INV, WF_total=812, Fixed_total=986
- B1: picked **R8_B04_CANON_bal_n500_t50** (prior block $-150), test block $8 on 19 trades
- B2: picked **R8_C04_MTF_early_imp4_b3_s8t24_INV** (prior block $896), test block $1,552 on 958 trades
- B3: picked **R8_C04_MTF_early_imp4_b3_s8t24_INV** (prior block $1,552), test block $-747 on 494 trades

**WF_CANON_INV_236** -- fixed_best=WF_CANON_INV_236_s12t20, WF_total=-4,509, Fixed_total=-5,482
- B1: picked **WF_CANON_INV_236_s10t30** (prior block $-1,279), test block $-3,705 on 2129 trades
- B2: picked **WF_CANON_INV_236_s5t20** (prior block $-3,461), test block $-2,310 on 2758 trades
- B3: picked **WF_CANON_INV_236_s12t20** (prior block $-1,339), test block $1,507 on 1153 trades

**WF_INV15s_imp2** -- fixed_best=WF_INV15s_imp2_s5t20, WF_total=-7,631, Fixed_total=-10,031
- B1: picked **WF_INV15s_imp2_s5t20** (prior block $-2,399), test block $-2,584 on 6597 trades
- B2: picked **WF_INV15s_imp2_s5t20** (prior block $-2,584), test block $-4,023 on 5350 trades
- B3: picked **WF_INV15s_imp2_s5t20** (prior block $-4,023), test block $-1,024 on 3790 trades

**WF_INV30s_imp3** -- fixed_best=WF_INV30s_imp3_s5t20, WF_total=-6,068, Fixed_total=-10,238
- B1: picked **WF_INV30s_imp3_s4t16** (prior block $-2,710), test block $-3,363 on 5749 trades
- B2: picked **WF_INV30s_imp3_s5t20** (prior block $-2,978), test block $-2,863 on 4181 trades
- B3: picked **WF_INV30s_imp3_s5t20** (prior block $-2,863), test block $158 on 2528 trades

**WF_INV_pp236_byimp** -- fixed_best=WF_INV_pp236_imp6_s10t20, WF_total=-4,478, Fixed_total=-5,834
- B1: picked **WF_INV_pp236_imp5_s10t20** (prior block $-1,912), test block $-3,552 on 2343 trades
- B2: picked **WF_INV_pp236_imp6_s8t20** (prior block $-3,499), test block $-1,471 on 2288 trades
- B3: picked **WF_INV_pp236_imp6_s10t20** (prior block $-776), test block $546 on 1167 trades

**WF_INV_pp382_imp6** -- fixed_best=WF_INV_pp382_imp6_s8t20, WF_total=-2,698, Fixed_total=-4,031
- B1: picked **WF_INV_pp382_imp6_s8t24** (prior block $-1,628), test block $-749 on 1790 trades
- B2: picked **WF_INV_pp382_imp6_s6t18** (prior block $-330), test block $-1,704 on 1885 trades
- B3: picked **WF_INV_pp382_imp6_s8t20** (prior block $-1,142), test block $-244 on 929 trades

## Section 4 — Regime-switching meta-strategy

Each tick we recompute (Hurst, Choppiness, Vol) -> 8-cell regime. For each cell, we pick the best strategy by per-cell P&L (min 5 trades in cell). Meta = sum of positive cell-bests.


### Meta under $1.91/RT fees

- Meta total: **$800** over 60d = $15/day
- Meta trades: 632, WR=39.1%
- Cells filled: 8/8

| Cell | Code | Best strategy | n | wr | $ |
|---:|:---:|---|---:|---:|---:|
| 0 | RDL | WF_INV15s_imp2_s4t16 | 97 | 35.1% | $206 |
| 1 | RDH | R4_INV_pp236_s5t20_imp5 | 46 | 34.8% | $163 |
| 2 | RCL | WF_INV15s_imp2_s3t12 | 27 | 48.1% | $125 |
| 3 | RCH | R4_INV_pp236_s2t12_imp3 | 6 | 33.3% | $17 |
| 4 | TDL | R8_B04_CANON_bal_n500_t50 | 15 | 53.3% | $152 |
| 5 | TDH | R8_B04_CANON_bal_n300_t30 | 135 | 41.5% | $-30 |
| 6 | TCL | R8_B04_CANON_bal_n300_t30 | 30 | 46.7% | $102 |
| 7 | TCH | R8_B02_CANON_velmin5 | 411 | 38.9% | $34 |

Cell code legend: 1st letter T=Hurst trending, R=mean-reverting; 2nd C=choppy, D=directional; 3rd H=high vol, L=low vol.

### Meta under $0.74/RT fees

- Meta total: **$2,692** over 60d = $51/day
- Meta trades: 3,118, WR=33.1%
- Cells filled: 8/8

| Cell | Code | Best strategy | n | wr | $ |
|---:|:---:|---|---:|---:|---:|
| 0 | RDL | WF_INV15s_imp2_s4t16 | 97 | 35.1% | $320 |
| 1 | RDH | R4_INV_pp236_s5t20_imp5 | 46 | 37.0% | $217 |
| 2 | RCL | WF_INV15s_imp2_s3t12 | 27 | 48.1% | $157 |
| 3 | RCH | R4_INV_pp236_s2t12_imp3 | 6 | 33.3% | $24 |
| 4 | TDL | R8_C04_MTF_early_imp4_b3_s8t24_INV | 1141 | 34.6% | $591 |
| 5 | TDH | R8_B04_CANON_bal_n300_t30 | 135 | 41.5% | $128 |
| 6 | TCL | R4_INV_pp382_s5t20_imp5 | 1079 | 27.9% | $629 |
| 7 | TCH | WF_CANON_INV_236_s10t30 | 587 | 36.3% | $627 |

Cell code legend: 1st letter T=Hurst trending, R=mean-reverting; 2nd C=choppy, D=directional; 3rd H=high vol, L=low vol.

## Section 5 — NQ economics (10x point value, same fees)

### Top 10 under $1.91 NQ

| Rank | Strategy | Tr/d | WR% | $/day | maxDD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|
| 1 | R8_C04_MTF_early_imp4_b3_s8t24_INV | 62.8 | 33.9 | $531 | $8,384 | 0.23 |
| 2 | R7_MTF_imp6_pp382_s5t20_INV | 47.2 | 26.3 | $275 | $7,660 | 0.21 |
| 3 | WF_INV15s_imp2_s5t20 | 376.0 | 24.5 | $172 | $25,317 | 0.05 |
| 4 | R8_B04_CANON_bal_n300_t30 | 5.5 | 41.2 | $121 | $3,964 | 0.25 |
| 5 | R8_B05_CANON_winOVR | 18.3 | 36.1 | $90 | $13,073 | 0.08 |
| 6 | R8_E01_CANON_OVR_INV_236 | 18.0 | 35.6 | $55 | $13,786 | 0.05 |
| 7 | R8_E01_CANON_NYO_INV_236 | 14.2 | 35.4 | $26 | $11,395 | 0.03 |
| 8 | R8_B04_CANON_bal_n500_t50 | 1.4 | 37.3 | $5 | $2,091 | 0.02 |
| 9 | R8_B04_CANON_bal_n200_t20 | 12.6 | 37.2 | $2 | $6,810 | 0.00 |
| 10 | R7_VRP_v1-3_s5t15 | 6.4 | 38.9 | $1 | $3,556 | 0.00 |

### Top 10 under $0.74 NQ

| Rank | Strategy | Tr/d | WR% | $/day | maxDD | Sharpe |
|---:|---|---:|---:|---:|---:|---:|
| 1 | WF_INV15s_imp2_s5t20 | 376.0 | 24.5 | $612 | $22,903 | 0.18 |
| 2 | R8_C04_MTF_early_imp4_b3_s8t24_INV | 62.8 | 33.9 | $605 | $7,788 | 0.26 |
| 3 | R7_MTF_imp6_pp382_s5t20_INV | 47.2 | 26.3 | $330 | $6,946 | 0.26 |
| 4 | WF_INV30s_imp3_s4t16 | 333.6 | 23.9 | $143 | $17,378 | 0.04 |
| 5 | R8_B04_CANON_bal_n300_t30 | 5.5 | 41.2 | $128 | $3,898 | 0.26 |
| 6 | R8_B05_CANON_winOVR | 18.3 | 36.1 | $112 | $12,506 | 0.10 |
| 7 | R4_INV_pp382_s5t20_imp5 | 133.9 | 25.6 | $100 | $16,883 | 0.04 |
| 8 | R4_INV30s_imp3_s3t12 | 403.7 | 23.8 | $92 | $19,896 | 0.04 |
| 9 | R8_E01_CANON_OVR_INV_236 | 18.0 | 35.6 | $76 | $13,297 | 0.07 |
| 10 | WF_INV_pp382_imp6_s6t18 | 122.6 | 30.1 | $54 | $14,768 | 0.02 |

## Section 6 — Constraint relaxation analysis

For each (volume-tier, WR-tier) cell, the highest $/day variant across the 60d period. Annual = $/day * 252.


### Under $1.91/RT fees

| Vol bin | WR-min | Best strategy | Tr/d | WR% | $/day | $/yr | maxDD |
|---|---:|---|---:|---:|---:|---:|---:|
| 50-100 | 0.45 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.46 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.47 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.50 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.55 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.45 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.46 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.47 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.50 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.55 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.45 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.46 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.47 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.50 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.55 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.45 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.46 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.47 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.50 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.55 | (no candidates) | - | - | - | - | - |

### Under $0.74/RT fees

| Vol bin | WR-min | Best strategy | Tr/d | WR% | $/day | $/yr | maxDD |
|---|---:|---|---:|---:|---:|---:|---:|
| 50-100 | 0.45 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.46 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.47 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.50 | (no candidates) | - | - | - | - | - |
| 50-100 | 0.55 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.45 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.46 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.47 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.50 | (no candidates) | - | - | - | - | - |
| 100-200 | 0.55 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.45 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.46 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.47 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.50 | (no candidates) | - | - | - | - | - |
| 200-300 | 0.55 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.45 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.46 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.47 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.50 | (no candidates) | - | - | - | - | - |
| 300-+inf | 0.55 | (no candidates) | - | - | - | - | - |

## Section 8 — Round 10 recommendation


Lever ranking by best $/day (MNQ-equivalent):

- **prop-firm NQ $0.74**: $61/day
- **baseline NQ $1.91**: $53/day
- **meta-regime MNQ $0.74**: $51/day
- **prop-firm MNQ $0.74**: $19/day
- **meta-regime MNQ $1.91**: $15/day
- **baseline MNQ $1.91**: $3/day

Walk-forward best family lift: $4,170 (WF_INV30s_imp3)

**ROUND 10 should attack the top lever exclusively** with a focused parameter sweep around its optimum.

## Section 9 — Full strategy table (sorted by $/day at $1.91)

| Strategy | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/tr 191 | maxDD 191 | Sharpe 191 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R8_B04_CANON_bal_n300_t30 | 291 | 5.5 | 41.2 | $3 | $9 | $0.49 | $493 | 0.06 |
| R8_B04_CANON_bal_n500_t50 | 75 | 1.4 | 37.3 | $-2 | $-0 | $-1.38 | $319 | -0.07 |
| R7_VRP_v1-3_s5t15 | 337 | 6.4 | 37.1 | $-11 | $-3 | $-1.70 | $799 | -0.30 |
| R7_SRR_lk20_sw8_s5t20 | 151 | 2.8 | 17.2 | $-12 | $-9 | $-4.24 | $690 | -0.47 |
| R8_B04_CANON_bal_n200_t20 | 667 | 12.6 | 37.0 | $-21 | $-7 | $-1.70 | $1,606 | -0.25 |
| R8_E01_CANON_NYO_INV_236 | 755 | 14.2 | 35.4 | $-22 | $-5 | $-1.53 | $1,814 | -0.22 |
| R8_B05_CANON_winOVR | 972 | 18.3 | 36.0 | $-23 | $-1 | $-1.23 | $2,204 | -0.20 |
| R8_B05_CANON_winNYO | 746 | 14.1 | 35.0 | $-25 | $-9 | $-1.78 | $2,118 | -0.24 |
| R8_E01_CANON_OVR_INV_236 | 954 | 18.0 | 35.5 | $-25 | $-4 | $-1.41 | $2,131 | -0.23 |
| R7_MTF_imp6_pp382_s5t20_INV | 2,501 | 47.2 | 25.9 | $-54 | $2 | $-1.14 | $2,938 | -0.43 |
| R8_C04_MTF_early_imp4_b3_s8t24_INV | 3,330 | 62.8 | 33.1 | $-55 | $19 | $-0.87 | $3,018 | -0.24 |
| R8_E01_CANON_RTH_INV_236 | 2,435 | 45.9 | 35.7 | $-87 | $-33 | $-1.89 | $5,495 | -0.49 |
| R8_B02_CANON_velmin5 | 4,010 | 75.7 | 35.8 | $-152 | $-63 | $-2.01 | $8,574 | -0.50 |
| WF_INV_pp382_imp6_s8t20 | 5,933 | 111.9 | 33.8 | $-207 | $-76 | $-1.85 | $11,165 | -0.83 |
| WF_INV_pp382_imp6_s8t24 | 5,789 | 109.2 | 31.7 | $-218 | $-90 | $-1.99 | $11,754 | -0.85 |
| WF_INV_pp382_imp6_s6t18 | 6,496 | 122.6 | 29.7 | $-220 | $-76 | $-1.79 | $11,857 | -0.90 |
| WF_INV_pp382_imp6_s5t20 | 6,635 | 125.2 | 24.9 | $-228 | $-82 | $-1.82 | $12,197 | -0.94 |
| R4_INV_pp382_s5t20_imp5 | 7,099 | 133.9 | 25.2 | $-236 | $-79 | $-1.76 | $12,576 | -0.95 |
| WF_CANON_INV_236_s12t20 | 7,020 | 132.5 | 40.8 | $-258 | $-103 | $-1.95 | $14,165 | -0.63 |
| WF_INV_pp382_imp6_s5t15 | 6,990 | 131.9 | 28.3 | $-265 | $-111 | $-2.01 | $14,155 | -1.23 |
| WF_INV_pp382_imp6_s8t16 | 6,184 | 116.7 | 36.0 | $-267 | $-130 | $-2.29 | $14,317 | -0.99 |
| WF_INV_pp236_imp6_s10t20 | 7,133 | 134.6 | 37.3 | $-268 | $-110 | $-1.99 | $14,315 | -0.71 |
| WF_CANON_INV_236_s10t30 | 6,825 | 128.8 | 33.4 | $-280 | $-129 | $-2.17 | $15,118 | -0.72 |
| WF_INV_pp382_imp6_s4t12 | 7,594 | 143.3 | 27.9 | $-281 | $-114 | $-1.96 | $15,051 | -1.34 |
| WF_INV_pp236_imp5_s10t20 | 7,421 | 140.0 | 37.4 | $-285 | $-121 | $-2.04 | $15,268 | -0.76 |
| WF_INV_pp382_imp6_s3t12 | 7,794 | 147.1 | 23.2 | $-287 | $-115 | $-1.95 | $15,354 | -1.45 |
| WF_CANON_INV_236_s10t20 | 7,452 | 140.6 | 37.3 | $-290 | $-126 | $-2.06 | $15,776 | -0.69 |
| R4_INV_pp236_s10t20 | 7,458 | 140.7 | 37.2 | $-297 | $-132 | $-2.11 | $16,042 | -0.74 |
| WF_CANON_INV_236_s10t25 | 7,055 | 133.1 | 34.8 | $-300 | $-144 | $-2.25 | $16,049 | -0.73 |
| WF_INV_pp382_imp6_s4t16 | 7,184 | 135.5 | 22.9 | $-304 | $-146 | $-2.25 | $16,285 | -1.32 |
| WF_INV_pp236_imp6_s8t20 | 7,771 | 146.6 | 32.7 | $-311 | $-140 | $-2.12 | $16,749 | -0.86 |
| WF_CANON_INV_236_s8t20 | 8,030 | 151.5 | 33.0 | $-312 | $-134 | $-2.06 | $16,686 | -0.85 |
| WF_CANON_INV_236_s12t24 | 6,724 | 126.9 | 38.1 | $-313 | $-164 | $-2.47 | $17,144 | -0.70 |
| WF_INV_pp236_imp8_s8t24 | 6,753 | 127.4 | 29.9 | $-314 | $-164 | $-2.46 | $16,804 | -0.92 |
| R4_INV_pp382_s5t20_imp3 | 8,018 | 151.3 | 24.7 | $-317 | $-140 | $-2.10 | $16,913 | -1.26 |
| WF_CANON_INV_236_s10t15 | 8,079 | 152.4 | 42.0 | $-320 | $-141 | $-2.10 | $17,226 | -0.92 |
| WF_INV_pp236_imp5_s8t20 | 8,061 | 152.1 | 32.9 | $-327 | $-149 | $-2.15 | $17,509 | -0.88 |
| WF_CANON_INV_236_s8t24 | 7,747 | 146.2 | 30.7 | $-343 | $-172 | $-2.35 | $18,307 | -0.88 |
| WF_CANON_INV_236_s8t16 | 8,557 | 161.5 | 36.1 | $-345 | $-156 | $-2.13 | $18,486 | -1.02 |
| WF_INV_pp236_imp4_s8t16 | 8,856 | 167.1 | 36.0 | $-351 | $-155 | $-2.10 | $18,819 | -1.05 |
| WF_INV_pp236_imp6_s8t16 | 8,228 | 155.2 | 35.8 | $-351 | $-170 | $-2.26 | $18,881 | -1.06 |
| WF_INV_pp236_imp4_s8t20 | 8,325 | 157.1 | 32.6 | $-355 | $-171 | $-2.26 | $18,923 | -0.99 |
| WF_INV_pp236_imp5_s8t16 | 8,546 | 161.2 | 35.9 | $-356 | $-168 | $-2.21 | $19,121 | -1.01 |
| R4_INV_pp382_s4t16_imp3 | 8,987 | 169.6 | 23.3 | $-364 | $-165 | $-2.14 | $19,384 | -1.48 |
| WF_CANON_INV_236_s5t20 | 9,397 | 177.3 | 24.3 | $-369 | $-162 | $-2.08 | $19,943 | -1.12 |
| R4_INV_pp236_s5t20_imp5 | 9,399 | 177.3 | 24.2 | $-374 | $-167 | $-2.11 | $20,120 | -1.09 |
| WF_CANON_INV_236_s5t15 | 10,055 | 189.7 | 27.8 | $-411 | $-189 | $-2.17 | $22,255 | -1.25 |
| R4_INV_pp236_s5t20_imp3 | 10,133 | 191.2 | 24.2 | $-419 | $-195 | $-2.19 | $22,362 | -1.17 |
| R4_INV_pp118_s4t16_imp5 | 11,711 | 221.0 | 23.6 | $-424 | $-166 | $-1.92 | $22,670 | -1.16 |
| R4_INV_pp236_s4t16_imp5 | 10,483 | 197.8 | 23.0 | $-426 | $-194 | $-2.15 | $22,846 | -1.41 |
| R4_INV_pp118_s5t20_imp5 | 10,487 | 197.9 | 24.0 | $-431 | $-200 | $-2.18 | $23,047 | -1.20 |
| R4_INV_pp118_s4t16_imp3 | 12,656 | 238.8 | 23.9 | $-443 | $-164 | $-1.86 | $23,598 | -1.26 |
| R4_INV_pp236_s4t16_imp3 | 11,496 | 216.9 | 23.3 | $-463 | $-209 | $-2.13 | $24,707 | -1.41 |
| R4_INV_pp236_s3t15_imp3 | 12,489 | 235.6 | 19.9 | $-487 | $-211 | $-2.07 | $25,938 | -1.71 |
| R4_INV_pp118_s5t20_imp3 | 11,161 | 210.6 | 23.8 | $-489 | $-242 | $-2.32 | $25,968 | -1.31 |
| R4_INV_pp236_s3t12_imp3 | 13,192 | 248.9 | 23.1 | $-511 | $-219 | $-2.05 | $27,254 | -1.66 |
| WF_INV30s_imp3_s5t20 | 14,931 | 281.7 | 24.3 | $-523 | $-193 | $-1.86 | $28,003 | -1.13 |
| R4_INV_pp118_s2t12_imp5 | 13,758 | 259.6 | 17.7 | $-528 | $-224 | $-2.03 | $27,991 | -1.69 |
| R4_INV_pp236_s2t12_imp3 | 14,109 | 266.2 | 17.7 | $-540 | $-228 | $-2.03 | $28,713 | -1.81 |
| R4_INV_pp118_s3t15_imp3 | 13,847 | 261.3 | 19.7 | $-550 | $-244 | $-2.11 | $29,166 | -1.57 |
| R4_INV_pp118_s3t12_imp3 | 14,484 | 273.3 | 23.0 | $-563 | $-243 | $-2.06 | $29,875 | -1.78 |
| R4_INV_pp118_s2t12_imp3 | 15,360 | 289.8 | 17.6 | $-596 | $-256 | $-2.06 | $31,567 | -1.80 |
| WF_INV30s_imp3_s4t16 | 17,681 | 333.6 | 23.8 | $-598 | $-208 | $-1.79 | $31,892 | -1.34 |
| R4_INV_pp118_s3t9_imp3 | 15,153 | 285.9 | 27.7 | $-612 | $-277 | $-2.14 | $32,414 | -1.84 |
| WF_INV30s_imp3_s5t15 | 16,637 | 313.9 | 28.1 | $-614 | $-247 | $-1.96 | $32,566 | -1.33 |
| WF_INV15s_imp2_s5t20 | 19,930 | 376.0 | 24.2 | $-629 | $-189 | $-1.67 | $33,416 | -1.26 |
| R4_INV_pp118_s2t10_imp3 | 15,801 | 298.1 | 19.9 | $-633 | $-284 | $-2.12 | $33,581 | -1.88 |
| R4_INV30s_imp3_s4t12 | 19,602 | 369.8 | 28.2 | $-696 | $-263 | $-1.88 | $36,940 | -1.74 |
| WF_INV30s_imp3_s4t12 | 19,597 | 369.8 | 28.2 | $-702 | $-269 | $-1.90 | $37,233 | -1.64 |
| WF_INV30s_imp3_s3t15 | 19,919 | 375.8 | 20.1 | $-715 | $-275 | $-1.90 | $37,924 | -1.51 |
| R4_INV30s_imp3_s3t12 | 21,395 | 403.7 | 23.7 | $-732 | $-260 | $-1.81 | $38,843 | -1.73 |
| WF_INV30s_imp3_s3t12 | 21,343 | 402.7 | 23.6 | $-744 | $-273 | $-1.85 | $39,514 | -1.67 |
| WF_INV15s_imp2_s5t15 | 22,980 | 433.6 | 28.2 | $-795 | $-288 | $-1.83 | $42,332 | -1.40 |
| WF_INV30s_imp3_s3t9 | 23,237 | 438.4 | 28.6 | $-837 | $-324 | $-1.91 | $44,370 | -1.86 |
| WF_INV15s_imp2_s4t16 | 24,677 | 465.6 | 23.4 | $-871 | $-326 | $-1.87 | $46,296 | -1.43 |
| R4_INV30s_imp3_s3t9 | 23,183 | 437.4 | 28.3 | $-871 | $-359 | $-1.99 | $46,154 | -1.95 |
| WF_INV30s_imp3_s2t10 | 24,700 | 466.0 | 20.5 | $-901 | $-355 | $-1.93 | $47,728 | -1.85 |
| R4_INV30s_imp3_s2t10 | 24,650 | 465.1 | 20.5 | $-901 | $-357 | $-1.94 | $47,748 | -1.93 |
| WF_INV30s_imp3_s2t8 | 25,829 | 487.3 | 24.3 | $-941 | $-371 | $-1.93 | $49,897 | -1.98 |
| WF_INV15s_imp2_s4t12 | 28,281 | 533.6 | 27.9 | $-1,042 | $-417 | $-1.95 | $55,386 | -1.61 |
| R4_INV15s_imp2_s4t12 | 28,257 | 533.2 | 27.9 | $-1,042 | $-418 | $-1.95 | $55,358 | -1.60 |
| WF_INV15s_imp2_s3t15 | 28,915 | 545.6 | 19.9 | $-1,057 | $-418 | $-1.94 | $56,057 | -1.61 |
| R4_INV15s_imp2_s3t12 | 31,773 | 599.5 | 23.3 | $-1,153 | $-451 | $-1.92 | $61,162 | -1.65 |
| WF_INV15s_imp2_s3t12 | 31,752 | 599.1 | 23.2 | $-1,155 | $-454 | $-1.93 | $61,305 | -1.70 |
| WF_INV15s_imp2_s2t12 | 36,438 | 687.5 | 18.0 | $-1,296 | $-491 | $-1.88 | $68,686 | -1.79 |
| WF_INV15s_imp2_s3t9 | 35,680 | 673.2 | 28.5 | $-1,301 | $-514 | $-1.93 | $69,010 | -1.85 |
| R4_INV15s_imp2_s3t9 | 35,668 | 673.0 | 28.3 | $-1,329 | $-542 | $-1.98 | $70,502 | -1.88 |
| WF_INV15s_imp2_s2t10 | 38,990 | 735.7 | 20.6 | $-1,413 | $-552 | $-1.92 | $74,956 | -1.89 |
| R4_INV15s_imp2_s2t10 | 39,034 | 736.5 | 20.4 | $-1,447 | $-586 | $-1.97 | $76,795 | -1.90 |
| WF_INV15s_imp2_s2t8 | 42,022 | 792.9 | 24.1 | $-1,564 | $-636 | $-1.97 | $82,921 | -1.95 |
| R4_INV15s_imp2_s2t8 | 42,076 | 793.9 | 24.1 | $-1,565 | $-636 | $-1.97 | $82,961 | -1.97 |

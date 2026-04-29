# Strategy Discovery — Full Report

Generated: 2026-04-29T00:07:10.265324+00:00

## Sources

  - **validated_v3_8yr.json**: 12 patterns validated, perms=500, MC=10000
  - **validated_v3_8yr_wide.json**: missing
  - **validated_v3_xa.json**: missing
  - **validated_long_rr25.json**: missing
  - **validated_long_rr30.json**: missing
  - **validated_long_rr40.json**: missing
  - **validated_v3_long_top60.json**: 60 patterns validated, perms=200, MC=10000

## Bucketing rules

  - **Tier A** (live, gold standard): WR ≥ 60% AND R:R ≥ 1:2 AND passes ALL 5 rigor tests
    (EV, 500-permutation, walk-forward CPCV, 10k Monte-Carlo, ±20% sensitivity)
  - **Tier B** (live, lower-WR): positive EV AND passes ≥3/5 tests AND walk-forward + permutation pass
    Sub-60% WR but profitable due to 1:2 R:R; sized at 5 MNQ same as Tier A
  - **Reject**: negative EV, or fails permutation/walk-forward

## Tier A — Live-ready (2 strategies)

| Name | Side | WR | PF | Trades | Net P&L | Perm p |
|---|---|---|---|---|---|---|
| V3_LONG_S20T50_55 | LONG | 60.8% | 2.83 | 4497 | $+721,368 | 0.0050 |
| V3_SHORT_S15T30_05 | SHORT | 60.3% | 2.39 | 2746 | $+264,845 | 0.0020 |

## Tier B — Watchlist (42 strategies)

| Name | Side | WR | PF | Trades | Net P&L | Tests |
|---|---|---|---|---|---|---|
| V3_LONG_S20T60_07 | LONG | 45.8% | 2.01 | 24131 | $+3,033,940 | 5/5 |
| V3_LONG_S20T50_05 | LONG | 47.3% | 1.78 | 23825 | $+2,220,895 | 5/5 |
| V3_LONG_S20T60_59 | LONG | 56.7% | 2.83 | 6626 | $+1,184,098 | 5/5 |
| V3_LONG_S15T37_10 | LONG | 45.4% | 1.56 | 17616 | $+958,618 | 5/5 |
| V3_LONG_S20T50_21 | LONG | 73.7% | 5.51 | 3503 | $+935,482 | 4/5 |
| V3_LONG_S20T50_12 | LONG | 74.8% | 5.67 | 3229 | $+853,558 | 4/5 |
| V3_LONG_S20T60_37 | LONG | 40.3% | 1.62 | 9653 | $+821,432 | 5/5 |
| V3_LONG_S20T60_32 | LONG | 39.8% | 1.58 | 9677 | $+773,005 | 5/5 |
| V3_LONG_S20T50_08 | LONG | 49.3% | 2.00 | 5808 | $+668,592 | 5/5 |
| V3_LONG_S20T60_11 | LONG | 42.1% | 1.77 | 5844 | $+592,968 | 5/5 |
| V3_LONG_S20T50_23 | LONG | 45.6% | 1.71 | 6623 | $+584,910 | 5/5 |
| V3_LONG_S15T45_31 | LONG | 64.7% | 4.21 | 2781 | $+558,615 | 4/5 |
| V3_LONG_S20T60_34 | LONG | 69.0% | 5.44 | 1760 | $+550,800 | 4/5 |
| V3_LONG_S15T45_09 | LONG | 39.9% | 1.50 | 9432 | $+506,332 | 5/5 |
| V3_LONG_S15T60_15 | LONG | 39.2% | 2.01 | 4433 | $+491,462 | 5/5 |
| V3_LONG_S20T60_20 | LONG | 78.5% | 8.76 | 1209 | $+455,892 | 4/5 |
| V3_LONG_S20T50_43 | LONG | 50.0% | 2.02 | 3915 | $+454,845 | 5/5 |
| V3_LONG_S15T37_06 | LONG | 42.9% | 1.42 | 9829 | $+424,702 | 5/5 |
| V3_LONG_S20T60_27 | LONG | 70.3% | 5.52 | 1345 | $+405,268 | 4/5 |
| V3_LONG_S15T30_04 | LONG | 96.7% | 46.73 | 1237 | $+337,490 | 4/5 |
| V3_LONG_S15T45_49 | LONG | 70.5% | 5.17 | 1462 | $+318,812 | 4/5 |
| V3_LONG_S20T50_61 | LONG | 72.6% | 5.27 | 1126 | $+293,090 | 4/5 |
| V3_LONG_S12T36_16 | LONG | 93.7% | 34.43 | 917 | $+290,820 | 4/5 |
| V3_LONG_S12T30_38 | LONG | 67.2% | 3.79 | 1552 | $+212,208 | 4/5 |
| V3_LONG_S15T37_64 | LONG | 49.7% | 1.92 | 2488 | $+206,040 | 5/5 |
| V3_LONG_S10T30_35 | LONG | 40.7% | 1.44 | 6060 | $+204,325 | 5/5 |
| V3_LONG_S12T36_57 | LONG | 40.5% | 1.55 | 4093 | $+200,218 | 5/5 |
| V3_LONG_S15T37_33 | LONG | 84.5% | 10.57 | 600 | $+159,695 | 4/5 |
| PDH_TOUCH | SHORT | 53.8% | 1.74 | 442 | $+153,150 | 5/5 |
| V3_LONG_S12T24_03 | LONG | 59.2% | 2.08 | 1957 | $+125,142 | 5/5 |
| V3_LONG_S10T30_28 | LONG | 45.5% | 1.80 | 2146 | $+121,298 | 5/5 |
| V3_LONG_S12T30_63 | LONG | 42.6% | 1.40 | 3329 | $+112,940 | 5/5 |
| V3_LONG_S10T25_56 | LONG | 44.2% | 1.34 | 4129 | $+102,700 | 5/5 |
| V3_LONG_S12T30_29 | LONG | 44.2% | 1.41 | 2909 | $+98,238 | 5/5 |
| V3_SHORT_S15T30_08 | SHORT | 52.6% | 1.68 | 1501 | $+82,908 | 5/5 |
| V3_SHORT_S15T30_07 | SHORT | 51.8% | 1.71 | 1267 | $+77,912 | 5/5 |
| V3_SHORT_S12T24_04 | SHORT | 48.7% | 1.37 | 2271 | $+63,805 | 5/5 |
| V3_LONG_S8T16_02 | LONG | 48.9% | 1.22 | 3821 | $+46,762 | 4/5 |
| V3_SHORT_S10T20_02 | SHORT | 48.6% | 1.25 | 2517 | $+40,258 | 5/5 |
| V3_SHORT_S10T20_03 | SHORT | 50.0% | 1.39 | 1493 | $+36,852 | 5/5 |
| V3_LONG_S10T30_60 | LONG | 34.2% | 1.16 | 2486 | $+34,388 | 5/5 |
| V3_SHORT_S8T16_01 | SHORT | 47.7% | 1.13 | 3208 | $+23,448 | 5/5 |

## Rejected (56 patterns)

| Name | Side | WR | Tests | Failed |
|---|---|---|---|---|
| V3_SHORT_S15T30_06 | SHORT | 56.0% | 4/5 | walk_forward |
| WR_SHORT_T15S12_10 | SHORT | 55.2% | 5/5 | - |
| WR_SHORT_T15S10_06 | SHORT | 54.5% | 5/5 | - |
| WR_SHORT_T12S10_03 | SHORT | 52.8% | 2/5 | ev, permutation, monte_carlo |
| WR_LONG_T15S12_08 | LONG | 50.0% | 2/5 | ev, permutation, monte_carlo |
| WR_SHORT_T15S10_07 | SHORT | 47.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_LONG_T12S10_01 | LONG | 46.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T20S10_13 | SHORT | 45.9% | 4/5 | walk_forward |
| WR_SHORT_T10S8_16 | SHORT | 44.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S8T20_47 | LONG | 43.1% | 4/5 | permutation |
| GAP_FILL_SHORT | SHORT | 43.0% | 3/5 | walk_forward, monte_carlo |
| V3_LONG_S10T25_24 | LONG | 41.7% | 4/5 | permutation |
| V3_LONG_S12T30_25 | LONG | 41.7% | 4/5 | permutation |
| WR_LONG_T10S8_14 | LONG | 41.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S15T37_26 | LONG | 40.5% | 4/5 | permutation |
| V3_LONG_S12T30_17 | LONG | 40.1% | 4/5 | permutation |
| GAP_FILL_LONG | LONG | 40.0% | 3/5 | walk_forward, monte_carlo |
| WR_LONG_T15S10_04 | LONG | 39.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_LONG_T20S10_11 | LONG | 39.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T15S12_09 | SHORT | 38.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S12T36_42 | LONG | 38.5% | 4/5 | permutation |
| WR_SHORT_T20S10_12 | SHORT | 38.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S12T36_36 | LONG | 38.2% | 4/5 | permutation |
| V3_LONG_S10T25_39 | LONG | 37.9% | 3/5 | permutation, monte_carlo |
| V3_LONG_S15T45_22 | LONG | 37.3% | 4/5 | permutation |
| V3_LONG_S15T45_46 | LONG | 36.6% | 4/5 | permutation |
| WR_SHORT_T15S10_05 | SHORT | 36.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S8T20_50 | LONG | 35.3% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S15T60_14 | LONG | 35.2% | 4/5 | permutation |
| V3_LONG_S10T40_19 | LONG | 34.9% | 4/5 | permutation |
| WR_SHORT_T12S10_02 | SHORT | 34.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S6T12_01 | LONG | 34.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S12T48_13 | LONG | 34.1% | 4/5 | permutation |
| V3_LONG_S8T20_30 | LONG | 33.3% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S10T25_40 | LONG | 33.2% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S12T30_44 | LONG | 32.5% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S10T30_62 | LONG | 32.5% | 3/5 | permutation, monte_carlo |
| VOL_COMP_LONG | LONG | 31.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T10S8_15 | SHORT | 31.5% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| ZSCORE_LONG | LONG | 30.9% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S10T30_48 | LONG | 30.9% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S8T20_53 | LONG | 30.9% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S12T48_18 | LONG | 30.8% | 4/5 | permutation |
| V3_LONG_S12T36_54 | LONG | 30.7% | 3/5 | permutation, monte_carlo |
| V3_LONG_S8T24_51 | LONG | 30.3% | 2/5 | ev, permutation, monte_carlo |
| VOL_COMP_SHORT | SHORT | 30.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| ZSCORE_SHORT | SHORT | 29.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VWAP_REJECT_SHORT | SHORT | 29.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VWAP_RECLAIM_LONG | LONG | 28.7% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| EQ50_LONG | LONG | 28.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S8T24_52 | LONG | 27.4% | 2/5 | ev, permutation, monte_carlo |
| EQ50_SHORT | SHORT | 27.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S6T18_41 | LONG | 26.3% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S6T15_58 | LONG | 25.8% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S6T18_45 | LONG | 20.8% | 2/5 | ev, permutation, monte_carlo |
| PDL_TOUCH | SHORT | 11.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
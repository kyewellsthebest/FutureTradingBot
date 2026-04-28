# Strategy Discovery — Full Report

Generated: 2026-04-28T23:01:43.907644+00:00

## Sources

  - **validated_v3_8yr.json**: 12 patterns validated, perms=500, MC=10000
  - **validated_v3_8yr_wide.json**: missing
  - **validated_v3_xa.json**: missing

## Bucketing rules

  - **Tier A** (live, gold standard): WR ≥ 60% AND R:R ≥ 1:2 AND passes ALL 5 rigor tests
    (EV, 500-permutation, walk-forward CPCV, 10k Monte-Carlo, ±20% sensitivity)
  - **Tier B** (live, lower-WR): positive EV AND passes ≥3/5 tests AND walk-forward + permutation pass
    Sub-60% WR but profitable due to 1:2 R:R; sized at 5 MNQ same as Tier A
  - **Reject**: negative EV, or fails permutation/walk-forward

## Tier A — Live-ready (1 strategies)

| Name | Side | WR | PF | Trades | Net P&L | Perm p |
|---|---|---|---|---|---|---|
| V3_SHORT_S15T30_05 | SHORT | 60.3% | 2.39 | 2746 | $+264,845 | 0.0020 |

## Tier B — Watchlist (12 strategies)

| Name | Side | WR | PF | Trades | Net P&L | Tests |
|---|---|---|---|---|---|---|
| V3_LONG_S15T30_04 | LONG | 96.7% | 46.73 | 1237 | $+337,490 | 4/5 |
| PDH_TOUCH | SHORT | 53.8% | 1.74 | 442 | $+153,150 | 5/5 |
| WR_SHORT_T15S12_10 | SHORT | 55.2% | 1.23 | 14411 | $+131,975 | 5/5 |
| V3_LONG_S12T24_03 | LONG | 59.2% | 2.08 | 1957 | $+125,142 | 5/5 |
| WR_SHORT_T15S10_06 | SHORT | 54.5% | 1.18 | 12664 | $+91,818 | 5/5 |
| V3_SHORT_S15T30_08 | SHORT | 52.6% | 1.68 | 1501 | $+82,908 | 5/5 |
| V3_SHORT_S15T30_07 | SHORT | 51.8% | 1.71 | 1267 | $+77,912 | 5/5 |
| V3_SHORT_S12T24_04 | SHORT | 48.7% | 1.37 | 2271 | $+63,805 | 5/5 |
| V3_LONG_S8T16_02 | LONG | 48.9% | 1.22 | 3821 | $+46,762 | 4/5 |
| V3_SHORT_S10T20_02 | SHORT | 48.6% | 1.25 | 2517 | $+40,258 | 5/5 |
| V3_SHORT_S10T20_03 | SHORT | 50.0% | 1.39 | 1493 | $+36,852 | 5/5 |
| V3_SHORT_S8T16_01 | SHORT | 47.7% | 1.13 | 3208 | $+23,448 | 5/5 |

## Rejected (27 patterns)

| Name | Side | WR | Tests | Failed |
|---|---|---|---|---|
| V3_SHORT_S15T30_06 | SHORT | 56.0% | 4/5 | walk_forward |
| WR_SHORT_T12S10_03 | SHORT | 52.8% | 2/5 | ev, permutation, monte_carlo |
| WR_LONG_T15S12_08 | LONG | 50.0% | 2/5 | ev, permutation, monte_carlo |
| WR_SHORT_T15S10_07 | SHORT | 47.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_LONG_T12S10_01 | LONG | 46.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T20S10_13 | SHORT | 45.9% | 4/5 | walk_forward |
| WR_SHORT_T10S8_16 | SHORT | 44.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| GAP_FILL_SHORT | SHORT | 43.0% | 3/5 | walk_forward, monte_carlo |
| WR_LONG_T10S8_14 | LONG | 41.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| GAP_FILL_LONG | LONG | 40.0% | 3/5 | walk_forward, monte_carlo |
| WR_LONG_T15S10_04 | LONG | 39.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_LONG_T20S10_11 | LONG | 39.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T15S12_09 | SHORT | 38.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T20S10_12 | SHORT | 38.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T15S10_05 | SHORT | 36.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T12S10_02 | SHORT | 34.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S6T12_01 | LONG | 34.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VOL_COMP_LONG | LONG | 31.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T10S8_15 | SHORT | 31.5% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| ZSCORE_LONG | LONG | 30.9% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VOL_COMP_SHORT | SHORT | 30.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| ZSCORE_SHORT | SHORT | 29.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VWAP_REJECT_SHORT | SHORT | 29.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VWAP_RECLAIM_LONG | LONG | 28.7% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| EQ50_LONG | LONG | 28.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| EQ50_SHORT | SHORT | 27.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| PDL_TOUCH | SHORT | 11.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
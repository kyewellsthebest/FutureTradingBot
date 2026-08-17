# Does any NON-PRICE data predict NQ at multi-day horizons?

Every hypothesis in the ledger read the price path, and every one was intraday. Both are the wrong end of the problem:

| horizon | sigma (MNQ $) | cost | IC needed |
|---|---|---|---|
| 10 min | $46 | $1.83 | 0.040 |
| 4 hours | $354 | $1.83 | 0.005 |
| 1 day | $428 | $1.83 | 0.0043 |
| 5 days | $957 | $1.83 | 0.0019 |

At ten minutes the bar is 0.040 and everything measured today came in under it. At a week it is **0.0019** -- twenty times lower. Book imbalance measures 0.0425, eight times what a daily horizon needs, and fails only because it decays inside five minutes. **A weak but persistent signal beats a strong one that evaporates.**

818 trading days. Every series lagged by its real publication delay -- DTS and FRED by 2 days, GEX by 1 -- because point-in-time discipline is where this kind of study usually dies. `floor` is the standard deviation of the same IC with the feature rolled +-30/60/90 days: that keeps each series' autocorrelation and destroys only the alignment, which is the harder bar, since two trending series survive shuffling but not the roll.

| feature | horizon | IC | roll floor | IC/floor | shuffled | edge $ | vs $1.83 cost |
|---|---|---|---|---|---|---|---|
| gex_SPX | 5d | -0.1853 | 0.0574 | **3.2** | -0.0026 | $204.70 | $+202.87 |
| gex_SPX | 10d | -0.1848 | 0.0666 | **2.8** | -0.0495 | $276.09 | $+274.26 |
| fred_VXV | 5d | +0.1805 | 0.0705 | **2.6** | +0.0245 | $199.44 | $+197.61 |
| fred_VXV | 3d | +0.1279 | 0.0535 | **2.4** | +0.0187 | $113.00 | $+111.17 |
| gex_SPX | 3d | -0.1233 | 0.0519 | **2.4** | +0.0016 | $108.87 | $+107.04 |
| fred_WTI_d5 | 20d | -0.1670 | 0.0763 | **2.2** | -0.0412 | $346.38 | $+344.55 |
| fred_VIX | 5d | +0.1593 | 0.0745 | **2.1** | +0.0273 | $175.98 | $+174.15 |
| fred_VXV | 10d | +0.1942 | 0.0963 | **2.0** | +0.0021 | $290.08 | $+288.25 |
| fred_HY_SPREAD | 20d | +0.2611 | 0.1300 | **2.0** | +0.0258 | $541.71 | $+539.88 |
| fred_HY_SPREAD | 10d | +0.1849 | 0.0947 | **2.0** | +0.0267 | $276.21 | $+274.38 |
| fred_VIX | 3d | +0.1075 | 0.0555 | **1.9** | +0.0319 | $94.93 | $+93.10 |
| fred_HY_SPREAD | 5d | +0.1273 | 0.0705 | **1.8** | +0.0017 | $140.62 | $+138.79 |
| fred_VXV | 1d | +0.0570 | 0.0326 | **1.7** | +0.0254 | $31.49 | $+29.66 |
| fred_VIX | 10d | +0.1762 | 0.1022 | **1.7** | +0.0023 | $263.13 | $+261.30 |
| gex_SPX | 1d | -0.0697 | 0.0409 | **1.7** | -0.0398 | $38.52 | $+36.69 |
| gex_NDX | 10d | -0.0979 | 0.0580 | **1.7** | +0.0213 | $146.26 | $+144.43 |
| dts_PubDebtCashAdj | 10d | -0.0940 | 0.0589 | **1.6** | -0.0421 | $140.42 | $+138.59 |
| fred_VIX | 1d | +0.0516 | 0.0341 | **1.5** | +0.0300 | $28.53 | $+26.70 |
| fred_DGS10_d5 | 5d | -0.0908 | 0.0603 | **1.5** | -0.0468 | $100.29 | $+98.46 |
| fred_WTI_d5 | 10d | -0.1067 | 0.0715 | **1.5** | -0.0322 | $159.46 | $+157.63 |
| dts_InterAgencyTaxTransfers_d5 | 20d | +0.0584 | 0.0402 | **1.5** | +0.0595 | $121.14 | $+119.31 |
| gex_SPX | 20d | -0.1143 | 0.0796 | **1.4** | -0.0232 | $237.15 | $+235.32 |
| fred_IORB_d5 | 3d | +0.0837 | 0.0586 | **1.4** | -0.0337 | $73.93 | $+72.10 |
| dts_PubDebtCashAdj | 20d | -0.1201 | 0.0847 | **1.4** | -0.0534 | $249.19 | $+247.36 |
| fred_HY_SPREAD | 3d | +0.0812 | 0.0586 | **1.4** | +0.0371 | $71.72 | $+69.89 |

**Clearing 3x the roll floor AND covering cost: 1 of 180**

- `gex_SPX` at 5d: IC -0.1853, 3.2x floor, $+202.87/trade net of cost

A survivor here is a CANDIDATE, not a strategy. It would still need the full gate: held-out P&L, an all-cell empirical null, 6/8 green quarters, a stale placebo that loses, and a trade-for-trade match against the live executor before any capital moves.


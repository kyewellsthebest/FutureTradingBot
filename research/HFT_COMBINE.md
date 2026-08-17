# Do the order-flow features combine?

Every number in this project is a **single feature measured alone**. At 60-second bars three sit at almost the same strength -- range, trade intensity and return, each ~0.15pt of edge at 3.1-3.5x the noise floor with sign-stable train/holdout. They are different measurements, so they may carry partly independent information.

    if fully independent: sqrt(3) x 0.15 = 0.26pt = $0.52
    cost at $0.60 all-in:                          $0.60
    -> 87% of breakeven, from features already measured

**What pays.** At 60s bars on one MNQ, `edge($) = IC x sigma x 2`. Breakeven at $0.60 needs **IC > 0.026**; $150/day at 200 trades needs **IC > 0.059**. Best single feature measured is intensity at holdout IC 0.0132, so breakeven needs 2.0x it and the income target 4.5x.

Train: NQH5, NQH6, NQM5, NQM6, NQU4. Holdout: NQU5, NQZ4, NQZ5. Purged by contract -- different quarters are different periods, so there is no leakage across the boundary. Exactly the nine features already measured, no new ones.

| horizon | model | train IC | **holdout IC** | edge $ | net @ $0.60 | vs best single |
|---|---|---|---|---|---|---|
| 60s | ridge | +0.0099 | **+0.0139** | $0.25 | $-0.35 | 0.99x |
| 60s | lightgbm | +0.0899 | **+0.0054** | $0.10 | $-0.50 | 0.39x |
| 60s | shuffled ctl | +0.0031 | **+0.0001** | $0.00 | $-0.60 | 0.00x |

| 120s | ridge | +0.0098 | **+0.0166** | $0.42 | $-0.18 | 0.90x |
| 120s | lightgbm | +0.0942 | **+0.0091** | $0.23 | $-0.37 | 0.49x |
| 120s | shuffled ctl | -0.0051 | **-0.0062** | $0.15 | $-0.45 | 0.33x |

| 300s | ridge | +0.0134 | **+0.0103** | $0.41 | $-0.19 | 0.46x |
| 300s | lightgbm | +0.1013 | **+0.0053** | $0.21 | $-0.39 | 0.24x |
| 300s | shuffled ctl | +0.0063 | **+0.0085** | $0.34 | $-0.26 | 0.39x |

## Verdict

Best combination: **ridge at 120s, holdout IC 0.0166**, edge $0.42/trade, **$-0.18 net of $0.60 cost**.

Still short by $0.18/trade. Combining helped only to the extent the features were independent, and the shortfall is what remains for full-depth book data to close.

Read the shuffled row first. Whatever it reports is what this pipeline manufactures from nothing, and every real number has to be judged against it rather than against zero. And compare train IC with holdout IC on the LightGBM row: a large gap there is overfitting made visible.


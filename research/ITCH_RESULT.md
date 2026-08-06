# ITCH order book study

Source: `01302019.NASDAQ_ITCH50.gz` (4.76 GB compressed), first 60,000,000 messages.

Parsed **60,000,000 messages**, 35,134 book snapshots across 11 tracked symbols (8,713 listed).

Message mix: `A`=25,836,794, `D`=24,351,509, `U`=4,669,858, `X`=1,669,367, `I`=1,051,943, `E`=1,015,325, `F`=944,865, `P`=208,638

Symbols: AAPL, AMD, AMZN, BAC, GOOGL, INTC, MSFT, NVDA, QQQ, SPY, TSLA

Median spread **4.3 bps**, median top of book 210 x 300 shares, 35,134 snapshots.

## Does book imbalance predict the next move?

| horizon | feature | train IC | holdout IC | sign held |
|---|---|---|---|---|
| 1 snapshots | imb | +0.0829 | +0.1165 | yes |
| 1 snapshots | shuffled | +0.0003 | +0.0031 | yes |
| 1 snapshots | shifted | +0.0051 | -0.0008 | no |
| 5 snapshots | imb | +0.0586 | +0.0542 | yes |
| 5 snapshots | shuffled | -0.0000 | -0.0027 | yes |
| 5 snapshots | shifted | -0.0092 | +0.0078 | no |
| 20 snapshots | imb | +0.0256 | +0.0066 | yes |
| 20 snapshots | shuffled | -0.0013 | -0.0152 | yes |
| 20 snapshots | shifted | -0.0323 | -0.0061 | yes |
| 50 snapshots | imb | +0.0265 | +0.0127 | yes |
| 50 snapshots | shuffled | -0.0042 | -0.0120 | yes |
| 50 snapshots | shifted | -0.0312 | -0.0178 | yes |

**Best: imbalance +0.1165 at 1 snapshots ahead, against a time-shifted control of -0.0008.** A typical move over that horizon is 0.0 bps.

- raw, before the control: 0.00 bps a trade
- **net of the control: 0.00 bps a trade**
- crossing the spread costs **4.3 bps**, so a taker needs 4287219187.3x this to break even
- **verdict: does NOT clear the spread**

Two controls, both of which imbalance has to beat -- not zero. `shuffled` is a plain permutation; `shifted` is the same series rolled forward inside each symbol, so it keeps imbalance's persistence and loses only its alignment with the future. The second is the harder bar and the honest one.

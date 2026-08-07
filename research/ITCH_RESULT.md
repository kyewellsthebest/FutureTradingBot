# ITCH order book study

Source: `01302019.NASDAQ_ITCH50.gz` (4.76 GB compressed), first 200,000,000 messages.

Parsed **200,000,000 messages**, 89,397 book snapshots across 11 tracked symbols (8,713 listed).

Message mix: `A`=89,214,226, `D`=85,706,955, `U`=14,842,947, `E`=3,855,365, `X`=3,060,168, `F`=1,281,753, `I`=1,062,015, `P`=673,252

Session: 89% of snapshots fall in 09:30-16:00 ET. Median spread 2.7 bps in hours against 13.9 bps outside.

Keeping the 79,816 in-hours snapshots and discarding the rest.

Symbols: AAPL, AMD, AMZN, BAC, GOOGL, INTC, MSFT, NVDA, QQQ, SPY, TSLA

Median spread **2.7 bps**, median top of book 400 x 400 shares, 79,816 snapshots.

## Does book imbalance predict the next move?

| horizon | feature | train IC | holdout IC | sign held |
|---|---|---|---|---|
| 1 snapshots | imb | +0.1299 | +0.1521 | yes |
| 1 snapshots | shuffled | -0.0077 | -0.0060 | yes |
| 1 snapshots | shifted | +0.0031 | -0.0003 | no |
| 5 snapshots | imb | +0.0859 | +0.0952 | yes |
| 5 snapshots | shuffled | -0.0030 | +0.0002 | no |
| 5 snapshots | shifted | +0.0091 | -0.0043 | no |
| 20 snapshots | imb | +0.0483 | +0.0543 | yes |
| 20 snapshots | shuffled | +0.0019 | +0.0011 | yes |
| 20 snapshots | shifted | +0.0101 | -0.0129 | no |
| 50 snapshots | imb | +0.0344 | +0.0334 | yes |
| 50 snapshots | shuffled | +0.0049 | -0.0029 | no |
| 50 snapshots | shifted | +0.0038 | -0.0111 | no |

## What actually happened next, by imbalance decile (holdout only)

| decile | mean forward move (1 snaps) | n | +/- |
|---|---|---|---|
| 0 | -0.166 bps | 2,394 | 0.029 |
| 1 | -0.193 bps | 2,397 | 0.032 |
| 2 | -0.131 bps | 2,391 | 0.030 |
| 3 | -0.067 bps | 2,395 | 0.029 |
| 4 | +0.027 bps | 3,153 | 0.025 |
| 5 | +0.091 bps | 1,632 | 0.032 |
| 6 | +0.109 bps | 2,693 | 0.028 |
| 7 | +0.178 bps | 2,094 | 0.033 |
| 8 | +0.249 bps | 2,393 | 0.030 |
| 9 | +0.193 bps | 2,394 | 0.027 |

**Top decile minus bottom: +0.359 bps +/- 0.039 (9.2 sigma).** Acting on one side of that captures about half of it, +0.180 bps, against a half-spread of 1.37 bps to cross.

**Best: imbalance +0.1521 at 1 snapshots ahead, against a time-shifted control of -0.0003.**

- forward move over that horizon: sigma 1.95 bps, mean absolute 0.81 bps, and the mid moves at all only 50% of the time
- raw, before the control: 0.30 bps a trade
- **net of the control: 0.30 bps a trade**
- crossing the spread costs **2.7 bps**, so a taker needs 9.3x this to break even
- a maker who never crosses pays no spread, and for them the bar is queue position and adverse selection, not 2.7 bps
- **verdict as a TAKER: does NOT clear the spread**

Two controls, both of which imbalance has to beat -- not zero. `shuffled` is a plain permutation; `shifted` is the same series rolled forward inside each symbol, so it keeps imbalance's persistence and loses only its alignment with the future. The second is the harder bar and the honest one.

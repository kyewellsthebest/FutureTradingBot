# Does the time-based breakeven stop actually work?

The claim: pull the stop to breakeven if a trade is not +40-60pt favourable by minute 30, and LEVELRIDE goes from $32/day to $129/day with half the drawdown.

On a martingale every stopping rule has the same expectancy, so an exit rule cannot invent edge. A 4x gain means either real negative autocorrelation in losing trades -- a genuine, tradable finding -- or selection, since four rules were tried and one won.

Those are distinguishable. **A real effect is a plateau**: it holds at 20, 30 and 40 minutes and across 30-60 points, because nothing in the market knows which number was tested. **Selection is a spike** at exactly the tested value. So the rule is swept, not evaluated at its own setting.

NQ, 8 quarters, 519 sessions, 1-second resolution, $1.50 round trip, 11-rung deployed ladder.

## entry slippage 0.25 pt

| BE rule | trades/day | win % | $/trade | **$/day** | max DD | RANDOM $/day |
|---|---|---|---|---|---|---|
| OFF (baseline) | 7.7 | 37.7% | $+3.33 | **$+25** | $-12,270 | $-5 |
| 20min / 30pt | 10.8 | 26.4% | $+17.03 | **$+184** | $-6,512 | $+150 |
| 20min / 40pt | 12.0 | 23.5% | $+17.60 | **$+211** | $-6,512 | $+215 |
| 20min / 50pt | 12.8 | 21.8% | $+17.92 | **$+229** | $-6,512 | $+211 |
| 20min / 60pt | 13.6 | 20.0% | $+17.32 | **$+235** | $-6,514 | $+230 |
| 30min / 30pt | 9.6 | 29.7% | $+15.04 | **$+145** | $-6,666 | $+120 |
| 30min / 40pt | 10.4 | 27.1% | $+16.09 | **$+168** | $-7,154 | $+102 |
| 30min / 50pt | 11.1 | 25.3% | $+16.21 | **$+181** | $-7,154 | $+169 |
| 30min / 60pt | 11.6 | 23.8% | $+16.55 | **$+193** | $-6,994 | $+184 |
| 40min / 30pt | 8.9 | 32.2% | $+14.33 | **$+128** | $-6,666 | $+108 |
| 40min / 40pt | 9.5 | 30.3% | $+16.67 | **$+159** | $-6,666 | $+108 |
| 40min / 50pt | 10.0 | 28.5% | $+17.49 | **$+175** | $-6,666 | $+142 |
| 40min / 60pt | 10.4 | 26.8% | $+17.08 | **$+178** | $-6,666 | $+157 |

## entry slippage 1.00 pt

| BE rule | trades/day | win % | $/trade | **$/day** | max DD | RANDOM $/day |
|---|---|---|---|---|---|---|
| OFF (baseline) | 7.7 | 36.9% | $-1.12 | **$-9** | $-20,692 | $-24 |
| 20min / 30pt | 11.0 | 25.8% | $+13.82 | **$+151** | $-8,352 | $+143 |
| 20min / 40pt | 12.1 | 23.2% | $+15.69 | **$+190** | $-8,230 | $+188 |
| 20min / 50pt | 12.9 | 21.2% | $+14.67 | **$+189** | $-8,238 | $+158 |
| 20min / 60pt | 13.7 | 19.6% | $+14.15 | **$+194** | $-8,241 | $+207 |
| 30min / 30pt | 9.8 | 29.0% | $+12.48 | **$+122** | $-9,399 | $+78 |
| 30min / 40pt | 10.5 | 26.7% | $+14.26 | **$+149** | $-8,216 | $+129 |
| 30min / 50pt | 11.2 | 24.9% | $+14.20 | **$+159** | $-8,220 | $+126 |
| 30min / 60pt | 11.7 | 23.3% | $+14.34 | **$+168** | $-8,060 | $+220 |
| 40min / 30pt | 9.1 | 31.3% | $+9.85 | **$+89** | $-10,820 | $+115 |
| 40min / 40pt | 9.6 | 29.5% | $+12.73 | **$+122** | $-8,579 | $+103 |
| 40min / 50pt | 10.1 | 27.7% | $+13.19 | **$+133** | $-8,213 | $+96 |
| 40min / 60pt | 10.5 | 26.2% | $+13.87 | **$+146** | $-8,213 | $+86 |

## Reading it

Compare every BE row with the OFF row at the same slippage. If the improvement holds across the whole grid it is real and it is the user's finding. If it appears only at one cell it is the four-rules-one-winner problem. And compare with the RANDOM column: a stop rule that also improves random-direction trades is managing exposure, not exploiting anything about the entry.


# Hypothesis ledger — append-only. What was searched, what it said.

Purpose: no future search rediscovers a corpse. Before building anything,
grep this file.

| # | family / claim | where tested | scale | verdict | notes |
|---|---|---|---|---|---|
| 1 | impulse-pullback (all variants) | NQ bars+tick, FX tick | 1000s of configs | NULL | −$2.21/tr OOS best case; user's own strategy +$0.14 at trade-through |
| 2 | mean reversion (z of close) | 7 futures, 8 FX | grid | NULL | |
| 3 | VWAP reversion | futures bars | grid | NULL | |
| 4 | opening range breakout | futures bars | grid | NULL | timestamp bug fixed, still null |
| 5 | range compression / squeeze | futures + FX | grid | NULL | |
| 6 | overnight gap | futures bars | grid | NULL | first-tradeable-bar bug fixed, still null |
| 7 | volume spike | futures | grid | NULL | |
| 8 | hour-of-day / weekday / wd×hour | futures | grid | NULL | |
| 9 | cross-market lead-lag | 15 markets | grid | NULL | |
| 10 | order-flow imbalance (trade prints) | NQ tick | grid | NULL | prints ≠ book; see #17 |
| 11 | continuous position sizing | futures | grid | NULL | account granularity too coarse |
| 12 | calendar effects | futures | grid | NULL | |
| 13 | sweeps / absorption | NQ tick | grid | NULL | |
| 14 | trailing-stop exits (13 rules) | 8 NQ contracts, 58,437 trades each | full | NULL | nothing beats fixed 6/12; tight trail doubles win rate, second-worst edge |
| 15 | AND-combos of technical features | 8 FX symbols | **1.38B distinct configs** | NULL+ | selection anti-persistent: mean holdout falls −1.13→−243 pips as cut tightens; hit-rate rises to 65.9% while mean falls — selection favours fat-loss configs |
| 16 | daily GEX / options positioning | NQ | daily | NULL | |
| 17 | **book imbalance** | NASDAQ ITCH L3 + 4 FX pairs | IC study | **REAL, small** | holdout IC +0.15/+0.13/+0.09/+0.06/+0.07, controls at zero; worth ~1/7 of spread as taker |
| 18 | COT / positioning | futures | weekly | NULL | |
| 19 | selection-by-train-score as a method | everywhere | 1.38B | HARMFUL | measured negative return to searching harder |
| 20 | FX impulse at 97% lower costs | 4 FX pairs, measured spread | full sim | NULL | all arms negative gross; "it was the costs" hypothesis retired |

| 21 | **leg-grammar conditional cells** | 8 NQ contracts, 27.6M legs, 3 scales | ~750 cells/scale | **RETRACTED — unsorted-tape artifact** | 76–97% of screened cells hold OOS vs shuffled floor 0–1; standout: large+fast+LOW-volume leg reversal continues +6.15 ticks OOS at DELAY=1, 8/8 contracts, both directions, nbhd 100%; same cell at HIGH volume flips sign. grammar.py never sorted the tape; raw parquets are 86–88% out of time order (jumps up to 73h back). Every 'leg' was row-order fiction; the 'continuation' was the file jumping back to where the market had been hours earlier — which is why it was symmetric, everywhere, stronger with horizon, and passed a synthetic null (the synthetic tape was generated sorted). The trade-level replay sorted the tape: effect = +0.6 ticks gross, negative after costs. Caught at the equity-curve stage, before deployment. Sorted rerun done: a SMALL real residue survives. **SIGN CORRECTED 2026-08-08** — an earlier note here called it "short side, fade upward spikes"; that was backwards. The surviving cell is `(-1,4,2,4,0)`, and `dir` in grammar.py is the direction of the COMPLETED leg with `fwd = (pc[tgt]-cp)*(-dir)`, so `dir=-1` is a completed DOWN leg and the trade is **LONG**: buy after a large, fast, deeply-retraced, LOW-volume DOWN spike. Holdout +1.64/+2.12/+3.81 ticks at F=50/200/1000, 3/3 contracts, ~$0.82-1.91 gross vs ~$1.75 realistic cost → breakeven-to-slightly-negative net. The genuine short mirror `(1,4,2,4,0)` is materially weaker and does not survive the long horizon: +1.39 at F=50 but **-0.33 at F=1000, 2/3 vote**. The asymmetry is itself informative — and it is also exactly what an uncorrected drift would look like on a rising index, which is why the dir-matched baseline audit below is the next test, not an optional one. Screened cells collapse 121-147 → 6-15 vs shuffled floor 1-2; sign-hold 78-83% vs coin. Real behaviour, an order of magnitude too small to trade as-is |

| 22 | **back-of-queue market making** | NASDAQ ITCH L3, 46,398 passive orders, order-ID-exact queue | full day | **NEGATIVE — maker path closed** | Fill rate 50.8%; half-spread captured +1.1 bps; adverse selection −1.9 bps at ALL horizons → net −0.7 to −0.8 bps BEFORE commission. Imbalance gating does not rescue: all five quintiles net negative (best −0.21). Joining the back of the queue loses everywhere; front-of-queue unreachable for late joiners |

Open questions with machinery built and answer pending:
- #21 next: trade-level simulation (equity curve, drawdown, weekly P&L distribution, MAE/MFE, session split), bootstrap, then paper execution design

Method rules validated the hard way (bug-derived, all reproduced in tests):
- confirmation-causal anchoring only (look-ahead entry filter once manufactured 50.6% at 2:1)
- controls must match trade counts (control once traded 4× the strategy)
- exits resolve from bar/print AFTER entry (same-bar asymmetry once flipped a sign)
- fill direction ≠ trade direction under inversion
- µs vs ns timestamps: never `astype(int64)//10**9` on pandas 3
- vacuous-test detection: a regression test where both versions reject everything tests nothing
- SORT THE TAPE AND ASSERT MONOTONICITY AT LOAD (unsorted parquets invented cell #21; the null check passed because the synthetic tape was born sorted — controls must share every defect of the real data path)

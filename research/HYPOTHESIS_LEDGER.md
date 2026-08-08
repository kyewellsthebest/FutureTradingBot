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

| 21 | **leg-grammar conditional cells** | 8 NQ contracts, 27.6M legs, 3 scales | ~750 cells/scale | **REAL — survives bounce test AND held-out-era test** | 76–97% of screened cells hold OOS vs shuffled floor 0–1; standout: large+fast+LOW-volume leg reversal continues +6.15 ticks OOS at DELAY=1, 8/8 contracts, both directions, nbhd 100%; same cell at HIGH volume flips sign. Era test (trained mid-2024→late-2025, tested Dec-2025→Jun-2026 never touched): +8.0/+8.3 ticks at F=50, +11.8/+11.5 at F=200, +17.7/+16.3 at F=1000 — F≥200 passes BOTH gates incl. $4.40; 3/3 contracts, both directions, nbhd 100%, shuffled floor 0–1 |

Open questions with machinery built and answer pending:
- adverse selection after passive fills (mm_study.py, ITCH) — decides the maker path
- #21 next: trade-level simulation (equity curve, drawdown, weekly P&L distribution, MAE/MFE, session split), bootstrap, then paper execution design

Method rules validated the hard way (bug-derived, all reproduced in tests):
- confirmation-causal anchoring only (look-ahead entry filter once manufactured 50.6% at 2:1)
- controls must match trade counts (control once traded 4× the strategy)
- exits resolve from bar/print AFTER entry (same-bar asymmetry once flipped a sign)
- fill direction ≠ trade direction under inversion
- µs vs ns timestamps: never `astype(int64)//10**9` on pandas 3
- vacuous-test detection: a regression test where both versions reject everything tests nothing

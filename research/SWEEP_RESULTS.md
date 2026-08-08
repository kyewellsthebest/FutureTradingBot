# SWEEP_RESULTS — Cross-Market Synthesis of the Leg-Grammar Sweeps

Date: 2026-08-08. Synthesizes 9 market sweeps (GC, CL, RTY, YM, HG, FX-EURUSD, FX-GBPUSD, FX-USDJPY, plus the failed ES and NQ-SEQ2 launches) and their adversarial audits. All runs: sorted tape via grammar.py's loader (argsort at load, line ~214), DELAY=1, cells judged against the event-population baseline and a shuffled floor, 70/30 chronological split, train screen |t|>=3, MIN_TR=400 / MIN_HO=150.

Reference under test: the NQ residue from the sorted rerun (research/TICK_GRAMMAR.md — TICK_GRAMMAR_DELAY1.md is the retracted unsorted artifact, ledger #21): cell **(-1, dist=4, vel=2, retr=4, vol=0)** with POSITIVE holdout **+1.6 / +2.1 / +3.8 ticks** across horizons, 3/3. Per grammar.py's convention (fwd = Δp × −dir) that is: after a thin-volume, fast, deep-retraced DOWN leg, price moves UP — a fade of the down-spike. NOTE (NQ-SEQ2 audit, defect 4): the ledger prose calls this "short side, fade upward spikes," which contradicts the code convention; the sign test below therefore uses convention-independent matching — **same key (-1,4,2,4,0), same fwd sign (+)**.

BROKEN items (per audits) are excluded from all conclusions and listed in Section 4.

---

## 1. THE SIGN TEST (headline)

Does (-1,4,2,4,0) with positive fwd — or its mirror behaving as a fade — appear in the other markets?

| market | exact cell present? | fwd sign vs NQ | strength (holdout) | audit disposition | tally |
|---|---|---|---|---|---|
| GC | NO (either dir, any R/h) | — | nearest relative (-1,4,2,2,0): same sign, +16.38 ± 16.39 (1.0 se, n_ho=183) | "using it as confirmation is retrofitting" | ABSENT |
| CL | YES: (-1,4,2,4,0) R=4 h1000 | **OPPOSITE** (−4.65 ± 3.13, continuation not fade) | 1.49 se iid, <1 se after ~2x autocorr deflation | "the sign check fails; opposite dynamic" | AGAINST |
| RTY | YES, both dirs | −1 key SAME (+1.99 ± 2.91, 0.7 se); +1 key OPPOSITE (−5.70 ± 4.49, 1.27 se, BROKEN-adjacent table) | neither reaches 2 se; all 21 RTY passers decode to one up-drift bet, which is exactly what a −1-key/+fwd cell is | "no RTY replication of the thin-volume fade" | MIXED (nominal same-sign hit explained by drift) |
| YM | −1 key ABSENT; +1 key present (R=8 h200/h1000, same 818/449 legs) | +1 key is momentum-continuation (−6.99 ± 3.06), i.e. **anti-fade** | 2.28 se nominal → ~1.1 se after deflation/multiplicity; h1000 copy is on a BROKEN table; 13/13 YM passers share one absolute direction (drift) | "same key string, different behaviour: not the NQ effect" | AGAINST |
| HG | NO (no vel=2/retr=4/vol=0 cell anywhere) | — | closest cells are vol=2 HGM6 artifacts (BROKEN) | "HG does not confirm the thin-volume fade in any volume regime" | ABSENT |
| FX-EURUSD | NO — zero cells passed anywhere | — | — | trustworthy null | ABSENT |
| FX-GBPUSD | NO | — | lone survivor is a different cell, flipped OOS | null | ABSENT |
| FX-USDJPY | NO | — | survivor is (−1,4,0,4,**2**): wrong volume bin, 0.9 se | "narrating it as the FX version would be retrofitting" | ABSENT |
| ES | — | — | — | run BROKEN, no tables exist | NO DATA |

**Count: 0 markets FOR at any audit-accepted standard / 2 AGAINST (CL, YM — both themselves noise- or drift-compatible) / 1 MIXED (RTY, same-sign at 0.7 se, drift-explained) / 5 ABSENT / 1 NO DATA.**

**The thin-volume-fade family does not replicate.** Nowhere outside NQ does the cell reach 2 se in either direction. By the project's own rule ("a real microstructure effect replicates; one market's residue does not"), the NQ residue must be treated as an NQ-only artifact until proven otherwise — and the cross-market failure mode observed (YM 13/13, RTY 21/21, HG passers all decoding to index/commodity drift through dir-conditioned cells) is a concrete mechanism that could also have produced the NQ residue itself. That check has not yet been run on NQ.

---

## 2. Per-market tables

"Best trustworthy cell" means a cell its own audit accepts (holdout |mean| >= 2 se after overlap deflation, not drift-decoded, not an artifact). Gates: $1.42 commission-only / $4.40 with slippage — MNQ-derived figures applied unchanged to every product (a flagged defect); footer text hardcodes $0.50/tick while GC/CL ran at $1.00/tick and HG at $1.25/tick.

### GC (6 contracts, but GCM6+GCZ4 = ~95% of legs; effective diversity ~2)

| R | horizon | passed | shuffled floor | audit verdict |
|---|---|---|---|---|
| 4 | 50 | 1 | 0 | WEAK |
| 4 | 200 | 0 | — | empty (honest) |
| 4 | 1000 | 3 | 0 | WEAK (1 of 3 flipped sign OOS) |
| 8 | 50 | 0 | — | empty (honest) |
| 8 | 200 | 2 | 0 | WEAK (holdouts 0.2–0.4 se) |
| 8 | 1000 | 1 | 0 | WEAK |

Multiplicity (audit): 7 passed across ~1,545 screens vs ~4.2 expected by chance, Poisson P ≈ 0.14 — the whole-sweep excess is chance-compatible. Printed floor of 0 is one permutation draw; the honest floor is ~4 across the sweep.
Best trustworthy cell: **NONE**. Best surviving candidate (not a finding): (1,4,2,4,2) R=8 h1000, holdout −22.41 ± 11.74 (1.9 se iid → ~1.2–1.4 after overlap deflation), $22.41 gross at $1.00/tick, nominal PASS/PASS on miscalibrated gates. Numbers replicate exactly under independent rerun; the report is honest, the evidence is insufficient.

### CL (8 contracts; CLM6 = 51% of legs)

| R | horizon | passed | shuffled floor | audit verdict |
|---|---|---|---|---|
| 4 | 50 | 2 | 2 | **BROKEN** (at floor) |
| 4 | 200 | 3 | 0 | WEAK (t inflated ~1.7x by +0.47 outcome autocorr) |
| 4 | 1000 | 6 | 0 | WEAK (+0.64 lag-1 autocorr; 2 of 6 flipped OOS) |
| 8 | 50 | 1 | 1 | **BROKEN** (at floor) |
| 8 | 200 | 0 | — | empty |
| 8 | 1000 | 0 | — | empty |

Audit headline: after deflating iid t-stats for autocorrelation, ZERO of 12 passed cells clears |t|>=3 train or 2 se holdout.
Best trustworthy cell: **NONE**. Best surviving candidate: (−1,4,2,4,0) R=4 h1000, −4.65 ± 3.13 (1.49 se iid, <1 se effective), $4.65 gross, the run's only dual-gate pass — and its sign CONTRADICTS the NQ fade (continuation, not exhaustion). n_ho = 362.

### RTY (8 contracts)

| R | horizon | passed | shuffled floor | audit verdict |
|---|---|---|---|---|
| 4 | 50 | 2 | 0 | WEAK (holdouts $0.01/$0.00) |
| 4 | 200 | 0 | — | trustworthy null |
| 4 | 1000 | 14 | 0 | WEAK (one common drift factor, not 14 findings) |
| 8 | 50 | 0 | — | trustworthy null |
| 8 | 200 | 1 | 1 | WEAK (at floor) |
| 8 | 1000 | 4 | 0 | WEAK/anti-signal (25% sign-hold, below coin) |

Audit headline: 0 of 21 passed cells reach holdout |mean| >= 2 se (max 1.68 pre-deflation); all 21 decode to "price drifts up" on a contract that rallied 1985→2337. Effects are an order of magnitude weaker than NQ (max |t| 4.5 vs 34.6). Correct summary: **clean null**.
Best trustworthy cell: **NONE**.

### YM (8 contracts)

| R | horizon | passed | shuffled floor | audit verdict |
|---|---|---|---|---|
| 4 | 50 | 0 | — | trustworthy null |
| 4 | 200 | 3 | 1 | WEAK (no cell reaches 2 se) |
| 4 | 1000 | 4 | 1 | WEAK (best cell 3.9 se → ~1.9 after overlap deflation) |
| 8 | 50 | 0 | — | trustworthy null |
| 8 | 200 | 2 | 0 | WEAK (best 2.28 se nominal → ~1.1 deflated) |
| 8 | 1000 | 4 | 1 | **BROKEN** (50% sign-hold = coin; PASS/PASS cell at 1.96 se fails the 2-se rule outright) |

Audit headline: **13/13** passed cells resolve to the same absolute market direction (up) — the sweep found YM's rally, not a grammar. One cell (818/449 legs) is double-counted at two nested horizons.
Best trustworthy cell: **NONE**. Best surviving candidate: (1,4,2,4,0) R=8 h200, −6.99 ± 3.06, $3.50 gross, PASS commission / fail slippage — decodes to up-leg momentum resumption, not a fade, and sits at ~1.1 se after deflation.

### HG (3 contracts; HGM6 is a degenerate tape, ~98 ticks/day)

| R | horizon | passed | shuffled floor | audit verdict |
|---|---|---|---|---|
| 4 | 50 | 0 | — | trustworthy null |
| 4 | 200 | 2 | 1 | WEAK (both failed OOS) |
| 4 | 1000 | 4 | 0 | **BROKEN** (drift riders; gates-PASS cell flipped sign OOS) |
| 8 | 50 | 0 | — | trustworthy null |
| 8 | 200 | 0 | — | trustworthy null |
| 8 | 1000 | 2 | 0 | **BROKEN** (12 HGM6 holdout legs at +323 ticks supply 77% of one headline mean, >100% of its mirror; sign flips when HGM6 removed) |

Best trustworthy cell: **NONE**. Nothing in the sweep survives removing one degenerate contract. Only 30 tested cells/horizon at R=4 and 3 at R=8 — floors over 3 cells are meaningless.

### FX (one file per symbol — no contract vote; futures $ gates inapplicable, spread is the yardstick)

| symbol | screens | passed | floors | outcome |
|---|---|---|---|---|
| EURUSD | 6 (R=10/20 × 3 h) | 0 | 0 | trustworthy null — tightest-spread pair shows nothing anywhere |
| GBPUSD | 6 | 1 | 0 | flipped sign OOS (−2.86 ± 3.76); nothing |
| USDJPY | 6 | 2 | 0 | one flipped OOS; survivor (−1,4,0,4,2) +4.99 ± 5.51 pipettes = 0.9 se nominal, ~0.3 se after ~12x overlap deflation, ≈ 1.0–1.25x median spread gross |

Audit: 3 passes across ~1,000+ tested cells is exactly the chance rate. **Honest null.** Best trustworthy cell: **NONE**.

### ES and NQ-SEQ2

No tables exist (see Section 4). ES contributes NO DATA to the sign test; NQ-SEQ2 was an NQ extension, not a cross-market point.

---

## 3. Dollars: honest net available today

**Best per-trade net available today, across all tick markets: $0. Per week if traded together: $0.**

Assumptions (stated, per instruction): "available" means a cell that survives its own audit — holdout |mean| >= 2 se after overlap deflation, not decoded to drift, not a single-contract artifact, and gross clearing a correctly calibrated per-product cost gate. **Zero cells in nine markets qualify.** The four nominal PASS/PASS cells are: GC (1.9 se → ~1.3 deflated), CL (1.49 se → <1), YM (1.96 se, on a BROKEN table), HG (HGM6 artifact, dies when one contract is removed). Summing their point estimates would be summing noise, and the $1.42/$4.40 gates they "passed" are MNQ cost figures never recalibrated for GC/CL/HG. The FX survivor is worth ~one spread gross at 0.9 se. There is nothing to trade from this sweep, and no weekly figure other than zero can be stated without inflating.

---

## 4. Defects and exclusions (BROKEN items and cross-cutting defects)

Excluded from all conclusions above:

1. **ES — all tables BROKEN.** No output was ever produced. The awaited background task was mislaunched with NQ defaults (GLOB=NQ*, TAG=NQ, $0.50/tick — would have produced NQ data under an ES headline at 2.5x-wrong dollar scale), and the process died at the header (log frozen at 196 bytes). ESZ5 tape is 96.7% out of time order (worst backward jump 52.75 h); the loader sorts but does not ASSERT monotonicity, weaker than the ledger rule. ES has 6 contracts, not 8.
2. **NQ-SEQ2 — all tables BROKEN.** Process dead ~10 min with header-only log; the report's "sorting and decomposing now" status line was false. The SEQ2 flag is never logged, so even a completed run could not prove SEQ2 was active; tested-cell counts are not logged.
3. **CL R=4 h50 and R=8 h50** — passed counts equal their shuffled floors.
4. **YM R=8 h1000** — coin-level sign-hold; the celebrated PASS/PASS cell fails the 2-se rule (1.96 se).
5. **HG R=4 h1000 and R=8 h1000** — drift contamination plus the HGM6 degenerate-tape artifact (12 holdout legs at +323 ticks each carrying the headline).
6. **FX GBPUSD R10-F1000 and USDJPY R10-F50 cells** — BROKEN as findings (sign flips); the tables themselves are honest.

Cross-cutting defects (appear in 3+ audits; must be fixed before the next sweep is interpretable):

- **Invalid null at long horizons:** the shuffled control is a single iid permutation that destroys the serial correlation (+0.47 to +0.64 lag-1) inflating real t-stats — the printed floors are biased low exactly where cells pass. Flagged in GC, CL, RTY, YM, HG audits.
- **Drift leakage through dir-conditioned cells:** the dir-signed population baseline cancels drift across directions but not within a dir-specific cell. YM 13/13, RTY 21/21 one-directional; HG headline cells decode to raw "price up ~20 ticks."
- **Overlap-understated SEs:** outcome windows at h=1000 overlap ~2–12x (up to ~100x+ on dense tapes); every "held sign" and se in the reports is optimistic by roughly 2x.
- **Multiplicity unreported:** tested-cell counts (271–450 per table; ~1,500–2,000 per sweep) were omitted from every report; several "N passed vs floor 0" excesses are at or below the analytic chance rate.
- **Cost-gate miscalibration:** $1.42/$4.40 are MNQ figures applied to gold, oil, copper, FX; footer hardcodes "$0.50/tick" regardless of the actual USD_TICK used; gates are evaluated on holdout means that are themselves noise (e.g. $16.38 gross vs se $16.39), and in one HG case a PASS printed on a sign-flipped cell.
- **NQ sign-convention conflict:** ledger #21 prose ("short side, fade upward thin spikes") contradicts grammar.py's convention for the cell carrying the +1.6/+2.1/+3.8 numbers ((−1,4,2,4,0) = long after down-spikes). Unresolved; gates any family-level claim.
- **Concentration/degenerate tapes:** GCM6+GCZ4 ~95% of GC legs; CLM6 51% of CL; HGM6 ~98 ticks/day. "Vote x/N" overstates independence everywhere.
- **Nested-horizon double counting:** the same legs reported as support at h200 and h1000 (YM 818/449; GC (−1,4,0,2,2) at two R×h).

---

## 5. Next actions (ranked)

1. **Run the drift-decode audit on NQ itself** (research/TICK_GRAMMAR.md): check whether NQ's surviving cells share one absolute direction, YM-style (13/13). Three markets' "findings" decoded to drift; this is now the leading hypothesis for the NQ residue too, and it is a one-hour check.
2. **Resolve the sign convention** for ledger #21: pin whether (−1,4,2,4,0)+ is a down-spike fade (long) or the prose's "short-side fade of up-spikes," and rewrite the ledger entry unambiguously. Every analog test is meaningless until this is fixed.
3. **Fix the null:** replace the single iid permutation with an autocorrelation-preserving control (per-contract circular shifts or block permutation), multiple draws; print tested-cell counts and expected chance passers in every table.
4. **Overlap-aware errors:** Newey–West or non-overlapping outcome sampling at h=200/1000 so the 2-se holdout rule is real.
5. **Relaunch ES correctly:** explicit `RAW_DIR=... GLOB="ES*.parquet" TAG=ES TICKSZ=0.25 USD_TICK=1.25 DELAY=1`, unbuffered logging, and add the monotonicity ASSERT to the loader per the ledger rule; then audit the actual tables. Same for NQ-SEQ2 with the SEQ2 flag and key-dims logged.
6. **Data hygiene:** exclude tapes under ~1,000 ticks/day (HGM6, GC slivers) from the universe; add a per-contract holdout-contribution breakdown to the report generator so one contract carrying a mean is visible without an audit.
7. **Recalibrate cost gates per product** (per-product commission/slippage and USD_TICK in the footer; FX judged against spread) — cosmetic until something survives, mandatory before anything is called tradeable.
8. **Only after 1–4: re-run the cross-market sign test.** Until then the thin-volume-fade family is unreplicated (0 for / 2 against / 5 absent / 1 no-data) and nothing from this sweep should be sized.

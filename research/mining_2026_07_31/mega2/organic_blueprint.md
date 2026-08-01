ORGANIC EDGE DISCOVERY — RESEARCH BLUEPRINT (synthesis of 42 proposals x 4 adversarial critics)

====================================================================
1. THE CORE FRAMEWORK
====================================================================

Every surviving proposal is one object viewed from different angles:

  STATE (causal, pre-registered, computable from trailing OHLCV+VIX)
    -> CONDITIONAL FORWARD PATH DISTRIBUTION (drift curve, MFE/MAE fans, first-passage probabilities — measured, never assumed)
    -> COMPILED POLICY (limit depth, stop, target, TTL, trail schedule — each number a READ-OFF of the distribution, then FROZEN)
    -> PESSIMISTIC REPLAY VERDICT (only the existing touch-only fill engine may score; the atlas never scores itself)

Three non-negotiable clauses attach to every module:

a) TOUCH-CONDITIONING. Any edge claimed for a resting limit must be recomputed conditional on the limit being touched. Filled instances are an adversely-selected subsample; every critic flagged this as the single most important statistical idea in the panel. Cell-average drift is never a tradeable number.

b) COST FLOOR IN TICKS. The bar is not $4.50. It is commission + (stop-rate x 1 tick slippage) + 0.5-tick adverse-selection buffer, per market — in ZB roughly $17-20/trade, against an incumbent edge of ~$15/trade. Printed on every drift curve.

c) EFFECTIVE N = DE-OVERLAPPED EPISODES. State visits cluster in runs and forward windows overlap; the unit of inference is the non-overlapping state-entry episode (or the trade, or the day), never the bar. This one accounting change killed a third of the panel.

Discovery universe: ZB/ZN only (pooled, with the honesty that they are ONE ~0.9-correlated bet — sibling agreement is necessary, never sufficient). The other 22 markets are validation surfaces and diagnostics; their commission-per-tick makes them undeployable and mining them only burns FDR budget.

====================================================================
2. TIER 1 — BUILD FIRST
====================================================================

T1.0 UNIFIED GOVERNANCE STACK (merge: Vault + Pipeline-as-Code + Cost Floors + Reality-Check Gauntlet + Consistency Battery + Graduation Ladder + LEDGER/LOCKBOX)
What: One split authority, one append-only ledger, one lockbox, one promotion ladder, deterministic pipeline-as-code with registration hashes. The two competing governance blueprints are reconciled: the CHRONOLOGICAL three-way split with purged embargo is primary; interleaved odd/even weeks are demoted to intra-Discovery consistency checks.
Why it survived: every critic ranked all seven components priority 1-2; the only fatal flaws were the components contradicting each other, fixed by merging.
First experiments (in order, all before any mining):
  1. N* power bootstrap from STEADY-7 per-trade PnL (one notebook cell). Expect N* ~250-450 trades. This number calibrates every floor in the program.
  2. Vol-autocorrelation decay on ZB/ZN/ES to size the embargo (extend until autocorr < 0.1); commit the split manifest + SHA-256 test hashes.
  3. Determinism smoke test (same pipeline, same slice, twice, hash-equal).
  4. Gauntlet controls: matched-random-entry null must PASS STEADY-7 (scored on post-selection/walk-forward data only — passing on discovery data proves nothing) and must FAIL a deliberately planted junk state. If it cannot separate known-real from known-junk, halt everything.
  5. Noise-floor calibration: run the atlas miner unchanged on 100 joint cross-market day-block surrogates; record the best cost-adjusted drift pure noise produces. Every future discovery must clear that bar.

T1.1 TOUCHCURVE — fill-probability x touch-conditional-edge placement optimizer (absorbs microstructure Excursion Atlas and Wick Forensics)
What: For any entry state, compute P(touch depth d within h) and E[PnL | touched d] from 1-min bars, d = 1..12 ticks. Optimal depth = argmax of the EV curve, deployable only if the EV is a plateau (within 10% across d* +/- 1 tick — the exact robustness live slippage demands). Also produces the same-bar resolution table: given a 5-min bar touched both entry and stop, what fraction of 1-min sequences fill entry first — an independent audit of the pessimistic engine's rules.
Why: priority 1 from all four critics. It attacks the declared existential risk (limit-fill quality) with the only data that can see it, and its first output improves the LIVE book.
First experiment: ZB 1-min, existing STEADY-7 post-impulse state only: touch curve + conditional-edge curve for d=1..8, h=30/60min, plus the same-bar resolution table. One afternoon; simultaneously validates the deployed pullback depth, stress-tests the fill model, and calibrates the method. Every result ships with a touch-must-exceed-limit-by-1-tick sensitivity row. No depth point reported with <300 fills.

T1.2 FILL-QUALITY CLOCK — execution-timing map
What: From 1-min data, per 30-min session bucket: touch probability at depth, post-touch expectancy, touch-minute velocity. Output is an execution policy (windows to pull orders, order lifetimes, velocity kill-switch), not a strategy. Asymmetric trust: it reliably identifies TOXIC fills; its "free money" windows stay unproven (queue position is invisible).
Why: priority 1 from three critics; highest value-per-line-of-code; protects STEADY-7 without touching its signals.
First experiment: replay STEADY-7 events, tabulate post-fill PnL by (session-third x touch-minute range tercile) — 9 cells, ~600-1,200 trades each, trimmed means + single-day jackknife. The monthly live-fill reconciliation job this spawns (sim-predicted vs Tradovate actual fills) becomes the program's supreme kill-switch metric with VETO power over all statistics.

T1.3 TRADE-AGE HAZARD CURVES — first deployable organic finding
What: Target-hazard and stop-hazard vs trade age from the trade archive, Kaplan-Meier with censoring. Outputs three rules already in the engine's exit vocabulary: derived max-age exit T*, dead-zone scratch (stale near-flat trades exited at a limit near entry), derived per-market flatten time.
Why: strongest sample-size position in the panel (1-D on ~11.6k trades), auditable by eye, zero new infrastructure. Priority 1-2 from all critics.
First experiment: PREREQUISITE — regenerate the full-history exit-free trade-path archive (stored logs like live_sim_results.json hold only small windows; every "pure log analysis" claim in the panel depends on this regeneration). Then plot both hazards for ZB/ZN calm regime + conditional win-rate vs (age, |PnL|<2 ticks). Deploy T*/scratch/flatten only after alternate-month AND chronological stability (+/-20% band) and agreement with T1.4's age-axis contour. Scratch deny-rate simulated with 1-tick market fallback charged.

T1.4 EXCURSION — the single shared exit library (absorbs In-Trade Hazard Model, Unified Hold-EV, Cloud Cartography, DP Excursion Atlas)
What: One (excursion e, age t, entry-state) hold/exit frontier built once, on the exit-free archive (the censoring bug: existing logs are truncated at incumbent brackets exactly where a new frontier would differ). Isotonic/monotone constraints; ~6x6 grid with >=300-TRADE floor per cell; strict dimension ladder (add a state axis only if it beats the simpler policy out-of-fold); incumbent fixed exits are the null, beaten only by a bootstrap-CI margin. Every frontier exit that is not a near-entry scratch is charged 1 tick market slippage.
Why: three lenses independently proposed this surface; the critics' unanimous instruction was build it ONCE. Pre-registered expectation, in writing: the frontier likely reproduces the incumbent exits (prior campaigns: adaptive targets lost, breakeven redundant) — that outcome is a PASS that validates the machinery, and the module's real alpha lives in T1.5.
First experiment: tabulate E[remaining net PnL | PnL-decile x age-quintile] from the regenerated archive; check whether the zero-contour reproduces the known 2-2.5x ATR stop / ~1x ATR target (the machinery-recovers-known-truth acceptance test, adopted campaign-wide).

T1.5 POST-FAILURE DRIFT ATLAS — canonical build (absorbs statistician Drift Maps, risk-engineer Atlas, Scar Harvest)
What: The user's "where does the market go after the strategy fails," done once with viable N: DISCOVERY on generic stop-shaped excursion events (5-10x population), actual STEADY-7 stop-outs as the VALIDATION subset only (the complement of a mined strategy shows anti-drift by construction — validation-fold trades only, +/-1-tick/+/-1-bar jitter test). Conditioning capped at two pre-declared dimensions (spike-vs-grind hit velocity, regime), regime-matched control bars so the estimate is the failure increment, day-clustered SEs (five stops in one cascade are one observation), monotonicity-in-conditioning required, independent ZB and ZN knees.
Why: all critics converged on this merged design; all three outcomes pay the live book (continuation -> maybe reversal layer; reversion -> current stops too tight, free money; nothing -> stops vindicated, branch closed).
Pre-registered economics: the stop-and-reverse limb pays ~2 slippage ticks + commission (~$66-70 ZB round trip) and must show >3 ticks net drift — expect it to die; the products are stop placement feedback and deeper limit re-entries (which recycle the freed margin slot).
First experiment: drift at 5/15/30/60/120/240 min after validation-fold stop-outs, split by time-to-stop terciles, ZB and ZN separately, bootstrap bands.

T1.6 ATLAS CORE — the entry-mining backbone (merges Conditional Forward-Path Atlas + firm ATLAS + Conditional Excursion Atlas + the Statistic Screen's library and nulls + AFTERMATH's event catalog + Bar-Anatomy's two best features)
What: One state atlas, one owner. Rank/percentile features from a pre-registered, hashed manifest (displacement z, vol ratio, position-in-range percentile, ATR percentile, time-of-day, VIX tercile; the statistic-screen library and <=2 anatomy features enter here as counted hypotheses). Cap: 3 state variables x <=4 bins (<=48-54 cells), pooled ZB+ZN. Occupancy floor: >=400 de-overlapped state-ENTRY episodes; >=200 effective for existence, >=500 for any per-cell parameter, else hierarchical fallback to pooled exits. Two conditioning modes: every-bar states, and the frozen 10-event AFTERMATH catalog (power-screened BEFORE freezing: any event with <200 expected discovery occurrences loses its splits or is dropped). Stage D: policies compile to the existing pattern-spec JSON and only the pessimistic fill engine's replay verdict counts.
Why: eight proposals across five lenses were this object; all survived, all were ordered merged.
Null-model fix (from the lookahead critic, mandatory): day-permutation of features is broken — rolling stats survive it. The null is feature/outcome MISALIGNMENT: circularly shift outcomes vs features by random whole-day offsets, plus matched-random-timestamp controls. Opening act: run the full pipeline on shuffled labels and confirm ~zero survivors — a pipeline never shown to return nothing when fed nothing cannot be trusted (the institutionalized same-bar-bug lesson).
First experiment: ZB+ZN, 3 features x 4x4x3 cells: 12-bar forward drift in ticks minus the full cost floor on Discovery, sign-stability check, survivor count vs misalignment-null count.

====================================================================
3. TIER 2 — BUILD IF TIER 1 SHOWS LIFE
====================================================================

T2.1 INTRA-BAR PATH ALPHABET (priority 3, survived all four critics). One of only two genuinely unmined information axes — prior campaigns were structurally blind to intra-5-min shape. k<=12 by bootstrap-ARI stability only; deterministic missing-minute rule registered (quiet ZB/ZN overnight minutes); mandatory regress-letters-on-range residual test AND time-of-day-matched baseline; drift measured from bar-close+1 actionable moment; letters route through TOUCHCURVE/EXCURSION. Sequence after the execution layer exists.

T2.2 EFFORT-VS-RESULT DIVERGENCE (priority 3, survived all four). The other unmined axis: absorption (high volume/low range) and vacuum, normalized by walk-forward minute-of-day baselines. Preconditions: volume-series audit (rolls, holidays, vendor quirks) and a research-vendor-vs-live-Tradovate volume parity test. Amputate the constant-volume-bar variant (one representation only). 9-cell OOS first experiment as designed.

T2.3 CROSS-MARKET DOUBLE-SORT (priority 3, survived all four; absorbs Orphan Moves). One 75-cell table: ZB 30-min forward return sorted on prior ES move x own move x VIX, day-block CIs, null = external-day permutation WITHIN vol strata (co-volatility must survive in the null), effect must survive lagging the external move one full 5-min bar, plus a research-side bar-clock alignment audit. Touch-conditional edge >=2 ZB ticks at >=30-min horizons or archive as real-but-untradeable. Regardless of outcome, run the free diagnostic: do STEADY-7 entries coincide with rates-cluster residual extremes? (Finally explains WHAT the edge is.) PCA machinery only if the double-sort shows monotone off-diagonal structure.

T2.4 DAILY-BIAS STATE MACHINE (priority 3, survived all four; the ONE day-bias vehicle). Transparent quantile states — the proven calm/elevated gate generalized. Start 3 states (overnight-drift terciles), pooled ZB+ZN, cap 6 forever, modulator/gate only, must beat the one-parameter AM-sign momentum baseline out-of-sample, calibration-before-profit reliability check, state-conditional exits only where floors are met. Imports: no-trade state (from Prototypes), posterior-collapse exit as one registered candidate. One clustering attempt (Day-Shape Taxonomy protocol: surrogate-null FIRST, k<=5, year-over-year assignment agreement) permitted only if the quantile machine finds day-level signal.

T2.5 SHAPE-RECURRENCE, GATED (kNN gatekeeper -> at most one symbolic run). The Embargoed kNN misaligned-null experiment runs ONCE as an offline existence diagnostic with de-overlapped queries (never deploys — per-trade neighbor exits categorically fail the 0.5-tick exit-precision floor). If dead: the entire pattern family (MOTIF, VOMM, k-medoids) closes, budget banked. If alive: ONE symbolic build — the VOM with <=12 letters, <=3-grams (MOTIF's 65k-word arithmetic is dead: ~0.4 effective occurrences/word), one encoding fixed a priori and hashed, studentized dispersion vs vol-preserving permutation, pooled exits only, pre-commitment in writing that a null closes symbolic mining permanently.

T2.6 VIRTUAL-SCALING LADDER (one shot, then closed forever). Pure post-processing of the regenerated archive: 3 pre-registered ladders + virtual-scaling (trail-tightening) vs fixed baseline on the pre-registered smoothness objective, week-bootstrap >80%. The 2-lot arm is amputated (halves concurrency on $4.1k, damaging the diversification that actually smooths the curve). Portfolio-level scoring including concurrency displacement.

One-shot closure tests (run cheap, expect death, cite forever): Touch-and-Reject first-touch vs random-price control (3 cells; if levels don't beat matched random prices, the level branch closes permanently alongside the pivot/prior-day negatives). Wick Forensics dies with it, except its GC/CL depth-monotonicity probe, whose only interesting outcome is a new tradeable market.

====================================================================
4. GRAVEYARD (do not re-litigate)
====================================================================

- Session-Shape Posterior: killed 4/4 — ~600 days cannot fund clustering + intraday posterior + calibration; its own acceptance test is underpowered. (Salvaged: calibration-before-profit gate; posterior-collapse exit as a registered candidate.)
- Day-Shape Prototypes: killed 3/4 — ~70 days/prototype; its own AM-sign baseline is nearly unbeatable. (Salvaged: that baseline, and the no-trade state.)
- Day-Shape Taxonomy as standalone: same 600-day pond; survives only as the single conditional clustering attempt inside T2.4. (Salvaged: surrogate-null-FIRST sequencing.)
- Shape-Cluster k-medoids Atlas: 24:1 window overlap -> ~45 effective/cluster/era; re-encodes displacement+vol with extra hyperparameters. (Salvaged: max-statistic-vs-max-statistic surrogate null; 3-era stability clause.)
- MOTIF as specified: 65,536 words vs ~26k effective windows = 0.4 occurrences/word. (Salvaged: one-encoding-forever clause, 20-fires/week compile floor.)
- HMM Regime Playbooks: multimodal EM + state relabeling = the unstable-fitting class; likelihood states re-discover vol buckets VIX already provides. (Salvaged: stop-as-regime-classifier concept, re-expressed in EXCURSION without the HMM.)
- Bar-Anatomy Drift Table: 18,750 cells vs ~6 bars/cell; re-tests the falsified candle family. (Salvaged: 2 features into the atlas manifest; shrinkage-toward-market-mean clause; "fifty survivors = broken pipeline" heuristic.)
- DP/Value-Iteration Exit Atlas: DP amplifies cell noise; (e,t) is not Markov — path history matters, which is the post-failure module's founding fact. (Salvaged: random-entry exit-null; DP-value-at-origin as tie-breaker metric.)
- Orphan Moves PCA layer: nightly refit = quiet retraining; 24-market alignment swamp; fires precisely at news where touch=fill is most wrong. (Diagnostic regression kept in T2.3.)
- Standalone KS Statistic Screen, standalone Excursion Atlas (1-min), Cloud Cartography, Hold-EV surface, both duplicate Post-Failure atlases, Scar Harvest, Wick Forensics, Conditional Excursion Atlas: not wrong — DUPLICATES, merged into T1 modules. Building any of them separately is an untracked degree of freedom.
- Stop-and-reverse entries generally: ~2 slippage ticks + commission ≈ $66-70 ZB round trip vs a ~$15/trade edge scale — pre-registered to die unless post-failure drift >3 ticks net.

====================================================================
5. THE VALIDATION PROTOCOL
====================================================================

SPLITS (chronological, purged; committed before any mining):
- Discovery: data start (~2024-02) through 2025-05-31 (~55%)
- Embargo: sized from measured vol-autocorrelation decay (expect 2-4 weeks; computed, not guessed; must also cover the longest holding period)
- Validation: 2025-06 through 2025-12 (~25%). Reusable but every evaluation is ledger-logged; validation floor = N* trades (NOT N*/3 — a 100-trade validation cannot exclude zero for a $15 edge).
- Test: 2026-01 through present (~20%). Files SHA-256 hashed in git, physically absent from miner code paths. Metered budget: 5 lookups for the entire campaign, each logged, each consumed forever; a failed look kills the candidate with no repair. NO lookup may be spent on a candidate whose expected test-window trade count < N*: underpowered candidates go to extended shadow instead.
- Odd/even weeks: intra-Discovery consistency checks only, with a co-equal chronological half-split.

FLOORS (calibrated by the N* bootstrap, first script of the campaign; recomputed per exit-geometry class, separately for ZB and ZN):
- >= max(300, N*) discovery occurrences; >= N* validation; spread over >=60% of weeks; no week >10% of PnL, no day >5%; VIX-stratified sign check.
- Effective N counted in de-overlapped episodes / trades / days — never bars.
- Below-floor states discarded UNSCORED (unfalsifiable states cannot re-enter through the back door).
- Exit quantiles: bootstrap CI < 0.5 ticks or fall back to pooled exits (this rule alone mechanically kills per-trade exits from small neighbor clouds).
- Effect floor: commission + stop-rate x 1-tick slippage + 0.5-tick buffer, in ticks, per market; touch-conditional.

NULLS (all three constructions must pass; ledger-sized max-statistic):
1. Feature/outcome misalignment: circular whole-day shifts of outcomes vs features (replaces the broken day-permutation null).
2. Joint cross-market day-block bootstrap surrogates (~200), whole REAL days resampled jointly across markets (preserves OHLC integrity, vol clustering, cross-market simultaneity), full frozen pipeline re-run; real best-candidate must beat surrogate 95th-percentile best-candidate (max vs max).
3. Matched-random-entry: identical exit logic at random timestamps matched on time-of-day, trailing vol, VIX. The sharpest test in the program — it isolates timing skill from "wide-stop/small-target geometry wins at random times in a reverting market," the exact confound of the incumbent edge's shape. Post-failure claims face matched-random-stop-out versions.
- Controls before use: STEADY-7 (scored on post-selection data only) must pass; planted junk must fail. STEADY-7 failing later = the family got too big -> budget review, never threshold relaxation.
- Ledger partitioned into pre-registered per-module families with candidate-count caps derived from the power math (one global family would eventually reject everything by bookkeeping). Human map-browsing sessions are ledger entries.

PRE-REGISTRATION: pipeline-as-code, git-hashed; the runner refuses unregistered pipeline hashes; result files embed pipeline + fill-engine hashes; any fill-engine change mechanically voids all prior results in CI, no grandfathering. Every registration states its reachable-candidate count, checked against the power budget before approval. EVERY first experiment — including "one afternoon" scripts — gets a one-paragraph registration and ledger entry BEFORE running. Consistency-battery thresholds (split-half correlation, Jaccard region overlap, +/-20% plateau degradation) are calibrated empirically from what STEADY-7 scores, not set by fiat. The plateau test applies to every derived number in every module.

PROMOTION LADDER (a state becomes a live sleeve only by climbing; criteria written before the climb):
- Rung 1: floors + consistency battery + full gauntlet on Discovery+Validation.
- Rung 2: one metered Test look (power-checked first), pass/fail against pre-stated numbers. Failure is terminal.
- Rung 3: shadow mode >=4 weeks AND >=N*/5 trades via a dry-run broker in engine/brokers/; match tolerance defined numerically per field IN ADVANCE (entry price exact, fill flag exact, timestamp within one bar). An entry that can't be reproduced bar-for-bar live is by definition an artifact.
- Rung 4: live 1 lot, <=20% of portfolio margin, fill-rate SPRT (25-40 touches to detect a 10% fill shortfall — compute the exact number now and publish it so nobody shortens Rung 3). Kill switches: CUSUM on live-vs-sim MAE distributions, cumulative PnL below the sim bootstrap 5th-percentile band, 4 consecutive negative weeks (accepting the pre-computed ~30%/yr false-kill rate for marginal sleeves).
- Standing rules: live data can only DOWNGRADE belief, never upgrade it. Demote-don't-tweak: live sleeve parameters are hash-pinned read-only artifacts; any modification re-enters at Discovery. Max ~6 concurrent sleeves with family-wise-adjusted thresholds. Monthly exit re-derivation constrained by CUMULATIVE drift since freeze (no band-ratchet random walk). The monthly live-fill reconciliation report holds veto power over everything the statistics promote — fill quality is the one risk statistics cannot see.

====================================================================
6. PIPELINE
====================================================================

Stage 0 — GOVERNANCE (week 1): split manifest + hashes, ledger, registration harness, N*, embargo measurement, gauntlet controls, noise-floor calibration. Plus the one shared prerequisite: regenerate the full-history exit-free trade-path archive from the campaign replay code (every "existing logs" claim depends on it — current stored logs are small windows).

Stage 1 — EXECUTION SCIENCE (weeks 1-3, protects the live book even if all discovery dies): TOUCHCURVE + Fill-Quality Clock on ZB/ZN 1-min. Ships as JSON policy tables consulted by the existing order layer (bot/tradovate_orders.py, bot/tradovate_bars.py). Stand up the monthly live-fill reconciliation GitHub Actions job immediately.

Stage 2 — EXIT SCIENCE (weeks 2-5): Trade-Age Hazards first (deployable rules: T*, dead-zone scratch, flatten time), then the EXCURSION frontier, then Post-Failure Atlas. Outputs are bracket numbers + a <=4-step trail table + one new engine primitive (limit-scratch order), all within existing Tradovate order-modification machinery. Shadow-mode against live STEADY-7 positions via the dry-run broker.

Stage 3 — ENTRY MINING (weeks 4-10): ATLAS core (every-bar states + AFTERMATH event catalog + statistic-screen manifest), under the misalignment null and ledger. New live-side component: one causal rolling-percentile feature buffer, with a mandatory research/live feature-parity test (same bars through both code paths -> identical state labels) — the classic silent-bug site.

Stage 4 — POLICY COMPILE + PESSIMISTIC REPLAY: surviving cells -> TOUCHCURVE depth -> EXCURSION exits -> frozen JSON in the existing pattern-spec format (bundled/deployed_strategies.json) -> Stage-D replay on Validation by the fill engine only.

Stage 5 — PORTFOLIO + GRADUATION: deployability knapsack on $4.1k — margin per contract, p95 concurrency <=4-5 lots, ZB/ZN correlation haircut (one bet), scored by weekly consistency and maxDD before profit, $/margin-dollar-day. Promotions land as reviewable PRs changing only the strategy JSONs, evidence chain linked in the ledger.

GitHub Actions: (1) monthly deterministic full-factory rerun, pinned data hash + pipeline commit + seeds, diffable vs last month; (2) quarterly lockbox/Test evaluation in a separate workflow with a separate data artifact; (3) weekly live-vs-sim reconciliation + fill SPRT.

Tier 2 modules slot into Stage 3 as additional registered conditioning families, sequenced: intra-bar alphabet and effort/result (new axes) first, cross-market double-sort next, day-bias machine in parallel (it is cheap), shape-recurrence only behind the kNN gate.

====================================================================
7. DECISION POINTS FOR THE USER
====================================================================

1. Test-set budget: 5 lookups for the entire campaign, quarterly lockbox cadence, and the rule that underpowered candidates can never spend one. This is a real constraint you will feel. Recommendation: accept 5; the pressure to peek is the failure mode that kills programs like this.

2. Sequencing: execution/exit science first (Stages 1-2, improves the live book with near-certainty) vs entry mining first (new edges, high failure probability). Recommendation: execution first — TOUCHCURVE + Clock + hazard exits are the only work in the panel whose expected value is positive under the null that no new edge exists.

3. The unfalsifiability rule: validation floor = N* (~250-450 trades) means rare, seductive setups are discarded UNSCORED, forever. This pushes the program hard toward frequent small states (your frequency priority) and away from "this fired 9 times and won 8". Recommendation: accept; the alternative is the multiple-comparisons trap wearing a costume.

4. 2-lot scaling: amputated in favor of virtual scaling (stop-tightening schedules, zero commission, zero engine risk). Reverses only if you'd accept halving concurrent positions on $4.1k. Recommendation: virtual only; diversification across sleeves is where your smoothness actually comes from.

5. Non-rates spend: discovery restricted to ZB/ZN; GC/CL get exactly one option-value probe (wick depth-monotonicity). Recommendation: accept — 18+ markets are cost-dead at these horizons and mining them only inflates the null bar every real candidate must clear.

====================================================================
8. HONEST EXPECTATIONS
====================================================================

What this program is likely to deliver:
- Near-certain: execution-layer value — measured resting depths, toxic-window avoidance, order lifetimes, and an audited fill model — protecting the ~$15/trade incumbent edge whose entire existence is fill quality. This pays even if every discovery module returns null.
- Probable: exit-science refinements at the margins — a derived T*, a dead-zone scratch, post-failure stop feedback — worth smoothness more than dollars. The pre-registered expectation is that the full derived frontier MATCHES the tuned fixed exits (prior campaigns' adaptive-target and breakeven nulls are the prior), and matching is a pass.
- Plausible: a re-parameterized STEADY-7 with data-derived levels replacing grid-searched ATR multiples on the same execution machinery, plus a limit re-entry layer after shakeout stops.
- Possible but unlikely: genuinely new states from the two unmined axes (intra-bar shape, effort/result) or cross-market conditioning — the only places in the data prior campaigns were structurally blind.
- Very unlikely: new tradeable markets, day-level bias with real content (~600 days is the hard ceiling), shape/motif alpha, or anything from the level-trading family.

What it cannot change: the data is the same 2.2-2.5 years the 7B-config campaigns already mined. Organic discovery is not a new information source; it is a lower-multiplicity, better-counted re-interrogation, with post-hoc freedom that is statistically MORE dangerous per hypothesis, held in check only by the governance stack. If the honest output of the whole program is "the incumbent edge, better executed, with validated exits and a calibrated null that nothing else clears" — that is not failure. That is the 34-family template result confirmed from the other direction, an executed edge protected against its one existential risk, and the multiple-comparisons ledger closed with a clean conscience.
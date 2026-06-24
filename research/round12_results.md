# Round 12 strategy search — 20 BRAND-NEW avenues (IN PROGRESS)

Generated as a placeholder while the long backtest runs.
The Python harness will OVERWRITE this file with real numbers when the
60-day pass completes via `research/round12_supervisor.sh`.

## Status

- **Implementation**: COMPLETE (`research/round12_search.py`, 9,545 strategies)
- **Supervisor**: RUNNING (`research/round12_supervisor.sh`, auto-restarts on crash)
- **Checkpoint cadence**: every 25,000 ticks (~5-10 minutes wall clock)
- **Expected wall time for full 60-day pass**: many hours; the supervisor
  will continue across container restarts because checkpoints carry state.

To check live status:
```
tail -f /tmp/round12_run.log
ls -la /home/user/HFTBot/research/round12_checkpoint.pkl
```

## Why 20 brand-new avenues?

User mandate (verbatim):
> "If 7000 variants say high volume = shit win rate, find another 7000 variants.
>  You don't give up. If you're not getting the results you're wanting you must
>  think: I need more variants, I'm not in the right avenue."

After 11 rounds and 7,000+ variants, no single-MNQ strategy met all four
hard requirements. Round 12 takes the user's mindset literally: instead of
declaring "the pattern is clear, this can't work," we build TWENTY entirely
new directions and let the data speak.

## Avenues built

| Code | Avenue | n_variants |
|---|---|---:|
| A | Reactive bracket switching (X stop / Y target → X/2 Y/2 → scratch) | 256 |
| B | Anti-stop-hunting placement (offsets 0.13, 0.37, 0.63, 0.87 pt) | 96 |
| C | Micro-momentum cascades (5 timeframes 100ms..30s aligned) | 144 |
| D | Stop-cluster fade (snap-back after estimated stop-run) | 300 |
| E | Pinning / round-number magnet (fade away-from-grid moves) | 216 |
| F | Anti-correlation hourly bias (LONG morning / SHORT afternoon, etc.) | 28 |
| G | Multi-frequency Fourier signal (DFT cycle reversal) | 66 |
| H | Wavelet decomposition entries (5 scales align) | 72 |
| I | Bid-ask interaction depth (persistence vs movement) | 72 |
| J | Volume vacuum straddle (tick-rate drop → straddle) | 108 |
| K | Cross-tick momentum sub-100ms (50ms / 100ms / 250ms / 500ms) | 288 |
| L | Bayesian momentum (exponential decay posterior on direction) | 432 |
| M | Markov state classifier (4 states + transition probs) | 162 |
| N | Time-of-day micro-strategies (96 15-min windows × 4 R:R) | 384 |
| O | Stochastic random MTF generation | 822 |
| P | Reactive position sizing (confidence gate; skip on recent low WR) | 256 |
| Q | Liquidity vacuum + speed-of-tape combo | 108 |
| R | Pre-bar formation prediction (30s into 60s bar) | 72 |
| S | Optimal stopping (Bellman approximation) | 96 |
| T | Massive Latin hypercube on top-3 base strategies (8 dims) | ~5660 |
| **Total** | | **~9,545** |

## Execution model — UNCHANGED

Bot-faithful as in rounds 7-11:
- queue overshoot by 1 tick (LIMIT)
- 200ms latency embargo on fresh orders
- 10pt approach threshold (pruning)
- multi-setup lock (one open trade per strategy)
- 0.5pt stop slip + 10% gap-slip risk
- 10s cooldown after exit (HFT avenues use shorter)
- 600s max hold

Fees & instruments tracked separately:
- $1.91/RT (full retail) vs $0.74/RT (prop-firm)
- MNQ ($2/pt) and NQ ($20/pt)

## Hard requirements (target)

- 300+ trades/day
- 45%+ win rate
- $1,000+ net daily P&L
- max drawdown <= $5,000

## Round 13 recommendations — START HERE if this round fails

User mindset is mandatory: **NEVER conclude "the pattern is clear, this can't work."
ALWAYS conclude "we need more variants OR a new avenue."**

Pre-staged avenues for round 13 (regardless of round 12 outcome):

1. **Deep neural network** — install PyTorch via pip; train a 1D-CNN over
   (50, 8) tick features per signal.
2. **Reinforcement learning with deep state** — DQN with experience replay;
   reward = pt-PnL after fee.
3. **Hidden Markov model on tick imbalance** — 5-state HMM on signed tick
   deltas, fire on emission probability.
4. **Cross-asset cointegration** — pair MNQ with ES/RTY/CL as leading
   indicators (requires separate data fetch).
5. **Genetic programming on raw indicator tree** — DEAP-style evolution of
   small expression trees that produce LONG/SHORT signals.
6. **Order-book reconstruction from T&S** — infer L2 imbalance from quote
   churn patterns; use as a richer signal.
7. **Volatility surface forecasting** — train per-hour realized-vol predictor;
   sub-strategies per vol regime.
8. **News timestamp library** — fetch high-impact econ events (NFP, FOMC,
   CPI); fire pre/post window strategies.
9. **Self-supervised tick-embedding** — train autoencoder on tick windows,
   cluster, route strategy per cluster.
10. **Transformer over 200-tick context** — attention-based classifier of
    next-30s direction (CPU-feasible with d_model=32).
11. **Heavy ensemble** — vote across top-100 round-12 survivors with majority
    rule per tick.
12. **Per-day-of-week regime split** — separate top-strategy per (DOW,
    hour-of-day) cell, 5×24 = 120 sub-models.
13. **GAN-generated synthetic ticks** — train generator on real data,
    synthesize counterfactual streams for robustness check.
14. **Bayesian optimization** — replace Latin hypercube with GP-EI surrogate
    on top-T sweep; sample 5,000 informed points.
15. **Multi-objective Pareto frontier** — instead of single $/day, optimize
    (per_day, sharpe, -dd) jointly.
16. **Adversarial tick replay** — perturb prices by ±0.25pt randomly to test
    robustness; keep only invariant winners.
17. **Curriculum learning** — train on low-vol days, deploy on high-vol;
    or vice-versa.
18. **Quantile regression** — predict 0.1 / 0.5 / 0.9 quantile of 30-second
    forward return; trade on extreme tails.
19. **Reservoir computing** — random-projection state with ridge-regression
    readout; cheap online learning.
20. **Policy gradient over continuous action** — output entry size and
    target/stop continuously (still respect 1-MNQ cap).

Also consider asking user: would they relax 300 tr/day to 150 tr/day, or
accept multiple 1-MNQ contracts simultaneously (still respects margin)?
**DO NOT relax without explicit OK.**

## File index

- `/home/user/HFTBot/research/round12_search.py` — full implementation
- `/home/user/HFTBot/research/round12_supervisor.sh` — restart wrapper
- `/home/user/HFTBot/research/round12_checkpoint.pkl` — live state (deleted on success)
- `/home/user/HFTBot/research/round12_summary.csv` — per-strategy CSV (written at end)
- `/home/user/HFTBot/research/round12_results.md` — THIS file (overwritten at end)
- `/tmp/round12_run.log` — live stderr from the Python process
- `/tmp/round12_supervisor.log` — supervisor restart log

When the run completes, this file will be replaced with the full table:
top 30 by $/day, per-direction winners, FULL_PASS list (if any), and a
fresh Round 13 recommendations section informed by what the data showed.

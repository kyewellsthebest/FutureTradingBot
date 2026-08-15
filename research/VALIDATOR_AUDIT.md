# Validator audit: three attacks on the causal engine

## 1. Sensitivity (planted edge): PASS
- synthetic tape with deterministic +8pt bounces at the 0.618 levels: **$+629** on 64 trades, 66% wins
- the engine detects a real edge when one exists

## 2. Bias (random walk, zero costs): PASS
- gross expectancy on a pure random walk: **$+0.86/trade** over 73 trades (win rate 52%)
- fills are fair: no manufactured losses

## 3. Bias (real Friday tape, zero costs): PASS
- gross expectancy: **$+0.90/trade** over 29 trades (win 48%) -- the signal itself is ~random; losses in the full model are the cost stack, not fill bias

## 4. Staleness placebo (30-min-delayed signals): PASS
- fresh: $-21/29 · stale: $-1,029/26
- no timing leak: stale does not beat fresh

Every attack the engine survives strengthens the family-search verdicts below it; any FAIL above voids them.


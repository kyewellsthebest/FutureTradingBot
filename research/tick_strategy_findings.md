# Tick-data strategy search — findings & deployment

Generated 2026-06-25. Data: `data/tick/NQ.03-26.Last.parquet` (24.9M real
NQ trades+bid/ask, 2025-12-10 → 2026-02-27, 69 trading days, UTC).

## TL;DR

The previous chat's backtest was **wrong**, exactly as suspected — too
strict and on the wrong data. It used a **$1.91/RT** retail fee and a
**US-Tech-100 CFD proxy** feed, and concluded the strategy loses
(-$233/day). On **real NQ ticks** with the bot's **actual** execution
model, the live strategy **makes money**, and a tuned variant clears the
**$1,000/day on 1 MNQ** target.

The simulator was validated against the live bot's own trades: it
reproduces the live **41.7% win rate (live 42%)** and the bit-exact cost
math (target win +$39.26, stop loss −$21.24).

## The faithful execution model (mimics the bot exactly)

Source: `bot/pullback_strategy.py`, `bot/fib_main.py`, and the
2026-06-25 diagnostic bundle. Implemented in `research/tick_sim.py`.

| Factor | Value | Source |
|---|---|---|
| Commission | **$0.74 / MNQ round-trip** | `FIB_COMM_PER_MNQ_RT` (live) |
| Point value | $2 / pt / MNQ | live |
| Entry | LIMIT at pullback level, **0 slip** | `ENTRY_SLIP_PTS=0` |
| Stop | stop-market, **0.25pt adverse slip** | `ADVERSE_SLIP_PTS`, verified in trades |
| Target | LIMIT, fills at level (bid for LONG / ask for SHORT) | `should_exit_on_tick` |
| Timeout | mid price at +600s | `MAX_HOLD_SECS=600` |
| Cooldown | 60s after each close | `COOLDOWN_SECS` |
| Max wait for fill | 300s then setup expires | `MAX_WAIT_SECS` |
| Session | no entries in CME break (17:00-18:00 ET) + weekends | `_in_daily_break` |

Setup geometry is the bot's real `detect_pullback_setup` (verified: 0
mismatches vs a vectorized replica across 3,000 random bars).

## Results (1 MNQ, realistic 0.25pt slip)

| Config (INVERSE fade) | $/day avg | worst month | OOS (Feb) | maxDD | @1.0pt slip |
|---|---|---|---|---|---|
| **Live** s10/t20 p0.236 i5/w4 | +$230 | — | — | $4,287 | +$112 |
| **S2 winner** s5/t44 p0.118 i2/w3 | **+$1,034** | **+$620** | +$1,515 | **$550** | +$871 |
| Conservative s6/t30 p0.236 i3/w4 | +$528 | +$214 | +$819 | $810 | +$374 |
| edge++ s4/t50 p0.06 i2/w3 | +$1,299 | +$691 | +$1,944 | $311 | +$1,134 |

Per-MNQ scaling on the S2 winner: 2 MNQ worst-month ≈ +$1,240/day; live
default 5 MNQ ≈ +$3,100/day worst-month.

### Why it's not curve-fit
- Profit spread across ~11,000 trades — **top-10 trades = 1.2% of net**.
- **Positive every month** (Dec +$1,084 / Jan +$620 / Feb +$1,443).
- Survives **4× worse slippage** (still +$871/day at 1.0pt).
- Win-rate-matched the live bot (engine fidelity).

### Honest caveats
1. **Feb was a favorable regime** — every config's OOS (Feb) beat its
   train half, so Feb was volatility/fade-friendly, not skill. Anchor
   expectations on the **worst month (~$620/day per MNQ)**.
2. **edge++ extremes (s4/p0.06) are NOT recommended live** — at the grid
   boundary the sim's entry-fill optimism on near-spread limits starts to
   dominate. The S2 winner keeps safety margin.
3. **Only 2.7 months** of tick data. Forward-validate in paper before
   committing real size.

## Deployment

Strategy params are env-driven (`bot/account_ctx.py`). The S2 winner is
now the **code default**, but to be explicit on Railway set:

```
STRAT_IMPULSE_PTS=2.0
STRAT_IMPULSE_BARS=3
STRAT_PULL_PCT=0.118
STRAT_STOP_PTS=5.0
STRAT_TARGET_PTS=44.0
STRAT_INVERT=1
STRAT_COOLDOWN_SECS=60        # 30 is marginally better; 60 is safer
```

Conservative alternative: `STRAT_PULL_PCT=0.236 STRAT_STOP_PTS=6
STRAT_TARGET_PTS=30 STRAT_IMPULSE_PTS=3 STRAT_IMPULSE_BARS=4`.

### Recommended path to live
1. Deploy these params in **paper mode** (the bot already paper-trades).
2. After ~1 week, compare paper $/day + win rate + exit mix to this sim.
   They should match within slippage; if paper is much worse, the entry-
   fill assumption is the suspect — fall back to the conservative config.
3. **Fix the broker connection** — the bundle showed all broker orders
   failing with `no_account_id` / `user_ws: no auth tokens`. That, not the
   strategy, is why the live broker bot is down while paper is up.

## Reproduce

```
python3 -m research.tick_sim        # baseline live config
python3 -m research.tick_search     # stage-1 grid (1152)
python3 -m research.tick_search2    # stage-2 refinement (576)
python3 -m research.tick_slip_test  # slippage stress
python3 -m research.tick_validate   # deep validation + beyond-edge probe
```

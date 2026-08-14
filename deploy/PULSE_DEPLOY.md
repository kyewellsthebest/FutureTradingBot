# Pulse deployment — the validated parameters (2026-08-14)

Two instances of `bot/fib_main.py` (the impulse-pullback executor in
`bot/pullback_strategy.py`), one per market, DEMO account, $4,000 reset.
Old strategies retired; old stats/history cleared at cutover.

## Instance 1 — MNQ (validated: +$20,701 held-out, 142/wk, 8/8 q, DD $393)

    STRAT_IMPULSE_PTS=5.0
    STRAT_IMPULSE_BARS=6
    STRAT_PULL_PCT=0.618
    STRAT_STOP_PTS=10.0
    STRAT_TARGET_PTS=20.0
    STRAT_COOLDOWN_SECS=60
    # MAX_HOLD_SECS=600 (in code), INVERT off, RTH only, 1 MNQ

## Instance 2 — MES (validated: +$5,976 held-out, 136/wk, 6/6 q)

    STRAT_IMPULSE_PTS=1.5
    STRAT_IMPULSE_BARS=6
    STRAT_PULL_PCT=0.618
    STRAT_STOP_PTS=3.0
    STRAT_TARGET_PTS=6.0
    STRAT_COOLDOWN_SECS=60
    # MAX_HOLD_SECS=600, INVERT off, RTH only, 1 MES (tick 0.25 same as MNQ)

## Validation chain both cells passed

1. tick-true fills: entry only when tape trades through the limit, on the
   correct side of the book; 250ms latency; no pre-crossed windows
2. gap-aware stop pricing + 1 tick slip; spread charged on timeouts
3. bar-label look-ahead audited and excluded (cost the fake +$51k)
4. placebo control: machinery under null loses -$60/trade -- profit
   requires the fresh-impulse signal; nothing in the plumbing invents it
5. both directions tested; fade fills are wrong-side fictions, never traded
6. 14 quarters across two independent markets, all green held-out

## Shadow protocol (first week)

Compare every live demo fill/exit against the model's prediction; the
backtest is believed only where reality agrees. Expected at $0.18 comm
(membership): NQ ~$648/wk, ES ~$450/wk equivalent-scale; at current
$1.24: ~$500 + ~$310.

## Remaining wiring before cutover

- fib_main currently single-instance MNQ: run second process with MES env
  (symbol/env plumbing to verify) and RTH gate check vs validation window
  13:30-20:00 UTC
- wipe data/ stats + trade history at reset; confirm account shows $4,000

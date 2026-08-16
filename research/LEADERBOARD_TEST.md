# The leaderboard configs, run through the validated engine

A second Claude published a leaderboard claiming **$984-$1,034 per day** per MNQ from the INVERSE FADE, with out-of-sample halves at $1,430-$1,590/day. This runs those exact parameters through `causal_engine.run_cell` -- the engine that reproduced the live bot's trade list 29/29 on real tape and that found a planted synthetic edge when one was hidden in the data.

NQ, 8 quarters, 727 RTH sessions, $1.33 round trip (the confirmed real cost), 10-minute window, timeouts marked to market.

**The one thing under test is where an against-the-impulse entry fills.** The strategy sells at a level BELOW the market. Such an order is either a STOP -- filling at the print that triggered it, several points past the level on NQ -- or a MARKETABLE LIMIT, which executes immediately at the bid on every signal. What it cannot be is an order that waits below the market and fills at its own price only when price comes down to meet it. That last one is the assumption under test.

| anchor | config | at-level $/day | honest $/day | at-level $/trade | honest $/trade | trades/day |
|---|---|---|---|---|---|---|
| range | 1 S2-WINNER | $+147 | **$-72** | $+6.02 | $-2.97 | 24 |
| range | 2 T36-W4 | $+171 | **$-65** | $+7.02 | $-2.66 | 24 |
| range | 3 T30-W4 | $+167 | **$-66** | $+6.85 | $-2.71 | 24 |
| range | 4 T36-W3 | $+144 | **$-69** | $+5.92 | $-2.83 | 24 |
| range | 5 T30-LOWDD | $+143 | **$-68** | $+5.85 | $-2.79 | 24 |
| range | 6 CONSERV | $+67 | **$-66** | $+2.81 | $-2.80 | 24 |
| range | - CANON live | $+49 | **$-79** | $+2.14 | $-3.46 | 23 |
| close | 1 S2-WINNER | $-27 | **$-76** | $-1.13 | $-3.17 | 24 |
| close | 2 T36-W4 | $-31 | **$-77** | $-1.28 | $-3.20 | 24 |
| close | 3 T30-W4 | $-29 | **$-76** | $-1.19 | $-3.17 | 24 |
| close | 4 T36-W3 | $-27 | **$-76** | $-1.11 | $-3.15 | 24 |
| close | 5 T30-LOWDD | $-25 | **$-74** | $-1.05 | $-3.06 | 24 |
| close | 6 CONSERV | $-26 | **$-71** | $-1.12 | $-3.05 | 23 |
| close | - CANON live | $-39 | **$-80** | $-1.75 | $-3.56 | 22 |


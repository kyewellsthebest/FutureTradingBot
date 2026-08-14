# Trades joined to the live quote

Two numbers this repo has been asserting rather than measuring: what the spread actually costs, and how often the tick rule guesses the aggressor correctly. Every cost figure charges 2.5 ticks of slippage, but that came from an estimate — the account has only traded on the simulator, which fills at the requested price. And every order-flow feature, `f_ofi` included, infers the aggressor from the last price change instead of knowing it.

## 2026-06-10 — `NQM6`

565,797 trades.

| | measured | what the repo assumed |
|---|---|---|
| median spread | **7.00 ticks** ($3.50 to cross one way) | 2.5 ticks, $1.25 per round turn |
| tick-rule accuracy | **84.1%** | ~85% |
| spread = 1 tick | 1.5% of trades | — |
| median top-of-book | 1 bid / 1 ask | — |
| aggressive buys | 10.6% | — |
| between the quotes | 79.0% | — |

## 2026-06-10 — `NQM6`

565,797 trades.

| | measured | what the repo assumed |
|---|---|---|
| median spread | **7.00 ticks** ($3.50 to cross one way) | 2.5 ticks, $1.25 per round turn |
| tick-rule accuracy | **84.1%** | ~85% |
| spread = 1 tick | 1.5% of trades | — |
| median top-of-book | 1 bid / 1 ask | — |
| aggressive buys | 10.6% | — |
| between the quotes | 79.0% | — |

## 2026-06-10 — `NQM6`

565,797 trades.

| | measured | what the repo assumed |
|---|---|---|
| median spread | **7.00 ticks** ($3.50 to cross one way) | 2.5 ticks, $1.25 per round turn |
| tick-rule accuracy | **84.1%** | ~85% |
| spread = 1 tick | 1.5% of trades | — |
| median top-of-book | 1 bid / 1 ask | — |
| aggressive buys | 10.6% | — |
| between the quotes | 79.0% | — |


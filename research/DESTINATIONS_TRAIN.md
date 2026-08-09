# Where does price actually go? Ten destinations, named in advance

Searching 103,680 strategies made the answer worse, not better — the best of 81,348 came in below what chance produces, and the one coherent family retained −19% on data it had not been selected on. Testing more guarantees the winner is luckier, not better. So this tests **ten** things, every one named before looking, and reports all ten.

**The design that removes the argument.** The target sits ON the destination and the stop sits at EXACTLY the same distance the other way. Symmetric barriers on a driftless walk win exactly 50% — not approximately, exactly, by the reflection principle. So the entire result is one number per row: `hit − 50%`. Positive means price genuinely seeks that place. The shuffled tape beside it must read 50% or the instrument is broken.

Held-out NQ contracts, 389 trading days, an entry sampled every 600 price changes.

| destination | trades | median distance | **hit rate** | **vs the 50% coin flip** | shuffled tape | unresolved |
|---|---|---|---|---|---|---|
| swing high R=20 | 119,033 | 18.0 pts | 44.13% | **-5.87 pp** (se 0.14) | 44.32% | 1% |
| swing low R=20 | 115,974 | 19.0 pts | 44.78% | **-5.22 pp** (se 0.15) | 44.36% | 1% |
| swing high R=8 | 125,238 | 9.0 pts | 45.57% | **-4.43 pp** (se 0.14) | 46.14% | 0% |
| swing low R=8 | 126,198 | 9.2 pts | 46.07% | **-3.93 pp** (se 0.14) | 46.28% | 0% |
| prev session high | 25,554 | 24.8 pts | 51.58% | **+1.58 pp** (se 0.31) | 50.77% | 2% |
| session low so far | 6,245 | 24.2 pts | 51.39% | **+1.39 pp** (se 0.63) | 48.80% | 0% |
| session high so far | 13,792 | 22.2 pts | 51.28% | **+1.28 pp** (se 0.43) | 50.34% | 3% |
| round 100pt above | 65,783 | 25.8 pts | 49.31% | **-0.69 pp** (se 0.19) | 50.28% | 2% |
| round 100pt below | 66,471 | 25.5 pts | 49.58% | **-0.42 pp** (se 0.19) | 50.03% | 2% |
| round 25pt above | 129,798 | 13.5 pts | 49.73% | **-0.27 pp** (se 0.14) | 50.17% | 0% |
| prev session low | 16,660 | 26.2 pts | 50.24% | **+0.24 pp** (se 0.39) | 49.23% | 1% |
| prev session close | 35,718 | 23.5 pts | 49.90% | **-0.10 pp** (se 0.26) | 49.97% | 2% |
| round 25pt below | 129,675 | 13.5 pts | 50.08% | **+0.08 pp** (se 0.14) | 50.04% | 0% |
| session VWAP | 29,295 | 22.2 pts | 50.03% | **+0.03 pp** (se 0.29) | 49.07% | 1% |

A destination is worth trading only if its deviation is several times its standard error AND the shuffled column sits at 50%. Anything else is the instrument, not the market.

### What a real one would be worth

At a symmetric bracket, expectancy is `(2p − 1) × distance × $2/point`. Against the $1.99 toll, a destination 20 points away needs **52.5%** to break even, and one 40 points away needs **51.2%**.

# Where does price actually go? Ten destinations, named in advance

Searching 103,680 strategies made the answer worse, not better — the best of 81,348 came in below what chance produces, and the one coherent family retained −19% on data it had not been selected on. Testing more guarantees the winner is luckier, not better. So this tests **ten** things, every one named before looking, and reports all ten.

**The design that removes the argument.** The target sits ON the destination and the stop sits at EXACTLY the same distance the other way. Symmetric barriers on a driftless walk win exactly 50% — not approximately, exactly, by the reflection principle. So the entire result is one number per row: `hit − 50%`. Positive means price genuinely seeks that place. The shuffled tape beside it must read 50% or the instrument is broken.

Held-out NQ contracts, 234 trading days, an entry sampled every 600 price changes.

| destination | trades | median distance | **hit rate** | **vs the 50% coin flip** | shuffled tape | unresolved |
|---|---|---|---|---|---|---|
| swing high R=20 | 76,357 | 18.2 pts | 43.83% | **-6.17 pp** (se 0.18) | 44.83% | 0% |
| swing low R=20 | 74,758 | 19.0 pts | 44.57% | **-5.43 pp** (se 0.18) | 44.18% | 0% |
| swing high R=8 | 80,409 | 9.0 pts | 45.58% | **-4.42 pp** (se 0.18) | 46.18% | 0% |
| swing low R=8 | 80,698 | 9.2 pts | 46.08% | **-3.92 pp** (se 0.18) | 45.96% | 0% |
| session low so far | 2,245 | 24.8 pts | 52.74% | **+2.74 pp** (se 1.06) | 51.53% | 0% |
| prev session low | 9,326 | 26.5 pts | 52.57% | **+2.57 pp** (se 0.52) | 50.28% | 0% |
| session VWAP | 16,400 | 23.5 pts | 47.49% | **-2.51 pp** (se 0.39) | 51.95% | 1% |
| session high so far | 9,031 | 21.8 pts | 51.79% | **+1.79 pp** (se 0.53) | 51.00% | 2% |
| round 100pt above | 42,913 | 25.2 pts | 49.06% | **-0.94 pp** (se 0.24) | 50.35% | 1% |
| prev session high | 12,795 | 26.0 pts | 49.20% | **-0.80 pp** (se 0.44) | 50.58% | 1% |
| prev session close | 17,798 | 24.5 pts | 49.48% | **-0.52 pp** (se 0.37) | 49.84% | 1% |
| round 25pt above | 82,913 | 13.5 pts | 49.76% | **-0.24 pp** (se 0.17) | 50.23% | 0% |
| round 100pt below | 42,696 | 25.8 pts | 49.89% | **-0.11 pp** (se 0.24) | 50.17% | 1% |
| round 25pt below | 83,141 | 13.5 pts | 49.93% | **-0.07 pp** (se 0.17) | 50.05% | 0% |

A destination is worth trading only if its deviation is several times its standard error AND the shuffled column sits at 50%. Anything else is the instrument, not the market.

### What a real one would be worth

At a symmetric bracket, expectancy is `(2p − 1) × distance × $2/point`. Against the $1.99 toll, a destination 20 points away needs **52.5%** to break even, and one 40 points away needs **51.2%**.

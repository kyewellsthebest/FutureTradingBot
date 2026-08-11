# Every stream, both entry styles, one search

Each idea was previously tested in its own script and never together. `hunt.py` searched NQ price and flow, `edge.py` tested passive entry and sweeps, `regime.py` tested gamma. So a rule needing *heavy buy flow AND the index complex agreeing AND a long-gamma session* could not be expressed, let alone found — which is the entire premise, since watching several unrelated streams at once is the one advantage a bot has that a human cannot copy.

Streams: NQ price, NQ order flow, the index complex (ES/YM/RTY), the macro complex (CL/GC/HG), sweeps, and dealer gamma over 484 labelled sessions. Entries scored **both** crossing and resting a limit. Cost **$1.24** — commission plus one spread, which is what a taker actually pays.

| gate | rejected |
|---|---|
| −1 geometry, before any data | 4,149 |
| 0 frequency, outcome untouched | 314,261,182 |
| 0b **degenerate — always true, or a duplicate mask** | 357,333 |
| 0c dropped by the cheap crossing screen | 358,536,418 |
| 1 win rate below break-even × 1.10 | 6,859,364 |
| 1b **below what RANDOM ENTRY earns** | 0 |
| 2 fully scored | 11,742 |

**908 beeps, 332,633 neighbours dug.** The sweep drops anything the cheap screen says cannot clear the gate — no Python loop, no bracket scan — and spends what it saves hill-climbing around whatever reads hot: thresholds nudged off the coarse grid, legs flipped, dropped and added, every combiner retried, repeating while it improves.

**Gate 1b is the one that matters.** NQ rose 8,492 points across this sample, so a long bracket makes money for no reason at all. Three separate findings today were exactly that, each surviving until someone asked what a random entry would have earned. Here it is a gate rather than a post-mortem.

`11,742` scored. `0` frequent enough, `750` paid enough, **`0` did both.** Selection ceiling **6.3σ**, from `365,407,524` configurations actually measured against an outcome — not from the handful that survived.

### Highest sigma over random entry, any frequency

| trigger | entry | R:R | win% | random | **σ vs random** | tr/wk | $/trade | **$/week** | worst run $ |
|---|---|---|---|---|---|---|---|---|---|
| DIG 3of(b_agree55>0.5,f_sz89>0.8 q0.5 | post | 2.5:1 | 33.3% | 29.2% | **+5.2σ** | 209 | $+1.73 | **$+363** | $287 |
| DIG 3of(b_agree55>0.16,f_sz89>0. q0.16 | cross | 2.8:1 | 32.3% | 27.1% | **+5.1σ** | 122 | $+1.73 | **$+211** | $314 |
| DIG 4of(b_agree55>0.2,d_ratio>0. q0.2 | cross | 2.2:1 | 36.6% | 31.4% | **+5.0σ** | 129 | $+1.55 | **$+201** | $300 |
| DIG 3of(b_agree55>0.5,d_z55>0.9, q0.5 | post | 1.6:1 | 43.9% | 39.0% | **+5.0σ** | 163 | $+2.42 | **$+394** | $305 |
| DIG 3of(b_agree55>0.5,f_sz89>0.8 q0.5 | post | 2.8:1 | 31.0% | 27.0% | **+5.0σ** | 199 | $+1.81 | **$+361** | $312 |
| DIG 3of(d_z55>0.8,f_sz89>0.82,i_ q0.8 | post | 2.8:1 | 31.3% | 27.1% | **+5.0σ** | 180 | $+2.20 | **$+397** | $341 |
| DIG 3of(b_agree55>0.48,d_z55>0.9 q0.48 | cross | 2.2:1 | 35.9% | 31.4% | **+5.0σ** | 174 | $+1.19 | **$+206** | $318 |
| DIG 3of(b_agree55>0.18,f_sz89>0. q0.18 | cross | 2.8:1 | 32.2% | 27.1% | **+5.0σ** | 120 | $+1.69 | **$+202** | $314 |
| DIG 4of(b_agree55>0.2,d_ratio>0. q0.2 | cross | 2.8:1 | 31.6% | 27.0% | **+5.0σ** | 142 | $+1.13 | **$+161** | $293 |
| DIG 3of(d_z55>0.8,f_sz89>0.8,i_r q0.8 | post | 2.8:1 | 31.2% | 27.1% | **+4.9σ** | 189 | $+2.12 | **$+402** | $345 |
| DIG 3of(b_agree55>0.15,f_sz89>0. q0.15 | cross | 2.8:1 | 32.1% | 27.1% | **+4.9σ** | 124 | $+1.62 | **$+201** | $317 |
| DIG 3of(b_agree55>0.48,d_z55>0.9 q0.48 | cross | 2.0:1 | 38.6% | 34.1% | **+4.9σ** | 165 | $+1.36 | **$+224** | $324 |

_Ran 5.53 h._

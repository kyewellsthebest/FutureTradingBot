# Every stream, both entry styles, one search

Each idea was previously tested in its own script and never together. `hunt.py` searched NQ price and flow, `edge.py` tested passive entry and sweeps, `regime.py` tested gamma. So a rule needing *heavy buy flow AND the index complex agreeing AND a long-gamma session* could not be expressed, let alone found — which is the entire premise, since watching several unrelated streams at once is the one advantage a bot has that a human cannot copy.

Streams: NQ price, NQ order flow, the index complex (ES/YM/RTY), the macro complex (CL/GC/HG), sweeps, and dealer gamma over 484 labelled sessions. Entries scored **both** crossing and resting a limit. Cost **$1.24** — commission plus one spread, which is what a taker actually pays.

| gate | rejected |
|---|---|
| −1 geometry, before any data | 11,091 |
| 0 frequency, outcome untouched | 16,510,256 |
| 0b **degenerate — always true, or a duplicate mask** | 77,208 |
| 0c dropped by the cheap crossing screen | 24,870,468 |
| 1 win rate below break-even × 1.10 | 55,798 |
| 1b **below what RANDOM ENTRY earns** | 0 |
| 2 fully scored | 62 |

**32 beeps, 7,479 neighbours dug.** The sweep drops anything the cheap screen says cannot clear the gate — no Python loop, no bracket scan — and spends what it saves hill-climbing around whatever reads hot: thresholds nudged off the coarse grid, legs flipped, dropped and added, every combiner retried, repeating while it improves.

**Gate 1b is the one that matters.** NQ rose 8,492 points across this sample, so a long bracket makes money for no reason at all. Three separate findings today were exactly that, each surviving until someone asked what a random entry would have earned. Here it is a gate rather than a post-mortem.

`62` scored. `0` frequent enough, `15` paid enough, **`0` did both.** Selection ceiling **2.9σ**.

### Highest sigma over random entry, any frequency

| trigger | entry | R:R | win% | random | **σ vs random** | tr/wk | $/trade | **$/week** | worst run $ |
|---|---|---|---|---|---|---|---|---|---|
| DIG 2of(i_divYM600<0.18,m_cl_int q0.18 | cross | 1.1:1 | 53.0% | 47.5% | **+4.2σ** | 92 | $+2.05 | **$+188** | $314 |
| DIG 2of(i_divYM600<0.18,m_cl_int q0.18 | cross | 1.1:1 | 52.8% | 47.5% | **+4.1σ** | 98 | $+1.92 | **$+188** | $318 |
| DIG 2of(i_divYM600<0.18,m_cl_int q0.18 | cross | 1.1:1 | 52.7% | 47.5% | **+4.0σ** | 98 | $+1.85 | **$+180** | $319 |
| DIG 2of(i_divYM600<0.2,m_cl_int3 q0.2 | cross | 1.1:1 | 52.7% | 47.5% | **+4.0σ** | 98 | $+1.85 | **$+180** | $319 |
| DIG 2of(i_divYM600<0.2,m_cl_int3 q0.2 | cross | 1.1:1 | 52.5% | 47.5% | **+4.0σ** | 104 | $+1.73 | **$+180** | $323 |
| DIG 2of(i_divYM600<0.18,m_cl_int q0.18 | cross | 1.2:1 | 49.8% | 44.7% | **+4.0σ** | 98 | $+1.65 | **$+162** | $310 |
| DIG 2of(i_divYM600<0.16,m_cl_int q0.16 | cross | 1.1:1 | 52.8% | 47.5% | **+4.0σ** | 92 | $+1.90 | **$+175** | $316 |
| DIG 2of(i_divYM600<0.18,m_cl_int q0.18 | cross | 1.1:1 | 52.4% | 47.5% | **+3.9σ** | 103 | $+1.69 | **$+174** | $324 |
| DIG 2of(i_divES600<0.2,m_cl_int3 q0.2 | post | 1.1:1 | 52.6% | 47.5% | **+3.9σ** | 95 | $+2.78 | **$+263** | $319 |
| DIG 3of(g_gex<0.37,i_divYM600<0. q0.37 | post | 1.1:1 | 52.5% | 47.5% | **+3.8σ** | 92 | $+2.76 | **$+254** | $318 |
| DIG 2of(i_divYM600<0.2,m_cl_int1 q0.2 | cross | 1.1:1 | 52.5% | 47.5% | **+3.8σ** | 92 | $+1.74 | **$+160** | $319 |
| DIG 2of(i_divYM600<0.2,m_cl_int1 q0.2 | cross | 1.2:1 | 49.6% | 44.7% | **+3.7σ** | 92 | $+1.53 | **$+141** | $309 |

_Ran 0.36 h._

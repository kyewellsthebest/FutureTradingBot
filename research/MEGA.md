# Every stream, both entry styles, one search

Each idea was previously tested in its own script and never together. `hunt.py` searched NQ price and flow, `edge.py` tested passive entry and sweeps, `regime.py` tested gamma. So a rule needing *heavy buy flow AND the index complex agreeing AND a long-gamma session* could not be expressed, let alone found — which is the entire premise, since watching several unrelated streams at once is the one advantage a bot has that a human cannot copy.

Streams: NQ price, NQ order flow, the index complex (ES/YM/RTY), the macro complex (CL/GC/HG), sweeps, and dealer gamma over 484 labelled sessions. Entries scored **both** crossing and resting a limit. Cost **$1.24** — commission plus one spread, which is what a taker actually pays.

| gate | rejected |
|---|---|
| −1 geometry, before any data | 0 |
| 0 frequency, outcome untouched | 474,418 |
| 1 win rate below what the bracket needs | 84,273 |
| 1b **below what RANDOM ENTRY earns** | 7,163 |
| 2 fully scored | 28,418 |

**Gate 1b is the one that matters.** NQ rose 8,492 points across this sample, so a long bracket makes money for no reason at all. Three separate findings today were exactly that, each surviving until someone asked what a random entry would have earned. Here it is a gate rather than a post-mortem.

`28,418` scored. `0` frequent enough, `9,605` paid enough, **`0` did both.** Selection ceiling **4.5σ**.

### Highest sigma over random entry, any frequency

| trigger | entry | stop | tgt | win% | needs | random | **σ vs random** | tr/wk | $/trade | **$/week** |
|---|---|---|---|---|---|---|---|---|---|---|
| g_gex q0.35 | cross | 184 | 62 | 75.9% | 75.8% | 73.3% | **+3.6σ** | 233 | $-2.33 | **$-543** |
| g_gex q0.35 | post | 184 | 62 | 75.9% | 75.8% | 73.3% | **+3.5σ** | 232 | $+9.16 | **$+2,124** |
| g_gex q0.35 | cross | 246 | 62 | 81.4% | 80.7% | 79.3% | **+2.8σ** | 195 | $-1.96 | **$-382** |
| g_gex q0.35 | cross | 369 | 62 | 87.8% | 86.2% | 85.7% | **+2.8σ** | 144 | $-0.61 | **$-88** |
| g_gex q0.35 | cross | 554 | 62 | 92.0% | 90.3% | 89.9% | **+2.7σ** | 102 | $+2.52 | **$+258** |
| g_gex q0.35 | post | 246 | 62 | 81.3% | 80.7% | 79.3% | **+2.7σ** | 195 | $+13.67 | **$+2,660** |
| g_gex q0.35 | post | 554 | 62 | 92.0% | 90.3% | 89.9% | **+2.7σ** | 102 | $+27.36 | **$+2,789** |
| g_gex q0.35 | cross | 554 | 123 | 85.0% | 82.2% | 81.4% | **+2.7σ** | 57 | $+5.46 | **$+312** |
| g_gex q0.35 | post | 369 | 62 | 87.7% | 86.2% | 85.7% | **+2.7σ** | 145 | $+19.87 | **$+2,873** |
| g_gex q0.35 | cross | 861 | 62 | 94.9% | 93.6% | 93.0% | **+2.7σ** | 79 | $+4.13 | **$+325** |
| g_gex q0.65 | post | 246 | 554 | 36.5% | 31.1% | 32.0% | **+2.7σ** | 50 | $-26.78 | **$-1,335** |
| g_gex q0.65 | cross | 246 | 554 | 36.5% | 31.1% | 32.0% | **+2.7σ** | 49 | $+2.82 | **$+139** |

_Ran 0.15 h._

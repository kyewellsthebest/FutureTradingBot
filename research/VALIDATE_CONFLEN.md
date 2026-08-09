# Does conf_len survive on data the search never saw?

One family topped the 103,680-strategy search and it was coherent rather than scattered: `conf_len` at 20-point structure, stop at 1.5x the recent median swing, long. It says that after a **slow, grinding** recovery off a low — as opposed to a sharp snap-back — price continues up.

The five TRAINING contracts, 389 million price changes, were excluded from that entire search. Nothing about them influenced which strategies rose to the top. If this is a mechanism it appears there at similar strength; if it is selection noise it collapses.

| strategy | split | trades | hit | geometry | above geo | shuffle | **edge** | $/trade | net |
|---|---|---|---|---|---|---|---|---|---|
| `conf_len>=q0.78 stop=m1.5 tgt=r1.0` | HELD-OUT (was searched) | 2,005 | 52.37% | 50.00% | +2.37 pp | -1.58 pp | **+3.95 pp** | $+4.553 | $+2.56 |
| `conf_len>=q0.78 stop=m1.5 tgt=r1.0` | TRAINING (never searched) | 1,953 | 49.72% | 50.00% | -0.28 pp | +0.00 pp | **-0.28 pp** | $-0.544 | $-2.53 |
| `conf_len>=q0.7 stop=m1.5 tgt=r1.0` | HELD-OUT (was searched) | 2,707 | 52.23% | 50.00% | +2.23 pp | -1.23 pp | **+3.47 pp** | $+4.320 | $+2.33 |
| `conf_len>=q0.7 stop=m1.5 tgt=r1.0` | TRAINING (never searched) | 2,659 | 49.27% | 50.00% | -0.73 pp | -0.30 pp | **-0.43 pp** | $-1.462 | $-3.45 |
| `conf_len>=q0.6 stop=m1.5 tgt=r1.0` | HELD-OUT (was searched) | 3,596 | 52.25% | 50.00% | +2.25 pp | -2.14 pp | **+4.39 pp** | $+4.401 | $+2.41 |
| `conf_len>=q0.6 stop=m1.5 tgt=r1.0` | TRAINING (never searched) | 3,887 | 49.45% | 50.00% | -0.55 pp | +1.39 pp | **-1.94 pp** | $-1.098 | $-3.09 |
| `conf_len>=q0.5 stop=m1.5 tgt=r1.0` | HELD-OUT (was searched) | 4,546 | 51.94% | 50.00% | +1.94 pp | -2.28 pp | **+4.21 pp** | $+3.781 | $+1.79 |
| `conf_len>=q0.5 stop=m1.5 tgt=r1.0` | TRAINING (never searched) | 5,285 | 49.18% | 50.00% | -0.82 pp | +0.86 pp | **-1.69 pp** | $-1.605 | $-3.59 |
| `conf_len>=q0.78 stop=m1.5 tgt=r0.75` | HELD-OUT (was searched) | 2,042 | 59.01% | 57.14% | +1.87 pp | -1.97 pp | **+3.83 pp** | $+3.103 | $+1.11 |
| `conf_len>=q0.78 stop=m1.5 tgt=r0.75` | TRAINING (never searched) | 1,992 | 57.43% | 57.15% | +0.28 pp | +0.14 pp | **+0.14 pp** | $+0.428 | $-1.56 |
| `conf_len>=q0.7 stop=m1.5 tgt=mm0.6` | HELD-OUT (was searched) | 2,659 | 70.97% | 69.69% | +1.28 pp | -0.14 pp | **+1.42 pp** | $+2.053 | $+0.06 |
| `conf_len>=q0.7 stop=m1.5 tgt=mm0.6` | TRAINING (never searched) | 2,619 | 69.99% | 69.72% | +0.27 pp | -0.53 pp | **+0.80 pp** | $+0.482 | $-1.51 |
| `conf_len>=q0.7 stop=m1.5 tgt=mm1.0` | HELD-OUT (was searched) | 2,190 | 62.88% | 61.41% | +1.47 pp | -0.86 pp | **+2.33 pp** | $+2.666 | $+0.68 |
| `conf_len>=q0.7 stop=m1.5 tgt=mm1.0` | TRAINING (never searched) | 2,128 | 61.98% | 61.66% | +0.32 pp | -0.07 pp | **+0.39 pp** | $+0.598 | $-1.39 |
| `prev_size>=q0.5 stop=m1.5 tgt=r1.0` | HELD-OUT (was searched) | 4,706 | 51.19% | 50.00% | +1.19 pp | -2.11 pp | **+3.30 pp** | $+2.361 | $+0.37 |
| `prev_size>=q0.5 stop=m1.5 tgt=r1.0` | TRAINING (never searched) | 5,470 | 48.78% | 50.00% | -1.22 pp | +0.77 pp | **-1.99 pp** | $-2.395 | $-4.38 |

## The verdict

| | mean edge | strategies positive |
|---|---|---|
| held-out, which the search selected on | **+3.36 pp** | 8/8 |
| training, which it never touched | **-0.62 pp** | 3/8 |

Retention: **-19%** of the edge carries to untouched data.

**It does not survive.** The edge was a property of the contracts the search picked it on, which is what selecting the best of 103,680 does to noise. No trade-level replay is warranted.

---
Same two controls as the search. First touch on the real tick sequence. The training contracts were excluded from the search by construction, so nothing about them shaped which strategies were ranked highest.

# 100,000 structural strategies, judged against geometry and a shuffled tape

Triggers, stops and targets are all STRUCTURAL — the distances differ on every trade and the risk:reward is an output, never an input. Resolving target-versus-stop is precomputed as first-passage tables, so every strategy costs two lookups instead of a walk down the tape.

Two baselines, and a strategy must beat both. **Its own geometry**: a trade risking S to make T wins S/(S+T) on a driftless walk however S and T were chosen, so a 70% win rate is nothing if geometry hands you 72%. And **a shuffled tape** — the same search on a random permutation of the real tick increments, identical volatility, order destroyed. That second control exists because the levels study caught a −0.79pp censoring bias in this very measurement.

Tables built in 564s.

Strategy space: 12 triggers x 12 strengths x 8 stop rules x 10 target rules x 3 sides x 3 scales = **311,040 evaluations**, 103,680 distinct strategies.

**81,348 strategies scored** (met the 400-trade gate on both the real and the shuffled tape) in 31.6 minutes.

### The whole population

Mean edge over geometry-and-shuffle: **-1.690 pp**. 2,624/81,348 positive (3.2%, a coin gives 50%). Spread -18.60 to +4.16 pp.

### The 40 strongest, after both controls

| edge vs geometry+shuffle | trades | hit | geometry | shuffle bias | $/trade gross | net | strategy |
|---|---|---|---|---|---|---|---|
| **+4.16 pp** | 2,005 | 52.37% | 50.00% | -1.79 pp | $+4.553 | $+2.56 | `conf_len>=q0.78 R=20 stop=m1.5 tgt=r1.0 long` |
| **+4.07 pp** | 2,042 | 59.01% | 57.14% | -2.20 pp | $+3.103 | $+1.11 | `conf_len>=q0.78 R=20 stop=m1.5 tgt=r0.75 long` |
| **+3.92 pp** | 3,596 | 52.25% | 50.00% | -1.67 pp | $+4.401 | $+2.41 | `conf_len>=q0.6 R=20 stop=m1.5 tgt=r1.0 long` |
| **+3.90 pp** | 2,964 | 68.79% | 68.56% | -3.66 pp | $+0.377 | $-1.61 | `regime>=q0.6 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+3.85 pp** | 2,707 | 52.23% | 50.00% | -1.61 pp | $+4.320 | $+2.33 | `conf_len>=q0.7 R=20 stop=m1.5 tgt=r1.0 long` |
| **+3.49 pp** | 2,659 | 70.97% | 69.69% | -2.21 pp | $+2.053 | $+0.06 | `conf_len>=q0.7 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+3.43 pp** | 2,190 | 62.88% | 61.41% | -1.96 pp | $+2.666 | $+0.68 | `conf_len>=q0.7 R=20 stop=m1.5 tgt=mm1.0 long` |
| **+3.34 pp** | 4,706 | 51.19% | 50.00% | -2.15 pp | $+2.361 | $+0.37 | `prev_size>=q0.5 R=20 stop=m1.5 tgt=r1.0 long` |
| **+3.28 pp** | 3,534 | 71.14% | 69.87% | -2.01 pp | $+2.013 | $+0.02 | `conf_len>=q0.6 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+3.20 pp** | 4,546 | 51.94% | 50.00% | -1.27 pp | $+3.781 | $+1.79 | `conf_len>=q0.5 R=20 stop=m1.5 tgt=r1.0 long` |
| **+3.19 pp** | 1,042 | 47.79% | 45.73% | -1.12 pp | $+3.114 | $+1.12 | `conf_len>=q0.85 R=20 stop=m1.0 tgt=mm1.6 long` |
| **+3.18 pp** | 1,661 | 71.52% | 72.50% | -4.15 pp | $-1.691 | $-3.68 | `regime>=q0.85 R=20 stop=m1.5 tgt=lvl2 both` |
| **+3.16 pp** | 1,951 | 33.42% | 33.34% | -3.08 pp | $+0.204 | $-1.79 | `prev_size>=q0.95 R=20 stop=m0.7 tgt=r2.0 both` |
| **+3.13 pp** | 2,752 | 58.87% | 57.14% | -1.40 pp | $+2.866 | $+0.88 | `conf_len>=q0.7 R=20 stop=m1.5 tgt=r0.75 long` |
| **+3.12 pp** | 2,934 | 62.78% | 61.52% | -1.86 pp | $+2.456 | $+0.47 | `conf_len>=q0.6 R=20 stop=m1.5 tgt=mm1.0 long` |
| **+3.12 pp** | 4,464 | 71.26% | 69.84% | -1.69 pp | $+2.240 | $+0.25 | `conf_len>=q0.5 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+3.07 pp** | 4,770 | 57.86% | 57.15% | -2.35 pp | $+1.251 | $-0.74 | `prev_size>=q0.5 R=20 stop=m1.5 tgt=r0.75 long` |
| **+3.06 pp** | 3,660 | 58.80% | 57.14% | -1.40 pp | $+2.805 | $+0.82 | `conf_len>=q0.6 R=20 stop=m1.5 tgt=r0.75 long` |
| **+3.02 pp** | 3,114 | 57.58% | 57.15% | -2.59 pp | $+0.813 | $-1.18 | `regime>=q0.6 R=20 stop=m1.5 tgt=r0.75 long` |
| **+2.98 pp** | 2,340 | 61.07% | 60.59% | -2.51 pp | $+0.897 | $-1.09 | `regime>=q0.6 R=20 stop=m1.5 tgt=mm1.0 long` |
| **+2.94 pp** | 4,436 | 63.95% | 63.46% | -2.45 pp | $+0.750 | $-1.24 | `prev_size>=q0.5 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+2.94 pp** | 5,945 | 33.98% | 33.33% | -2.29 pp | $+0.847 | $-1.14 | `conf_len>=q0.4 R=8 stop=m2.0 tgt=r2.0 long` |
| **+2.89 pp** | 3,703 | 62.71% | 61.48% | -1.67 pp | $+2.302 | $+0.31 | `conf_len>=q0.5 R=20 stop=m1.5 tgt=mm1.0 long` |
| **+2.88 pp** | 6,307 | 70.68% | 69.79% | -1.99 pp | $+1.404 | $-0.59 | `conf_len>=q0.3 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+2.80 pp** | 2,432 | 71.63% | 71.44% | -2.62 pp | $+0.072 | $-1.92 | `conf_len>=q0.6 R=20 stop=m1.5 tgt=lvl3 long` |
| **+2.77 pp** | 6,409 | 51.21% | 50.00% | -1.56 pp | $+2.375 | $+0.39 | `conf_len>=q0.3 R=20 stop=m1.5 tgt=r1.0 long` |
| **+2.76 pp** | 5,366 | 70.91% | 69.79% | -1.64 pp | $+1.697 | $-0.29 | `conf_len>=q0.4 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+2.75 pp** | 7,030 | 50.60% | 50.00% | -2.15 pp | $+1.197 | $-0.79 | `regime>=q0.2 R=20 stop=m1.5 tgt=r1.0 long` |
| **+2.74 pp** | 2,283 | 49.45% | 50.00% | -3.28 pp | $-0.720 | $-2.71 | `prev_size>=q0.95 R=20 stop=m1.0 tgt=r1.0 both` |
| **+2.67 pp** | 2,925 | 55.52% | 55.07% | -2.22 pp | $+0.741 | $-1.25 | `prev_size>=q0.5 R=20 stop=m1.5 tgt=mm1.0 long` |
| **+2.66 pp** | 5,020 | 33.78% | 33.33% | -2.21 pp | $+0.588 | $-1.40 | `prev_size>=q0.5 R=8 stop=m2.0 tgt=r2.0 long` |
| **+2.66 pp** | 5,459 | 51.29% | 50.00% | -1.37 pp | $+2.539 | $+0.55 | `conf_len>=q0.4 R=20 stop=m1.5 tgt=r1.0 long` |
| **+2.60 pp** | 7,132 | 57.38% | 57.14% | -2.37 pp | $+0.415 | $-1.58 | `regime>=q0.2 R=20 stop=m1.5 tgt=r0.75 long` |
| **+2.60 pp** | 3,747 | 51.13% | 50.00% | -1.46 pp | $+2.280 | $+0.29 | `prev_size>=q0.6 R=20 stop=m1.5 tgt=r1.0 long` |
| **+2.59 pp** | 6,870 | 69.37% | 69.40% | -2.61 pp | $-0.024 | $-2.01 | `regime>=q0.2 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+2.58 pp** | 2,126 | 57.57% | 57.14% | -2.15 pp | $+0.779 | $-1.21 | `prev_size>=q0.78 R=20 stop=m1.5 tgt=r0.75 long` |
| **+2.57 pp** | 3,073 | 50.60% | 50.00% | -1.97 pp | $+1.291 | $-0.70 | `regime>=q0.6 R=20 stop=m1.5 tgt=r1.0 long` |
| **+2.57 pp** | 5,709 | 51.15% | 50.00% | -1.42 pp | $+2.292 | $+0.30 | `prev_size>=q0.4 R=20 stop=m1.5 tgt=r1.0 long` |
| **+2.57 pp** | 3,832 | 68.76% | 68.80% | -2.60 pp | $-0.071 | $-2.06 | `regime>=q0.5 R=20 stop=m1.5 tgt=mm0.6 long` |
| **+2.57 pp** | 6,503 | 58.23% | 57.14% | -1.48 pp | $+1.852 | $-0.14 | `conf_len>=q0.3 R=20 stop=m1.5 tgt=r0.75 long` |

### Strategies profitable after the $1.99 toll: **3,541** of 81,348

| net $/trade | trades | edge vs controls | hit | strategy |
|---|---|---|---|---|
| **$+13.82** | 4,451 | -1.52 pp | 47.29% | `run>=q0.6 R=20 stop=swing tgt=mm1.6 short` |
| **$+13.82** | 4,451 | -1.52 pp | 47.29% | `run>=q0.7 R=20 stop=swing tgt=mm1.6 short` |
| **$+13.82** | 4,451 | -1.52 pp | 47.29% | `run>=q0.78 R=20 stop=swing tgt=mm1.6 short` |
| **$+13.82** | 4,451 | -1.52 pp | 47.29% | `run>=q0.85 R=20 stop=swing tgt=mm1.6 short` |
| **$+13.82** | 4,451 | -1.52 pp | 47.29% | `run>=q0.9 R=20 stop=swing tgt=mm1.6 short` |
| **$+13.82** | 4,451 | -1.52 pp | 47.29% | `run>=q0.95 R=20 stop=swing tgt=mm1.6 short` |
| **$+13.39** | 4,448 | -1.74 pp | 49.19% | `run>=q0.6 R=20 stop=m0.7 tgt=mm1.6 short` |
| **$+13.39** | 4,448 | -1.74 pp | 49.19% | `run>=q0.7 R=20 stop=m0.7 tgt=mm1.6 short` |
| **$+13.39** | 4,448 | -1.74 pp | 49.19% | `run>=q0.78 R=20 stop=m0.7 tgt=mm1.6 short` |
| **$+13.39** | 4,448 | -1.74 pp | 49.19% | `run>=q0.85 R=20 stop=m0.7 tgt=mm1.6 short` |
| **$+13.39** | 4,448 | -1.74 pp | 49.19% | `run>=q0.9 R=20 stop=m0.7 tgt=mm1.6 short` |
| **$+13.39** | 4,448 | -1.74 pp | 49.19% | `run>=q0.95 R=20 stop=m0.7 tgt=mm1.6 short` |
| **$+13.38** | 8,961 | -1.33 pp | 47.03% | `run>=q0.6 R=20 stop=swing tgt=mm1.6 both` |
| **$+13.38** | 8,961 | -1.33 pp | 47.03% | `run>=q0.7 R=20 stop=swing tgt=mm1.6 both` |
| **$+13.38** | 8,961 | -1.33 pp | 47.03% | `run>=q0.78 R=20 stop=swing tgt=mm1.6 both` |
| **$+13.38** | 8,961 | -1.33 pp | 47.03% | `run>=q0.85 R=20 stop=swing tgt=mm1.6 both` |
| **$+13.38** | 8,961 | -1.33 pp | 47.03% | `run>=q0.9 R=20 stop=swing tgt=mm1.6 both` |
| **$+13.38** | 8,961 | -1.33 pp | 47.03% | `run>=q0.95 R=20 stop=swing tgt=mm1.6 both` |
| **$+12.95** | 4,510 | -1.15 pp | 46.76% | `run>=q0.6 R=20 stop=swing tgt=mm1.6 long` |
| **$+12.95** | 4,510 | -1.15 pp | 46.76% | `run>=q0.7 R=20 stop=swing tgt=mm1.6 long` |
| **$+12.95** | 4,510 | -1.15 pp | 46.76% | `run>=q0.78 R=20 stop=swing tgt=mm1.6 long` |
| **$+12.95** | 4,510 | -1.15 pp | 46.76% | `run>=q0.85 R=20 stop=swing tgt=mm1.6 long` |
| **$+12.95** | 4,510 | -1.15 pp | 46.76% | `run>=q0.9 R=20 stop=swing tgt=mm1.6 long` |
| **$+12.95** | 4,510 | -1.15 pp | 46.76% | `run>=q0.95 R=20 stop=swing tgt=mm1.6 long` |
| **$+12.88** | 4,440 | -2.15 pp | 55.70% | `run>=q0.6 R=20 stop=m1.0 tgt=mm1.6 short` |
| **$+12.88** | 4,440 | -2.15 pp | 55.70% | `run>=q0.7 R=20 stop=m1.0 tgt=mm1.6 short` |
| **$+12.88** | 4,440 | -2.15 pp | 55.70% | `run>=q0.78 R=20 stop=m1.0 tgt=mm1.6 short` |
| **$+12.88** | 4,440 | -2.15 pp | 55.70% | `run>=q0.85 R=20 stop=m1.0 tgt=mm1.6 short` |
| **$+12.88** | 4,440 | -2.15 pp | 55.70% | `run>=q0.9 R=20 stop=m1.0 tgt=mm1.6 short` |
| **$+12.88** | 4,440 | -2.15 pp | 55.70% | `run>=q0.95 R=20 stop=m1.0 tgt=mm1.6 short` |
| **$+12.86** | 8,955 | -1.34 pp | 48.86% | `run>=q0.6 R=20 stop=m0.7 tgt=mm1.6 both` |
| **$+12.86** | 8,955 | -1.34 pp | 48.86% | `run>=q0.7 R=20 stop=m0.7 tgt=mm1.6 both` |
| **$+12.86** | 8,955 | -1.34 pp | 48.86% | `run>=q0.78 R=20 stop=m0.7 tgt=mm1.6 both` |
| **$+12.86** | 8,955 | -1.34 pp | 48.86% | `run>=q0.85 R=20 stop=m0.7 tgt=mm1.6 both` |
| **$+12.86** | 8,955 | -1.34 pp | 48.86% | `run>=q0.9 R=20 stop=m0.7 tgt=mm1.6 both` |
| **$+12.86** | 8,955 | -1.34 pp | 48.86% | `run>=q0.95 R=20 stop=m0.7 tgt=mm1.6 both` |
| **$+12.33** | 4,507 | -0.94 pp | 48.52% | `run>=q0.6 R=20 stop=m0.7 tgt=mm1.6 long` |
| **$+12.33** | 4,507 | -0.94 pp | 48.52% | `run>=q0.7 R=20 stop=m0.7 tgt=mm1.6 long` |
| **$+12.33** | 4,507 | -0.94 pp | 48.52% | `run>=q0.78 R=20 stop=m0.7 tgt=mm1.6 long` |
| **$+12.33** | 4,507 | -0.94 pp | 48.52% | `run>=q0.85 R=20 stop=m0.7 tgt=mm1.6 long` |

---
Held-out contracts only. First touch on the real tick sequence. Trades where neither barrier resolves inside the horizon are dropped on BOTH tapes, which is why the shuffled control is subtracted rather than assumed to be zero.

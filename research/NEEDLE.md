# The metal detector: 1.8M strategies, a bar noise cannot clear

Ranking a search finds the luckiest strategy, not the strongest — the best of N pure-noise draws is about sqrt(2 ln N) sigma, so 4.8 sigma at 100,000 tries. That is why the last winner came in at +4.16pp and retained −19% out of sample.

So this does not rank anything. It demands the edge clear **+0 pp in ALL EIGHT CONTRACTS SEPARATELY**, with at least **$-99.00/trade net after the $1.99 toll in every one** and at least 200 trades each. A coin clears one contract at that bar about 9% of the time, so it clears eight at roughly 3e-9.

**And that is measured, not asserted.** The identical filter runs over a shuffled-increment tape where no edge can exist. Whatever survives there is the false-positive rate.

Space: 1,209,600 strategies — single triggers and PAIRS of triggers, which is where a rare, strong setup would live.

## The result

| tape | strategies swept | **survivors** |
|---|---|---|
| real | 1,209,600 | **17** |
| shuffled (no edge can exist) | 1,209,600 | **2,085** |

The shuffled tape produced 2,085 survivors, so that is the false-positive floor. Real must beat it by a wide margin to mean anything.

### Was the bar reachable at all? The power curve

Both arms returning zero proves nothing unless a REAL edge could have cleared the bar. So the bar is lowered step by step and the two tapes compared at each level. If real never separates from shuffled, there is nothing below the bar either.

| bar: min edge in ALL 8 contracts | real survivors | shuffled | ratio |
|---|---|---|---|
| +0.0 pp | 17 | 2,085 | **0.01x** |
| +0.5 pp | 2 | 330 | **0.01x** |
| +1.0 pp | 0 | 56 | **0.00x** |
| +1.5 pp | 0 | 4 | **0.00x** |
| +2.0 pp | 0 | 2 | **0.00x** |
| +2.5 pp | 0 | 0 | **-** |
| +3.0 pp | 0 | 0 | **-** |
| +4.0 pp | 0 | 0 | **-** |
| +5.0 pp | 0 | 0 | **-** |

| bar: min NET $/trade in ALL 8 | real | shuffled | ratio |
|---|---|---|---|
| $-2.00 | 17 | 2,082 | **0.01x** |
| $-1.50 | 17 | 2,076 | **0.01x** |
| $-1.00 | 17 | 2,061 | **0.01x** |
| $-0.50 | 15 | 1,952 | **0.01x** |
| $+0.00 | 9 | 1,258 | **0.01x** |
| $+0.25 | 5 | 600 | **0.01x** |
| $+0.50 | 3 | 294 | **0.01x** |
| $+1.00 | 1 | 101 | **0.01x** |

### The 17 strongest survivors

| mean edge | WORST contract | net $/trade | trades | strategy |
|---|---|---|---|---|
| +1.90 pp | **+0.62 pp** | $+3.19 (worst $+1.34) | 4,217 | `regime>=q0.85+two_ago>=q0.85 R=12 stop=m2.0 tgt=r1.0 side=1` |
| +2.35 pp | **+0.55 pp** | $+3.39 (worst $+0.86) | 3,894 | `regime>=q0.5+size_z>=q0.93 R=12 stop=swing2 tgt=mm1.0 side=-1` |
| +1.97 pp | **+0.37 pp** | $+1.42 (worst $+0.21) | 5,867 | `prev_size>=q0.85+conf_len>=q0.7 R=12 stop=m1.0 tgt=r0.75 side=-1` |
| +1.26 pp | **+0.30 pp** | $+1.74 (worst $+0.52) | 35,235 | `conf_len>=q0.7+len_ratio>=q0.7 R=12 stop=m2.0 tgt=mm1.0 side=0` |
| +1.78 pp | **+0.21 pp** | $+1.08 (worst $-0.76) | 4,104 | `prev_size>=q0.5+conf_len>=q0.93 R=12 stop=m1.0 tgt=lvl2 side=-1` |
| +0.51 pp | **+0.17 pp** | $+0.69 (worst $+0.35) | 69,255 | `conf_len>=q0.7+len_ratio>=q0.25 R=12 stop=m2.0 tgt=mm1.0 side=0` |
| +1.11 pp | **+0.12 pp** | $+1.37 (worst $+0.40) | 14,214 | `conf_len>=q0.85+accel>=q0.7 R=12 stop=m2.0 tgt=mm1.0 side=0` |
| +1.63 pp | **+0.09 pp** | $+2.19 (worst $-0.07) | 5,595 | `size>=q0.93+regime>=q0.25 R=12 stop=swing2 tgt=mm1.0 side=-1` |
| +0.71 pp | **+0.08 pp** | $+0.45 (worst $-0.78) | 12,975 | `prev_size>=q0.25+conf_len>=q0.85 R=12 stop=m1.0 tgt=lvl3 side=-1` |
| +1.04 pp | **+0.08 pp** | $+1.24 (worst $-0.09) | 23,099 | `size>=q0.5+conf_len>=q0.85 R=12 stop=m2.0 tgt=mm1.0 side=0` |
| +0.65 pp | **+0.07 pp** | $+0.66 (worst $+0.17) | 24,242 | `retrace>=q0.5+conf_len>=q0.85 R=12 stop=m2.0 tgt=mm0.6 side=0` |
| +2.13 pp | **+0.06 pp** | $+2.32 (worst $+0.07) | 7,026 | `retrace>=q0.7+conf_len>=q0.85 R=12 stop=m2.0 tgt=mm1.0 side=1` |
| +2.37 pp | **+0.04 pp** | $+3.03 (worst $-0.30) | 6,662 | `size>=q0.7+conf_len>=q0.85 R=12 stop=m2.0 tgt=mm1.0 side=1` |
| +1.01 pp | **+0.03 pp** | $+1.20 (worst $-0.15) | 23,074 | `conf_len>=q0.85+size_z>=q0.5 R=12 stop=m2.0 tgt=mm1.0 side=0` |
| +0.44 pp | **+0.01 pp** | $+0.59 (worst $+0.09) | 64,811 | `retrace>=q0.25+conf_len>=q0.7 R=12 stop=m2.0 tgt=mm1.0 side=0` |
| +1.19 pp | **+0.01 pp** | $+1.49 (worst $-0.31) | 16,521 | `prev_size>=q0.5+conf_len>=q0.7 R=12 stop=m2.0 tgt=lvl3 side=-1` |
| +1.33 pp | **+0.00 pp** | $+1.80 (worst $-0.11) | 4,529 | `retrace>=q0.93+accel>=q0.93 R=12 stop=m2.0 tgt=lvl3 side=1` |

The column that matters is **WORST contract** — the weakest of eight independent verdicts. A strategy is only as good as the contract it did worst on.

---
Eight independent contract verdicts, no pooling, no ranking. First touch on the real tick sequence. The shuffled tape calibrates the false-positive rate empirically rather than by assumption.

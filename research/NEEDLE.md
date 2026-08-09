# The metal detector: 1.8M strategies, a bar noise cannot clear

Ranking a search finds the luckiest strategy, not the strongest — the best of N pure-noise draws is about sqrt(2 ln N) sigma, so 4.8 sigma at 100,000 tries. That is why the last winner came in at +4.16pp and retained −19% out of sample.

So this does not rank anything. It demands the edge clear **+0 pp in ALL EIGHT CONTRACTS SEPARATELY**, with at least **$-99.00/trade net after the $1.99 toll in every one** and at least 200 trades each. A coin clears one contract at that bar about 9% of the time, so it clears eight at roughly 3e-9.

**And that is measured, not asserted.** The identical filter runs over a shuffled-increment tape where no edge can exist. Whatever survives there is the false-positive rate.

Space: 1,209,600 strategies — single triggers and PAIRS of triggers, which is where a rare, strong setup would live.

## The result

| tape | strategies swept | **survivors** |
|---|---|---|
| real | 1,209,600 | **0** |
| shuffled (no edge can exist) | 1,209,600 | **33,818** |

The shuffled tape produced 33,818 survivors, so that is the false-positive floor. Real must beat it by a wide margin to mean anything.

### Was the bar reachable at all? The power curve

Both arms returning zero proves nothing unless a REAL edge could have cleared the bar. So the bar is lowered step by step and the two tapes compared at each level. If real never separates from shuffled, there is nothing below the bar either.

| bar: min edge in ALL 8 contracts | real survivors | shuffled | ratio |
|---|---|---|---|
| +0.0 pp | 0 | 33,818 | **0.00x** |
| +0.5 pp | 0 | 4,394 | **0.00x** |
| +1.0 pp | 0 | 196 | **0.00x** |
| +1.5 pp | 0 | 10 | **0.00x** |
| +2.0 pp | 0 | 2 | **0.00x** |
| +2.5 pp | 0 | 1 | **0.00x** |
| +3.0 pp | 0 | 0 | **-** |
| +4.0 pp | 0 | 0 | **-** |
| +5.0 pp | 0 | 0 | **-** |

| bar: min NET $/trade in ALL 8 | real | shuffled | ratio |
|---|---|---|---|
| $-2.00 | 0 | 26,757 | **0.00x** |
| $-1.50 | 0 | 492 | **0.00x** |
| $-1.00 | 0 | 23 | **0.00x** |
| $-0.50 | 0 | 14 | **0.00x** |
| $+0.00 | 0 | 1 | **0.00x** |
| $+0.25 | 0 | 1 | **0.00x** |
| $+0.50 | 0 | 0 | **-** |
| $+1.00 | 0 | 0 | **-** |

### No survivors

Not one strategy in 1,209,600 cleared +0 pp and $-99.00 net in all eight contracts. That is a much stronger statement than any ranking: it is not that the best was weak, it is that nothing in the space is strong ANYWHERE consistently.

---
Eight independent contract verdicts, no pooling, no ranking. First touch on the real tick sequence. The shuffled tape calibrates the false-positive rate empirically rather than by assumption.

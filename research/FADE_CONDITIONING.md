# Is the fade's edge concentrated in a subset?

The fade is worth about +0.3 percentage points overall and needs +3.5 to +4.9. Spread evenly that is hopeless, so the only surviving story is concentration: the edge living at full strength inside some subset and absent elsewhere. That needs roughly 10x.

NQ, 4 quarters, MARKET entries (no fill assumption anywhere), $1.33 real cost, 10-minute horizon. Each cell carries its OWN random-direction control, because every split selects a subset with its own geometry and the global control does not apply to it.

| conditioning | bucket | bracket | n | fade $/trade | RANDOM same cell | **fade - random** |
|---|---|---|---|---|---|---|
| imp | 0 | 5/30 | 18,267 | $-1.18 | $-1.28 | **$+0.10** |
| imp | 0 | 10/20 | 18,267 | $-1.16 | $-1.25 | **$+0.09** |
| imp | 0 | 20/10 | 18,267 | $-1.04 | $-1.12 | **$+0.09** |
| hour | 3 | 5/30 | 25,348 | $-1.44 | $-1.50 | **$+0.05** |
| hour | 3 | 10/20 | 25,348 | $-1.47 | $-1.39 | **$-0.09** |
| hour | 3 | 20/10 | 25,348 | $-1.17 | $-1.08 | **$-0.09** |
| hour | 1 | 5/30 | 27,087 | $-1.40 | $-1.31 | **$-0.10** |
| imp | 0 | 10/10 | 18,267 | $-1.35 | $-1.25 | **$-0.10** |
| pos | 1 | 5/30 | 24,990 | $-1.54 | $-1.42 | **$-0.12** |
| hour | 1 | 10/10 | 27,087 | $-1.43 | $-1.27 | **$-0.15** |
| pos | 1 | 20/10 | 24,990 | $-1.18 | $-1.02 | **$-0.16** |
| pos | 1 | 10/20 | 24,990 | $-1.45 | $-1.29 | **$-0.16** |
| hour | 1 | 10/20 | 27,087 | $-1.40 | $-1.24 | **$-0.16** |
| hour | 1 | 20/10 | 27,087 | $-1.25 | $-1.08 | **$-0.16** |
| imp | 1 | 5/30 | 23,782 | $-1.54 | $-1.38 | **$-0.16** |
| pos | 2 | 5/30 | 45,588 | $-1.51 | $-1.35 | **$-0.16** |
| hour | 3 | 10/10 | 25,348 | $-1.46 | $-1.29 | **$-0.17** |
| pos | 2 | 20/10 | 45,588 | $-1.38 | $-1.20 | **$-0.18** |

**Cells positive net of cost AND beating their own control: 0 of 52**

All-cell empirical null (99th percentile of the random-direction cells): **$-1.02/trade**. With this many cells something always looks good by luck, so the real best has to clear that line, not merely be positive.

Best real cell: imp=0 5/30 at **$-1.18/trade** over 18,267 trades — does NOT clear the $-1.02 null.

At 50.2 trades/day, $-1.18 a trade is **$-296/week** — against the $300/week target.


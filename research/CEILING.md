# The ceiling: how much signal is in these features AT ALL?

Every previous search enumerated axis-aligned threshold rules — 'feature A above its 70th percentile'. That is a blocky, measure-zero sliver of the ways features can combine, so 'have we covered a fifth?' has no good answer. This asks the question that does: fit a gradient-boosted model to all features at once and measure its out-of-sample power. That is an **upper bound on every strategy in this feature space**, including the ones never enumerated.

68,705 bars of 2000 price prints, 51 features, 8 NQ contracts. Walk-forward folds with an embargo the length of the prediction horizon, so no training row's outcome window can touch a test row. A shuffled-target control runs identically — a boosted tree WILL fit noise, and this measures how much rather than assuming zero.

| horizon | out-of-sample IC | shuffled control | **real − shuffled** | $/bar at full position | turnover-aware net |
|---|---|---|---|---|---|
| 1 bars | -0.0036 | +0.0046 | **-0.0082** | $-0.037 | **$-0.639** (turnover 0.61/bar) |
| 3 bars | -0.0067 | -0.0080 | **+0.0014** | $-0.321 | **$-0.768** (turnover 0.45/bar) |
| 10 bars | -0.0190 | +0.0027 | **-0.0218** | $-1.164 | **$-1.492** (turnover 0.33/bar) |
| 30 bars | -0.0298 | +0.0029 | **-0.0327** | $-5.712 | **$-5.987** (turnover 0.28/bar) |

**How to read it.** The IC column is the correlation between the model's prediction and what actually happened, out of sample. The shuffled column is the same model on scrambled targets — that is how much a boosted tree invents from nothing. Only the difference is real.

The last column is the one that decides everything: the model's output treated as a POSITION, with cost charged on how much the position CHANGES rather than a full round turn per signal. That is the turnover fix — every earlier test paid $1.99 for every opinion even when the opinion had not changed.

If real minus shuffled is at zero, no strategy built from these features can work, and no further enumeration in this space is worth running. That is the answer to 'how much of the haystack is left'.

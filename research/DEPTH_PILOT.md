# Does the top of the book predict forward returns? (one-week pilot)

NQU6 top-of-book, Jul 27-31 2026, 1,950 RTH minutes (~$10.55 of credit;
the full-July run completed but its results were lost to a push race).

| feature | IC vs 1min | IC vs 5min | Q5-Q1 (1min, ticks) |
|---|---|---|---|
| imbalance (mean) | +0.021 | +0.017 | +1.89 |
| imbalance (last) | -0.022 | +0.012 | -4.70 |
| size asymmetry | -0.003 | +0.014 | -1.45 |
| spread | -0.045 | -0.056 | -10.93 |
| quote rate | -0.050 | **-0.084** | -6.62 |

With ~1,950 minutes the IC standard error is ~0.023, so:

- **directional imbalance: not established** (+0.021 is one sigma -- the
  week cannot distinguish it from noise; the lost July run would have)
- **activity state is real**: quote rate at -0.084 (3.7 sigma) and spread
  at -0.056 (2.5 sigma) -- bursts of quoting and wide spreads are followed
  by weak/negative minutes. That is a REGIME/FILTER signal, not a
  directional one: it says when NOT to be entering longs, which plugs
  straight into the pulse executor as an entry filter candidate.

Verdict: the book carries usable state information even in a week of
data; the directional question needs the longer history and can wait.
No further credit spend required now.

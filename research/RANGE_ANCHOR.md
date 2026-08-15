# The level definition the live strategy actually used

`range` = fib retracement of the wick range with a close-minus-open impulse (what bot/pullback_strategy.py runs and what the 2025 spec described). `close` = close-to-close (what the 14,400-cell search tested). All 8 NQ quarters.

## ORIGINAL 2025 spec (5pt/4bar, .618, S6 T12)

| variant | anchor | trades | win rate | $/trade | **total** |
|---|---|---|---|---|---|
| baseline | **close** | 14,960 | 32.1% | $-3.35 | **$-50,136** |
| baseline | **range** | 14,233 | 31.7% | $-3.05 | **$-43,410** |
| touch entries+targets | **close** | 15,031 | 34.1% | $-2.57 | **$-38,653** |
| touch entries+targets | **range** | 14,299 | 33.3% | $-2.42 | **$-34,602** |
| lockout=exit+60s (real bot) | **close** | 76,035 | 19.0% | $-14.22 | **$-1,081,300** |
| lockout=exit+60s (real bot) | **range** | 72,733 | 19.6% | $-13.82 | **$-1,005,244** |
| no lockout (multi-position) | **close** | 98,836 | 32.7% | $-2.57 | **$-254,103** |
| no lockout (multi-position) | **range** | 94,388 | 32.2% | $-2.85 | **$-269,244** |
| membership comm $0.36 | **close** | 14,960 | 32.2% | $-2.47 | **$-36,972** |
| membership comm $0.36 | **range** | 14,233 | 31.8% | $-2.17 | **$-30,885** |
| CEILING: touch/touch/none/zero cost | **close** | 99,821 | 34.8% | $-0.34 | **$-33,682** |
| CEILING: touch/touch/none/zero cost | **range** | 95,415 | 34.3% | $-0.63 | **$-59,912** |

## deployed cell (5pt/6bar, .618, S10 T20)

| variant | anchor | trades | win rate | $/trade | **total** |
|---|---|---|---|---|---|
| baseline | **close** | 14,741 | 34.6% | $-4.06 | **$-59,838** |
| baseline | **range** | 13,624 | 34.5% | $-3.83 | **$-52,134** |
| touch entries+targets | **close** | 14,779 | 35.9% | $-3.26 | **$-48,122** |
| touch entries+targets | **range** | 13,684 | 35.4% | $-3.24 | **$-44,307** |
| lockout=exit+60s (real bot) | **close** | 62,383 | 18.5% | $-21.34 | **$-1,331,357** |
| lockout=exit+60s (real bot) | **range** | 58,116 | 19.0% | $-21.16 | **$-1,229,634** |
| no lockout (multi-position) | **close** | 98,420 | 35.9% | $-2.55 | **$-251,216** |
| no lockout (multi-position) | **range** | 92,601 | 35.5% | $-2.88 | **$-267,003** |
| membership comm $0.36 | **close** | 14,741 | 35.1% | $-3.18 | **$-46,866** |
| membership comm $0.36 | **range** | 13,624 | 34.9% | $-2.95 | **$-40,145** |
| CEILING: touch/touch/none/zero cost | **close** | 99,483 | 37.9% | $-0.30 | **$-30,230** |
| CEILING: touch/touch/none/zero cost | **range** | 93,621 | 37.5% | $-0.64 | **$-60,034** |


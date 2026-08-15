# Deep dive: attacking my own causal assumptions

Every fill rule the negative verdict rests on, toggled independently across all 8 NQ quarters (full data, one fixed cell -- no selection). If the strategy only works under an assumption, this names it.

## deployed (5/6bar, .618, S10 T20)

| variant | trades | win rate | $/trade | **total** |
|---|---|---|---|---|
| baseline (strict entry, strict target, window lockout) | 14,741 | 34.6% | $-4.06 | **$-59,838** |
| entries fill on TOUCH | 14,779 | 35.7% | $-3.38 | **$-49,931** |
| targets fill on TOUCH | 14,741 | 34.8% | $-3.94 | **$-58,079** |
| both fill on TOUCH | 14,779 | 35.9% | $-3.26 | **$-48,122** |
| lockout = exit+60s (realistic bot) | 62,383 | 18.5% | $-21.34 | **$-1,331,357** |
| lockout = none (multi-position) | 98,420 | 35.9% | $-2.55 | **$-251,216** |
| TOUCH both + lockout exit | 62,756 | 19.0% | $-21.03 | **$-1,319,997** |
| TOUCH both + no lockout | 99,483 | 37.0% | $-1.92 | **$-190,926** |
| membership commission $0.36 | 14,741 | 35.1% | $-3.18 | **$-46,866** |
| TOUCH both + no lockout + $0.36 comm | 99,483 | 37.6% | $-1.04 | **$-103,381** |
| EVERYTHING RELAXED: touch/touch/none/zero costs | 99,483 | 37.9% | $-0.30 | **$-30,230** |

## original 2025 spec (5/4bar, .618, S6 T12)

| variant | trades | win rate | $/trade | **total** |
|---|---|---|---|---|
| baseline (strict entry, strict target, window lockout) | 14,960 | 32.1% | $-3.35 | **$-50,136** |
| entries fill on TOUCH | 15,031 | 33.6% | $-2.77 | **$-41,582** |
| targets fill on TOUCH | 14,960 | 32.6% | $-3.18 | **$-47,603** |
| both fill on TOUCH | 15,031 | 34.1% | $-2.57 | **$-38,653** |
| lockout = exit+60s (realistic bot) | 76,035 | 19.0% | $-14.22 | **$-1,081,300** |
| lockout = none (multi-position) | 98,836 | 32.7% | $-2.57 | **$-254,103** |
| TOUCH both + lockout exit | 76,626 | 20.0% | $-13.74 | **$-1,053,176** |
| TOUCH both + no lockout | 99,821 | 34.4% | $-1.92 | **$-191,808** |
| membership commission $0.36 | 14,960 | 32.2% | $-2.47 | **$-36,972** |
| TOUCH both + no lockout + $0.36 comm | 99,821 | 34.7% | $-1.04 | **$-103,965** |
| EVERYTHING RELAXED: touch/touch/none/zero costs | 99,821 | 34.8% | $-0.34 | **$-33,682** |

## Read

The last row is the physical ceiling: entries and targets fill on any touch, unlimited concurrent positions, and ZERO commission or slippage. No real account can beat it. If it is not clearly positive, no cost structure or execution improvement can rescue this cell.


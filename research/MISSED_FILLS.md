# The 11% a resting limit never fills -- are those the winners?

A short resting ABOVE the market only fills when price rises into it. When the fade works immediately -- price drops and never comes back -- the order never fills. So the unfilled trades are structurally the ones that went your way, and the hypothesis that missing them is what costs the strategy is mechanically sound. This measures how much it is worth.

NQ, 4 quarters. Every signal split by whether a resting limit would ever have been reached, then BOTH groups priced as MARKET entries on the signal bar so they are comparable. Gross, before the $1.33 commission, so the fill question is isolated from the cost question.

| bracket | group | signals | target-first | gross $/trade | net $/trade |
|---|---|---|---|---|---|
| 5/44 | FILLED | 76,570 | 3.0% | **$-4.14** | $-5.47 |
| 5/44 | MISSED | 9,491 | 23.9% | **$+31.89** | $+30.56 |
| 5/44 | _RANDOM, missed_ | 9,491 | 11.3% | $+10.18 | $+8.85 |
| 5/36 | FILLED | 76,570 | 4.7% | **$-3.91** | $-5.24 |
| 5/36 | MISSED | 9,491 | 32.9% | **$+30.14** | $+28.81 |
| 5/36 | _RANDOM, missed_ | 9,491 | 15.8% | $+9.45 | $+8.12 |
| 5/30 | FILLED | 76,570 | 6.6% | **$-3.67** | $-5.00 |
| 5/30 | MISSED | 9,491 | 40.9% | **$+28.05** | $+26.72 |
| 5/30 | _RANDOM, missed_ | 9,491 | 19.7% | $+8.52 | $+7.19 |
| 10/20 | FILLED | 76,570 | 21.9% | **$-3.99** | $-5.32 |
| 10/20 | MISSED | 9,491 | 74.7% | **$+30.25** | $+28.92 |
| 10/20 | _RANDOM, missed_ | 9,491 | 36.9% | $+5.09 | $+3.76 |

## Reading it

If MISSED is strongly positive, the fill rate is the binding problem and the fix is a market order, which takes every one of them. If MISSED is not positive, then the trades the limit skips were never the prize, and no improvement in fill rate can rescue the strategy.

The RANDOM row matters here more than usual: MISSED is a selected subset -- these are the moves that ran away without looking back -- and a coin flip inside that same subset will not read zero. Only the difference between fade and RANDOM in the MISSED group is attributable to the signal.


## VOID -- this measurement is circular. Do not use the numbers above.

MISSED means the resting limit was never reached during the WHOLE
600-second window. That is decided by looking at the future. At entry
time you cannot know whether your order will fill, so the group cannot
be selected in advance and nothing measured inside it is tradable.

It is worse than ordinary hindsight, because the selection is
DIRECTIONALLY ALIGNED with the trade being tested. For an up-impulse the
fade is a SHORT, and the limit rests above the market, so MISSED means
price never came back up -- price went DOWN and stayed down. The group
is literally defined as "the occasions price moved the way this trade
wanted". A short earning +$31.89 there is arithmetic, not evidence.

The RANDOM control was not sufficient and saying otherwise was my error.
It detects that the subset is directionally loaded (+$10.18 for a coin
flip, when an unselected coin flip reads about zero), but the gap
between fade and RANDOM is mechanical for the same reason the level is:
the selection criterion and the fade direction are the same statement.
A control drawn from a subset that was selected on the answer cannot
rescue that subset.

WHAT THE ROWS DO LEGITIMATELY SHOW

The FILLED column is causal -- it is every trade a resting limit would
actually have taken, and it is -$3.67 to -$4.14 gross, before
commission, at every bracket. That is the real number for this order
type and it agrees with ENTRY_ACCURACY.md and ORDER_TYPES.md.

THE ANSWER TO THE ORIGINAL QUESTION

Are the 11% the limit misses the winners? Yes -- necessarily, because
"missed" means "price ran away in your favour". Is missing them what
costs the strategy? No. The only way to capture them is to take every
signal, which is a market order, and that is measured at -$1.48/trade
gross of commission. Recovering them is worth +$1.47/trade against the
resting limit -- the largest single improvement found in this whole
project -- and it still lands short of zero.

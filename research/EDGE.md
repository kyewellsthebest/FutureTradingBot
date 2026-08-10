# Searching the brainstormed edges

`36,917` configurations scored across 1 quarters, pooled to `36,917` families.

**The entry is modelled, not assumed.** Everything in this repo until now entered by crossing the spread. Here each strategy is run twice: once crossing (you pay the offer, a tick above the close) and once resting a limit a tick better. The passive version only fills if the tape actually trades there within 2 bars — so it fills precisely when price is moving against you. That is adverse selection, measured off the tape rather than assumed away, and there is no slippage constant anywhere in this file.

## Does posting beat crossing?

| entry | families | median $/trade | best $/trade | median fill rate |
|---|---|---|---|---|
| cross the spread | 6,912 | $-1.21 | $+16.09 | 100% |
| rest a limit | 6,912 | $-0.96 | $+28.00 | 97% |

Median difference: **$+0.26 per trade**, before any signal is considered. The theoretical maximum is two ticks ($1.00); anything less is adverse selection and missed fills eating into it.

## Passive entries, split by dealer gamma

| regime | families | median $/trade | best | trades |
|---|---|---|---|---|
| all | 6,912 | $-0.96 | $+28.00 | 13,785,399 |
| long-gamma | 6,912 | $-0.83 | $+32.83 | 12,639,202 |
| short-gamma | 4,638 | $-0.53 | $+54.67 | 875,324 |

## Best configurations, passive entry, present in most quarters

| trigger | side | regime | stop | target | trades | fill | **$/trade** |
|---|---|---|---|---|---|---|---|

Selection ceiling for 36,917 families is **4.6σ** and none of these have faced a shuffled control yet — this is a search, not a result. What matters at this stage is whether the passive column beats the crossing column by something near two ticks, because that part needs no edge to be real.

_Ran 1 min._

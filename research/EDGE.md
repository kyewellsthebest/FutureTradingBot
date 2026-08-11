# Searching the brainstormed edges

`645,251` configurations scored across 8 quarters, pooled to `603,859` families.

**The entry is modelled, not assumed.** Everything in this repo until now entered by crossing the spread. Here each strategy is run twice: once crossing (you pay the offer, a tick above the close) and once resting a limit a tick better. The passive version only fills if the tape actually trades there within 2 bars — so it fills precisely when price is moving against you. That is adverse selection, measured off the tape rather than assumed away, and there is no slippage constant anywhere in this file.

## Does posting beat crossing?

| entry | families | median $/trade | best $/trade | median fill rate |
|---|---|---|---|---|
| cross the spread | 103,680 | $-1.43 | $+23.20 | 100% |
| rest a limit | 103,680 | $-1.45 | $+33.93 | 97% |

Median difference: **$-0.02 per trade**, before any signal is considered. The theoretical maximum is two ticks ($1.00); anything less is adverse selection and missed fills eating into it.

## Passive entries, split by dealer gamma

| regime | families | median $/trade | best | trades |
|---|---|---|---|---|
| all | 103,680 | $-1.45 | $+33.93 | 328,017,022 |
| long-gamma | 102,904 | $-1.59 | $+43.59 | 235,851,244 |
| short-gamma | 95,434 | $-1.21 | $+68.49 | 48,982,171 |

## Best configurations, passive entry, present in most quarters

| trigger | side | regime | stop | target | trades | fill | **$/trade** |
|---|---|---|---|---|---|---|---|

Selection ceiling for 603,859 families is **5.2σ** and none of these have faced a shuffled control yet — this is a search, not a result. What matters at this stage is whether the passive column beats the crossing column by something near two ticks, because that part needs no edge to be real.

_Ran 19 min._

---

## The paired test, which is the one that decides it

Comparing medians across two separate populations is loose. The honest version
runs the **same family both ways** and takes the difference.

| | |
|---|---|
| pairs compared | 103,680 |
| median gain from posting | **−$0.066** |
| mean gain | +$0.087 |
| posting helps in | **49.6% of cases** |
| theoretical max, if adverse selection were free | +$1.00 |

49.6% is a coin flip. **Adverse selection consumes the entire two-tick price
improvement.** You obtain the better price precisely when the market was going
to keep moving against you, and the two cancel.

The single-quarter smoke test showed +$0.25 and I described the passive edge as
"worth more than every directional signal found in two years." One quarter, one
clock. Across eight quarters and two clocks it is zero — the third result this
session to vanish on pooling, after `conf_len` and the `f_ofi` +$2 rows.

### A bug this exposed

`max quarters seen: 2`, out of eight. Families cannot be matched across
quarters because they are keyed by ABSOLUTE tick distances, while the
stop/target ladder is scaled to each quarter's own volatility — so 135 ticks is
a different rung in a calm quarter than a wild one. `pool.py` keys by ladder
POSITION for exactly this reason and the fix was not carried over here.

The paired comparison above is unaffected, being within-quarter. But it is why
the "persists across quarters" table came back empty, and it means this search
cannot yet say which configurations survive out of sample.

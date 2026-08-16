# Are Treasuries really more deployable than MNQ?

A second research effort ruled MNQ out and ZB/ZN in, on the grounds that commission-per-tick makes everything else undeployable. That metric genuinely favours Treasuries -- one MNQ round trip costs **2.7 ticks** of commission, one ZB round trip costs **0.08**.

But commission is not the whole cost. Crossing a one-tick ZB spread costs **$31.25**; crossing a one-tick MNQ spread costs **$0.50**. Sixty-two times more. Whether that is worth paying depends on how far the instrument moves for it.

So: **how many round trips does one hour of movement pay for?** Same quantity for every instrument, counts the spread, counts the movement. Higher is more tradable.

| instrument | sigma 1h | tick $ | comm | spread+comm | **budget** | comm/tick | margin | micro |
|---|---|---|---|---|---|---|---|---|
| MNQ | $118 | $0.50 | $1.33 | $1.83 | **64.3x** | 2.66 ticks | $100 | IS micro |
| MGC | $106 | $1.00 | $1.33 | $2.33 | **45.5x** | 1.33 ticks | $300 | IS micro |
| MES | $60 | $1.25 | $1.33 | $2.58 | **23.1x** | 1.06 ticks | $200 | IS micro |
| MYM | $40 | $0.50 | $1.33 | $1.83 | **21.9x** | 2.66 ticks | $100 | IS micro |
| ZF 5y | $54 | $7.81 | $2.50 | $10.31 | **5.2x** | 0.32 ticks | $1,300 | no |
| ZB 30y | $158 | $31.25 | $2.50 | $33.75 | **4.7x** | 0.08 ticks | $4,200 | no |
| ZN 10y | $83 | $15.62 | $2.50 | $18.12 | **4.6x** | 0.16 ticks | $2,100 | no |
| ZT 2y | $47 | $7.81 | $2.50 | $10.31 | **4.6x** | 0.32 ticks | $800 | no |
| MCL | $4 | $0.10 | $1.33 | $1.43 | **3.1x** | 13.30 ticks | $200 | IS micro |
| M2K | $3 | $0.05 | $1.33 | $1.38 | **2.5x** | 26.60 ticks | $100 | IS micro |

`budget` is one hour of movement divided by one round trip. `comm/tick` is the metric the other effort used -- note it ranks the table almost backwards.

**MNQ's budget is 13.7x ZB's.** By commission-per-tick ZB looks 33x better; by movement-per-cost MNQ is 13.7x better. The two metrics disagree because commission-per-tick ignores the spread, and on Treasuries the spread IS the cost -- $31.25 a crossing against $2.50 of commission.

## The constraint that outranks the ratio

**ZB and ZN have no micro contract.** Full size or nothing: ~$4,200 and ~$2,100 of day-trade margin against a $4,000 account. One ZB position is the entire account; the 14-sleeve portfolio quoted at $4,093/week is not holdable at this capital regardless of whether its edge is real.

None of this says the ZB/ZN result is wrong. It says the reason given for preferring it -- commission per tick -- is not the quantity that decides tradability, and by the quantity that does, MNQ ranks better than the instrument being recommended over it.


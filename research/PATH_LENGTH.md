# 46,000 points move every day. Why not catch 1.5%?

**Path length is not a property of the market. It is a property of how finely you slice time.** Sum the absolute move of every 1-hour bar and you get one number; do it every second and you get a number fifty times larger, from the identical price history. So "NQ moves 46,000 points a day" is not a fact about NQ until you state the resolution -- and the resolution is something you choose.

For a random walk cut into N pieces:

    path length = 0.8 x sigma x sqrt(N)      grows as sqrt(N)
    cost        = N x cost_per_trade         grows as N

The ratio goes as 1/sqrt(N). **The finer you slice, the worse the deal.** More movement appears and it recedes faster than you can pay to chase it.

And capturing a fraction f of path length requires being on the right side with probability `p = (1 + f) / 2`. Capturing 1% needs 50.5% accuracy, which sounds easy. The question is never whether f is small -- it is whether the f you need is bigger than the f the trading costs.

## Sliced every 1 hour

| market | trades/day | path length/day | gross value | cost/day | **break-even f** | accuracy needed |
|---|---|---|---|---|---|---|
| MNQ | 23 | 588 pt | $1,176 | $42 | **3.6%** | 51.8% |
| MES | 23 | 116 pt | $581 | $59 | **10.2%** | 55.1% |
| MYM | 23 | 836 pt | $418 | $42 | **10.1%** | 55.0% |
| M2K | 23 | 74 pt | $369 | $32 | **8.6%** | 54.3% |
| MGC | 23 | 76 pt | $757 | $42 | **5.6%** | 52.8% |
| MCL | 23 | 4 pt | $38 | $42 | **111.1%** | 105.5% |

Combined path length across these six markets at 1 hour resolution: **1,694 points/day**.

## Sliced every 30 min

| market | trades/day | path length/day | gross value | cost/day | **break-even f** | accuracy needed |
|---|---|---|---|---|---|---|
| MNQ | 46 | 817 pt | $1,634 | $84 | **5.2%** | 52.6% |
| MES | 46 | 163 pt | $816 | $119 | **14.6%** | 57.3% |
| MYM | 46 | 1,166 pt | $583 | $84 | **14.4%** | 57.2% |
| M2K | 46 | 104 pt | $521 | $63 | **12.2%** | 56.1% |
| MGC | 46 | 107 pt | $1,072 | $84 | **7.9%** | 53.9% |
| MCL | 46 | 5 pt | $54 | $84 | **156.5%** | 128.2% |

Combined path length across these six markets at 30 min resolution: **2,363 points/day**.

## Sliced every 5 min

| market | trades/day | path length/day | gross value | cost/day | **break-even f** | accuracy needed |
|---|---|---|---|---|---|---|
| MNQ | 276 | 2,004 pt | $4,009 | $505 | **12.6%** | 56.3% |
| MES | 276 | 402 pt | $2,008 | $712 | **35.5%** | 67.7% |
| MYM | 276 | 2,897 pt | $1,448 | $505 | **34.9%** | 67.4% |
| M2K | 276 | 260 pt | $1,300 | $381 | **29.3%** | 64.6% |
| MGC | 276 | 262 pt | $2,619 | $505 | **19.3%** | 59.6% |
| MCL | 276 | 13 pt | $131 | $505 | **386.4%** | 243.2% |

Combined path length across these six markets at 5 min resolution: **5,838 points/day**.

## What the table says

Read the break-even column down the page. At coarse slicing you need a small fraction of a small pool; at fine slicing you need a large fraction of a large pool. The pool grows -- and the share of it you must capture grows faster.

That is the whole answer to "there is 46,000 points of movement out there". There is. There is also more of it at every finer resolution, without limit, all the way down to the tick -- and the finer you go, the larger the percentage you must take just to pay for the trades that reach it. The movement is not a pool you can dip into. It only exists at a resolution, and reaching that resolution costs more than the extra movement is worth.

The direction this points is the same one everything else in this project points: **fewer trades, longer holds.** Not because small edges are impossible, but because the break-even fraction falls as you slow down.


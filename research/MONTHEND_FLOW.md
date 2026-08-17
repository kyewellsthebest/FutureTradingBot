# Month-end rebalancing -- the first mechanism-first test here

**The mechanism, stated before the code ran.** A 60/40 pension fund whose equity sleeve rallied during the month is over-weight equities at month end. Its mandate obliges it to sell equities and buy bonds on a schedule, regardless of price or view. That is a counterparty forced to trade against their own interest at a known time -- the only kind of edge worth looking for, and the thing every failed family in this project lacked.

    strong equity month -> equities SOLD into month end
    weak equity month   -> equities BOUGHT into month end
    and the BOND leg must trade opposite

The bond leg is the real test. If this is rebalancing it has to appear with the opposite sign in ZN and ZB. If equities move and bonds do not, it is not rebalancing and the mechanism claim is false.

Each month end is **one observation**, not one per bar. The control draws the same number of month-end-shaped events at random month positions, so **clustering is preserved** and only the timing differs -- matching trade count alone compares clustered events against scattered ones and inflates every p-value.

| market | hold | trades | $/trade | $/year | p vs matched control |
|---|---|---|---|---|---|
| MNQ | 1d | 31 | **$+288.02** | $+3,456 | 0.003 |
| MES | 1d | 31 | **$+108.39** | $+1,301 | 0.015 |
| MNQ | 3d | 31 | **$+220.48** | $+2,646 | 0.054 |
| MES | 3d | 31 | **$+80.36** | $+964 | 0.083 |
| M2K | 1d | 31 | **$+30.09** | $+361 | 0.095 |
| MNQ | 2d | 31 | **$+166.86** | $+2,002 | 0.095 |
| MYM | 1d | 31 | **$+29.59** | $+355 | 0.129 |
| MES | 2d | 31 | **$+38.47** | $+462 | 0.232 |
| MYM | 5d | 31 | **$+26.17** | $+314 | 0.284 |
| M2K | 5d | 31 | **$+16.80** | $+202 | 0.289 |
| M2K | 3d | 31 | **$+10.93** | $+131 | 0.299 |
| MYM | 3d | 31 | **$+12.11** | $+145 | 0.334 |
| MES | 5d | 31 | **$+25.32** | $+304 | 0.338 |
| ZB | 1d | 31 | **$-13.59** | $-163 | 0.358 |
| MNQ | 5d | 31 | **$+36.51** | $+438 | 0.445 |
| M2K | 2d | 31 | **$+2.81** | $+34 | 0.447 |
| ZN | 1d | 32 | **$-22.51** | $-270 | 0.452 |
| MYM | 2d | 31 | **$-1.89** | $-23 | 0.490 |
| ZB | 2d | 31 | **$-89.19** | $-1,070 | 0.556 |
| ZB | 3d | 31 | **$-112.38** | $-1,349 | 0.627 |
| ZB | 5d | 31 | **$-215.20** | $-2,582 | 0.744 |
| ZN | 3d | 32 | **$-99.66** | $-1,196 | 0.780 |
| ZN | 2d | 32 | **$-97.22** | $-1,167 | 0.795 |
| ZN | 5d | 32 | **$-146.54** | $-1,758 | 0.855 |

**Positive after cost AND p < 0.05: 2 of 24**

- MNQ at 1 days: $+288.02/trade over 31 month ends, p = 0.003
- MES at 1 days: $+108.39/trade over 31 month ends, p = 0.015

## How to read a hit

A single market clearing p < 0.05 across roughly 24 tests is expected about once by luck. The claim only becomes interesting if the EQUITY markets and the BOND markets both clear it with the signs the mechanism predicts -- that is a joint statement luck does not easily produce, and it is the difference between a statistical artifact and a description of something a pension fund is actually obliged to do.


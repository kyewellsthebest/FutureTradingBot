# Portfolio — multi-market book

- searched **41,804,234,784** configs across 15 markets
- book: **3 streams** over **2 markets**, **33 trades/week**
- selected on 174 training weeks; the 43 holdout weeks below were never used to choose

| | train | holdout |
|---|---|---|
| per week | 165.5 | 239.81 |
| median week | 119.12 | 240.54 |
| pos weeks | 0.615 | 0.884 |
| worst week | -103.0 | -78.0 |
| maxdd | -121.0 | -78.0 |
| sharpe | 0.921 | 1.362 |
| total | 28796.0 | 10312.0 |

**Reading: holdout holds up — worth exact replay**

## Market mix

| market | streams | trades/wk | avg $/trade |
|---|---|---|---|
| ZN | 2 | 30.0 | 6.54 |
| NQ | 1 | 3.1 | 12.76 |

## The book

| market | tf | fam | etype | mf | H_min | tpw | n_tr | wk | ev | pf | poswk | maxdd | o10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZN | tf5 | fib | L | 0.00 | 240.00 | 19.56 | 2621 | 133.73 | 6.84 | 2.29 | 0.78 | -138.00 | 5,144.00 |
| ZN | tf5 | fib | L | 0.00 | 120.00 | 10.46 | 1401 | 65.24 | 6.24 | 1.76 | 0.65 | -190.00 | 2,058.00 |
| NQ | tf15 | fib | L | 0.00 | 240.00 | 3.15 | 346 | 40.13 | 12.76 | 2.83 | 0.72 | -178.00 | 830.00 |

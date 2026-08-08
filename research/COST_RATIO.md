# Where is the toll smallest? Cost in units of each market's own noise

Every dead family died the same way: a real edge of $0.50-1.50 against $1.75-2.00 of cost. That is a toll problem, not a signal problem, and it is measured here directly. For each market, the distribution of |forward move| in dollars on one micro contract at each event horizon, and where the all-in cost sits inside it.

`cost / avg move` is the share of a typical trade's raw material eaten by the toll. `% eaten` is the fraction of trades whose ENTIRE move is smaller than the cost. `edge needed` is the effect size a search has to find, in standard deviations — that is the difficulty rating.

| market | horizon | all-in cost | avg abs move | **cost / avg move** | % of trades whose whole move is eaten | edge needed (sd) |
|---|---|---|---|---|---|---|
| GC | 50 | $3.24 | $86.40 | **4%** | 3% | 0.04 |
| YM | 50 | $1.99 | $4.08 | **49%** | 27% | 0.58 |
| HG | 50 | $3.87 | $7.71 | **50%** | 36% | 0.53 |
| RTY | 50 | $1.99 | $3.96 | **50%** | 29% | 0.57 |
| NQ | 50 | $1.99 | $3.91 | **51%** | 28% | 0.64 |
| USDJPY | 50 | $0.80 | $1.47 | **54%** | 36% | 0.54 |
| CL | 50 | $3.24 | $5.26 | **62%** | 40% | 0.76 |
| EURUSD | 50 | $0.60 | $0.96 | **63%** | 40% | 0.70 |
| ES | 50 | $3.87 | $4.43 | **87%** | 56% | 0.94 |
| GBPUSD | 50 | $1.20 | $1.11 | **108%** | 65% | 1.06 |
| USDCHF | 50 | $1.40 | $0.89 | **158%** | 80% | 1.80 |
| AUDUSD | 50 | $1.60 | $0.94 | **171%** | 84% | 1.90 |
| XAUUSD | 50 | $23.80 | $13.17 | **181%** | 85% | 1.69 |
| NZDUSD | 50 | $1.80 | $0.82 | **219%** | 91% | 2.44 |
| USDCAD | 50 | $2.20 | $0.96 | **229%** | 93% | 2.46 |
| GC | 200 | $3.24 | $175.07 | **2%** | 1% | 0.02 |
| YM | 200 | $1.99 | $8.11 | **25%** | 14% | 0.29 |
| HG | 200 | $3.87 | $15.63 | **25%** | 18% | 0.28 |
| RTY | 200 | $1.99 | $7.97 | **25%** | 15% | 0.28 |
| NQ | 200 | $1.99 | $7.86 | **25%** | 14% | 0.33 |
| USDJPY | 200 | $0.80 | $3.01 | **27%** | 19% | 0.26 |
| CL | 200 | $3.24 | $10.52 | **31%** | 20% | 0.40 |
| EURUSD | 200 | $0.60 | $1.90 | **32%** | 21% | 0.35 |
| ES | 200 | $3.87 | $8.84 | **44%** | 31% | 0.48 |
| GBPUSD | 200 | $1.20 | $2.25 | **53%** | 37% | 0.53 |
| USDCHF | 200 | $1.40 | $1.76 | **80%** | 50% | 0.90 |
| AUDUSD | 200 | $1.60 | $1.91 | **84%** | 52% | 0.98 |
| XAUUSD | 200 | $23.80 | $27.10 | **88%** | 56% | 0.89 |
| NZDUSD | 200 | $1.80 | $1.68 | **107%** | 62% | 1.22 |
| USDCAD | 200 | $2.20 | $1.95 | **113%** | 66% | 1.25 |
| GC | 1000 | $3.24 | $362.99 | **1%** | 1% | 0.01 |
| YM | 1000 | $1.99 | $18.26 | **11%** | 6% | 0.13 |
| HG | 1000 | $3.87 | $34.43 | **11%** | 8% | 0.13 |
| RTY | 1000 | $1.99 | $17.52 | **11%** | 7% | 0.13 |
| NQ | 1000 | $1.99 | $17.50 | **11%** | 6% | 0.15 |
| USDJPY | 1000 | $0.80 | $6.77 | **12%** | 8% | 0.12 |
| CL | 1000 | $3.24 | $22.91 | **14%** | 10% | 0.18 |
| EURUSD | 1000 | $0.60 | $4.05 | **15%** | 9% | 0.17 |
| ES | 1000 | $3.87 | $19.46 | **20%** | 15% | 0.23 |
| GBPUSD | 1000 | $1.20 | $5.13 | **23%** | 16% | 0.25 |
| USDCHF | 1000 | $1.40 | $3.81 | **37%** | 25% | 0.41 |
| AUDUSD | 1000 | $1.60 | $4.34 | **37%** | 24% | 0.44 |
| XAUUSD | 1000 | $23.80 | $60.46 | **39%** | 28% | 0.41 |
| NZDUSD | 1000 | $1.80 | $3.71 | **48%** | 31% | 0.55 |
| USDCAD | 1000 | $2.20 | $4.31 | **51%** | 34% | 0.55 |
| GC | 4000 | $3.24 | $524.31 | **1%** | 0% | 0.01 |
| YM | 4000 | $1.99 | $36.81 | **5%** | 3% | 0.07 |
| HG | 4000 | $3.87 | $68.92 | **6%** | 4% | 0.08 |
| NQ | 4000 | $1.99 | $35.18 | **6%** | 3% | 0.07 |
| RTY | 4000 | $1.99 | $34.87 | **6%** | 3% | 0.07 |
| USDJPY | 4000 | $0.80 | $13.86 | **6%** | 4% | 0.07 |
| CL | 4000 | $3.24 | $45.91 | **7%** | 5% | 0.09 |
| EURUSD | 4000 | $0.60 | $8.05 | **7%** | 5% | 0.09 |
| ES | 4000 | $3.87 | $38.55 | **10%** | 8% | 0.12 |
| GBPUSD | 4000 | $1.20 | $10.25 | **12%** | 8% | 0.15 |
| USDCHF | 4000 | $1.40 | $7.89 | **18%** | 11% | 0.22 |
| AUDUSD | 4000 | $1.60 | $8.86 | **18%** | 12% | 0.23 |
| XAUUSD | 4000 | $23.80 | $121.04 | **20%** | 14% | 0.21 |
| NZDUSD | 4000 | $1.80 | $7.38 | **24%** | 16% | 0.30 |
| USDCAD | 4000 | $2.20 | $8.62 | **26%** | 19% | 0.31 |

## The ranking that matters

Averaged across horizons, cheapest toll first:

| market | mean cost / avg move | verdict |
|---|---|---|
| GC | **2%** | forgiving — a weak signal can still pay |
| YM | **22%** | workable if the signal is good |
| HG | **23%** | workable if the signal is good |
| RTY | **23%** | workable if the signal is good |
| NQ | **23%** | workable if the signal is good |
| USDJPY | **25%** | workable if the signal is good |
| CL | **28%** | workable if the signal is good |
| EURUSD | **29%** | workable if the signal is good |
| ES | **40%** | hostile — needs a strong signal |
| GBPUSD | **49%** | hostile — needs a strong signal |
| USDCHF | **73%** | close to unwinnable at this size |
| AUDUSD | **77%** | close to unwinnable at this size |
| XAUUSD | **82%** | close to unwinnable at this size |
| NZDUSD | **100%** | close to unwinnable at this size |
| USDCAD | **105%** | close to unwinnable at this size |

Read it as: to make money you must predict more than this share of a typical move, on average, forever. The leg-grammar cell predicted about $0.87 of NQ's move and lost, which is the same statement in dollars.

Not in this table because there is no tick data yet: **ZB and ZN**, whose tick values are $31.25 and $15.62 against the same $0.74 commission. That is the one structural way the ratio above gets dramatically smaller, and it is the strongest argument for acquiring bond tick data — see TODO_FOR_USER.md.

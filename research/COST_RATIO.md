# Where is the toll smallest? Cost in units of each market's own noise

Every dead family died the same way: a real edge of $0.50-1.50 against $1.75-2.00 of cost. That is a toll problem, not a signal problem, and it is measured here directly. For each market, the distribution of |forward move| in dollars on one micro contract at each event horizon, and where the all-in cost sits inside it.

`cost / avg move` is the share of a typical trade's raw material eaten by the toll. `% eaten` is the fraction of trades whose ENTIRE move is smaller than the cost. `edge needed` is the effect size a search has to find, in standard deviations — that is the difficulty rating.

| market | ticks/day | window | all-in cost | avg abs move | **cost / avg move** | % of trades whose whole move is eaten | edge needed (sd) |
|---|---|---|---|---|---|---|---|
| NQ | 393,787 | 1 min | $1.99 | $36.08 | **6%** | 6% | 0.04 |
| RTY | 81,096 | 1 min | $1.99 | $9.33 | **21%** | 22% | 0.12 |
| CL | 64,158 | 1 min | $3.24 | $13.09 | **25%** | 25% | 0.17 |
| USDJPY | 82,034 | 1 min | $0.60 | $2.01 | **30%** | 25% | 0.16 |
| YM | 62,483 | 1 min | $1.99 | $6.10 | **33%** | 26% | 0.28 |
| EURUSD | 98,857 | 1 min | $0.60 | $1.69 | **36%** | 27% | 0.32 |
| ES | 301,141 | 1 min | $3.87 | $10.15 | **38%** | 35% | 0.36 |
| GC | 50,227 | 1 min | $3.24 | $7.01 | **46%** | 39% | 0.40 |
| HG | 15,932 | 1 min | $3.87 | $4.82 | **80%** | 61% | 0.50 |
| XAUUSD | 280,404 | 1 min | $12.80 | $15.02 | **85%** | 59% | 0.75 |
| AUDUSD | 116,004 | 1 min | $1.80 | $1.63 | **111%** | 69% | 0.93 |
| GBPUSD | 68,749 | 1 min | $1.40 | $1.21 | **115%** | 72% | 0.92 |
| USDCAD | 84,081 | 1 min | $2.20 | $1.37 | **160%** | 81% | 1.50 |
| NZDUSD | 80,289 | 1 min | $2.00 | $1.20 | **166%** | 82% | 1.71 |
| USDCHF | 45,119 | 1 min | $1.60 | $0.91 | **175%** | 84% | 1.47 |
| NQ | 393,787 | 5 min | $1.99 | $81.46 | **2%** | 3% | 0.02 |
| RTY | 81,096 | 5 min | $1.99 | $20.44 | **10%** | 11% | 0.05 |
| CL | 64,158 | 5 min | $3.24 | $26.24 | **12%** | 12% | 0.09 |
| USDJPY | 82,034 | 5 min | $0.60 | $4.46 | **13%** | 11% | 0.09 |
| YM | 62,483 | 5 min | $1.99 | $12.90 | **15%** | 13% | 0.14 |
| EURUSD | 98,857 | 5 min | $0.60 | $3.75 | **16%** | 12% | 0.15 |
| ES | 301,141 | 5 min | $3.87 | $21.63 | **18%** | 18% | 0.18 |
| GC | 50,227 | 5 min | $3.24 | $14.65 | **22%** | 19% | 0.22 |
| XAUUSD | 280,404 | 5 min | $12.80 | $33.55 | **38%** | 32% | 0.34 |
| HG | 15,932 | 5 min | $3.87 | $9.81 | **39%** | 34% | 0.34 |
| AUDUSD | 116,004 | 5 min | $1.80 | $3.48 | **52%** | 39% | 0.45 |
| GBPUSD | 68,749 | 5 min | $1.40 | $2.64 | **53%** | 42% | 0.43 |
| USDCAD | 84,081 | 5 min | $2.20 | $3.01 | **73%** | 50% | 0.75 |
| NZDUSD | 80,289 | 5 min | $2.00 | $2.55 | **79%** | 51% | 0.85 |
| USDCHF | 45,119 | 5 min | $1.60 | $2.03 | **79%** | 55% | 0.73 |
| NQ | 393,787 | 30 min | $1.99 | $194.91 | **1%** | 1% | 0.01 |
| RTY | 81,096 | 30 min | $1.99 | $44.95 | **4%** | 5% | 0.03 |
| CL | 64,158 | 30 min | $3.24 | $58.36 | **6%** | 5% | 0.05 |
| USDJPY | 82,034 | 30 min | $0.60 | $10.07 | **6%** | 5% | 0.05 |
| YM | 62,483 | 30 min | $1.99 | $30.48 | **7%** | 6% | 0.06 |
| EURUSD | 98,857 | 30 min | $0.60 | $8.98 | **7%** | 5% | 0.08 |
| ES | 301,141 | 30 min | $3.87 | $49.74 | **8%** | 8% | 0.08 |
| GC | 50,227 | 30 min | $3.24 | $33.30 | **10%** | 9% | 0.10 |
| XAUUSD | 280,404 | 30 min | $12.80 | $78.69 | **16%** | 14% | 0.15 |
| HG | 15,932 | 30 min | $3.87 | $21.51 | **18%** | 15% | 0.20 |
| GBPUSD | 68,749 | 30 min | $1.40 | $6.56 | **21%** | 18% | 0.17 |
| AUDUSD | 116,004 | 30 min | $1.80 | $8.20 | **22%** | 16% | 0.22 |
| USDCAD | 84,081 | 30 min | $2.20 | $7.42 | **30%** | 23% | 0.31 |
| NZDUSD | 80,289 | 30 min | $2.00 | $6.00 | **33%** | 22% | 0.40 |
| USDCHF | 45,119 | 30 min | $1.60 | $4.76 | **34%** | 27% | 0.33 |
| NQ | 393,787 | 2 h | $1.99 | $370.91 | **1%** | 1% | 0.00 |
| RTY | 81,096 | 2 h | $1.99 | $74.14 | **3%** | 3% | 0.02 |
| CL | 64,158 | 2 h | $3.24 | $105.10 | **3%** | 3% | 0.03 |
| USDJPY | 82,034 | 2 h | $0.60 | $18.59 | **3%** | 2% | 0.03 |
| YM | 62,483 | 2 h | $1.99 | $54.02 | **4%** | 3% | 0.04 |
| EURUSD | 98,857 | 2 h | $0.60 | $15.61 | **4%** | 2% | 0.05 |
| ES | 301,141 | 2 h | $3.87 | $99.76 | **4%** | 4% | 0.04 |
| GC | 50,227 | 2 h | $3.24 | $63.20 | **5%** | 5% | 0.05 |
| XAUUSD | 280,404 | 2 h | $12.80 | $148.82 | **9%** | 7% | 0.09 |
| HG | 15,932 | 2 h | $3.87 | $40.72 | **9%** | 8% | 0.11 |
| GBPUSD | 68,749 | 2 h | $1.40 | $12.40 | **11%** | 10% | 0.10 |
| AUDUSD | 116,004 | 2 h | $1.80 | $15.25 | **12%** | 9% | 0.14 |
| USDCAD | 84,081 | 2 h | $2.20 | $13.48 | **16%** | 13% | 0.17 |
| NZDUSD | 80,289 | 2 h | $2.00 | $11.30 | **18%** | 13% | 0.22 |
| USDCHF | 45,119 | 2 h | $1.60 | $8.53 | **19%** | 14% | 0.21 |

## The ranking that matters

Averaged across horizons, cheapest toll first:

| market | mean cost / avg move | verdict |
|---|---|---|
| NQ | **2%** | forgiving — a weak signal can still pay |
| RTY | **10%** | forgiving — a weak signal can still pay |
| CL | **11%** | forgiving — a weak signal can still pay |
| USDJPY | **13%** | forgiving — a weak signal can still pay |
| YM | **15%** | forgiving — a weak signal can still pay |
| EURUSD | **16%** | workable if the signal is good |
| ES | **17%** | workable if the signal is good |
| GC | **21%** | workable if the signal is good |
| HG | **37%** | hostile — needs a strong signal |
| XAUUSD | **37%** | hostile — needs a strong signal |
| AUDUSD | **49%** | hostile — needs a strong signal |
| GBPUSD | **50%** | hostile — needs a strong signal |
| USDCAD | **70%** | close to unwinnable at this size |
| NZDUSD | **74%** | close to unwinnable at this size |
| USDCHF | **77%** | close to unwinnable at this size |

Read it as: to make money you must predict more than this share of a typical move, on average, forever. The leg-grammar cell predicted about $0.87 of NQ's move and lost, which is the same statement in dollars.

Not in this table because there is no tick data yet: **ZB and ZN**, whose tick values are $31.25 and $15.62 against the same $0.74 commission. That is the one structural way the ratio above gets dramatically smaller, and it is the strongest argument for acquiring bond tick data — see TODO_FOR_USER.md.

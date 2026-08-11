# The two best rules, traded together

Trades and dollars per week add up. **Best day, worst week, drawdown and losing streaks do not** — they depend on when each trade happened and whether the two rules lose on the same days. Two strategies that each drop $300 in a bad week are a $600 week if they fall together and a $300 week if they take turns. So both are put on one clock and the P&L is added bar by bar.

| | rule |
|---|---|
| **A · duration+regime** | 3 of (`d_z55`>0.9, `f_eff21`>0.78, `p_chop55`>0.85, `v_ac144`>0.3, `i_rty_sz600`>0.8) — **LONG**, 250-tick bars, stop 49/target 62, found in NQU4 |
| **B · two-horizon flow** | 2 of (`f_wcofi600`<0.35, `f_wcofi120`<0.35) — **SHORT**, 500-tick bars, stop 82/target 82, found in NQH5 |

## Out of sample: every quarter, not just the one it was found in

Each rule was discovered in a single quarter. A rule that only works in the three months it was found in is a description of those three months. **This table is the actual result** — the portfolio specs below only mean something if these numbers hold up.

| quarter | A · duration+regime | B · two-horizon flow |
|---|---|---|
| NQU4 | $+0.90/tr · $+161/wk ⌂ | $-1.02/tr · $-213/wk |
| NQZ4 | $-1.37/tr · $-175/wk | $-0.37/tr · $-55/wk |
| NQH5 | $-1.40/tr · $-291/wk | $+1.04/tr · $+242/wk ⌂ |
| NQM5 | $-1.28/tr · $-344/wk | $+0.51/tr · $+151/wk |
| NQU5 | $-0.77/tr · $-85/wk | $-0.51/tr · $-69/wk |
| NQZ5 | $-0.62/tr · $-118/wk | $-0.30/tr · $-66/wk |
| NQH6 | $-1.78/tr · $-378/wk | $+0.34/tr · $+81/wk |
| NQM6 | $-0.47/tr · $-125/wk | $-1.12/tr · $-335/wk |

⌂ = the quarter the rule was found in. Everything else is out of sample.

## Specs

| | A · duration+regime | B · two-horizon flow | **BOTH TOGETHER** |
|---|---|---|---|
| **trades/week** | 234 | 265 | 498 |
| **$/week** | $-193 | $-35 | $-228 |
| $/day | $-39 | $-7 | $-46 |
| % of days green | 43% | 48% | 44% |
| **best day** | $652 | $1,350 | $963 |
| **worst day** | $-1,177 | $-922 | $-1,799 |
| **best week** | $1,088 | $2,506 | $2,317 |
| **worst week** | $-3,310 | $-1,737 | $-3,815 |
| avg winning day | $139 | $252 | $236 |
| avg losing day | $-176 | $-245 | $-272 |
| **max drawdown** | $-23,272 | $-6,928 | $-25,657 |
| **longest losing streak** | 10 days | 9 days | 8 days |
| total over the sample | $-20,258 | $-3,651 | $-23,909 |

`520` trading days. Max drawdown **$25,657** is **626%** of a $4,100 account.

## What these numbers are resting on

**The two rules trade opposite directions** — one LONG and one SHORT. Their daily P&L correlates **-0.27** across the 728 days both were active. That number, not the direction labels, decides whether the second rule is a second bet: near zero and the drawdowns genuinely offset, strongly positive and they compound. Opposite signs do not guarantee opposite outcomes, because both can lose on the same choppy day.

**Execution is the whole result.** Both rest a limit, and the search credited that a flat two ticks. Measured, resting is worth **+$0.355** a trade at the front of the queue and **−$0.102** past five contracts of depth. Everything above uses the optimistic figure. At the pessimistic one the portfolio makes **$-451 a week** instead of **$-228**, with a max drawdown of **$48,896**. Which of those two you get is decided by the order book, which is not recorded yet.

**Overlap:** the two rules hold at the same time on `8,491` occasions, which is `16%` of all trades. In those moments two contracts are on and the risk is double what a single-rule drawdown suggests. That is already inside the numbers above — it is the reason to read the combined column rather than adding the two.


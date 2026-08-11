# The search's best results, re-priced against the measured queue

`mega.py` credits a resting entry a flat **two ticks — $1.00 a trade** — and **7,063 of 13,807** scored rows are passive, including every one of the leaders. `maker.py` then measured what resting is actually worth against crossing over 33,464 trades, and it is not a constant:

| contracts ahead of you | worth vs crossing |
|---|---|
| 0 | **$+0.355** |
| 2 | **$+0.064** |
| 5 | **$-0.019** |
| 10 | **$-0.075** |
| 25 | **$-0.097** |
| 50 | **$-0.102** |
| 100 | **$-0.101** |
| 200 | **$-0.101** |

So the headline numbers are overstated by between **$0.65 and $1.10 a trade**. Correcting that is arithmetic, not another search: the credit is a constant added to every passive trade, so swapping it leaves win rates, trade counts, brackets and random-entry baselines untouched. These are the same results, priced honestly — not a fresh set of draws against the selection ceiling.

## What survives, as the queue gets longer

Gates unchanged: **≥500 trades/week and ≥$2.00 a trade**, net, beating random entry.

| contracts ahead | rows clearing both gates | best $/trade | best $/week | best $/week at 500+ trades |
|---|---|---|---|---|
| 0 | 0 | $+2.53 | $+473 | $+221 |
| 2 | 0 | $+2.23 | $+407 | $+147 |
| 5 | 0 | $+2.15 | $+400 | $+147 |
| 10 | 0 | $+2.10 | $+400 | $+147 |
| 25 | 0 | $+2.07 | $+400 | $+147 |
| 50 | 0 | $+2.07 | $+400 | $+147 |
| 100 | 0 | $+2.07 | $+400 | $+147 |
| 200 | 0 | $+2.07 | $+400 | $+147 |

## Break-even queue depth, per candidate

For each of the strongest rows: how many contracts can sit ahead of you before it stops paying $2.00 a trade. **This is the number the DOM recorder settles.** A candidate whose break-even is 0 needs the front of the queue on every order, which is not reachable at 72 ms.

| trigger | tr/wk | $/trade **as credited** | **re-priced @0** | **@5** | **@50** | break-even queue |
|---|---|---|---|---|---|---|
| 2of(f_wcofi600<0.2,i_ym_eff120<0.2,m_cl_ret1 | 569 | $+1.00 | $+0.35 | $-0.02 | $-0.10 | **never** |
| 3of(f_wcofi600<0.2,i_ym_eff120<0.2,m_cl_ret1 | 531 | $+1.06 | $+0.42 | $+0.04 | $-0.04 | **never** |
| 2of(f_int21<0.2,g_gex<0.2,i_disp600<0.2,x_sw | 542 | $+0.94 | $+0.30 | $-0.08 | $-0.16 | **never** |
| 2of(f_ofi21<0.35,g_gex<0.2,i_disp600<0.2,m_c | 518 | $+0.97 | $+0.33 | $-0.05 | $-0.13 | **never** |
| 2of(f_ofi21<0.35,g_gex<0.2,i_disp600<0.2,p_r | 514 | $+0.92 | $+0.27 | $-0.10 | $-0.18 | **never** |
| 2of(g_gex<0.2,i_disp600<0.2,m_cl_eff600<0.35 | 504 | $+0.90 | $+0.26 | $-0.12 | $-0.20 | **never** |
| 2of(g_gex<0.2,i_disp600<0.2,m_cl_eff600<0.35 | 506 | $+0.87 | $+0.22 | $-0.15 | $-0.23 | **never** |
| 2of(f_ofi21<0.2,i_ym_eff120<0.2,m_cl_int600< | 572 | $+0.77 | $+0.12 | $-0.25 | $-0.34 | **never** |
| 2of(g_gex<0.35,i_disp600<0.2,p_rev3<0.35,x_s | 531 | $+0.83 | $+0.18 | $-0.19 | $-0.28 | **never** |
| 2of(f_wcofi600<0.2,i_ym_eff120<0.2,m_cl_int6 | 551 | $+0.79 | $+0.15 | $-0.23 | $-0.31 | **never** |

At the **front of the queue** — the best case physics allows, and one we cannot actually reach — **0** rows clear both gates. Every row that needs a break-even of 0 is asking for a queue position that costs a rack in Aurora, Illinois to obtain.

The honest reading: these are not results waiting on more searching. They are results waiting on **one measurement** — the median depth at top of book — and that measurement decides all of them at once.

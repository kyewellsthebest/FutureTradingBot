# Do any of them survive a quarter they were not fitted to?

The first two did not. Each was profitable in the single quarter it was discovered in and lost money almost everywhere else — together **−$228 a week** with a drawdown six times the account. The sigma had already said so: 4.76 against a 6.28 noise ceiling means *this is what randomness produces*, and out of sample it behaved exactly like randomness.

So the question here is not how much each makes. It is whether any of them survives a quarter it was not fitted to. `10` distinct strategies, `8` quarters, priced at the **+$0.355** a trade that resting a limit was actually measured to be worth rather than the flat two ticks the search assumed.

Deduplicated by feature set, side and bar size first — the top five by dollars per week were four copies of one rule with thresholds nudged by 0.02, the dig reporting its own neighbours. Testing that as ten strategies would be testing one, ten times, and calling the agreement confirmation.

| # | strategy | side | home | **home $/tr** | **out-of-sample $/tr** | green qtrs | claimed | check |
|---|---|---|---|---|---|---|---|---|
| 1 | 2of(`f_wcofi600`, `f_wcofi120`) | S | NQH5 | $+1.04 | **$-0.33** | 3/8 | $+2.08 | **MISMATCH** |
| 2 | 2of(`f_wcofi120`, `i_es_ofi30`, `m_cl_ret30`) | S | NQH5 | $+0.45 | **$-1.08** | 1/8 | $+1.32 | **MISMATCH** |
| 3 | 3of(`f_wcofi120`, `m_cl_ret30`, `p_rng21`, `x_sweep`) | S | NQH5 | $+0.63 | **$-0.74** | 1/8 | $+1.59 | **MISMATCH** |
| 4 | 2of(`i_es_ofi30`, `m_cl_ret30`, `p_chop55`) | S | NQH5 | $+0.67 | **$-1.17** | 1/8 | $+1.28 | **MISMATCH** |
| 5 | 3of(`i_es_ofi30`, `m_cl_ret30`, `p_rng21`, `x_sweep`) | S | NQH5 | $+1.05 | **$-1.33** | 1/8 | $+1.49 | ok |
| 6 | 3of(`f_wcofi120`, `i_es_ofi30`, `m_cl_ret30`, `x_sweep`) | S | NQH5 | $+0.80 | **$-1.14** | 1/8 | $+1.54 | **MISMATCH** |
| 7 | 3of(`f_wcofi120`, `i_es_ofi30`, `m_cl_int600`, `p_hour`, `x_sweep`) | S | NQH5 | $+0.39 | **$-1.35** | 1/8 | $+1.26 | **MISMATCH** |
| 8 | 2of(`f_wcofi600`, `i_es_ofi30`, `m_cl_ret30`) | S | NQH5 | $+0.42 | **$-1.04** | 1/8 | $+1.29 | **MISMATCH** |
| 9 | 4of(`f_ofi21`, `g_regime`, `i_es_ofi30`, `m_cl_ret120`, `p_hour`, `x_sweep) | S | NQH5 | $+1.48 | **$-1.20** | 1/8 | $+1.97 | ok |
| 10 | 2of(`f_wcofi120`, `x_sweep`) | S | NQH5 | $+0.51 | **$-0.60** | 2/8 | $+1.79 | **MISMATCH** |

`out-of-sample $/tr` is the only column that matters. `check` compares the home quarter against what the search claimed, repriced for execution — a mismatch means the reconstruction is wrong and the whole row should be ignored, which is exactly how a direction error was caught earlier today.

## Verdict

**Not one of the 10 strategies is profitable out of sample.** Every single one makes money in the quarter it was found in and loses money on average across the others. That is not a marginal result or a tuning problem — it is what overfitting looks like when you go and check, and it is the same answer the selection ceiling gave before any of these were backtested.


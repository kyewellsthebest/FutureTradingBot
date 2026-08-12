# The validated survivors, stacked as one portfolio

`100` unique survivor parameterisations collapsed to **10 genuinely distinct cores** — rules whose actual trades overlap less than 40% (Jaccard on trade-bar sets). The rest were the same trades wearing different labels. Every number below **excludes each rule's home quarter** — only money made on data the rule never saw is counted.

| core | side | legs | tr/wk | $/tr | **$/wk** | worst wk | max DD | streak |
|---|---|---|---|---|---|---|---|---|
| 15 | S | `g_gex,v_vr,w_fbreak,x_sweep` | 18 | $+1.17 | **$+21** | $-355 | $476 | 4d |
| 55 | S | `d_z144,g_gex,i_rty_ret600,r_beta30,w_fbreak` | 28 | $+0.95 | **$+26** | $-636 | $1,276 | 4d |
| 14 | S | `b_agree,f_ofi21,g_gex,v_vr,x_sweep` | 17 | $+1.03 | **$+17** | $-374 | $824 | 6d |
| 99 | S | `t_amihud,w_reject` | 17 | $+1.07 | **$+19** | $-434 | $939 | 4d |
| 74 | L | `d_z55,m_divCL5,o_gapabs,p_chop55,v_ac144` | 29 | $+0.79 | **$+23** | $-529 | $1,056 | 4d |
| 1 | S | `b_agree,f_ofi21,g_gex,t_amihud,x_sweep` | 25 | $+1.00 | **$+25** | $-340 | $689 | 4d |
| 54 | S | `g_gex,i_lead600,r_beta30,v_vr,x_sweep` | 21 | $+0.82 | **$+17** | $-347 | $872 | 5d |
| 94 | S | `f_ret89,g_gex,i_divRTY120,v_eff55,x_sweep` | 19 | $+0.86 | **$+17** | $-460 | $809 | 6d |
| 66 | L | `d_z55,f_ofi89,i_lead600,r_beta30` | 13 | $+1.28 | **$+17** | $-299 | $529 | 6d |
| 77 | S | `c_dom,t_gapmax` | 14 | $+1.17 | **$+17** | $-210 | $369 | 3d |

## The portfolio — all cores, one contract each

| | value |
|---|---|
| trades/week | **202** |
| **$/week** | **$+196** |
| best / worst day | $+1,010 / $-702 |
| best / worst week | $+2,359 / $-1,031 |
| avg winning / losing day | $+149 / $-107 |
| % days green | 56% |
| **max drawdown** | **$1,904** (46% of $4,100) |
| longest losing streak | 9 days |
| total over 520 days | $+20,624 |

Pairwise daily correlation between cores: median **+0.02**, max +0.25. Low is the whole point — that is what makes stacking reduce risk instead of multiplying it.

Caveats that stay attached to these numbers: execution is priced at the **measured front-of-queue** maker edge (+$0.355), not the flat two ticks; concurrent cores mean more than one contract at once on some days — margin needs checking against the account; and the cores were selected from 66,220 validated draws, so the ensemble must be re-proven on ES/CL before it is believed.

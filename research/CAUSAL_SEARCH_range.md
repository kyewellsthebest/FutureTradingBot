# Exhaustive causal family search (14,400 cells, NQ, anchor=range, train-pick discipline)

Both archetypes, every parameter variation, audited causal engine (research/VALIDATOR_AUDIT.md). Held-out = last 40% of each quarter, never used for selection.

**Null context**: across ALL 14,400 cells the held-out distribution is mean $-50,035, p95 $-10,271, p99 $-8,118, max $-4,485. A train-winner inside this spread is selection noise, not edge.

| arch | imp | w | retr | S | T | hold | pol | train $ | **held-out $** | ho n | ho/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stop | 12 | 10 | 1.0 | 20 | 10 | 20m | firs | -8,587 | **-8,875** | 2722 | 63 | 0/8 |
| stop | 8 | 10 | 1.0 | 20 | 10 | 20m | firs | -8,859 | **-9,037** | 3086 | 72 | 2/8 |
| limit | 12 | 3 | 0.5 | 20 | 20 | 20m | firs | -9,334 | **-7,719** | 3088 | 72 | 0/8 |
| stop | 12 | 6 | 0.786 | 20 | 20 | 20m | firs | -9,433 | **-8,803** | 2873 | 67 | 1/8 |
| stop | 12 | 10 | 0.786 | 20 | 10 | 20m | firs | -9,757 | **-8,642** | 2792 | 65 | 0/8 |
| stop | 12 | 3 | 1.0 | 20 | 10 | 20m | firs | -9,759 | **-7,244** | 2893 | 67 | 0/8 |
| stop | 12 | 10 | 1.0 | 15 | 10 | 20m | firs | -9,910 | **-9,041** | 2722 | 63 | 0/8 |
| limit | 12 | 3 | 0.5 | 15 | 20 | 20m | firs | -9,966 | **-6,820** | 3088 | 72 | 1/8 |
| stop | 12 | 3 | 1.0 | 15 | 10 | 20m | firs | -10,016 | **-7,845** | 2893 | 67 | 0/8 |
| limit | 12 | 3 | 0.618 | 5 | 10 | 20m | firs | -10,183 | **-9,480** | 2996 | 70 | 0/8 |
| stop | 12 | 10 | 1.0 | 20 | 5 | 20m | firs | -10,205 | **-9,291** | 2722 | 63 | 0/8 |
| stop | 12 | 10 | 1.0 | 20 | 5 | 5m | firs | -10,271 | **-9,124** | 2743 | 64 | 0/8 |
| stop | 12 | 10 | 0.786 | 10 | 10 | 20m | firs | -10,356 | **-9,275** | 2792 | 65 | 0/8 |
| stop | 12 | 3 | 0.618 | 20 | 40 | 20m | firs | -10,375 | **-10,266** | 2996 | 70 | 2/8 |
| stop | 12 | 6 | 0.786 | 20 | 10 | 20m | firs | -10,469 | **-8,053** | 2873 | 67 | 0/8 |
| limit | 12 | 3 | 0.618 | 5 | 20 | 20m | firs | -10,618 | **-8,954** | 2996 | 70 | 0/8 |
| limit | 12 | 3 | 0.382 | 20 | 20 | 20m | firs | -10,618 | **-9,328** | 3185 | 74 | 0/8 |
| stop | 12 | 10 | 1.0 | 20 | 10 | 5m | firs | -10,646 | **-9,400** | 2743 | 64 | 0/8 |
| limit | 12 | 3 | 0.618 | 10 | 10 | 20m | firs | -10,722 | **-8,705** | 2996 | 70 | 0/8 |
| stop | 8 | 10 | 1.0 | 20 | 5 | 20m | firs | -10,809 | **-9,667** | 3086 | 72 | 0/8 |

## Verdict: train-winner held-out **$-8,875** (0/8 green) vs all-cell p99 $-8,118 -> **NOISE — no causal edge in this family on NQ**


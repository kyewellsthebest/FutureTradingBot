# Exhaustive causal family search (14,400 cells, NQ, train-pick discipline)

Both archetypes, every parameter variation, audited causal engine (research/VALIDATOR_AUDIT.md). Held-out = last 40% of each quarter, never used for selection.

**Null context**: across ALL 14,400 cells the held-out distribution is mean $-35,247, p95 $-10,678, p99 $-8,646, max $-3,906. A train-winner inside this spread is selection noise, not edge.

| arch | imp | w | retr | S | T | hold | pol | train $ | **held-out $** | ho n | ho/wk | green q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| limit | 12 | 3 | 0.382 | 15 | 10 | 20m | firs | -6,475 | **-8,266** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.382 | 15 | 20 | 20m | firs | -7,257 | **-6,295** | 3146 | 73 | 1/8 |
| limit | 12 | 3 | 0.382 | 20 | 10 | 20m | firs | -7,845 | **-8,572** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.382 | 15 | 5 | 20m | firs | -8,151 | **-9,482** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.382 | 20 | 20 | 20m | firs | -8,375 | **-6,682** | 3146 | 73 | 1/8 |
| limit | 12 | 3 | 0.382 | 15 | 30 | 20m | firs | -8,674 | **-6,044** | 3146 | 73 | 2/8 |
| limit | 12 | 3 | 0.382 | 20 | 30 | 20m | firs | -9,088 | **-6,347** | 3146 | 73 | 1/8 |
| limit | 12 | 3 | 0.382 | 20 | 5 | 20m | firs | -9,404 | **-9,373** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.382 | 10 | 10 | 20m | firs | -9,475 | **-7,831** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.5 | 15 | 30 | 20m | firs | -9,566 | **-8,344** | 3094 | 72 | 0/8 |
| limit | 8 | 3 | 0.382 | 20 | 10 | 20m | firs | -9,739 | **-10,882** | 3534 | 82 | 0/8 |
| limit | 8 | 3 | 0.382 | 15 | 10 | 20m | firs | -9,821 | **-10,616** | 3534 | 82 | 0/8 |
| limit | 12 | 3 | 0.5 | 15 | 10 | 20m | firs | -9,838 | **-9,189** | 3094 | 72 | 0/8 |
| limit | 12 | 3 | 0.382 | 10 | 5 | 20m | firs | -9,943 | **-8,530** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.5 | 15 | 20 | 20m | firs | -10,003 | **-9,665** | 3094 | 72 | 0/8 |
| limit | 12 | 3 | 0.382 | 10 | 20 | 20m | firs | -10,049 | **-6,516** | 3146 | 73 | 1/8 |
| limit | 12 | 3 | 0.382 | 20 | 40 | 20m | firs | -10,073 | **-4,009** | 3146 | 73 | 2/8 |
| limit | 12 | 3 | 0.382 | 10 | 30 | 20m | firs | -10,501 | **-7,214** | 3146 | 73 | 0/8 |
| limit | 12 | 3 | 0.382 | 15 | 40 | 20m | firs | -10,529 | **-4,056** | 3146 | 73 | 2/8 |
| limit | 12 | 3 | 0.5 | 10 | 10 | 20m | firs | -10,536 | **-8,846** | 3094 | 72 | 0/8 |

## Verdict: train-winner held-out **$-8,266** (0/8 green) vs all-cell p99 $-8,646 -> **NOISE — no causal edge in this family on NQ**


# NQ Futures Local Data

2 years of 1-minute NQ futures bars, contract-by-contract. Stitched into a
continuous front-month series by `research/local_data_loader.py` (rolls
8 days before each contract's 3rd-Friday expiry).

| File | Contract | Active range used |
|------|----------|-------------------|
| `nq_0624.txt` | Jun 2024 | start → 2024-06-10 |
| `nq_0924.txt` | Sep 2024 | 2024-06-10 → 2024-09-10 |
| `nq_0325.txt` | Mar 2025 | 2024-09-10 → 2025-03-10 (covers gap from missing nq_1224) |
| `nq_0625.txt` | Jun 2025 | 2025-03-10 → 2025-06-10 |
| `nq_0925.txt` | Sep 2025 | 2025-06-10 → 2025-09-10 |
| `nq_1225.txt` | Dec 2025 | 2025-09-10 → 2025-12-10 |
| `nq_0326.txt` | Mar 2026 | 2025-12-10 → 2026-03-10 |
| `nq_0626.txt` | Jun 2026 | 2026-03-10 → present (front) |

Format (semicolon-separated):
```
YYYYMMDD HHMMSS;open;high;low;close;volume
```
Timestamps are UTC. Resample to 5-min via `load_intraday_5min()`.

To override the location, set `NQ_LOCAL_DATA_DIR` in the env.

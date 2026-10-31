# DATA — what is in this repository, and how to get it

Everything listed here is in the repo already. Clone it and it is on your
disk. **~1.2 GB in total**, so the sparse-checkout recipes below matter if
you only want one piece.

```bash
git clone --depth 1 https://github.com/kyewellsthebest/FutureTradingBot
```

**If you would rather have Claude do it**, paste this:

> Clone `https://github.com/kyewellsthebest/FutureTradingBot` with
> `--depth 1`, read `DATA.md` at the root, and load the datasets I ask
> about. The loaders in `researcher/data_tiers.py` and
> `research/local_data_loader.py` already know these formats.

---

## 1. Futures price data

### 1-minute bars, contract by contract — `data/nq/`, `data/es/`, `data/rty/`

The longest futures history here. Plain semicolon text, one file per
quarterly contract:

```
20180225 230100;6918.25;6928.75;6918.25;6921.75;730
YYYYMMDD HHMMSS;open;high;low;close;volume
```

| market | contracts | 1-min bars | range | span |
|---|---|---|---|---|
| **NQ** | 34 | **2,930,516** | 2018-02-25 → 2026-04-08 | **8.2 years** |
| ES | 9 | 811,403 | 2023-12-06 → 2026-02-27 | 2.2 years |
| RTY | 9 | 703,376 | 2024-02-25 → 2026-02-27 | 2.0 years |
| VIX | 1 | 389,171 | 2024-02-29 → 2026-02-27 | 2.0 years |

`research/local_data_loader.py` stitches the contracts into a continuous
front-month series, rolling 8 days before each third-Friday expiry. It
exposes `load_intraday_1min(sym)`, `load_intraday_5min(sym)`,
`load_daily(sym)`, `load_vix_1min()` and `load_vix_5min()`.

```bash
git clone -n --depth 1 --filter=tree:0 \
  https://github.com/kyewellsthebest/FutureTradingBot && \
  cd FutureTradingBot && git sparse-checkout set --no-cone data/nq && \
  git checkout
```

### 5-minute bars, 26 instruments — `data/polygon/`

4,548,315 bars, 286 MB. Columns: `ts, open, high, low, close, volume`.
Most begin 2023-12-15; the exceptions are worth knowing.

| group | symbols | note |
|---|---|---|
| Index | NQ, ES, YM, RTY | NQ also has `NQ_1min.csv`, 585,396 bars |
| Energy | CL, NG, HO, RB | **NG runs from 2022-06** (4.1 yrs), CL from 2023-10 |
| Metals | GC, SI, HG | GC from 2023-09 |
| Rates | ZB, ZN, ZF, ZT | ZN from 2023-05, ZT from 2023-05 |
| FX | 6A, 6B, 6E, 6J | all from 2023-12 |
| Grains | ZC, ZS, ZW | **ZC from 2022-09**; ZS and ZW are thin (52k, 73k bars) |
| Crypto | ETH, MBT | from 2023-09 |
| Equity ETF | SPY, QQQ (daily) | 501 rows each |

### Pre-computed NQ bars — `data/research_bars/`

1,022,027 bars, parquet, built from tick and kept because the tick itself
is not here. Eight quarterly contracts (NQU4 → NQH6, 2024-06 → 2026-06) at
**15s, 60s and 300s**. Columns: `close, vol, n, absret` plus `hl`/`gap`
where available.

---

## 2. Order book and trade-level

| file | rows | what it holds |
|---|---|---|
| `data/depth/NQU6_book_1s.parquet` | **1,593,637** | 1-second top of book: `bid_px, ask_px, bid_sz, ask_sz, n_evt, n_trade, tv_buy, tv_sell` |
| `data/poly/NQM6_2026-06-10_tbbo.parquet` | **565,797** | true trade-by-trade with quotes, **one day** |
| `data/depth/nq_book_july_1min.parquet` | 1,950 | derived book features: imbalance, spread, queue rate, size asymmetry |

### What is NOT here

`data/tick/` is in `.gitignore` — about **4.7 GB of NQ tick (8 quarterly
contracts, ~25M trades)** and a 249 MB cache of 266-feature matrices. It
was deliberately kept local and is not in any clone. `data/research_bars/`
above is what was derived from it and survives. To rebuild the tick layer
you need a Databento `GLBX.MDP3` subscription.

---

## 3. Positioning, macro and volatility

All of this is public-domain or free-to-redistribute at source.

| dataset | path | contents | span |
|---|---|---|---|
| **CFTC Commitments of Traders** | `data/research_data/cftc/` | 9 files, weekly: dealer / asset-manager / leveraged-money long, short and spread, plus open interest | **2018 → 2026** |
| **CBOE VIX history** | `data/positioning/VIX_History.csv` | 9,243 daily OHLC | **1990 → 2026 (36.6 yrs)** |
| **CBOE SKEW** | `data/positioning/SKEW_History.csv` | 9,198 daily | **1990 → 2026 (36.6 yrs)** |
| **CBOE VVIX** | `data/positioning/VVIX_History.csv` | 5,075 daily | 2006 → 2026 (20.4 yrs) |
| **Treasury DTS** | `data/research_data/dts/` | 10 series: operating cash balance, tax deposits, debt subject to limit | 2021 → 2026 |
| **FRED** | `data/research_data/fred/` | DGS10, DXY, EFFR, SOFR, IORB, HY_SPREAD, T10Y2Y, T10Y3M + 3 more | — |
| **CBOE put/call + skew** | `data/research_data/cboe/` | equity, index and total put-call ratios, SKEW archive | — |
| **Dealer gamma** | `data/gex/gex_history.parquet` | 968 days, NDX + SPX: `day, fam, spot, gex_vol, n` | — |
| **Option chains** | `data/gex/I_NDX_*.parquet`, `I_SPX_*.parquet` | two full chains | 2026-08-10 |
| **Options EOD sample** | `data/research_data/cboe_options_sample/` | one full day of EOD option calcs | 2023-08-25 |
| **Index cash** | `data/positioning/` | SPX, NDX, SPY, QQQ from Stooq and Polygon | — |

```bash
# just the free fundamental data, ~68 MB
git sparse-checkout set --no-cone data/research_data data/positioning data/gex
```

---

## 4. Search checkpoints (skip these)

`data/fsearch_ck/` (497 MB), `data/f2_K500/`, `data/f2_K250/` and
`data/pulse_ck_*.pkl` are **regenerable run state**, not source data. They
are over half the repository's weight. Exclude them unless you are resuming
one of those exact searches:

```bash
git sparse-checkout set --no-cone data research \
  ':!data/fsearch_ck' ':!data/f2_K500' ':!data/f2_K250'
```

---

## 5. The research record

Worth more than the data, and entirely original to this project.

| what | where |
|---|---|
| 155 research documents | `research/*.md` |
| Append-only hypothesis ledger — 35 families, scale and verdict each | `research/HYPOTHESIS_LEDGER.md` |
| Cost-per-market ranking: where the toll is smallest | `research/COST_RATIO.md` |
| Measured passive fill rate on MNQ (6.6%) | `research/DEPTH.md` |
| 14 machine-readable result files | `research/*.json` |
| Five-page summary of all 27.55 billion configurations | `research/RESEARCH_DOSSIER.pdf` |

---

## 6. Provenance, so nobody is surprised

- `data/research_data/*`, `data/positioning/*` and `data/gex/*` come from
  CFTC, CBOE, FRED and the US Treasury. Public domain or free to
  redistribute.
- `data/polygon/*` was pulled with a **Polygon.io** subscription,
  `data/depth/*` and `data/poly/*` with **Databento**. Both licence data
  per-subscriber. They are in this public repository, but that does not
  grant you a licence to them — if you intend to rely on this data for
  anything beyond reading along with the research, buy your own
  subscription. Polygon and Databento both have free tiers that cover the
  bar data here.
- `data/nq`, `data/es`, `data/rty` and `data/vix` are vendor-sourced
  1-minute exports of unrecorded origin. Same caution.

## 7. Loading any of it

```python
# 5-minute bars
import pandas as pd
nq = pd.read_csv("data/polygon/NQ_5min.csv", parse_dates=["ts"]).set_index("ts")

# 1-minute contract files, stitched into a continuous front-month series
from research.local_data_loader import (load_intraday_1min, load_intraday_5min,
                                        load_daily, load_vix_1min)
nq8y = load_intraday_1min("nq")       # 8.2 years, rolled 8d before expiry
es   = load_intraday_1min("es")
vix  = load_vix_1min()

# the tier loaders the searcher itself uses
from researcher import data_tiers as DT
t1 = DT.tier1()                        # every 5-minute market, one clock
book = DT.tier3(bar_s=1)               # the NQ book
```

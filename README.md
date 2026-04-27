# NQ Paper-Trading Bot

A multi-strategy NQ-futures paper-trading bot with an institutional-grade
filter stack (HMM regime, VPIN, adverse-selection, GEX, macro / alt-data),
XGBoost ML confirmation, and a live web dashboard.

```
research/   strategy code: indicators, signals, filters, ML, alt-data
bot/        live runtime + paper portfolio
dashboard/  Flask server + static frontend (Lightweight Charts)
data/       cached snapshots, validation results, paper account state
.vscode/    VS Code launch configs
scripts/    setup / run scripts
```

---

## 1. Install

```bash
git clone https://github.com/<your-user>/HFTBot.git
cd HFTBot
./scripts/setup.sh                  # creates .venv and installs deps
source .venv/bin/activate
```

If `setup.sh` doesn't run on Windows, do it manually:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.11 or newer is required. Tested on 3.11 / 3.12 / 3.13.

## 2. Run

Two processes: the bot loop, and the dashboard server.

```bash
# terminal 1 — paper trading loop, polls every 60s
python -m bot.main

# terminal 2 — dashboard at http://localhost:5000
python -m dashboard.server
```

The bot writes `data/dashboard_data.json` each cycle; the dashboard reads
that file and renders the chart, readiness meters, microstructure, and
recent trades.

## 3. Train the ML model (optional)

The whitelist in `data/validation_results.json` is already populated so
the bot will trade out of the box. To retrain XGBoost on fresh data:

```bash
python -m research.ml_model            # full grid (slow)
python -m research.ml_model --fast     # 1-combo smoke
```

Outputs:
- `data/ml_model.pkl`
- `data/ml_features.json`

## 4. Data sources

- `research/local_data_loader.py` reads NQ 1-minute files from `data/nq/`
  (override with `NQ_LOCAL_DATA_DIR`). The repo ships 8 contracts
  (Mar 2024 → Apr 2026, 628k 1-min bars).
- If those files aren't present, `research/data_loader.py` falls back to
  yfinance (NQ=F) and finally a synthetic random-walk so the bot still boots.

## 5. Strategy whitelist

The recommended-signal whitelist comes from
`data/validation_results.json` (any signal with `recommended: true`).
On launch the bot prints something like:

```
[engine] whitelist (7): ['EQ50_SHORT', 'GAP_FILL_LONG', 'GAP_FILL_SHORT',
                        'PDL_TOUCH', 'VOL_COMP_LONG', 'ZSCORE_LONG', 'ZSCORE_SHORT']
```

To regenerate with fresh data:

```bash
python -m research.run_validation              # FAST  (200 permutations)
python -m research.run_validation --full       # FULL  (1000 permutations)
```

That runs the 6-stage pipeline from the spec (signal generation → backtest
with realistic costs → EV → permutation test → walk-forward → Monte Carlo →
parameter sensitivity) on the 2-year local NQ data and rewrites
`data/validation_results.json`.

To search for *new* signals:

```bash
python -m research.discover_signals            # 12 candidates from pattern_discovery4
python -m research.discover_signals --merge    # also append survivors to whitelist
```

## 5b. Trade frequency — filter modes

The 13 production filters can run in three strictness modes. Pick with
`HFT_FILTER_MODE`:

| Mode | Trades/day (measured) | When to use |
|------|----------------------|-------------|
| `STRICT` (default) | ~1.4 | Live capital. Original 13-filter veto chain. |
| `MODERATE` | ~3.3 | More activity, kill-zone becomes a sizing penalty instead of a veto. |
| `AGGRESSIVE` | ~7.9 | Maximum trade rate. Daily-bias and proximity also become sizing penalties. Only cooldown still vetoes. |

```bash
HFT_FILTER_MODE=AGGRESSIVE python -m bot.main
```

Per-field overrides exist (`HFT_MAX_TRADES_PER_DAY`, `HFT_MIN_GAP_MIN`,
`HFT_KILLZONE_AS_VETO`, etc.) — see `research/filter_config.py`.

To preview how many trades a mode would actually fire on the historical
data without placing them:

```bash
python -m research.dry_run_engine
HFT_FILTER_MODE=AGGRESSIVE python -m research.dry_run_engine
```

## 6. Filter stack (per trade)

Every candidate signal must pass, in order:

1. **VPIN** — toxic-flow gauge (block on crash warning, scale size on HIGH).
2. **Adverse selection** — Roll spread + serial correlation.
3. **GEX regime** — extreme positive gamma reduces directional size.
4. **Macro / alt-data** — composite of COT, GEX, insider, congress, WSB.
5. **HMM volatility regime** — per-signal affinity matrix.
6. **Daily bias** — 3-candle bias; mean-reversion fades are exempt.
7. **Vol regime** — sets stop distance and base size multiplier.
8. **Kill zone** — Asian / London / NY AM/PM windows.
9. **Key-level proximity** — PDH/PDL/EQ50 distance check.
10. **R:R minimum** — per-signal, default 1.5.
11. **Cooldown** — 90-min gap, 120 min after a winner, 2 trades/day cap.
12. **ML direction** — XGBoost p_bull / p_bear @ 0.55 threshold.

Sizing is then Kelly-capped (25%) and scaled by every filter's mult.

## 7. Repo layout

```
HFTBot/
├── bot/
│   ├── __init__.py
│   ├── main.py                # run loop + dashboard publisher
│   ├── persistence.py         # JSON I/O for account/trades/dashboard
│   └── portfolio_manager.py   # paper portfolio, fills, exits
├── dashboard/
│   ├── __init__.py
│   ├── server.py              # Flask app
│   └── static/
│       ├── index.html
│       ├── styles.css
│       ├── app.js
│       └── lightweightcharts.js
├── research/
│   ├── __init__.py
│   ├── adverse_selection_detector.py
│   ├── alternative_data.py
│   ├── congressional_trades.py
│   ├── cot_parser.py
│   ├── data_loader.py
│   ├── edgar_insider.py
│   ├── execution_optimizer.py
│   ├── gex_calculator.py
│   ├── indicators.py
│   ├── local_data_loader.py
│   ├── ml_model.py
│   ├── position_sizer.py
│   ├── regime_detector.py
│   ├── signal_engine.py
│   ├── signal_filters.py
│   ├── signal_generator.py
│   ├── vpin_calculator.py
│   └── wsb_sentiment.py
├── data/                      # JSON state, caches, validation results
├── scripts/                   # setup.sh, run_bot.sh, run_dashboard.sh
├── .vscode/launch.json        # Trading Bot / Dashboard / Static Preview
├── requirements.txt
├── .gitignore
└── README.md
```

## 8. Notes about the transfer

This repository was reconstructed from the snapshot exported from the
original development machine. Provided source files (indicators, ML,
signal engine, alternative data, WSB, congress, local-data loader)
are kept verbatim. The previously-compiled `.pyc` modules
(`portfolio_manager`, `persistence`, `pattern_discovery4`) were
re-implemented from their public interfaces — their behaviour matches
how `research/signal_engine.py` and the dashboard JSON use them.

If you have the original Python sources for those modules, drop them
into `bot/` (or `research/`) and the rest of the stack will pick them
up unchanged.

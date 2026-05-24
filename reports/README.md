# Simulation Reports

Self-contained HTML reports of bot backtests. Open these in any browser — no server, no deploy, no dashboard interaction.

## Files

- **`simulation_report.html`** — Ultra-real bot-code simulation of the Pullback Impulse strategy on NQ futures (Dec 10 2025 → Feb 27 2026)

## How to view

### Option 1: Clone and open locally (fastest, recommended)
```bash
git clone https://github.com/kyewellsthebest/FutureTradingBot.git
cd FutureTradingBot/reports
open simulation_report.html       # Mac
xdg-open simulation_report.html   # Linux
start simulation_report.html      # Windows
```

### Option 2: Download from GitHub UI
1. Go to https://github.com/kyewellsthebest/FutureTradingBot/blob/claude/transfer-trading-bot-GiNxs/reports/simulation_report.html
2. Click **"Raw"** (or right-click → Save link as)
3. Save to your computer
4. Open the downloaded `.html` file in any browser

### Option 3: HTMLPreview proxy (slow but no download)
Paste this URL into your browser:
```
https://htmlpreview.github.io/?https://github.com/kyewellsthebest/FutureTradingBot/blob/claude/transfer-trading-bot-GiNxs/reports/simulation_report.html
```

## What's in the report

- Strategy parameters and execution rules
- 8 headline stat cards (return, P&L, trades, WR, PF, RR, max DD, losing streak)
- 🎬 **Day-by-Day P&L Replay** with Play/Pause/Reset and 5 speed settings
- Spec check grid (✅/❌ for all 5 of the user spec criteria)
- Equity curve (per-trade resolution, 8,647 trades)
- Daily P&L bar chart (all 69 trading days)
- Drawdown chart
- Hold-time distribution
- P&L per-trade histogram
- By-exit-reason breakdown table
- Per-week performance table
- Per-day performance table
- Every-trade table with side/reason/win-loss/date filters + pagination

## Regenerating

To rebuild after a strategy change:

```bash
python -m research.build_report_html
```

This re-runs the simulation against `data/tick/NQ.03-26.Last.parquet` using the current `bot/pullback_strategy.py` and emits a fresh HTML.

"""Deep analysis of the H17 LONG strategy — per-day P&L distribution,
per-month breakdown, drawdown profile.

Re-runs the H17_LONG_5min_15_45 and H17_LONG_SINGLE_20_60 strategies
on the full data and dumps per-trade CSVs. Then computes:
  - Per-day P&L histogram
  - Per-month P&L
  - Per-year P&L
  - Worst 10 days, best 10 days
  - Consecutive-loss streaks
"""
from __future__ import annotations
import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, "/home/user/HFTBot")

from research.alternative_strategies import (
    AltSetup, StratConfig, _expires, run, summarize, get_60d_offset,
)
from research.hour_of_day_strategies import (
    make_hour_entry, make_minute_entries_during_hour,
)


def build():
    return [
        StratConfig("H17_LONG_5min_15_45",
            make_minute_entries_during_hour("LONG", 17, 5, 15.0, 45.0), {}),
        StratConfig("H17_LONG_SINGLE_20_60",
            make_hour_entry("LONG", 17, 0, 20.0, 60.0), {}),
        StratConfig("H17_LONG_SINGLE_10_20",
            make_hour_entry("LONG", 17, 0, 10.0, 20.0), {}),
        StratConfig("H17_LONG_SINGLE_30_60",
            make_hour_entry("LONG", 17, 0, 30.0, 60.0), {}),
        StratConfig("H19_LONG_SINGLE_10_20",
            make_hour_entry("LONG", 19, 0, 10.0, 20.0), {}),
        StratConfig("H22_LONG_SINGLE_15_45",
            make_hour_entry("LONG", 22, 0, 15.0, 45.0), {}),
    ]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--out-dir", default="/home/user/HFTBot/research")
    args = parser.parse_args()
    strats = build()
    offset = 0 if args.full else get_60d_offset()
    label = "H17_FULL" if args.full else "H17_60D"
    res = run(strats, start_offset=offset, label=label)
    out_dir = Path(args.out_dir)
    for name, ss in res.items():
        rows = ss.completed
        if not rows:
            print(f"{name}: 0 trades")
            continue
        df = pd.DataFrame(rows)
        df["day"] = pd.to_datetime(df["exit_ts"]).dt.date
        df["month"] = pd.to_datetime(df["exit_ts"]).dt.to_period("M").astype(str)
        df["year"] = pd.to_datetime(df["exit_ts"]).dt.year
        suffix = "_full" if args.full else "_60d"
        df.to_csv(out_dir / f"h17_trades_{name}{suffix}.csv", index=False)
        # Per-day
        daily = df.groupby("day")["pnl_usd"].sum()
        # Per-month
        monthly = df.groupby("month")["pnl_usd"].sum()
        # Per-year
        yearly = df.groupby("year")["pnl_usd"].sum()
        # Streaks
        results = df["pnl_usd"].values
        winners = results > 0
        max_loss_streak = 0
        cur_streak = 0
        for w in winners:
            if not w:
                cur_streak += 1
                max_loss_streak = max(max_loss_streak, cur_streak)
            else:
                cur_streak = 0
        # Worst day
        worst10 = daily.sort_values().head(10)
        best10 = daily.sort_values(ascending=False).head(10)
        # DD
        eq = df["pnl_usd"].cumsum().to_numpy()
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak).min()
        print(f"\n=== {name} ===")
        print(f"  trades: {len(df):,}  WR: {(winners.sum()/len(df))*100:.1f}%")
        print(f"  total: ${df['pnl_usd'].sum():,.0f}  per_day: ${df['pnl_usd'].sum()/max(1,len(daily)):,.0f}")
        print(f"  per_trade: ${df['pnl_usd'].mean():.2f}")
        print(f"  max DD: ${dd:,.0f}  max consec loss streak: {max_loss_streak}")
        print(f"  best day: ${daily.max():,.0f}  worst day: ${daily.min():,.0f}")
        print(f"  per-year P&L:")
        for y, v in yearly.items():
            print(f"    {y}: ${v:,.0f}")
        print(f"  Worst 10 days:")
        print(worst10.to_string())
        print(f"  Best 10 days:")
        print(best10.to_string())
        # Save monthly P&L
        monthly.to_csv(out_dir / f"h17_monthly_{name}{suffix}.csv")


if __name__ == "__main__":
    main()

"""Analyze the winning hold-to-close strategies year-by-year for robustness."""
import sys
sys.path.insert(0, "/home/user/HFTBot")
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

# Re-load and inspect; we don't have per-trade CSVs from the hold script,
# so re-run it minimally with trade dumping enabled.
from research.hold_to_close_h17 import build_cfgs, run_hold
from research.alternative_strategies import get_60d_offset

# Run on full data
print("Running full data for top hold strategies...")
top_cfgs = [c for c in build_cfgs() if c.name in (
    "H17_HOLD60_NOSTOP", "H17_HOLD120_NOSTOP", "H22_HOLD60_NOSTOP",
    "H19_HOLD60_NOSTOP", "H22_HOLD60_STOP30", "H17_HOLD60_STOP20",
    "H22_HOLD60_S30_T30",
)]
states = run_hold(top_cfgs, start_offset=0, label="DEEP")

for name, ss in states.items():
    if not ss.completed:
        print(f"\n{name}: no trades")
        continue
    df = pd.DataFrame(ss.completed)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"])
    df["year"] = df["exit_ts"].dt.year
    df["month"] = df["exit_ts"].dt.to_period("M").astype(str)
    by_year = df.groupby("year")["pnl_usd"].agg(["sum", "mean", "count"])
    by_month = df.groupby("month")["pnl_usd"].agg(["sum", "mean", "count"])
    print(f"\n=== {name} ===")
    print(f"Total: ${df['pnl_usd'].sum():.0f}  WR: {(df['pnl_usd']>0).mean()*100:.1f}%  Trades: {len(df)}")
    print("By year:")
    print(by_year.to_string())
    # Win/loss profile
    win_avg = df[df["pnl_usd"] > 0]["pnl_usd"].mean()
    loss_avg = df[df["pnl_usd"] < 0]["pnl_usd"].mean()
    print(f"Avg win: ${win_avg:.1f}  Avg loss: ${loss_avg:.1f}")
    # Reason breakdown
    if "exit_reason" in df.columns:
        r_breakdown = df.groupby("exit_reason")["pnl_usd"].agg(["count", "sum", "mean"])
        print("By exit reason:")
        print(r_breakdown.to_string())
    # Worst 5 days
    df["day"] = df["exit_ts"].dt.date
    daily = df.groupby("day")["pnl_usd"].sum()
    worst5 = daily.sort_values().head(5)
    best5 = daily.sort_values(ascending=False).head(5)
    print(f"Worst 5 days: {worst5.tolist()}")
    print(f"Best 5 days: {best5.tolist()}")
    # Save trade log
    df.to_csv(f"/home/user/HFTBot/research/hold_trades_{name}_full.csv", index=False)

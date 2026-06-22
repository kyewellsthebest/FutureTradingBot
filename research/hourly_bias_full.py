"""Per-hour bias analysis on FULL data (~767 days), broken down by year.

We need to verify whether the strong Hour 17 UTC LONG bias holds
across the full historical window. If it's a 60-day artifact, the
strategy is overfit.
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "/home/user/HFTBot")

from research.alternative_strategies import iter_tick_chunks, TICK_CSV, US_PER_MIN


def main():
    print("Building 1-min bars from FULL tick data...")
    bars = []
    cur_min = None
    cur_o = cur_h = cur_l = cur_c = float("nan")
    n_ticks = 0
    for chunk in iter_tick_chunks(TICK_CSV, start_offset=0):
        ts = chunk["ts"]
        mid = chunk["mid"]
        minutes = ts // US_PER_MIN
        for i in range(len(ts)):
            m = int(minutes[i])
            if m != cur_min:
                if cur_min is not None:
                    bars.append((cur_min * US_PER_MIN, cur_o, cur_h, cur_l, cur_c))
                cur_min = m
                cur_o = float(mid[i]); cur_h = cur_o; cur_l = cur_o; cur_c = cur_o
            else:
                v = float(mid[i])
                if v > cur_h: cur_h = v
                if v < cur_l: cur_l = v
                cur_c = v
        n_ticks += len(ts)
        if n_ticks % 50_000_000 < 1_000_000:
            print(f"  ticks: {n_ticks/1e6:.0f}M, bars: {len(bars):,}")
    if cur_min is not None:
        bars.append((cur_min * US_PER_MIN, cur_o, cur_h, cur_l, cur_c))
    print(f"Total bars: {len(bars):,}")
    df = pd.DataFrame(bars, columns=["ts_us", "o", "h", "l", "c"])
    df["dt"] = pd.to_datetime(df["ts_us"], unit="us", utc=True)
    df["hour"] = df["dt"].dt.hour
    df["year"] = df["dt"].dt.year
    df.to_parquet("/home/user/HFTBot/research/bars_full.parquet")

    # Hour open-to-close return per year
    df_hh = df.groupby([df["dt"].dt.date, "hour", "year"]).agg(
        open=("o", "first"), close=("c", "last"))
    df_hh["ret_pts"] = df_hh["close"] - df_hh["open"]
    df_hh = df_hh.reset_index()
    by_hy = df_hh.groupby(["year", "hour"])["ret_pts"].agg(["mean", "sum", "count"])
    print("\n=== HOUR 17 BY YEAR ===")
    h17 = by_hy.loc[(slice(None), 17), :]
    print(h17.to_string())
    print("\n=== ALL HOURS PER YEAR ===")
    by_hy.to_csv("/home/user/HFTBot/research/hourly_bias_full_by_year.csv")
    print(by_hy.unstack(level=0)["mean"].fillna(0).round(1).to_string())

    # Aggregate full-period
    by_h = df_hh.groupby("hour")["ret_pts"].agg(["mean", "sum", "count", "std"])
    by_h.to_csv("/home/user/HFTBot/research/hourly_oc_bias_full.csv")
    print("\n=== ALL HOURS, FULL DATA ===")
    print(by_h.sort_values("mean", ascending=False).to_string())


if __name__ == "__main__":
    main()

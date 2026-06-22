"""Compute per-UTC-hour P&L bias for MNQ over the 60-day subset.

For each hour, compute average return from hour-open to hour-close. Then
report the most directionally-biased hours. If ANY hour shows a strong
bias (>1pt/hr average), then strategies trading only that hour might
be viable.

Also probe hour-of-week (Mon-Fri x 0-23).
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd
sys.path.insert(0, "/home/user/HFTBot")

from research.alternative_strategies import (
    iter_tick_chunks, TICK_CSV, US_PER_MIN, US_PER_SEC, get_60d_offset,
)


def main():
    offset = get_60d_offset()
    print(f"60d offset: {offset:,}")
    # Build 1-min bars
    bars = []  # (ts_us, o, h, l, c)
    cur_min = None
    cur_o = cur_h = cur_l = cur_c = float("nan")
    cnt = 0
    for chunk in iter_tick_chunks(TICK_CSV, start_offset=offset):
        ts = chunk["ts"]
        mid = chunk["mid"]
        minutes = ts // US_PER_MIN
        if cur_min is None:
            cur_min = int(minutes[0])
            cur_o = float(mid[0]); cur_h = cur_o; cur_l = cur_o; cur_c = cur_o
        for i in range(len(ts)):
            m = int(minutes[i])
            if m != cur_min:
                bars.append((cur_min * US_PER_MIN, cur_o, cur_h, cur_l, cur_c))
                cur_min = m
                cur_o = float(mid[i]); cur_h = cur_o; cur_l = cur_o; cur_c = cur_o
            else:
                v = float(mid[i])
                if v > cur_h: cur_h = v
                if v < cur_l: cur_l = v
                cur_c = v
        cnt += len(ts)
        if cnt % 10_000_000 < 1_000_000:
            print(f"  ticks: {cnt/1e6:.1f}M, bars: {len(bars):,}")
    if cur_min is not None:
        bars.append((cur_min * US_PER_MIN, cur_o, cur_h, cur_l, cur_c))
    print(f"Total bars: {len(bars):,}")
    df = pd.DataFrame(bars, columns=["ts_us", "o", "h", "l", "c"])
    df["dt"] = pd.to_datetime(df["ts_us"], unit="us", utc=True)
    df["hour"] = df["dt"].dt.hour
    df["dow"] = df["dt"].dt.dayofweek
    # Per-bar return
    df["ret_pts"] = df["c"] - df["o"]

    # Group: per hour
    by_hour = df.groupby("hour")["ret_pts"].agg(["mean", "sum", "count", "std"])
    by_hour["mean_per_min"] = by_hour["mean"]  # avg pts per minute
    by_hour["sum_pts"] = by_hour["sum"]
    print("\n=== PER-HOUR (UTC) AVERAGE RETURN ===")
    print(by_hour.sort_values("mean", ascending=False).to_string())
    by_hour.to_csv("/home/user/HFTBot/research/hourly_bias.csv")

    # Per hour, per day-of-week
    by_hdw = df.groupby(["dow", "hour"])["ret_pts"].agg(["mean", "sum", "count"])
    print("\n=== TOP 20 (DOW, HOUR) by absolute mean per minute ===")
    by_hdw["abs_mean"] = by_hdw["mean"].abs()
    print(by_hdw.sort_values("abs_mean", ascending=False).head(20).to_string())
    by_hdw.to_csv("/home/user/HFTBot/research/hourly_bias_by_dow.csv")

    # Aggregate session-wide (60-minute window) for sharp-edge identification
    # We compute hour-by-hour P&L for an "always LONG entire hour" strategy.
    print("\n=== SUMMARY ===")
    print(f"Best hour for LONG bias: {by_hour['mean'].idxmax()} "
          f"({by_hour['mean'].max():.3f} pts/min avg, "
          f"{by_hour.loc[by_hour['mean'].idxmax(), 'sum']:.1f} total pts)")
    print(f"Best hour for SHORT bias: {by_hour['mean'].idxmin()} "
          f"({by_hour['mean'].min():.3f} pts/min avg, "
          f"{by_hour.loc[by_hour['mean'].idxmin(), 'sum']:.1f} total pts)")

    # Direct "buy at hour open, sell at hour close" hourly returns
    df_hh = df.groupby([df["dt"].dt.date, "hour"]).agg(
        open=("o", "first"), close=("c", "last"))
    df_hh["ret_pts"] = df_hh["close"] - df_hh["open"]
    df_hh = df_hh.reset_index()
    by_hour2 = df_hh.groupby("hour")["ret_pts"].agg(["mean", "sum", "count", "std"])
    print("\n=== HOUR OPEN TO HOUR CLOSE RETURN (pts) ===")
    print(by_hour2.sort_values("mean", ascending=False).to_string())
    by_hour2.to_csv("/home/user/HFTBot/research/hourly_oc_bias.csv")


if __name__ == "__main__":
    main()

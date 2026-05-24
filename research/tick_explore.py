"""Explore tick data to understand structure before strategy design.

Goals:
1. Trade-size distribution (where's the 'large trade' threshold?)
2. Bid-ask spread distribution
3. Hourly trade-rate / volume profile
4. Aggressor balance over time (does delta drift?)
5. Per-day stats (number of days, trades per day)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")


def main():
    print("Loading tick parquet...")
    df = pd.read_parquet(SRC)
    print(f"  rows: {len(df):,}")
    print(f"  date range: {df['ts'].iloc[0]} → {df['ts'].iloc[-1]}")
    n_days = df["ts"].dt.tz_convert("America/New_York").dt.date.nunique()
    print(f"  unique calendar days: {n_days}")
    print()

    # 1. Trade size distribution
    print("=" * 70)
    print("TRADE SIZE DISTRIBUTION")
    print("=" * 70)
    vol = df["volume"].astype(int)
    print(f"  Total volume: {vol.sum():,} contracts")
    print(f"  Number of trades: {len(vol):,}")
    print(f"  Mean trade size: {vol.mean():.2f}")
    print(f"  Median: {vol.median()}")
    for pct in [50, 75, 90, 95, 99, 99.9]:
        print(f"  {pct}th percentile: {np.percentile(vol, pct):.0f}")
    print(f"  Max trade size: {vol.max()}")
    print(f"  Trades >= 10: {(vol >= 10).sum():,}  ({(vol >= 10).mean()*100:.1f}%)")
    print(f"  Trades >= 50: {(vol >= 50).sum():,}  ({(vol >= 50).mean()*100:.2f}%)")
    print(f"  Trades >= 100: {(vol >= 100).sum():,}  ({(vol >= 100).mean()*100:.3f}%)")
    print(f"  Trades >= 250: {(vol >= 250).sum():,}")
    print()

    # 2. Bid-ask spread
    print("=" * 70)
    print("BID-ASK SPREAD")
    print("=" * 70)
    spread = (df["ask"] - df["bid"]).astype(np.float32)
    print(f"  Min: {spread.min():.2f}")
    print(f"  Median: {spread.median():.2f}")
    print(f"  Mean: {spread.mean():.3f}")
    for pct in [50, 75, 90, 95, 99]:
        print(f"  {pct}th: {np.percentile(spread, pct):.2f}")
    print(f"  Max: {spread.max():.2f}")
    # NQ tick = 0.25
    print(f"  In ticks (each 0.25): mean = {spread.mean()/0.25:.2f}")
    print()

    # 3. Hourly activity profile (NY time)
    print("=" * 70)
    print("HOURLY TRADE COUNT (NY time)")
    print("=" * 70)
    ny_hour = df["ts"].dt.tz_convert("America/New_York").dt.hour
    hourly_counts = ny_hour.value_counts().sort_index()
    for h, n in hourly_counts.items():
        bar = "█" * int(n / hourly_counts.max() * 40)
        print(f"  {h:02d}:00  {n:>10,}  {bar}")
    print()

    # 4. Delta over time (per day)
    print("=" * 70)
    print("DAILY NET DELTA (sample first/last 5 days)")
    print("=" * 70)
    df["date"] = df["ts"].dt.tz_convert("America/New_York").dt.date
    df["signed_vol"] = df["volume"] * df["aggressor"]
    daily_delta = df.groupby("date").agg(
        n_trades=("price", "size"),
        total_vol=("volume", "sum"),
        net_delta=("signed_vol", "sum"),
        price_open=("price", "first"),
        price_close=("price", "last"),
    )
    daily_delta["price_change"] = daily_delta["price_close"] - daily_delta["price_open"]
    print(daily_delta.head(5))
    print("...")
    print(daily_delta.tail(5))
    print()
    # Correlation between net delta and same-day price change
    corr = daily_delta["net_delta"].corr(daily_delta["price_change"])
    print(f"Correlation: daily net delta vs daily price change: {corr:.3f}")
    print()

    # 5. Trade-size groups vs price impact
    print("=" * 70)
    print("LARGE TRADE FREQUENCY")
    print("=" * 70)
    avg_per_day = (vol >= 50).sum() / n_days
    print(f"  Trades >= 50 contracts: {avg_per_day:.1f} per day on average")
    print(f"  Trades >= 100 contracts: {(vol >= 100).sum()/n_days:.1f} per day")
    print(f"  Trades >= 250 contracts: {(vol >= 250).sum()/n_days:.2f} per day")


if __name__ == "__main__":
    main()

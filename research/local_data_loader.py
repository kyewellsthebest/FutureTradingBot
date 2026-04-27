"""
Local data loader for the NQ futures 1-minute files at C:/trading_bot/data/.

Files are per-contract-month:
  nq_0624 (Jun 2024), nq_0924 (Sep 2024), nq_1224 (Dec 2024),
  nq_0325, nq_0625, nq_0925, nq_1225, nq_0326, nq_0626.

Format: "YYYYMMDD HHMMSS;open;high;low;close;volume"
Timestamps are UTC.

We stitch files together using front-month convention: each contract is
"active" during the 3 months preceding its expiry. Roll date convention:
use contract until ~8 days before its 3rd-Friday expiry, then roll to next.

Output:
  load_intraday_1min()  -> DataFrame indexed by UTC timestamp, columns O/H/L/C/V
  load_intraday_5min()  -> resampled 5-min version (backward compatible with existing code)
  load_daily()          -> daily OHLCV from RTH sessions
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import os
DATA_ROOT = Path(os.environ.get("NQ_LOCAL_DATA_DIR", "C:/trading_bot/data"))

# (filename, expiry_date, roll_date (use this file UNTIL this date, exclusive))
CONTRACTS = [
    ("nq_0624.txt", date(2024, 6, 21),  date(2024, 6, 10)),
    ("nq_0924.txt", date(2024, 9, 20),  date(2024, 9, 10)),
    ("nq_1224.txt", date(2024, 12, 20), date(2024, 12, 10)),
    ("nq_0325.txt", date(2025, 3, 21),  date(2025, 3, 10)),
    ("nq_0625.txt", date(2025, 6, 20),  date(2025, 6, 10)),
    ("nq_0925.txt", date(2025, 9, 19),  date(2025, 9, 10)),
    ("nq_1225.txt", date(2025, 12, 19), date(2025, 12, 10)),
    ("nq_0326.txt", date(2026, 3, 20),  date(2026, 3, 10)),
    ("nq_0626.txt", date(2026, 6, 19),  date(2026, 6, 19)),  # current front
]


def _parse_file(path: Path) -> pd.DataFrame:
    """Parse a single contract file into OHLCV DataFrame indexed by UTC timestamp."""
    df = pd.read_csv(
        path,
        sep=";",
        header=None,
        names=["ts", "open", "high", "low", "close", "volume"],
        engine="c",
    )
    df["ts"] = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S", utc=True)
    df = df.set_index("ts").sort_index()
    return df


def load_intraday_1min() -> pd.DataFrame:
    """
    Stitch all contract files together using front-month convention.
    Returns 1-min OHLCV DataFrame indexed by UTC timestamp.
    """
    parts: list[pd.DataFrame] = []
    prev_roll: date | None = None
    for idx, (fname, _expiry, roll) in enumerate(CONTRACTS):
        path = DATA_ROOT / fname
        if not path.exists():
            continue
        df = _parse_file(path)
        # Use this contract from prev_roll (or start of file) to its roll date
        start = prev_roll or df.index[0].date()
        end = roll
        mask = (df.index.date >= start) & (df.index.date < end)
        if idx == len(CONTRACTS) - 1:
            # Last contract - use everything up to end of data
            mask = df.index.date >= start
        parts.append(df.loc[mask])
        prev_roll = roll
    combined = pd.concat(parts).sort_index()
    # Deduplicate if any overlap
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined


def load_intraday_5min() -> pd.DataFrame:
    """Resample 1-min data to 5-min bars."""
    m1 = load_intraday_1min()
    m5 = m1.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return m5


def load_daily() -> pd.DataFrame:
    """
    Build daily OHLCV from 1-min RTH data (09:30-16:00 EST / 14:30-21:00 UTC DST).
    Use calendar day in UTC for simplicity; close of RTH approximates daily close.
    """
    m1 = load_intraday_1min()
    # Use full 24h bars, grouped by UTC calendar date, to match yfinance daily convention
    daily = m1.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    # Keep only days with substantial volume (drop weekends/holidays)
    daily = daily[daily["volume"] > 0]
    return daily


if __name__ == "__main__":
    m1 = load_intraday_1min()
    print(f"1-min bars: {len(m1):,}  from {m1.index[0]} to {m1.index[-1]}")
    m5 = load_intraday_5min()
    print(f"5-min bars: {len(m5):,}  from {m5.index[0]} to {m5.index[-1]}")
    d = load_daily()
    print(f"Daily bars: {len(d):,}  from {d.index[0].date()} to {d.index[-1].date()}")

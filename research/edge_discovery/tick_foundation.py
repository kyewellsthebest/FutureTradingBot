"""Tick data foundation.

Input: data/tick/raw/<TICKER>.parquet  (Polygon NQ trades: ts ns-epoch, price, size)
Output (scratchpad cache):
  ticks_<TICKER>.parquet   sorted, deduped, front-month window, ET-localized epoch
  sec1.parquet             continuous 1-second bars with microstructure features

Aggressor side is inferred with the tick rule (uptick = buyer-initiated),
carried forward on zero-ticks. No quote data exists, so spread/queue families
remain untestable; everything trade-derived is fair game.
"""
import sys, warnings
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from numba import njit
import harness as H

RAW = Path(__file__).resolve().parent.parent.parent / "data" / "tick" / "raw"
MONTH = {"H": 3, "M": 6, "U": 9, "Z": 12}
ORDER = ["NQU3", "NQZ3", "NQH4", "NQM4", "NQU4", "NQZ4",
         "NQH5", "NQM5", "NQU5", "NQZ5", "NQH6", "NQM6"]


def third_friday(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def roll_date(tk):
    m, y = MONTH[tk[2]], 2020 + int(tk[3])
    return third_friday(y, m) - timedelta(days=9)


@njit(cache=True)
def tick_rule(price):
    """+1 buyer-initiated, -1 seller-initiated, carry on zero-tick."""
    n = len(price)
    side = np.empty(n, np.int8)
    last = np.int8(1)
    prev = price[0]
    for i in range(n):
        p = price[i]
        if p > prev:
            last = 1
        elif p < prev:
            last = -1
        side[i] = last
        prev = p
    return side


def load_contract(tk):
    df = pd.read_parquet(RAW / f"{tk}.parquet")
    df = df.sort_values("ts", kind="mergesort").drop_duplicates()
    # front-month window
    i = ORDER.index(tk)
    start = pd.Timestamp(roll_date(ORDER[i - 1]), tz="America/New_York") if i else None
    end = pd.Timestamp(roll_date(tk), tz="America/New_York")
    t = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("America/New_York")
    m = t < end
    if start is not None:
        m &= t >= start
    df, t = df[m], t[m]
    # session hygiene + bad prints (robust median over 501 trades)
    dow, hr = t.dt.dayofweek, t.dt.hour
    good = ~((dow == 5) | ((dow == 6) & (hr < 18)) | ((dow == 4) & (hr >= 18)) | (hr == 17))
    df, t = df[good.values], t[good.values]
    med = df["price"].rolling(501, center=True, min_periods=50).median()
    ok = ((df["price"] - med).abs() / med < 0.01).values
    df, t = df[ok], t[ok]
    out = pd.DataFrame({"ts": df["ts"].values, "price": df["price"].values.astype(np.float64),
                        "size": df["size"].values.astype(np.int32)})
    out["side"] = tick_rule(out["price"].to_numpy())
    return out, t


def build_sec1(df, t):
    """1-second bars with microstructure features for one contract slice."""
    sec = (df["ts"].values // 1_000_000_000).astype(np.int64)
    g = pd.DataFrame({
        "sec": sec, "price": df["price"].values, "size": df["size"].values,
        "signed": df["size"].values * df["side"].values,
        "big": (df["size"].values >= 10).astype(np.int32),
        "big_signed": np.where(df["size"].values >= 10,
                               df["size"].values * df["side"].values, 0),
    })
    a = g.groupby("sec", sort=True)
    bars = pd.DataFrame({
        "open": a["price"].first(), "high": a["price"].max(),
        "low": a["price"].min(), "close": a["price"].last(),
        "volume": a["size"].sum(), "n_trades": a["size"].count(),
        "delta": a["signed"].sum(), "n_big": a["big"].sum(),
        "big_delta": a["big_signed"].sum(),
    })
    return bars


if __name__ == "__main__":
    all_bars = []
    for tk in ORDER:
        df, t = load_contract(tk)
        df.to_parquet(H.CACHE / f"ticks_{tk}.parquet")
        b = build_sec1(df, t)
        b["contract"] = tk
        all_bars.append(b)
        print(f"{tk}: {len(df):>10,} ticks  {t.iloc[0]} -> {t.iloc[-1]}  sec-bars={len(b):,}")
    sec1 = pd.concat(all_bars).sort_index()
    sec1 = sec1[~sec1.index.duplicated(keep="first")]
    # panama-adjust roll seams on the second series
    seam_offset = 0.0
    codes = sec1["contract"].values
    closes = sec1["close"].to_numpy().copy()
    opens = sec1["open"].to_numpy().copy()
    highs = sec1["high"].to_numpy().copy()
    lows = sec1["low"].to_numpy().copy()
    switch = np.flatnonzero(codes[1:] != codes[:-1]) + 1
    offset = np.zeros(len(sec1))
    for i in switch:
        gap = opens[i] - closes[i - 1]
        offset[:i] += gap
    for arr in (opens, highs, lows, closes):
        arr += offset
    sec1["open"], sec1["high"], sec1["low"], sec1["close"] = opens, highs, lows, closes
    sec1["close_raw"] = sec1["close"] - offset
    sec1.index.name = "sec"
    sec1.to_parquet(H.CACHE / "sec1.parquet")
    print(f"TOTAL 1s bars: {len(sec1):,}  seams adjusted: {len(switch)}")

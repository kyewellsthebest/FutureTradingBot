"""Second-scale feature layer over the 1s bars from tick_foundation.

Produces a frame compatible with harness.simulate (open/high/low/close, atr,
hhmm, tday) plus tick-microstructure features. All features use information
available at the close of second t; signals fire entry at the next bar's open
(>=1s latency, conservative for these holding periods).
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H


BASE_COLS = ["open", "high", "low", "close", "atr", "hhmm", "tday", "rth"]


def load_sec(with_features=True, columns=None) -> pd.DataFrame:
    """columns: extra feature columns to load besides BASE_COLS (memory guard:
    loading all ~28 columns of the 33M-row frame OOMs a 16GB box)."""
    pq = H.CACHE / "sec1_feat.parquet"
    if with_features and pq.exists():
        cols = None if columns is None else list(dict.fromkeys(BASE_COLS + columns))
        return pd.read_parquet(pq, columns=cols)
    df = pd.read_parquet(H.CACHE / "sec1.parquet")
    idx = pd.to_datetime(df.index, unit="s", utc=True).tz_convert("America/New_York")
    df.index = idx
    df["hour"] = idx.hour
    df["hhmm"] = idx.hour * 100 + idx.minute
    tday = pd.Series(idx.date, index=idx)
    after = idx.hour >= 18
    tday[after] = (idx[after] + pd.Timedelta(hours=6)).date
    df["tday"] = pd.to_datetime(tday.values)
    df["rth"] = (df["hhmm"] >= 930) & (df["hhmm"] < 1600)
    if not with_features:
        return df

    f32 = np.float32
    c = df["close"]
    # second-to-second return & vol (EW over ~10 min of traded seconds)
    ret = c.diff()
    df["ret"] = ret.astype(f32)
    sd = ret.ewm(span=600, min_periods=120).std()
    df["ret_sd"] = sd.astype(f32)
    df["atr"] = (df["high"] - df["low"]).ewm(span=600, min_periods=120).mean().clip(lower=0.25)
    # multi-horizon returns (traded-second clock)
    for w in (10, 30, 60, 300):
        df[f"r{w}"] = (c.diff(w) / (sd * np.sqrt(w)).clip(lower=1e-9)).astype(f32)
    # order-flow imbalance: rolling signed volume over traded seconds
    vol = df["volume"].astype(np.float64)
    for w in (10, 60, 300):
        d = df["delta"].rolling(w, min_periods=w // 2).sum()
        v = vol.rolling(w, min_periods=w // 2).sum()
        df[f"ofi{w}"] = (d / v.clip(lower=1)).astype(f32)
    # activity: trades/sec vs trailing baseline
    ntr = df["n_trades"].astype(np.float64)
    base = ntr.ewm(span=1800, min_periods=300).mean()
    df["burst"] = (ntr.rolling(10).mean() / base.clip(lower=0.1)).astype(f32)
    # large-lot flow
    df["big_flow"] = df["big_delta"].rolling(60, min_periods=30).sum().astype(f32)
    df["n_big60"] = df["n_big"].rolling(60, min_periods=30).sum().astype(f32)
    # silence: seconds since previous traded second (gap in event time)
    tsec = (idx.view(np.int64) // 1_000_000_000)
    df["gap_s"] = pd.Series(tsec, index=idx).diff().astype(f32)
    df.to_parquet(pq)
    return df


if __name__ == "__main__":
    df = load_sec()
    print(len(df), "bars", df.index[0], "->", df.index[-1])
    print(df[["volume", "n_trades", "delta", "n_big"]].describe().round(2).to_string())

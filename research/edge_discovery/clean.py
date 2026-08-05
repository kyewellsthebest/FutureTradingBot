"""Data cleaning for the continuous 1-min series.

Fixes three classes of artifacts that fabricate fake edges:
  1. Bars outside real CME hours (Saturday prints, Sunday daytime, Friday
     evening) — pure garbage in the raw files.
  2. Bad prints: bars whose close deviates >2% from the rolling median of
     neighbors (e.g. NQ printing 611.25 on 2024-01-20).
  3. Contract-roll seams: the loader switches contracts at midnight of the
     roll date with no back-adjustment, so the basis jump (~0.2-0.8%) books
     as a phantom overnight move. We difference-adjust history at each seam
     (panama adjustment). Raw close is kept as `close_raw` for level/round-
     number logic.
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H


def clean(symbol: str = "nq") -> pd.DataFrame:
    df = H.load(symbol)

    # ---- 1. session hygiene (ET): CME equity futures week is
    # Sun 18:00 -> Fri 17:00, with 17:00-18:00 daily maintenance halt
    idx = df.index
    dow, hr = idx.dayofweek, idx.hour
    bad = (dow == 5) | ((dow == 6) & (hr < 18)) | ((dow == 4) & (hr >= 18)) | (hr == 17)
    df = df[~bad]

    # ---- 2. bad prints: close vs centered rolling median of 11
    med = df["close"].rolling(11, center=True, min_periods=3).median()
    dev = (df["close"] - med).abs() / med
    ohlc_bad = (df["high"] < df["low"]) | (df["high"] < df[["open", "close"]].max(axis=1) - 1e-9) \
               | (df["low"] > df[["open", "close"]].min(axis=1) + 1e-9)
    n_bad = int((dev > 0.02).sum() + ohlc_bad.sum())
    df = df[(dev <= 0.02) & ~ohlc_bad]
    print(f"{symbol}: dropped {n_bad} bad-print bars")

    # also clamp intrabar spikes: high/low more than 1.5% away from close get winsorized
    lim = 0.015
    df["high"] = np.minimum(df["high"], df["close"] * (1 + lim))
    df["low"] = np.maximum(df["low"], df["close"] * (1 - lim))

    # ---- 3. roll-seam back adjustment
    df["close_raw"] = df["close"].copy()
    import local_data_loader as ldl
    asset_dir = ldl.DATA_ROOT / symbol
    contracts = ldl._build_contracts(asset_dir)
    roll_dates = [pd.Timestamp(r[2]).tz_localize("America/New_York") for r in contracts[:-1]]
    offset_total = np.zeros(len(df))
    pos = df.index
    closes = df["close"].to_numpy()
    for rd in roll_dates:
        i = pos.searchsorted(rd)
        if i <= 0 or i >= len(df):
            continue
        # gap between last bar before seam and first bar after (within 3h)
        if (pos[i] - pos[i - 1]) > pd.Timedelta(hours=26):
            continue
        gap = df["open"].iloc[i] - closes[i - 1]
        # only treat as seam if the jump is anomalous vs typical bar-to-bar move
        typical = np.nanmedian(np.abs(np.diff(closes[max(0, i - 300):i])))
        if abs(gap) < max(6 * typical, 1e-9):
            continue
        offset_total[:i] += gap
    for col in ("open", "high", "low", "close"):
        df[col] = df[col] + offset_total
    n_seams = int((np.diff(np.concatenate([offset_total, [0]])) != 0).sum())
    print(f"{symbol}: adjusted {n_seams} roll seams, max cumulative offset "
          f"{np.abs(offset_total).max():.1f} pts")
    return df


if __name__ == "__main__":
    for sym in (sys.argv[1:] or ["nq"]):
        df = clean(sym)
        df.to_parquet(H.CACHE / f"{sym}_clean.parquet")
        feat = H.add_features(df)
        feat.to_parquet(H.CACHE / f"{sym}_feat.parquet")
        lv = H.day_levels(feat)
        lv.to_parquet(H.CACHE / f"{sym}_levels.parquet")
        print(f"{sym}: {len(df)} bars cached (clean + features + levels)")

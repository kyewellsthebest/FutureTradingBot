"""Convert NQ.03-26.Last.txt (NinjaTrader Last tick export) -> Parquet.

Input row format (semicolon-separated):
    YYYYMMDD HHMMSS NNNNNNN;price;bid;ask;volume
where NNNNNNN is the .NET 100-ns fraction (7 digits).

Output columns:
    ts      datetime64[ns]   (naive, as-exported exchange clock)
    price   float32
    bid     float32
    ask     float32
    volume  uint32
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
import pandas as pd

SRC = Path("/home/user/FutureTradingBot/data/tick/NQ.03-26.Last.txt")
DST = Path("/home/user/FutureTradingBot/data/tick/NQ.03-26.Last.parquet")
CHUNK = 4_000_000

def main():
    print(f"src {SRC} ({SRC.stat().st_size/1e9:.2f} GB)", flush=True)
    t0 = time.time()
    reader = pd.read_csv(
        SRC, sep=";", header=None,
        names=["ts_raw", "price", "bid", "ask", "volume"],
        dtype={"ts_raw": "string", "price": "float32",
               "bid": "float32", "ask": "float32", "volume": "uint32"},
        chunksize=CHUNK, engine="c",
    )
    parts = []
    total = 0
    for i, ch in enumerate(reader):
        # ts_raw = "YYYYMMDD HHMMSS NNNNNNN"
        s = ch["ts_raw"].str
        date = s[:8]
        hh = s[9:11]; mm = s[11:13]; ss = s[13:15]
        frac = ch["ts_raw"].str[16:]  # 7-digit 100ns fraction
        # Build ns timestamp: date+time to ns, plus frac*100ns
        base = pd.to_datetime(date + hh + mm + ss, format="%Y%m%d%H%M%S")
        ns = pd.to_numeric(frac, errors="coerce").fillna(0).astype("int64") * 100
        ch["ts"] = base.values.astype("datetime64[ns]") + ns.values.astype("timedelta64[ns]")
        parts.append(ch[["ts", "price", "bid", "ask", "volume"]])
        total += len(ch)
        print(f"  chunk {i}: {len(ch):,} rows (total {total:,})  {time.time()-t0:.0f}s", flush=True)
    df = pd.concat(parts, ignore_index=True)
    print(f"concat done: {len(df):,} rows  {time.time()-t0:.0f}s", flush=True)
    print(f"date range: {df['ts'].min()} -> {df['ts'].max()}", flush=True)
    df.to_parquet(DST, engine="pyarrow", compression="zstd", index=False)
    print(f"wrote {DST} ({DST.stat().st_size/1e6:.0f} MB)  total {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()

"""Parse NinjaTrader Last tick CSV into Parquet for fast access.

Input format:
  YYYYMMDD HHMMSS NNNNNNN;PRICE;BID;ASK;VOLUME

Where:
  NNNNNNN is 100-nanosecond ticks (7 digits, .NET DateTime fraction)

Output: Parquet file with columns:
  - ts (datetime64[ns] UTC)
  - price (float32)
  - bid (float32)
  - ask (float32)
  - volume (uint16)
  - aggressor (int8): +1 if price >= ask (buy), -1 if price <= bid (sell), 0 between
"""
from __future__ import annotations
import time
from pathlib import Path
import numpy as np
import pandas as pd

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.txt")
DST = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
CHUNK_SIZE = 2_000_000   # ~2M rows per chunk = ~100MB raw text

def parse_ts(date_str: str, time_str: str, frac_str: str) -> int:
    """Returns nanoseconds since epoch."""
    pass  # we vectorize this below


def main():
    print(f"Source: {SRC}  ({SRC.stat().st_size / 1e9:.2f} GB)")
    print(f"Dest:   {DST}")
    print()

    t0 = time.time()
    chunks_out = []
    total_rows = 0

    # Read CSV in chunks; columns: combined_ts_string;price;bid;ask;vol
    reader = pd.read_csv(
        SRC,
        sep=";",
        header=None,
        names=["ts_raw", "price", "bid", "ask", "volume"],
        dtype={"ts_raw": "string", "price": "float32",
               "bid": "float32", "ask": "float32", "volume": "uint16"},
        chunksize=CHUNK_SIZE,
        engine="c",
    )

    for i, chunk in enumerate(reader):
        # ts_raw looks like "20251210 130130 4760000"
        # Split into date "20251210" + time "130130" + ns_ticks "4760000"
        parts = chunk["ts_raw"].str.split(" ", n=2, expand=True)
        date_str = parts[0]
        time_str = parts[1]
        frac_str = parts[2]

        # Construct full datetime string: "20251210 130130.476"
        # 7-digit fraction = 100-ns ticks. To convert to seconds: divide by 1e7
        # But pandas can parse the date+time, and we'll add fraction as ns
        full = date_str + time_str
        dt = pd.to_datetime(full, format="%Y%m%d%H%M%S", utc=True)
        # add fractional part: 7 digits * 100 ns each = N * 100 ns
        ns_offset = frac_str.astype(np.int64) * 100   # ns
        dt = dt + pd.to_timedelta(ns_offset, unit="ns")

        out = pd.DataFrame({
            "ts": dt,
            "price": chunk["price"].values,
            "bid": chunk["bid"].values,
            "ask": chunk["ask"].values,
            "volume": chunk["volume"].values,
        })

        # Aggressor side: +1 buy (price >= ask), -1 sell (price <= bid), 0 mid
        agg = np.zeros(len(out), dtype=np.int8)
        agg[out["price"].values >= out["ask"].values] = 1
        agg[out["price"].values <= out["bid"].values] = -1
        out["aggressor"] = agg

        chunks_out.append(out)
        total_rows += len(out)
        elapsed = time.time() - t0
        print(f"  chunk {i+1}: {len(out):>9,} rows  (total {total_rows:>11,}  "
              f"elapsed {elapsed:.1f}s, {total_rows/elapsed/1e6:.2f}M rows/s)")

    print(f"\nMerging {len(chunks_out)} chunks...")
    df = pd.concat(chunks_out, ignore_index=True)
    del chunks_out

    print(f"Sorting by timestamp...")
    df = df.sort_values("ts", kind="mergesort").reset_index(drop=True)

    print(f"Writing Parquet to {DST}...")
    df.to_parquet(DST, engine="pyarrow", compression="zstd",
                  compression_level=3, index=False)

    out_size = DST.stat().st_size
    print(f"\nDone. {total_rows:,} ticks.")
    print(f"  Input size:  {SRC.stat().st_size / 1e9:.2f} GB")
    print(f"  Output size: {out_size / 1e6:.0f} MB  "
          f"({out_size / SRC.stat().st_size * 100:.1f}% of original)")
    print(f"  Total elapsed: {time.time() - t0:.1f}s")

    # quick sanity check
    print(f"\nSample rows:")
    print(df.head(3))
    print(df.tail(3))
    print(f"\nAggressor distribution:")
    print(df["aggressor"].value_counts())
    print(f"\nDate range: {df['ts'].iloc[0]} to {df['ts'].iloc[-1]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ONE-TIME historical options fetch (Polygon Options Starter).

Purpose: 2 years of daily bars (close, volume) for EVERY QQQ option
contract - alive or expired. From these the research side rebuilds
an approximate historical gamma map (Black-Scholes inversion of the
option price -> IV -> gamma, volume-weighted) and backtests the
gamma-regime idea against the 2.5-year tick tape WITHOUT waiting
for 30 daily snapshots.

Run (takes roughly 1-3 hours, safe to leave running; resumable -
re-running skips contracts already fetched):
    python3 fetch_options_history.py YOUR_POLYGON_KEY
Output: OPTHIST_QQQ_<n>.parquet shards (~50-200MB total).
Upload them all:  gh release upload week-ticks OPTHIST_QQQ_*.parquet
"""
import datetime as dt
import glob
import os
import sys
import time

import pandas as pd
import requests

KEY = sys.argv[1] if len(sys.argv) > 1 else \
    os.environ.get("POLYGON_API_KEY", "")
if not KEY:
    sys.exit("run: python3 fetch_options_history.py YOUR_KEY")
BASE = "https://api.polygon.io"
UND = "QQQ"
START = (dt.date.today() - dt.timedelta(days=730)).isoformat()
END = dt.date.today().isoformat()
DONE_LOG = "opthist_done.txt"
SHARD_ROWS = 2_000_000

S = requests.Session()


def get(url, params=None):
    params = dict(params or {})
    params["apiKey"] = KEY
    for _ in range(6):
        try:
            r = S.get(url, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(5)
            continue
        if r.status_code == 429:
            time.sleep(12)
            continue
        if r.status_code >= 500:
            time.sleep(5)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"kept failing: {url}")


def list_contracts():
    """All QQQ contracts that existed at any point in the window."""
    out = {}
    for expired in ("false", "true"):
        url = f"{BASE}/v3/reference/options/contracts"
        params = {"underlying_ticker": UND, "expired": expired,
                  "limit": 1000,
                  "expiration_date.gte": START}
        while True:
            j = get(url, params)
            for c in j.get("results", []):
                out[c["ticker"]] = dict(
                    ticker=c["ticker"],
                    expiry=c.get("expiration_date"),
                    strike=c.get("strike_price"),
                    type=c.get("contract_type"))
            nxt = j.get("next_url")
            if not nxt:
                break
            url, params = nxt, {}
        print(f"  listed expired={expired}: total {len(out)}",
              flush=True)
    return list(out.values())


def main():
    t0 = time.time()
    done = set()
    if os.path.exists(DONE_LOG):
        done = set(open(DONE_LOG).read().split())
        print(f"resuming: {len(done)} contracts already fetched")
    cons = list_contracts()
    print(f"contracts to fetch: {len(cons)} "
          f"({time.time()-t0:.0f}s)", flush=True)
    shard, rows, nshard = [], 0, len(glob.glob(
        f"OPTHIST_{UND}_*.parquet"))
    dlog = open(DONE_LOG, "a")
    for i, c in enumerate(cons):
        if c["ticker"] in done:
            continue
        try:
            j = get(f"{BASE}/v2/aggs/ticker/{c['ticker']}/range/1/"
                    f"day/{START}/{END}",
                    {"limit": 50000, "adjusted": "true"})
        except Exception as e:
            print(f"  skip {c['ticker']}: {e}", flush=True)
            continue
        for b in j.get("results") or []:
            shard.append(dict(
                ticker=c["ticker"], expiry=c["expiry"],
                strike=c["strike"], type=c["type"],
                date=b["t"], close=b.get("c"),
                volume=b.get("v"), vwap=b.get("vw")))
        dlog.write(c["ticker"] + "\n")
        rows = len(shard)
        if rows >= SHARD_ROWS:
            nshard += 1
            out = f"OPTHIST_{UND}_{nshard:02d}.parquet"
            pd.DataFrame(shard).to_parquet(out, index=False)
            print(f"  wrote {out} ({rows:,} rows, "
                  f"{i+1}/{len(cons)} contracts, "
                  f"{time.time()-t0:.0f}s)", flush=True)
            shard = []
        if (i + 1) % 1000 == 0:
            dlog.flush()
            print(f"  {i+1}/{len(cons)} contracts "
                  f"({time.time()-t0:.0f}s)", flush=True)
    if shard:
        nshard += 1
        out = f"OPTHIST_{UND}_{nshard:02d}.parquet"
        pd.DataFrame(shard).to_parquet(out, index=False)
        print(f"  wrote {out} ({len(shard):,} rows)")
    print(f"DONE {len(cons)} contracts, {nshard} shards "
          f"({time.time()-t0:.0f}s)")
    print("now: gh release upload week-ticks "
          f"OPTHIST_{UND}_*.parquet")


if __name__ == "__main__":
    main()

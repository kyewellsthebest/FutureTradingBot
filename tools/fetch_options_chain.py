#!/usr/bin/env python3
"""Daily QQQ options-chain snapshot fetcher (Polygon Options Starter).

Purpose: build the dealer-gamma (GEX) dataset. Run ONCE per day,
any time after ~16:30 ET (the chain settles after the close). Each
run saves one small parquet: OPT_QQQ_YYYYMMDD.parquet with one row
per contract: expiry, strike, type, open_interest, implied_vol,
delta, gamma, close price, volume.

Setup:
    pip install requests pandas pyarrow
    export POLYGON_API_KEY=your_key_here
Run:
    python3 fetch_options_chain.py            # today's snapshot
Then upload the OPT_*.parquet files to the week-ticks release like
the tick/quote files.

First run also performs a plan-capability check and prints exactly
what your subscription returns (greeks? OI? how much history via
aggregates?) so the research side can design around reality.
"""
import datetime as dt
import json
import os
import sys
import time

import pandas as pd
import requests

KEY = sys.argv[1] if len(sys.argv) > 1 else \
    os.environ.get("POLYGON_API_KEY", "")
if not KEY:
    try:
        KEY = input("paste your Polygon API key and press "
                    "Enter: ").strip()
    except EOFError:
        KEY = ""
if not KEY:
    sys.exit("no key given - run: python3 fetch_options_chain.py "
             "YOUR_KEY")
BASE = "https://api.polygon.io"
UNDERLYING = "QQQ"
OUTDIR = os.environ.get("OPT_OUTDIR", ".")


def get(url, params=None):
    params = dict(params or {})
    params["apiKey"] = KEY
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(15)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"rate-limited too long: {url}")


def fetch_chain():
    """Full option chain snapshot with greeks + OI, paginated."""
    rows = []
    url = f"{BASE}/v3/snapshot/options/{UNDERLYING}"
    params = {"limit": 250}
    while True:
        j = get(url, params)
        for c in j.get("results", []):
            det = c.get("details", {})
            g = c.get("greeks") or {}
            day = c.get("day") or {}
            rows.append(dict(
                ticker=det.get("ticker"),
                expiry=det.get("expiration_date"),
                strike=det.get("strike_price"),
                type=det.get("contract_type"),
                open_interest=c.get("open_interest"),
                iv=c.get("implied_volatility"),
                delta=g.get("delta"), gamma=g.get("gamma"),
                close=day.get("close"), volume=day.get("volume"),
                underlying=c.get("underlying_asset", {})
                .get("price"),
            ))
        nxt = j.get("next_url")
        if not nxt:
            break
        url, params = nxt, {}
    return pd.DataFrame(rows)


def main():
    d = dt.date.today().strftime("%Y%m%d")
    df = fetch_chain()
    n_oi = int(df["open_interest"].notna().sum())
    n_g = int(df["gamma"].notna().sum())
    print(f"contracts: {len(df)} | with OI: {n_oi} | "
          f"with gamma: {n_g}")
    if len(df) == 0:
        sys.exit("empty chain - check plan/entitlements")
    out = os.path.join(OUTDIR, f"OPT_{UNDERLYING}_{d}.parquet")
    df.to_parquet(out, index=False)
    print(f"saved {out} ({os.path.getsize(out)//1024} KB)")
    # ---- one-time capability probe (cheap, informative)
    probe = {}
    try:
        j = get(f"{BASE}/v3/reference/options/contracts",
                {"underlying_ticker": UNDERLYING, "expired": "true",
                 "limit": 1})
        probe["expired_contracts_listable"] = bool(j.get("results"))
    except Exception as e:
        probe["expired_contracts_listable"] = f"error {e}"
    try:
        tick = df["ticker"].dropna().iloc[0]
        past = (dt.date.today() - dt.timedelta(days=400)) \
            .strftime("%Y-%m-%d")
        j = get(f"{BASE}/v2/aggs/ticker/{tick}/range/1/day/"
                f"{past}/{dt.date.today()}", {"limit": 5})
        probe["daily_aggs_history"] = j.get("resultsCount", 0)
    except Exception as e:
        probe["daily_aggs_history"] = f"error {e}"
    print("capability probe:", json.dumps(probe))
    print("NOTE: historical OI/greeks are generally NOT served "
          "retroactively - the dataset builds forward from today. "
          "Run daily; 30 snapshots = first regime test.")


if __name__ == "__main__":
    main()

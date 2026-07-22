#!/usr/bin/env python3
"""TICK-LEVEL MNQ trades + quotes fetch from Polygon Futures Advanced.

Why this exists
---------------
Our 26-day microstructure test failed for a RESOLUTION reason: the quotes
we had were 1-second AVERAGES, which destroy queue imbalance / microprice /
OFI (they live at the message level, sub-second). Polygon Futures Advanced
serves RAW tick trades and RAW BBO quotes (bid/ask price + SIZE, nanosecond
stamps). That is exactly what the decisive predictive test needs - no
Databento required.

This script runs headless on a GitHub Actions runner (see
.github/workflows/polygon-futures-fetch.yml). You never keep a tab open and
nothing lands on your device: output parquet is pushed straight to a GitHub
release. It pulls HISTORICAL data in bulk, so there is no week-long live
capture - a single overnight run grabs the past N weeks at once.

Modes
-----
  probe    - CHEAP. Lists MNQ contracts, prints the front-month ticker, and
             dumps ONE raw trade + ONE raw quote JSON so we can confirm the
             exact field names before spending hours. ALWAYS run this first.
  trades   - full tick trade tape for the window
  quotes   - full tick BBO quote tape for the window (the big one)
  both     - trades then quotes

Run locally:
    python3 tools/fetch_polygon_futures.py probe  YOUR_KEY
    python3 tools/fetch_polygon_futures.py both   YOUR_KEY  2026-06-01 2026-07-15
Output: PGF_MNQ_TRADES_<n>.parquet / PGF_MNQ_QUOTES_<n>.parquet shards.
Upload: gh release upload week-ticks PGF_MNQ_*.parquet --clobber

The API key must come from an env var / CLI arg (a GitHub secret in CI),
NEVER be committed to the repo.
"""
import datetime as dt
import glob
import json
import os
import sys
import time

import pandas as pd
import requests

# ------------------------------------------------------------------ config
BASE = "https://api.polygon.io"
PRODUCT = "MNQ"                 # Micro E-mini Nasdaq-100
SHARD_ROWS = 3_000_000         # rows per parquet shard (quotes are dense)
PAGE_LIMIT = 50_000            # Polygon max page size for tick endpoints
DONE_LOG = "pgf_done.txt"      # resume marker: "<kind> <ticker> <day>"

S = requests.Session()


def _args():
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    key = sys.argv[2] if len(sys.argv) > 2 else \
        os.environ.get("POLYGON_API_KEY", "")
    start = sys.argv[3] if len(sys.argv) > 3 else \
        (dt.date.today() - dt.timedelta(days=21)).isoformat()
    end = sys.argv[4] if len(sys.argv) > 4 else dt.date.today().isoformat()
    ticker = sys.argv[5] if len(sys.argv) > 5 else \
        os.environ.get("MNQ_TICKER", "")   # optional override
    if not key:
        sys.exit("usage: fetch_polygon_futures.py "
                 "<probe|trades|quotes|both> KEY [START] [END] [TICKER]")
    return mode, key, start, end, ticker


def get(url, params, key):
    params = dict(params or {})
    params["apiKey"] = key
    for attempt in range(7):
        try:
            r = S.get(url, params=params, timeout=45)
        except requests.RequestException:
            time.sleep(min(5 * (attempt + 1), 30))
            continue
        if r.status_code == 429:
            time.sleep(15)
            continue
        if r.status_code >= 500:
            time.sleep(min(5 * (attempt + 1), 30))
            continue
        if r.status_code == 403:
            # surface the body: plan/entitlement problems say why here
            sys.exit(f"403 from Polygon: {r.text[:400]}\n"
                     "-> your key may lack the Futures Advanced entitlement.")
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"kept failing: {url}")


# ---------------------------------------------------- contract discovery
def list_contracts(key):
    """Every MNQ contract Polygon knows (active + recently expired)."""
    out = {}
    for active in ("true", "false"):
        url = f"{BASE}/futures/vX/contracts"
        params = {"product_code": PRODUCT, "active": active, "limit": 250}
        while True:
            j = get(url, params, key)
            for c in j.get("results", []):
                tk = c.get("ticker") or c.get("contract_code")
                if tk:
                    out[tk] = c
            nxt = j.get("next_url")
            if not nxt:
                break
            url, params = nxt, {}
    return list(out.values())


def _expiry_of(c):
    for k in ("last_trade_date", "expiration_date", "last_trading_date",
              "first_notice_date"):
        if c.get(k):
            return str(c[k])
    return "9999-99-99"


def pick_front_month(contracts, on_date):
    """Front month = nearest not-yet-expired contract as of on_date."""
    fut = [c for c in contracts if _expiry_of(c) >= on_date]
    fut.sort(key=_expiry_of)
    return fut[0] if fut else (
        sorted(contracts, key=_expiry_of)[-1] if contracts else None)


# ------------------------------------------------------------ tick pull
TRADE_KEYS = ("PGF_MNQ_TRADES", ["price", "size", "timestamp"])
QUOTE_KEYS = ("PGF_MNQ_QUOTES",
              ["bid_price", "bid_size", "ask_price", "ask_size", "timestamp"])


def _ns(day, end_of=False):
    d = dt.date.fromisoformat(day)
    base = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
    if end_of:
        base += dt.timedelta(days=1)
    return int(base.timestamp() * 1_000_000_000)


def fetch_kind(kind, ticker, start, end, key):
    """Pull one tick endpoint over [start, end] day-by-day, sharded."""
    endpoint = "trades" if kind == "trades" else "quotes"
    prefix = TRADE_KEYS[0] if kind == "trades" else QUOTE_KEYS[0]
    done = set()
    if os.path.exists(DONE_LOG):
        done = set(open(DONE_LOG).read().splitlines())
    dlog = open(DONE_LOG, "a")
    days = pd.bdate_range(start, end)            # weekdays only
    shard, nshard = [], len(glob.glob(f"{prefix}_*.parquet"))
    t0 = time.time()
    for d in days:
        day = d.date().isoformat()
        marker = f"{kind} {ticker} {day}"
        if marker in done:
            continue
        url = f"{BASE}/futures/vX/{endpoint}/{ticker}"
        params = {"timestamp.gte": _ns(day),
                  "timestamp.lt": _ns(day, end_of=True),
                  "order": "asc", "sort": "timestamp", "limit": PAGE_LIMIT}
        nrows_day = 0
        while True:
            j = get(url, params, key)
            res = j.get("results") or []
            for r in res:
                r["_ticker"] = ticker
                shard.append(r)
            nrows_day += len(res)
            nxt = j.get("next_url")
            if not nxt or not res:
                break
            url, params = nxt, {}
            if len(shard) >= SHARD_ROWS:
                nshard += 1
                out = f"{prefix}_{nshard:03d}.parquet"
                pd.DataFrame(shard).to_parquet(out, index=False)
                print(f"  wrote {out} ({len(shard):,} rows) "
                      f"[{time.time()-t0:.0f}s]", flush=True)
                shard = []
        dlog.write(marker + "\n")
        dlog.flush()
        print(f"  {kind} {day}: {nrows_day:,} rows "
              f"[{time.time()-t0:.0f}s]", flush=True)
    if shard:
        nshard += 1
        out = f"{prefix}_{nshard:03d}.parquet"
        pd.DataFrame(shard).to_parquet(out, index=False)
        print(f"  wrote {out} ({len(shard):,} rows)", flush=True)
    print(f"DONE {kind}: {nshard} shards [{time.time()-t0:.0f}s]", flush=True)


# ---------------------------------------------------------------- probe
def probe(ticker, start, end, key):
    print("=== PROBE: confirm contract + tick schema (cheap) ===")
    cons = list_contracts(key)
    print(f"MNQ contracts found: {len(cons)}")
    for c in sorted(cons, key=_expiry_of)[:12]:
        tk = c.get("ticker") or c.get("contract_code")
        print(f"   {tk:14s} exp={_expiry_of(c)}")
    fm = ticker or (pick_front_month(cons, start) or {}).get("ticker") \
        or (pick_front_month(cons, start) or {}).get("contract_code")
    print(f"\n>>> front-month for {start}: {fm}")
    if not fm:
        print("!! could not resolve a ticker - inspect the list above.")
        return
    for endpoint, tag in (("trades", "TRADE"), ("quotes", "QUOTE")):
        url = f"{BASE}/futures/vX/{endpoint}/{fm}"
        j = get(url, {"order": "asc", "sort": "timestamp", "limit": 1}, key)
        res = (j.get("results") or [{}])
        print(f"\n--- sample {tag} ({endpoint}) ---")
        print(json.dumps(res[0], indent=2)[:900])
    print("\nProbe OK. If field names match the parser, run mode=both.")


def main():
    mode, key, start, end, ticker = _args()
    print(f"mode={mode} product={PRODUCT} window={start}..{end} "
          f"ticker={ticker or '(auto front-month)'}", flush=True)
    if mode == "probe":
        probe(ticker, start, end, key)
        return
    if not ticker:
        cons = list_contracts(key)
        fm = pick_front_month(cons, start)
        ticker = (fm or {}).get("ticker") or (fm or {}).get("contract_code")
        print(f"auto front-month: {ticker}", flush=True)
    if not ticker:
        sys.exit("no MNQ contract resolved; run probe mode to inspect.")
    if mode in ("trades", "both"):
        fetch_kind("trades", ticker, start, end, key)
    if mode in ("quotes", "both"):
        fetch_kind("quotes", ticker, start, end, key)


if __name__ == "__main__":
    main()

"""
Fetch Polygon.io futures history for v14 cross-asset mining.

Runs on a GitHub Actions runner (which has open internet — the research
sandbox does not). Downloads ~2.5 years of 5-min bars for a basket of
CME futures, stitches continuous front-month series, and writes CSVs to
data/polygon/ which the workflow then commits back to the repo.

Products (all on the Polygon Futures Starter plan):
  Equity index : NQ, ES, RTY, YM
  Treasuries   : ZN (10y), ZB (30y)
  Commodities  : GC (gold), CL (crude), HG (copper), SI (silver)
  Currency     : 6E (euro), 6J (yen)

API key: env var POLYGON_API.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "polygon"
OUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                      stream=sys.stdout)
log = logging.getLogger("fetch_polygon")

KEY = os.environ.get("POLYGON_API") or os.environ.get("POLYGON_API_KEY")
# 8 core products — equity index, treasuries, gold, crude. Dropped SI/HG/
# 6E/6J to cut API calls; these 8 cover the cross-asset families we mine.
PRODUCTS = ["NQ", "ES", "RTY", "YM", "ZN", "ZB", "GC", "CL"]
HISTORY_DAYS = 920   # ~2.5 years
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}
QUARTERLY_CODES = set("HMUZ")   # only download quarterly front-month contracts


def _is_quarterly(ticker: str, product: str) -> bool:
    """True if ticker is a quarterly contract, e.g. NQH6 / ESM7.
    The month code is the char right after the product code."""
    rest = ticker[len(product):]
    return len(rest) >= 2 and rest[0] in QUARTERLY_CODES and rest[1:].isdigit()


def _get(url: str, tries: int = 4):
    """GET JSON with retry/backoff for Polygon rate limits."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:   # rate limited
                wait = 2 ** attempt * 5
                log.info(f"  rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            log.warning(f"  HTTP {e.code}: {body.get('message') or body.get('error')}")
            return None
        except Exception as e:
            log.warning(f"  fetch error: {e}")
            time.sleep(3)
    return None


def list_contracts(product: str) -> list[dict]:
    """All contracts for a product with last_trade_date inside our window."""
    today = date.today()
    floor = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    url = (f"https://api.polygon.io/futures/v1/contracts"
            f"?product_code={product}&last_trade_date.gte={floor}"
            f"&limit=1000&apiKey={KEY}")
    d = _get(url)
    if not d:
        return []
    rows = [r for r in (d.get("results") or [])
              if isinstance(r, dict) and r.get("ticker") and r.get("last_trade_date")
              and _is_quarterly(r["ticker"], product)]
    rows.sort(key=lambda r: r["last_trade_date"])
    return rows


def fetch_contract_bars(ticker: str) -> pd.DataFrame | None:
    """5-min OHLCV bars for one contract."""
    url = (f"https://api.polygon.io/futures/v1/aggs/{ticker}"
            f"?resolution=5_minute&limit=50000&apiKey={KEY}")
    d = _get(url)
    if not d:
        return None
    results = d.get("results") or []
    rows = []
    for r in results:
        try:
            ts = pd.Timestamp(int(r["window_start"]), unit="ns", tz="UTC")
            rows.append((ts, float(r["open"]), float(r["high"]),
                          float(r["low"]), float(r["close"]),
                          float(r.get("volume", 0))))
        except Exception:
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]
                        ).set_index("ts").sort_index()
    return df[~df.index.duplicated(keep="last")]


def build_continuous(product: str) -> pd.DataFrame | None:
    """Stitch a continuous front-month series. For each contract, keep the
    bars from when it becomes front-month until its last_trade_date; the
    next contract takes over from there."""
    contracts = list_contracts(product)
    if not contracts:
        log.warning(f"{product}: no contracts found")
        return None
    log.info(f"{product}: {len(contracts)} contracts in window")
    segments = []
    prev_roll = None
    for c in contracts:
        ticker = c["ticker"]
        ltd = pd.Timestamp(c["last_trade_date"], tz="UTC")
        bars = fetch_contract_bars(ticker)
        time.sleep(0.4)   # be gentle on rate limits
        if bars is None or bars.empty:
            continue
        # This contract is front-month from prev_roll until its last_trade_date
        seg = bars[bars.index <= ltd]
        if prev_roll is not None:
            seg = seg[seg.index > prev_roll]
        if not seg.empty:
            segments.append(seg)
            log.info(f"  {ticker}: {len(seg)} bars "
                       f"({seg.index[0].date()} → {seg.index[-1].date()})")
        prev_roll = ltd
    if not segments:
        return None
    cont = pd.concat(segments).sort_index()
    return cont[~cont.index.duplicated(keep="last")]


def main():
    if not KEY:
        log.error("POLYGON_API not set — aborting")
        sys.exit(1)
    summary = {}
    for product in PRODUCTS:
        log.info(f"=== {product} ===")
        try:
            df = build_continuous(product)
        except Exception as e:
            log.warning(f"{product} crashed: {e}")
            df = None
        if df is None or df.empty:
            summary[product] = "FAILED"
            continue
        out = OUT_DIR / f"{product}_5min.csv"
        df.to_csv(out)
        summary[product] = f"{len(df)} bars {df.index[0].date()}→{df.index[-1].date()}"
        log.info(f"{product}: wrote {len(df):,} bars → {out.name}")
    log.info("=" * 50)
    log.info("SUMMARY")
    for p, s in summary.items():
        log.info(f"  {p}: {s}")
    (OUT_DIR / "_fetch_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

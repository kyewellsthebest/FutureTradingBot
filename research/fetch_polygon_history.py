"""
Fetch Polygon.io futures history — continuous front-month 5-min bars.

Runs on a GitHub Actions runner (open internet — the research sandbox is
network-restricted). Writes CSVs to data/polygon/ which the workflow
commits back to the repo.

WHY THIS VERSION EXISTS
-----------------------
Earlier versions queried Polygon's /futures/v1/contracts endpoint to
discover contract tickers. That endpoint returns mostly SPREAD / BUTTERFLY
pseudo-contracts ("YM:BF H6-M6-U6") and its outright-contract coverage is
unreliable — so the discovery step found nothing and every product FAILED.

This version does NOT touch the contracts endpoint. CME equity-index and
the other liquid futures roll on a fixed quarterly cycle (H/M/U/Z = Mar/
Jun/Sep/Dec), expiring the third Friday of the contract month. So the
front-month ticker for any date is fully determined by the calendar — we
CONSTRUCT every quarterly ticker for the history window and fetch its
aggregates directly. The only Polygon endpoint used is the aggregates one
(/futures/v1/aggs/{ticker}), which is confirmed working.

API key: env var POLYGON_API.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
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
# override with e.g. PRODUCTS="MBT" to fetch a single product without
# re-downloading the whole universe
_default_products = [
    # equity index          rates                   metals
    "NQ", "ES", "RTY", "YM", "ZT", "ZF", "ZN", "ZB", "GC", "SI", "HG",
    # energy                 FX                       crypto (monthly)
    "CL", "NG", "RB", "HO", "6E", "6B", "6J", "6A", "MBT", "ETH",
    # grains
    "ZC", "ZS", "ZW",
]
PRODUCTS = (os.environ.get("PRODUCTS", "").split(",")
            if os.environ.get("PRODUCTS") else _default_products)
PRODUCTS = [p.strip().upper() for p in PRODUCTS if p.strip()]
HISTORY_DAYS = 920                       # ~2.5 years
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}   # quarterly cycle
ALL_MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
                  7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
# products on a MONTHLY listing cycle (CME crypto: expiry = LAST Friday
# of the contract month, not the third)
MONTHLY_PRODUCTS = {"MBT", "BTC", "MET", "ETH"}


def _third_friday(year: int, month: int) -> date:
    """Third Friday of a month — CME equity-index futures expiry."""
    d = date(year, month, 1)
    first_friday = 1 + ((4 - d.weekday()) % 7)   # weekday(): Fri == 4
    return date(year, month, first_friday + 14)


def _last_friday(year: int, month: int) -> date:
    """Last Friday of a month — CME crypto futures expiry."""
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


# Metals/energy do NOT trade the quarterly H/M/U/Z cycle. Building gold
# from March/September contracts left the "continuous" series on a
# near-dead contract for half of every year (June 2026: 213 bars where
# ~1,600 belong — found 2026-07-28 when phantom gaps faked fade signals
# in a replay). Cycle = liquid delivery months; roll = day of the month
# BEFORE delivery (mirrors the live engine's front_symbol rules).
PRODUCT_CYCLES = {
    "GC": ([2, 4, 6, 8, 10, 12], 25),
    "SI": ([3, 5, 7, 9, 12], 25),
    "HG": ([3, 5, 7, 9, 12], 25),
    "CL": (list(range(1, 13)), 18),
    "NG": (list(range(1, 13)), 25),
    "RB": (list(range(1, 13)), 25),
    "HO": (list(range(1, 13)), 25),
}


def quarterly_tickers(product: str) -> list[tuple[str, date]]:
    """Every contract (ticker, roll-date) whose roll falls inside the
    history window — constructed from the calendar, no API call.
    Quarterly (H/M/U/Z, 3rd-Friday) for index/rate products; per-product
    liquid-month cycles for metals/energy (PRODUCT_CYCLES); MONTHLY
    (all 12 codes, LAST-Friday) for CME crypto (MBT etc.)."""
    today = date.today()
    start = today - timedelta(days=HISTORY_DAYS + 120)
    end = today + timedelta(days=120)
    out: list[tuple[str, date]] = []
    if product in PRODUCT_CYCLES:
        months, roll_day = PRODUCT_CYCLES[product]
        for year in range(start.year, end.year + 2):
            for m in months:
                # roll happens in the month BEFORE delivery
                ry, rm = (year, m - 1) if m > 1 else (year - 1, 12)
                exp = date(ry, rm, roll_day)
                if start <= exp <= end:
                    out.append((f"{product}{ALL_MONTH_CODE[m]}{year % 10}", exp))
        out.sort(key=lambda t: t[1])
        return out
    monthly = product in MONTHLY_PRODUCTS
    codes = ALL_MONTH_CODE if monthly else MONTH_CODE
    for year in range(start.year, end.year + 1):
        for month, code in codes.items():
            exp = (_last_friday(year, month) if monthly
                   else _third_friday(year, month))
            if start <= exp <= end:
                out.append((f"{product}{code}{year % 10}", exp))
    out.sort(key=lambda t: t[1])
    return out


def _get(url: str, tries: int = 4) -> tuple[dict | None, str | None]:
    """GET JSON with retry/backoff. Returns (data, error) — error is a
    short human string so failures are visible in the Actions log."""
    safe = url.split("apiKey=")[0] + "apiKey=***"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt * 5
                log.info(f"  rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            return None, (f"HTTP {e.code}: "
                          f"{body.get('message') or body.get('error') or safe}")
        except Exception as e:
            if attempt < tries - 1:
                time.sleep(3)
                continue
            return None, f"{type(e).__name__}: {e}"
    return None, "exhausted retries"


def fetch_contract_bars(ticker: str, resolution: str = "5_minute"
                         ) -> pd.DataFrame | None:
    """OHLCV bars for one outright contract from the aggs endpoint.
    `resolution`: "1_minute" / "5_minute" / "1_hour" / "1_day"."""
    url = (f"https://api.polygon.io/futures/v1/aggs/{ticker}"
           f"?resolution={resolution}&limit=50000&apiKey={KEY}")
    data, err = _get(url)
    if err:
        log.info(f"  {ticker}: {err}")
        return None
    results = (data or {}).get("results") or []
    if not results:
        log.info(f"  {ticker}: 0 bars (status={(data or {}).get('status')})")
        return None
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
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close",
                                     "volume"]).set_index("ts").sort_index()
    return df[~df.index.duplicated(keep="last")]


def build_continuous(product: str, resolution: str = "5_minute"
                      ) -> pd.DataFrame | None:
    """Stitch a continuous front-month series. Each quarterly contract
    contributes the bars between the prior contract's expiry and its own."""
    tickers = quarterly_tickers(product)
    log.info(f"{product} ({resolution}): {len(tickers)} quarterly contracts "
             f"constructed ({tickers[0][0]} … {tickers[-1][0]})")
    segments = []
    prev_exp = None
    for ticker, exp in tickers:
        bars = fetch_contract_bars(ticker, resolution=resolution)
        time.sleep(0.3)                  # gentle on rate limits
        exp_ts = pd.Timestamp(exp, tz="UTC")
        if bars is None or bars.empty:
            prev_exp = exp_ts
            continue
        seg = bars[bars.index <= exp_ts]
        if prev_exp is not None:
            seg = seg[seg.index > prev_exp]
        if not seg.empty:
            segments.append(seg)
            log.info(f"  {ticker}: {len(seg)} bars "
                     f"({seg.index[0].date()} → {seg.index[-1].date()})")
        prev_exp = exp_ts
    if not segments:
        return None
    cont = pd.concat(segments).sort_index()
    return cont[~cont.index.duplicated(keep="last")]


def main() -> None:
    if not KEY:
        log.error("POLYGON_API not set — aborting")
        sys.exit(1)
    summary = {}

    # 5-min for all products (research / cross-asset backtesting)
    for product in PRODUCTS:
        log.info(f"=== {product} 5-min ===")
        try:
            df = build_continuous(product, resolution="5_minute")
        except Exception as e:
            log.warning(f"{product} 5-min crashed: {e}")
            df = None
        if df is None or df.empty:
            summary[f"{product}_5min"] = "FAILED"
            continue
        out = OUT_DIR / f"{product}_5min.csv"
        df.to_csv(out)
        summary[f"{product}_5min"] = (f"{len(df)} bars "
                                       f"{df.index[0].date()}→{df.index[-1].date()}")
        log.info(f"{product} 5-min: wrote {len(df):,} bars → {out.name}")

    # 1-min for NQ only (live trading + 1-min strategy backtest). 1-min
    # for all 8 products would be ~560MB committed; we only need it for
    # the one product we actually trade. Skipped when PRODUCTS override
    # excludes NQ (e.g. an MBT-only fetch).
    if "NQ" in PRODUCTS:
        log.info("=== NQ 1-min ===")
        try:
            df1 = build_continuous("NQ", resolution="1_minute")
        except Exception as e:
            log.warning(f"NQ 1-min crashed: {e}")
            df1 = None
        if df1 is None or df1.empty:
            summary["NQ_1min"] = "FAILED"
        else:
            out = OUT_DIR / "NQ_1min.csv"
            df1.to_csv(out)
            summary["NQ_1min"] = (f"{len(df1)} bars "
                                   f"{df1.index[0].date()}→{df1.index[-1].date()}")
            log.info(f"NQ 1-min: wrote {len(df1):,} bars → {out.name}")

    log.info("=" * 50)
    log.info("SUMMARY")
    for p, s in summary.items():
        log.info(f"  {p}: {s}")
    (OUT_DIR / "_fetch_summary.json").write_text(json.dumps(summary, indent=2))
    if all(v == "FAILED" for v in summary.values()):
        log.error("Every product failed — see per-ticker errors above. The "
                  "aggs endpoint or ticker format may differ on this plan.")
        sys.exit(1)


if __name__ == "__main__":
    main()

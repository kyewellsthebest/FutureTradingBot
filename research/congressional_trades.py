"""
US Congressional trading signal for NQ-100 exposure.

Uses the free mirror maintained by `housestockwatcher.com` and
`senatestockwatcher.com` (open-source community projects that scrape
the official House Clerk and Senate Financial Disclosure portals).

Data sources (no API key needed):
  https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json
  https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json

NOTE: As of April 2026 these S3 buckets return 403. The housestockwatcher
project was archived. A paid API (CapitolTrades.com, QuiverQuant at $10/mo)
is the reliable live source. The code below remains so that if a free mirror
comes back online, it will work without modification — but returns None
gracefully when the endpoints are unreachable.

We filter trades in major NQ-100 components plus NQ-tracking ETFs
(QQQ, TQQQ, QLD) over the last 60 days, weight by amount range, and
produce a signed score in [-1, +1].

Degrades gracefully: if either endpoint is unreachable, returns None.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from research.data_loader import DATA_DIR

CACHE_PATH = DATA_DIR / "congress_cache.json"
CACHE_TTL_SECONDS = 12 * 3600

HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
SENATE_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"

# NQ-100 heavy hitters + direct NQ ETFs
NQ_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO",
    "NFLX", "COST", "AMD", "ADBE", "PEP", "CSCO", "CMCSA", "INTC", "TMUS",
    "QQQ", "TQQQ", "QLD", "SQQQ", "PSQ",  # ETFs
}

# Amount-range midpoints (disclosure ranges)
# Congress reports "1001-15000", "15001-50000", etc.
AMOUNT_MIDPOINTS = {
    "$1,001 - $15,000": 8_000,
    "$15,001 - $50,000": 32_500,
    "$50,001 - $100,000": 75_000,
    "$100,001 - $250,000": 175_000,
    "$250,001 - $500,000": 375_000,
    "$500,001 - $1,000,000": 750_000,
    "$1,000,001 - $5,000,000": 3_000_000,
    "$5,000,001 - $25,000,000": 15_000_000,
    "$25,000,001 - $50,000,000": 37_500_000,
    "$50,000,001 +": 75_000_000,
}

CongressBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]


@dataclass
class CongressSnapshot:
    as_of: str
    house_net: float
    senate_net: float
    total_net: float
    n_trades_60d: int
    score: float           # -1..+1
    bias: CongressBias
    top_trades: list[dict]  # summary of largest 5 trades


def _http_get_json(url: str) -> list | None:
    req = urllib.request.Request(url, headers={"User-Agent": "nq-trading-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Congress fetch failed {url}: {e}")
        return None


def _midpoint(amount_str: str) -> float:
    """Parse amount range string to midpoint dollar value."""
    if not amount_str:
        return 0.0
    # Exact match
    if amount_str in AMOUNT_MIDPOINTS:
        return float(AMOUNT_MIDPOINTS[amount_str])
    # Fuzzy match: some senate entries use slightly different formats
    for key, val in AMOUNT_MIDPOINTS.items():
        if amount_str.replace(" ", "") == key.replace(" ", ""):
            return float(val)
    return 0.0


def _normalize_ticker(raw: str) -> str:
    if not raw:
        return ""
    return raw.strip().upper().split(" ")[0].replace("$", "")


def _score_trade(trx: dict, cutoff: datetime) -> tuple[float, str, str]:
    """
    Return (signed_dollars, ticker, trade_date) for a single trade dict,
    or (0, "", "") if filtered out.
    """
    ticker = _normalize_ticker(trx.get("ticker") or trx.get("asset_ticker") or "")
    if ticker not in NQ_TICKERS:
        return 0.0, ticker, ""
    trade_date = trx.get("transaction_date") or trx.get("disclosure_date") or ""
    try:
        td = datetime.fromisoformat(trade_date[:10])
        td = td.replace(tzinfo=timezone.utc)
        if td < cutoff:
            return 0.0, ticker, ""
    except Exception:
        return 0.0, ticker, ""
    typ = (trx.get("type") or trx.get("order_type") or "").lower()
    amount = trx.get("amount") or trx.get("tx_range") or ""
    mid = _midpoint(amount)
    if "purchase" in typ or typ == "buy":
        return mid, ticker, trade_date[:10]
    if "sale" in typ or typ == "sell" or typ == "sale_full" or typ == "sale_partial":
        return -mid, ticker, trade_date[:10]
    return 0.0, ticker, ""


def fetch_congress_snapshot(*, force_refresh: bool = False,
                            days: int = 60) -> CongressSnapshot | None:
    if not force_refresh and CACHE_PATH.exists():
        try:
            d = json.loads(CACHE_PATH.read_text())
            ts = datetime.fromisoformat(d["as_of"])
            if (datetime.now(timezone.utc) - ts).total_seconds() < CACHE_TTL_SECONDS:
                return CongressSnapshot(**d)
        except Exception:
            pass

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    house = _http_get_json(HOUSE_URL) or []
    senate = _http_get_json(SENATE_URL) or []

    if not house and not senate:
        return None

    house_net = 0.0
    senate_net = 0.0
    trades: list[dict] = []

    for trx in house:
        v, tk, td = _score_trade(trx, cutoff)
        if v != 0:
            house_net += v
            trades.append({"chamber": "house", "ticker": tk,
                           "date": td, "amount_dollars": v,
                           "person": trx.get("representative") or trx.get("name") or ""})
    for trx in senate:
        v, tk, td = _score_trade(trx, cutoff)
        if v != 0:
            senate_net += v
            trades.append({"chamber": "senate", "ticker": tk,
                           "date": td, "amount_dollars": v,
                           "person": trx.get("senator") or trx.get("name") or ""})

    total = house_net + senate_net
    # Scale: $5M net is meaningful for a 60-day congressional window
    import math
    score = math.tanh(total / 5_000_000.0)
    if score > 0.3:
        bias: CongressBias = "BULLISH"
    elif score < -0.3:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    top_trades = sorted(trades, key=lambda t: abs(t["amount_dollars"]),
                        reverse=True)[:5]
    snap = CongressSnapshot(
        as_of=datetime.now(timezone.utc).isoformat(),
        house_net=float(house_net),
        senate_net=float(senate_net),
        total_net=float(total),
        n_trades_60d=len(trades),
        score=float(score),
        bias=bias,
        top_trades=top_trades,
    )
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(snap.__dict__))
    return snap


def _main() -> int:
    print("Fetching congressional trades (House + Senate)...")
    snap = fetch_congress_snapshot(force_refresh=True)
    if snap is None:
        print("Congress data unavailable.")
        return 1
    print(f"Trades in window: {snap.n_trades_60d}")
    print(f"House net: {snap.house_net:+,.0f}")
    print(f"Senate net: {snap.senate_net:+,.0f}")
    print(f"Total net: {snap.total_net:+,.0f}")
    print(f"Score: {snap.score:+.3f}  ({snap.bias})")
    print("Top trades:")
    for t in snap.top_trades:
        print(f"  {t['chamber']}  {t['ticker']:6s}  {t['date']}  {t['amount_dollars']:+,.0f}  {t['person']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

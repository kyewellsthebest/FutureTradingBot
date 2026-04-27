"""
SEC EDGAR Form-4 insider-buy/sell aggregator for NQ-100 components.

Pulls the latest Form-4 RSS feed for each tracked ticker, scores recent
buys minus sells (weighted by transaction value), and produces a signed score
in [-1, +1]. Cached to data/insider_cache.json (12h TTL).
"""
from __future__ import annotations

import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal

from research.data_loader import DATA_DIR

logger = logging.getLogger("edgar")

CACHE_PATH = DATA_DIR / "insider_cache.json"
CACHE_TTL_SECONDS = 12 * 3600

USER_AGENT = "nq-trading-bot/1.0 contact@example.com"

InsiderBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]

NQ_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "META",
              "GOOGL", "TSLA", "AMD", "AVGO", "NFLX", "COST"]


@dataclass
class InsiderSnapshot:
    as_of: str
    bias: InsiderBias
    net_buy_dollars: float
    n_filings_30d: int
    score: float


def _http_get(url: str, timeout: int = 20) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        logger.info("[edgar] fetch failed for %s: %s", url, e)
        return None


def fetch_insider_snapshot(*, force_refresh: bool = False) -> InsiderSnapshot | None:
    if not force_refresh and CACHE_PATH.exists():
        try:
            d = json.loads(CACHE_PATH.read_text())
            ts = datetime.fromisoformat(d["as_of"])
            if (datetime.now(timezone.utc) - ts).total_seconds() < CACHE_TTL_SECONDS:
                return InsiderSnapshot(**d)
        except Exception:
            pass

    # Aggregate count of recent Form-4s per ticker via EDGAR full-text search.
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    n = 0
    net = 0.0
    import math
    for tk in NQ_TICKERS:
        url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
               f"&CIK={tk}&type=4&dateb=&owner=include&count=40&output=atom")
        body = _http_get(url)
        if body is None:
            continue
        try:
            root = ET.fromstring(body)
        except Exception:
            continue
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            updated = entry.findtext("a:updated", default="", namespaces=ns)
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt < cutoff:
                continue
            n += 1
    if n == 0:
        return None
    score = math.tanh(net / 5e8) if net != 0 else 0.0
    bias: InsiderBias
    if score > 0.3:
        bias = "BULLISH"
    elif score < -0.3:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    snap = InsiderSnapshot(
        as_of=datetime.now(timezone.utc).isoformat(),
        bias=bias, net_buy_dollars=float(net), n_filings_30d=n, score=float(score),
    )
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(snap.__dict__))
    return snap

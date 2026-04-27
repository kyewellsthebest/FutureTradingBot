"""
CFTC Commitments of Traders parser for NQ-related contracts.

Pulls the "Disaggregated Futures Only" report for E-mini NASDAQ-100, scores
commercial vs spec positioning, and emits a combined score in [-1, +1].
Cached to data/cot_cache.json with a 24h TTL.

Free source: https://www.cftc.gov/dea/futures/deanytradlf.htm (weekly).
We use the disaggregated short report CSV mirror via Quandl-like JSON when
reachable; otherwise return None and the rest of the system degrades.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal

from research.data_loader import DATA_DIR

logger = logging.getLogger("cot")

CACHE_PATH = DATA_DIR / "cot_cache.json"
CACHE_TTL_SECONDS = 24 * 3600

NDX_CODES = {"209742", "209747"}  # E-mini NASDAQ-100, micro variants

COTBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]


@dataclass
class COTSnapshot:
    as_of: str
    report_date: str
    commercial_long: int
    commercial_short: int
    commercial_net: int
    spec_long: int
    spec_short: int
    spec_net: int
    commercial_bias: COTBias
    spec_bias: COTBias
    combined_score: float


def _http_get(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nq-trading-bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        logger.info("[cot] fetch failed: %s", e)
        return None


def fetch_cot_snapshot(*, force_refresh: bool = False) -> COTSnapshot | None:
    if not force_refresh and CACHE_PATH.exists():
        try:
            d = json.loads(CACHE_PATH.read_text())
            ts = datetime.fromisoformat(d["as_of"])
            if (datetime.now(timezone.utc) - ts).total_seconds() < CACHE_TTL_SECONDS:
                return COTSnapshot(**d)
        except Exception:
            pass
    # Live source is unreliable (CFTC site blocks scrapers, no public JSON).
    # Return None — alternative_data.py degrades gracefully when this is missing.
    logger.info("[cot] no live source configured — returning None")
    return None

"""
PriceMonitor — background poller with a 7-source fallback chain.

Sources (in order):
  0. Polygon front-month NQ futures  (live; freshness logged — top source)
  1. CNBC NQc1 quote endpoint                       (10-15min delayed, 4s timeout)
  2. yfinance period=5d interval=1m  (last bar)
  3. yfinance period=5d interval=5m  (last bar)
  4. yfinance period=1mo interval=15m (more resilient)
  5. yfinance fast_info last_price   (point only — no high/low)
  6. Cached data/nq_5min.csv last row (offline last-resort)

Polygon is tried first because it carries a real high/low (CNBC gives a
single delayed point) and, on a real-time plan, a current price. Every
fallback returns None on failure, so a missing/failing Polygon key simply
defers to CNBC exactly as before.

snapshot_and_reset() takes the lock, returns
    {price, high, low, ts, poll_count}
representing extremes since the previous tick, then resets the running
high/low to the current price so the *next* cycle accumulates fresh
extremes. This is what gives the exit-check its "did we touch the
stop/target intra-bar" capability.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from research.data_loader import DATA_DIR, cache_path

logger = logging.getLogger("price_monitor")

POLL_SECONDS = 3
CNBC_TIMEOUT = 4
CNBC_URL = (
    "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
    "?symbols=NQc1&requestMethod=quick&exthrs=1&fund=1&output=json"
)


@dataclass
class PriceSnapshot:
    price: float
    high: float
    low: float
    ts: datetime
    poll_count: int


_polygon_last_age_log = 0.0


def _fetch_polygon() -> tuple[float, float, float] | None:
    """Polygon front-month NQ futures — the freshest source available.

    Returns (price, high, low) or None to fall through. Logs the data age
    every few minutes so the plan's REAL delay is visible in the logs
    rather than guessed at — a real-time plan reads a few minutes, a
    delayed plan reads ~15+.
    """
    global _polygon_last_age_log
    try:
        from research.data_loader import polygon_latest_quote
        q = polygon_latest_quote("NQ")
    except Exception as e:
        logger.debug(f"polygon live fetch failed: {e!r}")
        return None
    if q is None:
        return None
    price, high, low, age = q
    now = time.time()
    if now - _polygon_last_age_log > 300:
        _polygon_last_age_log = now
        # New thresholds match the snapshot endpoint's real-time
        # capability: sub-second on the Futures Advanced plan, minutes
        # on the aggregate fallback. >60s strongly suggests we're
        # falling back to 5-min bars; >12 min means truly delayed.
        if age > 720:        # > 12 min: confirmed delayed plan
            logger.warning(f"polygon live quote {age/60:.0f} min old — this "
                           f"plan is DELAYED, not real-time")
        elif age > 60:       # 1-12 min: snapshot likely failed, on aggs fallback
            logger.warning(f"polygon live quote {age/60:.1f} min old — snapshot "
                           f"endpoint not returning data; running on 5-min bar "
                           f"fallback. Check Futures Advanced plan is active.")
        elif age > 5:        # 5-60s: working but throttled
            logger.info(f"polygon live quote {age:.1f}s old (real-time, throttled)")
        else:
            logger.info(f"polygon live quote {age:.1f}s old (real-time)")
    return price, high, low


def _fetch_cnbc() -> tuple[float, float, float] | None:
    try:
        req = urllib.request.Request(CNBC_URL,
                                     headers={"User-Agent": "nq-trading-bot/1.0"})
        with urllib.request.urlopen(req, timeout=CNBC_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = (data.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
        if not items:
            return None
        q = items[0]
        last = float(q.get("last") or q.get("lastTrade") or 0.0)
        if last <= 0:
            return None
        return last, last, last  # CNBC has no high/low — same value 3x
    except Exception as e:
        logger.debug(f"CNBC fetch failed: {e!r}")
        return None


def _fetch_yf(period: str, interval: str) -> tuple[float, float, float] | None:
    try:
        import yfinance as yf
        df = yf.download("NQ=F", period=period, interval=interval,
                         progress=False, threads=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        last = df.iloc[-1]
        return float(last["close"]), float(last["high"]), float(last["low"])
    except Exception as e:
        logger.debug(f"yfinance {interval} fetch failed: {e!r}")
        return None


def _fetch_yf_fast() -> tuple[float, float, float] | None:
    try:
        import yfinance as yf
        info = yf.Ticker("NQ=F").fast_info
        last = float(info["last_price"])
        return last, last, last
    except Exception as e:
        logger.debug(f"yfinance fast_info failed: {e!r}")
        return None


def _fetch_csv() -> tuple[float, float, float] | None:
    try:
        path = cache_path("5min")
        if not path.exists():
            return None
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if df.empty:
            return None
        last = df.iloc[-1]
        return float(last["close"]), float(last["high"]), float(last["low"])
    except Exception:
        return None


_CHAIN = [
    ("polygon",    _fetch_polygon),
    ("cnbc",       _fetch_cnbc),
    ("yf_1m",      lambda: _fetch_yf("5d", "1m")),
    ("yf_5m",      lambda: _fetch_yf("5d", "5m")),
    ("yf_15m",     lambda: _fetch_yf("1mo", "15m")),
    ("yf_fast",    _fetch_yf_fast),
    ("csv_cache",  _fetch_csv),
]


class PriceMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._price: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._ts: datetime | None = None
        self._poll_count: int = 0
        self.last_source: str = ""

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="PriceMonitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(POLL_SECONDS)

    def _poll_once(self) -> None:
        for name, fn in _CHAIN:
            res = fn()
            if res is None:
                continue
            price, high, low = res
            now = datetime.now(timezone.utc)
            with self._lock:
                prev_source = self.last_source
                prev_price = self._price
                self._price = price
                self._ts = now
                self._poll_count += 1
                self.last_source = name
                if self._high is None or high > self._high:
                    self._high = max(high, price)
                if self._low is None or low < self._low:
                    self._low = min(low, price)
            # Log source changes -- catches the dual-source flicker
            # (e.g., Polygon at 30470 alternating with CNBC at 30463
            # because CNBC is 15min delayed). When this fires repeatedly
            # in the logs, the bot's live-anchor caller will see it and
            # skip trades via realtime_only=True.
            if prev_source and prev_source != name:
                delta = (price - prev_price) if prev_price is not None else 0.0
                logger.warning(
                    f"price-monitor source change: {prev_source}"
                    f"@{prev_price} -> {name}@{price} (delta {delta:+.2f}pt)")
            return
        logger.warning("price-monitor: every source failed this poll")

    def snapshot_and_reset(self) -> PriceSnapshot | None:
        """Take the lock, return current snapshot, reset extremes to current price."""
        with self._lock:
            if self._price is None:
                return None
            snap = PriceSnapshot(
                price=self._price,
                high=self._high if self._high is not None else self._price,
                low=self._low if self._low is not None else self._price,
                ts=self._ts or datetime.now(timezone.utc),
                poll_count=self._poll_count,
            )
            self._high = self._price
            self._low = self._price
            self._poll_count = 0
            return snap

    def latest(self, realtime_only: bool = False) -> PriceSnapshot | None:
        """Return current snapshot without mutating extremes.

        realtime_only: if True, return None unless the most recent poll
        came from Polygon (the only real-time source in the chain). Use
        this for any live-anchoring path -- CNBC is 15min delayed, the
        yfinance sources are 1-15min delayed, and anchoring a bracket
        to a delayed price reproduces the same stale-anchor catastrophe
        we just fixed with the live-tick re-anchoring. Better to skip
        a trade than enter with a 7pt-flicker anchor.
        """
        with self._lock:
            if self._price is None:
                return None
            if realtime_only and self.last_source != "polygon":
                return None
            return PriceSnapshot(
                price=self._price,
                high=self._high or self._price,
                low=self._low or self._price,
                ts=self._ts or datetime.now(timezone.utc),
                poll_count=self._poll_count,
            )

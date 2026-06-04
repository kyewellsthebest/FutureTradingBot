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
import os
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
        # Track MNQ (the micro contract user actually trades) not NQ
        # (the big contract). They follow the same Nasdaq-100 index but
        # trade in separate orderbooks and can diverge 2-15pt during
        # thin liquidity overnight -- when the bot was on NQ and the
        # broker filled on MNQ, every bracket was anchored to the wrong
        # contract. Override with POLYGON_CONTRACT env var if needed.
        product = os.environ.get("POLYGON_CONTRACT", "MNQ")
        q = polygon_latest_quote(product, max_age_s=1.0)
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
]
# Polygon-only by design. Previous chain included CNBC (15min delayed),
# yfinance (1-15min delayed), and a CSV cache (days/weeks old). Those
# fallbacks caused the dashboard NQ price to flicker between two values
# whenever Polygon missed a poll -- the bot would briefly anchor on a
# delayed source, then snap back to real-time. Triggered runaway P&L
# because brackets attached to stale prices.
#
# If Polygon is down, _poll_once returns nothing and latest()/snapshot
# return None. The bot's bracket forwarder already refuses to trade on
# None price, so we cleanly skip trades during outages instead of using
# wrong data.


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
        # WebSocket subscriber for tick-level updates. When connected,
        # every actual NQ trade pushes a price update with ~sub-second
        # latency. REST polling continues as a heartbeat / fallback so
        # if the WS dies we still get updates every POLL_SECONDS.
        self._ws_client = None
        self._ws_started: bool = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        # Spin up the WS subscriber first. If it fails to start (no
        # POLYGON_API key, websocket-client not installed, etc) it
        # returns False and we keep REST polling as the sole source.
        self._start_ws()
        self._thread = threading.Thread(target=self._loop,
                                         name="PriceMonitor", daemon=True)
        self._thread.start()

    def _start_ws(self) -> None:
        """Spawn the Polygon WS subscriber on the front-month ticker.
        Returns silently if WS isn't available -- bot keeps running on
        REST poll as before."""
        try:
            from bot.polygon_ws import PolygonWSClient
            from research.data_loader import polygon_front_month
            # Subscribe to MNQ (the contract user trades), not NQ.
            product = os.environ.get("POLYGON_CONTRACT", "MNQ")
            tk = polygon_front_month(product)
            self._ws_client = PolygonWSClient(
                ticker=tk, on_tick=self._on_ws_tick)
            self._ws_started = self._ws_client.start()
        except Exception as e:
            logger.warning(f"polygon WS init failed: {e!r} -- "
                           f"falling back to REST-only polling")
            self._ws_client = None
            self._ws_started = False

    def _on_ws_tick(self, price: float, ts_utc: datetime) -> None:
        """Called by PolygonWSClient on every trade event. Updates the
        in-memory price atomically under the existing lock so
        snapshot()/latest() readers see consistent values."""
        with self._lock:
            prev_source = self.last_source
            self._price = price
            self._ts = ts_utc
            self._poll_count += 1
            self.last_source = "polygon_ws"
            # Accumulate intra-snapshot extremes from tick stream (same
            # contract as the REST path -- snapshot_and_reset() consumes
            # and resets them).
            if self._high is None or price > self._high:
                self._high = price
            if self._low is None or price < self._low:
                self._low = price
        # Log source change once when WS first kicks in or if we fell
        # back to REST and now WS came back.
        if prev_source and prev_source != "polygon_ws":
            logger.info(f"price source promoted to polygon_ws "
                        f"(was {prev_source})")

    def stop(self) -> None:
        self._stop.set()
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(POLL_SECONDS)

    def _poll_once(self) -> None:
        # If the WS subscriber is ticking, skip the REST poll -- the
        # WS is sub-second fresh and the REST aggregate would just
        # stomp on it with a 30-60s old close. Threshold: 10s since
        # last WS tick. If WS goes longer than 10s without a tick the
        # contract is dead/illiquid OR the WS is broken; either way
        # REST takes over until WS recovers.
        if (self._ws_client is not None
                and self._ws_client._last_tick_ts is not None
                and time.time() - self._ws_client._last_tick_ts < 10.0):
            return
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

    def latest(self) -> PriceSnapshot | None:
        """Return current snapshot without mutating extremes. Since the
        source chain is Polygon-only, any non-None return is real-time."""
        with self._lock:
            if self._price is None:
                return None
            return PriceSnapshot(
                price=self._price,
                high=self._high or self._price,
                low=self._low or self._price,
                ts=self._ts or datetime.now(timezone.utc),
                poll_count=self._poll_count,
            )

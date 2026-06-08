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

    REFUSES to return data more than POLYGON_MAX_PRICE_AGE_S seconds old
    (default 120s = 2 min). Without this guard the polygon_latest_quote
    fallback path returns whatever the last aggregate bar's close was,
    even if that bar is 9 hours old -- producing a frozen price display
    that looks live but isn't. Falling through to None lets _CHAIN try
    the next source.
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
    # Reject stale prices. The reseller plan has been observed serving
    # quotes >9h old without any error. Returning those would lie to
    # the dashboard and the strategy.
    max_age = float(os.environ.get("POLYGON_MAX_PRICE_AGE_S", "120"))
    if age > max_age:
        if time.time() - _polygon_last_age_log > 60:
            _polygon_last_age_log = time.time()
            logger.warning(f"polygon price rejected: age {age/60:.1f}min "
                           f"> threshold {max_age/60:.1f}min. Falling "
                           f"through to next source.")
        return None
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
    ("yf_fast",    _fetch_yf_fast),
]
# Polygon is the primary source. Pre-weekend the chain was Polygon-
# only by design (to prevent dashboard flicker between real-time vs
# delayed sources). That worked while Polygon delivered. As of this
# weekend Polygon's reseller stopped serving fresh data for futures
# aggregates, leaving _CHAIN with nothing usable and the dashboard
# stuck on whatever value was cached when WS last delivered a tick.
#
# yfinance fast_info is added as a SECOND-CHANCE source -- it only
# runs when _fetch_polygon returns None (which now happens on stale
# data thanks to POLYGON_MAX_PRICE_AGE_S). yfinance NQ=F is 15min
# delayed but a 15min-old price that ticks is infinitely more useful
# than a 9h-old price that's frozen.
#
# Bracket forwarder still refuses to trade on stale data (10pt
# divergence kill-switch), so the worst case from yfinance fallback
# is the dashboard shows a 15min-delayed value -- the bot's broker
# calls are still gated by the WS tick (when present) or skipped
# entirely.


class _TickBarAggregator:
    """Builds rolling 1-min OHLC bars from WebSocket tick stream.

    Used as a live replacement for Polygon's REST /futures/v1/aggs
    endpoint when the latter is returning stale data despite WS being
    alive (observed on the user's plan tier: WS pushes ticks fine but
    REST aggs stops updating shortly after each session reopen).

    Thread-safe: on_tick is called from PolygonWSClient's recv thread,
    get_bars from the bot's main loop. Internal lock protects the
    current-bar state plus the closed-bar deque.

    Bar boundary: floor(ts, 1 minute). The first tick of a new minute
    closes the previous minute's bar (emitted to the deque) and starts
    a fresh one.
    """

    def __init__(self, max_bars: int = 2000) -> None:
        self._lock = threading.Lock()
        # Current in-progress bar
        self._cur_start: Optional[datetime] = None
        self._cur_o: float | None = None
        self._cur_h: float | None = None
        self._cur_l: float | None = None
        self._cur_c: float | None = None
        self._cur_v: int = 0
        # Rolling closed bars (oldest first)
        self._closed: list[tuple[datetime, float, float, float, float, int]] = []
        self._max_bars = max_bars
        self.closed_count: int = 0

    @staticmethod
    def _floor_minute(ts: datetime) -> datetime:
        return ts.replace(second=0, microsecond=0)

    def on_tick(self, price: float, ts: datetime) -> None:
        bucket = self._floor_minute(ts)
        with self._lock:
            if self._cur_start is None:
                # First tick ever -- start a fresh bar
                self._cur_start = bucket
                self._cur_o = self._cur_h = self._cur_l = self._cur_c = price
                self._cur_v = 1
                return
            if bucket == self._cur_start:
                # Same minute -- update H/L/C
                if price > self._cur_h:  # type: ignore[operator]
                    self._cur_h = price
                if price < self._cur_l:  # type: ignore[operator]
                    self._cur_l = price
                self._cur_c = price
                self._cur_v += 1
                return
            # New minute -- close the prior bar and start fresh
            self._closed.append((
                self._cur_start, self._cur_o, self._cur_h,  # type: ignore[arg-type]
                self._cur_l, self._cur_c, self._cur_v,
            ))
            self.closed_count += 1
            if len(self._closed) > self._max_bars:
                self._closed = self._closed[-self._max_bars:]
            self._cur_start = bucket
            self._cur_o = self._cur_h = self._cur_l = self._cur_c = price
            self._cur_v = 1

    def on_bar(self, o: float, h: float, l: float, c: float,
               v: int, ts: datetime) -> None:
        """Direct insertion of a closed 1-min bar from a WS AM event.
        Idempotent: if a bar with the same ts already exists, replace
        it (Polygon occasionally re-emits the latest closed bar). If
        the bar belongs to the current in-progress minute being built
        by on_tick, finalize it (drop the in-progress state) and use
        the AM data as authoritative -- AM aggregates Polygon's whole
        trade tape which is more accurate than our tick aggregator
        seeing only what the WS pushes."""
        bucket = self._floor_minute(ts)
        with self._lock:
            # If this minute matches the current in-progress bar, drop
            # it -- AM is authoritative.
            if self._cur_start == bucket:
                self._cur_start = None
                self._cur_o = self._cur_h = self._cur_l = self._cur_c = None
                self._cur_v = 0
            # Replace any existing bar at this ts (idempotent).
            self._closed = [row for row in self._closed if row[0] != bucket]
            self._closed.append((bucket, o, h, l, c, v))
            self._closed.sort(key=lambda r: r[0])
            self.closed_count += 1
            if len(self._closed) > self._max_bars:
                self._closed = self._closed[-self._max_bars:]

    def get_bars(self, include_current: bool = False) -> "pd.DataFrame":
        """Return all closed bars as a DataFrame indexed by UTC ts.
        Columns: open, high, low, close, volume.
        include_current=True appends the in-progress bar (for live
        last-bar fallback only -- do not pass to strategies that
        require closed bars)."""
        with self._lock:
            rows = list(self._closed)
            if include_current and self._cur_start is not None:
                rows.append((
                    self._cur_start, self._cur_o, self._cur_h,
                    self._cur_l, self._cur_c, self._cur_v,
                ))
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(
            rows, columns=["ts", "open", "high", "low", "close", "volume"]
        ).set_index("ts").sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        return df


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
        # Tick->bar aggregator. Builds 1-min OHLC bars from incoming WS
        # ticks so the strategy has a live bar source when Polygon's
        # REST aggs endpoint is returning stale data. Exposed for the
        # bot to consume in place of REST bars when WS has enough
        # history.
        self.tick_bars = _TickBarAggregator(max_bars=2000)

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
                ticker=tk,
                on_tick=self._on_ws_tick,
                on_bar=self._on_ws_bar)
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
        # Feed tick->bar aggregator outside the lock to avoid holding
        # both locks at once (aggregator has its own).
        try:
            self.tick_bars.on_tick(price, ts_utc)
        except Exception as e:
            logger.debug(f"tick_bars.on_tick failed: {e!r}")

    def _on_ws_bar(self, o: float, h: float, l: float, c: float,
                    v: int, ts_utc: datetime) -> None:
        """Called by PolygonWSClient on every AM (minute-aggregate)
        event. Inserts the closed bar directly into the aggregator so
        the strategy has authoritative OHLC even when the plan doesn't
        deliver T (trade) events. Also updates the in-memory price/ts
        with the bar close so latest()/api_price report the most
        recent minute's close."""
        with self._lock:
            self._price = c
            self._ts = ts_utc
            self.last_source = "polygon_ws_am"
        try:
            self.tick_bars.on_bar(o, h, l, c, v, ts_utc)
        except Exception as e:
            logger.debug(f"tick_bars.on_bar failed: {e!r}")
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

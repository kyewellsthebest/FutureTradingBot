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
    """Polygon front-month MNQ snapshot via the new clean client
    (bot.polygon_data). Returns (price, high, low) or None to fall
    through to next source in _CHAIN.

    The new client REJECTS stale prices internally (>300s old) and
    returns None instead. So this function never gets a frozen
    9-hour-old value -- if we get something back, it's fresh.

    Returns price for both high/low since the snapshot is a single
    tick, not a bar. PriceMonitor.snapshot_and_reset() accumulates
    H/L from the tick stream during the poll interval anyway.
    """
    try:
        from bot.polygon_data import get_snapshot_price
        q = get_snapshot_price()
    except Exception as e:
        logger.debug(f"polygon_data snapshot failed: {e!r}")
        return None
    if q is None:
        return None
    price, age = q
    if not (PRICE_MIN <= price <= PRICE_MAX):
        logger.warning(f"polygon snapshot returned implausible price "
                       f"{price} (expected {PRICE_MIN}-{PRICE_MAX}) -- "
                       f"rejecting. Likely wrong field extracted from v3 "
                       f"snapshot response.")
        return None
    if age > 5:
        logger.info(f"polygon snapshot {age:.1f}s old (real-time)")
    return price, price, price


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
    except Exception as e:
        logger.debug(f"yfinance fast_info failed: {e!r}")
        return None
    if not (PRICE_MIN <= last <= PRICE_MAX):
        logger.warning(f"yfinance NQ=F returned implausible price "
                       f"{last} (expected {PRICE_MIN}-{PRICE_MAX}) -- "
                       f"rejecting. yfinance backend occasionally "
                       f"swaps NQ=F for an unrelated symbol.")
        return None
    return last, last, last


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
# Polygon only. Pre-weekend this was Polygon-only and worked. After
# weekend Polygon's reseller broke, and I added yfinance as a fall-
# back -- but yfinance NQ=F sometimes returns prices for unrelated
# symbols (observed: NQ=F returning 2899.72 and 4375.53, neither
# even close to a real MNQ price). That polluted the cache and
# displayed garbage. Reverted to Polygon-only.
#
# If Polygon is unavailable: _CHAIN returns nothing, _price stays
# None, dashboard shows "--". That's honest. Nothing gets traded.

# Sanity range for a valid MNQ/NQ price. Defense-in-depth guard --
# polygon_data already checks but a future source might not. Anything
# outside this band gets rejected before it touches cached state.
PRICE_MIN = float(os.environ.get("PRICE_SANITY_MIN", "15000"))
PRICE_MAX = float(os.environ.get("PRICE_SANITY_MAX", "60000"))
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
        # Tradovate market-data subscriber -- when configured, replaces
        # Polygon as the primary live tick source. Same on_ws_tick
        # callback so downstream (cached price, tick_bars) is identical.
        self._tradovate_md = None
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
        # Spin up the Tradovate market data WS FIRST. When this delivers
        # ticks they go through _on_ws_tick (same code path as Polygon),
        # which populates tick_bars and the cached price. Polygon stays
        # as a fallback so if Tradovate hiccups the bot still has data.
        self._start_tradovate_md()
        self._start_ws()
        self._thread = threading.Thread(target=self._loop,
                                         name="PriceMonitor", daemon=True)
        self._thread.start()

    def _start_tradovate_md(self) -> None:
        """Spawn the Tradovate market data subscriber. Returns silently
        if Tradovate credentials aren't set -- Polygon stays the source."""
        try:
            from bot.tradovate_client import TradovateSession
            from bot.tradovate_md import TradovateMarketData
            sess = TradovateSession()
            if not sess.is_configured:
                logger.info("tradovate_md: credentials not set, skipping")
                self._tradovate_md = None
                return
            # Resolve the symbol Tradovate expects. The MNQ June 2026
            # contract is "MNQM6" on CME short format.
            from research.data_loader import polygon_front_month
            product = os.environ.get("POLYGON_CONTRACT", "MNQ")
            symbol = os.environ.get("TRADOVATE_SYMBOL",
                                     polygon_front_month(product))
            self._tradovate_md = TradovateMarketData(
                session=sess, symbol=symbol, on_tick=self._on_ws_tick)
            started = self._tradovate_md.start()
            if started:
                logger.info(f"tradovate_md started for {symbol}")
            else:
                logger.warning("tradovate_md failed to start -- falling "
                               "back to Polygon")
        except Exception as e:
            logger.warning(f"tradovate_md init failed: {e!r} -- falling back "
                           f"to Polygon")
            self._tradovate_md = None

    def _start_ws(self) -> None:
        """Spawn the Polygon WS subscriber on the front-month ticker.
        Returns silently if WS isn't available -- bot keeps running on
        REST poll as before.

        Skipped when Tradovate is configured -- the user wants live
        price tracked through Tradovate only, not Polygon. Set env
        POLYGON_ALWAYS=1 to force Polygon WS to start anyway (e.g.
        for redundancy comparison)."""
        if (self._tradovate_md is not None
                and os.environ.get("POLYGON_ALWAYS", "0") != "1"):
            logger.info("polygon WS skipped (Tradovate is primary source)")
            self._ws_client = None
            self._ws_started = False
            return
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
            logger.warning(f"polygon WS init failed: {e!r}")
            self._ws_client = None
            self._ws_started = False

    def _on_ws_tick(self, price: float, ts_utc: datetime) -> None:
        """Called by PolygonWSClient on every trade event. Updates the
        in-memory price atomically under the existing lock so
        snapshot()/latest() readers see consistent values."""
        if not (PRICE_MIN <= price <= PRICE_MAX):
            # Drop bogus ticks rather than corrupting the cached state.
            # If the WS is genuinely subscribed to the wrong contract
            # this will be noisy and visible in the logs.
            if not hasattr(self, "_last_ws_oor_log_t") or \
                    time.time() - getattr(self, "_last_ws_oor_log_t", 0) > 30:
                self._last_ws_oor_log_t = time.time()
                logger.warning(f"WS tick rejected: {price} out of range "
                               f"[{PRICE_MIN},{PRICE_MAX}]")
            return
        with self._lock:
            prev_source = self.last_source
            self._price = price
            self._ts = ts_utc
            self._poll_count += 1
            # Tag the source based on which subscriber is alive. Both
            # Polygon and Tradovate route through _on_ws_tick; we look
            # at recent tick timestamps to figure out which one fired.
            if (self._tradovate_md is not None
                    and self._tradovate_md.tick_count > 0):
                self.last_source = "tradovate_md"
            else:
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
        if not (PRICE_MIN <= c <= PRICE_MAX):
            if not hasattr(self, "_last_ws_bar_oor_log") or \
                    time.time() - getattr(self, "_last_ws_bar_oor_log", 0) > 30:
                self._last_ws_bar_oor_log = time.time()
                logger.warning(f"WS AM-bar rejected: close={c} out of "
                               f"range [{PRICE_MIN},{PRICE_MAX}]")
            return
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
        if self._tradovate_md is not None:
            try:
                self._tradovate_md.stop()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(POLL_SECONDS)

    def _poll_once(self) -> None:
        # Skip the REST poll entirely when Tradovate WS is the
        # primary source -- the user explicitly wants Polygon
        # disabled. The Tradovate WS delivers sub-second ticks and
        # we don't want stale REST data overwriting them.
        if (self._tradovate_md is not None
                and os.environ.get("POLYGON_ALWAYS", "0") != "1"):
            return
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
            # Double-check the sanity range here too, in case a future
            # source skips its own check.
            if not (PRICE_MIN <= price <= PRICE_MAX):
                logger.warning(f"_poll_once {name} returned out-of-range "
                               f"price {price}; skipping")
                continue
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
            # Log every poll that produced a price + which source won.
            # Critical for diagnosing "what's feeding this nonsense
            # value" issues. Throttled to once per 60s to keep log
            # volume sane.
            if (not hasattr(self, "_last_poll_log_t")
                    or time.time() - getattr(self, "_last_poll_log_t", 0) > 60):
                self._last_poll_log_t = time.time()
                logger.info(f"price poll: {name}={price} (poll {self._poll_count})")
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
            if not (PRICE_MIN <= self._price <= PRICE_MAX):
                logger.warning(f"snapshot_and_reset(): clearing out-of-"
                               f"range cached price {self._price}")
                self._price = None
                self._high = None
                self._low = None
                self._ts = None
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
        """Return current snapshot without mutating extremes.

        Validates the cached price against PRICE_MIN/PRICE_MAX AND
        the timestamp age. If price is out-of-range OR older than
        STALE_AFTER_S, returns None and clears the cache so future
        callers can't see the bad value either.

        Without the age check, a value cached just before the source
        stopped delivering would persist indefinitely (the 28989-all-
        day bug). Combined with the sanity range, this guarantees
        latest() returns either a fresh in-range price or None.
        """
        STALE_AFTER_S = float(os.environ.get("PRICE_STALE_AFTER_S", "60"))
        with self._lock:
            if self._price is None:
                return None
            # Age check
            if self._ts is not None:
                age = (datetime.now(timezone.utc) - self._ts).total_seconds()
                if age > STALE_AFTER_S:
                    logger.warning(f"latest(): clearing stale cached "
                                   f"price {self._price} (age {age:.0f}s)")
                    self._price = None
                    self._high = None
                    self._low = None
                    self._ts = None
                    return None
            if not (PRICE_MIN <= self._price <= PRICE_MAX):
                logger.warning(f"latest(): clearing out-of-range cached "
                               f"price {self._price} "
                               f"[{PRICE_MIN},{PRICE_MAX}]")
                self._price = None
                self._high = None
                self._low = None
                self._ts = None
                return None
            return PriceSnapshot(
                price=self._price,
                high=self._high or self._price,
                low=self._low or self._price,
                ts=self._ts or datetime.now(timezone.utc),
                poll_count=self._poll_count,
            )

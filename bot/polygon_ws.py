"""
Polygon Futures WebSocket subscriber -- tick-level price feed.

Replaces REST polling for the LIVE price in PriceMonitor. Every actual
trade on the front-month NQ contract pushes a message through this WS;
PriceMonitor's _price gets updated within ~1ms of the print instead of
~3s+ of REST poll lag.

Architecture:
  - One background thread per subscriber: connects, authenticates,
    subscribes to T.{front-month-ticker} (trades), pumps messages
  - On each trade event, invokes the supplied on_tick callback with
    (price, ts_utc)
  - Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, capped 30s)
  - Stop signal cleanly shuts down the connection
  - No external state held here; PriceMonitor owns the price state

If websocket-client isn't installed or POLYGON_API isn't set, start()
logs and returns -- PriceMonitor's existing REST poll then handles
everything as it did before. Zero blast radius: WS failure can never
hurt the bot, only prevent it from getting tick-level updates.

Polygon docs: https://polygon.io/docs/futures/quickstart
  Endpoint:  wss://socket.polygon.io/futures
  Auth:      {"action":"auth","params":"<API_KEY>"}
  Subscribe: {"action":"subscribe","params":"T.NQM6"}  (Trades)
  Tick msg:  [{"ev":"T","sym":"NQM6","p":30505.25,"s":1,"t":<ns>}]
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger("polygon_ws")

POLYGON_WS_URL = "wss://socket.polygon.io/futures"
BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 30.0


class PolygonWSClient:
    """Single-symbol futures trade subscriber.

    on_tick(price, ts_utc): called on every trade event. Must be
    thread-safe and fast -- don't do I/O in the callback or you'll
    back up the message queue."""

    def __init__(self, ticker: str,
                 on_tick: Callable[[float, datetime], None],
                 on_bar: Optional[Callable[[float, float, float, float,
                                             int, datetime], None]] = None,
                 api_key: Optional[str] = None) -> None:
        self.ticker = ticker
        self.on_tick = on_tick
        # on_bar(open, high, low, close, volume, bar_start_utc) -- fired
        # for every AM (minute-aggregate) event. Lets PriceMonitor
        # populate its bar history directly from the WS feed when the
        # plan delivers aggregates but not raw trades.
        self.on_bar = on_bar
        self.api_key = api_key or os.environ.get("POLYGON_API")
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._last_tick_ts: Optional[float] = None
        self._subscribed_at: Optional[float] = None
        # Counter of trade messages received since start -- exposed for
        # the dashboard's "WS alive?" indicator and for log rate-limit
        # logging.
        self.tick_count: int = 0
        self.connected: bool = False
        self.last_error: Optional[str] = None

    def health(self) -> dict:
        """Snapshot for the dashboard. Tells the user whether WS is
        actually delivering ticks (vs just "connected but silent")."""
        now = time.time()
        return {
            "ticker": self.ticker,
            "connected": bool(self.connected),
            "tick_count": int(self.tick_count),
            "last_tick_age_s": (round(now - self._last_tick_ts, 1)
                                 if self._last_tick_ts else None),
            "subscribed_age_s": (round(now - self._subscribed_at, 1)
                                  if self._subscribed_at else None),
            "last_error": self.last_error,
        }

    def start(self) -> bool:
        """Spawn the WS thread. Returns True if started, False if
        prerequisites are missing (websocket-client not installed or
        API key not set). Safe to call multiple times."""
        if self._thread is not None and self._thread.is_alive():
            return True
        if not self.api_key:
            logger.warning("polygon_ws: POLYGON_API not set -- WS disabled, "
                           "REST polling will handle price")
            return False
        try:
            import websocket  # noqa: F401  -- presence check
        except ImportError:
            logger.warning("polygon_ws: websocket-client not installed -- "
                           "WS disabled, REST polling will handle price")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop,
                                         name=f"PolygonWS-{self.ticker}",
                                         daemon=True)
        self._thread.start()
        logger.info(f"polygon_ws: started for {self.ticker}")
        return True

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=3)

    def _run_loop(self) -> None:
        """Outer reconnect loop. Each iteration tries to connect, auth,
        subscribe, and pump messages until disconnect or stop signal.
        Backoff between failed attempts grows exponentially up to 30s."""
        backoff = BACKOFF_INITIAL_S
        while not self._stop.is_set():
            try:
                self._connect_and_pump()
                # Clean disconnect -- reset backoff for next attempt
                backoff = BACKOFF_INITIAL_S
            except Exception as e:
                self.last_error = repr(e)
                logger.warning(f"polygon_ws: connection failed: {e!r} -- "
                               f"retrying in {backoff:.1f}s")
            finally:
                self.connected = False
            # Sleep with stop-aware wait so shutdown is responsive
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, BACKOFF_MAX_S)

    def _connect_and_pump(self) -> None:
        import websocket
        self._ws = websocket.create_connection(POLYGON_WS_URL, timeout=10)
        try:
            # Polygon sends a welcome message first; consume it (don't
            # block forever -- 5s is plenty for the handshake)
            self._ws.settimeout(5)
            try:
                hello = self._ws.recv()
                logger.debug(f"polygon_ws hello: {hello[:200]}")
            except Exception:
                pass

            # Authenticate
            self._ws.send(json.dumps({"action": "auth",
                                       "params": self.api_key}))
            auth_resp = self._ws.recv()
            if "auth_success" not in auth_resp and "success" not in auth_resp:
                raise RuntimeError(f"polygon_ws auth failed: {auth_resp[:300]}")
            logger.info(f"polygon_ws: authenticated, subscribing to "
                        f"T.{self.ticker},AM.{self.ticker},A.{self.ticker}")

            # Subscribe to ALL price channels on the front-month:
            #   T.*   = trades (preferred, sub-second)
            #   AM.*  = aggregate-minute (1-min OHLC, fires at minute close)
            #   A.*   = aggregate-second (1-sec OHLC, fires every second
            #           with a trade)
            #
            # Plan tier on massive.com / Polygon reseller frequently
            # excludes raw trade events for futures but DOES include
            # aggregate streams. Subscribing to all three means we get
            # whatever the plan delivers, and the bot can build its
            # 1-min bars from either AM (direct) or T (aggregated).
            #
            # Polygon accepts comma-separated subscriptions in a single
            # action.
            self._ws.send(json.dumps({
                "action": "subscribe",
                "params": (f"T.{self.ticker},"
                           f"AM.{self.ticker},"
                           f"A.{self.ticker}"),
            }))
            sub_resp = self._ws.recv()
            # Log subscription response at INFO so plan-entitlement
            # failures are visible. Polygon returns a status event like
            # {"ev":"status","status":"success","message":"subscribed..."}
            # on success, or {"status":"error","message":"unauthorized"}
            # when the plan doesn't include futures WS.
            logger.info(f"polygon_ws sub response: {sub_resp[:500]}")
            try:
                _parsed = json.loads(sub_resp)
                if isinstance(_parsed, list) and _parsed:
                    first = _parsed[0]
                    if isinstance(first, dict):
                        status = str(first.get("status", "")).lower()
                        msg = str(first.get("message", ""))
                        if status in ("error", "auth_failed", "max_connections"):
                            self.last_error = f"sub_failed: {msg}"
                            raise RuntimeError(
                                f"polygon_ws subscription rejected by "
                                f"Polygon: {msg!r}. Plan likely doesn't "
                                f"include real-time futures WebSocket.")
            except RuntimeError:
                raise
            except Exception as e:
                logger.debug(f"polygon_ws sub parse failed: {e!r}")

            # Pump trade messages. Use a generous read timeout (15s) so
            # quiet periods on the contract don't tear down the
            # connection -- if Polygon doesn't send a tick or heartbeat
            # in 15s the contract is probably illiquid or the connection
            # is broken; the outer loop will reconnect either way.
            self._ws.settimeout(15)
            self.connected = True
            self.last_error = None
            self._subscribed_at = time.time()
            while not self._stop.is_set():
                try:
                    raw = self._ws.recv()
                except Exception as e:
                    logger.warning(f"polygon_ws recv: {e!r} -- reconnecting")
                    break
                if not raw:
                    continue
                self._process_message(raw)
        finally:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    @staticmethod
    def _polygon_ts_to_utc(ts_raw) -> datetime:
        """Polygon timestamps come as ms or ns since epoch. Auto-detect
        magnitude and return a tz-aware UTC datetime."""
        if ts_raw is None:
            return datetime.now(timezone.utc)
        try:
            ts_n = float(ts_raw)
            if ts_n > 1e15:
                ts_s = ts_n / 1e9
            elif ts_n > 1e12:
                ts_s = ts_n / 1e3
            else:
                ts_s = ts_n
            return datetime.fromtimestamp(ts_s, tz=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _process_message(self, raw: str) -> None:
        """Polygon sends arrays of events. We subscribe to T (trades),
        AM (minute aggregates), and A (second aggregates) so we get
        whichever the plan delivers."""
        try:
            events = json.loads(raw)
        except Exception:
            logger.debug(f"polygon_ws non-json msg: {raw[:200]}")
            return
        if not isinstance(events, list):
            events = [events]
        for e in events:
            if not isinstance(e, dict):
                continue
            ev = e.get("ev")
            # First 10 of EVERY event type at INFO level so the user
            # can see in deploy logs which channel their plan is
            # delivering. Beyond that, throttle to every 500.
            self.tick_count += 1
            if self.tick_count <= 10 or self.tick_count % 500 == 0:
                logger.info(f"polygon_ws event #{self.tick_count} "
                            f"ev={ev!r} keys={list(e.keys())[:8]}")

            if ev == "T":
                # Single trade
                price = e.get("p") or e.get("price")
                ts_raw = e.get("t") or e.get("timestamp")
                if price is None:
                    continue
                ts_utc = self._polygon_ts_to_utc(ts_raw)
                self._last_tick_ts = time.time()
                try:
                    self.on_tick(float(price), ts_utc)
                except Exception as cb_err:
                    logger.warning(f"polygon_ws on_tick (T) failed: {cb_err!r}")

            elif ev == "A":
                # Second-aggregate. Treat as a tick using the close price.
                close = e.get("c") or e.get("close")
                ts_raw = e.get("s") or e.get("start_timestamp") or e.get("t")
                if close is None:
                    continue
                ts_utc = self._polygon_ts_to_utc(ts_raw)
                self._last_tick_ts = time.time()
                try:
                    self.on_tick(float(close), ts_utc)
                except Exception as cb_err:
                    logger.warning(f"polygon_ws on_tick (A) failed: {cb_err!r}")

            elif ev == "AM":
                # Minute-aggregate: full OHLC of the just-closed minute.
                # Feed both on_tick (for live price) and on_bar (for
                # direct insertion into the strategy's bar history).
                o = e.get("o") or e.get("open")
                h = e.get("h") or e.get("high")
                l = e.get("l") or e.get("low")
                c = e.get("c") or e.get("close")
                v = e.get("v") or e.get("volume") or 0
                ts_raw = e.get("s") or e.get("start_timestamp") or e.get("t")
                if c is None:
                    continue
                ts_utc = self._polygon_ts_to_utc(ts_raw)
                self._last_tick_ts = time.time()
                try:
                    self.on_tick(float(c), ts_utc)
                except Exception as cb_err:
                    logger.warning(f"polygon_ws on_tick (AM) failed: {cb_err!r}")
                if self.on_bar is not None and None not in (o, h, l, c):
                    try:
                        self.on_bar(float(o), float(h), float(l),
                                     float(c), int(v), ts_utc)
                    except Exception as cb_err:
                        logger.warning(f"polygon_ws on_bar failed: {cb_err!r}")

            elif ev == "status":
                logger.info(f"polygon_ws status: {e}")

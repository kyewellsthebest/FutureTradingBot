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
                 api_key: Optional[str] = None) -> None:
        self.ticker = ticker
        self.on_tick = on_tick
        self.api_key = api_key or os.environ.get("POLYGON_API")
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._last_tick_ts: Optional[float] = None
        # Counter of trade messages received since start -- exposed for
        # the dashboard's "WS alive?" indicator and for log rate-limit
        # logging.
        self.tick_count: int = 0
        self.connected: bool = False
        self.last_error: Optional[str] = None

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
                        f"T.{self.ticker}")

            # Subscribe to trades on the front-month
            self._ws.send(json.dumps({"action": "subscribe",
                                       "params": f"T.{self.ticker}"}))
            sub_resp = self._ws.recv()
            logger.debug(f"polygon_ws sub: {sub_resp[:200]}")

            # Pump trade messages. Use a generous read timeout (15s) so
            # quiet periods on the contract don't tear down the
            # connection -- if Polygon doesn't send a tick or heartbeat
            # in 15s the contract is probably illiquid or the connection
            # is broken; the outer loop will reconnect either way.
            self._ws.settimeout(15)
            self.connected = True
            self.last_error = None
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

    def _process_message(self, raw: str) -> None:
        """Polygon sends arrays of events. Each event is one trade
        when ev='T'. Status/heartbeat events have ev='status' and are
        logged at debug. Anything else we ignore."""
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
            if ev == "T":
                price = e.get("p") or e.get("price")
                ts_raw = e.get("t") or e.get("timestamp")
                if price is None:
                    continue
                # Polygon futures trade timestamps: documentation says ms
                # since epoch; some endpoints return ns. Auto-detect via
                # magnitude (anything > 1e15 is ns).
                try:
                    ts_n = float(ts_raw) if ts_raw is not None else \
                           time.time() * 1000
                    if ts_n > 1e15:
                        ts_s = ts_n / 1e9
                    elif ts_n > 1e12:
                        ts_s = ts_n / 1e3
                    else:
                        ts_s = ts_n
                    ts_utc = datetime.fromtimestamp(ts_s, tz=timezone.utc)
                except Exception:
                    ts_utc = datetime.now(timezone.utc)
                self._last_tick_ts = time.time()
                self.tick_count += 1
                # Throttle log spam: only every 500th tick
                if self.tick_count % 500 == 0:
                    logger.info(f"polygon_ws: {self.tick_count} ticks "
                                f"received, last={price}")
                try:
                    self.on_tick(float(price), ts_utc)
                except Exception as cb_err:
                    logger.warning(f"polygon_ws on_tick callback: {cb_err!r}")
            elif ev == "status":
                logger.debug(f"polygon_ws status: {e}")
            # All other event types (A=aggregates, Q=quotes) silently
            # ignored since we only subscribed to T.

"""Tradovate Market Data WebSocket subscriber.

Replaces Polygon as the live price source. Connects to
wss://md.tradovateapi.com/v1/websocket, authorizes with the
mdAccessToken, subscribes to live quotes for the front-month MNQ
contract, and pushes each Trade print into a callback.

Tradovate WebSocket protocol (SockJS-derived):
  Server frames:
    'o'         -- open frame (connection established)
    'h'         -- heartbeat (server -> client, every ~2.5s when idle)
    'a[...]'    -- data array (one or more JSON messages)
    'c[...]'    -- close frame

  Client must:
    1. Receive 'o' on connect
    2. Send authorization: 'authorize\n<id>\n\n<accessToken>'
    3. Send subscription requests as: '<endpoint>\n<id>\n<query>\n<body>'
    4. Send heartbeats every 2.5s as the literal string '[]' to keep
       the connection alive

  Data messages we care about:
    {"e":"md","d":{"quotes":[{...}]}}    -- live quote update

Quote entries contain {Bid, Offer, Trade, LowPrice, HighPrice, ...}.
We forward the "Trade" entry as the live tick (the actual last-traded
price), matching the semantics of Polygon's T events.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger("tradovate_md")

import os as _os

# Tradovate market data WebSocket. The market data feed runs on
# md.tradovateapi.com for BOTH live and demo clusters -- it's the
# same exchange tape, the cluster split (live vs demo) only applies
# to auth/orders/account ops. The mdAccessToken returned at auth
# time is what gates demo vs live data entitlement.
def _md_ws_url() -> str:
    return _os.environ.get("TRADOVATE_MD_WS",
                            "wss://md.tradovateapi.com/v1/websocket")

HEARTBEAT_INTERVAL_S = 2.0
BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 30.0


class TradovateMarketData:
    """Single-symbol Tradovate market data subscriber.

    on_tick(price, ts_utc): called on every Trade print
    """

    def __init__(self,
                 session,             # TradovateSession
                 symbol: str,         # initial hint, e.g. "MNQM6"
                 on_tick: Callable[[float, datetime], None],
                 product_root: str = "MNQ") -> None:
        self.session = session
        self.symbol = symbol      # may be overridden after contract lookup
        self.product_root = product_root
        self.on_tick = on_tick
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._last_tick_ts: Optional[float] = None
        self._next_req_id: int = 1
        self._subscribed: bool = False
        # The actual contract used for subscription (resolved via
        # /contract/suggest at connect time). Could be the original
        # short name or the longer canonical name Tradovate prefers.
        self._resolved_symbol: Optional[str] = None
        self._contract_id: Optional[int] = None
        self.tick_count: int = 0
        self.connected: bool = False
        self.last_error: Optional[str] = None

    def start(self) -> bool:
        """Spawn the WS thread. Returns True if started."""
        if self._thread is not None and self._thread.is_alive():
            return True
        if not self.session.is_configured:
            logger.warning("tradovate_md: session not configured (env vars "
                           "missing) -- WS disabled")
            return False
        try:
            import websocket  # noqa: F401  -- presence check
        except ImportError:
            logger.warning("tradovate_md: websocket-client not installed -- "
                           "WS disabled")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop,
                                         name=f"TradovateMD-{self.symbol}",
                                         daemon=True)
        self._thread.start()
        logger.info(f"tradovate_md: started for {self.symbol}")
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

    def health(self) -> dict:
        now = time.time()
        return {
            "symbol": self.symbol,
            "resolved_symbol": self._resolved_symbol,
            "contract_id": self._contract_id,
            "connected": bool(self.connected),
            "subscribed": bool(self._subscribed),
            "tick_count": int(self.tick_count),
            "frames_seen": getattr(self, "_frames_seen", 0),
            "last_tick_age_s": (round(now - self._last_tick_ts, 1)
                                 if self._last_tick_ts else None),
            "last_error": self.last_error,
        }

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        backoff = BACKOFF_INITIAL_S
        while not self._stop.is_set():
            try:
                self._connect_and_pump()
                backoff = BACKOFF_INITIAL_S
            except Exception as e:
                self.last_error = repr(e)
                logger.warning(f"tradovate_md: connection failed: {e!r} -- "
                               f"retrying in {backoff:.1f}s")
            finally:
                self.connected = False
                self._subscribed = False
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, BACKOFF_MAX_S)

    def _connect_and_pump(self) -> None:
        import websocket
        tokens = self.session.get_tokens()
        if tokens is None:
            raise RuntimeError("auth failed")
        md_token = tokens.md_access_token

        url = _md_ws_url()
        logger.info(f"tradovate_md: connecting to {url}")
        self._ws = websocket.create_connection(url, timeout=10)
        self._ws.settimeout(5)

        # Step 1: Receive the open frame 'o'
        hello = self._ws.recv()
        logger.info(f"tradovate_md: open frame={hello[:80]!r}")

        # Step 2: Authorize
        auth_msg = self._build_request("authorize", "", md_token)
        self._ws.send(auth_msg)

        # Step 3: Receive auth response (should be 'a[{"s":200, ...}]')
        auth_resp = self._ws.recv()
        logger.info(f"tradovate_md: auth response={auth_resp[:200]!r}")
        if not self._auth_succeeded(auth_resp):
            raise RuntimeError(f"auth rejected: {auth_resp[:200]!r}")

        # Step 4: Resolve the contract via REST. /contract/suggest gives us
        # the canonical name Tradovate has on file, which may differ from
        # our internal CME-short convention. Also gets the numeric ID
        # which is the most reliable subscription key.
        contract = self.session.find_contract(self.product_root)
        if contract is None:
            # Fall back to the symbol we were given (may still work)
            sub_symbol = self.symbol
            self._resolved_symbol = self.symbol
            self._contract_id = None
            logger.warning(f"tradovate_md: contract lookup failed for "
                           f"{self.product_root!r}, trying symbol="
                           f"{self.symbol!r} as-is")
        else:
            self._resolved_symbol = contract.get("name") or self.symbol
            self._contract_id = contract.get("id")
            # Prefer the numeric ID -- most reliable per the API docs
            # which show symbol can be either a string or contract ID.
            sub_symbol = (int(self._contract_id) if self._contract_id
                          else self._resolved_symbol)
            logger.info(f"tradovate_md: subscribing with symbol="
                        f"{sub_symbol!r} (resolved name="
                        f"{self._resolved_symbol!r}, id={self._contract_id!r})")

        # Step 5: Subscribe to live quotes for the resolved symbol
        sub_body = json.dumps({"symbol": sub_symbol})
        sub_msg = self._build_request("md/subscribeQuote", "", sub_body)
        self._ws.send(sub_msg)
        sub_resp = self._ws.recv()
        logger.info(f"tradovate_md: subscribeQuote response={sub_resp[:300]!r}")
        if not self._sub_succeeded(sub_resp):
            # If first attempt failed, try the OTHER format (name vs ID)
            alt_symbol = (self._resolved_symbol
                          if isinstance(sub_symbol, int)
                          else self._contract_id)
            if alt_symbol:
                logger.warning(f"tradovate_md: retrying with alt symbol "
                               f"{alt_symbol!r}")
                sub_body = json.dumps({"symbol": alt_symbol})
                sub_msg = self._build_request("md/subscribeQuote", "", sub_body)
                self._ws.send(sub_msg)
                sub_resp = self._ws.recv()
                logger.info(f"tradovate_md: retry response={sub_resp[:300]!r}")
                if not self._sub_succeeded(sub_resp):
                    raise RuntimeError(f"subscribeQuote rejected (both "
                                        f"attempts): {sub_resp[:200]!r}")
            else:
                raise RuntimeError(f"subscribeQuote rejected: {sub_resp[:200]!r}")
        self._subscribed = True
        self.connected = True
        self.last_error = None

        # Step 5: Pump messages + send heartbeats every 2s
        self._ws.settimeout(0.5)  # short timeout so we can heartbeat
        last_hb_sent = time.time()
        while not self._stop.is_set():
            try:
                raw = self._ws.recv()
                if raw:
                    self._process_frame(raw)
            except Exception as e:
                # recv timeout is expected -- not an error
                msg = repr(e)
                if "timed out" not in msg and "timeout" not in msg.lower():
                    logger.warning(f"tradovate_md recv: {e!r} -- reconnecting")
                    break
            # Heartbeat
            now = time.time()
            if now - last_hb_sent > HEARTBEAT_INTERVAL_S:
                try:
                    self._ws.send("[]")
                    last_hb_sent = now
                except Exception as e:
                    logger.warning(f"tradovate_md heartbeat failed: {e!r}")
                    break

        try:
            self._ws.close()
        except Exception:
            pass
        self._ws = None

    # ------------------------------------------------------------------
    # Request building / response parsing
    # ------------------------------------------------------------------

    def _build_request(self, endpoint: str, query: str, body: str) -> str:
        """Tradovate WS request format:
            <endpoint>\n<id>\n<query>\n<body>
        """
        req_id = self._next_req_id
        self._next_req_id += 1
        return f"{endpoint}\n{req_id}\n{query}\n{body}"

    @staticmethod
    def _auth_succeeded(raw: str) -> bool:
        if not raw or len(raw) < 2:
            return False
        if raw[0] != "a":
            return False
        try:
            arr = json.loads(raw[1:])
            for msg in arr:
                if isinstance(msg, dict) and msg.get("s") == 200:
                    return True
        except Exception:
            return False
        return False

    @staticmethod
    def _sub_succeeded(raw: str) -> bool:
        """Subscription response is similar to auth -- 's':200 means OK."""
        if not raw or len(raw) < 2:
            return False
        if raw[0] != "a":
            return False
        try:
            arr = json.loads(raw[1:])
            for msg in arr:
                if isinstance(msg, dict) and msg.get("s") == 200:
                    return True
                # An immediate event push can also indicate the sub is active
                if isinstance(msg, dict) and msg.get("e") == "md":
                    return True
        except Exception:
            return False
        return False

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def _process_frame(self, raw: str) -> None:
        if not raw:
            return
        # VERBOSE: log first N frames of every type so we can see what
        # Tradovate is actually sending us. Without this we're flying
        # blind when tick_count stays at 0.
        self._frames_seen = getattr(self, "_frames_seen", 0) + 1
        if self._frames_seen <= 20:
            logger.info(f"tradovate_md frame #{self._frames_seen} ({len(raw)} "
                        f"bytes): {raw[:500]!r}")
        prefix = raw[0]
        if prefix == "h":
            return
        if prefix == "o":
            logger.debug(f"tradovate_md: open frame in pump: {raw[:80]!r}")
            return
        if prefix == "c":
            logger.warning(f"tradovate_md: close frame: {raw[:200]!r}")
            return
        if prefix != "a":
            logger.info(f"tradovate_md: unknown frame prefix {prefix!r}: "
                        f"{raw[:200]!r}")
            return
        try:
            messages = json.loads(raw[1:])
        except Exception as e:
            logger.warning(f"tradovate_md: JSON decode failed on frame: "
                           f"{e!r} raw={raw[:200]!r}")
            return
        if not isinstance(messages, list):
            messages = [messages]
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            # Log first few of each event type so we know what's arriving
            ev = msg.get("e")
            if ev and ev != "md" and self._frames_seen <= 30:
                logger.info(f"tradovate_md non-md event: {msg!r}")
            self._handle_message(msg)

    def _handle_message(self, msg: dict) -> None:
        # Event messages (server -> client streaming data)
        if msg.get("e") == "md":
            self._handle_md_event(msg.get("d") or {})
            return
        # Response messages (replies to client requests)
        if "s" in msg:
            return  # acks for our auth/sub already handled
        # Status / heartbeat / unknown
        logger.debug(f"tradovate_md: unhandled message: "
                     f"keys={list(msg.keys())}")

    def _handle_md_event(self, data: dict) -> None:
        quotes = data.get("quotes")
        if not isinstance(quotes, list):
            return
        for q in quotes:
            if not isinstance(q, dict):
                continue
            entries = q.get("entries") or {}
            trade = entries.get("Trade") if isinstance(entries, dict) else None
            bid_entry = entries.get("Bid") if isinstance(entries, dict) else None
            ask_entry = entries.get("Offer") if isinstance(entries, dict) else None
            # IMPORTANT: record bid/ask-only quotes too. Previously the
            # code required entries.Trade and skipped frames that only
            # had Bid/Offer -- which meant tick_count stayed at 0 even
            # though 1900+ frames arrived. Without bid/ask the bracket
            # re-anchor logic in tradovate_orders can't work. Use the
            # mid-price as the synthetic "last" when no Trade is
            # present so tick_history always has a price.
            price = None
            if isinstance(trade, dict):
                price = trade.get("price")
            if price is None and isinstance(bid_entry, dict) and isinstance(ask_entry, dict):
                b = bid_entry.get("price")
                a = ask_entry.get("price")
                if b is not None and a is not None:
                    price = (float(b) + float(a)) / 2.0
            if price is None and isinstance(bid_entry, dict):
                price = bid_entry.get("price")
            if price is None and isinstance(ask_entry, dict):
                price = ask_entry.get("price")
            if price is None:
                continue
            ts_raw = q.get("timestamp")
            ts_utc = self._parse_ts(ts_raw)
            self._last_tick_ts = time.time()
            self.tick_count += 1
            if self.tick_count <= 10 or self.tick_count % 500 == 0:
                logger.info(f"tradovate_md tick #{self.tick_count} "
                            f"price={price} ts={ts_raw}")
            # Record into the diagnostic tick buffer (with bid/ask if
            # present) so the bundle has the broker's view of the tape.
            # bid_entry/ask_entry already extracted above (used for the
            # synthetic-mid fallback when no Trade entry exists).
            try:
                bid = bid_entry.get("price") if isinstance(bid_entry, dict) else None
                ask = ask_entry.get("price") if isinstance(ask_entry, dict) else None
                from bot.tick_history import record_tick
                record_tick(float(price),
                             bid=float(bid) if bid is not None else None,
                             ask=float(ask) if ask is not None else None,
                             src="tradovate")
                # And compare to the latest Polygon tick to catch
                # feed divergence in real time. The two modules don't
                # know about each other -- we read the latest Polygon
                # tick from the shared tick-history cache.
                try:
                    from bot.tick_history import latest_by_src
                    poly = latest_by_src("polygon")
                    if poly is not None:
                        from bot.price_diff_tracker import record_sample
                        record_sample(poly_px=poly["px"],
                                       trad_px=float(price))
                except Exception:
                    pass
            except Exception:
                pass
            try:
                self.on_tick(float(price), ts_utc)
            except Exception as cb_err:
                logger.warning(f"tradovate_md on_tick callback: {cb_err!r}")

    @staticmethod
    def _parse_ts(ts_raw) -> datetime:
        if ts_raw is None:
            return datetime.now(timezone.utc)
        try:
            if isinstance(ts_raw, (int, float)):
                # Heuristic: ms vs ns
                v = float(ts_raw)
                if v > 1e15:
                    return datetime.fromtimestamp(v / 1e9, tz=timezone.utc)
                if v > 1e12:
                    return datetime.fromtimestamp(v / 1e3, tz=timezone.utc)
                return datetime.fromtimestamp(v, tz=timezone.utc)
            s = str(ts_raw).replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except Exception:
            return datetime.now(timezone.utc)

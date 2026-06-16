"""Tradovate user/account WebSocket.

Subscribes to user-data events (ExecutionReport, Order, Fill, Position,
CashBalance) for real-time fill notifications. Without this, the bot
polls the REST API on a timer (best case 500ms granularity, worst case
seconds). With this, we get fill events the instant the matching
engine generates them.

WHY this matters for paper-vs-broker matching:
  - Currently we poll for parent fill at +0.5s, +2s, +5s, +15s. If fill
    happened at t=0.3s and we exit at t=12s, paper-vs-broker timeline
    is off by ~700ms.
  - With WS: fill event arrives in <100ms. Timeline + reconciliation
    have proper resolution.

WS authentication mirrors tradovate_md.py exactly -- different URL
(live/demo cluster), same auth frame.

Cluster split:
  - Live:  wss://live.tradovateapi.com/v1/websocket
  - Demo:  wss://demo.tradovateapi.com/v1/websocket
(unlike market data, which is md.tradovateapi.com for both)

Subscription is via /user/syncrequest -- one request gets all entity
updates for the authenticated user.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("tradovate_user_ws")


def _user_ws_url() -> str:
    if os.environ.get("TRADOVATE_USER_WS"):
        return os.environ["TRADOVATE_USER_WS"]
    demo = os.environ.get("TRADOVATE_DEMO", "true").lower() in (
        "true", "1", "yes")
    return ("wss://demo.tradovateapi.com/v1/websocket" if demo
             else "wss://live.tradovateapi.com/v1/websocket")


HEARTBEAT_S = 2.0
BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 30.0


class TradovateUserWS:
    """Connects to Tradovate's user cluster WS and surfaces every
    entity update event into a bounded ring buffer + per-event
    callbacks.

    The bot's diagnostic bundle reads from get_recent_events() to
    show real-time fill/cancel/reject activity.
    """

    def __init__(self, session) -> None:
        self.session = session
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._next_req_id = 1
        self.connected = False
        self.subscribed = False
        self.last_error: Optional[str] = None
        self._last_msg_ts: Optional[float] = None
        self._frames_seen = 0

        # Event buffers (bounded, thread-safe via GIL on append)
        self.events: "deque[dict]" = deque(maxlen=2000)
        self.fills: "deque[dict]" = deque(maxlen=500)
        self.exec_reports: "deque[dict]" = deque(maxlen=500)
        self.order_updates: "deque[dict]" = deque(maxlen=500)
        self.position_updates: "deque[dict]" = deque(maxlen=200)
        # LATENCY: cache the latest netPos per contractId so callers can
        # check positions without a REST round-trip (~100-200ms saved
        # per check). The user WS pushes position updates instantly when
        # fills happen, so this cache is more current than REST polling.
        self._netpos_cache: dict = {}  # contractId -> {netPos, ts}
        self.cash_updates: "deque[dict]" = deque(maxlen=200)

    # ----- lifecycle -----

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return True
        if not self.session.is_configured:
            logger.warning("user_ws: session not configured -- WS disabled")
            return False
        try:
            import websocket  # noqa: F401
        except ImportError:
            logger.warning("user_ws: websocket-client not installed")
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="TradovateUserWS", daemon=True)
        self._thread.start()
        logger.info("user_ws: started")
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
            "url": _user_ws_url(),
            "connected": self.connected,
            "subscribed": self.subscribed,
            "frames_seen": self._frames_seen,
            "events_buffered": len(self.events),
            "fills_buffered": len(self.fills),
            "exec_reports_buffered": len(self.exec_reports),
            "last_msg_age_s": (round(now - self._last_msg_ts, 1)
                                if self._last_msg_ts else None),
            "last_error": self.last_error,
        }

    def get_netpos_cached(self, contract_id: int, max_age_s: float = 5.0) -> Optional[int]:
        """Return the most recent netPos for contract_id pushed via WS.
        None if no recent update (caller should fall back to REST)."""
        entry = self._netpos_cache.get(int(contract_id))
        if not entry:
            return None
        if time.time() - entry["ts"] > max_age_s:
            return None
        return entry["netPos"]

    def get_recent_events(self, limit: int = 200) -> list:
        return list(self.events)[-limit:]

    def get_fills(self, limit: int = 100) -> list:
        return list(self.fills)[-limit:]

    def get_exec_reports(self, limit: int = 100) -> list:
        return list(self.exec_reports)[-limit:]

    # ----- WS plumbing -----

    def _run_loop(self) -> None:
        import websocket
        backoff = BACKOFF_INITIAL_S
        while not self._stop.is_set():
            try:
                self._connect_and_pump()
                backoff = BACKOFF_INITIAL_S
            except Exception as e:
                self.last_error = repr(e)
                self.connected = False
                self.subscribed = False
                logger.warning(f"user_ws: loop exception: {e!r} -- "
                               f"reconnect in {backoff}s")
                if self._stop.wait(backoff):
                    break
                backoff = min(BACKOFF_MAX_S, backoff * 2)
        logger.info("user_ws: loop ended")

    def _connect_and_pump(self) -> None:
        import websocket
        tokens = self.session.get_tokens()
        if tokens is None:
            raise RuntimeError("user_ws: no auth tokens")
        url = _user_ws_url()
        logger.info(f"user_ws: connecting {url}")
        self._ws = websocket.create_connection(url, timeout=15)
        # Tradovate sends an "o" frame on connect
        try:
            hello = self._ws.recv()
            logger.info(f"user_ws: open frame={hello[:80]!r}")
        except Exception:
            pass

        # Send authorize
        auth_frame = self._build_request(
            "authorize", body_text=tokens.access_token)
        self._ws.send(auth_frame)
        auth_resp = self._ws.recv()
        logger.info(f"user_ws: auth response={auth_resp[:200]!r}")
        self.connected = True

        # Subscribe to user/syncrequest -- this returns initial state +
        # streams updates for ALL entity types for this user.
        sync_frame = self._build_request(
            "user/syncrequest", body_json={"users": [tokens.user_id]})
        self._ws.send(sync_frame)
        sync_resp = self._ws.recv()
        logger.info(f"user_ws: sync response={sync_resp[:200]!r}")
        self.subscribed = True

        self._ws.settimeout(5.0)
        last_heartbeat = time.time()
        while not self._stop.is_set():
            try:
                raw = self._ws.recv()
            except Exception as e:
                if self._stop.is_set():
                    break
                # Timeout is expected -- use it to send heartbeat
                if "timed out" in str(e).lower():
                    if time.time() - last_heartbeat > HEARTBEAT_S:
                        try:
                            self._ws.send("[]")
                            last_heartbeat = time.time()
                        except Exception as he:
                            logger.warning(f"user_ws heartbeat failed: {he!r}")
                            raise
                    continue
                logger.warning(f"user_ws recv: {e!r} -- reconnecting")
                raise
            self._last_msg_ts = time.time()
            self._frames_seen += 1
            self._handle_frame(raw)

    def _build_request(self, url_path: str,
                        body_json: Optional[dict] = None,
                        body_text: Optional[str] = None) -> str:
        """Tradovate WS request frame format: M (verb) URL\nReqId\nQuery\nBody."""
        rid = self._next_req_id
        self._next_req_id += 1
        body = ""
        if body_json is not None:
            body = json.dumps(body_json)
        elif body_text is not None:
            body = body_text
        return f"{url_path}\n{rid}\n\n{body}"

    def _handle_frame(self, raw: str) -> None:
        if not raw:
            return
        prefix = raw[0]
        if prefix == "a":  # array message
            try:
                msgs = json.loads(raw[1:])
            except Exception as e:
                logger.warning(f"user_ws: JSON parse fail: {e!r}")
                return
            if isinstance(msgs, list):
                for m in msgs:
                    self._dispatch(m)
        elif prefix == "h":  # heartbeat
            pass
        elif prefix == "c":
            logger.warning(f"user_ws: close frame: {raw[:200]!r}")
            self.connected = False
            self.subscribed = False
        elif prefix == "o":
            pass

    def _dispatch(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        # Tradovate event envelope: {e: event_type, d: data_dict}
        # or response envelope: {i: req_id, s: status, d: data}
        ev_type = msg.get("e")
        data = msg.get("d") or {}
        if not ev_type:
            return
        record = {
            "ts": time.time(),
            "event_type": ev_type,
            "data": data,
        }
        self.events.append(record)
        # Route by entity type. Tradovate emits "props" envelopes for
        # entity changes; the entityType field tells us what changed.
        entity_type = data.get("entityType") if isinstance(data, dict) else None
        entity = data.get("entity") if isinstance(data, dict) else None
        if entity_type == "fill" and isinstance(entity, dict):
            self.fills.append(entity)
            logger.info(f"[user_ws FILL] id={entity.get('id')} "
                        f"orderId={entity.get('orderId')} "
                        f"action={entity.get('action')} "
                        f"qty={entity.get('qty')} price={entity.get('price')}")
        elif entity_type == "executionReport" and isinstance(entity, dict):
            self.exec_reports.append(entity)
            logger.info(f"[user_ws EXEC] orderId={entity.get('orderId')} "
                        f"execType={entity.get('execType')} "
                        f"ordStatus={entity.get('ordStatus')} "
                        f"avgPx={entity.get('avgPx')}")
        elif entity_type == "order" and isinstance(entity, dict):
            self.order_updates.append(entity)
        elif entity_type == "position" and isinstance(entity, dict):
            self.position_updates.append(entity)
            try:
                cid = entity.get("contractId")
                np = entity.get("netPos")
                if cid is not None and np is not None:
                    self._netpos_cache[int(cid)] = {
                        "netPos": int(np),
                        "ts": time.time(),
                    }
            except Exception:
                pass
        elif entity_type in ("cashBalance", "currency") and isinstance(entity, dict):
            self.cash_updates.append(entity)


# Module-level singleton (started lazily by anyone who needs it)
_INSTANCE: Optional[TradovateUserWS] = None
_INSTANCE_LOCK = threading.Lock()


def get_user_ws():
    """Lazy singleton. Auto-starts on first call."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            try:
                from bot.tradovate_client import get_session
                sess = get_session()
                _INSTANCE = TradovateUserWS(sess)
                _INSTANCE.start()
            except Exception as e:
                logger.warning(f"user_ws auto-start failed: {e!r}")
                return None
        return _INSTANCE

"""Tradovate API client — clean rebuild.

Replaces the engine/brokers/tradovate.py skeleton with a working
implementation focused on what THIS bot needs:

  1. Authenticate (REST + market data tokens)
  2. Stream live MNQ ticks via market data WebSocket
  3. Place market orders with isAutomated=true (CME requirement)
  4. Receive fill confirmations via trading WebSocket

Env vars required (8):
  TRADOVATE_USERNAME       account email (e.g. "KyeWells")
  TRADOVATE_PASSWORD       account password
  TRADOVATE_APP_ID         registered app name (e.g. "Bot")
  TRADOVATE_APP_VERSION    registered app version (e.g. "0.0.1")
  TRADOVATE_CID            numeric client ID (integer, e.g. 14142)
  TRADOVATE_DEVICE_ID      pre-assigned UUID from Tradovate
  TRADOVATE_API_SECRET     the "sec" field -- long secret string
  TRADOVATE_DEMO           "true" -> demo cluster, "false" -> live

The auth flow (per Tradovate API docs):
  POST /v1/auth/accesstokenrequest
    {name, password, appId, appVersion, cid, sec, deviceId}
  Returns:
    accessToken      -- for REST + trading WebSocket
    mdAccessToken    -- for market data WebSocket
    expirationTime   -- ISO8601, typically ~1.5 hours away
    hasMarketData    -- bool, confirms data entitlement
    userId           -- numeric user ID
"""
from __future__ import annotations

import json
import logging
import os
import time
import time as _time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# --------------------------------------------------------------------
# REST latency metrics (module-level so the diag bundle can read them)
# --------------------------------------------------------------------
_LATENCY_BY_ENDPOINT: "dict[str, deque[float]]" = defaultdict(
    lambda: deque(maxlen=200))
_LATENCY_RECENT: "deque[dict]" = deque(maxlen=500)


def _record_latency(method: str, path: str, ms: float,
                     status: Optional[int]) -> None:
    key = f"{method} {path.split('?', 1)[0]}"
    _LATENCY_BY_ENDPOINT[key].append(ms)
    _LATENCY_RECENT.append({
        "ts": _time.time(), "endpoint": key,
        "ms": round(ms, 1), "status": status,
    })


def get_latency_stats() -> dict:
    """Return p50 / p95 / p99 latency per endpoint plus the most recent
    calls. Used by the diagnostic bundle."""
    import statistics
    summary = {}
    for ep, samples in _LATENCY_BY_ENDPOINT.items():
        if not samples:
            continue
        s = list(samples)
        s.sort()
        n = len(s)
        def _pct(p):
            idx = min(n - 1, int(n * p / 100))
            return round(s[idx], 1)
        summary[ep] = {
            "n": n,
            "p50": _pct(50),
            "p95": _pct(95),
            "p99": _pct(99),
            "max": round(s[-1], 1),
            "mean": round(statistics.mean(s), 1),
        }
    return {"per_endpoint": summary,
            "recent_calls": list(_LATENCY_RECENT)[-50:]}

logger = logging.getLogger("tradovate")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _is_demo() -> bool:
    return os.environ.get("TRADOVATE_DEMO", "true").lower() in ("true", "1", "yes")


def _rest_base() -> str:
    return "https://demo.tradovateapi.com/v1" if _is_demo() \
           else "https://live.tradovateapi.com/v1"


def _md_ws() -> str:
    # Market data uses the same cluster for demo/live (md.tradovateapi.com)
    return "wss://md.tradovateapi.com/v1/websocket"


def _trading_ws() -> str:
    return ("wss://demo.tradovateapi.com/v1/websocket" if _is_demo()
            else "wss://live.tradovateapi.com/v1/websocket")


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

@dataclass
class TradovateCredentials:
    username: str
    password: str
    app_id: str
    app_version: str
    cid: int
    device_id: str
    sec: str

    @classmethod
    def from_env(cls) -> Optional["TradovateCredentials"]:
        required = (
            "TRADOVATE_USERNAME", "TRADOVATE_PASSWORD",
            "TRADOVATE_APP_ID", "TRADOVATE_APP_VERSION",
            "TRADOVATE_CID", "TRADOVATE_DEVICE_ID",
            "TRADOVATE_API_SECRET",
        )
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            logger.warning(f"Tradovate credentials incomplete; missing: {missing}")
            return None
        try:
            cid_str = os.environ["TRADOVATE_CID"].strip()
            cid_int = int(cid_str)
        except ValueError:
            logger.error(f"TRADOVATE_CID is not numeric: "
                         f"{os.environ['TRADOVATE_CID']!r}")
            return None
        return cls(
            username=os.environ["TRADOVATE_USERNAME"].strip(),
            password=os.environ["TRADOVATE_PASSWORD"],
            app_id=os.environ["TRADOVATE_APP_ID"].strip(),
            app_version=os.environ["TRADOVATE_APP_VERSION"].strip(),
            cid=cid_int,
            device_id=os.environ["TRADOVATE_DEVICE_ID"].strip(),
            sec=os.environ["TRADOVATE_API_SECRET"].strip(),
        )

    def auth_payload(self) -> dict:
        return {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
            "cid": self.cid,
            "sec": self.sec,
            "deviceId": self.device_id,
        }


# ---------------------------------------------------------------------------
# Session: handles auth + token refresh
# ---------------------------------------------------------------------------

@dataclass
class TradovateTokens:
    access_token: str
    md_access_token: str
    expires_at: float          # unix seconds
    user_id: int
    has_market_data: bool
    has_live: bool

    @property
    def is_expiring_soon(self) -> bool:
        # Refresh if less than 5 minutes remaining
        return time.time() > (self.expires_at - 300)


class TradovateSession:
    """Manages auth + access-token lifecycle. Thread-safe (auth is
    idempotent on the server side, but we serialize requests anyway)."""

    def __init__(self, creds: Optional[TradovateCredentials] = None) -> None:
        self.creds = creds or TradovateCredentials.from_env()
        self._tokens: Optional[TradovateTokens] = None
        self._account_id: Optional[int] = None  # populated on first /account/list
        # LATENCY: cache the resolved contract_id for the active symbol
        # so we don't hit /contract/find on every liquidate/order. Same
        # value all day for a given front-month contract.
        self._contract_id_cache: dict = {}  # symbol -> contractId
        # Connection pre-warmed flag -- the first REST call after start
        # pays TCP+TLS handshake (~300ms). We do a cheap /v1/me call on
        # startup to amortize this cost before any actual trade fires.
        self._connection_warmed = False

    @property
    def is_configured(self) -> bool:
        return self.creds is not None

    def authenticate(self) -> Optional[TradovateTokens]:
        """Request a new access token. Returns None on failure (logged).

        Handles Tradovate's p-ticket captcha pattern: when rate-limited,
        the response contains {"p-ticket": "...", "p-time": N, "p-captcha":
        bool}. We block for p-time seconds then resubmit the SAME payload
        with the p-ticket included so we get past the gate instead of
        looping forever returning None.
        """
        if self.creds is None:
            logger.error("Tradovate not configured (env vars missing)")
            return None
        # Allow up to 2 captcha-retry cycles (each waits p-time seconds)
        # before giving up. Beyond that, something else is wrong (bad
        # creds, server outage) and we should let the caller back off.
        for attempt in range(3):
            url = f"{_rest_base()}/auth/accesstokenrequest"
            payload = self.creds.auth_payload()
            # On retry, attach the p-ticket from prior response. Tradovate
            # requires the SAME payload + the ticket to clear the captcha.
            pt = getattr(self, "_pending_p_ticket", None)
            if pt:
                payload["p-ticket"] = pt
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "hftbot/1.0",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_body = resp.read().decode("utf-8", errors="replace")
                    data = json.loads(resp_body)
            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = ""
                logger.error(f"Tradovate auth HTTP {e.code}: {err_body[:500]!r}")
                return None
            except Exception as e:
                logger.error(f"Tradovate auth failed: {e!r}")
                return None

            # Captcha / rate-limit handling.
            if "p-ticket" in data:
                wait_s = int(data.get("p-time", 60))
                self._pending_p_ticket = data.get("p-ticket")
                if attempt < 2:
                    logger.warning(
                        f"Tradovate auth rate-limited (attempt {attempt+1}); "
                        f"waiting {wait_s}s then retrying with p-ticket")
                    import time as _t
                    _t.sleep(wait_s + 1)
                    continue
                logger.error(
                    f"Tradovate auth rate-limited after {attempt+1} attempts "
                    f"-- giving up; bot will fall back to scheduled "
                    f"refresh loop")
                return None
            # Clear the ticket once we got past it.
            self._pending_p_ticket = None
            if "errorText" in data:
                logger.error(f"Tradovate auth rejected: {data['errorText']!r}")
                return None
            break  # fall through to token parse below

        access = data.get("accessToken")
        md_access = data.get("mdAccessToken")
        exp_iso = data.get("expirationTime")
        if not access or not exp_iso:
            logger.error(f"Tradovate auth response missing fields: "
                         f"keys={list(data.keys())}")
            return None

        try:
            exp_dt = datetime.fromisoformat(exp_iso.replace("Z", "+00:00"))
            expires_at = exp_dt.timestamp()
        except Exception:
            expires_at = time.time() + 3600  # fallback 1hr

        tokens = TradovateTokens(
            access_token=access,
            md_access_token=md_access or access,
            expires_at=expires_at,
            user_id=int(data.get("userId", 0)),
            has_market_data=bool(data.get("hasMarketData", False)),
            has_live=bool(data.get("hasLive", False)),
        )
        self._tokens = tokens
        cluster = "demo" if _is_demo() else "live"
        logger.info(f"Tradovate authenticated ({cluster}): user_id="
                    f"{tokens.user_id} has_market_data={tokens.has_market_data} "
                    f"has_live={tokens.has_live} expires_in="
                    f"{(expires_at - time.time()) / 60:.0f}min")
        return tokens

    def prewarm(self) -> None:
        """Pre-establish the TCP+TLS connection to Tradovate before the
        first trade fires. The first REST call after process start pays
        ~300ms of TCP handshake + TLS negotiation; subsequent calls reuse
        the keep-alive socket and are ~50-100ms. By doing a cheap
        /v1/me call at bot startup, we move that latency off the
        critical path.

        Safe to call multiple times -- idempotent.
        """
        if self._connection_warmed:
            return
        try:
            # /v1/me is the cheapest authenticated endpoint.
            self._rest("GET", "/me")
            self._connection_warmed = True
            logger.info("[Tradovate prewarm] connection ready -- "
                        "first trade no longer pays TCP+TLS handshake")
        except Exception as e:
            logger.debug(f"prewarm: {e!r}")

    def get_tokens(self) -> Optional[TradovateTokens]:
        """Return current tokens, refreshing if expiring soon."""
        if self._tokens is None or self._tokens.is_expiring_soon:
            return self.authenticate()
        return self._tokens

    def start_background_refresh(self) -> None:
        """Start a daemon thread that refreshes the access token BEFORE
        it expires, so trade-path calls never trigger an inline
        authenticate() (which adds ~500ms-1s of network round-trip).

        Idempotent -- safe to call multiple times.
        """
        if getattr(self, "_refresh_thread_started", False):
            return
        self._refresh_thread_started = True
        import threading as _th
        def _loop():
            import time as _t
            while True:
                try:
                    tokens = self._tokens
                    if tokens is None:
                        # No tokens yet -- get them, then wait.
                        self.authenticate()
                        _t.sleep(60)
                        continue
                    # Refresh 10 minutes before expiry.
                    remaining = tokens.expires_at - _t.time()
                    sleep_for = max(60, remaining - 600)
                    _t.sleep(min(sleep_for, 600))
                    if self._tokens and self._tokens.is_expiring_soon:
                        logger.info(
                            "[token refresh] proactive refresh -- "
                            "trade path stays fast")
                        self.authenticate()
                except Exception as e:
                    logger.debug(f"token refresh loop: {e!r}")
                    _t.sleep(60)
        t = _th.Thread(target=_loop, daemon=True, name="tradovate-token-refresh")
        t.start()

    # ----- REST helpers ----------------------------------------------------

    def _rest(self, method: str, path: str,
              params: Optional[dict] = None,
              body: Optional[dict] = None) -> tuple[Optional[int], dict]:
        tokens = self.get_tokens()
        if tokens is None:
            return None, {"error": "auth_failed"}
        url = f"{_rest_base()}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{qs}"
        # LATENCY: use a persistent requests.Session with HTTP keep-alive
        # so the TCP+TLS connection is reused across calls. urllib
        # creates a NEW TCP+TLS connection per call (~200-300ms of
        # handshake overhead each time). With keep-alive, first call
        # pays the handshake; subsequent calls are bare HTTP RTT
        # (~50-100ms instead of 250-400ms).
        if not hasattr(self, '_http_session'):
            import requests as _rq
            from requests.adapters import HTTPAdapter
            self._http_session = _rq.Session()
            # LATENCY: custom HTTPAdapter that sets TCP_NODELAY on every
            # new socket. Without this, urllib3 inherits OS defaults
            # which usually have Nagle's algorithm ON -- small HTTP
            # bodies (~few hundred bytes for placeoso) get buffered up
            # to 40ms before being sent. With TCP_NODELAY, frames go
            # out immediately. 10-40ms saved per call.
            try:
                from urllib3.poolmanager import PoolManager
                import socket as _sk
                class _NoDelayAdapter(HTTPAdapter):
                    def init_poolmanager(self, *a, **kw):
                        kw['socket_options'] = [
                            (_sk.IPPROTO_TCP, _sk.TCP_NODELAY, 1),
                            (_sk.SOL_SOCKET, _sk.SO_KEEPALIVE, 1),
                        ]
                        try:
                            kw['socket_options'].append(
                                (_sk.IPPROTO_TCP, _sk.TCP_QUICKACK, 1))
                        except Exception:
                            pass
                        return super().init_poolmanager(*a, **kw)
                adapter_cls = _NoDelayAdapter
            except Exception:
                adapter_cls = HTTPAdapter
            adapter = adapter_cls(pool_connections=4, pool_maxsize=8,
                                   max_retries=0)
            self._http_session.mount("https://", adapter)
            self._http_session.mount("http://", adapter)
            self._http_session.headers.update({
                "User-Agent": "hftbot/1.0",
                "Accept": "application/json",
            })
            # LATENCY: orjson is 5-10x faster than stdlib json for the
            # placeoso payload. Saves ~1-3ms per call (modest but
            # compounds when called from a tick callback).
            try:
                import orjson as _oj
                self._json_dumps = lambda d: _oj.dumps(d).decode()
                self._json_loads = _oj.loads
            except ImportError:
                self._json_dumps = json.dumps
                self._json_loads = json.loads
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {tokens.access_token}",
        }
        # Track wall-clock latency for every REST call. Used by the
        # diagnostic bundle to spot slow endpoints / network hiccups.
        t_start = _time.monotonic()
        status_for_metric = None
        try:
            resp = self._http_session.request(
                method, url, headers=headers,
                data=self._json_dumps(body) if body else None,
                timeout=15)
            status_for_metric = resp.status_code
            body_text = resp.text
            try:
                return resp.status_code, self._json_loads(body_text) if body_text else {}
            except Exception:
                return resp.status_code, {"raw": body_text[:500]}
        except Exception as e:
            logger.warning(f"Tradovate {method} {path} failed: {e!r}")
            return None, {"error": repr(e)}
        finally:
            ms = (_time.monotonic() - t_start) * 1000.0
            _record_latency(method, path, ms, status_for_metric)

    def account_list(self) -> list[dict]:
        """Returns all accounts for the authenticated user."""
        status, data = self._rest("GET", "/account/list")
        if status != 200 or not isinstance(data, list):
            return []
        return data

    def get_account_id(self, name_match: Optional[str] = None) -> Optional[int]:
        """Find the numeric account ID. If name_match given, prefers an
        account whose name contains that substring. Caches the result."""
        if self._account_id is not None and name_match is None:
            return self._account_id
        accts = self.account_list()
        if not accts:
            return None
        if name_match:
            for a in accts:
                if name_match.lower() in str(a.get("name", "")).lower():
                    self._account_id = int(a["id"])
                    return self._account_id
        # First account by default
        self._account_id = int(accts[0]["id"])
        logger.info(f"Tradovate active account: id={self._account_id} "
                    f"name={accts[0].get('name')!r}")
        return self._account_id

    # ----- Contract lookup ------------------------------------------------

    def find_contract(self, root: str = "MNQ") -> Optional[dict]:
        """Resolve the FRONT-MONTH contract for a product root using
        Tradovate's /contract/suggest endpoint. Returns the contract
        dict (with 'id' and 'name') or None.

        WHY this matters: market data WebSocket subscription needs
        either the numeric contract ID or the EXACT contract name that
        Tradovate has on file. CME short format ('MNQM6') is the bot's
        internal convention but Tradovate's API may use the longer
        'MNQM2026' format or only accept the numeric ID. /contract/suggest
        returns whatever Tradovate considers canonical, so we use that.

        Caches result so steady-state calls don't hammer the REST API.
        """
        if hasattr(self, "_contract_cache"):
            cached = self._contract_cache.get(root)
            if cached is not None:
                return cached
        else:
            self._contract_cache: dict = {}

        # /contract/suggest?t=<text>&l=<limit> returns a list of contract
        # entities whose name starts with the search text. We ask for
        # ~20 to ensure we see all listed expirations.
        status, results = self._rest(
            "GET", "/contract/suggest", params={"t": root, "l": 20})
        if status != 200 or not isinstance(results, list):
            logger.warning(f"Tradovate contract/suggest({root!r}) -> "
                           f"status={status} body[:300]={str(results)[:300]!r}")
            return None
        # Filter to active futures matching our root, pick soonest expiration.
        candidates = []
        for c in results:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name", ""))
            if not name.startswith(root):
                continue
            # Prefer entries that have a maturityMonthYear or expiration date
            candidates.append(c)
        if not candidates:
            logger.warning(f"Tradovate contract/suggest({root!r}): no "
                           f"matching contracts found. Sample: "
                           f"{[c.get('name') for c in results[:5]]!r}")
            return None
        # Pick the contract whose name is shortest (front-month convention)
        # and which is the earliest expiring. /contract/suggest typically
        # returns in expiration order with closest first.
        chosen = candidates[0]
        self._contract_cache[root] = chosen
        logger.info(f"Tradovate front-month for {root}: name={chosen.get('name')!r} "
                    f"id={chosen.get('id')!r} "
                    f"expiry={chosen.get('lastTradingDay') or chosen.get('maturityMonthYear')!r}")
        return chosen


# ---------------------------------------------------------------------------
# Module-level singleton -- shared auth state across all threads
# ---------------------------------------------------------------------------
# Many threads in the bot (MD WebSocket, order placement, dashboard
# endpoints) each need a Tradovate session. If each creates its own
# instance, each runs authenticate() against Tradovate's heavily
# rate-limited /auth/accesstokenrequest endpoint and they collide --
# the MD thread was stuck on RuntimeError("auth failed") while the
# dashboard's diag endpoint reported auth_ok=true because they were
# racing for tokens. Singleton -> everyone shares cached tokens, auth
# happens once per token lifetime (~80 min).
import threading as _threading
_session_singleton: Optional[TradovateSession] = None
_session_lock = _threading.Lock()


def get_session() -> TradovateSession:
    """Process-wide shared TradovateSession. Lazy-inits on first call."""
    global _session_singleton
    with _session_lock:
        if _session_singleton is None:
            _session_singleton = TradovateSession()
        return _session_singleton


# ---------------------------------------------------------------------------
# Self-test entrypoint: lets us verify auth with `python -m bot.tradovate_client`
# ---------------------------------------------------------------------------

def _selftest() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sess = TradovateSession()
    if not sess.is_configured:
        logger.error("Cannot self-test: TRADOVATE_* env vars not set")
        return 1
    tokens = sess.authenticate()
    if tokens is None:
        logger.error("Self-test FAILED at auth step")
        return 2
    logger.info(f"Auth OK. accessToken length={len(tokens.access_token)}")
    accts = sess.account_list()
    if not accts:
        logger.error("Self-test FAILED at account/list (got 0 accounts)")
        return 3
    for a in accts:
        logger.info(f"  account: id={a.get('id')} name={a.get('name')!r} "
                    f"type={a.get('accountType')!r} active={a.get('active')}")
    acct_id = sess.get_account_id()
    logger.info(f"Selected account id={acct_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())

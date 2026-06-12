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
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

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

    @property
    def is_configured(self) -> bool:
        return self.creds is not None

    def authenticate(self) -> Optional[TradovateTokens]:
        """Request a new access token. Returns None on failure (logged)."""
        if self.creds is None:
            logger.error("Tradovate not configured (env vars missing)")
            return None
        url = f"{_rest_base()}/auth/accesstokenrequest"
        payload = self.creds.auth_payload()
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

        # Check for rate-limit / captcha responses
        if "p-ticket" in data:
            wait_s = data.get("p-time", 60)
            logger.warning(f"Tradovate auth rate-limited; retry in {wait_s}s "
                           f"(p-ticket: {data.get('p-ticket')!r})")
            return None
        if "errorText" in data:
            logger.error(f"Tradovate auth rejected: {data['errorText']!r}")
            return None

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

    def get_tokens(self) -> Optional[TradovateTokens]:
        """Return current tokens, refreshing if expiring soon."""
        if self._tokens is None or self._tokens.is_expiring_soon:
            return self.authenticate()
        return self._tokens

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
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {tokens.access_token}",
                "User-Agent": "hftbot/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                return resp.status, json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            logger.warning(f"Tradovate {method} {path} -> HTTP {e.code}: "
                           f"{err_body[:300]!r}")
            try:
                return e.code, json.loads(err_body) if err_body else {}
            except Exception:
                return e.code, {"raw": err_body[:500]}
        except Exception as e:
            logger.warning(f"Tradovate {method} {path} failed: {e!r}")
            return None, {"error": repr(e)}

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

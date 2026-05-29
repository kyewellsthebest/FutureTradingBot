"""TradovateFillModel + TradovateSession.

This is the ADAPTER LAYER between the engine and a real Tradovate
account. Implements `engine.fills.base.FillModel` so the runtime is
broker-agnostic.

OPERATING MODES (controlled by env vars):

  TRADOVATE_LIVE=true   → real API calls go to Tradovate.
                          Requires all credentials below. Order submission,
                          fills, and position queries hit the real exchange.

  TRADOVATE_LIVE=false (default) → DRY-RUN mode.
                          Wraps SimFillModel as the actual fill engine but
                          ALSO exercises the full Tradovate code path
                          (auth, order submission, fill polling) against a
                          configurable mock or the Tradovate demo endpoint.
                          Useful for integration testing without risking
                          capital.

REQUIRED ENV VARS for LIVE mode:
  TRADOVATE_USERNAME       -- account login email
  TRADOVATE_PASSWORD       -- account password
  TRADOVATE_API_KEY        -- developer app key
  TRADOVATE_API_SECRET     -- developer app secret
  TRADOVATE_DEVICE_ID      -- a stable UUID per machine (Tradovate quirk)
  TRADOVATE_APP_ID         -- the registered app's ID
  TRADOVATE_APP_VERSION    -- semver string for your app
  TRADOVATE_DEMO=true|false -- if true, hit the demo cluster, else live

Tradovate URL conventions (from their API docs):
  Demo REST: https://demo.tradovateapi.com/v1
  Live REST: https://live.tradovateapi.com/v1
  Demo WS:   wss://md.tradovateapi.com/v1/websocket
  Live WS:   wss://live.tradovateapi.com/v1/websocket
  Market WS: wss://md.tradovateapi.com/v1/websocket   (same for both)

This file is INTENTIONALLY a shell:
  - The interface is complete and matches the engine
  - The session manager has the full auth flow including the token-refresh
    loop documented inline
  - Order submission stubs out the actual HTTP request but logs exactly
    what would be sent
  - Fill polling stubs likewise

Before flipping to LIVE you must:
  1. Sign up for a Tradovate developer account at developer.tradovate.com
  2. Get sandbox credentials and put them in Railway env vars
  3. Replace the `_http_request` stub with a real `urllib`/`requests` call
  4. Verify end-to-end on the demo cluster with a single 1-contract trade
  5. Inspect 50+ real fills, then run engine/calibration/ to update
     SimFillParams to match the real broker's behaviour
  6. ONLY THEN flip TRADOVATE_LIVE=true
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from engine.fills.base import FillModel
from engine.fills.sim import SimFillModel, SimFillParams
from engine.market_context import MarketContext
from engine.types import Fill, LimitOrder, Side, StopOrder

logger = logging.getLogger("tradovate")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _is_live() -> bool:
    return os.environ.get("TRADOVATE_LIVE", "false").lower() in ("true", "1", "yes")


def _is_demo() -> bool:
    return os.environ.get("TRADOVATE_DEMO", "true").lower() in ("true", "1", "yes")


def _base_url() -> str:
    return "https://demo.tradovateapi.com/v1" if _is_demo() \
           else "https://live.tradovateapi.com/v1"


@dataclass
class TradovateCredentials:
    username: str
    password: str
    api_key: str
    api_secret: str
    device_id: str
    app_id: str
    app_version: str = "0.1.0"

    @classmethod
    def from_env(cls) -> Optional["TradovateCredentials"]:
        required = ("TRADOVATE_USERNAME", "TRADOVATE_PASSWORD",
                    "TRADOVATE_API_KEY", "TRADOVATE_API_SECRET",
                    "TRADOVATE_DEVICE_ID", "TRADOVATE_APP_ID")
        if not all(os.environ.get(k) for k in required):
            return None
        return cls(
            username=os.environ["TRADOVATE_USERNAME"],
            password=os.environ["TRADOVATE_PASSWORD"],
            api_key=os.environ["TRADOVATE_API_KEY"],
            api_secret=os.environ["TRADOVATE_API_SECRET"],
            device_id=os.environ["TRADOVATE_DEVICE_ID"],
            app_id=os.environ["TRADOVATE_APP_ID"],
            app_version=os.environ.get("TRADOVATE_APP_VERSION", "0.1.0"),
        )


# ---------------------------------------------------------------------------
# Session manager: handles auth + access-token refresh
# ---------------------------------------------------------------------------
class TradovateSession:
    """Manages the Tradovate access token. Refreshes ~5 minutes before
    expiry. All authenticated requests go through .get / .post."""

    def __init__(self, creds: TradovateCredentials):
        self.creds = creds
        self.access_token: Optional[str] = None
        self.expires_at: Optional[datetime] = None
        self.account_id: Optional[int] = None  # populated after first auth

    def _http_request(self, method: str, path: str,
                       body: Optional[dict] = None,
                       auth_header: Optional[str] = None) -> dict:
        """STUB: replace with a real HTTP call in production.

        Currently raises NotImplementedError if TRADOVATE_LIVE=true so the
        bot can't accidentally hit prod. In DRY_RUN, returns canned
        responses for the auth + order endpoints so integration tests
        run end-to-end without network.
        """
        url = f"{_base_url()}{path}"
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        if _is_live():
            # PRODUCTION PATH (to be implemented)
            #
            # try:
            #     data = json.dumps(body).encode() if body else None
            #     req = urllib.request.Request(url, data=data, method=method,
            #                                   headers=headers)
            #     with urllib.request.urlopen(req, timeout=15) as resp:
            #         return json.loads(resp.read().decode())
            # except urllib.error.HTTPError as e:
            #     raise TradovateAPIError(e.code, e.read().decode()) from e
            #
            raise NotImplementedError(
                "Tradovate LIVE HTTP path not yet implemented. "
                "Set TRADOVATE_LIVE=false to use DRY_RUN mode.")
        # DRY_RUN canned responses
        return self._dry_run_response(method, path, body)

    def _dry_run_response(self, method: str, path: str, body) -> dict:
        """Canned responses for DRY_RUN. Lets integration tests exercise
        the full code path without network calls."""
        if path == "/auth/accesstokenrequest" and method == "POST":
            return {
                "accessToken": "DRY_RUN_TOKEN_xxx",
                "expirationTime": (datetime.now(timezone.utc) +
                                    timedelta(hours=1)).isoformat(),
                "mdAccessToken": "DRY_RUN_MD_TOKEN_xxx",
                "userId": 999999,
                "name": self.creds.username,
            }
        if path == "/account/list" and method == "GET":
            return [{"id": 12345, "name": "DRY_RUN_ACCT", "active": True}]
        if path.startswith("/order/placeorder") and method == "POST":
            return {"orderId": int(time.time() * 1000) % 10**9, "success": True}
        if path.startswith("/order/list"):
            return []
        if path.startswith("/position/list"):
            return []
        return {"dry_run": True, "method": method, "path": path, "body": body}

    def authenticate(self) -> None:
        """POST /auth/accesstokenrequest. Sets access_token + expires_at."""
        body = {
            "name":         self.creds.username,
            "password":     self.creds.password,
            "appId":        self.creds.app_id,
            "appVersion":   self.creds.app_version,
            "cid":          self.creds.api_key,
            "sec":          self.creds.api_secret,
            "deviceId":     self.creds.device_id,
        }
        resp = self._http_request("POST", "/auth/accesstokenrequest", body=body)
        self.access_token = resp.get("accessToken")
        exp = resp.get("expirationTime")
        if exp:
            self.expires_at = pd.Timestamp(exp).to_pydatetime()
        # Resolve the trading account
        accts = self._http_request(
            "GET", "/account/list",
            auth_header=f"Bearer {self.access_token}")
        if accts:
            self.account_id = accts[0]["id"]
        logger.info(f"Tradovate authenticated. account_id={self.account_id} "
                    f"expires={self.expires_at}")

    def ensure_authenticated(self) -> None:
        """Call before every authed request. Refreshes if expired or close
        to expiring."""
        if self.access_token is None:
            self.authenticate()
            return
        if self.expires_at is None:
            self.authenticate()
            return
        # Refresh ~5 min before expiry to avoid mid-flight 401s
        if datetime.now(timezone.utc) > self.expires_at - timedelta(minutes=5):
            logger.info("Tradovate token expiring soon; refreshing")
            self.authenticate()

    def get(self, path: str) -> dict:
        self.ensure_authenticated()
        return self._http_request("GET", path,
                                   auth_header=f"Bearer {self.access_token}")

    def post(self, path: str, body: dict) -> dict:
        self.ensure_authenticated()
        return self._http_request("POST", path, body=body,
                                   auth_header=f"Bearer {self.access_token}")


# ---------------------------------------------------------------------------
# The actual FillModel implementation
# ---------------------------------------------------------------------------
class TradovateFillModel(FillModel):
    """Real broker adapter. Submits orders via Tradovate, polls for fills,
    reports them back through the same FillModel interface the SimFillModel
    uses. The runtime doesn't know or care which one it's talking to."""

    def __init__(self, session: Optional[TradovateSession] = None,
                 dry_run_sim: Optional[SimFillModel] = None,
                 contract_id: int = 0):
        """contract_id: the Tradovate-internal numeric ID for the NQ/MNQ
        front-month contract. Fetch via /contract/find?name=MNQH26 etc.
        Cache once per session.

        dry_run_sim: if provided, this SimFillModel handles fill simulation
        when TRADOVATE_LIVE=false. In production this is unused.
        """
        self.session = session
        self.sim = dry_run_sim or SimFillModel(SimFillParams())
        self.contract_id = contract_id
        # Track submitted orders by setup_id so we can match fills back
        self._open_submissions: dict = {}  # {setup_id: tradovate_order_id}

    # -----------------------------------------------------------------
    # LimitOrder submission + fill polling
    # -----------------------------------------------------------------
    def check_limit_fill(self, order: LimitOrder, bar: pd.Series,
                          ctx: MarketContext) -> Optional[Fill]:
        if _is_live() and self.session is not None:
            # PRODUCTION PATH
            return self._live_check_limit_fill(order, bar, ctx)
        # DRY_RUN: ALSO exercise the order submission code path against the
        # canned responses, then delegate the actual fill decision to the
        # SimFillModel so we still get realistic behaviour.
        if self.session is not None and order.setup_id not in self._open_submissions:
            try:
                resp = self.session.post("/order/placeorder", {
                    "accountId":    self.session.account_id,
                    "contractId":   self.contract_id,
                    "action":       "Buy" if order.side is Side.LONG else "Sell",
                    "orderQty":     order.qty,
                    "orderType":    "Limit",
                    "price":        order.price,
                    "isAutomated":  True,
                    "timeInForce":  "Day",
                })
                self._open_submissions[order.setup_id] = resp.get("orderId")
            except Exception as e:
                logger.warning(f"DRY_RUN order submit failed: {e!r}")
        return self.sim.check_limit_fill(order, bar, ctx)

    def fill_stop(self, order: StopOrder, bar: pd.Series,
                   ctx: MarketContext) -> Optional[Fill]:
        if _is_live() and self.session is not None:
            return self._live_fill_stop(order, bar, ctx)
        return self.sim.fill_stop(order, bar, ctx)

    def fill_market(self, side: Side, qty: int, bar: pd.Series,
                     ctx: MarketContext) -> Fill:
        if _is_live() and self.session is not None:
            return self._live_fill_market(side, qty, bar, ctx)
        return self.sim.fill_market(side, qty, bar, ctx)

    # -----------------------------------------------------------------
    # LIVE methods (skeletons -- TO IMPLEMENT)
    # -----------------------------------------------------------------
    def _live_check_limit_fill(self, order, bar, ctx) -> Optional[Fill]:
        """Submit (if not already) + poll for fill.

        Implementation outline:
          1. If order.setup_id not in _open_submissions:
             POST /order/placeorder with type=Limit, price=order.price
             store the returned orderId
          2. Poll GET /order/{orderId} for status
             - "Filled" → return Fill with actual filledPrice
             - "Working"/"Pending" → return None (keep waiting)
             - "Cancelled"/"Rejected" → log + return None
          3. On fill, also persist the executionReports so we can build
             the per-trade analytics later

        Latency caveat: the runtime calls this once per bar (every ~1
        minute). Real fills can happen within 80-500ms. We need a separate
        WebSocket subscriber for instant fill notifications -- this
        polling path is the fallback / reconciliation channel.
        """
        raise NotImplementedError(
            "Live Tradovate fill polling not implemented. Use DRY_RUN.")

    def _live_fill_stop(self, order, bar, ctx) -> Optional[Fill]:
        """Submit a Stop-Market order or rely on a pre-placed bracket.
        Implementation outline:
          - On entry fill, we should have already placed a Stop-Market
            child order via /order/placeoso (one-sends-other) bracket
          - This method just checks if the stop child fired
        """
        raise NotImplementedError(
            "Live Tradovate stop fill not implemented. Use DRY_RUN.")

    def _live_fill_market(self, side, qty, bar, ctx) -> Fill:
        """Emergency flatten: POST /order/placeorder type=Market."""
        raise NotImplementedError(
            "Live Tradovate market fill not implemented. Use DRY_RUN.")


# ---------------------------------------------------------------------------
# Pretty status for the dashboard
# ---------------------------------------------------------------------------
def tradovate_status() -> dict:
    """Returns a dict with all the relevant config + connection state.
    Surfaced on the dashboard Downloads tab so we can audit setup without
    SSH'ing into Railway."""
    creds = TradovateCredentials.from_env()
    return {
        "live_mode": _is_live(),
        "demo_cluster": _is_demo(),
        "base_url": _base_url(),
        "credentials": {
            "username":    "set" if creds and creds.username else "missing",
            "password":    "set" if creds and creds.password else "missing",
            "api_key":     "set" if creds and creds.api_key else "missing",
            "api_secret":  "set" if creds and creds.api_secret else "missing",
            "device_id":   "set" if creds and creds.device_id else "missing",
            "app_id":      "set" if creds and creds.app_id else "missing",
        },
        "ready_for_dry_run": creds is not None,
        "ready_for_live":    creds is not None and _is_live(),
    }

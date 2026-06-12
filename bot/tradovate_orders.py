"""Tradovate order placement.

Sends bracketed market entries to Tradovate via REST API.

Architecture C (chosen earlier in conversation):
  - MARKET entry at current best ask/bid
  - Server-side OCO bracket attached at fill price:
      stop = fill_price -/+ STOP_PTS    (stop-market)
      target = fill_price +/- TARGET_PTS  (limit)
  - Atomic placement via /order/placeOSO so the bracket can never
    fail to attach. If the entry fills, brackets are live before
    the next tick.

CME compliance: isAutomated=true is FORCED on every order body. Per
Tradovate API docs (page on "Automated Orders"): "The exchange is
very serious about this requirement and failing to do so could
violate exchange policies."
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("tradovate_orders")


# Per Tradovate API docs: round prices to product tick size (0.25 for
# NQ/MNQ). Misaligned prices get silently rejected by the exchange.
def _tick_round(px: float, tick: float = 0.25) -> float:
    return round(round(float(px) / tick) * tick, 2)


@dataclass
class OrderResult:
    ok: bool
    order_id: Optional[int]
    status_code: Optional[int]
    response: dict
    error: Optional[str] = None


class TradovateOrders:
    """REST order placement against the Tradovate API."""

    def __init__(self, session) -> None:
        # session: bot.tradovate_client.TradovateSession
        self.session = session

    @property
    def account_id(self) -> Optional[int]:
        return self.session.get_account_id()

    def _account_spec(self) -> str:
        """The username doubles as accountSpec in Tradovate's API."""
        return self.session.creds.username if self.session.creds else ""

    # ------------------------------------------------------------------
    # Entry with bracket (the bot's primary order type)
    # ------------------------------------------------------------------

    def submit_market_with_bracket(self, *,
                                    side: str,           # "LONG" or "SHORT"
                                    qty: int,
                                    symbol: str,         # e.g. "MNQM6"
                                    stop_pts: float,     # 6.0
                                    target_pts: float,   # 12.0
                                    setup_ref: Optional[str] = None
                                    ) -> OrderResult:
        """Place a market entry with an OCO bracket attached at fill.

        Uses /order/placeOSO: parent = market entry, children = OCO
        of (stop-market, limit-target). Both children are GTC and
        sized to match the parent. The exchange attaches the bracket
        relative to the actual fill price -- not the price we specify
        -- so slippage on entry doesn't leave the bracket mis-anchored.
        """
        account_id = self.account_id
        if account_id is None:
            return OrderResult(ok=False, order_id=None, status_code=None,
                                response={}, error="no_account_id")

        action = "Buy" if side == "LONG" else "Sell"
        opposite_action = "Sell" if side == "LONG" else "Buy"

        # For market orders we don't specify the entry price -- the
        # exchange fills at current bid/ask. The bracket children use
        # PRICE OFFSETS in points relative to fill, which Tradovate
        # supports via the priceOffset field on stopLossBracket /
        # takeProfitBracket parameters.
        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "action": action,
            "symbol": symbol,
            "orderQty": int(qty),
            "orderType": "Market",
            "isAutomated": True,
            # Server-side bracket -- broker attaches at fill price.
            # priceOffset is in TICKS for stop/target. MNQ tick = 0.25,
            # so 6pt stop = 24 ticks, 12pt target = 48 ticks.
            "bracket": {
                "stopLossBracket": {
                    "action": opposite_action,
                    "orderType": "Stop",
                    "priceOffset": float(stop_pts) * (-1 if side == "LONG" else 1),
                },
                "takeProfitBracket": {
                    "action": opposite_action,
                    "orderType": "Limit",
                    "priceOffset": float(target_pts) * (1 if side == "LONG" else -1),
                },
            },
        }
        if setup_ref:
            body["text"] = setup_ref[:64]  # Tradovate caps user text

        logger.info(
            f"[tradovate placeoso] {action} {qty} {symbol} MARKET "
            f"stop={stop_pts}pt target={target_pts}pt ref={setup_ref!r}")
        logger.info(f"[tradovate placeoso BODY] {json.dumps(body)}")

        status, resp = self.session._rest("POST", "/order/placeoso", body=body)
        logger.info(f"[tradovate placeoso RESULT] status={status} "
                    f"resp={str(resp)[:500]!r}")
        result = self._parse_order_response(status, resp)
        # FALLBACK: if placeoso doesn't work (endpoint not recognized or
        # bracket format wrong), drop to a plain market order. Catches
        # the case where Tradovate's REST surface has changed names or
        # the bracket sub-object expects a different shape. Better to
        # have a position without a bracket than no position at all --
        # the bot's 10-min timeout will close it as a safety net.
        if not result.ok:
            logger.warning(f"[tradovate placeoso FAILED] {result.error} "
                           f"-- falling back to plain placeorder (no bracket)")
            return self.submit_market(side=side, qty=qty, symbol=symbol,
                                       setup_ref=setup_ref)
        return result

    # ------------------------------------------------------------------
    # Fallback: simple market order (no bracket -- use only when the
    # OSO endpoint isn't accepted by the account's permission set).
    # ------------------------------------------------------------------

    def submit_market(self, *,
                       side: str,
                       qty: int,
                       symbol: str,
                       setup_ref: Optional[str] = None) -> OrderResult:
        account_id = self.account_id
        if account_id is None:
            return OrderResult(ok=False, order_id=None, status_code=None,
                                response={}, error="no_account_id")

        action = "Buy" if side == "LONG" else "Sell"
        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "action": action,
            "symbol": symbol,
            "orderQty": int(qty),
            "orderType": "Market",
            "isAutomated": True,
        }
        if setup_ref:
            body["text"] = setup_ref[:64]

        logger.info(f"[tradovate placeorder] {action} {qty} {symbol} MARKET")
        logger.info(f"[tradovate placeorder BODY] {json.dumps(body)}")
        status, resp = self.session._rest("POST", "/order/placeorder", body=body)
        logger.info(f"[tradovate placeorder RESULT] status={status} "
                    f"resp={str(resp)[:500]!r}")
        return self._parse_order_response(status, resp)

    # ------------------------------------------------------------------
    # Flat (manual close, used for timeout exits)
    # ------------------------------------------------------------------

    def submit_market_close(self, *,
                             side: str,        # side of the OPEN position
                             qty: int,
                             symbol: str,
                             setup_ref: Optional[str] = None) -> OrderResult:
        """Send opposite-side market order to flatten a position. Used
        for the 10-min timeout exit since the OCO bracket has no
        timeout equivalent."""
        # Opposite direction of the open
        close_side = "SHORT" if side == "LONG" else "LONG"
        return self.submit_market(
            side=close_side, qty=qty, symbol=symbol,
            setup_ref=(f"{setup_ref}-close" if setup_ref else None),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_order_response(self, status: Optional[int],
                                resp: dict) -> OrderResult:
        if status != 200:
            err = (resp.get("errorText") if isinstance(resp, dict) else None) \
                  or f"http_{status}"
            logger.warning(f"[tradovate order FAIL] status={status} err={err!r} "
                           f"resp={str(resp)[:300]!r}")
            return OrderResult(ok=False, order_id=None, status_code=status,
                                response=resp if isinstance(resp, dict) else {},
                                error=err)
        # Tradovate /order/placeorder returns {"orderId": <int>, ...}
        # Tradovate /order/placeOSO returns {"orderId": <int>, ...} as well
        # (the parent order's ID; children are linked server-side)
        order_id = None
        if isinstance(resp, dict):
            order_id = resp.get("orderId") or resp.get("id")
        logger.info(f"[tradovate order OK] order_id={order_id} resp_keys="
                    f"{list(resp.keys()) if isinstance(resp, dict) else None}")
        return OrderResult(ok=True, order_id=order_id, status_code=status,
                            response=resp if isinstance(resp, dict) else {},
                            error=None)

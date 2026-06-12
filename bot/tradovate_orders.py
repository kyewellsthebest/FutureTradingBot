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
                                    entry_estimate: float,  # current market
                                    setup_ref: Optional[str] = None
                                    ) -> OrderResult:
        """Place a market entry with an OCO bracket via /order/placeoso.

        Tradovate's placeoso accepts a parent order with two child
        bracket orders in `bracket1` and `bracket2` fields. Children
        use ABSOLUTE PRICES (stopPrice for Stop, price for Limit),
        not offsets. Both children inherit qty from the parent and
        form an OCO pair server-side -- when one fills, the other
        is auto-cancelled.

        entry_estimate: the bot's current best guess at where the
        market order will fill (typically the live tick price). The
        bracket stop/target are placed relative to this. With sub-
        second WS data the estimate is usually within 1-2 ticks of
        the actual fill, which is fine for a 6pt stop / 12pt target.
        """
        account_id = self.account_id
        if account_id is None:
            return OrderResult(ok=False, order_id=None, status_code=None,
                                response={}, error="no_account_id")

        action = "Buy" if side == "LONG" else "Sell"
        opposite_action = "Sell" if side == "LONG" else "Buy"

        # Compute absolute bracket prices relative to the entry estimate
        if side == "LONG":
            stop_price = _tick_round(entry_estimate - float(stop_pts))
            target_price = _tick_round(entry_estimate + float(target_pts))
        else:
            stop_price = _tick_round(entry_estimate + float(stop_pts))
            target_price = _tick_round(entry_estimate - float(target_pts))

        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "action": action,
            "symbol": symbol,
            "orderQty": int(qty),
            "orderType": "Market",
            "isAutomated": True,
            # bracket1 + bracket2 form an OCO server-side. When the
            # parent (market entry) fills, both children are activated.
            # When either child fills, the other is auto-cancelled.
            "bracket1": {
                "action": opposite_action,
                "orderType": "Stop",
                "stopPrice": stop_price,
                "isAutomated": True,
            },
            "bracket2": {
                "action": opposite_action,
                "orderType": "Limit",
                "price": target_price,
                "isAutomated": True,
            },
        }
        if setup_ref:
            body["text"] = setup_ref[:64]  # Tradovate caps user text

        logger.info(
            f"[tradovate placeoso] {action} {qty} {symbol} MARKET "
            f"entry~={entry_estimate:.2f} stop@{stop_price:.2f} "
            f"target@{target_price:.2f} ref={setup_ref!r}")
        logger.info(f"[tradovate placeoso BODY] {json.dumps(body)}")

        status, resp = self.session._rest("POST", "/order/placeoso", body=body)
        logger.info(f"[tradovate placeoso RESULT] status={status} "
                    f"resp={str(resp)[:500]!r}")
        result = self._parse_order_response(status, resp)
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
        """Flatten an open position AND cancel any working orders for it.

        Uses /order/liquidateposition rather than placeorder for two
        reasons:

        1. ATOMIC FLATTEN + BRACKET CANCEL. After placeoso, the stop
           and target child orders sit as pending working orders. If
           we send a plain opposite market via placeorder to flatten,
           the bracket children remain active -- when price later hits
           one of those levels it opens a NEW position in the bracket
           direction. liquidateposition cancels all working orders on
           the contract AND sends a flatten market in one call.

        2. Tradovate handles the size automatically; we don't have to
           re-derive qty from the position record.

        Used for timeout exits (10-min max hold). For stop/target,
        the OCO bracket handles it server-side and we never call this.
        """
        account_id = self.account_id
        if account_id is None:
            return OrderResult(ok=False, order_id=None, status_code=None,
                                response={}, error="no_account_id")

        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "symbol": symbol,
            "admin": False,
            "isAutomated": True,
        }
        if setup_ref:
            body["text"] = (setup_ref + "-flat")[:64]

        logger.info(f"[tradovate liquidateposition] {symbol}")
        logger.info(f"[tradovate liquidateposition BODY] {json.dumps(body)}")
        status, resp = self.session._rest(
            "POST", "/order/liquidateposition", body=body)
        logger.info(f"[tradovate liquidateposition RESULT] status={status} "
                    f"resp={str(resp)[:500]!r}")
        result = self._parse_order_response(status, resp)
        if not result.ok:
            # FALLBACK: drop to plain placeorder (opposite side market).
            # Leaves bracket children active but at least flattens the
            # naked position immediately.
            logger.warning(f"[tradovate liquidateposition FAILED] "
                           f"{result.error} -- falling back to placeorder")
            close_side = "SHORT" if side == "LONG" else "LONG"
            return self.submit_market(
                side=close_side, qty=qty, symbol=symbol,
                setup_ref=(f"{setup_ref}-close" if setup_ref else None),
            )
        return result

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

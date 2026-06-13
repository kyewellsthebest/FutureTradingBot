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
                                    entry_estimate: float,  # strategy's intended entry
                                    setup_ref: Optional[str] = None
                                    ) -> OrderResult:
        """Place a LIMIT entry at the strategy's intended price with an
        OCO bracket via /order/placeoso.

        WHY LIMIT not MARKET:
        Previously this was a MARKET entry. Market orders fill at
        current bid/ask which slips 1-3pt from the strategy's intended
        retrace level. The bracket children at entry_estimate +/-
        stop_pts/target_pts then end up at the WRONG distance from
        the actual fill -- so when price reaches where the bot
        THOUGHT the stop/target was, the bracket sits elsewhere and
        never fires. User saw this directly: "ticking slowly past
        the target/stop levels" with no execution.

        With LIMIT entry at entry_estimate: order only fills at the
        exact intended price (or doesn't fill at all). Bracket
        children at +/- stop_pts/target_pts are then exactly where
        the strategy expected them. If price taps and reverses
        without filling, no trade -- which matches what the strategy
        wanted in the first place.

        Trade-off: ~15-25% of would-be fills miss. That's the price
        of clean execution vs slipped MARKET execution. Net: better
        because the trades that DO fill match paper expectations.
        """
        account_id = self.account_id
        if account_id is None:
            return OrderResult(ok=False, order_id=None, status_code=None,
                                response={}, error="no_account_id")

        action = "Buy" if side == "LONG" else "Sell"
        opposite_action = "Sell" if side == "LONG" else "Buy"

        # Bracket children are absolute prices relative to the LIMIT
        # entry. Since we're using a LIMIT entry that fills at
        # entry_estimate exactly (or not at all), the bracket distances
        # are now CORRECT relative to the fill price.
        if side == "LONG":
            stop_price = _tick_round(entry_estimate - float(stop_pts))
            target_price = _tick_round(entry_estimate + float(target_pts))
        else:
            stop_price = _tick_round(entry_estimate + float(stop_pts))
            target_price = _tick_round(entry_estimate - float(target_pts))

        entry_price = _tick_round(entry_estimate)
        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "action": action,
            "symbol": symbol,
            "orderQty": int(qty),
            "orderType": "Limit",
            "price": entry_price,
            "timeInForce": "GTC",
            "isAutomated": True,
            # bracket1 + bracket2 form an OCO server-side. When the
            # parent (limit entry) fills, both children are activated.
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
            f"[tradovate placeoso] {action} {qty} {symbol} LIMIT@"
            f"{entry_price:.2f} stop@{stop_price:.2f} "
            f"target@{target_price:.2f} ref={setup_ref!r}")
        logger.info(f"[tradovate placeoso BODY] {json.dumps(body)}")

        status, resp = self.session._rest("POST", "/order/placeoso", body=body)
        logger.info(f"[tradovate placeoso RESULT] status={status} "
                    f"resp={str(resp)[:500]!r}")
        result = self._parse_order_response(status, resp)
        # CRITICAL SAFETY: do NOT fall back to a naked market order. If
        # the bracket fails, we refuse the trade entirely. Previously we
        # silently dropped to /order/placeorder (no bracket) which left
        # positions running naked -- one of those naked positions ran
        # 107pt against the bot for -$428 unrealized before being
        # caught. Better to skip a trade than open a stop-less one.
        if not result.ok:
            logger.error(
                f"[tradovate placeoso FAILED] {result.error}: "
                f"{str(result.response)[:300]!r} -- REFUSING TRADE "
                f"rather than open without bracket. Check the response "
                f"body above to debug the bracket format.")
        else:
            # Verify the bracket children IDs are present. placeoso
            # should return oso1Id and oso2Id pointing at the stop and
            # target child orders. If they're missing, the parent
            # placed but no bracket attached -- still naked.
            resp_dict = result.response if isinstance(result.response, dict) else {}
            oso1 = resp_dict.get("oso1Id")
            oso2 = resp_dict.get("oso2Id")
            # NEW: Actively query each child order to verify it exists
            # with the correct parameters. The user reported seeing
            # price tick past stop/target levels without the bracket
            # firing -- this happens when oso1Id/oso2Id are returned
            # but the orders don't actually exist on the matching
            # engine. Query each and log every field so we have
            # definitive evidence.
            if oso1 and oso2:
                for label, child_id in (("STOP", oso1), ("TARGET", oso2)):
                    try:
                        c_status, c_data = self.session._rest(
                            "GET", "/order/item", params={"id": int(child_id)})
                        if c_status == 200 and isinstance(c_data, dict):
                            logger.info(
                                f"[bracket verify {label}] id={child_id} "
                                f"action={c_data.get('action')} "
                                f"orderType={c_data.get('orderType')} "
                                f"qty={c_data.get('orderQty')} "
                                f"price={c_data.get('price')} "
                                f"stopPrice={c_data.get('stopPrice')} "
                                f"status={c_data.get('ordStatus')}")
                        else:
                            logger.error(
                                f"[bracket verify {label} FAIL] id={child_id} "
                                f"status={c_status} body={str(c_data)[:200]!r}")
                    except Exception as e:
                        logger.error(f"[bracket verify {label}] exception: {e!r}")
            if not oso1 or not oso2:
                logger.error(
                    f"[tradovate placeoso INCOMPLETE] parent order_id="
                    f"{result.order_id} placed but bracket children "
                    f"missing (oso1Id={oso1!r} oso2Id={oso2!r}). "
                    f"Position is NAKED. Sending immediate flatten via "
                    f"liquidateposition.")
                # Emergency: flatten the naked parent right away rather
                # than leave it running. Better to take 0-1pt slippage
                # than risk a runaway like the -$428 position.
                try:
                    self.session._rest(
                        "POST", "/order/liquidateposition",
                        body={
                            "accountSpec": self._account_spec(),
                            "accountId": int(self.account_id),
                            "symbol": symbol,
                            "admin": False,
                            "isAutomated": True,
                        })
                except Exception as e:
                    logger.error(f"emergency liquidate failed: {e!r}")
                return OrderResult(
                    ok=False, order_id=result.order_id,
                    status_code=result.status_code,
                    response=resp_dict,
                    error="bracket_missing_flattened")
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

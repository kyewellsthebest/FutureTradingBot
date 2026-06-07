"""TradersPost webhook broker adapter.

Architecture:
    Bot opens / closes a trade
        -> bot/fib_main.py _on_trade_open / _on_trade_close
        -> TradersPostBroker.submit_open / submit_close
        -> POST JSON to TradersPost webhook URL
        -> TradersPost relays to the user's connected broker
           (Tradovate, IBKR, TradeStation, etc.) via the integration
           the user configured in their TradersPost dashboard.

CONFIGURATION (env vars):
    TRADERSPOST_WEBHOOK_URL   -- the secret URL from TradersPost dashboard
    TRADERSPOST_LIVE          -- "true" to actually POST; default is dry-run
    TRADERSPOST_TICKER        -- contract symbol to send (e.g. "MNQ", "NQ",
                                  or specific like "MNQH26"). Default "MNQ".

SAFETY:
    - Off by default. TRADERSPOST_LIVE=true required to actually send.
    - Dry-run mode logs the exact JSON payload that WOULD be sent.
    - All POSTs wrapped in try/except so a TradersPost outage never
      crashes the bot loop.
    - Webhook URL never written to logs (only the hash prefix).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("traderspost")


def _is_live() -> bool:
    return os.environ.get("TRADERSPOST_LIVE", "false").lower() in ("true", "1", "yes")


def _webhook_url() -> Optional[str]:
    return os.environ.get("TRADERSPOST_WEBHOOK_URL")


def _ticker() -> str:
    # Default to MNQ (micro NQ) which is what the user's strategy is sized for.
    return os.environ.get("TRADERSPOST_TICKER", "MNQ")


def _url_id(url: str) -> str:
    """Short hash prefix for logging (never logs the full secret URL)."""
    return hashlib.sha256(url.encode()).hexdigest()[:8]


def _extract_fill_info(text: str) -> dict:
    """Defensively extract anything fill-related from a TradersPost
    response body. The exact JSON shape varies by broker (Tradovate,
    Alpaca, etc.) and TradersPost version, so we use heuristics:

      - Look for common keys: fillPrice, fill_price, filledAt,
        avgPrice, fillAvgPrice, executionPrice, brokerageOrders[]
      - Capture all numeric values that look like NQ-range prices
        (10000-40000) so a future pass can correlate them
      - Capture any order/transaction IDs we see

    Returns a dict that always has the same keys (filled with None /
    [] if nothing found), so downstream code can read it without
    isinstance() checks.
    """
    out = {
        "fill_price": None,
        "broker_order_id": None,
        "trader_post_id": None,
        "candidate_prices": [],
        "ids": [],
    }
    if not text:
        return out
    try:
        data = json.loads(text)
    except Exception:
        # Not JSON. Skip structured parse; regex over text might still
        # work for ID-looking strings but skip for now.
        return out
    # Walk the JSON structure looking for fill-related keys.
    fill_keys = {
        "fillPrice", "fill_price", "filledAt", "avgPrice",
        "fillAvgPrice", "executionPrice", "filledPrice",
        "price",
    }
    id_keys = {
        "id", "orderId", "order_id", "transactionId", "ticketId",
        "brokerageOrderId", "external_id",
    }
    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in fill_keys and isinstance(v, (int, float)):
                    out["candidate_prices"].append({"key": k, "value": float(v)})
                    if out["fill_price"] is None and 10000 < v < 50000:
                        out["fill_price"] = float(v)
                if k in id_keys and isinstance(v, (str, int)):
                    out["ids"].append({"key": k, "value": str(v)})
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
    _walk(data)
    # Pick the first id-looking value for the top-level shortcuts
    if out["ids"]:
        out["broker_order_id"] = out["ids"][0]["value"]
        if len(out["ids"]) > 1:
            out["trader_post_id"] = out["ids"][1]["value"]
    return out


def _tick_round(px: float, tick: float = 0.25) -> float:
    """Round to nearest NQ tick (0.25 pt). Tradovate / TradersPost can
    silently reject brackets whose prices aren't tick-aligned, leaving
    the position naked. Use this on every price field that goes into a
    payload."""
    return round(round(float(px) / tick) * tick, 2)


@dataclass
class WebhookResult:
    ok: bool
    status_code: Optional[int]
    response_text: str
    payload: dict
    dry_run: bool
    error: Optional[str] = None


class TradersPostBroker:
    """Sends bot signals to TradersPost as HTTP POSTs. Stateless --
    every call is one POST. Idempotency keys recommended on TradersPost's
    side via the orderRef field (we include a deterministic ref per
    trade so retries don't double-fill)."""

    def __init__(self):
        self.url = _webhook_url()
        self.live = _is_live()
        self.ticker = _ticker()
        if self.url:
            logger.info(
                f"TradersPost broker initialised: live={self.live}, "
                f"ticker={self.ticker}, url=<sha:{_url_id(self.url)}>")
        else:
            logger.info("TradersPost broker DISABLED (TRADERSPOST_WEBHOOK_URL not set)")

    # ------------------------------------------------------------------
    # PUBLIC: bot lifecycle hooks
    # ------------------------------------------------------------------
    def submit_open(self, *, side: str, qty: int,
                    setup_id: Optional[str] = None) -> WebhookResult:
        """Send TradersPost a MARKET entry signal.

        Bare-minimum payload -- direction, quantity, market type. NO
        prices, NO brackets. This is the canonical TradersPost design
        pattern: subscription settings own the bracket logic ($12
        stop-loss + $24 take-profit per contract). When the market
        order fills, TradersPost auto-attaches the bracket relative to
        the ACTUAL fill price.

        Why bare-minimum: previous architectures tried to send absolute
        stop/target prices, deferred-target signals, and orderType
        overrides to compensate for our incomplete understanding of
        TradersPost's behavior. Each layer introduced bugs:
          - Limit prices that didn't fill (paper booked phantom wins)
          - Bracket prices that mis-anchored when fill differed
          - Override toggles that we didn't fully control
          - Deferred targets that wiped the stop bracket
          - Bar-based close signals that raced the bracket

        By sending JUST direction+qty+market, the broker fills
        immediately at current price, subscription attaches brackets
        relative to that fill, and the OCO bracket lives on Tradovate
        as the single source of truth for the trade's lifecycle. We
        never need to send another signal until either (a) the bracket
        fires (no action needed from us), or (b) a 10-min timeout
        exhausts (we send a market flat to clean up).

        REQUIREMENTS on the TradersPost subscription side:
          - Stop loss type: Stop Market
          - Stop loss amount: $12 per contract
          - Take profit amount: $24 per contract
          - Entry order type: Market
          - Allow signal override on quantity: Yes
          - Allow signal override on stop/target amounts: No (force
            subscription to own brackets, ignore our payload's silence)

        Timing: caller (fib_main._on_trade_open) is responsible for
        deciding WHEN to fire this signal. The strategy fires the
        signal when price has reached the 0.618 pullback level on a
        closed bar. The market entry fills at whatever current price
        is when TradersPost forwards -- typically very close to the
        bar's close.
        """
        action = "buy" if side == "LONG" else "sell"
        sentiment = "long" if side == "LONG" else "short"
        payload = {
            "ticker":    self.ticker,
            "action":    action,
            "sentiment": sentiment,
            "quantity":  int(qty),
            "orderType": "market",
        }
        if setup_id:
            payload["orderRef"] = setup_id
        return self._post(payload)

    def submit_target(self, *, side: str, qty: int,
                      target_price: float,
                      setup_id: Optional[str] = None) -> WebhookResult:
        """Send a deferred take-profit limit order.

        Used after submit_open(target_price=None) once the Lucid 10s
        microscalp deferral window has elapsed. The position is already
        open (from the prior submit_open with entry+stop). This call
        adds a closing LIMIT order at the target price. When price
        reaches the target, the limit fills and the position closes.

        side: the side of the OPEN position ("LONG" closes via "sell",
              "SHORT" closes via "buy").
        target_price: absolute price the limit should fire at.
        setup_id: same ref as the open, with "-target" suffix appended.
        """
        close_action = "sell" if side == "LONG" else "buy"
        payload = {
            "ticker":    self.ticker,
            "action":    close_action,
            "sentiment": "flat",   # closes the position when filled
            "quantity":  int(qty),
            "price":     _tick_round(target_price),
            "orderType": "limit",
            "timeInForce": "Day",
        }
        if setup_id:
            payload["orderRef"] = setup_id + "-target"
        return self._post(payload)

    def submit_close(self, *, side: str, qty: int,
                     reason: str = "manual",
                     setup_id: Optional[str] = None) -> WebhookResult:
        """Bot has decided to flatten. Send TradersPost an exit signal.

        side: the side of the trade being CLOSED ("LONG" -> exit long).
        reason: free-text label for our own audit trail.

        TradersPost close format: action is the OPPOSITE direction of the
        position being closed, with sentiment="flat". Previous version
        used action="exit" which TradersPost rejected as "Invalid
        Sentiment Action" on every close.
        """
        close_action = "sell" if side == "LONG" else "buy"
        payload = {
            "ticker":    self.ticker,
            "action":    close_action,
            "sentiment": "flat",
            "quantity":  int(qty),
        }
        if setup_id:
            payload["orderRef"] = setup_id + "-exit"
        return self._post(payload)

    # ------------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------------
    def _audit(self, payload: dict, result: "WebhookResult",
                kind: str) -> None:
        """Append a single JSONL row capturing the full request/response
        round-trip. Persistent across restarts. Each row is independently
        parseable so the user can `tail -f`, `jq`, or `grep` the file
        without parsing anything else.

        Schema (one JSON object per line):
          ts        ISO-8601 UTC of the POST attempt
          kind      "open" | "target" | "close"  (which method called)
          ref       orderRef from payload (the trade's setup_id)
          live_mode bool (dry-run vs real POST)
          ok        bool (request succeeded)
          status    HTTP status code (None on dry-run / network fail)
          error     short error tag if any
          payload   the actual JSON we sent
          response  first 500 chars of response body
                    -- for TradersPost LIVE responses this contains the
                    placed order details + brokerage IDs which is what
                    you cross-reference against the broker's order log

        File: data/traderspost_audit.jsonl (account-namespaced via env)
        """
        import os as _os
        try:
            log_dir = _os.environ.get("TRADERSPOST_AUDIT_DIR",
                                       "/home/user/HFTBot/data")
            log_path = f"{log_dir}/traderspost_audit.jsonl"
            # Try to extract structured fill data from the response body
            # so we don't have to re-parse it every time we read the log.
            # TradersPost responses vary by broker; defensively scan for
            # the common field names. Captures ALL price-looking numbers
            # so a future analysis pass can cross-reference against paper.
            extracted = _extract_fill_info(result.response_text or "")
            row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "ref": payload.get("orderRef"),
                "live_mode": self.live,
                "ok": result.ok,
                "status": result.status_code,
                "error": result.error,
                "payload": payload,
                "response": (result.response_text or "")[:500],
                "extracted": extracted,
            }
            with open(log_path, "a") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except Exception as e:
            logger.debug(f"audit log write failed: {e!r}")

    def _post(self, payload: dict) -> WebhookResult:
        # Dry run: log + return
        if not self.live:
            logger.info(f"[traderspost DRY_RUN] would POST: {json.dumps(payload)}")
            result = WebhookResult(ok=True, status_code=None, response_text="DRY_RUN",
                                    payload=payload, dry_run=True)
            self._audit(payload, result, self._kind_from_payload(payload))
            return result
        if not self.url:
            logger.warning("[traderspost] LIVE=true but TRADERSPOST_WEBHOOK_URL not set")
            result = WebhookResult(ok=False, status_code=None, response_text="",
                                    payload=payload, dry_run=False,
                                    error="webhook_url_missing")
            self._audit(payload, result, self._kind_from_payload(payload))
            return result
        kind = self._kind_from_payload(payload)
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.url, data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                # Log the response body too -- this is where Tradovate's
                # bracket attach confirmation / order IDs land, and the
                # only way to verify the stop+target actually got placed
                # vs. silently rejected for tick-alignment or other
                # validation reasons.
                logger.info(
                    f"[traderspost LIVE OK] status={resp.status} "
                    f"action={payload.get('action')} "
                    f"qty={payload.get('quantity')} "
                    f"price={payload.get('price')} "
                    f"stop={payload.get('stopLoss', {}).get('stopPrice')} "
                    f"tgt={payload.get('takeProfit', {}).get('limitPrice')} "
                    f"resp={text[:300]}")
                result = WebhookResult(ok=True, status_code=resp.status,
                                        response_text=text[:500],
                                        payload=payload, dry_run=False)
                self._audit(payload, result, kind)
                return result
        except urllib.error.HTTPError as e:
            err_text = ""
            try:
                err_text = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            logger.warning(
                f"[traderspost LIVE FAIL] status={e.code} "
                f"action={payload.get('action')} body={err_text}")
            result = WebhookResult(ok=False, status_code=e.code,
                                    response_text=err_text,
                                    payload=payload, dry_run=False,
                                    error=f"http_{e.code}")
            self._audit(payload, result, kind)
            return result
        except urllib.error.URLError as e:
            logger.warning(f"[traderspost LIVE NETWORK FAIL] {e!r}")
            result = WebhookResult(ok=False, status_code=None, response_text="",
                                    payload=payload, dry_run=False,
                                    error=f"network_{e.reason!r}")
            self._audit(payload, result, kind)
            return result
        except Exception as e:
            logger.warning(f"[traderspost LIVE UNEXPECTED] {e!r}")
            result = WebhookResult(ok=False, status_code=None, response_text="",
                                    payload=payload, dry_run=False,
                                    error=f"unexpected_{type(e).__name__}")
            self._audit(payload, result, kind)
            return result

    @staticmethod
    def _kind_from_payload(payload: dict) -> str:
        """Derive kind from payload shape -- saves caller from passing it
        through every layer. Detects:
          open   -- has stopLoss/takeProfit child, sentiment in long/short
          target -- has price field but sentiment=flat (separate target)
          close  -- sentiment=flat with no price (market exit)
        """
        # "stopLoss" / "takeProfit" presence -> open (entry+bracket).
        # Use `in` not truthy-get because the child dict might be empty.
        if "stopLoss" in payload or "takeProfit" in payload:
            return "open"
        if payload.get("sentiment") == "flat":
            if "price" in payload:
                return "target"
            return "close"
        # Entries without explicit bracket (shouldn't happen with current
        # code, but handle it): sentiment long/short = open.
        if payload.get("sentiment") in ("long", "short"):
            return "open"
        return "unknown"


def traderspost_status() -> dict:
    """Returns a dict with the adapter's current config + readiness flags.
    Surfaced on the Downloads tab so we can audit without SSH'ing in.
    Never returns the webhook URL itself -- only a hash prefix."""
    url = _webhook_url()
    return {
        "webhook_url_set":  url is not None,
        "webhook_url_hash": _url_id(url) if url else None,
        "live_mode":        _is_live(),
        "ticker":           _ticker(),
        "ready_for_dry_run": True,    # always works in dry-run
        "ready_for_live":   url is not None and _is_live(),
    }

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
                    entry_price: float, stop_price: float,
                    target_price: float,
                    setup_id: Optional[str] = None) -> WebhookResult:
        """Bot has decided to open a trade. Send TradersPost a MARKET
        entry. The TradersPost subscription is configured with $-based
        brackets ($12 stop, $24 target) that compute relative to the
        ACTUAL fill price, so brackets stay correctly distanced even
        when market entries slip.

        side: "LONG" or "SHORT" (bot convention) -> mapped to TP "buy"/"sell"

        Brackets (stopLoss, takeProfit) are NOT sent in the payload --
        TradersPost computes them from the subscription config. This is
        the only way to keep stop/target distances correct when market
        entries fill at a different price than the bot's intended entry.

        entry_price, stop_price, target_price are kept as function
        parameters for caller backwards-compat but only entry_price is
        used (as a reference field in the payload; not used for execution).
        """
        action = "buy" if side == "LONG" else "sell"
        sentiment = "long" if side == "LONG" else "short"
        payload = {
            "ticker":     self.ticker,
            "action":     action,
            "sentiment":  sentiment,
            "quantity":   int(qty),
            # NOTE: "price" field intentionally OMITTED. TradersPost was
            # using it as the bracket-reference price (computing stop/
            # target as offsets from "price", NOT from the actual market
            # fill). For a market order that fills with slippage, this
            # left the brackets at the wrong distance from the real fill
            # -- effectively pinning brackets to the bot's intended entry
            # while the position is at a different price. Omitting "price"
            # forces TradersPost to use the actual fill as the reference,
            # which is what we want for market entries.
            "orderType":  "market",
            "timeInForce": "Day",
        }
        if setup_id:
            # TradersPost respects orderRef as idempotency key on many
            # broker integrations. Prevents accidental double-fills if
            # we retry a transient error.
            payload["orderRef"] = setup_id
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
    def _post(self, payload: dict) -> WebhookResult:
        # Dry run: log + return
        if not self.live:
            logger.info(f"[traderspost DRY_RUN] would POST: {json.dumps(payload)}")
            return WebhookResult(ok=True, status_code=None, response_text="DRY_RUN",
                                 payload=payload, dry_run=True)
        if not self.url:
            logger.warning("[traderspost] LIVE=true but TRADERSPOST_WEBHOOK_URL not set")
            return WebhookResult(ok=False, status_code=None, response_text="",
                                 payload=payload, dry_run=False,
                                 error="webhook_url_missing")
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.url, data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                logger.info(
                    f"[traderspost LIVE OK] status={resp.status} "
                    f"action={payload.get('action')} "
                    f"qty={payload.get('quantity')} "
                    f"price={payload.get('price')}")
                return WebhookResult(ok=True, status_code=resp.status,
                                     response_text=text[:500],
                                     payload=payload, dry_run=False)
        except urllib.error.HTTPError as e:
            err_text = ""
            try:
                err_text = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            logger.warning(
                f"[traderspost LIVE FAIL] status={e.code} "
                f"action={payload.get('action')} body={err_text}")
            return WebhookResult(ok=False, status_code=e.code,
                                 response_text=err_text,
                                 payload=payload, dry_run=False,
                                 error=f"http_{e.code}")
        except urllib.error.URLError as e:
            logger.warning(f"[traderspost LIVE NETWORK FAIL] {e!r}")
            return WebhookResult(ok=False, status_code=None, response_text="",
                                 payload=payload, dry_run=False,
                                 error=f"network_{e.reason!r}")
        except Exception as e:
            logger.warning(f"[traderspost LIVE UNEXPECTED] {e!r}")
            return WebhookResult(ok=False, status_code=None, response_text="",
                                 payload=payload, dry_run=False,
                                 error=f"unexpected_{type(e).__name__}")


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

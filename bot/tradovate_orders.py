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
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("tradovate_orders")


# Module-level audit log: every order placement attempt with full body +
# response + parsed result. Bounded so we don't leak memory over a long
# session. The dashboard's diagnostic bundle exports this verbatim so we
# can reconstruct exactly what was sent vs what the broker returned.
#
# DIAGNOSTIC PERSISTENCE 2026-06-16: also append every audit entry to
# /app/data/audit_log.jsonl so the bundle can replay events across bot
# restarts. Critical for debugging because the bot redeploys every time
# we push -- without persistence, the in-memory ring is always empty for
# the period before the latest deploy.
_AUDIT_LOG: "deque[dict]" = deque(maxlen=2000)

_AUDIT_PERSIST_PATH = None
try:
    import pathlib as _pl
    _ad = _pl.Path(os.environ.get("BOT_DATA_DIR", "/app/data"))
    _ad.mkdir(parents=True, exist_ok=True)
    _AUDIT_PERSIST_PATH = _ad / "audit_log.jsonl"
    # Hydrate the ring buffer from yesterday's persisted file so the bot's
    # in-memory view spans the last ~24h of events on startup.
    if _AUDIT_PERSIST_PATH.exists():
        try:
            with open(_AUDIT_PERSIST_PATH) as _f:
                _lines = _f.readlines()[-2000:]
                for _line in _lines:
                    try:
                        _AUDIT_LOG.append(json.loads(_line))
                    except Exception:
                        pass
        except Exception:
            pass
except Exception:
    pass


def get_audit_log() -> list:
    """Return a copy of the order audit log (newest last)."""
    return list(_AUDIT_LOG)


# LATENCY: audit log disk writes moved OFF the hot path.
# Synchronous open()+write()+close() on every order event was adding
# 1-5ms of unpredictable IO latency to placeoso. The audit queue is
# drained by a background thread so the trade path returns instantly.
import queue as _q
_AUDIT_QUEUE: "_q.Queue" = _q.Queue()
_AUDIT_FLUSHER_STARTED = False
_AUDIT_FLUSHER_LOCK = threading.Lock()


def _start_audit_flusher():
    global _AUDIT_FLUSHER_STARTED
    with _AUDIT_FLUSHER_LOCK:
        if _AUDIT_FLUSHER_STARTED:
            return
        _AUDIT_FLUSHER_STARTED = True
    def _flusher():
        import time as _t
        batch = []
        while True:
            try:
                # Block until something arrives, then drain greedily.
                first = _AUDIT_QUEUE.get(timeout=5.0)
                batch.append(first)
                while True:
                    try:
                        batch.append(_AUDIT_QUEUE.get_nowait())
                    except _q.Empty:
                        break
                if _AUDIT_PERSIST_PATH is not None and batch:
                    try:
                        with open(_AUDIT_PERSIST_PATH, "a") as f:
                            for e in batch:
                                f.write(json.dumps(e, default=str) + "\n")
                    except Exception:
                        pass
                batch.clear()
            except _q.Empty:
                continue
            except Exception:
                _t.sleep(0.5)
    t = threading.Thread(target=_flusher, daemon=True,
                          name="audit-log-flusher")
    t.start()


def _audit(entry: dict) -> None:
    entry = dict(entry)
    entry.setdefault("ts", time.time())
    _AUDIT_LOG.append(entry)
    # Enqueue for background disk flush -- never blocks the caller.
    if _AUDIT_PERSIST_PATH is not None:
        try:
            if not _AUDIT_FLUSHER_STARTED:
                _start_audit_flusher()
            _AUDIT_QUEUE.put_nowait(entry)
        except Exception:
            pass


# Per Tradovate API docs: round prices to product tick size (0.25 for
# NQ/MNQ). Misaligned prices get silently rejected by the exchange.
def _tick_round(px: float, tick: float = 0.25) -> float:
    return round(round(float(px) / tick) * tick, 2)


def _is_marketable(side: str, entry_price: float,
                    bid: Optional[float],
                    ask: Optional[float]) -> Optional[bool]:
    """Return True if a LIMIT @ entry_price would fill immediately given
    the current bid/ask. None if bid/ask unknown.

    For LONG (BUY LIMIT): fills when ask <= limit price.
    For SHORT (SELL LIMIT): fills when bid >= limit price.

    The reconciliation uses this to answer "did we expect this LIMIT
    to fill instantly, or was it sitting waiting for the market to
    come to us?"
    """
    try:
        if side == "LONG" and ask is not None:
            return float(ask) <= float(entry_price)
        if side == "SHORT" and bid is not None:
            return float(bid) >= float(entry_price)
    except Exception:
        pass
    return None


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
    # Liquidate body helper
    # ------------------------------------------------------------------

    def _liquidate_body(self, symbol: str,
                          text_tag: str = "") -> Optional[dict]:
        """Build a valid /order/liquidateposition body. Returns None
        if contractId can't be resolved (caller should skip the call).

        CRITICAL: Tradovate requires contractId in the body, NOT just
        symbol. Symbol-only body returns HTTP 400 with violation:
          {"constraint":"contractId","value":"0",
           "description":"Contract Id should be greater than 0"}
        Production bug observed: target chase + discrepancy detector
        + emergency flatten ALL returning 400, position stuck LONG 4.
        """
        account_id = self.account_id
        if account_id is None:
            return None
        contract_id = None
        try:
            sym_root = symbol.rstrip("0123456789MHUZQNF") if symbol else ""
            # LATENCY: hit the session cache first (set at boot via
            # prewarm) before calling /contract/find. Saves ~100-200ms.
            cache = getattr(self.session, '_contract_id_cache', {}) or {}
            if symbol in cache:
                contract_id = int(cache[symbol])
            else:
                for try_root in [sym_root, "MNQ", symbol]:
                    if not try_root:
                        continue
                    contract = self.session.find_contract(try_root)
                    if contract and contract.get("id"):
                        contract_id = int(contract["id"])
                        # Memoize for next time.
                        cache[symbol] = contract_id
                        break
        except Exception:
            pass
        if not contract_id:
            return None
        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "contractId": contract_id,
            "admin": False,
            "isAutomated": True,
        }
        if text_tag:
            body["text"] = text_tag[:64]
        return body

    # ------------------------------------------------------------------
    # Entry with bracket (the bot's primary order type)
    # ------------------------------------------------------------------

    def submit_market_with_bracket(self, *,
                                    side: str,           # "LONG" or "SHORT"
                                    qty: int,
                                    symbol: str,         # e.g. "MNQM6"
                                    stop_pts: float,     # 6.0  (legacy / fallback)
                                    target_pts: float,   # 12.0 (legacy / fallback)
                                    entry_estimate: float,  # strategy's intended entry
                                    live_price: Optional[float] = None,  # current last from PriceMonitor
                                    setup_ref: Optional[str] = None,
                                    # USER REQUIREMENT 2026-06-15: bot must
                                    # trade EXACTLY like paper. Paper computes
                                    # stop_px/target_px from setup structure
                                    # (fib levels, swing points) -- not from
                                    # fixed 6/12 point distances. When these
                                    # are provided, the broker bracket uses
                                    # paper's exact prices so every fill
                                    # mirrors paper's bracket levels.
                                    paper_stop_px: Optional[float] = None,
                                    paper_target_px: Optional[float] = None,
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
        #
        # USER REQUIREMENT 2026-06-15: bot must trade EXACTLY like paper.
        # Previously BRACKET_SLIP_PRE_ADJUST shifted the broker stop
        # TOWARD entry by 0.5pt so the broker stop-market fill would
        # slip back to paper's level. This made broker stops fire
        # EARLIER than paper stops -- on 11 trades in this audit period
        # the broker hit a 0.5pt-tighter stop while paper's wider stop
        # survived a wick and ran to target. Net leak: ~$36 per false
        # stop-out * 11 = ~$400. Permanently disabled.
        slip_adjust = False
        slip_pts = 0.0

        # CRITICAL: re-anchor bracket prices to actual market when the
        # LIMIT entry is going to fill with PRICE IMPROVEMENT.
        #
        # Bug observed in the wild: SHORT entry @ 30072.50 when current
        # bid was 30083. LIMIT fills immediately at 30083 (price
        # improvement +10.5pt for the seller). But the bracket STOP was
        # pre-computed at entry_estimate + 5.5pt = 30078 -- which is
        # BELOW the actual fill price. Tradovate rejects the bracket
        # as InvalidPrice ("stop already triggered before activation").
        # Result: SHORT position open with NO STOP PROTECTION.
        #
        # Fix: pull the latest Tradovate bid/ask. If the LIMIT will be
        # marketable (filling immediately at improved price), use the
        # current market as the bracket reference. This preserves the
        # strategy's intended RR ratio relative to the actual fill,
        # not relative to the strategy's intended fill.
        # Decide entry type first -- because bracket_ref logic depends
        # on it. With LIMIT entry, the fill price IS entry_estimate (or
        # nothing fills). So bracket_ref should be entry_estimate, no
        # re-anchor to live market.
        # With MARKET entry, fill price is current market (slipped),
        # so bracket_ref must track live market for the bracket to be
        # placed correctly relative to the actual fill.
        # Default flipped to "marketable_limit" 2026-06-22 per user
        # 95%-broker-fill-rate requirement. After the arming fix
        # (commit 9652204) eliminated phantom fires, the remaining
        # ~30% LIMIT miss rate is structural: when the strategy fires
        # SHORT in inverse mode, price has just dropped TO pullback,
        # bid is below pullback, LIMIT SELL waits for bid to come up,
        # and if the down-move continues the LIMIT never fills.
        # Same story for LONG fires after a continuing bounce.
        # Marketable LIMIT bumps the price so it's marketable on
        # submission (LIMIT >= ask for LONG, LIMIT <= bid for SHORT)
        # which guarantees immediate fill within a small buffer
        # (default 1pt via BROKER_MARKETABLE_BUFFER_PTS). It's still
        # a LIMIT (bounded slip protection, NOT a MARKET order) and
        # the paper-revise-on-fill in fib_main records the actual
        # fill price into paper so paper-broker match stays exact.
        # Set BROKER_ENTRY_TYPE=limit to revert to strict LIMIT.
        entry_type = os.environ.get("BROKER_ENTRY_TYPE", "marketable_limit").lower()

        bracket_ref = float(entry_estimate)
        cur_bid = cur_ask = None
        bid_ask_age = None
        try:
            from bot.tick_history import latest_by_src
            tv = latest_by_src("tradovate")
            if tv:
                cur_bid = tv.get("bid")
                cur_ask = tv.get("ask")
                bid_ask_age = time.time() - tv.get("ts", 0)
        except Exception:
            pass
        marketable_with_improvement = False
        ref_source = "entry_estimate"

        # bracket_ref logic for LIMIT entries:
        #
        # When the LIMIT will fill IMMEDIATELY at a better-than-requested
        # price (marketable LIMIT), the actual fill is at live market,
        # NOT at entry_estimate. The bracket must anchor to live market
        # for the stop/target prices to be on the correct side of fill.
        #
        # When the LIMIT is NON-marketable (price hasn't reached the
        # level yet), it rests until price comes back. Fill will be at
        # entry_estimate exactly. bracket_ref = entry_estimate.
        #
        # Bug observed (2026-06-15 20:00): LIMIT entries with improvement
        # were getting brackets calculated against entry_estimate, but
        # the actual fill was 10-30pt away (marketable improvement).
        # Stop ended up wrong-side of fill -> REJECTED -> naked position.
        #
        # Restored: re-anchor bracket_ref to live market ONLY when the
        # LIMIT will be marketable. Non-marketable LIMITs keep
        # bracket_ref = entry_estimate.
        if bid_ask_age is not None and bid_ask_age < 5.0:
            if side == "LONG" and cur_ask is not None:
                ask = float(cur_ask)
                if ask < bracket_ref:
                    bracket_ref = ask
                    marketable_with_improvement = True
                    ref_source = "tradovate_ask"
            elif side == "SHORT" and cur_bid is not None:
                bid = float(cur_bid)
                if bid > bracket_ref:
                    bracket_ref = bid
                    marketable_with_improvement = True
                    ref_source = "tradovate_bid"
        elif live_price is not None:
            lp = float(live_price)
            if side == "LONG" and lp < bracket_ref:
                bracket_ref = lp
                marketable_with_improvement = True
                ref_source = "live_price"
            elif side == "SHORT" and lp > bracket_ref:
                bracket_ref = lp
                marketable_with_improvement = True
                ref_source = "live_price"

        # For MARKET and MARKETABLE_LIMIT entries, anchor bracket_ref
        # to the expected fill side (LONG buys at ask, SHORT sells at
        # bid). This ensures stop/target are at the right distance
        # from where the order will actually fill, not from the
        # theoretical pullback level. Without this, spillover trades
        # (price already 5-15pt past pullback) get brackets that
        # produce 1:1 RR instead of the strategy's intended 1:2.
        if entry_type in ("market", "marketable_limit") and not marketable_with_improvement:
            if bid_ask_age is not None and bid_ask_age < 5.0:
                if side == "LONG" and cur_ask is not None:
                    bracket_ref = float(cur_ask)
                    ref_source = ("tradovate_ask_marketable"
                                   if entry_type == "marketable_limit"
                                   else "tradovate_ask_adverse")
                    marketable_with_improvement = True
                elif side == "SHORT" and cur_bid is not None:
                    bracket_ref = float(cur_bid)
                    ref_source = ("tradovate_bid_marketable"
                                   if entry_type == "marketable_limit"
                                   else "tradovate_bid_adverse")
                    marketable_with_improvement = True
            elif live_price is not None:
                bracket_ref = float(live_price)
                ref_source = ("live_price_marketable"
                               if entry_type == "marketable_limit"
                               else "live_price_adverse")
                marketable_with_improvement = True

        # SAFETY CAP: if the order will fill immediately at a slipped
        # price (MARKET order OR marketable LIMIT) AND the slip would
        # create a bracket > 2x the strategy's intended risk, abort.
        # The strategy's pullback level no longer applies.
        #
        # For non-marketable LIMITs we DON'T abort: the LIMIT rests at
        # entry_estimate, and either fills there (correct) or doesn't
        # fill (no harm). Aborting here would skip the trade unnecessarily.
        will_fill_immediately = (
            entry_type in ("market", "marketable_limit")
            or marketable_with_improvement)
        # Safety cap: skip if drift is so extreme the trade can't be
        # rescued. Default 12pt (2x stop_pts) -- generous; we rely on
        # the anticipatory pre-submit + low-latency reaction to keep
        # actual drift well under 1pt on most fills. Reducing this
        # would cut trade frequency which the user explicitly opposed.
        max_drift = float(os.environ.get(
            "BROKER_MAX_ENTRY_DRIFT_PT", str(float(stop_pts) * 2.0)))
        drift = abs(bracket_ref - float(entry_estimate))
        if will_fill_immediately and drift > max_drift:
            logger.warning(
                f"[placeoso ABORT] price drift {drift:.2f}pt > safety "
                f"cap {max_drift:.2f}pt (entry_est={entry_estimate}, "
                f"bracket_ref={bracket_ref}, side={side}). The market "
                f"moved too far between strategy decision and submit. "
                f"Skipping this trade to preserve risk envelope.")
            _audit({
                "kind": "placeoso_aborted_safety_cap",
                "side": side, "qty": qty, "symbol": symbol,
                "entry_estimate": float(entry_estimate),
                "bracket_ref": bracket_ref,
                "drift_pts": round(drift, 2),
                "max_drift_pts": max_drift,
                "current_bid": cur_bid, "current_ask": cur_ask,
                "setup_ref": setup_ref,
            })
            return OrderResult(
                ok=False, order_id=None, status_code=None,
                response={}, error="price_drift_safety_cap")

        # USER REQUIREMENT: bot trades EXACTLY like paper. When paper's
        # exact stop_px/target_px are supplied, use them as the bracket
        # prices -- but only if they're on the correct side of the
        # expected fill price (otherwise Tradovate rejects InvalidPrice).
        #
        # SHORT bracket: stop must be ABOVE fill, target must be BELOW fill.
        # LONG bracket:  stop must be BELOW fill, target must be ABOVE fill.
        #
        # Reference for "correct side" check: bracket_ref (live market or
        # entry_estimate). If MARKET entry, this is what the fill will be
        # near. If LIMIT entry, fill should be at or improved from entry.
        use_paper_prices = False
        if (paper_stop_px is not None and paper_target_px is not None):
            ps = float(paper_stop_px)
            pt = float(paper_target_px)
            # WIDER STOP TOLERANCE: shift the broker stop AWAY from entry
            # by N points. Live audit found broker stops firing on tick
            # wicks that Polygon's 1-min bar HIGH/LOW didn't capture --
            # converting paper-target trades into broker-stop losses (e.g.
            # 00:17 SHORT entry 30534.75 stop 30540.5 -- paper hit target,
            # broker stopped on a Tradovate tick that didn't print on
            # Polygon). Adding a tolerance buffer keeps the broker bracket
            # alive through those tick wicks, matching paper's bar-based
            # exit detection.
            #
            # Trade-off: when stop legitimately fires, broker takes a
            # slightly bigger loss (extra distance pts). But this saves
            # many false stop-outs that paper survives.
            #
            # Empirical: live broker WR was 30% vs paper 57% (27pp gap).
            # That gap is dominantly tick-wick false stops. +1pt buffer
            # should recover most of it. Tunable via env.
            # USER REQUIREMENT 2026-06-16: broker entry+exit must
            # match paper to within 1pt or exact. The +1pt wick
            # tolerance was making broker stops fire $1-2.50 worse
            # than paper, breaking the price match. Default now 0pt
            # (exact paper). Tuneable via env if needed later.
            tolerance_pts = float(os.environ.get(
                "BROKER_STOP_WICK_TOLERANCE_PTS", "0.0"))
            if side == "LONG":
                # Shift stop further BELOW entry (more negative)
                ps_adj = ps - tolerance_pts
                ok = ps_adj < bracket_ref < pt
            else:  # SHORT
                # Shift stop further ABOVE entry (more positive)
                ps_adj = ps + tolerance_pts
                ok = pt < bracket_ref < ps_adj
            if ok:
                stop_price = _tick_round(ps_adj)
                target_price = _tick_round(pt)
                if slip_adjust:
                    if side == "LONG":
                        stop_price = _tick_round(ps_adj + slip_pts)
                    else:
                        stop_price = _tick_round(ps_adj - slip_pts)
                use_paper_prices = True
                logger.info(
                    f"[bracket EXACT paper +tolerance{tolerance_pts}] {side} "
                    f"entry_est={entry_estimate} ref={bracket_ref:.2f} "
                    f"stop={stop_price:.2f} (paper {ps:.2f} +tol={tolerance_pts}) "
                    f"target={target_price:.2f}")
            else:
                logger.warning(
                    f"[bracket paper-price WRONG SIDE] {side} ref={bracket_ref:.2f} "
                    f"paper_stop={ps} (adj {ps_adj}) paper_target={pt} -- "
                    f"falling back to points-based bracket")

        if not use_paper_prices:
            if side == "LONG":
                stop_raw = bracket_ref - float(stop_pts)
                if slip_adjust:
                    # Stop triggers higher; broker fills slipped down to
                    # match the strategy's intended stop level.
                    stop_raw += slip_pts
                stop_price = _tick_round(stop_raw)
                target_price = _tick_round(bracket_ref + float(target_pts))
            else:
                stop_raw = bracket_ref + float(stop_pts)
                if slip_adjust:
                    stop_raw -= slip_pts
                stop_price = _tick_round(stop_raw)
                target_price = _tick_round(bracket_ref - float(target_pts))

            if marketable_with_improvement:
                logger.info(
                    f"[bracket re-anchored] {side} entry_est={entry_estimate} "
                    f"-> ref={bracket_ref} (drift {drift:.2f}pt via "
                    f"bid={cur_bid} ask={cur_ask}). Bracket: stop={stop_price} "
                    f"target={target_price}.")

        entry_price = _tick_round(entry_estimate)
        # entry_type was decided at the top of this function (~line 242)
        # so the bracket_ref logic could branch on LIMIT vs MARKET.
        # Default is "limit" -- exact fill at strategy entry, no slip
        # cost. Set BROKER_ENTRY_TYPE=market to revert to MARKET with
        # bidirectional bracket_ref re-anchor.
        body = {
            "accountSpec": self._account_spec(),
            "accountId": int(account_id),
            "action": action,
            "symbol": symbol,
            "orderQty": int(qty),
            "isAutomated": True,
            # bracket1 + bracket2 form an OCO server-side. When the
            # parent fills, both children activate. When either fills,
            # the other is auto-cancelled.
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

        # Apply chosen entry type. Three modes:
        #
        # - "limit" (legacy): LIMIT at exactly entry_estimate. Only
        #   fills if price actually trades through that level. Misses
        #   ~15-30% of trades when price moves past the level too
        #   fast for the LIMIT to catch (sustained bounce / continued
        #   move). Per-trade match is perfect when it fills.
        #
        # - "marketable_limit" (new default 2026-06-22 per user
        #   95%-fill-rate requirement): LIMIT priced to GUARANTEE
        #   immediate fill at live ± BROKER_MARKETABLE_BUFFER_PTS.
        #   Still a LIMIT (bounded slip), but the limit is bumped
        #   above current ask (LONG) / below current bid (SHORT) so
        #   it's marketable on submission. Fills at live price or
        #   better. The paper-revise-on-fill in fib_main records the
        #   actual fill price into paper, so paper-broker match stays
        #   perfect even when the fill price differs from
        #   entry_estimate.
        #
        # - "market": MARKET order, no price field. Unbounded slip.
        #   Available for emergency situations; not recommended.
        if entry_type in ("limit", "marketable_limit"):
            body["orderType"] = "Limit"
            limit_price = entry_price
            if entry_type == "marketable_limit":
                # Bump the LIMIT price so it's marketable right now.
                # Use the Tradovate-provided bid/ask if fresh, else
                # fall back to the polygon live_price.
                buffer_pts = float(os.environ.get(
                    "BROKER_MARKETABLE_BUFFER_PTS", "1.0"))
                ref_px = None
                if (bid_ask_age is not None and bid_ask_age < 5.0
                        and cur_ask is not None and cur_bid is not None):
                    ref_px = float(cur_ask) if side == "LONG" else float(cur_bid)
                elif live_price is not None:
                    ref_px = float(live_price)
                if ref_px is not None:
                    if side == "LONG":
                        # LONG LIMIT BUY: marketable when LIMIT >= ask.
                        # Bump to ask + buffer (rounded to tick) so it
                        # crosses the spread immediately and fills.
                        marketable_floor = ref_px + buffer_pts
                        if limit_price < marketable_floor:
                            limit_price = _tick_round(marketable_floor)
                    else:
                        # SHORT LIMIT SELL: marketable when LIMIT <= bid.
                        # Bump down to bid - buffer.
                        marketable_ceiling = ref_px - buffer_pts
                        if limit_price > marketable_ceiling:
                            limit_price = _tick_round(marketable_ceiling)
            body["price"] = limit_price
            body["timeInForce"] = "Day"
        else:
            body["orderType"] = "Market"
            # MARKET orders have no price field

        # Capture market state at submit time so the audit log + bundle
        # show the bid/ask spread when the order went in. This is pure
        # diagnostic -- doesn't change the order, doesn't reduce trades.
        # Used by the post-hoc reconciliation to answer "was this LIMIT
        # marketable (ask <= entry for LONG)?" without guessing.
        market_state = None
        try:
            from bot.tick_history import latest_by_src
            tv = latest_by_src("tradovate") or {}
            market_state = {
                "tradovate_bid": tv.get("bid"),
                "tradovate_ask": tv.get("ask"),
                "tradovate_last": tv.get("px"),
                "tradovate_age_s": (
                    round(time.time() - tv.get("ts"), 3)
                    if tv.get("ts") else None),
                "spread_pts": (
                    round(tv["ask"] - tv["bid"], 4)
                    if tv.get("bid") is not None
                    and tv.get("ask") is not None else None),
                "marketable": _is_marketable(
                    side, entry_price, tv.get("bid"), tv.get("ask")),
            }
        except Exception:
            pass

        logger.info(
            f"[tradovate placeoso] {action} {qty} {symbol} "
            f"{entry_type.upper()}@{entry_price:.2f} stop@{stop_price:.2f} "
            f"target@{target_price:.2f} ref={setup_ref!r} "
            f"market={market_state}")
        logger.info(f"[tradovate placeoso BODY] {json.dumps(body)}")

        # Auto-retry on transient failures. Tradovate's placeoso can
        # return failureReason values like "TimeoutAtMatchingEngine",
        # "QueueFull", "Throttled", "Pending", or HTTP 500/502/503 on
        # ephemeral matching-engine glitches. Without retry, a one-off
        # 200ms blip wipes out the entry entirely. With retry, we
        # recover automatically.
        #
        # NEVER retries on:
        #   - Permanent failures (InvalidPrice, AccountClosed,
        #     Unauthorized, RiskCheckFailed, MaxOrderQty, etc.)
        #   - HTTP 4xx other than 429
        # Retry budget: 3 attempts, exponential backoff 0.2s/0.5s/1.0s.
        # Total worst case ~1.7s -- still inside the strategy's window.
        RETRYABLE_REASONS = {
            "TimeoutAtMatchingEngine",
            "OtherExecProviderError",
            "QueueFull",
            "Throttled",
            "Pending",
            "ServiceUnavailable",
        }
        # LATENCY: retry IMMEDIATELY on first transient (no backoff).
        # The previous 200ms+500ms+1000ms backoff means a single network
        # blip could delay the order by 1.7s -- catastrophic for HFT.
        # Now retry instantly on first failure (matching engine glitches
        # are typically <10ms), short backoff on subsequent failures.
        backoff = [0.0, 0.1, 0.3]
        status, resp = None, None
        attempt = 0
        last_failure_reason = None
        # LATENCY: try WS-based order placement first (saves ~50-100ms
        # vs REST because no new HTTP overhead, just a frame on the
        # already-open authenticated socket). Fall back to REST on the
        # rare case the WS is disconnected.
        use_ws_first = os.environ.get(
            "BROKER_WS_ORDER_SUBMIT", "true").lower() in ("true", "1", "yes")
        while attempt < len(backoff) + 1:
            status, resp = None, None
            if use_ws_first and attempt == 0:
                try:
                    from bot.tradovate_user_ws import get_user_ws
                    _uws = get_user_ws()
                    if _uws is not None and _uws.connected:
                        ws_status, ws_data = _uws.send_request_sync(
                            "order/placeoso", body_json=body, timeout_s=2.0)
                        if ws_status is not None and isinstance(ws_data, dict):
                            status = ws_status
                            resp = ws_data
                            logger.info(
                                f"[tradovate placeoso WS] status={status} "
                                f"resp={str(resp)[:300]!r}")
                except Exception as ws_e:
                    logger.debug(f"WS placeoso failed: {ws_e!r} -- falling to REST")
            if status is None:
                status, resp = self.session._rest(
                    "POST", "/order/placeoso", body=body)
                logger.info(f"[tradovate placeoso REST attempt={attempt}] "
                            f"status={status} resp={str(resp)[:400]!r}")
            # Success?
            if status == 200 and isinstance(resp, dict):
                fr = resp.get("failureReason")
                if not fr:
                    break
                last_failure_reason = fr
                if fr not in RETRYABLE_REASONS:
                    logger.warning(
                        f"[placeoso permanent failure] {fr} -- not retrying")
                    break
                logger.warning(
                    f"[placeoso transient {fr}] retrying...")
            elif status in (429, 500, 502, 503, 504, None):
                logger.warning(
                    f"[placeoso transient HTTP {status}] retrying...")
                last_failure_reason = f"http_{status}"
            else:
                # Permanent HTTP error (400/401/403/404 etc)
                logger.warning(
                    f"[placeoso permanent HTTP {status}] not retrying")
                break
            if attempt < len(backoff):
                import time as _t
                _t.sleep(backoff[attempt])
            attempt += 1
        result = self._parse_order_response(status, resp)
        _audit({
            "kind": "placeoso",
            "side": side, "qty": qty, "symbol": symbol,
            "entry_estimate": float(entry_estimate),
            "entry_price": entry_price,
            "bracket_ref": bracket_ref,
            "bracket_ref_source": ref_source,
            "bracket_drift_pts": round(drift, 4),
            "marketable_with_improvement": marketable_with_improvement,
            "current_bid": cur_bid, "current_ask": cur_ask,
            "bid_ask_age_s": round(bid_ask_age, 3) if bid_ask_age is not None else None,
            "live_price_hint": live_price,
            "stop_price": stop_price, "target_price": target_price,
            "stop_pts": float(stop_pts), "target_pts": float(target_pts),
            "setup_ref": setup_ref,
            "market_state": market_state,
            "request_body": body,
            "http_status": status,
            "response": resp if isinstance(resp, dict) else {"_raw": str(resp)[:500]},
            "parsed_ok": result.ok,
            "parsed_order_id": result.order_id,
            "parsed_error": result.error,
            "attempts": attempt + 1,
            "last_transient_reason": last_failure_reason if attempt > 0 else None,
        })
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
            bracket_verification = {"oso1Id": oso1, "oso2Id": oso2,
                                     "children": []}
            # LATENCY: skip per-child verification REST calls by default.
            # Each placeoso confirmation requires 4 extra REST round-trips
            # (/order/item + /orderVersion/deps for stop AND target) =
            # ~1000-1500ms added to every entry. With LIMIT entries at
            # the strategy's exact price, broker fill happens
            # IMMEDIATELY when price touches -- waiting 1s post-submit
            # to verify means missing the next tick. Trust placeoso's
            # oso1Id/oso2Id presence as the bracket-attached signal.
            # Set BRACKET_VERIFY_POSTSUBMIT=true to re-enable.
            verify_postsubmit = os.environ.get(
                "BRACKET_VERIFY_POSTSUBMIT", "false").lower() in ("true", "1", "yes")
            if oso1 and oso2 and verify_postsubmit:
                # Per Tradovate API entity model:
                #   Order      = {id, accountId, contractId, action, ordStatus,
                #                 ocoId, parentId, linkedId, timestamp}
                #                ^^ NO price, NO orderQty, NO stopPrice!
                #   OrderVersion = {id, orderId, orderQty, orderType,
                #                   price, stopPrice, timeInForce}
                #                ^^ THIS is where the prices live.
                # Previously we queried /order/item and logged
                # qty/price/stopPrice as None for every child, hiding the
                # fact that the bracket might have wrong values. Now we
                # query /order/item for ordStatus AND /orderVersion/deps
                # for the actual prices, and log both.
                for label, child_id in (("STOP", oso1), ("TARGET", oso2)):
                    try:
                        # Order entity for status (Working/Filled/Rejected/Canceled)
                        o_status, o_data = self.session._rest(
                            "GET", "/order/item", params={"id": int(child_id)})
                        # OrderVersion deps for the actual price/qty fields.
                        # /orderVersion/deps?masterid=<orderId> returns ALL
                        # OrderVersion rows for that order (initial + each
                        # modification). We want the latest by id.
                        v_status, v_data = self.session._rest(
                            "GET", "/orderVersion/deps",
                            params={"masterid": int(child_id)})
                        latest_version = None
                        if v_status == 200 and isinstance(v_data, list) and v_data:
                            latest_version = max(
                                v_data,
                                key=lambda d: d.get("id", 0)
                                if isinstance(d, dict) else 0)
                        if o_status == 200 and isinstance(o_data, dict):
                            ord_status = o_data.get("ordStatus")
                            action_field = o_data.get("action")
                            parent_id = o_data.get("parentId")
                            oco_id = o_data.get("ocoId")
                        else:
                            ord_status = action_field = parent_id = oco_id = None
                        if isinstance(latest_version, dict):
                            qty = latest_version.get("orderQty")
                            otype = latest_version.get("orderType")
                            px = latest_version.get("price")
                            spx = latest_version.get("stopPrice")
                            tif = latest_version.get("timeInForce")
                        else:
                            qty = otype = px = spx = tif = None
                        logger.info(
                            f"[bracket verify {label}] id={child_id} "
                            f"action={action_field} orderType={otype} "
                            f"qty={qty} price={px} stopPrice={spx} "
                            f"tif={tif} ordStatus={ord_status} "
                            f"parentId={parent_id} ocoId={oco_id} "
                            f"order_http={o_status} version_http={v_status}")
                        mismatch = None
                        # Sanity: did the bracket attach at the right price?
                        if label == "STOP" and spx is not None:
                            if abs(float(spx) - stop_price) > 0.001:
                                mismatch = (
                                    f"STOP sent={stop_price} broker={spx}")
                                logger.error(
                                    f"[bracket MISMATCH STOP] sent={stop_price} "
                                    f"broker={spx} -- bracket will fire at the "
                                    f"WRONG level, this is the bug the user "
                                    f"reported")
                        if label == "TARGET" and px is not None:
                            if abs(float(px) - target_price) > 0.001:
                                mismatch = (
                                    f"TARGET sent={target_price} broker={px}")
                                logger.error(
                                    f"[bracket MISMATCH TARGET] sent={target_price} "
                                    f"broker={px} -- target will fire at the "
                                    f"WRONG level")
                        bracket_verification["children"].append({
                            "label": label,
                            "child_id": child_id,
                            "order_http": o_status,
                            "version_http": v_status,
                            "action": action_field,
                            "orderType": otype,
                            "orderQty": qty,
                            "price": px,
                            "stopPrice": spx,
                            "timeInForce": tif,
                            "ordStatus": ord_status,
                            "parentId": parent_id,
                            "ocoId": oco_id,
                            "mismatch": mismatch,
                        })
                    except Exception as e:
                        logger.error(f"[bracket verify {label}] exception: {e!r}")
                        bracket_verification["children"].append({
                            "label": label, "child_id": child_id,
                            "exception": repr(e),
                        })
            # Per Tradovate API PDF (Order entity, ordStatus enum):
            #   "Working" = active in the matching engine
            #   "Filled"  = already executed
            #   "Canceled"/"Rejected"/"Expired"/"PendingCancel" = dead
            # If either child is in a dead state, the bracket is broken
            # (one side could fire but the other can't), so we must
            # flatten the position rather than leave it running.
            dead_states = {"Canceled", "Rejected", "Expired",
                            "PendingCancel"}
            bad_child = None
            for c in bracket_verification.get("children", []):
                # Mismatched price = bracket fires at wrong level = bad
                if c.get("mismatch"):
                    bad_child = ("mismatch", c)
                    break
                # Dead ordStatus = bracket child won't trigger = bad
                if c.get("ordStatus") in dead_states:
                    bad_child = ("dead_status", c)
                    break
            if bad_child and oso1 and oso2:
                reason, c = bad_child
                logger.error(
                    f"[tradovate placeoso BAD BRACKET] reason={reason} "
                    f"child={c} -- flattening position immediately to "
                    f"avoid runaway")
                try:
                    body = self._liquidate_body(symbol, text_tag="bad-bracket-flat")
                    if body:
                        self.session._rest(
                            "POST", "/order/liquidateposition", body=body)
                    else:
                        logger.error("emergency liquidate: no contractId")
                except Exception as e:
                    logger.error(f"emergency liquidate failed: {e!r}")
                if _AUDIT_LOG:
                    _AUDIT_LOG[-1]["bracket_verification"] = bracket_verification
                    _AUDIT_LOG[-1]["emergency_flatten"] = {
                        "reason": reason, "child": c,
                    }
                return OrderResult(
                    ok=False, order_id=result.order_id,
                    status_code=result.status_code,
                    response=resp_dict,
                    error=f"bracket_{reason}_flattened")
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
                    body = self._liquidate_body(symbol, text_tag="naked-flat")
                    if body:
                        self.session._rest(
                            "POST", "/order/liquidateposition", body=body)
                    else:
                        logger.error("naked-flatten: no contractId")
                except Exception as e:
                    logger.error(f"emergency liquidate failed: {e!r}")
                return OrderResult(
                    ok=False, order_id=result.order_id,
                    status_code=result.status_code,
                    response=resp_dict,
                    error="bracket_missing_flattened")
            # Attach the bracket verification to the most recent audit
            # entry so the dashboard bundle includes children prices +
            # any MISMATCH we detected.
            if _AUDIT_LOG:
                _AUDIT_LOG[-1]["bracket_verification"] = bracket_verification
        return result

    # ------------------------------------------------------------------
    # Post-submit operations: fill confirmation, cancel
    # ------------------------------------------------------------------

    def get_order_status(self, order_id: int) -> Optional[str]:
        """Return the current ordStatus for an Order id, or None on
        failure. Used to confirm whether a LIMIT entry actually filled.

        ordStatus values per Tradovate API:
          Pending, PendingNew, PendingCancel, PendingReplace,
          Working, Filled, PartialFill (deprecated),
          Canceled, Rejected, Expired, Suspended
        """
        try:
            s, d = self.session._rest(
                "GET", "/order/item", params={"id": int(order_id)})
            if s == 200 and isinstance(d, dict):
                return d.get("ordStatus")
        except Exception:
            pass
        return None

    def get_order_fill_price(self, order_id: int) -> Optional[float]:
        """Return the average fill price for a Filled order, or None
        on failure / not-yet-filled. Used by the paper-revise-entry
        flow when the WS path missed the exec_report and the REST
        poll fallback is what caught the fill.

        Looks at the executionStatistics endpoint which carries
        avgPx / cumQty. For 1-MNQ orders avgPx == fill price.
        """
        try:
            s, d = self.session._rest(
                "GET", "/order/item", params={"id": int(order_id)})
            if s == 200 and isinstance(d, dict):
                if d.get("ordStatus") != "Filled":
                    return None
            # Fills live under /fill/list filtered by orderId, OR
            # the executionStatistics endpoint.
            s2, d2 = self.session._rest(
                "GET", "/executionReport/deps", params={"masterid": int(order_id)})
            if s2 == 200 and isinstance(d2, list):
                # Walk for the last execType=Fill exec report.
                for er in reversed(d2):
                    if not isinstance(er, dict): continue
                    if er.get("execType") in ("Fill", "Filled", "F"):
                        return float(er.get("avgPx") or er.get("lastPx") or 0) or None
            # Fallback: /fill/list filter
            s3, d3 = self.session._rest("GET", "/fill/list")
            if s3 == 200 and isinstance(d3, list):
                for f in d3:
                    if not isinstance(f, dict): continue
                    if int(f.get("orderId") or 0) == int(order_id):
                        return float(f.get("price") or 0) or None
        except Exception:
            pass
        return None

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a working order. Used by fib_main to kill stale
        LIMIT entries that didn't fill within the strategy's window.

        WHY this matters: a LIMIT sitting beyond the strategy's
        intended window can fill on a later price reversion at a
        time the strategy would never have wanted to open. That's
        the "bot opened at the wrong moment" symptom users describe
        when reviewing the broker tab.
        """
        try:
            body = {
                "orderId": int(order_id),
                "isAutomated": True,
            }
            s, d = self.session._rest(
                "POST", "/order/cancelorder", body=body)
            ok = (s == 200 and isinstance(d, dict)
                   and not d.get("failureReason"))
            logger.info(f"[cancelorder] id={order_id} http={s} ok={ok} "
                        f"resp={str(d)[:200]!r}")
            _audit({
                "kind": "cancelorder",
                "order_id": int(order_id),
                "request_body": body,
                "http_status": s,
                "response": d if isinstance(d, dict) else {"_raw": str(d)[:300]},
                "parsed_ok": ok,
            })
            return ok
        except Exception as e:
            logger.error(f"[cancelorder] exception: {e!r}")
            return False

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
        result = self._parse_order_response(status, resp)
        _audit({
            "kind": "placeorder",
            "side": side, "qty": qty, "symbol": symbol,
            "setup_ref": setup_ref,
            "request_body": body,
            "http_status": status,
            "response": resp if isinstance(resp, dict) else {"_raw": str(resp)[:500]},
            "parsed_ok": result.ok,
            "parsed_order_id": result.order_id,
            "parsed_error": result.error,
        })
        return result

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

        # Use the contractId-aware helper. symbol-only liquidate
        # returns HTTP 400 (production bug observed).
        body = self._liquidate_body(
            symbol, text_tag=(setup_ref + "-flat") if setup_ref else "")
        if body is None:
            logger.error(f"[liquidateposition] could not resolve "
                         f"contractId for symbol={symbol}; cannot flatten")
            return OrderResult(ok=False, order_id=None, status_code=None,
                                response={"error": "no_contract_id"},
                                error="no_contract_id")

        logger.info(f"[tradovate liquidateposition] {symbol}")
        logger.info(f"[tradovate liquidateposition BODY] {json.dumps(body)}")
        status, resp = self.session._rest(
            "POST", "/order/liquidateposition", body=body)
        logger.info(f"[tradovate liquidateposition RESULT] status={status} "
                    f"resp={str(resp)[:500]!r}")
        result = self._parse_order_response(status, resp)
        _audit({
            "kind": "liquidateposition",
            "side": side, "qty": qty, "symbol": symbol,
            "setup_ref": setup_ref,
            "request_body": body,
            "http_status": status,
            "response": resp if isinstance(resp, dict) else {"_raw": str(resp)[:500]},
            "parsed_ok": result.ok,
            "parsed_order_id": result.order_id,
            "parsed_error": result.error,
        })
        if not result.ok:
            # CRITICAL BUG FIX: The previous fallback called
            # submit_market(opposite_side) which OPENED A NEW POSITION
            # in the opposite direction when liquidateposition failed.
            #
            # Real-world consequence: the TARGET CHASE fix (e9ea951)
            # calls submit_market_close when paper detects a target
            # wick. If the bracket already fired (most common case),
            # the broker position is already flat. liquidateposition
            # then returns an error (nothing to liquidate). The
            # placeorder fallback then OPENED a new LONG/SHORT --
            # exactly the wrong thing.
            #
            # Result observed in bundle: bot accumulated netPos=4
            # LONG positions because each "target chase" on a closed
            # SHORT opened a new LONG via this fallback.
            #
            # Fix: just log and return the failure. If position is
            # already flat, that's the desired end state -- no action
            # needed. If position is open and liquidate genuinely
            # failed (rare API issue), we DON'T want to compound by
            # opening MORE positions; we want to alert and stop.
            logger.warning(
                f"[tradovate liquidateposition FAILED] {result.error} "
                f"-- NO fallback (refusing to open opposite position "
                f"that previously caused position-stacking bug)")
            return result
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
        # CRITICAL: Tradovate's PlaceOrderResult / PlaceOsoResult / PlaceOcoResult
        # schemas ALL return HTTP 200 even on rejection. The rejection
        # signal is the `failureReason` field. Per the API PDF:
        #   PlaceOsoResult = {
        #     "failureReason": <enum: MaxOrderQty/NoOrderId/AccountClosed/
        #                       LiquidationOnly/InvalidPrice/RiskCheckFailed/
        #                       Unauthorized/OtherExecProviderError/...>,
        #     "failureText":  <human-readable>,
        #     "orderId":      <int -- parent order, present on SUCCESS only>,
        #     "oso1Id":       <int -- bracket child 1, success only>,
        #     "oso2Id":       <int -- bracket child 2, success only>,
        #   }
        # We were treating any 200 as success, so silent rejections looked
        # OK and the bot moved on thinking it had a position when it didn't
        # (or worse, parent placed but children rejected leaving naked).
        if isinstance(resp, dict):
            failure_reason = resp.get("failureReason")
            failure_text = resp.get("failureText")
            if failure_reason:
                err = f"{failure_reason}: {failure_text}" if failure_text else str(failure_reason)
                logger.warning(f"[tradovate order REJECTED by API] "
                               f"failureReason={failure_reason!r} "
                               f"failureText={failure_text!r} "
                               f"resp={str(resp)[:300]!r}")
                return OrderResult(ok=False, order_id=None, status_code=status,
                                    response=resp, error=err)
        # Tradovate /order/placeorder returns {"orderId": <int>, ...}
        # Tradovate /order/placeoso returns {"orderId": <int>, "oso1Id": <int>,
        # "oso2Id": <int>} on success (parent + 2 children)
        order_id = None
        if isinstance(resp, dict):
            order_id = resp.get("orderId") or resp.get("id")
        logger.info(f"[tradovate order OK] order_id={order_id} resp_keys="
                    f"{list(resp.keys()) if isinstance(resp, dict) else None}")
        return OrderResult(ok=True, order_id=order_id, status_code=status,
                            response=resp if isinstance(resp, dict) else {},
                            error=None)

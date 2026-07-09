"""FADESZ+P — the deployed strategy. Passive-entry sized overextension
fade, the champion of the 39-round hunt (research/round39_results.txt):
since Mar 2026: $1,330/wk at ~110 trades/wk, worst week -$400, 82%
positive weeks; blind Jun-Jul: $2,344/wk, 100% positive weeks. All at
tick-walked fills with $1.50/RT.

Rules (exactly the validated simulation):
  - signal on each CLOSED 1m bar, 14:00 <= UTC < 20:44 (entry cutoff so
    the 15m exit lands before the 21:00 close)
  - mom10 = close - close[10 bars ago]; ATR = 20-bar mean true range
  - |mom10| > 1.2*ATR  ->  fade it (price down hard -> BUY, up -> SELL)
  - size by magnitude: |mom10|/ATR >= 3.0 -> 3 MNQ, >= 2.0 -> 2, else 1
  - entry: LIMIT 1.0 pt beyond the close (deeper into the move),
    cancel if unfilled after 180 s
  - exit: MARKET 15 minutes after the fill. No stops, no targets
    (both tested; both hurt). Disaster guard only: 100 pts.
  - one position at a time; new signals ignored while pending/open

The engine drives BOTH books: real Tradovate orders and the paper
account (entry booked at the limit price when the broker order fills;
exit at the engine's model price; the execution audit measures true
divergence). State persists to data_dir()/fadesz_engine.json.

Kill switch: BROKER_ENGINE=off -> no new entries, existing position
exits on schedule. Weekly regime gate is operational guidance (trailing
4 weeks negative -> stand down) surfaced in the snapshot, not enforced.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("fadesz")

THRESH_ATR = 1.2
LADDER = (2.0, 3.0)          # fmag >= 2.0 -> 2 MNQ, >= 3.0 -> 3 MNQ
OFFSET_PT = 1.0
CANCEL_S = 180
HOLD_MIN = 15
ENTRY_LO, ENTRY_HI = 14.0, 20.73     # UTC hours; exit lands pre-close
DISASTER_PT = 100.0


def strategy_mode() -> str:
    """fadesz (default) | off. BROKER_ENGINE=stack/mirror fall back to
    legacy engines handled in fib_main."""
    return os.environ.get("BROKER_ENGINE", "fadesz").strip().lower()


class FadeszEngine:
    def __init__(self, tradovate_orders, symbol_fn,
                 paper_enter=None, paper_close=None):
        self.orders = tradovate_orders
        self.symbol_fn = symbol_fn
        self.paper_enter = paper_enter
        self.paper_close = paper_close
        self.qty_cap = int(os.environ.get("FADESZ_MAX_QTY", "3"))
        self.pos: Optional[dict] = None      # side, qty, entry_px, exit_due
        self.pending: Optional[dict] = None  # order_id, side, qty, price, ts
        self.last_bar_ts: Optional[str] = None
        self.first_cycle_done = False
        self.counters = {"signals": 0, "placed": 0, "filled": 0,
                         "canceled": 0, "exits": 0, "order_errors": 0,
                         "disaster": 0}
        self._load()

    # ---- persistence -----------------------------------------------------
    def _path(self):
        from bot.account_ctx import data_dir
        return data_dir() / "fadesz_engine.json"

    def _load(self):
        try:
            p = self._path()
            if p.exists():
                d = json.loads(p.read_text())
                self.pos = d.get("pos")
                self.pending = d.get("pending")
                self.last_bar_ts = d.get("last_bar_ts")
                self.counters.update(d.get("counters", {}))
                if self.pos or self.pending:
                    logger.warning(f"[fadesz] resumed pos={self.pos} "
                                   f"pending={self.pending}")
        except Exception as e:
            logger.warning(f"[fadesz] load: {e!r}")

    def _save(self):
        try:
            self._path().write_text(json.dumps({
                "pos": self.pos, "pending": self.pending,
                "last_bar_ts": self.last_bar_ts,
                "counters": self.counters}))
        except Exception as e:
            logger.debug(f"[fadesz] save: {e!r}")

    # ---- public ------------------------------------------------------------
    def holds_position(self) -> bool:
        return bool(self.pos) or bool(self.pending)

    def snapshot(self) -> dict:
        return {"active": True, "strategy": "FADESZ+P",
                "pos": self.pos, "pending": self.pending,
                "counters": dict(self.counters)}

    # ---- broker I/O ----------------------------------------------------------
    def _rest(self, method, path, body=None):
        sess = self.orders.session
        return sess._rest(method, path, body=body)

    def _place(self, action: str, qty: int, order_type: str,
               price: float | None, tag: str):
        try:
            sess = self.orders.session
            spec = None
            try:
                spec = self.orders._account_spec()
            except Exception:
                pass
            body = {"accountSpec": spec, "accountId": sess.get_account_id(),
                    "action": action, "symbol": self.symbol_fn(),
                    "orderQty": int(qty), "orderType": order_type,
                    "isAutomated": True, "text": tag[:64]}
            if order_type == "Limit" and price is not None:
                body["price"] = float(price)
            body = {k: v for k, v in body.items() if v is not None}
            status, resp = self._rest("POST", "/order/placeorder", body=body)
            ok = status == 200 and isinstance(resp, dict) and resp.get("orderId")
            if not ok:
                self.counters["order_errors"] += 1
                logger.error(f"[fadesz] order fail {status} {resp}")
                return None
            logger.warning(f"[fadesz] {order_type} {action} {qty} "
                           f"@{price if price else 'MKT'} ({tag})")
            return int(resp["orderId"])
        except Exception as e:
            self.counters["order_errors"] += 1
            logger.error(f"[fadesz] order exc: {e!r}")
            return None

    def _order_status(self, order_id: int) -> str:
        try:
            st, resp = self._rest("GET", f"/order/item?id={int(order_id)}")
            if st == 200 and isinstance(resp, dict):
                return str(resp.get("ordStatus") or "")
        except Exception as e:
            logger.debug(f"[fadesz] status: {e!r}")
        return ""

    def _cancel(self, order_id: int) -> None:
        try:
            self._rest("POST", "/order/cancelorder",
                       body={"orderId": int(order_id), "isAutomated": True})
        except Exception as e:
            logger.debug(f"[fadesz] cancel: {e!r}")

    def _flatten_stale_broker(self):
        """First cycle after (re)start with no engine position: any broker
        net position is stale (previous strategy / crash) -> flatten."""
        try:
            sess = self.orders.session
            st, positions = self._rest("GET", "/position/list")
            if st != 200 or not isinstance(positions, list):
                return
            aid = sess.get_account_id()
            net = 0
            for p in positions:
                if isinstance(p, dict) and p.get("accountId") == aid:
                    net = int(p.get("netPos") or 0)
                    break
            if net > 0:
                self._place("Sell", net, "Market", None, "fadesz_reset_flat")
            elif net < 0:
                self._place("Buy", -net, "Market", None, "fadesz_reset_flat")
            if net != 0:
                logger.warning(f"[fadesz] flattened stale broker net {net}")
        except Exception as e:
            logger.debug(f"[fadesz] stale flatten: {e!r}")

    # ---- cycle ------------------------------------------------------------------
    def on_cycle(self, bars_1m, now: datetime) -> None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if not self.first_cycle_done:
            self.first_cycle_done = True
            if self.pos is None and self.pending is None \
                    and self.orders is not None:
                self._flatten_stale_broker()

        # 1) pending limit management ------------------------------------
        if self.pending is not None:
            placed = datetime.fromisoformat(self.pending["ts"])
            status = self._order_status(self.pending["order_id"]) \
                if self.orders is not None else "Filled"
            if status == "Filled":
                p = self.pending
                self.pending = None
                self.counters["filled"] += 1
                exit_due = now + timedelta(minutes=HOLD_MIN)
                self.pos = {"side": p["side"], "qty": p["qty"],
                            "entry_px": p["price"],
                            "entry_ts": now.isoformat(),
                            "exit_due": exit_due.isoformat()}
                logger.warning(f"[fadesz] FILLED {p['side']} {p['qty']} "
                               f"@{p['price']}")
                if self.paper_enter is not None:
                    try:
                        self.paper_enter(
                            side="LONG" if p["side"] > 0 else "SHORT",
                            entry_px=float(p["price"]), qty=int(p["qty"]),
                            now=now)
                    except Exception as e:
                        logger.error(f"[fadesz] paper enter: {e!r}")
                self._save()
            elif status in ("Canceled", "Rejected", "Expired"):
                self.pending = None
                self.counters["canceled"] += 1
                self._save()
            elif (now - placed).total_seconds() > CANCEL_S:
                if self.orders is not None:
                    self._cancel(self.pending["order_id"])
                self.pending = None
                self.counters["canceled"] += 1
                logger.warning("[fadesz] limit unfilled 180s -> canceled")
                self._save()

        if bars_1m is None or len(bars_1m) < 25:
            return
        c = bars_1m["close"].to_numpy()
        h = bars_1m["high"].to_numpy()
        l = bars_1m["low"].to_numpy()
        last_close = float(c[-1])

        # 2) position exit --------------------------------------------------
        if self.pos is not None:
            due = datetime.fromisoformat(self.pos["exit_due"])
            side = int(self.pos["side"])
            adverse = (self.pos["entry_px"] - last_close) * side
            eod = (now.hour == 20 and now.minute >= 55) or now.hour == 21
            if now >= due or eod or adverse >= DISASTER_PT:
                if adverse >= DISASTER_PT:
                    self.counters["disaster"] += 1
                action = "Sell" if side > 0 else "Buy"
                ok = True
                if self.orders is not None:
                    ok = self._place(action, int(self.pos["qty"]), "Market",
                                     None, "fadesz_exit") is not None
                if ok:
                    self.counters["exits"] += 1
                    if self.paper_close is not None:
                        try:
                            self.paper_close(exit_px=last_close, now=now)
                        except Exception as e:
                            logger.error(f"[fadesz] paper close: {e!r}")
                    self.pos = None
                    self._save()
            return          # never enter on the same cycle as a held position

        # 3) new signal on newest CLOSED bar --------------------------------
        if strategy_mode() != "fadesz" or self.pending is not None:
            return
        bar_ts = str(bars_1m.index[-1])
        if bar_ts == self.last_bar_ts:
            return
        self.last_bar_ts = bar_ts
        hr = now.hour + now.minute / 60.0
        if not (ENTRY_LO <= hr < ENTRY_HI):
            self._save()
            return
        import numpy as np
        mom10 = last_close - float(c[-11])
        r1 = np.abs(np.diff(c[-21:]))          # 20 close-to-close moves
        trr = np.maximum(h[-20:] - l[-20:], r1)
        atr = float(np.mean(trr))
        if atr <= 0 or abs(mom10) <= THRESH_ATR * atr:
            self._save()
            return
        self.counters["signals"] += 1
        side = 1 if mom10 < 0 else -1
        fmag = abs(mom10) / atr
        qty = 3 if fmag >= LADDER[1] else (2 if fmag >= LADDER[0] else 1)
        qty = min(qty, self.qty_cap)
        price = last_close - OFFSET_PT * side
        action = "Buy" if side > 0 else "Sell"
        oid = None
        if self.orders is not None:
            oid = self._place(action, qty, "Limit", price,
                              f"fadesz_entry_m{fmag:.1f}")
            if oid is None:
                self._save()
                return
        self.pending = {"order_id": oid or 0, "side": side, "qty": qty,
                        "price": price, "ts": now.isoformat()}
        self.counters["placed"] += 1
        self._save()

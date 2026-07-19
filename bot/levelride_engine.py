"""LEVELRIDE-LADDER 3-rung — BROKER engine (v2).

Strategy (round 82/83/84 audits, clean 2026-dedup numbers):
  Ladder of 3 levels set at the session open (14:00 UTC first 1m
  bar): L0 = open, L+ = open+20, L- = open-20 (NQ pts).
  A 1m bar CLOSING across a rung's level (vs the prior close) fires
  a market-with-the-cross entry on that rung: 1 MNQ, target +260,
  stop -80, max hold 4h, entries until 20:26 UTC, flat 20:55.
  Each rung re-arms after its trade closes. Up to 3 concurrent.

Backtest (3-rung, 2y, $1.50/RT worst-case): +$2,471/wk, WR 63.9%,
avgW +$290 / avgL -$149, worst day -$1,301, MDD -$2,508, 96% pos
weeks. v2 places MARKET orders on the Tradovate account (demo
simulator) per explicit user order Jul 19 2026, replacing FADESZ.
Ledger in data_dir()/levelride_engine.json mirrors model prices;
the nightly execution audit compares broker fills vs this model.
Kill switch: LEVELRIDE_ENABLED=0 (or LEVELRIDE_BROKER=0 for
model-only mode).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from bot.config import data_dir

logger = logging.getLogger(__name__)

TGT_PT = 260.0
STP_PT = 80.0
HOLD_H = 4
RUNG_OFF = [0.0, 20.0, -20.0]
PT_VALUE = 2.0
FEES_RT = 1.50
ADVERSE_PT = 0.25          # market-entry adverse assumption
ENTRY_END = (20, 26)       # UTC
FLAT_AT = (20, 55)
SESS_OPEN = (14, 0)


class LevelrideEngine:
    def __init__(self, tradovate_orders=None, symbol_fn=None):
        self.enabled = os.environ.get("LEVELRIDE_ENABLED", "1") == "1"
        self.orders = tradovate_orders
        self.symbol_fn = symbol_fn
        self.broker_on = (os.environ.get("LEVELRIDE_BROKER", "1") == "1"
                          and tradovate_orders is not None)
        self.day = None
        self.anchor = None
        self.levels = []
        self.prev_close = None
        self.pos = {}          # rung idx -> dict
        self.trades = []
        self.day_pnl = 0.0
        self.total_pnl = 0.0
        self.counters = {"entries": 0, "target": 0, "stop": 0,
                         "timer": 0, "eod": 0}
        self._load()

    def _path(self):
        return data_dir() / "levelride_engine.json"

    def _load(self):
        try:
            p = self._path()
            if p.exists():
                d = json.loads(p.read_text())
                self.trades = d.get("trades", [])[:500]
                self.total_pnl = d.get("total_pnl", 0.0)
                self.counters.update(d.get("counters", {}))
        except Exception as e:
            logger.debug(f"[levelride] load: {e!r}")

    def _save(self):
        try:
            self._path().write_text(json.dumps({
                "trades": self.trades[:500],
                "total_pnl": round(self.total_pnl, 2),
                "counters": self.counters,
                "day": self.day, "anchor": self.anchor,
            }))
        except Exception as e:
            logger.debug(f"[levelride] save: {e!r}")

    def snapshot(self) -> dict:
        return {
            "strategy": "LEVELRIDE-LADDER 3 (BROKER)" if self.broker_on else "LEVELRIDE-LADDER 3 (MODEL)",
            "enabled": self.enabled,
            "anchor": self.anchor,
            "levels": self.levels,
            "open_rungs": {str(k): v for k, v in self.pos.items()},
            "day_pnl": round(self.day_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "n_trades": len(self.trades),
            "counters": self.counters,
        }

    def _mkt(self, action: str, tag: str) -> bool:
        """Market order via the same REST path FADESZ uses."""
        if not self.broker_on:
            return True
        try:
            sess = self.orders.session
            spec = None
            try:
                spec = self.orders._account_spec()
            except Exception:
                pass
            body = {"accountSpec": spec,
                    "accountId": sess.get_account_id(),
                    "action": action, "symbol": self.symbol_fn(),
                    "orderQty": 1, "orderType": "Market",
                    "isAutomated": True, "text": tag[:64]}
            body = {k: v for k, v in body.items() if v is not None}
            st, resp = sess._rest("POST", "/order/placeorder", body=body)
            ok = st == 200 and isinstance(resp, dict) \
                and resp.get("orderId")
            if not ok:
                self.counters["order_errors"] = \
                    self.counters.get("order_errors", 0) + 1
                logger.error(f"[levelride] order fail {st} {resp}")
                return False
            logger.warning(f"[levelride] MKT {action} 1 ({tag})")
            return True
        except Exception as e:
            self.counters["order_errors"] = \
                self.counters.get("order_errors", 0) + 1
            logger.error(f"[levelride] order exc: {e!r}")
            return False

    def _close(self, ri, px, reason, now):
        p = self.pos.pop(ri)
        self._mkt("Sell" if p["side"] > 0 else "Buy",
                  f"levelride_exit_r{ri}_{reason}")
        pnl = (px - p["entry"]) * p["side"] * PT_VALUE - FEES_RT
        self.day_pnl += pnl
        self.total_pnl += pnl
        self.counters[reason] = self.counters.get(reason, 0) + 1
        self.trades.insert(0, {
            "rung": ri, "side": p["side"], "entry": p["entry"],
            "exit": px, "pnl": round(pnl, 2), "reason": reason,
            "t_in": p["t_in"], "t_out": now.isoformat()})
        logger.warning(f"[levelride] EXIT rung{ri} {reason} "
                       f"pnl {pnl:+.2f} (day {self.day_pnl:+.0f})")
        self._save()

    def on_cycle(self, bars_1m, now: datetime) -> None:
        if not self.enabled or not bars_1m:
            return
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        b = bars_1m[-1]
        try:
            c = float(b["close"]); h = float(b["high"])
            l = float(b["low"])
            bt = b.get("ts") or b.get("time")
        except Exception:
            return
        dstr = now.strftime("%Y-%m-%d")
        if now.weekday() >= 5:
            return
        # new day / session anchor
        if self.day != dstr:
            self.day = dstr
            self.anchor = None
            self.levels = []
            self.prev_close = None
            self.day_pnl = 0.0
        after_open = (now.hour, now.minute) >= SESS_OPEN
        if self.anchor is None and after_open:
            self.anchor = c          # first closed bar of the session
            self.levels = [self.anchor + o for o in RUNG_OFF]
            self.prev_close = c
            logger.warning(f"[levelride] anchor {self.anchor} "
                           f"levels {self.levels}")
            return
        if self.anchor is None:
            return
        # ---- manage open rungs (intrabar target/stop via bar h/l)
        flat_now = (now.hour, now.minute) >= FLAT_AT
        for ri in list(self.pos.keys()):
            p = self.pos[ri]
            s = p["side"]
            tgt = p["entry"] + TGT_PT * s
            stp = p["entry"] - STP_PT * s
            hit_stop = l <= stp if s > 0 else h >= stp
            hit_tgt = h >= tgt if s > 0 else l <= tgt
            due = datetime.fromisoformat(p["t_in"]) \
                + timedelta(hours=HOLD_H)
            if hit_stop:                       # stop first (conservative)
                self._close(ri, stp - ADVERSE_PT * s, "stop", now)
            elif hit_tgt:
                self._close(ri, tgt, "target", now)
            elif flat_now:
                self._close(ri, c - ADVERSE_PT * s, "eod", now)
            elif now >= due:
                self._close(ri, c - ADVERSE_PT * s, "timer", now)
        # ---- entries on bar-close crossings
        can_enter = after_open and not flat_now and \
            (now.hour, now.minute) <= ENTRY_END
        if can_enter and self.prev_close is not None:
            for ri, lev in enumerate(self.levels):
                if ri in self.pos:
                    continue
                a, bb = self.prev_close, c
                if a == bb:
                    continue
                crossed = (a < lev <= bb) or (a > lev >= bb)
                if not crossed:
                    continue
                side = 1 if bb > lev else -1
                if not self._mkt("Buy" if side > 0 else "Sell",
                                 f"levelride_enter_r{ri}"):
                    continue
                entry = c + ADVERSE_PT * side
                self.pos[ri] = {"side": side, "entry": entry,
                                "t_in": now.isoformat()}
                self.counters["entries"] += 1
                logger.warning(f"[levelride] ENTER rung{ri} "
                               f"{'LONG' if side > 0 else 'SHORT'} "
                               f"@{entry} (level {lev})")
                self._save()
        self.prev_close = c

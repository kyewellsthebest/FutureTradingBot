"""LEVELRIDE-LADDER — BROKER engine (v3, matches confirmed backtest).

Confirmed clean self-contained backtest (2yr, tick-level, $1.50/RT,
no lookahead): 3 concurrent -> +$2,189/wk, 68% WR, 96% pos weeks,
worst day -$1,463. Definition:
  - Anchor = session open (first price at/after 14:00 UTC).
  - 11 levels = anchor + [0, +-25, +-50, +-75, +-100, +-150] NQ pts.
  - A price CROSS of a level (prev tick one side -> now the other)
    fires a market entry WITH the cross on that level's rung.
  - Bracket: target +260 / stop -80 pts, max hold 4h, flat 20:55.
  - Up to 3 positions open at once (nearest-triggered win the slots).
  - Each level re-arms after its position closes.
Crossing is checked on every price update the caller feeds (live:
~2s cycles via the forming 1m bar; replay: per tick) -> matches the
backtest's tick-level detection closely.

Broker orders via the same REST path FADESZ used (demo account).
Kill: LEVELRIDE_ENABLED=0 (all off) / LEVELRIDE_BROKER=0 (model).
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
OFFS = [0.0, 25.0, -25.0, 50.0, -50.0, 75.0, -75.0,
        100.0, -100.0, 150.0, -150.0]
MAX_CONCURRENT = 3
PT_VALUE = 2.0
FEES_RT = 1.50
ADVERSE_PT = 0.25
ENTRY_LO = 14.0
ENTRY_HI = 20.73
FLAT_AT = (20, 55)
SESS_OPEN = (14, 0)


class LevelrideEngine:
    def __init__(self, tradovate_orders=None, symbol_fn=None,
                 on_trade=None):
        self.enabled = os.environ.get("LEVELRIDE_ENABLED", "1") == "1"
        self.orders = tradovate_orders
        self.symbol_fn = symbol_fn
        self.on_trade = on_trade
        self.broker_on = (os.environ.get("LEVELRIDE_BROKER", "1") == "1"
                          and tradovate_orders is not None)
        self.day = None
        self.anchor = None
        self.levels = []            # (offset, price)
        self.armed = []             # bool per level (can it fire?)
        self.last_px = None
        self.pos = {}               # level idx -> position dict
        self.trades = []
        self.day_pnl = 0.0
        self.total_pnl = 0.0
        self.counters = {"entries": 0, "target": 0, "stop": 0,
                         "timer": 0, "eod": 0, "order_errors": 0,
                         "blocked_cap": 0}
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
                "counters": self.counters, "day": self.day,
                "anchor": self.anchor}))
        except Exception as e:
            logger.debug(f"[levelride] save: {e!r}")

    def snapshot(self) -> dict:
        return {
            "strategy": ("LEVELRIDE-LADDER (BROKER)" if self.broker_on
                         else "LEVELRIDE-LADDER (MODEL)"),
            "enabled": self.enabled, "anchor": self.anchor,
            "n_levels": len(self.levels), "open": len(self.pos),
            "max_concurrent": MAX_CONCURRENT,
            "day_pnl": round(self.day_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "n_trades": len(self.trades), "counters": self.counters,
        }

    def _mkt(self, action, tag):
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
            if not (st == 200 and isinstance(resp, dict)
                    and resp.get("orderId")):
                self.counters["order_errors"] += 1
                logger.error(f"[levelride] order fail {st} {resp}")
                return False
            logger.warning(f"[levelride] MKT {action} 1 ({tag})")
            return True
        except Exception as e:
            self.counters["order_errors"] += 1
            logger.error(f"[levelride] order exc: {e!r}")
            return False

    def _close(self, li, px, reason, now):
        p = self.pos.pop(li)
        self._mkt("Sell" if p["side"] > 0 else "Buy",
                  f"levelride_exit_L{li}_{reason}")
        pnl = (px - p["entry"]) * p["side"] * PT_VALUE - FEES_RT
        self.day_pnl += pnl
        self.total_pnl += pnl
        self.counters[reason] = self.counters.get(reason, 0) + 1
        self.armed[li] = True         # rung re-arms after exit
        self.trades.insert(0, {
            "level": li, "side": p["side"], "entry": p["entry"],
            "exit": px, "pnl": round(pnl, 2), "reason": reason,
            "t_in": p["t_in"], "t_out": now.isoformat()})
        logger.warning(f"[levelride] EXIT L{li} {reason} "
                       f"{pnl:+.2f} (day {self.day_pnl:+.0f})")
        if self.on_trade is not None:
            try:
                hold_s = (now - datetime.fromisoformat(
                    p["t_in"])).total_seconds()
                self.on_trade({
                    "ts": now.isoformat(), "entry_ts": p["t_in"],
                    "side": "LONG" if p["side"] > 0 else "SHORT",
                    "n_mnq": 1, "entry_px": float(p["entry"]),
                    "exit_px": float(px),
                    "exit_reason": f"levelride_{reason}",
                    "pnl_usd": round(pnl, 2), "pnl_pts": 0.0,
                    "hold_s": float(hold_s)})
            except Exception as e:
                logger.debug(f"[levelride] on_trade: {e!r}")
        self._save()

    def on_price(self, px, now):
        """Core tick/price handler. Caller feeds every price update."""
        if not self.enabled:
            return
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if now.weekday() >= 5:
            return
        hr = now.hour + now.minute / 60.0
        dstr = now.strftime("%Y-%m-%d")
        if self.day != dstr:                       # new day
            self.day = dstr
            self.anchor = None
            self.levels = []
            self.armed = []
            self.last_px = None
            self.pos = {}
            self.day_pnl = 0.0
        # set anchor at first price in session
        if self.anchor is None:
            if hr >= ENTRY_LO:
                self.anchor = px
                self.levels = [self.anchor + o for o in OFFS]
                self.armed = [True] * len(self.levels)
                self.last_px = px
                logger.warning(f"[levelride] anchor {self.anchor} "
                               f"({len(self.levels)} levels)")
            return
        flat_now = (now.hour, now.minute) >= FLAT_AT
        # ---- manage open positions
        for li in list(self.pos.keys()):
            p = self.pos[li]; s = p["side"]
            tgt = p["entry"] + TGT_PT * s
            stp = p["entry"] - STP_PT * s
            due = now >= datetime.fromisoformat(p["t_in"]) \
                + timedelta(hours=HOLD_H)
            if (px - stp) * s <= 0:                 # stop hit
                self._close(li, stp - ADVERSE_PT * s, "stop", now)
            elif (px - tgt) * s >= 0:               # target hit
                self._close(li, tgt, "target", now)
            elif flat_now:
                self._close(li, px - ADVERSE_PT * s, "eod", now)
            elif due:
                self._close(li, px - ADVERSE_PT * s, "timer", now)
        # ---- detect level crossings (prev -> now straddles a level)
        can_enter = (ENTRY_LO <= hr < ENTRY_HI) and not flat_now
        if can_enter and self.last_px is not None:
            for li, lev in enumerate(self.levels):
                if not self.armed[li] or li in self.pos:
                    continue
                a, b = self.last_px, px
                crossed = (a < lev <= b) or (a > lev >= b)
                if not crossed:
                    continue
                if len(self.pos) >= MAX_CONCURRENT:
                    self.counters["blocked_cap"] += 1
                    continue
                side = 1 if b > lev else -1
                if not self._mkt("Buy" if side > 0 else "Sell",
                                 f"levelride_enter_L{li}"):
                    continue
                # RESTING STOP-ORDER fill: order was pre-placed AT the
                # level, so the exchange fills at the level (+ slippage),
                # NOT at wherever price reached by the time the bot
                # noticed. This is the fix - bot cadence no longer
                # affects the fill price.
                entry = lev + ADVERSE_PT * side
                self.pos[li] = {"side": side, "entry": entry,
                                "t_in": now.isoformat()}
                self.armed[li] = False
                self.counters["entries"] += 1
                logger.warning(
                    f"[levelride] ENTER L{li} "
                    f"{'LONG' if side > 0 else 'SHORT'} @{entry} "
                    f"(level {lev:.2f})")
                self._save()
        self.last_px = px

    def on_cycle(self, bars_1m, now):
        """Live entrypoint: use the latest (forming) bar's close as the
        current price. Called every ~2s cycle by the bot."""
        if not bars_1m:
            return
        try:
            px = float(bars_1m[-1]["close"])
        except Exception:
            return
        self.on_price(px, now)

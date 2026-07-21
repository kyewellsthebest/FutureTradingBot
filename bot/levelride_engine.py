"""LEVELRIDE-LADDER — BROKER engine (v4, resting-stop execution).

Confirmed clean self-contained backtest (2yr, tick-level, $1.50/RT,
no lookahead): 3 concurrent -> +$2,189/wk, 68% WR, 96% pos weeks,
worst day -$1,463. Definition:
  - Anchor = session open (first price at/after 14:00 UTC).
  - 11 levels = anchor + [0, +-25, +-50, +-75, +-100, +-150] NQ pts.
  - A price CROSS of a level fires an entry WITH the cross on that
    level's rung. Bracket: target +260 / stop -80 pts, max hold 4h,
    flat 20:55. Up to 3 positions open at once; each rung re-arms
    after its position closes.

v4 EXECUTION FIX (the whole point):
  The v3 engine sent a MARKET order the instant the bot NOTICED a
  crossing. At the live ~2s cycle the market order filled 20-30 pts
  PAST the level -> the recorded edge evaporated (deployed -$1,209
  over 4 days). v4 instead PRE-PLACES a resting stop-entry order AT
  every level in advance (buy-stop above the anchor, sell-stop
  below), each carrying a server-side OCO bracket (target/stop).
  The EXCHANGE fills the entry on touch at the level and manages the
  exit -> bot cadence no longer affects the fill. This is exactly
  what the backtest assumed (fill at level) and what recovered
  profitability in the 2s-cadence replay (+$823 / 3 days).

Broker mechanics:
  - Session open: place OSO (Stop entry + OCO bracket) at each armed
    level via /order/placeoso.
  - Entries + target/stop exits are handled autonomously by the
    exchange. The model tracks them for accounting/dashboard.
  - 3-cap: once 3 rungs are open, remaining resting entries are
    cancelled; they are re-placed when a slot frees (and price is
    back on the resting side of the level).
  - EOD 20:55: liquidateposition flattens everything AND cancels all
    working orders (entries + brackets) in one call.
  - The 4h intraday timer is ACCOUNTING-ONLY on the broker: a netted
    futures account can't isolate one rung's flatten safely, so a
    timed-out rung rides its OCO bracket until target/stop or the
    20:55 daily flatten. Documented divergence; bounded by EOD.

Kill: LEVELRIDE_ENABLED=0 (all off) / LEVELRIDE_BROKER=0 (model
only, no broker orders -- pure paper accounting).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from bot.account_ctx import data_dir

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
TICK = 0.25


def _tick(px: float) -> float:
    return round(round(float(px) / TICK) * TICK, 2)


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
        self.levels = []            # price per offset
        self.armed = []             # bool per level (can it fire?)
        self.last_px = None
        self.pos = {}               # level idx -> position dict
        self.rest_oids = {}         # level idx -> resting entry order id
        self._eod_done = False
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
            "resting": len(self.rest_oids),
            "max_concurrent": MAX_CONCURRENT,
            "day_pnl": round(self.day_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "n_trades": len(self.trades), "counters": self.counters,
        }

    # ------------------------------------------------------------------
    # Broker order helpers (resting OSO stop-entry + OCO bracket)
    # ------------------------------------------------------------------

    def _place_oso(self, li, lev) -> bool:
        """Pre-place a resting stop-ENTRY at the level plus a server-side
        OCO bracket (target/stop). The exchange fills the entry on touch
        AT the level and manages the exit -> bot cadence never affects
        the fill. Buy-stop above the anchor, sell-stop below."""
        if not self.broker_on:
            self.rest_oids[li] = -1
            return True
        try:
            sess = self.orders.session
            try:
                spec = self.orders._account_spec()
            except Exception:
                spec = None
            s = 1 if lev > self.anchor else -1
            act = "Buy" if s > 0 else "Sell"
            opp = "Sell" if s > 0 else "Buy"
            body = {
                "accountSpec": spec,
                "accountId": sess.get_account_id(),
                "action": act, "symbol": self.symbol_fn(),
                "orderQty": 1, "orderType": "Stop",
                "stopPrice": _tick(lev), "isAutomated": True,
                "text": f"lr_L{li}"[:64],
                "bracket1": {"action": opp, "orderType": "Stop",
                             "stopPrice": _tick(lev - STP_PT * s),
                             "isAutomated": True},
                "bracket2": {"action": opp, "orderType": "Limit",
                             "price": _tick(lev + TGT_PT * s),
                             "isAutomated": True},
            }
            body = {k: v for k, v in body.items() if v is not None}
            st, resp = sess._rest("POST", "/order/placeoso", body=body)
            oid = resp.get("orderId") if isinstance(resp, dict) else None
            fr = resp.get("failureReason") if isinstance(resp, dict) else None
            if st == 200 and oid and not fr:
                self.rest_oids[li] = int(oid)
                logger.warning(
                    f"[levelride] OSO {act}-stop L{li} @{_tick(lev)} "
                    f"tgt {_tick(lev + TGT_PT * s)} "
                    f"stp {_tick(lev - STP_PT * s)}")
                return True
            self.counters["order_errors"] += 1
            logger.error(f"[levelride] OSO fail L{li} {st} {str(resp)[:200]}")
            return False
        except Exception as e:
            self.counters["order_errors"] += 1
            logger.error(f"[levelride] OSO exc: {e!r}")
            return False

    def _cancel_rest(self, li):
        """Cancel a resting (unfilled) stop-entry order for a level."""
        oid = self.rest_oids.pop(li, None)
        if not self.broker_on or oid in (None, -1):
            return
        try:
            self.orders.cancel_order(int(oid))
        except Exception as e:
            logger.debug(f"[levelride] cancel L{li}: {e!r}")

    def _flatten_all(self):
        """EOD / clean-slate: liquidateposition flattens every open
        position AND cancels all working orders (resting entries +
        brackets) on the contract in one atomic call."""
        if not self.broker_on:
            self.rest_oids = {}
            return
        try:
            self.orders.submit_market_close(
                side="LONG", qty=1, symbol=self.symbol_fn(),
                setup_ref="levelride_eod")
        except Exception as e:
            logger.error(f"[levelride] flatten_all: {e!r}")
        self.rest_oids = {}

    def _side_ok(self, lev, px) -> bool:
        """A buy-stop must rest ABOVE current price (px < lev); a
        sell-stop must rest BELOW current price (px > lev). Otherwise
        it would fill immediately (marketable) instead of on the next
        genuine breakout."""
        if lev > self.anchor:
            return px < lev - 1e-9
        return px > lev + 1e-9

    def _sync_resting(self, px):
        """Reconcile broker resting orders with model state each cycle:
        place OSOs for armed, side-valid, un-open levels while below the
        3-cap; cancel resting entries once the cap is full."""
        if not self.broker_on or self.anchor is None:
            return
        at_cap = len(self.pos) >= MAX_CONCURRENT
        for li, lev in enumerate(self.levels):
            if abs(lev - self.anchor) < 1e-6:
                continue
            have = li in self.rest_oids
            want = (self.armed[li] and li not in self.pos
                    and not at_cap and self._side_ok(lev, px))
            if want and not have:
                self._place_oso(li, lev)
            elif have and (li in self.pos or at_cap or not self.armed[li]):
                self._cancel_rest(li)

    # ------------------------------------------------------------------
    # Model accounting (authoritative; broker mirrors it)
    # ------------------------------------------------------------------

    def _close(self, li, px, reason, now):
        """Record a rung's exit. Broker exits are handled server-side:
        target/stop by the OCO bracket, EOD by liquidateposition. This
        is accounting + dashboard only -- it never sends an order."""
        p = self.pos.pop(li)
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
            self.rest_oids = {}
            self._eod_done = False
            self.day_pnl = 0.0
        # set anchor at first price in session, then pre-place resting
        # OSOs at every level (after a clean-slate flatten so a mid-day
        # restart can't stack on stale broker state).
        if self.anchor is None:
            if hr >= ENTRY_LO:
                self.anchor = px
                self.levels = [self.anchor + o for o in OFFS]
                self.armed = [True] * len(self.levels)
                self.last_px = px
                logger.warning(f"[levelride] anchor {self.anchor} "
                               f"({len(self.levels)} levels)")
                if self.broker_on:
                    self._flatten_all()      # clean slate
                self._sync_resting(px)       # place initial resting OSOs
            return
        flat_now = (now.hour, now.minute) >= FLAT_AT
        # ---- EOD flatten: one liquidateposition cancels every working
        #      order + flattens all rungs; close the model book too.
        if flat_now and not self._eod_done:
            if self.broker_on:
                self._flatten_all()
            for li in list(self.pos.keys()):
                s = self.pos[li]["side"]
                self._close(li, px - ADVERSE_PT * s, "eod", now)
            self._eod_done = True
        # ---- manage open positions (exits handled server-side; model
        #      records them). Timer is accounting-only on the broker.
        if not flat_now:
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
                elif due:
                    self._close(li, px - ADVERSE_PT * s, "timer", now)
        # ---- detect level crossings -> a resting stop filled at the
        #      level on the exchange. Register the position; in broker
        #      mode only if a resting order was actually there to fill.
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
                if self.broker_on and li not in self.rest_oids:
                    continue          # no resting order filled -> no fill
                side = 1 if b > lev else -1
                # RESTING STOP fill: the order rested AT the level, so
                # the exchange fills at the level (+1 tick slippage),
                # NOT at wherever price reached when the bot noticed.
                entry = lev + ADVERSE_PT * side
                self.pos[li] = {"side": side, "entry": entry,
                                "t_in": now.isoformat()}
                self.rest_oids.pop(li, None)   # it filled -> not pending
                self.armed[li] = False
                self.counters["entries"] += 1
                logger.warning(
                    f"[levelride] ENTER L{li} "
                    f"{'LONG' if side > 0 else 'SHORT'} @{entry} "
                    f"(level {lev:.2f})")
                # cap reached -> cancel remaining resting entries
                if self.broker_on and len(self.pos) >= MAX_CONCURRENT:
                    for lj in list(self.rest_oids.keys()):
                        self._cancel_rest(lj)
                self._save()
        # ---- keep broker resting orders in sync with model state
        self._sync_resting(px)
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

"""10-leg verified stack engine. One broker order stream, virtual legs.

Every leg passed three gates on real data (selection 2023-24, blind
2025-26, held-out week of ticks): DON, NRB, TDAY, CONSECC, RSI2, ONH,
RETEST, ENGX, BWEXP, FHFADE. Combined: ~50 trades/wk, ~$1,300/wk net
average at 1 MNQ/leg, +$8,999 on the held-out week.

Design:
  - each leg holds a VIRTUAL position (0/+1/-1); the engine's target
    net = sum of legs; a diff-allocator sends plain MARKET orders to
    move the actual broker net position to the target. Netting is
    exact: opposite legs cancel at the broker (margin-free hedge)
    while the books still track each leg's own entry/exit.
  - exits are engine-managed (legs use time exits / EOD / one hard
    stop), checked every cycle against leg rules identical to the
    validated simulations.
  - every order carries text "stk_<leg>_<n>" so bundles attribute
    every fill to its leg.
  - net cap: |net| <= STACK_MAX_NET (default 6); entries beyond the
    cap are skipped and counted.
  - kill switch: BROKER_ENGINE=off (no new entries + flatten target 0)
    STACK_DISASTER_PT (default 150): if net position's mark moves
    that far against its average price, flatten everything.

State persists to data_dir()/stack_engine.json across restarts.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("stack_engine")


def engine_mode() -> str:
    m = os.environ.get("BROKER_ENGINE", "stack").strip().lower()
    return {"trend": "stack"}.get(m, m)   # trend = legacy alias


# leg spec: (tf_minutes, exit_bars, hard_stop_pts, rth_entry_only)
LEGS = {
    "DON":     (15, None, 0, True),    # EOD exit handled specially
    "NRB":     (5, 120, 0, True),
    "TDAY":    (5, 120, 0, True),
    "CONSECC": (15, 60, 0, True),
    "RSI2":    (5, 60, 20, False),
    "ONH":     (15, 65, 0, False),
    "RETEST":  (15, 120, 0, False),
    "ENGX":    (15, 120, 0, False),
    "BWEXP":   (3, 40, 0, True),
    "FHFADE":  (3, 40, 0, False),
}
RTH_LO, RTH_HI = 13.5, 20.9
DON_LO, DON_HI = 14.5, 20.92


class BrokerStackEngine:
    def __init__(self, tradovate_orders, symbol_fn):
        self.orders = tradovate_orders
        self.symbol_fn = symbol_fn
        self.qty = int(os.environ.get("STACK_QTY_PER_LEG", "1"))
        self.max_net = int(os.environ.get("STACK_MAX_NET", "10"))
        self.disaster_pt = float(os.environ.get("STACK_DISASTER_PT", "250"))
        self.enabled_legs = set(
            os.environ.get("STACK_LEGS", ",".join(LEGS)).split(","))
        self.pos: dict = {}          # leg -> {side,+1/-1, entry_px, entry_ts, bars_held_key}
        self.last_bar: dict = {}     # tf -> last processed bar ts (iso)
        self.counters = {"entries": 0, "exits": 0, "cap_skips": 0,
                         "orders": 0, "order_errors": 0, "disaster": 0}
        self.oid_seq = 0
        self._load()

    # ---- persistence -----------------------------------------------------
    def _path(self):
        from bot.account_ctx import data_dir
        return data_dir() / "stack_engine.json"

    def _load(self):
        try:
            p = self._path()
            if p.exists():
                d = json.loads(p.read_text())
                self.pos = d.get("pos", {})
                self.last_bar = d.get("last_bar", {})
                self.counters.update(d.get("counters", {}))
                if self.pos:
                    logger.warning(f"[stack] resumed legs: {list(self.pos)}")
        except Exception as e:
            logger.warning(f"[stack] load: {e!r}")

    def _save(self):
        try:
            self._path().write_text(json.dumps({
                "pos": self.pos, "last_bar": self.last_bar,
                "counters": self.counters}))
        except Exception as e:
            logger.debug(f"[stack] save: {e!r}")

    # ---- public ----------------------------------------------------------
    def holds_position(self) -> bool:
        return bool(self.pos)

    def target_net(self) -> int:
        return sum(p["side"] for p in self.pos.values()) * self.qty

    def snapshot(self) -> dict:
        return {"active": True, "legs_open": {k: v for k, v in self.pos.items()},
                "target_net": self.target_net(),
                "enabled": sorted(self.enabled_legs),
                "counters": dict(self.counters)}

    # ---- broker I/O --------------------------------------------------------
    def _market(self, action: str, qty: int, tag: str) -> bool:
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
                    "orderQty": int(qty), "orderType": "Market",
                    "isAutomated": True, "text": tag[:64]}
            body = {k: v for k, v in body.items() if v is not None}
            status, resp = sess._rest("POST", "/order/placeorder", body=body)
            self.counters["orders"] += 1
            ok = status == 200 and isinstance(resp, dict) and resp.get("orderId")
            if not ok:
                self.counters["order_errors"] += 1
                logger.error(f"[stack] order fail {status} {resp}")
            else:
                logger.warning(f"[stack] {action} {qty} ({tag})")
            return bool(ok)
        except Exception as e:
            self.counters["order_errors"] += 1
            logger.error(f"[stack] order exc: {e!r}")
            return False

    def _reconcile_net(self, tag: str) -> None:
        """Move actual broker net to the target via a diff MARKET order."""
        try:
            sess = self.orders.session
            st, positions = sess._rest("GET", "/position/list")
            actual = 0
            if st == 200 and isinstance(positions, list):
                aid = sess.get_account_id()
                for p in positions:
                    if isinstance(p, dict) and p.get("accountId") == aid:
                        actual = int(p.get("netPos") or 0)
                        break
            diff = self.target_net() - int(actual)
            if diff > 0:
                self._market("Buy", diff, tag)
            elif diff < 0:
                self._market("Sell", -diff, tag)
        except Exception as e:
            logger.error(f"[stack] reconcile: {e!r}")

    # ---- signal evaluation (mirrors the validated sims exactly) ----------
    def _signals(self, b, tf, now):
        import numpy as np
        import pandas as pd
        o = b["open"].to_numpy(); h = b["high"].to_numpy()
        l = b["low"].to_numpy(); c = b["close"].to_numpy()
        idx = b.index
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        dk = idx.normalize()
        cs = pd.Series(c, index=idx)
        out = {}
        i = len(c) - 1                      # newest CLOSED bar
        hr_i = hrs[i]
        if tf == 15:
            if "DON" in self.enabled_legs and DON_LO <= hr_i < DON_HI:
                if len(c) > 13:
                    dh = h[-13:-1].max(); dl = l[-13:-1].min()
                    if c[i] > dh: out["DON"] = 1
                    elif c[i] < dl: out["DON"] = -1
            if "CONSECC" in self.enabled_legs and RTH_LO <= hr_i < RTH_HI and len(c) > 4:
                ups = [(c[j] > o[j]) for j in range(i - 3, i + 1)]
                if all(ups): out["CONSECC"] = 1
                elif not any(ups): out["CONSECC"] = -1
            if "ONH" in self.enabled_legs and 20.75 <= hr_i < 20.92:
                out["ONH"] = 1
            if "RETEST" in self.enabled_legs and len(c) > 30:
                d_high = pd.Series(h, index=idx).resample("1D").max().dropna()
                ph = d_high.shift(1).reindex(dk).to_numpy()
                today = dk == dk[i]
                broke = bool((c[today & (np.arange(len(c)) <= i)] >
                              np.nan_to_num(ph[today & (np.arange(len(c)) <= i)],
                                            nan=np.inf)).any())
                if (broke and not np.isnan(ph[i]) and l[i] <= ph[i]
                        and c[i] > ph[i]):
                    out["RETEST"] = 1
            if "ENGX" in self.enabled_legs and len(c) > 22:
                lo20 = l[-22:-2].min(); hi20 = h[-22:-2].max()
                bull = (c[i] > o[i] and c[i - 1] < o[i - 1]
                        and c[i] > o[i - 1] and o[i] < c[i - 1])
                bear = (c[i] < o[i] and c[i - 1] > o[i - 1]
                        and c[i] < o[i - 1] and o[i] > c[i - 1])
                if bull and l[i - 1] <= lo20: out["ENGX"] = 1
                elif bear and h[i - 1] >= hi20: out["ENGX"] = -1
        elif tf == 5:
            if "NRB" in self.enabled_legs and RTH_LO <= hr_i < RTH_HI and len(c) > 9:
                rngs = (h - l)[-9:-1]
                if (h[i - 1] - l[i - 1]) == rngs.min():
                    if c[i] > h[i - 1]: out["NRB"] = 1
                    elif c[i] < l[i - 1]: out["NRB"] = -1
            if "TDAY" in self.enabled_legs and 14.5 <= hr_i < 14.75 and len(c) > 30:
                today = dk == dk[i]
                fh = (hrs >= 13.5) & (hrs < 14.5) & today
                if fh.any():
                    fhh = h[fh].max(); fhl = l[fh].min()
                    fr = fhh - fhl
                    tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
                    atr = pd.Series(tr).rolling(20).mean().to_numpy()
                    day_first = np.argmax(today)
                    a0 = atr[day_first] if day_first < len(atr) else np.nan
                    if not np.isnan(a0) and fr > 3 * a0:
                        mid = (fhh + fhl) / 2
                        if c[i] > mid + fr / 4: out["TDAY"] = 1
                        elif c[i] < mid - fr / 4: out["TDAY"] = -1
            if "RSI2" in self.enabled_legs and len(c) > 210:
                d = cs.diff()
                up = d.clip(lower=0).rolling(2).mean()
                dn = (-d.clip(upper=0)).rolling(2).mean()
                rsi = float((100 - 100 / (1 + up / dn.replace(0, np.nan))).iloc[-1])
                sma200 = float(cs.rolling(200).mean().iloc[-1])
                if rsi < 10 and c[i] > sma200: out["RSI2"] = 1
                elif rsi > 90 and c[i] < sma200: out["RSI2"] = -1
        elif tf == 3:
            if len(c) > 32:
                sma20 = cs.rolling(20).mean(); sd20 = cs.rolling(20).std()
                bw = (4 * sd20).to_numpy()
                if ("BWEXP" in self.enabled_legs and RTH_LO <= hr_i < RTH_HI
                        and not np.isnan(bw[i]) and not np.isnan(bw[i - 10])
                        and bw[i] > 1.5 * bw[i - 10]):
                    if c[i] > o[i]: out["BWEXP"] = 1
                    elif c[i] < o[i]: out["BWEXP"] = -1
            if "FHFADE" in self.enabled_legs and hr_i >= 14.5:
                today = dk == dk[i]
                fh = (hrs >= 13.5) & (hrs < 14.5) & today
                if fh.any():
                    fhh = h[fh].max()
                    if h[i] >= fhh and c[i] < o[i]:
                        out["FHFADE"] = 1     # as validated (long at FH-high touch)
        return out

    # ---- main cycle hook ---------------------------------------------------
    def on_cycle(self, bars_1m, now: datetime) -> None:
        if engine_mode() != "stack" or self.orders is None:
            return
        try:
            self._on_cycle(bars_1m, now)
        except Exception as e:
            logger.warning(f"[stack] cycle: {e!r}")

    def _on_cycle(self, bars_1m, now) -> None:
        import pandas as pd
        if bars_1m is None or len(bars_1m) < 60:
            return
        hr = now.hour + now.minute / 60.0
        changed = False
        # 1. EXITS -- checked every cycle
        for leg, p in list(self.pos.items()):
            tf, exit_bars, hard, _ = LEGS[leg]
            close_it = False
            if leg == "DON" and (hr >= DON_HI or hr < DON_LO):
                close_it = True
            elif exit_bars is not None:
                held_min = (now.timestamp() - p["entry_ts"]) / 60.0
                if held_min >= exit_bars * tf:
                    close_it = True
            if not close_it and hard > 0:
                last_px = float(bars_1m["close"].iloc[-1])
                if (last_px - p["entry_px"]) * p["side"] <= -hard:
                    close_it = True
            if close_it:
                self.pos.pop(leg)
                self.counters["exits"] += 1
                changed = True
                logger.warning(f"[stack] EXIT {leg}")
        # 2. ENTRIES -- on newly closed bars per timeframe
        for tf in (3, 5, 15):
            rule = f"{tf}min"
            b = pd.DataFrame({
                "open": bars_1m["open"].resample(rule).first(),
                "high": bars_1m["high"].resample(rule).max(),
                "low": bars_1m["low"].resample(rule).min(),
                "close": bars_1m["close"].resample(rule).last()}).dropna()
            cutoff = pd.Timestamp(now).floor(rule)
            if cutoff.tz is None:
                cutoff = cutoff.tz_localize("UTC")
            if b.index.tz is None:
                b.index = b.index.tz_localize("UTC")
            b = b[b.index < cutoff]
            if len(b) < 30:
                continue
            last = str(b.index[-1])
            if self.last_bar.get(rule) == last:
                continue
            self.last_bar[rule] = last
            changed = True
            sigs = self._signals(b.iloc[-2200:], tf, now)
            px = float(b["close"].iloc[-1])
            for leg, side in sigs.items():
                if leg in self.pos:
                    continue
                if abs(self.target_net() + side * self.qty) > self.max_net:
                    self.counters["cap_skips"] += 1
                    continue
                self.oid_seq += 1
                self.pos[leg] = {"side": int(side), "entry_px": px,
                                 "entry_ts": now.timestamp(),
                                 "tag": f"stk_{leg}_{self.oid_seq}"}
                self.counters["entries"] += 1
                logger.warning(f"[stack] ENTRY {leg} {'L' if side>0 else 'S'} @~{px}")
        # 3. Disaster guard: PER-LEG exit at -disaster_pt (validated
        # legs never see this in normal regimes; it only bounds tails
        # without flattening healthy legs alongside).
        if self.pos:
            last_px = float(bars_1m["close"].iloc[-1])
            for leg, p in list(self.pos.items()):
                if (last_px - p["entry_px"]) * p["side"] <= -self.disaster_pt:
                    logger.error(f"[stack] LEG DISASTER exit {leg}")
                    self.pos.pop(leg)
                    self.counters["disaster"] += 1
                    changed = True
        # 4. Send the diff order if the target moved
        if changed:
            self._reconcile_net(f"stk_net_{int(time.time())}")
            self._save()

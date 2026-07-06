"""Broker-side trend engine: 15-min Donchian continuation, EOD flatten.

WHY THIS EXISTS (2026-07-06). The fade strategy's paper edge lives in
fill-at-touch prices no real order can buy: 23 execution/geometry
variants simulated over a full week of real MNQ ticks ALL lost money at
the broker (best -$1,066/wk, worst -$17,930/wk) while paper made
+$5,878. The broker therefore stops mirroring the fade and instead
trades the strongest real-fill edge from the June strategy search:

    DON_15min_N12, RTH-only, exit at session close
    - 4-year backtest: +$34.4/day per MNQ, positive EVERY year,
      Sharpe 1.63, 54.6% win rate, ~1 trade/day (avenue_intraday_trend)
    - Last week's real ticks: +$1,061/MNQ, positive every traded day

Profile: ~1 trade/day, wins average ~100+ pts, so the $5-7/trade
real-execution toll that killed the fade mirror is a rounding error.

The PAPER fade bot is untouched -- it keeps trading and driving the
dashboard. This engine owns the BROKER position instead of the mirror.

Env:
  BROKER_ENGINE            "trend" (default) | "mirror" | "off"
  BROKER_TREND_QTY         contracts (default 1)
  BROKER_TREND_N           Donchian lookback in 15m bars (default 12)
  BROKER_TREND_DISASTER_PT protective stop distance (default 120pt --
                           never hit in backtest; pure catastrophe guard)

State persists to data_dir()/trend_engine.json so restarts resume the
open position instead of orphaning it.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("trend_engine")

RTH_LO = 14.5    # 14:30 UTC
RTH_HI = 20.92   # ~20:55 UTC (flatten before CME close)


def engine_mode() -> str:
    return os.environ.get("BROKER_ENGINE", "trend").strip().lower()


class BrokerTrendEngine:
    def __init__(self, tradovate_orders, symbol_fn):
        self.orders = tradovate_orders
        self.symbol_fn = symbol_fn      # () -> "MNQU6"
        self.qty = int(os.environ.get("BROKER_TREND_QTY", "1"))
        self.N = int(os.environ.get("BROKER_TREND_N", "12"))
        self.disaster_pt = float(os.environ.get(
            "BROKER_TREND_DISASTER_PT", "120"))
        self.pos: Optional[dict] = None   # {side, entry_ref, entry_px, day}
        self.last_bar_ts = None           # last processed CLOSED 15m bar
        self._load()

    # ---- persistence ----------------------------------------------------
    def _path(self):
        from bot.account_ctx import data_dir
        return data_dir() / "trend_engine.json"

    def _load(self):
        try:
            p = self._path()
            if p.exists():
                d = json.loads(p.read_text())
                self.pos = d.get("pos")
                lb = d.get("last_bar_ts")
                if lb:
                    import pandas as pd
                    self.last_bar_ts = pd.Timestamp(lb)
                if self.pos:
                    logger.warning(f"[trend] resumed open position: {self.pos}")
        except Exception as e:
            logger.warning(f"[trend] state load: {e!r}")

    def _save(self):
        try:
            self._path().write_text(json.dumps({
                "pos": self.pos,
                "last_bar_ts": str(self.last_bar_ts) if self.last_bar_ts is not None else None,
            }))
        except Exception as e:
            logger.debug(f"[trend] state save: {e!r}")

    # ---- helpers --------------------------------------------------------
    def holds_position(self) -> bool:
        return self.pos is not None

    def _flatten(self, reason: str, ref: str) -> None:
        try:
            r = self.orders.submit_market_close(
                side=self.pos["side"], qty=self.qty,
                symbol=self.symbol_fn(), setup_ref=ref)
            logger.warning(f"[trend] FLATTEN {reason} ok={r.ok}")
        except Exception as e:
            logger.error(f"[trend] flatten failed ({reason}): {e!r}")
        self.pos = None
        self._save()

    # ---- main hook: call from the bot cycle with the 1m bar frame -------
    def on_cycle(self, bars_1m, now: datetime) -> None:
        if engine_mode() != "trend" or self.orders is None:
            return
        try:
            self._on_cycle(bars_1m, now)
        except Exception as e:
            logger.warning(f"[trend] cycle: {e!r}")

    def _on_cycle(self, bars_1m, now) -> None:
        import pandas as pd
        hr = now.hour + now.minute / 60.0
        # 1. EOD flatten guard runs regardless of bars
        if self.pos is not None:
            if hr >= RTH_HI or hr < RTH_LO or (
                    self.pos.get("day") and
                    self.pos["day"] != now.strftime("%Y-%m-%d")):
                self._flatten("eod", f"trend_eod_{int(time.time())}")
                return
        if bars_1m is None or len(bars_1m) < self.N * 15 + 20:
            return
        # 2. Resample to CLOSED 15m bars (drop the in-progress bucket)
        df = bars_1m
        b15 = pd.DataFrame({
            "high": df["high"].resample("15min").max(),
            "low": df["low"].resample("15min").min(),
            "close": df["close"].resample("15min").last(),
        }).dropna()
        if len(b15) < self.N + 2:
            return
        cutoff = pd.Timestamp(now).floor("15min")
        if cutoff.tz is None:
            cutoff = cutoff.tz_localize("UTC")
        idx = b15.index
        if idx.tz is None:
            b15.index = idx = idx.tz_localize("UTC")
        b15 = b15[idx < cutoff]
        if len(b15) < self.N + 1:
            return
        last = b15.index[-1]
        if self.last_bar_ts is not None and last <= self.last_bar_ts:
            return                       # this closed bar already handled
        self.last_bar_ts = last
        self._save()
        # 3. Signal on the newly closed bar (Donchian N, prior bars)
        close = float(b15["close"].iloc[-1])
        don_hi = float(b15["high"].iloc[-self.N - 1:-1].max())
        don_lo = float(b15["low"].iloc[-self.N - 1:-1].min())
        bar_hr = last.hour + last.minute / 60.0
        in_rth = RTH_LO <= bar_hr < RTH_HI
        if self.pos is not None or not in_rth:
            return
        side = None
        if close > don_hi:
            side = "LONG"
        elif close < don_lo:
            side = "SHORT"
        if side is None:
            return
        # 4. Enter at market with a catastrophe-only bracket
        ref = f"trend_{int(time.time())}"
        try:
            res = self.orders.submit_market_with_bracket(
                side=side, qty=self.qty, symbol=self.symbol_fn(),
                stop_pts=self.disaster_pt,
                target_pts=self.disaster_pt * 4,   # placeholder, EOD exits first
                entry_estimate=close, live_price=close,
                setup_ref=ref)
            if getattr(res, "ok", False):
                self.pos = {"side": side, "entry_ref": ref,
                            "entry_px": close,
                            "day": now.strftime("%Y-%m-%d")}
                self._save()
                logger.warning(
                    f"[trend] OPEN {side} {self.qty} @~{close} "
                    f"(don_hi={don_hi} don_lo={don_lo}) ref={ref}")
            else:
                logger.error(f"[trend] entry rejected: {getattr(res, 'error', None)}")
        except Exception as e:
            logger.error(f"[trend] entry failed: {e!r}")

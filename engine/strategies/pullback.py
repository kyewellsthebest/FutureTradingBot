"""Pullback Impulse strategy -- pure refactor of bot/pullback_strategy.py.

WHAT IT DOES: on each bar, check the last 4 bars. If close-vs-open net move
across the window is >= 5pt in either direction, the strategy is signalling
"a real impulse just happened." Place a LIMIT order at the 0.618 retrace
of the impulse range, with stop 6pt away and target 12pt away.

DESIGN CHANGES vs the old bot/pullback_strategy.py:
  - Pure function: takes bars + now + params, returns Setup or None
  - No state held in the strategy (live state lives in Runtime)
  - No global constants -- everything via `params` dict so the engine
    can A/B-test parameter variants without code edits
  - No side effects: no logging, no DB writes, no clock reads

PARAMETER NAMES match bot/account_ctx.py _DEFAULT_PARAMS exactly so we
can swap implementations without changing configs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from engine.strategies.base import Strategy
from engine.types import Setup, Side


# Defaults matching bot/account_ctx.py account "1" (legacy target=12 config).
DEFAULTS = {
    "IMPULSE_PTS":         5.0,
    "IMPULSE_WINDOW_BARS": 4,
    "PULLBACK_PCT":        0.618,
    "STOP_PTS":            6.0,
    "TARGET_PTS":          12.0,
}


class PullbackImpulse(Strategy):
    name = "pullback_impulse"

    def detect_setup(self, bars: pd.DataFrame, now: datetime,
                      params: dict) -> Optional[Setup]:
        p = {**DEFAULTS, **(params or {})}
        W      = int(p["IMPULSE_WINDOW_BARS"])
        IMP    = float(p["IMPULSE_PTS"])
        PCT    = float(p["PULLBACK_PCT"])
        STOP   = float(p["STOP_PTS"])
        TARGET = float(p["TARGET_PTS"])

        if bars is None or len(bars) < W:
            return None

        # WHAT THE LIVE CODE DOES (matches bot/pullback_strategy.py):
        # window = last W bars
        # net = window["close"].iloc[-1] - window["open"].iloc[0]
        window = bars.iloc[-W:]
        net = float(window["close"].iloc[-1]) - float(window["open"].iloc[0])
        if abs(net) < IMP:
            return None

        imp_high = float(window["high"].max())
        imp_low  = float(window["low"].min())
        rng = imp_high - imp_low
        if rng <= 0:
            return None

        side = Side.LONG if net > 0 else Side.SHORT
        if side is Side.LONG:
            entry_px = imp_high - rng * PCT
            stop_px  = entry_px - STOP
            tgt_px   = entry_px + TARGET
        else:
            entry_px = imp_low + rng * PCT
            stop_px  = entry_px + STOP
            tgt_px   = entry_px - TARGET

        return Setup(
            detected_at=now,
            side=side,
            entry_price=round(entry_px, 2),
            stop_price=round(stop_px, 2),
            target_price=round(tgt_px, 2),
            impulse_high=imp_high,
            impulse_low=imp_low,
            impulse_pts=round(net, 2),
            strategy_name=self.name,
            meta={
                "window_bars": W,
                "impulse_range": round(rng, 2),
                "pullback_pct": PCT,
            },
        )

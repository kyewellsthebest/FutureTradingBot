"""MarketContext bundles everything the FillModel + RiskEngine need to
know about CURRENT market state. Built fresh by the runtime each bar so
strategy / fill / risk don't have to share global state.

The point: the FillModel's slippage scales with vol regime; the RiskEngine
disables on news; the strategy is regime-agnostic. They all need slightly
different views of "what's going on right now," and putting them in one
dataclass keeps the call signatures clean.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

ET_OFFSET_HOURS = -4   # EDT; -5 during EST. Production should use proper tz.


@dataclass(frozen=True)
class MarketContext:
    now: datetime               # bar timestamp
    last_close: float
    atr_5: float                # 5-bar ATR (pt)
    atr_60: float               # 60-bar ATR (pt)
    bar_range_pts: float        # high - low of THIS bar
    et_hour: int                # 0-23
    is_us_rth: bool             # 09:30-16:00 ET
    is_us_open_15min: bool      # 09:30-09:45 ET, where spreads widen
    is_news_window: bool        # within ±30min of scheduled event
    is_overnight: bool          # outside US RTH

    @property
    def vol_ratio(self) -> float:
        """5-bar ATR / 60-bar ATR. >1 = expanding vol. <0.5 = contracting."""
        if self.atr_60 <= 0:
            return 1.0
        return self.atr_5 / self.atr_60

    @property
    def is_fast_market(self) -> bool:
        """Fast = vol expanding AND already high. Used by SimFillModel to
        boost touched-not-filled probability and stop slippage."""
        return self.vol_ratio > 1.5 and self.atr_5 > 3.0


def build_market_context(bars: pd.DataFrame, now: datetime,
                          news_calendar=None) -> MarketContext:
    """Compute MarketContext from the most recent bars. bars is the FULL
    history up to and including the current bar.

    news_calendar is an optional callable that returns True if `now` is
    within an event window. None = ignore news.
    """
    last = bars.iloc[-1]
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()

    def _atr(n):
        if len(c) < n + 1:
            return float(h[-1] - l[-1])
        hh = h[-(n+1):]
        ll = l[-(n+1):]
        cc = c[-(n+1):]
        prev_c = np.r_[cc[0], cc[:-1]]
        tr = np.maximum.reduce([hh - ll, np.abs(hh - prev_c), np.abs(ll - prev_c)])
        return float(tr[1:].mean())

    et = now + pd.Timedelta(hours=ET_OFFSET_HOURS)
    et_h = et.hour
    et_m = et.minute
    is_rth = (et_h == 9 and et_m >= 30) or (10 <= et_h <= 15) \
             or (et_h == 16 and et_m == 0)
    is_open = (et_h == 9 and et_m >= 30) or (et_h == 9 and et_m < 45)
    is_news = bool(news_calendar(now)) if news_calendar else False
    return MarketContext(
        now=now,
        last_close=float(last["close"]),
        atr_5=_atr(5),
        atr_60=_atr(60),
        bar_range_pts=float(last["high"]) - float(last["low"]),
        et_hour=et_h,
        is_us_rth=is_rth,
        is_us_open_15min=is_open,
        is_news_window=is_news,
        is_overnight=not is_rth,
    )

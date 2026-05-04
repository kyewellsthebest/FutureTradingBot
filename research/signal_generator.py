"""
Signal generators.

Each Signal subclass implements `.generate(intraday, daily) -> DataFrame`
returning columns: signal_time, signal_name, side, entry_px, target_hint.

`_attach_prev_day_levels` decorates the intraday frame with PDH / PDL / prev_close
columns (computed from the daily frame, joined by NY calendar date).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.indicators import (
    atr,
    bollinger_pct_b,
    eq50,
    session_vwap,
    sma,
    volume_ratio,
    zscore,
)

logger = logging.getLogger("signal_generator")
NY = "America/New_York"


# ---------------------------------------------------------------------------
# Helper: attach prior-day high / low / close to intraday bars
# ---------------------------------------------------------------------------

def _attach_prev_day_levels(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Attach previous DAY's daily H/L/C to each intraday bar.

    BUG FIX 2026-05-04: was using `tz_convert(NY).normalize()` to map daily
    bar timestamps to NY calendar dates — which shifted them by 4–5 hrs and
    aligned daily-bar UTC-midnight 2026-03-17 to NY date 2026-03-16. Then
    shift(1) made the "prev day" lookup for an intraday bar on UTC date
    2026-03-17 actually return the SAME-day's H/L/C (a future-data leak).

    Symptoms: ALL V3-family signals' edge inflated because their feature
    `dist_pdh_atr` / `dist_pdl_atr` was secretly comparing the bar's price
    to the SAME day's full-session H/L (which is unknown until after the
    session closes). A strategy that "fires when price is far below pdh"
    was actually firing when price was far below today's intraday peak —
    trivially profitable in hindsight, completely impossible live.

    Fix: index daily by its UTC trading date directly (no tz convert).
    Daily bar timestamped 2026-03-17 00:00 UTC represents the trading day
    spanning 2026-03-17 00:00–23:55 UTC. An intraday bar with any time on
    UTC date 2026-03-17 looks up the previous calendar UTC date, gets
    the 2026-03-16 daily bar — that's a strictly past quantity. Honest.
    """
    if intraday.empty or daily.empty:
        df = intraday.copy()
        df["pdh"] = np.nan
        df["pdl"] = np.nan
        df["prev_close"] = np.nan
        return df
    d = daily.copy()
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC")
    # Map each daily bar to its own UTC trading-date. shift(1) then gives
    # the strictly-prior trading day's OHLC.
    daily_dates = d.index.normalize()
    daily_by_date = pd.DataFrame({
        "high": d["high"].values,
        "low":  d["low"].values,
        "close": d["close"].values,
    }, index=daily_dates)
    daily_by_date = daily_by_date[~daily_by_date.index.duplicated(keep="last")]
    pdh = daily_by_date["high"].shift(1)
    pdl = daily_by_date["low"].shift(1)
    pc  = daily_by_date["close"].shift(1)

    intra = intraday.copy()
    if intra.index.tz is None:
        intra.index = intra.index.tz_localize("UTC")
    intra_dates = intra.index.normalize()
    intra["pdh"] = pdh.reindex(intra_dates).to_numpy()
    intra["pdl"] = pdl.reindex(intra_dates).to_numpy()
    intra["prev_close"] = pc.reindex(intra_dates).to_numpy()
    return intra


# ---------------------------------------------------------------------------
# Signal base
# ---------------------------------------------------------------------------

@dataclass
class _Hit:
    signal_time: pd.Timestamp
    signal_name: str
    side: str
    entry_px: float
    target_hint: float = float("nan")


class Signal:
    name: str = "BASE"

    def generate(self, intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError

    @staticmethod
    def _empty() -> pd.DataFrame:
        return pd.DataFrame(columns=["signal_time", "signal_name", "side",
                                     "entry_px", "target_hint"])


def _bullish_bar(df: pd.DataFrame) -> pd.Series:
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    return (df["close"] > df["open"]) & ((body / rng) > 0.5)


def _bearish_bar(df: pd.DataFrame) -> pd.Series:
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    return (df["close"] < df["open"]) & ((body / rng) > 0.5)


# ---------------------------------------------------------------------------
# Concrete signals
# ---------------------------------------------------------------------------

class PDLTouch(Signal):
    name = "PDL_TOUCH"

    def generate(self, intraday, daily):
        df = _attach_prev_day_levels(intraday, daily)
        vr = volume_ratio(df["volume"], 20)
        touched = (df["low"] <= df["pdl"] + 1.0) & (df["close"] > df["pdl"])
        bull = _bullish_bar(df)
        hi_vol = vr >= 1.2
        mask = touched & bull & hi_vol & df["pdl"].notna()
        return self._materialize(df, mask, "LONG")

    def _materialize(self, df, mask, side):
        if not mask.any():
            return self._empty()
        idx = df.index[mask]
        return pd.DataFrame({
            "signal_time": idx,
            "signal_name": self.name,
            "side": side,
            "entry_px": df.loc[idx, "close"].values,
            "target_hint": np.nan,
        })


class PDHTouch(Signal):
    name = "PDH_TOUCH"

    def generate(self, intraday, daily):
        df = _attach_prev_day_levels(intraday, daily)
        vr = volume_ratio(df["volume"], 20)
        touched = (df["high"] >= df["pdh"] - 1.0) & (df["close"] < df["pdh"])
        bear = _bearish_bar(df)
        mask = touched & bear & (vr >= 1.2) & df["pdh"].notna()
        if not mask.any():
            return self._empty()
        idx = df.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "SHORT",
            "entry_px": df.loc[idx, "close"].values, "target_hint": np.nan,
        })


class EQ50Long(Signal):
    name = "EQ50_LONG"

    def generate(self, intraday, daily):
        df = _attach_prev_day_levels(intraday, daily).copy()
        df["eq50"] = eq50(df["high"], df["low"], 50)
        below = (df["eq50"] - df["close"]) >= 40
        mask = below & _bullish_bar(df) & df["eq50"].notna()
        if not mask.any():
            return self._empty()
        idx = df.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "LONG",
            "entry_px": df.loc[idx, "close"].values, "target_hint": np.nan,
        })


class EQ50Short(Signal):
    name = "EQ50_SHORT"

    def generate(self, intraday, daily):
        df = _attach_prev_day_levels(intraday, daily).copy()
        df["eq50"] = eq50(df["high"], df["low"], 50)
        above = (df["close"] - df["eq50"]) >= 40
        mask = above & _bearish_bar(df) & df["eq50"].notna()
        if not mask.any():
            return self._empty()
        idx = df.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "SHORT",
            "entry_px": df.loc[idx, "close"].values, "target_hint": np.nan,
        })


class GapFillLong(Signal):
    name = "GAP_FILL_LONG"

    def generate(self, intraday, daily):
        df = _attach_prev_day_levels(intraday, daily)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        ny = df.index.tz_convert(NY)
        is_open_bar = (ny.hour == 9) & (ny.minute == 30)
        gap = df["open"] - df["prev_close"]
        mask = is_open_bar & (gap <= -20) & _bullish_bar(df)
        if not mask.any():
            return self._empty()
        idx = df.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "LONG",
            "entry_px": df.loc[idx, "close"].values,
            "target_hint": df.loc[idx, "prev_close"].values,
        })


class GapFillShort(Signal):
    name = "GAP_FILL_SHORT"

    def generate(self, intraday, daily):
        df = _attach_prev_day_levels(intraday, daily)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        ny = df.index.tz_convert(NY)
        is_open_bar = (ny.hour == 9) & (ny.minute == 30)
        gap = df["open"] - df["prev_close"]
        mask = is_open_bar & (gap >= 50) & _bearish_bar(df)
        if not mask.any():
            return self._empty()
        idx = df.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "SHORT",
            "entry_px": df.loc[idx, "close"].values,
            "target_hint": df.loc[idx, "prev_close"].values,
        })


class ZScoreLong(Signal):
    name = "ZSCORE_LONG"

    def generate(self, intraday, daily):
        z = zscore(intraday["close"], 20)
        was_below = z.shift(1) < -1.5
        crossed_up = z >= -1.5
        mask = was_below & crossed_up
        if not mask.any():
            return self._empty()
        idx = intraday.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "LONG",
            "entry_px": intraday.loc[idx, "close"].values, "target_hint": np.nan,
        })


class ZScoreShort(Signal):
    name = "ZSCORE_SHORT"

    def generate(self, intraday, daily):
        z = zscore(intraday["close"], 20)
        mask = (z.shift(1) > 1.5) & (z <= 1.5)
        if not mask.any():
            return self._empty()
        idx = intraday.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "SHORT",
            "entry_px": intraday.loc[idx, "close"].values, "target_hint": np.nan,
        })


class VolCompLong(Signal):
    name = "VOL_COMP_LONG"

    def generate(self, intraday, daily):
        vr = volume_ratio(intraday["volume"], 20)
        squeeze = (vr.shift(1) < 0.7) & (vr.shift(2) < 0.7)
        mask = squeeze & (vr >= 2.0) & _bullish_bar(intraday)
        if not mask.any():
            return self._empty()
        idx = intraday.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "LONG",
            "entry_px": intraday.loc[idx, "close"].values, "target_hint": np.nan,
        })


class VolCompShort(Signal):
    name = "VOL_COMP_SHORT"

    def generate(self, intraday, daily):
        vr = volume_ratio(intraday["volume"], 20)
        squeeze = (vr.shift(1) < 0.7) & (vr.shift(2) < 0.7)
        mask = squeeze & (vr >= 2.0) & _bearish_bar(intraday)
        if not mask.any():
            return self._empty()
        idx = intraday.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "SHORT",
            "entry_px": intraday.loc[idx, "close"].values, "target_hint": np.nan,
        })


class VWAPReclaimLong(Signal):
    name = "VWAP_RECLAIM_LONG"

    def generate(self, intraday, daily):
        try:
            vwap = session_vwap(intraday)
        except Exception:
            return self._empty()
        prev_below = intraday["close"].shift(1) < vwap.shift(1)
        now_above = intraday["close"] > vwap
        vr = volume_ratio(intraday["volume"], 20)
        mask = prev_below & now_above & (vr >= 1.3) & vwap.notna()
        if not mask.any():
            return self._empty()
        idx = intraday.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "LONG",
            "entry_px": intraday.loc[idx, "close"].values, "target_hint": np.nan,
        })


class VWAPRejectShort(Signal):
    name = "VWAP_REJECT_SHORT"

    def generate(self, intraday, daily):
        try:
            vwap = session_vwap(intraday)
        except Exception:
            return self._empty()
        prev_above = intraday["close"].shift(1) > vwap.shift(1)
        now_below = intraday["close"] < vwap
        vr = volume_ratio(intraday["volume"], 20)
        mask = prev_above & now_below & (vr >= 1.3) & vwap.notna()
        if not mask.any():
            return self._empty()
        idx = intraday.index[mask]
        return pd.DataFrame({
            "signal_time": idx, "signal_name": self.name, "side": "SHORT",
            "entry_px": intraday.loc[idx, "close"].values, "target_hint": np.nan,
        })


ALL_SIGNALS: list[Signal] = [
    PDLTouch(), PDHTouch(),
    EQ50Long(), EQ50Short(),
    GapFillLong(), GapFillShort(),
    ZScoreLong(), ZScoreShort(),
    VolCompLong(), VolCompShort(),
    VWAPReclaimLong(), VWAPRejectShort(),
]

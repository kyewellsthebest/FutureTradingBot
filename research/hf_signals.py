"""
High-frequency 1-minute signal candidates.

These are time-anchored, structure-anchored micro-patterns designed to
fire many times per day on 1-min NQ bars. Each one has a precisely-defined
mathematical entry condition (TRUE/FALSE per bar — no subjectivity), a
natural stop placement and a natural target.

Typical 1-min cost profile:
  stop  = 4-6 pts
  target = 6-15 pts
  hold  = 3-15 minutes

Each signal class follows the same protocol as research/signal_generator.py
so it slots straight into research/backtest_engine.py for validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.indicators import atr, ema, rsi, sma, session_vwap, volume_ratio


NY = "America/New_York"
EMPTY_COLS = ["signal_time", "signal_name", "side", "entry_px", "target_hint"]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=EMPTY_COLS)


def _emit(idx, name: str, side: str, entry: pd.Series, target: pd.Series | float = np.nan
          ) -> pd.DataFrame:
    if hasattr(target, "values") and not np.isscalar(target):
        target_vals = target.loc[idx].values
    else:
        target_vals = np.full(len(idx), float(target) if target == target else np.nan)
    return pd.DataFrame({
        "signal_time": idx,
        "signal_name": name,
        "side": side,
        "entry_px": entry.loc[idx].values,
        "target_hint": target_vals,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ny_minutes(idx: pd.DatetimeIndex) -> pd.Series:
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    ny = idx.tz_convert(NY)
    return pd.Series(ny.hour * 60 + ny.minute, index=idx)


def _bullish_bar(df: pd.DataFrame) -> pd.Series:
    body = (df["close"] - df["open"])
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    return (body > 0) & ((body / rng).abs() > 0.55)


def _bearish_bar(df: pd.DataFrame) -> pd.Series:
    body = (df["open"] - df["close"])
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    return (body > 0) & ((body / rng).abs() > 0.55)


# ---------------------------------------------------------------------------
# 1. TICK_REVERT — micro mean-reversion on extreme 3-bar moves
# ---------------------------------------------------------------------------

class TickRevertLong:
    name = "HF_TICK_REVERT_LONG"

    def generate(self, intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
        c = intraday["close"]
        # 3-bar drop of 8+ pts followed by a bullish bar
        drop3 = c - c.shift(3)
        atr14 = atr(intraday["high"], intraday["low"], c, 14).bfill()
        mask = (drop3 <= -8.0) & (drop3 <= -1.5 * atr14) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c, c.loc[idx] + 8.0)


class TickRevertShort:
    name = "HF_TICK_REVERT_SHORT"

    def generate(self, intraday, daily):
        c = intraday["close"]
        rise3 = c - c.shift(3)
        atr14 = atr(intraday["high"], intraday["low"], c, 14).bfill()
        mask = (rise3 >= 8.0) & (rise3 >= 1.5 * atr14) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c, c.loc[idx] - 8.0)


# ---------------------------------------------------------------------------
# 2. VOL_SPIKE_DIR — 3× avg volume + same direction close
# ---------------------------------------------------------------------------

class VolSpikeLong:
    name = "HF_VOL_SPIKE_LONG"

    def generate(self, intraday, daily):
        v = intraday["volume"]
        vr = volume_ratio(v, 60)
        mask = (vr >= 3.0) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", intraday["close"])


class VolSpikeShort:
    name = "HF_VOL_SPIKE_SHORT"

    def generate(self, intraday, daily):
        v = intraday["volume"]
        vr = volume_ratio(v, 60)
        mask = (vr >= 3.0) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", intraday["close"])


# ---------------------------------------------------------------------------
# 3. INSIDE_BREAK_VOL — 1-min inside bar breaks with vol expansion
# ---------------------------------------------------------------------------

class InsideBreakLong:
    name = "HF_INSIDE_BREAK_LONG"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        inside = (h < h.shift(1)) & (l > l.shift(1))
        # Current bar breaks above the *previous* outer bar's high
        outer_high = h.shift(1)
        breakout = c > outer_high
        vr = volume_ratio(intraday["volume"], 30)
        mask = inside.shift(1).fillna(False) & breakout & (vr >= 1.5)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class InsideBreakShort:
    name = "HF_INSIDE_BREAK_SHORT"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        inside = (h < h.shift(1)) & (l > l.shift(1))
        outer_low = l.shift(1)
        breakdown = c < outer_low
        vr = volume_ratio(intraday["volume"], 30)
        mask = inside.shift(1).fillna(False) & breakdown & (vr >= 1.5)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 4. RSI2_REVERSAL — RSI(2) extreme + counter-direction bar
# ---------------------------------------------------------------------------

class RSI2ReversalLong:
    name = "HF_RSI2_REV_LONG"

    def generate(self, intraday, daily):
        c = intraday["close"]
        r = rsi(c, 2)
        mask = (r.shift(1) < 5.0) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class RSI2ReversalShort:
    name = "HF_RSI2_REV_SHORT"

    def generate(self, intraday, daily):
        c = intraday["close"]
        r = rsi(c, 2)
        mask = (r.shift(1) > 95.0) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 5. ORB_5MIN — first 5 1-min bars define range, break either side
# ---------------------------------------------------------------------------

class ORB5MinLong:
    name = "HF_ORB5_LONG"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        # 9:30 - 9:34 NY
        ny_min = ny.hour * 60 + ny.minute
        in_open5 = (ny_min >= 570) & (ny_min < 575)
        # range = max(high) over open 5 bars per session
        df = intraday.copy()
        df["session"] = pd.Series(ny.date, index=df.index)
        df["in_open5"] = in_open5
        sess = df.groupby("session")
        # Compute 5-min open-range high per session
        orh = df["high"].where(df["in_open5"]).groupby(df["session"]).transform("max")
        breakout = df["close"] > orh
        # Only fire on the first breakout of the day (after 9:35 NY)
        df["after_open"] = (ny_min >= 575) & (ny_min < 600)
        mask = breakout & df["after_open"]
        # Limit to first hit per session
        first_hit = mask & ~mask.groupby(df["session"]).cumsum().shift(1).fillna(0).astype(bool)
        idx = df.index[first_hit.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", df["close"])


class ORB5MinShort:
    name = "HF_ORB5_SHORT"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_open5 = (ny_min >= 570) & (ny_min < 575)
        df = intraday.copy()
        df["session"] = pd.Series(ny.date, index=df.index)
        df["in_open5"] = in_open5
        orl = df["low"].where(df["in_open5"]).groupby(df["session"]).transform("min")
        breakdown = df["close"] < orl
        df["after_open"] = (ny_min >= 575) & (ny_min < 600)
        mask = breakdown & df["after_open"]
        first_hit = mask & ~mask.groupby(df["session"]).cumsum().shift(1).fillna(0).astype(bool)
        idx = df.index[first_hit.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", df["close"])


# ---------------------------------------------------------------------------
# 6. EMA_PULLBACK — 5/13 EMA-cross trend, enter on pullback to 5-EMA
# ---------------------------------------------------------------------------

class EMAPullbackLong:
    name = "HF_EMA_PULLBACK_LONG"

    def generate(self, intraday, daily):
        c = intraday["close"]
        e5 = ema(c, 5)
        e13 = ema(c, 13)
        e50 = ema(c, 50)
        # Trend: 5 > 13 > 50, pullback: low touched 5-EMA, then bullish bar above
        trend_up = (e5 > e13) & (e13 > e50)
        touched_5 = intraday["low"] <= e5
        mask = trend_up.shift(1).fillna(False) & touched_5.shift(1).fillna(False) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class EMAPullbackShort:
    name = "HF_EMA_PULLBACK_SHORT"

    def generate(self, intraday, daily):
        c = intraday["close"]
        e5 = ema(c, 5)
        e13 = ema(c, 13)
        e50 = ema(c, 50)
        trend_dn = (e5 < e13) & (e13 < e50)
        touched_5 = intraday["high"] >= e5
        mask = trend_dn.shift(1).fillna(False) & touched_5.shift(1).fillna(False) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 7. VWAP_CROSS_VOL — VWAP cross from below/above with volume
# ---------------------------------------------------------------------------

class VWAPCrossLong:
    name = "HF_VWAP_CROSS_LONG"

    def generate(self, intraday, daily):
        c = intraday["close"]
        vw = session_vwap(intraday).ffill()
        was_below = c.shift(1) < vw.shift(1)
        crossed = c > vw
        vr = volume_ratio(intraday["volume"], 30)
        mask = was_below & crossed & (vr >= 1.3) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class VWAPCrossShort:
    name = "HF_VWAP_CROSS_SHORT"

    def generate(self, intraday, daily):
        c = intraday["close"]
        vw = session_vwap(intraday).ffill()
        was_above = c.shift(1) > vw.shift(1)
        crossed = c < vw
        vr = volume_ratio(intraday["volume"], 30)
        mask = was_above & crossed & (vr >= 1.3) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 8. RANGE_COMPRESSION_BREAK — 5 small bars then expansion
# ---------------------------------------------------------------------------

class RangeCompressBreakLong:
    name = "HF_RANGE_BREAK_LONG"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        bar_range = (h - l)
        avg_range = bar_range.rolling(20).mean()
        compressed = (bar_range.rolling(5).max() < 0.6 * avg_range)
        breakout = c > h.rolling(5).max().shift(1)
        vr = volume_ratio(intraday["volume"], 30)
        mask = compressed.shift(1).fillna(False) & breakout & (vr >= 1.5)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class RangeCompressBreakShort:
    name = "HF_RANGE_BREAK_SHORT"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        bar_range = (h - l)
        avg_range = bar_range.rolling(20).mean()
        compressed = (bar_range.rolling(5).max() < 0.6 * avg_range)
        breakdown = c < l.rolling(5).min().shift(1)
        vr = volume_ratio(intraday["volume"], 30)
        mask = compressed.shift(1).fillna(False) & breakdown & (vr >= 1.5)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 9. LIQUIDITY_GRAB — wick beyond N-bar high/low then close back inside
# ---------------------------------------------------------------------------

class LiqGrabLong:
    name = "HF_LIQ_GRAB_LONG"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        prior_low = l.rolling(20).min().shift(1)
        wicked = l < prior_low
        closed_inside = c > prior_low
        mask = wicked & closed_inside & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class LiqGrabShort:
    name = "HF_LIQ_GRAB_SHORT"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        prior_high = h.rolling(20).max().shift(1)
        wicked = h > prior_high
        closed_inside = c < prior_high
        mask = wicked & closed_inside & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 10. POWER_HOUR_MOMO — 15:00-15:55 NY time, last-hour momentum
# ---------------------------------------------------------------------------

class PowerHourLong:
    name = "HF_POWER_HOUR_LONG"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_window = (ny_min >= 900) & (ny_min < 955)
        c = intraday["close"]
        e10 = ema(c, 10)
        # Closed > 10-EMA in last 5 bars consistently + bullish bar with volume
        above = (c > e10).rolling(5).sum() >= 4
        vr = volume_ratio(intraday["volume"], 30)
        mask = pd.Series(in_window, index=intraday.index) & above & _bullish_bar(intraday) & (vr >= 1.2)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class PowerHourShort:
    name = "HF_POWER_HOUR_SHORT"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_window = (ny_min >= 900) & (ny_min < 955)
        c = intraday["close"]
        e10 = ema(c, 10)
        below = (c < e10).rolling(5).sum() >= 4
        vr = volume_ratio(intraday["volume"], 30)
        mask = pd.Series(in_window, index=intraday.index) & below & _bearish_bar(intraday) & (vr >= 1.2)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 11. THREE_BAR_THRUST — 3 consecutive bars in same direction, no overlap
# ---------------------------------------------------------------------------

class ThreeBarThrustLong:
    name = "HF_3BAR_THRUST_LONG"

    def generate(self, intraday, daily):
        c, h, l = intraday["close"], intraday["high"], intraday["low"]
        b1 = (c > intraday["open"]) & (c > c.shift(1))
        b2 = b1.shift(1) & (h > h.shift(1)) & (l > l.shift(1))
        b3 = b2.shift(1) & (h > h.shift(1)) & (l > l.shift(1))
        mask = b1 & b2.shift(1).fillna(False) & b3.shift(2).fillna(False)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class ThreeBarThrustShort:
    name = "HF_3BAR_THRUST_SHORT"

    def generate(self, intraday, daily):
        c, h, l = intraday["close"], intraday["high"], intraday["low"]
        b1 = (c < intraday["open"]) & (c < c.shift(1))
        b2 = b1.shift(1) & (h < h.shift(1)) & (l < l.shift(1))
        b3 = b2.shift(1) & (h < h.shift(1)) & (l < l.shift(1))
        mask = b1 & b2.shift(1).fillna(False) & b3.shift(2).fillna(False)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 12. MORNING_REVERSION — 9:30-10:30 NY only, fade first 10-pt move
# ---------------------------------------------------------------------------

class MorningRevertLong:
    name = "HF_MORN_REVERT_LONG"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_window = (ny_min >= 570) & (ny_min < 630)
        c = intraday["close"]
        # Recent 5-min drop ≥ 8 pts, then bullish bar
        drop5 = c - c.shift(5)
        mask = pd.Series(in_window, index=intraday.index) & (drop5 <= -8.0) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class MorningRevertShort:
    name = "HF_MORN_REVERT_SHORT"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_window = (ny_min >= 570) & (ny_min < 630)
        c = intraday["close"]
        rise5 = c - c.shift(5)
        mask = pd.Series(in_window, index=intraday.index) & (rise5 >= 8.0) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 13. ATR_SPIKE_FADE — single bar moves > 2x recent ATR, fade
# ---------------------------------------------------------------------------

class ATRSpikeFadeLong:
    name = "HF_ATR_FADE_LONG"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        a = atr(h, l, c, 14)
        bar_move = c - intraday["open"]
        mask = (bar_move <= -2.0 * a) & (a > 1.5)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class ATRSpikeFadeShort:
    name = "HF_ATR_FADE_SHORT"

    def generate(self, intraday, daily):
        h, l, c = intraday["high"], intraday["low"], intraday["close"]
        a = atr(h, l, c, 14)
        bar_move = c - intraday["open"]
        mask = (bar_move >= 2.0 * a) & (a > 1.5)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# 14. BB_TOUCH_REVERT — Bollinger 2σ touch, close back inside
# ---------------------------------------------------------------------------

class BBRevertLong:
    name = "HF_BB_REVERT_LONG"

    def generate(self, intraday, daily):
        c = intraday["close"]
        ma = c.rolling(20).mean()
        sd = c.rolling(20).std(ddof=0)
        lower = ma - 2 * sd
        # Low touched lower band and close above lower band, bullish bar
        mask = (intraday["low"] <= lower) & (c > lower) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c, ma)


class BBRevertShort:
    name = "HF_BB_REVERT_SHORT"

    def generate(self, intraday, daily):
        c = intraday["close"]
        ma = c.rolling(20).mean()
        sd = c.rolling(20).std(ddof=0)
        upper = ma + 2 * sd
        mask = (intraday["high"] >= upper) & (c < upper) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c, ma)


# ---------------------------------------------------------------------------
# 15. NY_LUNCH_FADE — fade ranges during NY lunch (12-13 NY)
# ---------------------------------------------------------------------------

class NYLunchFadeLong:
    name = "HF_LUNCH_FADE_LONG"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_window = (ny_min >= 720) & (ny_min < 780)
        c = intraday["close"]
        # 10-bar low + bullish bar
        prior_low = intraday["low"].rolling(10).min().shift(1)
        mask = pd.Series(in_window, index=intraday.index) & (intraday["low"] <= prior_low) & _bullish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "LONG", c)


class NYLunchFadeShort:
    name = "HF_LUNCH_FADE_SHORT"

    def generate(self, intraday, daily):
        if intraday.index.tz is None:
            intraday = intraday.tz_localize("UTC")
        ny = intraday.index.tz_convert(NY)
        ny_min = ny.hour * 60 + ny.minute
        in_window = (ny_min >= 720) & (ny_min < 780)
        c = intraday["close"]
        prior_high = intraday["high"].rolling(10).max().shift(1)
        mask = pd.Series(in_window, index=intraday.index) & (intraday["high"] >= prior_high) & _bearish_bar(intraday)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty()
        return _emit(idx, self.name, "SHORT", c)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_HF_SIGNALS = [
    TickRevertLong(), TickRevertShort(),
    VolSpikeLong(), VolSpikeShort(),
    InsideBreakLong(), InsideBreakShort(),
    RSI2ReversalLong(), RSI2ReversalShort(),
    ORB5MinLong(), ORB5MinShort(),
    EMAPullbackLong(), EMAPullbackShort(),
    VWAPCrossLong(), VWAPCrossShort(),
    RangeCompressBreakLong(), RangeCompressBreakShort(),
    LiqGrabLong(), LiqGrabShort(),
    PowerHourLong(), PowerHourShort(),
    ThreeBarThrustLong(), ThreeBarThrustShort(),
    MorningRevertLong(), MorningRevertShort(),
    ATRSpikeFadeLong(), ATRSpikeFadeShort(),
    BBRevertLong(), BBRevertShort(),
    NYLunchFadeLong(), NYLunchFadeShort(),
]

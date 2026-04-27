"""
Vectorised technical indicators on pandas DataFrames.

Convention: every function takes a DataFrame with at least the columns it needs
(open, high, low, close, volume) and returns a Series aligned to the input index.
No look-ahead: every value at time t uses only data up to and including t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


# ---------------------------------------------------------------------------
# Momentum & oscillators
# ---------------------------------------------------------------------------

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    dn = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    roll_dn = dn.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = roll_up / roll_dn.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    sig = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - sig
    return macd_line, sig, hist


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    ll = low.rolling(n, min_periods=n).min()
    hh = high.rolling(n, min_periods=n).max()
    k = 100.0 * (close - ll) / (hh - ll).replace(0.0, np.nan)
    d = k.rolling(3, min_periods=3).mean()
    return k, d


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    return -100.0 * (hh - close) / (hh - ll).replace(0.0, np.nan)


def cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20) -> pd.Series:
    tp = (high + low + close) / 3.0
    ma = tp.rolling(n, min_periods=n).mean()
    md = (tp - ma).abs().rolling(n, min_periods=n).mean()
    return (tp - ma) / (0.015 * md.replace(0.0, np.nan))


def roc(close: pd.Series, n: int) -> pd.Series:
    return 100.0 * (close / close.shift(n) - 1.0)


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    return pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return true_range(high, low, close).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def bollinger_pct_b(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    """%B = position within bands (0 = lower band, 1 = upper band)."""
    ma = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper = ma + k * sd
    lower = ma - k * sd
    return (close - lower) / (upper - lower).replace(0.0, np.nan)


def zscore(close: pd.Series, n: int = 20) -> pd.Series:
    ma = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return (close - ma) / sd.replace(0.0, np.nan)


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def volume_ratio(volume: pd.Series, n: int = 20) -> pd.Series:
    avg = volume.rolling(n, min_periods=n).mean()
    return volume / avg.replace(0.0, np.nan)


# ---------------------------------------------------------------------------
# Market structure helpers
# ---------------------------------------------------------------------------

def eq50(high: pd.Series, low: pd.Series, n: int = 50) -> pd.Series:
    """Midpoint of the rolling n-bar high/low range."""
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    return (hh + ll) / 2.0


def price_position_in_range(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 50) -> pd.Series:
    """0.0 = at n-bar low, 1.0 = at n-bar high."""
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    return (close - ll) / (hh - ll).replace(0.0, np.nan)


# ---------------------------------------------------------------------------
# VWAP (session-level, computed per RTH day)
# ---------------------------------------------------------------------------

def session_vwap(df: pd.DataFrame, tz: str = "America/New_York",
                 rth_start_min: int = 570, rth_end_min: int = 960) -> pd.Series:
    """
    Compute intra-session VWAP for each RTH day.

    RTH default: 9:30 (570 min) to 16:00 (960 min) Eastern.
    Returns a Series aligned to df.index with NaN outside RTH.
    """
    ny = df.index.tz_convert(tz)
    ny_dates = ny.date
    ny_min = ny.hour * 60 + ny.minute
    rth_mask = (ny_min >= rth_start_min) & (ny_min < rth_end_min)

    vwap = pd.Series(np.nan, index=df.index, dtype=float)
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()

    unique_dates = pd.unique(ny_dates)
    for d in unique_dates:
        day_mask = (ny_dates == d) & rth_mask
        idxs = np.where(day_mask)[0]
        if len(idxs) < 2:
            continue
        cum_vol = np.cumsum(volume[idxs])
        cum_pv = np.cumsum(close[idxs] * volume[idxs])
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)
        vwap.iloc[idxs] = v

    return vwap

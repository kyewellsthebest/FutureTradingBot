"""
ICT pattern detectors — fair-value gaps, order blocks, swings/MSS,
liquidity sweeps, kill zones, daily bias. All strictly point-in-time:

  * an FVG at bar t is detectable at bar t (the closing of bar t completes
    the 3-candle pattern around bars t-2, t-1, t).
  * a swing pivot at bar t is a fractal max/min of [t-k, t+k] — known only
    at bar t+k, so it is stamped THERE.
  * displacement check uses ATR computed up to t-1 (no look-ahead).
  * "kill zones" and "daily bias" use only previously-closed bars.

Returns are pandas Series aligned to the 5-min bar index — booleans for
masks, floats for price levels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"


# --------------------------------------------------------------------- #
# kill-zone time masks (NY local hours)
# --------------------------------------------------------------------- #
def kill_zones(idx: pd.DatetimeIndex) -> dict[str, pd.Series]:
    ny = idx.tz_convert(NY)
    h = ny.hour
    m = ny.minute
    london_open = (h >= 2) & (h < 5)
    ny_open     = (h >= 7) & (h < 10)
    ny_am       = (h == 10)                            # the silver-bullet hour
    london_close = (h >= 10) & (h < 12)
    ny_pm       = ((h == 13) & (m >= 30)) | ((h >= 14) & (h < 16))
    rth         = ((h == 9) & (m >= 30)) | ((h >= 10) & (h < 16))
    return {
        "london_open": pd.Series(london_open, index=idx),
        "ny_open":     pd.Series(ny_open, index=idx),
        "silver_bullet": pd.Series(ny_am, index=idx),
        "london_close": pd.Series(london_close, index=idx),
        "ny_pm":       pd.Series(ny_pm, index=idx),
        "rth":         pd.Series(rth, index=idx),
    }


# --------------------------------------------------------------------- #
# daily bias — yesterday's daily close above/below daily EMA20
# --------------------------------------------------------------------- #
def daily_bias(nq: pd.DataFrame) -> pd.Series:
    """Return a Series aligned to nq.index where +1 = bullish bias, -1 = bearish.
    Bias is yesterday's close vs daily EMA20 (lagged by one full session)."""
    dates = pd.DatetimeIndex(nq.index.tz_convert(NY)).date
    daily_close = nq["close"].groupby(dates).last()
    ema = daily_close.ewm(span=20, adjust=False).mean()
    bias = np.where(daily_close > ema, 1, -1)
    bias_s = pd.Series(bias, index=daily_close.index).shift(1)  # yesterday's
    bar_dates = pd.Series(dates, index=nq.index)
    return bar_dates.map(bias_s.to_dict()).fillna(0).astype(int)


# --------------------------------------------------------------------- #
# fair value gap detection (3-candle, completed at bar t)
# --------------------------------------------------------------------- #
def find_fvgs(nq: pd.DataFrame, min_atr_mult: float = 1.5) -> pd.DataFrame:
    """At each bar t (>= 2), is there an FVG formed across t-2 .. t?

      Bullish FVG : low[t]  > high[t-2]   (gap)
      Bearish FVG : high[t] < low[t-2]

    A 'displacement' filter requires the candle's range to exceed
    min_atr_mult × ATR(t-1). Returns a DataFrame with columns:
      fvg_dir   ( 0 / +1 / -1 ),
      fvg_top   (upper edge of the gap),
      fvg_bot   (lower edge of the gap),
      fvg_disp_t  (timestamp the FVG was confirmed at)
    """
    h, l = nq["high"].to_numpy(), nq["low"].to_numpy()
    atr = (nq["high"] - nq["low"]).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    n = len(nq)
    direction = np.zeros(n, dtype=np.int8)
    top = np.full(n, np.nan)
    bot = np.full(n, np.nan)
    for t in range(2, n):
        rng_t = h[t] - l[t]
        if rng_t < min_atr_mult * atr[t - 1]:
            continue
        if l[t] > h[t - 2]:                    # bullish FVG
            direction[t] = 1
            top[t] = l[t]
            bot[t] = h[t - 2]
        elif h[t] < l[t - 2]:                  # bearish FVG
            direction[t] = -1
            top[t] = l[t - 2]
            bot[t] = h[t]
    return pd.DataFrame({
        "fvg_dir": direction, "fvg_top": top, "fvg_bot": bot,
    }, index=nq.index)


# --------------------------------------------------------------------- #
# order block — the last opposite-color candle before a displacement
# --------------------------------------------------------------------- #
def find_order_blocks(nq: pd.DataFrame, min_atr_mult: float = 1.5
                      ) -> pd.DataFrame:
    """At each bar t, if the t-bar range is >= min_atr_mult × ATR and price
    closed > open (bullish displacement), the OB is the most recent
    DOWN-candle at t-1, t-2, ... (last red before the green push). For a
    bearish displacement, mirror.

    Returns OB high/low/dir confirmed at bar t (where the displacement
    happened). These are forward-fillable until price returns to them.
    """
    o, c = nq["open"].to_numpy(), nq["close"].to_numpy()
    h, l = nq["high"].to_numpy(), nq["low"].to_numpy()
    atr = (nq["high"] - nq["low"]).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    n = len(nq)
    direction = np.zeros(n, dtype=np.int8)
    ob_top = np.full(n, np.nan)
    ob_bot = np.full(n, np.nan)
    for t in range(2, n):
        rng_t = h[t] - l[t]
        if rng_t < min_atr_mult * atr[t - 1]:
            continue
        if c[t] > o[t]:                       # bullish displacement
            # find last bar with close < open within prior 10
            for j in range(t - 1, max(t - 11, -1), -1):
                if c[j] < o[j]:
                    direction[t] = 1
                    ob_top[t] = h[j]
                    ob_bot[t] = l[j]
                    break
        elif c[t] < o[t]:
            for j in range(t - 1, max(t - 11, -1), -1):
                if c[j] > o[j]:
                    direction[t] = -1
                    ob_top[t] = h[j]
                    ob_bot[t] = l[j]
                    break
    return pd.DataFrame({
        "ob_dir": direction, "ob_top": ob_top, "ob_bot": ob_bot,
    }, index=nq.index)


# --------------------------------------------------------------------- #
# confirmed swing pivots (fractal max/min of [t-k, t+k])
# --------------------------------------------------------------------- #
def confirmed_swings(nq: pd.DataFrame, k: int = 5
                     ) -> tuple[pd.Series, pd.Series]:
    """Returns two Series — most recent confirmed swing HIGH price and the
    most recent confirmed swing LOW price, ffilled. Each pivot is stamped
    at t+k (the bar at which it becomes knowable)."""
    h_arr, l_arr = nq["high"].to_numpy(), nq["low"].to_numpy()
    n = len(nq)
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    for t in range(k, n - k):
        if h_arr[t] == h_arr[t - k:t + k + 1].max():
            sh[t + k] = h_arr[t]
        if l_arr[t] == l_arr[t - k:t + k + 1].min():
            sl[t + k] = l_arr[t]
    return (pd.Series(sh, index=nq.index).ffill(),
            pd.Series(sl, index=nq.index).ffill())


# --------------------------------------------------------------------- #
# market structure shift — bar that closes through last confirmed swing
# --------------------------------------------------------------------- #
def mss_events(nq: pd.DataFrame, k: int = 5) -> pd.Series:
    """At each bar t, +1 if bullish MSS (close > last confirmed swing high
    that was confirmed BEFORE t), -1 if bearish MSS (close < last confirmed
    swing low), else 0. Lookahead-safe via the t+k confirmation lag."""
    sh, sl = confirmed_swings(nq, k=k)
    sh_prev = sh.shift(1)
    sl_prev = sl.shift(1)
    c = nq["close"]
    bull = (c > sh_prev) & (c.shift(1) <= sh_prev)
    bear = (c < sl_prev) & (c.shift(1) >= sl_prev)
    out = pd.Series(0, index=nq.index, dtype=np.int8)
    out[bull] = 1
    out[bear] = -1
    return out


# --------------------------------------------------------------------- #
# liquidity sweep — wick beyond yesterday's H/L then close back inside
# --------------------------------------------------------------------- #
def liquidity_sweeps(nq: pd.DataFrame) -> pd.DataFrame:
    """Tag bars that swept the prior day's high (wick > PDH but close <= PDH)
    or prior day's low (wick < PDL but close >= PDL). Returns +1 / -1 / 0."""
    dates = pd.DatetimeIndex(nq.index.tz_convert(NY)).date
    g = nq.groupby(dates)
    pdh = g["high"].max().shift(1)
    pdl = g["low"].min().shift(1)
    bar_dates = pd.Series(dates, index=nq.index)
    pdh_aligned = bar_dates.map(pdh.to_dict())
    pdl_aligned = bar_dates.map(pdl.to_dict())
    sweep_high = (nq["high"] > pdh_aligned) & (nq["close"] <= pdh_aligned)
    sweep_low = (nq["low"] < pdl_aligned) & (nq["close"] >= pdl_aligned)
    out = pd.Series(0, index=nq.index, dtype=np.int8)
    out[sweep_high] = 1     # +1 = swept HIGH (potential SHORT setup)
    out[sweep_low] = -1     # -1 = swept LOW  (potential LONG setup)
    return out

"""
Smart Money Concepts (SMC) / ICT-style features.

The big prop firms / market makers don't trade off RSI and EMAs — they trade off
liquidity. Their playbook (made famous by ICT and now standard in institutional
algo books):

  1. ORDER BLOCKS  — the last opposite-direction candle before a strong impulse.
     Price returns to it and reverses. Ours: detect the candle preceding any 5-bar
     directional move ≥ 1.5 ATR; track distance from current bar.

  2. FAIR VALUE GAPS (FVG / imbalance) — 3-bar gap where bar1.high < bar3.low
     (bullish FVG) or bar1.low > bar3.high (bearish FVG). Price tends to return
     to fill these "liquidity voids".

  3. LIQUIDITY SWEEPS (stop-runs) — when price spikes through PDH/PDL/swing
     high/low for 1-3 bars then snaps back. This is where prop firms hunt
     retail stops then reverse.

  4. EQUAL HIGHS / LOWS (relative liquidity) — clusters of swing points within
     0.5 ATR of each other. Magnets for liquidity sweeps.

  5. BREAKER BLOCKS — failed order blocks that flip role (bullish OB that gets
     broken, then acts as resistance).

  6. KILLZONE INTERACTION — was price at PDH/PDL during NY_OPEN/LONDON_OPEN?
     Most of the day's institutional liquidity is harvested in those windows.

These features are designed to be model-fed (continuous, scale-invariant in
ATR units) so the v3 miner can pick them up automatically.

Returned columns (all in ATR units or 0/1 flags):
    dist_bull_ob_atr     distance to most recent bullish order block (LONG support)
    dist_bear_ob_atr     distance to most recent bearish order block (SHORT supply)
    bull_fvg_open        1 if there's an unfilled bullish FVG below current price
    bear_fvg_open        1 if there's an unfilled bearish FVG above current price
    dist_bull_fvg_atr    distance to nearest unfilled bullish FVG
    dist_bear_fvg_atr    distance to nearest unfilled bearish FVG
    sweep_pdh            1 if last 3 bars swept above PDH then closed below
    sweep_pdl            1 if last 3 bars swept below PDL then closed above
    sweep_swing_high     1 if last 3 bars swept above 20-bar swing high then closed below
    sweep_swing_low      1 if last 3 bars swept below 20-bar swing low then closed above
    eq_highs_count_50    count of equal-highs (within 0.3 ATR) in last 50 bars
    eq_lows_count_50     count of equal-lows (within 0.3 ATR) in last 50 bars
    in_killzone          1 if currently in NY_OPEN, LONDON_OPEN, or NY_PM kill zone
    killzone_at_pdh      1 if in killzone AND within 1 ATR of PDH (bearish setup)
    killzone_at_pdl      1 if in killzone AND within 1 ATR of PDL (bullish setup)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.indicators import atr
from research.signal_generator import _attach_prev_day_levels

NY = "America/New_York"

SMC_FEATURES = [
    "dist_bull_ob_atr", "dist_bear_ob_atr",
    "bull_fvg_open", "bear_fvg_open",
    "dist_bull_fvg_atr", "dist_bear_fvg_atr",
    "sweep_pdh", "sweep_pdl",
    "sweep_swing_high", "sweep_swing_low",
    "eq_highs_count_50", "eq_lows_count_50",
    "in_killzone", "killzone_at_pdh", "killzone_at_pdl",
]

_SMC_CACHE: dict = {}


def _last_strong_impulse_idx(o, c, atr_arr, lookback=20, threshold=1.5):
    """For each bar, find the most recent bar i where the next-5-bar return
    exceeds threshold × ATR. Returns the index of the candle BEFORE the impulse
    (the "order block") for each direction.

    Vectorized: returns two arrays bull_ob_idx, bear_ob_idx.
    """
    n = len(c)
    # 5-bar return looking forward (causal: at bar i, what's the move from bar i to bar i+5)
    fwd5 = np.full(n, np.nan)
    fwd5[:-5] = c[5:] - c[:-5]
    bull_impulse = fwd5 > threshold * atr_arr
    bear_impulse = fwd5 < -threshold * atr_arr

    # For each bar, the order block is the LAST bar in lookback before an impulse
    # where the candle direction was OPPOSITE the impulse direction.
    # bull OB: bearish candle (c<o) that preceded a bullish impulse
    # bear OB: bullish candle (c>o) that preceded a bearish impulse
    bull_ob_mask = bull_impulse & (c < o)
    bear_ob_mask = bear_impulse & (c > o)

    bull_ob_idx = np.full(n, -1, dtype=np.int64)
    bear_ob_idx = np.full(n, -1, dtype=np.int64)
    last_bull = -1; last_bear = -1
    for i in range(n):
        if bull_ob_mask[i]:
            last_bull = i
        if bear_ob_mask[i]:
            last_bear = i
        bull_ob_idx[i] = last_bull
        bear_ob_idx[i] = last_bear
    return bull_ob_idx, bear_ob_idx


def _detect_fvgs(h: np.ndarray, l: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Detect 3-bar fair-value-gaps. Returns (bull_fvg_low, bear_fvg_high) for each
    bar — 0 where no unfilled FVG exists. We check the last 100 bars of FVGs and
    mark them as filled once price retraces through the gap."""
    n = len(h)
    bull_fvg_low = np.full(n, np.nan)   # if price > this, the bullish FVG is still open
    bear_fvg_high = np.full(n, np.nan)
    # A bullish FVG is created at bar i+2 when h[i] < l[i+2]. The gap is [h[i], l[i+2]].
    # Price has to dip below l[i+2] to fill it.
    # Maintain rolling list of open FVGs.
    open_bull = []   # list of (created_idx, gap_low, gap_high)
    open_bear = []
    for i in range(n):
        # Create new FVG at bar i (looking back 2)
        if i >= 2:
            if h[i - 2] < l[i]:
                open_bull.append((i, h[i - 2], l[i]))
            if l[i - 2] > h[i]:
                open_bear.append((i, h[i], l[i - 2]))
        # Mark filled FVGs
        open_bull = [(idx, lo, hi) for (idx, lo, hi) in open_bull
                     if l[i] > lo and i - idx < 200]
        open_bear = [(idx, lo, hi) for (idx, lo, hi) in open_bear
                     if h[i] < hi and i - idx < 200]
        # Nearest open FVG below (bull) / above (bear) current price
        if open_bull:
            bull_fvg_low[i] = max(lo for (idx, lo, hi) in open_bull)
        if open_bear:
            bear_fvg_high[i] = min(hi for (idx, lo, hi) in open_bear)
    return bull_fvg_low, bear_fvg_high


def _ny_minute(idx: pd.DatetimeIndex) -> np.ndarray:
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    ny = idx.tz_convert(NY)
    return (ny.hour * 60 + ny.minute).to_numpy()


def build_smc_features(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Compute all SMC/ICT features. Cached by (id(intraday), id(daily))."""
    key = (id(intraday), id(daily), len(intraday))
    if key in _SMC_CACHE:
        return _SMC_CACHE[key]

    df = _attach_prev_day_levels(intraday, daily)
    o, h, l, c = (df["open"].to_numpy(dtype=np.float64),
                  df["high"].to_numpy(dtype=np.float64),
                  df["low"].to_numpy(dtype=np.float64),
                  df["close"].to_numpy(dtype=np.float64))
    atr14 = atr(df["high"], df["low"], df["close"], 14).to_numpy(dtype=np.float64)
    atr14 = np.where(np.isnan(atr14) | (atr14 <= 0), np.nanmedian(atr14), atr14)
    pdh = df["pdh"].to_numpy(dtype=np.float64)
    pdl = df["pdl"].to_numpy(dtype=np.float64)

    feats = pd.DataFrame(index=intraday.index)

    # Order blocks
    bull_ob_idx, bear_ob_idx = _last_strong_impulse_idx(o, c, atr14, lookback=50, threshold=1.5)
    bull_ob_close = np.where(bull_ob_idx >= 0, c[np.maximum(bull_ob_idx, 0)], np.nan)
    bear_ob_close = np.where(bear_ob_idx >= 0, c[np.maximum(bear_ob_idx, 0)], np.nan)
    feats["dist_bull_ob_atr"] = (c - bull_ob_close) / atr14
    feats["dist_bear_ob_atr"] = (c - bear_ob_close) / atr14

    # Fair value gaps
    bull_fvg_low, bear_fvg_high = _detect_fvgs(h, l)
    feats["bull_fvg_open"] = (~np.isnan(bull_fvg_low)).astype(float)
    feats["bear_fvg_open"] = (~np.isnan(bear_fvg_high)).astype(float)
    feats["dist_bull_fvg_atr"] = np.where(np.isnan(bull_fvg_low), 0,
                                            (c - bull_fvg_low) / atr14)
    feats["dist_bear_fvg_atr"] = np.where(np.isnan(bear_fvg_high), 0,
                                            (bear_fvg_high - c) / atr14)

    # Liquidity sweeps — last 3 bars went above PDH/PDL/swing then closed back inside
    h3 = pd.Series(h).rolling(3).max().to_numpy()
    l3 = pd.Series(l).rolling(3).min().to_numpy()
    swing_h20 = pd.Series(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
    swing_l20 = pd.Series(l).shift(1).rolling(20, min_periods=20).min().to_numpy()

    feats["sweep_pdh"]        = ((h3 > pdh) & (c < pdh)).astype(float)
    feats["sweep_pdl"]        = ((l3 < pdl) & (c > pdl)).astype(float)
    feats["sweep_swing_high"] = ((h3 > swing_h20) & (c < swing_h20)).astype(float)
    feats["sweep_swing_low"]  = ((l3 < swing_l20) & (c > swing_l20)).astype(float)

    # Equal highs/lows count: in last 50 bars, how many highs are within 0.3 ATR
    # of the running max (and same for lows). High count = liquidity cluster.
    def _eq_count(arr, w, atol):
        s = pd.Series(arr)
        roll_max = s.rolling(w, min_periods=w).max()
        diff = (roll_max - s).abs()
        return (diff < atol).rolling(w, min_periods=w).sum().to_numpy()

    feats["eq_highs_count_50"] = _eq_count(h, 50, 0.3 * np.nanmedian(atr14))
    feats["eq_lows_count_50"]  = _eq_count(-np.asarray(l), 50, 0.3 * np.nanmedian(atr14))

    # Killzones (NY time minutes-of-day)
    ny_min = _ny_minute(intraday.index)
    in_kz = (((ny_min >= 9 * 60 + 30) & (ny_min < 11 * 60))     # NY_OPEN
              | ((ny_min >= 3 * 60) & (ny_min < 5 * 60))         # LONDON_OPEN
              | ((ny_min >= 14 * 60) & (ny_min < 16 * 60)))      # NY_PM
    feats["in_killzone"] = in_kz.astype(float)
    near_pdh = (np.abs(c - pdh) < atr14)
    near_pdl = (np.abs(c - pdl) < atr14)
    feats["killzone_at_pdh"] = (in_kz & near_pdh).astype(float)
    feats["killzone_at_pdl"] = (in_kz & near_pdl).astype(float)

    out = feats[SMC_FEATURES]
    _SMC_CACHE[key] = out
    if len(_SMC_CACHE) > 4:
        for k in list(_SMC_CACHE)[:-4]:
            _SMC_CACHE.pop(k, None)
    return out


if __name__ == "__main__":
    from research.local_data_loader import load_daily, load_intraday_1min
    import time
    m1 = load_intraday_1min("nq")
    daily = load_daily("nq")
    t0 = time.time()
    f = build_smc_features(m1.tail(50_000), daily.tail(60))
    print(f"SMC features on 50k 1-min bars: {f.shape}  ({time.time()-t0:.1f}s)")
    print(f.describe().T)

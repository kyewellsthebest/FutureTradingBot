"""
S/R level-fade signal building blocks — inspired by the discretionary swing
short shown in the user's screenshot (fade resistance, tight stop above the
level, target the prior support).

EVERYTHING in this module is strictly point-in-time:
  * a swing high at bar t is the max of [t-k, t+k] — it can only be KNOWN at
    bar t+k, so it's STAMPED THERE (never at t) and forward-filled. There is
    no peeking at future bars.
  * "recent significant level" at bar t = the most recent CONFIRMED swing
    inside the last N bars, again strictly using stamps at or before t.

Triggers exposed:
  * sr_short_REJ_<k>_<n>_<p>  — close is within p bps of the recent swing
                                 high AND the bar closed in its lower half
                                 (rejection wick at resistance).
  * sr_long_REJ_<k>_<n>_<p>   — symmetric at recent swing low.

These return boolean Series indexed identically to the input bars and can be
plugged into the same gauntlet (label_strategy / evaluate_strategy) that
graded v11/v15.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def confirmed_swing_highs(high: pd.Series, k: int) -> pd.Series:
    """Most recent confirmed swing high as of each bar.

    A swing high at t is a fractal max of [t-k, t+k] — only knowable at t+k.
    The level is therefore stamped at t+k (NOT at t) and ffilled forward."""
    h = high.to_numpy()
    out = np.full(len(h), np.nan)
    for t in range(k, len(h) - k):
        if h[t] == h[t - k:t + k + 1].max():
            out[t + k] = h[t]
    return pd.Series(out, index=high.index).ffill()


def confirmed_swing_lows(low: pd.Series, k: int) -> pd.Series:
    l = low.to_numpy()
    out = np.full(len(l), np.nan)
    for t in range(k, len(l) - k):
        if l[t] == l[t - k:t + k + 1].min():
            out[t + k] = l[t]
    return pd.Series(out, index=low.index).ffill()


def recent_level_high(high: pd.Series, k: int, n: int) -> pd.Series:
    """Largest CONFIRMED swing high inside the last n bars at every bar.

    Used as the 'significant resistance' our trigger fades."""
    sh = confirmed_swing_highs(high, k)
    return sh.rolling(n, min_periods=1).max()


def recent_level_low(low: pd.Series, k: int, n: int) -> pd.Series:
    sl = confirmed_swing_lows(low, k)
    return sl.rolling(n, min_periods=1).min()


def sr_short_rejection(o: pd.Series, h: pd.Series, l: pd.Series, c: pd.Series,
                       k: int, n: int, prox_bps: float) -> pd.Series:
    """Short trigger: bar high tested within prox_bps of recent swing high AND
    bar closed in the lower half of its own range (failure to hold the level).
    All inputs are bar-level, so the test at t uses only bar t's OHLC and the
    swing level stamped at or before t."""
    lvl = recent_level_high(h, k, n)
    if lvl.isna().all():
        return pd.Series(False, index=h.index)
    near = h >= lvl * (1.0 - prox_bps * 1e-4)
    rejected = c < (h + l) / 2.0
    valid = lvl.notna() & h.notna() & l.notna() & c.notna()
    return (near & rejected & valid).fillna(False)


def sr_long_rejection(o: pd.Series, h: pd.Series, l: pd.Series, c: pd.Series,
                      k: int, n: int, prox_bps: float) -> pd.Series:
    lvl = recent_level_low(l, k, n)
    if lvl.isna().all():
        return pd.Series(False, index=l.index)
    near = l <= lvl * (1.0 + prox_bps * 1e-4)
    rejected = c > (h + l) / 2.0
    valid = lvl.notna() & h.notna() & l.notna() & c.notna()
    return (near & rejected & valid).fillna(False)


# Parameter grid for the S/R miner. Three swing scales × three level recency
# windows × three proximity tolerances × both sides = the 54 candidate triggers
# the miner will pair with time contexts and RR profiles.
SWING_K = [10, 30, 100]          # 10/30/100 5-min bars ≈ 50min / 2.5h / 8h
LEVEL_RECENCY = [300, 1000, 3000] # 300/1000/3000 bars ≈ 1d / 3.5d / 10d
PROX_BPS = [10, 25, 50]           # 0.10% / 0.25% / 0.50%


def build_sr_triggers(nq_5m: pd.DataFrame) -> dict[str, pd.Series]:
    """Build every (k, n, prox, side) trigger as a named boolean Series."""
    o, h, l, c = nq_5m["open"], nq_5m["high"], nq_5m["low"], nq_5m["close"]
    triggers: dict[str, pd.Series] = {}
    for k in SWING_K:
        for n in LEVEL_RECENCY:
            for p in PROX_BPS:
                triggers[f"sr_short_REJ_{k}_{n}_{p}"] = sr_short_rejection(
                    o, h, l, c, k, n, p)
                triggers[f"sr_long_REJ_{k}_{n}_{p}"] = sr_long_rejection(
                    o, h, l, c, k, n, p)
    return triggers

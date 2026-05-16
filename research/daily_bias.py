"""
Daily-timeframe bias engine — Smart Money / ICT top-down analysis.

Computes a directional bias for each trading day from the DAILY chart, so
the intraday strategy pool can be filtered to only trade WITH the bigger
picture. Concepts implemented:

  * Swing structure  — fractal swing highs/lows; HH+HL = bullish,
                        LH+LL = bearish (market structure).
  * BOS / CHoCH      — break of structure (continuation) vs change of
                        character (potential reversal).
  * Liquidity pools  — BSL (buy-side liquidity, resting above swing highs)
                        and SSL (sell-side liquidity, below swing lows).
  * Liquidity sweep  — price wicks through a pool then closes back —
                        the classic ICT "liquidity grab" before a reversal.
  * Fair Value Gaps  — 3-candle imbalances; unfilled FVGs act as draw-on-
                        liquidity targets / reaction zones.

The synthesis:
  swept SSL  -> sell-side liquidity taken at lows  -> reversal UP  -> LONG
  swept BSL  -> buy-side liquidity taken at highs  -> reversal DOWN -> SHORT
  no sweep   -> follow structure (bullish->LONG, bearish->SHORT, else BOTH)

compute_daily_bias(daily_df, asof) -> dict with the bias + every component
so the live sim can filter strategies and we can audit the reasoning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Swing detection
# ----------------------------------------------------------------------------
def find_swings(df: pd.DataFrame, n: int = 2) -> tuple[list[int], list[int]]:
    """Return (swing_high_idx, swing_low_idx) — fractal swings.

    A swing high at i: high[i] is the strict max of the 2n+1 window centred
    on i. Swing low symmetric on lows.
    """
    highs = df["high"].values
    lows = df["low"].values
    sh, sl = [], []
    for i in range(n, len(df) - n):
        win_h = highs[i - n:i + n + 1]
        win_l = lows[i - n:i + n + 1]
        if highs[i] == win_h.max() and (win_h == highs[i]).sum() == 1:
            sh.append(i)
        if lows[i] == win_l.min() and (win_l == lows[i]).sum() == 1:
            sl.append(i)
    return sh, sl


# ----------------------------------------------------------------------------
# Market structure
# ----------------------------------------------------------------------------
def market_structure(df: pd.DataFrame, n: int = 2) -> str:
    """BULLISH / BEARISH / RANGING from the last two swing highs + lows."""
    sh, sl = find_swings(df, n)
    if len(sh) < 2 or len(sl) < 2:
        return "RANGING"
    h1, h2 = df["high"].iloc[sh[-2]], df["high"].iloc[sh[-1]]
    l1, l2 = df["low"].iloc[sl[-2]], df["low"].iloc[sl[-1]]
    higher_highs = h2 > h1
    higher_lows = l2 > l1
    lower_highs = h2 < h1
    lower_lows = l2 < l1
    if higher_highs and higher_lows:
        return "BULLISH"
    if lower_highs and lower_lows:
        return "BEARISH"
    return "RANGING"


# ----------------------------------------------------------------------------
# Fair Value Gaps (imbalances)
# ----------------------------------------------------------------------------
@dataclass
class FVG:
    direction: str   # "BULLISH" or "BEARISH"
    top: float
    bottom: float
    created_idx: int
    filled: bool = False


def find_fvgs(df: pd.DataFrame, lookback: int = 90) -> list[FVG]:
    """3-candle fair-value-gap detection over the last `lookback` bars.

    Bullish FVG: candle[i-1].high < candle[i+1].low  (gap left below price)
    Bearish FVG: candle[i-1].low  > candle[i+1].high (gap left above price)
    An FVG is 'filled' once a later bar trades fully back through it.
    """
    out: list[FVG] = []
    start = max(1, len(df) - lookback)
    highs = df["high"].values
    lows = df["low"].values
    for i in range(start, len(df) - 1):
        # bullish
        if highs[i - 1] < lows[i + 1]:
            fvg = FVG("BULLISH", top=lows[i + 1], bottom=highs[i - 1], created_idx=i)
            # filled if any later low trades down through the bottom
            later_low = lows[i + 2:].min() if i + 2 < len(df) else np.inf
            fvg.filled = later_low <= fvg.bottom
            out.append(fvg)
        # bearish
        if lows[i - 1] > highs[i + 1]:
            fvg = FVG("BEARISH", top=lows[i - 1], bottom=highs[i + 1], created_idx=i)
            later_high = highs[i + 2:].max() if i + 2 < len(df) else -np.inf
            fvg.filled = later_high >= fvg.top
            out.append(fvg)
    return out


# ----------------------------------------------------------------------------
# Liquidity sweep
# ----------------------------------------------------------------------------
def detect_recent_sweep(df: pd.DataFrame, n: int = 2,
                          window: int = 3) -> str:
    """Did the last `window` daily bars sweep a liquidity pool?

    Returns "BSL" (buy-side liquidity grabbed at an old swing high),
    "SSL" (sell-side grabbed at an old swing low), or "NONE".
    A sweep = a bar's wick pierces the level but the bar CLOSES back
    on the other side (the classic stop-hunt / liquidity grab).
    """
    sh, sl = find_swings(df, n)
    if len(df) < window + 2:
        return "NONE"
    recent = df.iloc[-window:]
    # prior swing levels (exclude the most recent few bars)
    prior_high = max((df["high"].iloc[i] for i in sh if i < len(df) - window),
                       default=None)
    prior_low = min((df["low"].iloc[i] for i in sl if i < len(df) - window),
                      default=None)
    swept_bsl = swept_ssl = False
    if prior_high is not None:
        for _, bar in recent.iterrows():
            if bar["high"] > prior_high and bar["close"] < prior_high:
                swept_bsl = True
    if prior_low is not None:
        for _, bar in recent.iterrows():
            if bar["low"] < prior_low and bar["close"] > prior_low:
                swept_ssl = True
    if swept_bsl and not swept_ssl:
        return "BSL"
    if swept_ssl and not swept_bsl:
        return "SSL"
    if swept_bsl and swept_ssl:
        # both — use the most recent bar's behaviour
        last = df.iloc[-1]
        return "BSL" if last["close"] < last["open"] else "SSL"
    return "NONE"


# ----------------------------------------------------------------------------
# Daily bias synthesis
# ----------------------------------------------------------------------------
@dataclass
class DailyBias:
    asof: str
    structure: str          # BULLISH / BEARISH / RANGING
    last_sweep: str         # BSL / SSL / NONE
    recommended_side: str   # LONG / SHORT / BOTH
    in_opposing_fvg: bool   # price sitting in a counter-trend imbalance
    n_unfilled_fvgs: int
    reason: str


def compute_daily_bias(daily: pd.DataFrame, asof: Optional[pd.Timestamp] = None,
                          swing_n: int = 2) -> DailyBias:
    """Top-down daily bias as of `asof` (uses only bars up to that date)."""
    d = daily.copy()
    if d.index.tz is not None:
        d.index = d.index.tz_localize(None)
    if asof is not None:
        cutoff = pd.Timestamp(asof)
        if cutoff.tz is not None:
            cutoff = cutoff.tz_localize(None)
        d = d[d.index <= cutoff]
    if len(d) < 30:
        return DailyBias(str(asof), "RANGING", "NONE", "BOTH", False, 0,
                            "insufficient history")

    structure = market_structure(d, swing_n)
    sweep = detect_recent_sweep(d, swing_n)
    fvgs = find_fvgs(d, lookback=90)
    unfilled = [f for f in fvgs if not f.filled]
    last_close = float(d["close"].iloc[-1])

    # is price sitting inside a counter-trend (opposing) unfilled FVG?
    in_opposing = False
    for f in unfilled:
        inside = f.bottom <= last_close <= f.top
        if inside and structure == "BULLISH" and f.direction == "BEARISH":
            in_opposing = True
        if inside and structure == "BEARISH" and f.direction == "BULLISH":
            in_opposing = True

    # ---- synthesis ------------------------------------------------------
    # Liquidity sweeps drive the immediate direction (ICT reversal logic).
    if sweep == "SSL":
        side = "LONG"
        reason = "swept sell-side liquidity (lows) -> reversal up"
        if structure == "BEARISH":
            side = "BOTH"  # counter-trend grab; lower conviction
            reason += "; but daily structure still bearish -> low conviction"
    elif sweep == "BSL":
        side = "SHORT"
        reason = "swept buy-side liquidity (highs) -> reversal down"
        if structure == "BULLISH":
            side = "BOTH"
            reason += "; but daily structure still bullish -> low conviction"
    else:
        # no sweep — follow structure
        if structure == "BULLISH":
            side, reason = "LONG", "bullish daily structure (HH/HL), no sweep"
        elif structure == "BEARISH":
            side, reason = "SHORT", "bearish daily structure (LH/LL), no sweep"
        else:
            side, reason = "BOTH", "ranging structure, no sweep"

    # entering an opposing imbalance argues for a counter-trend pullback
    if in_opposing and side in ("LONG", "SHORT"):
        reason += "; price in opposing FVG -> expect pullback"

    return DailyBias(
        asof=str(d.index[-1].date()),
        structure=structure,
        last_sweep=sweep,
        recommended_side=side,
        in_opposing_fvg=in_opposing,
        n_unfilled_fvgs=len(unfilled),
        reason=reason,
    )

"""Session structure: PDH, PDL, ON_HIGH, ON_LOW, OR_HIGH, OR_LOW, POC,
VAH, VAL, current-session VWAP.

CONVENTIONS:
  - Times are US Eastern (DST-aware via pandas)
  - Regular Trading Hours (RTH): 09:30-16:00 ET
  - Overnight Session (ON):       18:00 prev day -> 09:30 today ET
  - Opening Range (OR):           09:30-09:45 ET (first 15 min)
  - Previous Day (PD):            yesterday's RTH session
  - Value Area Percent:           70% (CME standard)

POC / VAH / VAL are computed via the standard TPO/volume-profile method:
  1. Bucket prices into 0.25pt ticks
  2. Sum volume per bucket
  3. POC = bucket with most volume
  4. VAH/VAL = expand from POC outward until 70% of total volume covered

USAGE:
    s = compute_session_structure(bars_df_1min, now)
    print(s.pdh, s.vwap_today)
    nearest = s.nearest_level(price, threshold_pts=3)   # 'pdh', 'poc', etc
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("session_structure")

NY_TZ = "America/New_York"

# Session boundaries in ET (24-hour)
RTH_OPEN  = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
ON_OPEN   = dtime(18, 0)   # previous day evening
OR_END    = dtime(9, 45)   # 15 min after RTH open

VALUE_AREA_PCT = 0.70
TICK_SIZE = 0.25            # NQ futures tick


@dataclass(frozen=True)
class SessionStructure:
    # Previous day's RTH session
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    pd_close: Optional[float] = None

    # Overnight session (prev day 18:00 ET -> today 09:30 ET)
    on_high: Optional[float] = None
    on_low: Optional[float] = None

    # Today's opening range (09:30-09:45 ET)
    or_high: Optional[float] = None
    or_low: Optional[float] = None

    # Volume profile of previous full RTH day
    poc: Optional[float] = None
    vah: Optional[float] = None
    val: Optional[float] = None

    # Current session VWAP (since today's 09:30 ET, or since 18:00 ET prev day)
    vwap: Optional[float] = None

    computed_at: Optional[datetime] = None

    # ---------------------------------------------------------------
    def all_levels(self) -> dict[str, float]:
        """All non-None levels as dict {name: price}. Useful for analytics
        and nearest-level lookups."""
        return {
            name: val for name, val in {
                "pdh": self.pdh, "pdl": self.pdl, "pd_close": self.pd_close,
                "on_high": self.on_high, "on_low": self.on_low,
                "or_high": self.or_high, "or_low": self.or_low,
                "poc": self.poc, "vah": self.vah, "val": self.val,
                "vwap": self.vwap,
            }.items() if val is not None
        }

    def nearest_level(self, price: float,
                       threshold_pts: float = 3.0) -> Optional[str]:
        """Returns the name of the nearest level within threshold_pts of
        price, or None if no level is that close. Useful as a feature for
        analytics: 'this trade fired within 3pt of yesterday's POC'."""
        levels = self.all_levels()
        if not levels:
            return None
        nearest_name, nearest_dist = None, float("inf")
        for name, lvl in levels.items():
            d = abs(price - lvl)
            if d < nearest_dist:
                nearest_dist, nearest_name = d, name
        if nearest_dist <= threshold_pts:
            return nearest_name
        return None

    def distance_to(self, price: float, level_name: str) -> Optional[float]:
        """Signed distance from price to a named level (negative = price
        is below the level). None if level unknown."""
        lvl = self.all_levels().get(level_name)
        if lvl is None:
            return None
        return price - lvl

    def in_value_area(self, price: float) -> Optional[bool]:
        if self.vah is None or self.val is None:
            return None
        return self.val <= price <= self.vah

    def above_pdh(self, price: float) -> Optional[bool]:
        if self.pdh is None:
            return None
        return price > self.pdh

    def to_dict(self) -> dict:
        return {**self.all_levels(),
                "computed_at": self.computed_at.isoformat() if self.computed_at else None}


# =====================================================================
# Computation
# =====================================================================
def compute_session_structure(bars: pd.DataFrame, now: datetime,
                                volume_col: str = "volume") -> SessionStructure:
    """Build a SessionStructure from a 1-min OHLCV DataFrame with a
    UTC-indexed DatetimeIndex. Tolerates missing volume by falling back
    to range-weighted estimates.

    `now` is the current wall-clock UTC time (for selecting "today"
    and "yesterday" properly).
    """
    if bars is None or bars.empty:
        return SessionStructure(computed_at=now)

    # Ensure tz-aware UTC
    if bars.index.tz is None:
        bars = bars.copy()
        bars.index = bars.index.tz_localize("UTC")
    elif str(bars.index.tz) != "UTC":
        bars = bars.copy()
        bars.index = bars.index.tz_convert("UTC")

    # Project to ET for session bucketing
    et_index = bars.index.tz_convert(NY_TZ)
    et_dates = et_index.date

    today_et = pd.Timestamp(now).tz_convert(NY_TZ).date()

    # ---- previous RTH day -------------------------------------------------
    # Find the most recent date BEFORE today_et that has any 09:30+ bars
    unique_dates = sorted(set(et_dates))
    prev_rth_date = None
    for d in reversed(unique_dates):
        if d >= today_et:
            continue
        # Check that this date has any bars in 09:30-16:00
        mask = (et_dates == d)
        et_times = et_index[mask].time
        if any(RTH_OPEN <= t <= RTH_CLOSE for t in et_times):
            prev_rth_date = d
            break

    pdh = pdl = pd_close = poc = vah = val = None
    if prev_rth_date is not None:
        prev_mask = (et_dates == prev_rth_date)
        prev_bars = bars[prev_mask]
        prev_et_times = et_index[prev_mask].time
        rth_mask = np.array([RTH_OPEN <= t <= RTH_CLOSE for t in prev_et_times])
        if rth_mask.any():
            prev_rth = prev_bars[rth_mask]
            pdh = float(prev_rth["high"].max())
            pdl = float(prev_rth["low"].min())
            pd_close = float(prev_rth["close"].iloc[-1])
            try:
                poc, vah, val = _compute_value_area(prev_rth, volume_col=volume_col)
            except Exception as e:
                logger.debug(f"value-area compute failed: {e!r}")

    # ---- overnight session (yesterday 18:00 ET -> today 09:30 ET) --------
    on_high = on_low = None
    # The ON session is "today's overnight" -- the chunk of bars from
    # 18:00 ET previous calendar day up to today 09:30 ET.
    on_start_et = pd.Timestamp.combine(
        today_et - timedelta(days=1), ON_OPEN).tz_localize(NY_TZ)
    on_end_et = pd.Timestamp.combine(
        today_et, RTH_OPEN).tz_localize(NY_TZ)
    on_start_utc = on_start_et.tz_convert("UTC")
    on_end_utc = on_end_et.tz_convert("UTC")
    on_mask = (bars.index >= on_start_utc) & (bars.index < on_end_utc)
    if on_mask.any():
        on_bars = bars[on_mask]
        on_high = float(on_bars["high"].max())
        on_low = float(on_bars["low"].min())

    # ---- opening range (today 09:30-09:45 ET) ---------------------------
    or_high = or_low = None
    or_start_et = pd.Timestamp.combine(today_et, RTH_OPEN).tz_localize(NY_TZ)
    or_end_et = pd.Timestamp.combine(today_et, OR_END).tz_localize(NY_TZ)
    or_start_utc = or_start_et.tz_convert("UTC")
    or_end_utc = or_end_et.tz_convert("UTC")
    or_mask = (bars.index >= or_start_utc) & (bars.index < or_end_utc)
    if or_mask.any():
        or_bars = bars[or_mask]
        or_high = float(or_bars["high"].max())
        or_low = float(or_bars["low"].min())

    # ---- current session VWAP -------------------------------------------
    # Start of "today" = today's RTH open if we're past it, else today's ON open
    now_et = pd.Timestamp(now).tz_convert(NY_TZ)
    if now_et.time() >= RTH_OPEN:
        vwap_start_et = pd.Timestamp.combine(today_et, RTH_OPEN).tz_localize(NY_TZ)
    else:
        # Pre-RTH: use ON start
        vwap_start_et = on_start_et
    vwap_start_utc = vwap_start_et.tz_convert("UTC")
    vwap_mask = bars.index >= vwap_start_utc
    vwap = None
    if vwap_mask.any():
        v_bars = bars[vwap_mask]
        if volume_col in v_bars.columns and v_bars[volume_col].sum() > 0:
            typical = (v_bars["high"] + v_bars["low"] + v_bars["close"]) / 3
            vwap = float((typical * v_bars[volume_col]).sum() /
                         v_bars[volume_col].sum())
        else:
            # No-volume fallback: equal-weighted typical price
            typical = (v_bars["high"] + v_bars["low"] + v_bars["close"]) / 3
            vwap = float(typical.mean())

    return SessionStructure(
        pdh=pdh, pdl=pdl, pd_close=pd_close,
        on_high=on_high, on_low=on_low,
        or_high=or_high, or_low=or_low,
        poc=poc, vah=vah, val=val,
        vwap=vwap,
        computed_at=now,
    )


def _compute_value_area(bars: pd.DataFrame,
                          volume_col: str = "volume") -> tuple[float, float, float]:
    """Standard 70% volume-profile method.

    Bucket prices into TICK_SIZE buckets, sum volume per bucket, expand
    from POC outward (alternating up/down, taking the larger volume side)
    until 70% of total volume is enclosed.
    """
    if bars.empty:
        raise ValueError("empty bars")

    use_volume = (volume_col in bars.columns
                  and bars[volume_col].sum() > 0)

    # Build the price->volume histogram. For each bar, distribute its
    # volume uniformly across the high-low range (a standard approximation
    # since we don't have intra-bar tick volume).
    low_min = float(bars["low"].min())
    high_max = float(bars["high"].max())
    n_buckets = max(1, int(round((high_max - low_min) / TICK_SIZE)) + 1)
    if n_buckets > 10000:   # sanity cap
        n_buckets = 10000
    hist = np.zeros(n_buckets)

    for _, row in bars.iterrows():
        bar_low = float(row["low"]); bar_high = float(row["high"])
        bar_vol = float(row[volume_col]) if use_volume else 1.0
        start_i = max(0, int((bar_low - low_min) / TICK_SIZE))
        end_i = min(n_buckets - 1, int((bar_high - low_min) / TICK_SIZE))
        span = max(1, end_i - start_i + 1)
        per_bucket = bar_vol / span
        hist[start_i:end_i + 1] += per_bucket

    total = hist.sum()
    if total <= 0:
        # Fallback: degenerate to typical price
        tp = float((bars["high"] + bars["low"] + bars["close"]).mean() / 3)
        return tp, tp, tp

    poc_idx = int(hist.argmax())
    poc = low_min + poc_idx * TICK_SIZE

    # Expand from POC until we've covered VALUE_AREA_PCT of volume
    covered = hist[poc_idx]
    lo_i = hi_i = poc_idx
    target = total * VALUE_AREA_PCT
    while covered < target and (lo_i > 0 or hi_i < n_buckets - 1):
        # Look at 2 buckets above and 2 below, take whichever side has more volume
        up_vol   = hist[hi_i + 1:hi_i + 3].sum() if hi_i + 1 < n_buckets else 0.0
        down_vol = hist[max(0, lo_i - 2):lo_i].sum() if lo_i > 0 else 0.0
        if up_vol >= down_vol and hi_i < n_buckets - 1:
            new_hi = min(hi_i + 2, n_buckets - 1)
            covered += hist[hi_i + 1:new_hi + 1].sum()
            hi_i = new_hi
        elif lo_i > 0:
            new_lo = max(lo_i - 2, 0)
            covered += hist[new_lo:lo_i].sum()
            lo_i = new_lo
        else:
            break

    val = low_min + lo_i * TICK_SIZE
    vah = low_min + hi_i * TICK_SIZE
    return poc, vah, val

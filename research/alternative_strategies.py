"""Alternative-strategy bake-off for the MNQ bot — same execution model
as research/comprehensive_backtest.py, but with simpler detection
functions that emit explicit (entry-side, stop, target) setups instead
of going through bot.pullback_strategy.

USAGE:
  # 60-day subset (default ~10-20 mins depending on strategy count)
  python -m research.alternative_strategies

  # full 766-day data
  python -m research.alternative_strategies --full

  # restrict to single strategy for debugging
  python -m research.alternative_strategies --only MOMENTUM_3BAR

Output:
  research/alternative_strategies_results.md
  research/alt_summary_60d.csv
  research/alt_summary_full.csv

Execution model (mirrors comprehensive_backtest.py exactly):
  - Detection runs on closed 1-min bars. A detected setup is an
    AltSetup(side, entry_kind, entry_px, stop_px, target_px,
             detected_at, expires_at).
  - "Immediate" entry_kind means: fire on the very NEXT tick. LONG fills
    at ASK; SHORT fills at BID.
  - "Limit" entry_kind means: wait for price to reach entry_px the same
    way the pullback strategy does — arming above (LONG) or below (SHORT)
    then trigger when price reverses through. Fill at ASK/BID (marketable
    LIMIT model).
  - Exits: stop-MARKET = stop_px +/- 0.5pt slip; target = LIMIT exact
    fill when bid (LONG) or ask (SHORT) reaches the level; timeout =
    midpoint after MAX_HOLD_SECS.
  - Cooldown 10s, $0.74 commission, 1 MNQ ($2/pt), 1 position max.
"""
from __future__ import annotations
import argparse
import copy
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")

# ============================================================================
# Constants — match comprehensive_backtest.py exactly
# ============================================================================
TICK_CSV = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
CHUNK_SIZE = 1_000_000
COMMISSION_RT = 0.74
MNQ_PER_PT = 2.0
N_MNQ = 1
STOP_SLIP_PTS = 0.5
ENTRY_BUFFER_PTS = 1.0
MAX_WAIT_SECS = 300                  # setup expires if not filled in 5min
MAX_HOLD_SECS = 600                  # 10 minutes max in trade
MIN_TARGET_HOLD_SECONDS = 10
HISTORY_BARS = 240
PROGRESS_TICKS = 10_000_000

US_PER_SEC = 1_000_000
US_PER_MIN = 60 * US_PER_SEC


# ============================================================================
# AltSetup — minimal pending-setup record
# ============================================================================
@dataclass
class AltSetup:
    detected_at: datetime
    side: str                   # "LONG" or "SHORT" (TRADE direction)
    entry_kind: str             # "immediate" or "limit"
    entry_px: float             # for "limit" entries; mid at detection for "immediate"
    stop_px: float
    target_px: float
    expires_at: datetime
    # For limit-style entry: which side price approaches from. For an
    # "immediate" entry we just use side directly.
    orig_side: Optional[str] = None
    used: bool = False
    entry_armed: bool = False
    # Strategy metadata (helpful for debugging)
    note: str = ""


# ============================================================================
# Tick parsing — copied verbatim from comprehensive_backtest.py
# ============================================================================
def iter_tick_chunks(path: str, *, start_offset: int = 0):
    f = open(path, "r")
    if start_offset > 0:
        f.seek(start_offset)
        f.readline()
    reader = pd.read_csv(
        f, sep=";", header=None,
        names=["dt", "mid", "bid", "ask", "vol"],
        chunksize=CHUNK_SIZE,
        usecols=[0, 1, 2, 3],
        engine="c",
        dtype={"dt": str, "mid": np.float64,
               "bid": np.float64, "ask": np.float64},
    )
    for raw in reader:
        dt = raw["dt"].values
        n = len(dt)
        dt_arr = np.array(dt, dtype="S23")
        b = dt_arr.view(np.uint8).reshape(n, 23)

        def digits_to_int(slc):
            k = slc.shape[1]
            out = np.zeros(n, dtype=np.int64)
            for j in range(k):
                out = out * 10 + (slc[:, j].astype(np.int64) - 48)
            return out

        yr = digits_to_int(b[:, 0:4])
        mo = digits_to_int(b[:, 4:6])
        dy = digits_to_int(b[:, 6:8])
        hr = digits_to_int(b[:, 9:11])
        mn = digits_to_int(b[:, 11:13])
        sc = digits_to_int(b[:, 13:15])
        us = digits_to_int(b[:, 16:22])
        date_int = (yr * 10000 + mo * 100 + dy).astype(np.int64)
        unique_dates = np.unique(date_int)
        date_us_map = {}
        for di in unique_dates:
            di_str = str(int(di))
            tsmid = pd.Timestamp(di_str, tz="UTC")
            date_us_map[int(di)] = int(tsmid.value // 1000)
        sorted_keys = np.array(sorted(date_us_map.keys()), dtype=np.int64)
        vals = np.array([date_us_map[int(k)] for k in sorted_keys], dtype=np.int64)
        idx = np.searchsorted(sorted_keys, date_int)
        midnight_us = vals[idx]
        ts_us = midnight_us + (hr * 3600 + mn * 60 + sc) * US_PER_SEC + us
        yield {
            "ts": ts_us,
            "bid": raw["bid"].values.astype(np.float64),
            "ask": raw["ask"].values.astype(np.float64),
            "mid": raw["mid"].values.astype(np.float64),
        }


# ============================================================================
# Bar history — keep last HISTORY_BARS as a dict of numpy arrays.
# We don't use a pandas DataFrame: every strategy works on numpy directly.
# ============================================================================
@dataclass
class BarHistory:
    keep: int = HISTORY_BARS
    ts_us: list = field(default_factory=list)        # bar OPEN epoch us
    o: list = field(default_factory=list)
    h: list = field(default_factory=list)
    l: list = field(default_factory=list)
    c: list = field(default_factory=list)
    v: list = field(default_factory=list)
    # Session VWAP state — reset at 22:00 UTC daily
    session_pv: float = 0.0
    session_vol: float = 0.0
    session_started_at: Optional[int] = None  # us
    # Daily previous-day OHLC for pivots (rolling)
    prev_day_h: Optional[float] = None
    prev_day_l: Optional[float] = None
    prev_day_c: Optional[float] = None
    cur_day_h: Optional[float] = None
    cur_day_l: Optional[float] = None
    cur_day_c: Optional[float] = None
    cur_day_str: Optional[str] = None

    def append(self, ts_us: int, o: float, h: float, l: float, c: float, v: int):
        self.ts_us.append(ts_us)
        self.o.append(o); self.h.append(h); self.l.append(l)
        self.c.append(c); self.v.append(v)
        if len(self.ts_us) > self.keep:
            # Trim only when significantly over to amortize O(n) cost
            self.ts_us = self.ts_us[-self.keep:]
            self.o = self.o[-self.keep:]
            self.h = self.h[-self.keep:]
            self.l = self.l[-self.keep:]
            self.c = self.c[-self.keep:]
            self.v = self.v[-self.keep:]
        # Session VWAP — reset at 22:00 UTC. We use 22:00 boundary as
        # cme open / new "session day".
        bar_dt = datetime.fromtimestamp(ts_us / 1e6, tz=timezone.utc)
        # Define session-day key: if bar hour >= 22, the session-day is "tomorrow",
        # otherwise "today".
        if bar_dt.hour >= 22:
            sess_day = bar_dt.date() + timedelta(days=1)
        else:
            sess_day = bar_dt.date()
        sess_day_str = sess_day.isoformat()
        if self.session_started_at is None or self.cur_day_str != sess_day_str:
            # Rollover -> archive prev day OHLC for pivot calcs.
            if self.cur_day_str is not None:
                self.prev_day_h = self.cur_day_h
                self.prev_day_l = self.cur_day_l
                self.prev_day_c = self.cur_day_c
            self.session_pv = 0.0
            self.session_vol = 0.0
            self.session_started_at = ts_us
            self.cur_day_h = h
            self.cur_day_l = l
            self.cur_day_c = c
            self.cur_day_str = sess_day_str
        else:
            self.cur_day_h = max(self.cur_day_h, h)
            self.cur_day_l = min(self.cur_day_l, l)
            self.cur_day_c = c
        # Update VWAP (use HLC/3 as typical price, vol as weight)
        typ = (h + l + c) / 3.0
        self.session_pv += typ * max(1, v)
        self.session_vol += max(1, v)

    def vwap(self) -> float:
        if self.session_vol <= 0:
            return float("nan")
        return self.session_pv / self.session_vol

    def arrays(self):
        """Return numpy arrays of the bar history (no copy if possible)."""
        return {
            "o": np.asarray(self.o, dtype=np.float64),
            "h": np.asarray(self.h, dtype=np.float64),
            "l": np.asarray(self.l, dtype=np.float64),
            "c": np.asarray(self.c, dtype=np.float64),
            "v": np.asarray(self.v, dtype=np.int64),
            "ts": np.asarray(self.ts_us, dtype=np.int64),
        }


# ============================================================================
# DETECTORS — each returns a list of AltSetup or empty list
# Signature: detector(arrs, bar_hist, now, params) -> list[AltSetup]
# arrs is what BarHistory.arrays() returns; bar_hist is the BarHistory.
# ============================================================================
def _atr(arrs, n=14):
    h, l, c = arrs["h"], arrs["l"], arrs["c"]
    if len(c) < n + 1:
        return float("nan")
    pc = np.concatenate([[c[-(n + 1)]], c[-(n + 1):-1]])
    tr = np.maximum.reduce([
        h[-n:] - l[-n:],
        np.abs(h[-n:] - c[-(n + 1):-1]),
        np.abs(l[-n:] - c[-(n + 1):-1]),
    ])
    return float(tr.mean())


def _ema(c, n):
    """Simple recursive EMA. c is numpy array. Returns ema array (same len)."""
    if len(c) == 0:
        return c
    alpha = 2.0 / (n + 1)
    out = np.empty_like(c)
    out[0] = c[0]
    for i in range(1, len(c)):
        out[i] = alpha * c[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(c, n=14):
    if len(c) < n + 1:
        return np.full_like(c, np.nan, dtype=np.float64)
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # Wilder smoothing
    avg_gain = np.zeros_like(c)
    avg_loss = np.zeros_like(c)
    avg_gain[n] = gain[:n].mean()
    avg_loss[n] = loss[:n].mean()
    for i in range(n + 1, len(c)):
        avg_gain[i] = (avg_gain[i - 1] * (n - 1) + gain[i - 1]) / n
        avg_loss[i] = (avg_loss[i - 1] * (n - 1) + loss[i - 1]) / n
    rs = np.where(avg_loss > 0, avg_gain / np.maximum(avg_loss, 1e-9), 0.0)
    rsi = 100 - (100 / (1 + rs))
    rsi[:n] = np.nan
    return rsi


def _expires(now, secs=MAX_WAIT_SECS):
    return now + timedelta(seconds=secs)


# ---------------------------------------------------------------------------
# A. CONTINUATION_PULLBACK — trade WITH impulse direction (INVERT=0 pullback)
# Reuses the same impulse-then-pullback structure. We implement here
# inline (no dependency on bot.pullback_strategy) so it stays standalone.
# ---------------------------------------------------------------------------
def detect_continuation_pullback(arrs, bh, now, p):
    """Look for an impulse over the last `impulse_bars` bars of >= impulse_pts,
    then a pullback of pull_pct retrace. Trade WITH the impulse."""
    c = arrs["c"]; h = arrs["h"]; l = arrs["l"]
    n = len(c)
    nb = p.get("impulse_bars", 4)
    ip = p.get("impulse_pts", 5.0)
    pull = p.get("pull_pct", 0.5)
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if n < nb + 2:
        return []
    # Most recent impulse: largest pivot range over last nb bars
    hi = float(h[-nb:].max())
    lo = float(l[-nb:].min())
    leg = hi - lo
    if leg < ip:
        return []
    last_close = float(c[-1])
    # Determine impulse direction from where close sits within leg AND
    # which extreme came LAST.
    hi_idx = int(np.argmax(h[-nb:]))
    lo_idx = int(np.argmin(l[-nb:]))
    if hi_idx > lo_idx:
        # UP impulse: low first then high
        impulse_side = "LONG"
        entry = hi - leg * pull
        stop_px = entry - stop
        target_px = entry + target
    else:
        impulse_side = "SHORT"
        entry = lo + leg * pull
        stop_px = entry + stop
        target_px = entry - target
    return [AltSetup(
        detected_at=now, side=impulse_side, entry_kind="limit",
        entry_px=entry, stop_px=stop_px, target_px=target_px,
        expires_at=_expires(now), orig_side=impulse_side,
        note=f"cont_pullback leg={leg:.1f}",
    )]


# ---------------------------------------------------------------------------
# B. MOMENTUM_3BAR — 3 same-direction bars => enter direction on next tick
# ---------------------------------------------------------------------------
def detect_momentum_3bar(arrs, bh, now, p):
    o, c = arrs["o"], arrs["c"]
    if len(c) < 3:
        return []
    last3_dir = np.sign(c[-3:] - o[-3:])
    if (last3_dir == 1).all():
        side = "LONG"
    elif (last3_dir == -1).all():
        side = "SHORT"
    else:
        return []
    mid = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    stop_px = mid - stop if side == "LONG" else mid + stop
    target_px = mid + target if side == "LONG" else mid - target
    return [AltSetup(
        detected_at=now, side=side, entry_kind="immediate",
        entry_px=mid, stop_px=stop_px, target_px=target_px,
        expires_at=_expires(now, 120),
        note="mom_3bar",
    )]


# ---------------------------------------------------------------------------
# C. RANGE_BREAKOUT — N-bar range, fire when close breaks. Immediate next-tick.
# ---------------------------------------------------------------------------
def detect_range_breakout(arrs, bh, now, p):
    h, l, c = arrs["h"], arrs["l"], arrs["c"]
    N = p.get("range_bars", 10)
    if len(c) < N + 1:
        return []
    hh = float(h[-(N + 1):-1].max())
    ll = float(l[-(N + 1):-1].min())
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if last_c > hh:
        side = "LONG"
        stop_px = ll  # opposite range edge as stop
        # but cap stop at stop_pts to avoid runaway
        stop_px = max(stop_px, last_c - stop)
        target_px = last_c + target
    elif last_c < ll:
        side = "SHORT"
        stop_px = hh
        stop_px = min(stop_px, last_c + stop)
        target_px = last_c - target
    else:
        return []
    return [AltSetup(
        detected_at=now, side=side, entry_kind="immediate",
        entry_px=last_c, stop_px=stop_px, target_px=target_px,
        expires_at=_expires(now, 120),
        note=f"range_br {N}b",
    )]


# ---------------------------------------------------------------------------
# D. INSIDE_BAR — prev-1 bar contains prev bar => trade on break of prev-1
# ---------------------------------------------------------------------------
def detect_inside_bar(arrs, bh, now, p):
    h, l, c = arrs["h"], arrs["l"], arrs["c"]
    if len(c) < 2:
        return []
    mh = float(h[-2]); ml = float(l[-2])  # mother bar = penultimate
    ih = float(h[-1]); il = float(l[-1])  # inside bar = last
    if not (ih <= mh and il >= ml):
        return []  # not inside
    # Trade break of mother bar — we emit a LIMIT-style setup with entry
    # at mother high (LONG) or mother low (SHORT). But we don't know yet
    # which side will break, so emit BOTH and let whichever triggers first
    # win.
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    # LONG: entry just above mother high. To get it filled via the
    # arming-then-trigger machinery we treat it as an "immediate" entry
    # gated by a custom condition. Simpler: use the entry_kind="limit"
    # with orig_side reversed so trigger fires when price RISES to entry.
    # Specifically: for LONG breakout we want trigger when mid >= mh.
    # In the arming code path: approach="SHORT" arms when mid < entry,
    # then triggers when mid >= entry. So orig_side="SHORT" for a LONG
    # trade entry above price.
    setups = []
    setups.append(AltSetup(
        detected_at=now, side="LONG", entry_kind="limit",
        entry_px=mh + 0.25, stop_px=mh + 0.25 - stop, target_px=mh + 0.25 + target,
        expires_at=_expires(now, 300), orig_side="SHORT",  # approach from below
        note="inside_bar LONG",
    ))
    setups.append(AltSetup(
        detected_at=now, side="SHORT", entry_kind="limit",
        entry_px=ml - 0.25, stop_px=ml - 0.25 + stop, target_px=ml - 0.25 - target,
        expires_at=_expires(now, 300), orig_side="LONG",  # approach from above
        note="inside_bar SHORT",
    ))
    return setups


# ---------------------------------------------------------------------------
# E. VWAP_PULLBACK — wait for trend day, pullback to VWAP, trade with trend
# ---------------------------------------------------------------------------
def detect_vwap_pullback(arrs, bh, now, p):
    c = arrs["c"]; h = arrs["h"]; l = arrs["l"]
    if len(c) < 30:
        return []
    vwap = bh.vwap()
    if math.isnan(vwap):
        return []
    last_c = float(c[-1])
    last_h = float(h[-1])
    last_l = float(l[-1])
    # Are we in an UP trend? Use 20-EMA slope as quick filter.
    ema20 = _ema(c, 20)
    if len(ema20) < 21:
        return []
    slope = float(ema20[-1] - ema20[-5])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    dist = abs(last_c - vwap)
    if dist > 5.0:        # not near VWAP
        return []
    if slope > 0.5 and last_l <= vwap and last_c > vwap:
        # Pullback into VWAP from above in uptrend -> LONG
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
            expires_at=_expires(now, 120),
            note=f"vwap_pull UP slope={slope:.2f}",
        )]
    if slope < -0.5 and last_h >= vwap and last_c < vwap:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
            expires_at=_expires(now, 120),
            note=f"vwap_pull DOWN slope={slope:.2f}",
        )]
    return []


# ---------------------------------------------------------------------------
# F. VWAP_BREAKOUT — N bars on one side of VWAP, then close back through
# ---------------------------------------------------------------------------
def detect_vwap_breakout(arrs, bh, now, p):
    c = arrs["c"]
    N = p.get("vwap_bars", 5)
    if len(c) < N + 2:
        return []
    vwap = bh.vwap()
    if math.isnan(vwap):
        return []
    last_c = float(c[-1])
    prev_c = c[-(N + 1):-1]
    above = (prev_c > vwap).all()
    below = (prev_c < vwap).all()
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if below and last_c > vwap:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
            expires_at=_expires(now, 120), note="vwap_br up",
        )]
    if above and last_c < vwap:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
            expires_at=_expires(now, 120), note="vwap_br down",
        )]
    return []


# ---------------------------------------------------------------------------
# G. BB_REVERSION — 20-bar Bollinger touch outside => revert
# ---------------------------------------------------------------------------
def detect_bb_reversion(arrs, bh, now, p):
    c = arrs["c"]; h = arrs["h"]; l = arrs["l"]
    N = p.get("bb_n", 20)
    k = p.get("bb_k", 2.0)
    if len(c) < N + 1:
        return []
    win = c[-N:]
    mid = float(win.mean())
    sd = float(win.std(ddof=0))
    if sd <= 0:
        return []
    upper = mid + k * sd
    lower = mid - k * sd
    last_c = float(c[-1])
    last_h = float(h[-1])
    last_l = float(l[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if last_h > upper and last_c < upper:
        # Closed back inside from above -> SHORT (fade)
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
            expires_at=_expires(now, 120), note="bb_rev top",
        )]
    if last_l < lower and last_c > lower:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
            expires_at=_expires(now, 120), note="bb_rev bot",
        )]
    return []


# ---------------------------------------------------------------------------
# H. BB_BREAKOUT — BB squeeze then breakout
# ---------------------------------------------------------------------------
def detect_bb_breakout(arrs, bh, now, p):
    c = arrs["c"]
    N = p.get("bb_n", 20)
    k = p.get("bb_k", 2.0)
    if len(c) < N + 6:
        return []
    win = c[-N:]
    mid = float(win.mean())
    sd = float(win.std(ddof=0))
    if sd <= 0:
        return []
    upper = mid + k * sd
    lower = mid - k * sd
    bandwidth = upper - lower
    # Compare current bandwidth to past 50-bar mean: must be in bottom quartile
    if len(c) >= N + 50:
        bws = []
        for i in range(-50, 0):
            w = c[-N + i: i if i != 0 else None]
            if len(w) == N:
                bws.append(float(w.std(ddof=0)) * 2 * k)
        bws = np.array(bws)
        thr = float(np.percentile(bws, 25))
        if bandwidth > thr:
            return []
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if last_c > upper:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
            expires_at=_expires(now, 120), note="bb_br up",
        )]
    if last_c < lower:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
            expires_at=_expires(now, 120), note="bb_br down",
        )]
    return []


# ---------------------------------------------------------------------------
# I. ORB_15MIN — opening range first 15 minutes after CME open (22:00 UTC)
# Trade break of OR. Single signal per session.
# ---------------------------------------------------------------------------
def detect_orb_15min(arrs, bh, now, p):
    ts = arrs["ts"]; h = arrs["h"]; l = arrs["l"]; c = arrs["c"]
    if len(ts) < 20:
        return []
    # Find the bar at exact CME open of current session: ts_us where the
    # bar's hour == 22 (UTC) and minute == 0. We look back ~30 bars max.
    open_idx = None
    for i in range(len(ts) - 1, max(0, len(ts) - 40), -1):
        bar_dt = datetime.fromtimestamp(ts[i] / 1e6, tz=timezone.utc)
        if bar_dt.hour == 22 and bar_dt.minute == 0:
            open_idx = i
            break
    if open_idx is None or open_idx > len(ts) - 16:
        return []
    # Last bar must be the 16th bar (idx open_idx+15 = the bar closing
    # at minute 15) — only fire ONCE on that bar.
    if (len(ts) - 1) != open_idx + 15:
        return []
    or_hi = float(h[open_idx: open_idx + 15].max())
    or_lo = float(l[open_idx: open_idx + 15].min())
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    # Emit BOTH breakout setups (one will trigger).
    return [
        AltSetup(detected_at=now, side="LONG", entry_kind="limit",
                 entry_px=or_hi + 0.5, stop_px=or_hi + 0.5 - stop,
                 target_px=or_hi + 0.5 + target, expires_at=_expires(now, 60 * 60 * 4),
                 orig_side="SHORT", note="orb15 up"),
        AltSetup(detected_at=now, side="SHORT", entry_kind="limit",
                 entry_px=or_lo - 0.5, stop_px=or_lo - 0.5 + stop,
                 target_px=or_lo - 0.5 - target, expires_at=_expires(now, 60 * 60 * 4),
                 orig_side="LONG", note="orb15 down"),
    ]


# ---------------------------------------------------------------------------
# J. EMA_PULLBACK — 50-EMA trend filter, pull to 20-EMA
# ---------------------------------------------------------------------------
def detect_ema_pullback(arrs, bh, now, p):
    c = arrs["c"]; h = arrs["h"]; l = arrs["l"]
    if len(c) < 60:
        return []
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    last_c = float(c[-1])
    last_h = float(h[-1])
    last_l = float(l[-1])
    e20 = float(ema20[-1])
    e50 = float(ema50[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    # Uptrend & pulled to 20-EMA: LONG
    if last_c > e50 and last_l <= e20 and last_c > e20:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
            expires_at=_expires(now, 120), note="ema_pull UP",
        )]
    if last_c < e50 and last_h >= e20 and last_c < e20:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
            expires_at=_expires(now, 120), note="ema_pull DOWN",
        )]
    return []


# ---------------------------------------------------------------------------
# K. PIVOT_REVERSAL — daily pivot R1/R2/S1/S2 fade. Uses prev day OHLC.
# ---------------------------------------------------------------------------
def detect_pivot_reversal(arrs, bh, now, p):
    if bh.prev_day_h is None:
        return []
    pH = bh.prev_day_h; pL = bh.prev_day_l; pC = bh.prev_day_c
    P = (pH + pL + pC) / 3.0
    R1 = 2 * P - pL; S1 = 2 * P - pH
    R2 = P + (pH - pL); S2 = P - (pH - pL)
    c = arrs["c"]
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    tol = 2.0  # within 2pts of a level
    for level, side in [(R1, "SHORT"), (R2, "SHORT"),
                         (S1, "LONG"), (S2, "LONG")]:
        if abs(last_c - level) <= tol:
            if side == "SHORT":
                return [AltSetup(
                    detected_at=now, side="SHORT", entry_kind="immediate",
                    entry_px=last_c, stop_px=last_c + stop,
                    target_px=last_c - target,
                    expires_at=_expires(now, 120), note=f"pivot {side} L={level:.1f}",
                )]
            return [AltSetup(
                detected_at=now, side="LONG", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c - stop,
                target_px=last_c + target,
                expires_at=_expires(now, 120), note=f"pivot {side} L={level:.1f}",
            )]
    return []


# ---------------------------------------------------------------------------
# L. RSI_EXTREMES — fade RSI > 80 / < 20
# ---------------------------------------------------------------------------
def detect_rsi_extremes(arrs, bh, now, p):
    c = arrs["c"]
    n = p.get("rsi_n", 14)
    if len(c) < n + 2:
        return []
    rsi = _rsi(c, n)
    if math.isnan(rsi[-1]):
        return []
    hi_thr = p.get("rsi_hi", 80)
    lo_thr = p.get("rsi_lo", 20)
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if rsi[-1] > hi_thr and rsi[-2] > hi_thr:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop,
            target_px=last_c - target, expires_at=_expires(now, 120),
            note=f"rsi {rsi[-1]:.0f}",
        )]
    if rsi[-1] < lo_thr and rsi[-2] < lo_thr:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop,
            target_px=last_c + target, expires_at=_expires(now, 120),
            note=f"rsi {rsi[-1]:.0f}",
        )]
    return []


# ---------------------------------------------------------------------------
# M. RSI_DIVERGENCE — classic bullish/bearish divergence
# Bullish: price makes new low but RSI doesn't (RSI > prev RSI at prev low).
# Look-back window 30 bars.
# ---------------------------------------------------------------------------
def detect_rsi_divergence(arrs, bh, now, p):
    c = arrs["c"]; l = arrs["l"]; h = arrs["h"]
    if len(c) < 35:
        return []
    rsi = _rsi(c, 14)
    if math.isnan(rsi[-1]):
        return []
    look = 30
    # Find two most recent swing lows
    lows_idx = []
    for i in range(len(c) - 3, len(c) - look, -1):
        if l[i] < l[i - 1] and l[i] < l[i + 1] and l[i] < l[i - 2] and l[i] < l[i + 2]:
            lows_idx.append(i)
            if len(lows_idx) == 2:
                break
    highs_idx = []
    for i in range(len(c) - 3, len(c) - look, -1):
        if h[i] > h[i - 1] and h[i] > h[i + 1] and h[i] > h[i - 2] and h[i] > h[i + 2]:
            highs_idx.append(i)
            if len(highs_idx) == 2:
                break
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    last_c = float(c[-1])
    # Bullish divergence
    if len(lows_idx) == 2:
        i_recent, i_prev = lows_idx
        if l[i_recent] < l[i_prev] and rsi[i_recent] > rsi[i_prev]:
            return [AltSetup(
                detected_at=now, side="LONG", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c - stop,
                target_px=last_c + target, expires_at=_expires(now, 120),
                note="rsi_div bull",
            )]
    if len(highs_idx) == 2:
        i_recent, i_prev = highs_idx
        if h[i_recent] > h[i_prev] and rsi[i_recent] < rsi[i_prev]:
            return [AltSetup(
                detected_at=now, side="SHORT", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c + stop,
                target_px=last_c - target, expires_at=_expires(now, 120),
                note="rsi_div bear",
            )]
    return []


# ---------------------------------------------------------------------------
# N. ATR_EXPANSION — ATR contracts then expands; enter direction
# ---------------------------------------------------------------------------
def detect_atr_expansion(arrs, bh, now, p):
    c = arrs["c"]; o = arrs["o"]
    if len(c) < 40:
        return []
    # Compute 14-bar ATR for the last bar and the prior 20 bars.
    atr_cur = _atr(arrs, 14)
    if math.isnan(atr_cur):
        return []
    # Approximation: compare to ATR-20-bars-ago via min over recent window
    # We'll detect "expansion" as: last 3 bars true range > 2 * 20-bar avg TR
    h = arrs["h"]; l = arrs["l"]
    tr_recent = (h[-3:] - l[-3:]).mean()
    tr_20 = (h[-23:-3] - l[-23:-3]).mean() if len(c) >= 23 else float("nan")
    if math.isnan(tr_20) or tr_20 <= 0:
        return []
    if tr_recent < 2.0 * tr_20:
        return []
    # Direction = sign of last bar
    last_c = float(c[-1])
    side = "LONG" if c[-1] > o[-1] else "SHORT"
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    stop_px = last_c - stop if side == "LONG" else last_c + stop
    target_px = last_c + target if side == "LONG" else last_c - target
    return [AltSetup(
        detected_at=now, side=side, entry_kind="immediate",
        entry_px=last_c, stop_px=stop_px, target_px=target_px,
        expires_at=_expires(now, 120), note="atr_exp",
    )]


# ---------------------------------------------------------------------------
# O. CUMULATIVE_DELTA divergence (approx from bar close vs prior close)
# We approximate cumulative delta as cumsum of (close - open) over bars.
# Divergence: price makes new high but cumdelta doesn't => SHORT.
# ---------------------------------------------------------------------------
def detect_cumdelta_div(arrs, bh, now, p):
    c = arrs["c"]; o = arrs["o"]; h = arrs["h"]; l = arrs["l"]
    if len(c) < 30:
        return []
    cd = np.cumsum(c - o)  # proxy cumulative delta
    look = 20
    # Compare last bar's high vs prior look-window high; cd of last bar
    # vs cd at that high.
    recent_h_idx = len(c) - 1
    prior_h_idx = int(np.argmax(h[-look:-1])) + (len(c) - look)
    recent_l_idx = len(c) - 1
    prior_l_idx = int(np.argmin(l[-look:-1])) + (len(c) - look)
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if h[recent_h_idx] > h[prior_h_idx] and cd[recent_h_idx] < cd[prior_h_idx]:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop,
            target_px=last_c - target, expires_at=_expires(now, 120),
            note="cumdelta_div bear",
        )]
    if l[recent_l_idx] < l[prior_l_idx] and cd[recent_l_idx] > cd[prior_l_idx]:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop,
            target_px=last_c + target, expires_at=_expires(now, 120),
            note="cumdelta_div bull",
        )]
    return []


# ---------------------------------------------------------------------------
# P. LIQUIDITY_SWEEP — price sweeps prior high/low then closes back inside
# ---------------------------------------------------------------------------
def detect_liquidity_sweep(arrs, bh, now, p):
    c = arrs["c"]; h = arrs["h"]; l = arrs["l"]
    look = p.get("sweep_lookback", 20)
    if len(c) < look + 2:
        return []
    prior_h = float(h[-(look + 1):-1].max())
    prior_l = float(l[-(look + 1):-1].min())
    last_h = float(h[-1]); last_l = float(l[-1]); last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    # Sweep high but close back below -> SHORT
    if last_h > prior_h and last_c < prior_h:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_h + 1.0,
            target_px=last_c - target, expires_at=_expires(now, 120),
            note=f"sweep top",
        )]
    if last_l < prior_l and last_c > prior_l:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_l - 1.0,
            target_px=last_c + target, expires_at=_expires(now, 120),
            note=f"sweep bot",
        )]
    return []


# ---------------------------------------------------------------------------
# Q. SCALP_TICK_VELOCITY — high volume bar + range expansion
# (Approximate "tick velocity" as bar volume > X times trailing average)
# ---------------------------------------------------------------------------
def detect_tick_velocity(arrs, bh, now, p):
    c = arrs["c"]; o = arrs["o"]; v = arrs["v"]
    if len(c) < 30:
        return []
    avg_v = float(v[-30:-1].mean())
    if avg_v <= 0:
        return []
    last_v = float(v[-1])
    if last_v < 3.0 * avg_v:
        return []
    # Enter direction of bar
    side = "LONG" if c[-1] > o[-1] else "SHORT"
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    stop_px = last_c - stop if side == "LONG" else last_c + stop
    target_px = last_c + target if side == "LONG" else last_c - target
    return [AltSetup(
        detected_at=now, side=side, entry_kind="immediate",
        entry_px=last_c, stop_px=stop_px, target_px=target_px,
        expires_at=_expires(now, 120),
        note=f"velocity v={last_v:.0f}/avg={avg_v:.0f}",
    )]


# ---------------------------------------------------------------------------
# R. NEWS_PAUSE — large vol burst, wait one bar for settle, then fade
# ---------------------------------------------------------------------------
def detect_news_pause(arrs, bh, now, p):
    c = arrs["c"]; o = arrs["o"]; h = arrs["h"]; l = arrs["l"]; v = arrs["v"]
    if len(c) < 30:
        return []
    # Last bar normal; prev bar had a large range (3x average TR) and high vol
    tr_avg = float((h[-30:-2] - l[-30:-2]).mean())
    last2_tr = float(h[-2] - l[-2])
    if last2_tr < 3.0 * tr_avg:
        return []
    # Did prev-2 bar move up or down? Fade it.
    prev2_dir = "LONG" if c[-2] > o[-2] else "SHORT"
    fade_side = "SHORT" if prev2_dir == "LONG" else "LONG"
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    stop_px = last_c - stop if fade_side == "LONG" else last_c + stop
    target_px = last_c + target if fade_side == "LONG" else last_c - target
    return [AltSetup(
        detected_at=now, side=fade_side, entry_kind="immediate",
        entry_px=last_c, stop_px=stop_px, target_px=target_px,
        expires_at=_expires(now, 120),
        note=f"news_pause fade {prev2_dir}",
    )]


# ---------------------------------------------------------------------------
# Bonus: simple TREND_FOLLOW — close > EMA20 and ema slope positive => LONG
# ---------------------------------------------------------------------------
def detect_trend_follow(arrs, bh, now, p):
    c = arrs["c"]
    if len(c) < 30:
        return []
    ema = _ema(c, 20)
    slope = float(ema[-1] - ema[-5])
    last_c = float(c[-1])
    e = float(ema[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if last_c > e and slope > 1.0:
        return [AltSetup(
            detected_at=now, side="LONG", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
            expires_at=_expires(now, 120), note="trend_follow up",
        )]
    if last_c < e and slope < -1.0:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
            expires_at=_expires(now, 120), note="trend_follow dn",
        )]
    return []


# ---------------------------------------------------------------------------
# Bonus: GAP_FADE - first 5 min after open, if price > 10pts above prev close
# fade to prev close.
# ---------------------------------------------------------------------------
def detect_gap_fade(arrs, bh, now, p):
    ts = arrs["ts"]; c = arrs["c"]
    if len(ts) < 5 or bh.prev_day_c is None:
        return []
    bar_dt = datetime.fromtimestamp(ts[-1] / 1e6, tz=timezone.utc)
    if not (bar_dt.hour == 22 and bar_dt.minute < 5):
        return []
    gap = float(c[-1]) - bh.prev_day_c
    if abs(gap) < 10.0:
        return []
    last_c = float(c[-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if gap > 0:
        return [AltSetup(
            detected_at=now, side="SHORT", entry_kind="immediate",
            entry_px=last_c, stop_px=last_c + stop,
            target_px=last_c - target, expires_at=_expires(now, 60 * 30),
            note=f"gap_fade up {gap:.1f}",
        )]
    return [AltSetup(
        detected_at=now, side="LONG", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c - stop,
        target_px=last_c + target, expires_at=_expires(now, 60 * 30),
        note=f"gap_fade dn {gap:.1f}",
    )]


# ============================================================================
# Strategy catalogue — list of (name, detector_callable, params, invert=False)
# ============================================================================
@dataclass
class StratConfig:
    name: str
    detector: Callable
    params: dict
    invert: bool = False
    # Time-of-day gate (optional)
    ny_session_only: bool = False
    skip_open: bool = False
    cooldown_secs: int = 10


def build_catalog() -> list[StratConfig]:
    V = []
    # A. continuation pullback (the simplest first test)
    V.append(StratConfig("A_CONT_PULL_10_20", detect_continuation_pullback,
                         {"impulse_bars": 4, "impulse_pts": 5.0,
                          "pull_pct": 0.5, "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("A_CONT_PULL_8_16", detect_continuation_pullback,
                         {"impulse_bars": 4, "impulse_pts": 5.0,
                          "pull_pct": 0.5, "stop_pts": 8.0, "target_pts": 16.0}))
    V.append(StratConfig("A_CONT_PULL_12_24", detect_continuation_pullback,
                         {"impulse_bars": 4, "impulse_pts": 5.0,
                          "pull_pct": 0.5, "stop_pts": 12.0, "target_pts": 24.0}))
    V.append(StratConfig("A_CONT_PULL_15_30", detect_continuation_pullback,
                         {"impulse_bars": 4, "impulse_pts": 5.0,
                          "pull_pct": 0.5, "stop_pts": 15.0, "target_pts": 30.0}))
    # B. momentum 3-bar
    V.append(StratConfig("B_MOM3_10_20", detect_momentum_3bar,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("B_MOM3_8_16", detect_momentum_3bar,
                         {"stop_pts": 8.0, "target_pts": 16.0}))
    V.append(StratConfig("B_MOM3_FADE_10_20", detect_momentum_3bar,
                         {"stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # C. range breakout
    V.append(StratConfig("C_RANGE_BR_10_10_20", detect_range_breakout,
                         {"range_bars": 10, "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("C_RANGE_BR_15_10_20", detect_range_breakout,
                         {"range_bars": 15, "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("C_RANGE_BR_20_12_24", detect_range_breakout,
                         {"range_bars": 20, "stop_pts": 12.0, "target_pts": 24.0}))
    V.append(StratConfig("C_RANGE_FADE_10_10_20", detect_range_breakout,
                         {"range_bars": 10, "stop_pts": 10.0, "target_pts": 20.0},
                         invert=True))
    # D. inside bar
    V.append(StratConfig("D_INSIDE_10_20", detect_inside_bar,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("D_INSIDE_8_16", detect_inside_bar,
                         {"stop_pts": 8.0, "target_pts": 16.0}))
    # E. VWAP pullback
    V.append(StratConfig("E_VWAP_PULL_10_20", detect_vwap_pullback,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("E_VWAP_PULL_8_16", detect_vwap_pullback,
                         {"stop_pts": 8.0, "target_pts": 16.0}))
    V.append(StratConfig("E_VWAP_PULL_FADE", detect_vwap_pullback,
                         {"stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # F. VWAP breakout
    V.append(StratConfig("F_VWAP_BR_10_20", detect_vwap_breakout,
                         {"vwap_bars": 5, "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("F_VWAP_BR_FADE", detect_vwap_breakout,
                         {"vwap_bars": 5, "stop_pts": 10.0, "target_pts": 20.0},
                         invert=True))
    # G. BB reversion
    V.append(StratConfig("G_BB_REV_10_20", detect_bb_reversion,
                         {"bb_n": 20, "bb_k": 2.0,
                          "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("G_BB_REV_8_16", detect_bb_reversion,
                         {"bb_n": 20, "bb_k": 2.5,
                          "stop_pts": 8.0, "target_pts": 16.0}))
    # H. BB breakout
    V.append(StratConfig("H_BB_BR_10_20", detect_bb_breakout,
                         {"bb_n": 20, "bb_k": 2.0,
                          "stop_pts": 10.0, "target_pts": 20.0}))
    # I. ORB 15
    V.append(StratConfig("I_ORB15_15_30", detect_orb_15min,
                         {"stop_pts": 15.0, "target_pts": 30.0}))
    V.append(StratConfig("I_ORB15_10_20", detect_orb_15min,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    # J. EMA pullback
    V.append(StratConfig("J_EMA_PULL_10_20", detect_ema_pullback,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("J_EMA_PULL_8_16", detect_ema_pullback,
                         {"stop_pts": 8.0, "target_pts": 16.0}))
    V.append(StratConfig("J_EMA_PULL_FADE", detect_ema_pullback,
                         {"stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # K. Pivot reversal
    V.append(StratConfig("K_PIVOT_REV_10_20", detect_pivot_reversal,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("K_PIVOT_REV_8_16", detect_pivot_reversal,
                         {"stop_pts": 8.0, "target_pts": 16.0}))
    # L. RSI extremes
    V.append(StratConfig("L_RSI_EXT_80_20_10_20", detect_rsi_extremes,
                         {"rsi_n": 14, "rsi_hi": 80, "rsi_lo": 20,
                          "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("L_RSI_EXT_75_25_10_20", detect_rsi_extremes,
                         {"rsi_n": 14, "rsi_hi": 75, "rsi_lo": 25,
                          "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("L_RSI_EXT_FOLLOW", detect_rsi_extremes,
                         {"rsi_n": 14, "rsi_hi": 80, "rsi_lo": 20,
                          "stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # M. RSI divergence
    V.append(StratConfig("M_RSI_DIV_10_20", detect_rsi_divergence,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    # N. ATR expansion
    V.append(StratConfig("N_ATR_EXP_10_20", detect_atr_expansion,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("N_ATR_EXP_FADE", detect_atr_expansion,
                         {"stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # O. cumdelta divergence
    V.append(StratConfig("O_CUMDELTA_DIV_10_20", detect_cumdelta_div,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("O_CUMDELTA_DIV_FADE", detect_cumdelta_div,
                         {"stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # P. liquidity sweep
    V.append(StratConfig("P_SWEEP_REV_10_20", detect_liquidity_sweep,
                         {"sweep_lookback": 20, "stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("P_SWEEP_REV_8_16", detect_liquidity_sweep,
                         {"sweep_lookback": 15, "stop_pts": 8.0, "target_pts": 16.0}))
    V.append(StratConfig("P_SWEEP_FOLLOW", detect_liquidity_sweep,
                         {"sweep_lookback": 20, "stop_pts": 10.0, "target_pts": 20.0},
                         invert=True))
    # Q. tick velocity
    V.append(StratConfig("Q_VELOCITY_10_20", detect_tick_velocity,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Q_VELOCITY_FADE", detect_tick_velocity,
                         {"stop_pts": 10.0, "target_pts": 20.0}, invert=True))
    # R. news pause
    V.append(StratConfig("R_NEWS_PAUSE_10_20", detect_news_pause,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    # Bonus: trend follow + gap fade
    V.append(StratConfig("X_TREND_FOLLOW_10_20", detect_trend_follow,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("X_GAP_FADE_10_20", detect_gap_fade,
                         {"stop_pts": 10.0, "target_pts": 20.0}))
    return V


# ============================================================================
# Strategy runtime state + execution
# ============================================================================
@dataclass
class StratState:
    cfg: StratConfig
    pending: list = field(default_factory=list)
    active_trade: Optional[dict] = None
    completed: list = field(default_factory=list)
    last_close_ts: Optional[datetime] = None
    recent_keys: deque = field(default_factory=lambda: deque(maxlen=200))
    cur_day: Optional[str] = None
    daily_pnl: float = 0.0


def _apply_invert(setup: AltSetup) -> AltSetup:
    """Flip side; keep orig_side as the original (so limit-approach logic
    still works) for limit entries. For immediate entries we don't need
    orig_side."""
    new = copy.copy(setup)
    new.side = "SHORT" if setup.side == "LONG" else "LONG"
    # Recompute stop/target around the SAME entry price for the new side.
    # Stop distance and target distance preserved.
    stop_dist = abs(setup.entry_px - setup.stop_px)
    tgt_dist = abs(setup.entry_px - setup.target_px)
    if new.side == "LONG":
        new.stop_px = setup.entry_px - stop_dist
        new.target_px = setup.entry_px + tgt_dist
    else:
        new.stop_px = setup.entry_px + stop_dist
        new.target_px = setup.entry_px - tgt_dist
    return new


def _check_exit_vec(at, bid, ask, ts, start):
    """Vectorized exit scan from start. Returns (idx, exit_px, reason) or None tuple."""
    side = at["side"]
    entry_ts_us = at["entry_ts_us"]
    sp, tp = at["stop_px"], at["target_px"]
    if side == "LONG":
        stop_hit = bid[start:] <= sp
        tgt_hit = bid[start:] >= tp
    else:
        stop_hit = ask[start:] >= sp
        tgt_hit = ask[start:] <= tp
    stop_idx = (start + int(np.argmax(stop_hit))) if stop_hit.any() else None
    tgt_idx = (start + int(np.argmax(tgt_hit))) if tgt_hit.any() else None
    # Target needs hold >= MIN_TARGET_HOLD_SECONDS
    if tgt_idx is not None:
        hold_us = ts[tgt_idx] - entry_ts_us
        if hold_us < MIN_TARGET_HOLD_SECONDS * US_PER_SEC:
            min_ts = entry_ts_us + MIN_TARGET_HOLD_SECONDS * US_PER_SEC
            valid = (ts[start:] >= min_ts) & tgt_hit
            tgt_idx = (start + int(np.argmax(valid))) if valid.any() else None
    timeout_us = entry_ts_us + MAX_HOLD_SECS * US_PER_SEC
    timeout_arr = ts[start:] >= timeout_us
    timeout_idx = (start + int(np.argmax(timeout_arr))) if timeout_arr.any() else None
    cands = []
    if stop_idx is not None: cands.append((stop_idx, "stop"))
    if tgt_idx is not None: cands.append((tgt_idx, "target"))
    if timeout_idx is not None: cands.append((timeout_idx, "timeout"))
    if not cands:
        return (None, None, None)
    cands.sort(key=lambda x: x[0])
    idx, reason = cands[0]
    if reason == "stop":
        exit_px = float(sp) - STOP_SLIP_PTS if side == "LONG" else float(sp) + STOP_SLIP_PTS
    elif reason == "target":
        exit_px = float(tp)
    else:
        exit_px = float((bid[idx] + ask[idx]) / 2.0)
    return (idx, exit_px, reason)


def _check_trigger(setup, mid, start):
    """Find first index in mid[start:] where setup triggers. Returns idx or None.

    Immediate: fires at start (the next tick after detection).
    Limit: arming-then-trigger same as existing harness.
    """
    if setup.entry_kind == "immediate":
        return start if start < len(mid) else None
    # limit kind
    pe = setup.entry_px
    approach = setup.orig_side or setup.side
    seg = mid[start:]
    if not setup.entry_armed:
        if approach == "LONG":
            arm = seg > pe
        else:
            arm = seg < pe
        if not arm.any():
            return None
        arm_i = int(np.argmax(arm))
        setup.entry_armed = True
        trig_start = arm_i + 1
    else:
        trig_start = 0
    if trig_start >= len(seg):
        return None
    seg2 = seg[trig_start:]
    if approach == "LONG":
        trig = seg2 <= pe
    else:
        trig = seg2 >= pe
    if not trig.any():
        return None
    return start + trig_start + int(np.argmax(trig))


def _time_blocked(cfg: StratConfig, ts: datetime) -> bool:
    hh, mm = ts.hour, ts.minute
    if cfg.ny_session_only:
        t = hh * 60 + mm
        if t < 13 * 60 + 30 or t >= 20 * 60:
            return True
    if cfg.skip_open:
        if hh == 22 and mm < 30:
            return True
    return False


def _open_trade(ss: StratState, setup, fire_idx, bid, ask, ts_us):
    cfg = ss.cfg
    ts = datetime.fromtimestamp(ts_us[fire_idx] / 1e6, tz=timezone.utc)
    if _time_blocked(cfg, ts):
        return False
    if ss.last_close_ts is not None:
        if (ts - ss.last_close_ts).total_seconds() < cfg.cooldown_secs:
            return False
    if setup.side == "LONG":
        entry_px = float(ask[fire_idx])
    else:
        entry_px = float(bid[fire_idx])
    ss.active_trade = {
        "entry_ts": ts,
        "entry_ts_us": int(ts_us[fire_idx]),
        "side": setup.side,
        "entry_px": entry_px,
        "stop_px": float(setup.stop_px),
        "target_px": float(setup.target_px),
        "note": setup.note,
    }
    setup.used = True
    return True


def _record_exit(ss: StratState, exit_ts_us, exit_px, reason):
    at = ss.active_trade
    side = at["side"]
    if side == "LONG":
        pnl_pts = exit_px - at["entry_px"]
    else:
        pnl_pts = at["entry_px"] - exit_px
    pnl_usd = pnl_pts * N_MNQ * MNQ_PER_PT - COMMISSION_RT
    exit_ts = datetime.fromtimestamp(exit_ts_us / 1e6, tz=timezone.utc)
    rec = {
        "entry_ts": at["entry_ts"], "exit_ts": exit_ts,
        "side": side, "entry_px": at["entry_px"], "exit_px": exit_px,
        "stop_px": at["stop_px"], "target_px": at["target_px"],
        "exit_reason": reason,
        "hold_s": (exit_ts - at["entry_ts"]).total_seconds(),
        "pnl_pts": pnl_pts, "pnl_usd": pnl_usd,
        "note": at.get("note", ""),
    }
    ss.completed.append(rec)
    ss.active_trade = None
    ss.last_close_ts = exit_ts


def _process_segment(ss: StratState, bid, ask, mid, ts_us, seg_start, seg_end):
    cur = seg_start
    while cur < seg_end:
        if ss.active_trade is not None:
            idx, exit_px, reason = _check_exit_vec(
                ss.active_trade, bid[:seg_end], ask[:seg_end], ts_us[:seg_end], cur)
            if idx is None:
                return
            _record_exit(ss, int(ts_us[idx]), exit_px, reason)
            cur = idx + 1
            continue
        if not ss.pending:
            return
        # Expire stale setups
        now_us = ts_us[cur]
        ss.pending = [s for s in ss.pending
                       if (not s.used) and
                       (int(s.expires_at.timestamp() * US_PER_SEC) > now_us)]
        if not ss.pending:
            return
        earliest_idx = None
        earliest_setup = None
        for s in ss.pending:
            if s.used:
                continue
            fi = _check_trigger(s, mid[:seg_end], cur)
            if fi is not None and (earliest_idx is None or fi < earliest_idx):
                earliest_idx = fi
                earliest_setup = s
        if earliest_idx is None:
            return
        opened = _open_trade(ss, earliest_setup, earliest_idx, bid, ask, ts_us)
        if not opened:
            earliest_setup.used = True
            cur = earliest_idx + 1
            continue
        cur = earliest_idx + 1


def _on_closed_bar(ss: StratState, arrs, bh: BarHistory, now: datetime):
    cfg = ss.cfg
    new_setups = cfg.detector(arrs, bh, now, cfg.params)
    if not new_setups:
        return
    for s in new_setups:
        if cfg.invert:
            s = _apply_invert(s)
        # Dedupe by (entry rounded, side) against active pending list
        key = (round(s.entry_px, 1), s.side, s.note[:8])
        if key in ss.recent_keys:
            continue
        already = False
        for ex in ss.pending:
            if ex.used:
                continue
            if (round(ex.entry_px, 1), ex.side, ex.note[:8]) == key:
                already = True
                break
        if already:
            continue
        ss.pending.append(s)
        ss.recent_keys.append(key)


# ============================================================================
# Streaming driver
# ============================================================================
def run(strats: list[StratConfig], *, start_offset: int = 0,
        end_after_ticks: Optional[int] = None, label: str = "RUN"):
    print(f"\n[{label}] starting {len(strats)} strats, offset={start_offset:,}",
          flush=True)
    states = {s.name: StratState(cfg=s) for s in strats}
    bh = BarHistory(keep=HISTORY_BARS)
    # Current bar accumulator
    cur_min = None
    cur_o = cur_h = cur_l = cur_c = float("nan")
    cur_v = 0
    n_ticks = 0
    n_bars = 0
    t0 = time.time()
    last_progress = t0
    ticks_since = 0
    states_list = list(states.values())

    for chunk in iter_tick_chunks(TICK_CSV, start_offset=start_offset):
        ts_us = chunk["ts"]
        bid = chunk["bid"]
        ask = chunk["ask"]
        mid = chunk["mid"]
        chunk_len = len(ts_us)
        minutes = ts_us // US_PER_MIN
        if cur_min is None:
            prev_min = int(minutes[0])
        else:
            prev_min = cur_min
        diff_idxs = np.where(np.diff(np.concatenate([[prev_min], minutes])) != 0)[0]

        seg_start = 0
        for new_min_idx in diff_idxs:
            # Accumulate ticks belonging to the PRIOR minute
            if seg_start < new_min_idx:
                slm = mid[seg_start:new_min_idx]
                if cur_min is None:
                    cur_min = int(minutes[seg_start])
                    cur_o = float(slm[0]); cur_h = float(slm.max())
                    cur_l = float(slm.min()); cur_c = float(slm[-1])
                    cur_v = int(len(slm))
                else:
                    cur_h = max(cur_h, float(slm.max()))
                    cur_l = min(cur_l, float(slm.min()))
                    cur_c = float(slm[-1])
                    cur_v += int(len(slm))
            # Process segment for each strategy BEFORE closing the bar
            for ss in states_list:
                _process_segment(ss, bid, ask, mid, ts_us, seg_start, new_min_idx)
            # Close the current bar
            closed_ts_us = cur_min * US_PER_MIN
            bh.append(closed_ts_us, cur_o, cur_h, cur_l, cur_c, cur_v)
            n_bars += 1
            # Detection. `now` represents the BAR CLOSE time (= next-min
            # boundary), which is also the moment new ticks start arriving.
            if len(bh.c) >= 5:
                arrs = bh.arrays()
                bar_close_ts = datetime.fromtimestamp(
                    (closed_ts_us + US_PER_MIN) / 1e6, tz=timezone.utc)
                for ss in states_list:
                    _on_closed_bar(ss, arrs, bh, bar_close_ts)
            # Start new bar
            cur_min = int(minutes[new_min_idx])
            cur_o = float(mid[new_min_idx])
            cur_h = cur_o; cur_l = cur_o; cur_c = cur_o
            cur_v = 1
            seg_start = new_min_idx

        if seg_start < chunk_len:
            slm = mid[seg_start:chunk_len]
            if cur_min is None:
                cur_min = int(minutes[seg_start])
                cur_o = float(slm[0]); cur_h = float(slm.max())
                cur_l = float(slm.min()); cur_c = float(slm[-1])
                cur_v = int(len(slm))
            else:
                cur_h = max(cur_h, float(slm.max()))
                cur_l = min(cur_l, float(slm.min()))
                cur_c = float(slm[-1])
                cur_v += int(len(slm))
            for ss in states_list:
                _process_segment(ss, bid, ask, mid, ts_us, seg_start, chunk_len)

        n_ticks += chunk_len
        ticks_since += chunk_len
        if ticks_since >= PROGRESS_TICKS:
            now = time.time()
            rate = ticks_since / max(0.001, now - last_progress)
            last_progress = now
            ticks_since = 0
            tc = {k: len(s.completed) for k, s in states.items()}
            best = max(tc.items(), key=lambda kv: kv[1])
            print(f"  [{label}] {n_ticks/1e6:.1f}M ticks  "
                  f"{n_bars:,} bars  rate={rate/1e6:.2f}M/s  "
                  f"best={best[0]}({best[1]} tr)  "
                  f"elapsed={now-t0:.0f}s", flush=True)
        if end_after_ticks is not None and n_ticks >= end_after_ticks:
            break

    print(f"[{label}] done. ticks={n_ticks:,} bars={n_bars:,} "
          f"elapsed={time.time()-t0:.0f}s", flush=True)
    return states


# ============================================================================
# Reporting
# ============================================================================
def summarize(ss: StratState) -> dict:
    trades = ss.completed
    if not trades:
        return {"name": ss.cfg.name, "trades": 0, "wr": 0.0, "pnl": 0.0,
                "per_day": 0.0, "per_trade": 0.0, "n_days": 0,
                "max_dd": 0.0, "worst_day": 0.0, "best_day": 0.0,
                "trades_per_day": 0.0, "sharpe": 0.0}
    df = pd.DataFrame(trades)
    df["day"] = pd.to_datetime(df["exit_ts"]).dt.date
    daily = df.groupby("day")["pnl_usd"].sum()
    pnl = float(df["pnl_usd"].sum())
    wins = int((df["pnl_usd"] > 0).sum())
    n = len(df)
    wr = wins / n
    n_days = len(daily)
    per_day = pnl / max(1, n_days)
    per_trade = pnl / max(1, n)
    eq = df["pnl_usd"].cumsum().to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak).min() if len(eq) else 0.0
    sharpe = (daily.mean() / daily.std()) if (len(daily) > 1 and daily.std() > 0) else 0.0
    return {
        "name": ss.cfg.name, "trades": n, "wr": wr, "pnl": pnl,
        "per_day": per_day, "per_trade": per_trade, "n_days": n_days,
        "max_dd": float(dd), "worst_day": float(daily.min()),
        "best_day": float(daily.max()),
        "trades_per_day": n / max(1, n_days),
        "sharpe": float(sharpe),
    }


def write_report(out_path, results_60d, results_full=None):
    lines = []
    lines.append("# Alternative-Strategy Bake-Off (MNQ)\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n\n")
    lines.append("Execution model — IDENTICAL to research/comprehensive_backtest.py:\n")
    lines.append("- Marketable LIMIT entry (LONG fills at ASK, SHORT fills at BID)\n")
    lines.append("- Stop-MARKET exit with 0.5pt slip against trader\n")
    lines.append("- LIMIT target — exact fill only when bid (LONG)/ask (SHORT) reaches level\n")
    lines.append("- 10s cooldown between trades, $0.74 round-trip commission, 1 MNQ\n\n")
    lines.append("## 60-day subset results (2026-04-18 to 2026-06-17)\n\n")
    sums = [summarize(s) for s in results_60d.values()]
    sums.sort(key=lambda s: s["pnl"], reverse=True)
    lines.append("| Strategy | Trades | WR | P&L $ | $/day | $/trade | "
                  "Tr/day | Max DD | Worst day | Best day | Sharpe |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for s in sums:
        lines.append(
            f"| {s['name']} | {s['trades']:,} | {s['wr']*100:.1f}% | "
            f"${s['pnl']:,.0f} | ${s['per_day']:,.0f} | ${s['per_trade']:.2f} | "
            f"{s['trades_per_day']:.1f} | ${s['max_dd']:,.0f} | "
            f"${s['worst_day']:,.0f} | ${s['best_day']:,.0f} | "
            f"{s['sharpe']:.2f} |\n")
    # Best 5
    profitable = [s for s in sums if s["pnl"] > 0]
    lines.append("\n## Verdict\n\n")
    if profitable:
        lines.append(f"**{len(profitable)} strategies were net profitable** "
                     f"on the 60-day subset. Top:\n\n")
        for s in profitable[:5]:
            lines.append(f"- **{s['name']}**: ${s['pnl']:,.0f} total, "
                         f"${s['per_day']:,.0f}/day, "
                         f"WR {s['wr']*100:.1f}%, "
                         f"{s['trades_per_day']:.1f} tr/day, "
                         f"max DD ${s['max_dd']:,.0f}\n")
    else:
        lines.append("**No strategy was profitable on the 60-day subset.** "
                      "All standard structural strategies tested have a "
                      "negative expectancy under realistic execution.\n")
    if results_full:
        lines.append("\n## Full-data confirmation\n\n")
        sums_f = [summarize(s) for s in results_full.values()]
        sums_f.sort(key=lambda s: s["pnl"], reverse=True)
        lines.append("| Strategy | Trades | WR | P&L $ | $/day | $/trade | "
                      "Tr/day | Max DD | Worst day | Best day | Sharpe |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for s in sums_f:
            lines.append(
                f"| {s['name']} | {s['trades']:,} | {s['wr']*100:.1f}% | "
                f"${s['pnl']:,.0f} | ${s['per_day']:,.0f} | ${s['per_trade']:.2f} | "
                f"{s['trades_per_day']:.1f} | ${s['max_dd']:,.0f} | "
                f"${s['worst_day']:,.0f} | ${s['best_day']:,.0f} | "
                f"{s['sharpe']:.2f} |\n")
    Path(out_path).write_text("".join(lines))
    print(f"[REPORT] wrote {out_path}")


def get_60d_offset() -> int:
    path = TICK_CSV
    size = os.path.getsize(path)
    target = b"20260418"
    with open(path, "rb") as f:
        lo, hi = 0, size
        while hi - lo > 4096:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()
            line = f.readline()
            if not line:
                hi = mid
                continue
            d = line[:8]
            if d < target:
                lo = mid
            else:
                hi = mid
    return lo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="Run on full data (slow)")
    parser.add_argument("--only", default=None,
                        help="Restrict to strategy name (debug)")
    parser.add_argument("--out-dir", default="/home/user/HFTBot/research")
    args = parser.parse_args()

    strats = build_catalog()
    if args.only:
        strats = [s for s in strats if args.only.upper() in s.name.upper()]
        print(f"Filtered to {len(strats)} strategies matching {args.only!r}")
    print(f"Catalog: {len(strats)} strategies")
    for s in strats:
        print(f"  {s.name}  invert={s.invert}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    offset_60 = get_60d_offset()
    print(f"60-day offset: {offset_60:,}")

    results_60d = run(strats, start_offset=offset_60, label="60D")
    rows = [summarize(s) for s in results_60d.values()]
    df = pd.DataFrame(rows).sort_values("pnl", ascending=False)
    df.to_csv(out_dir / "alt_summary_60d.csv", index=False)
    print("\nTop 10 (60d):")
    print(df.head(10).to_string())

    results_full = None
    if args.full:
        # Run top-positive strategies on full data
        winners = df[df["pnl"] > 0]["name"].tolist()
        if not winners:
            # Run top 5 anyway for confirmation that nothing works
            winners = df.head(5)["name"].tolist()
        print(f"Full-data run on: {winners}")
        strats_top = [s for s in strats if s.name in winners]
        results_full = run(strats_top, start_offset=0, label="FULL")
        rows_f = [summarize(s) for s in results_full.values()]
        df_f = pd.DataFrame(rows_f).sort_values("pnl", ascending=False)
        df_f.to_csv(out_dir / "alt_summary_full.csv", index=False)
        print("\nFull-data results:")
        print(df_f.to_string())

    write_report(out_dir / "alternative_strategies_results.md",
                 results_60d, results_full)


if __name__ == "__main__":
    main()

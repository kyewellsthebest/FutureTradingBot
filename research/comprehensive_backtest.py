"""Comprehensive backtest battery for the MNQ pullback (inverse-fade) bot.

Runs ALL variants in a single streaming pass over the tick data. Each
variant has independent state (pending setups, active trade, completed
trades, daily P&L, etc.). The tick stream is read in 1M-row chunks via
pandas. On every closed 1-min bar we update the bar history. For every
tick we let each variant attempt arming + trigger.

Strategy code is imported from bot.pullback_strategy. We call
ps.detect_pullback_setup() directly to keep the strategy logic in one
place; the arming + trigger gates are mirrored inline so we can drive
them from tick (bid/ask) rather than a single price.

Broker execution model:
  - "marketable LIMIT" entry: at fire time, LONG fills at the tick ask;
    SHORT fills at the tick bid. (live bot's bracket bumps the LIMIT
    1pt past ask/bid so it crosses; paper books at the actual fill.)
  - Stop-MARKET exits: LONG closes at bid - 0.5pt slip, SHORT at
    ask + 0.5pt slip.
  - LIMIT target: LONG fills when bid >= target (at target px exactly);
    SHORT fills when ask <= target.
  - Timeout: midpoint at the timeout tick.
  - Round-trip commission: $0.74.

USAGE:
  # 60-day subset (default, ~9 mins)
  python -m research.comprehensive_backtest

  # full data set (~2.5h)
  python -m research.comprehensive_backtest --full

  # run only TOP-5 refined variants on full data
  python -m research.comprehensive_backtest --top5-full

Output:
  research/backtest_results.md        -- comparison report
  research/backtest_summary.csv       -- per-variant summary
  research/backtest_trades_<v>.csv    -- per-variant trade log (top 5 only)
"""
from __future__ import annotations
import argparse
import os
import sys
import csv
import time
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")

# ----- Configure strategy env BEFORE importing bot.pullback_strategy -----
# We force the canonical inverse-fade live config; per-variant overrides
# are passed through `params` to detect_pullback_setup so they don't need
# env mutation.
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")    # baseline is OFF; per-variant flips this in code
os.environ.setdefault("BOT_TRADING_HOURS", "cme")
os.environ.setdefault("FIB_AUTO_DLL", "0")
os.environ.setdefault("PAPER_STOP_SLIP_PTS", "0.0")   # we apply slip in our exec model directly
os.environ.setdefault("PAPER_SPREAD_PTS", "0.0")

import bot.pullback_strategy as ps  # noqa: E402

# ------------- Data + cost constants -------------
TICK_CSV = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
CHUNK_SIZE = 1_000_000
COMMISSION_RT = 0.74
MNQ_PER_PT = 2.0
N_MNQ = 1
STOP_SLIP_PTS = 0.5
ENTRY_BUFFER_PTS = 1.0        # marketable LIMIT bump
MAX_WAIT_SECS = ps.MAX_WAIT_SECS
MAX_HOLD_SECS = ps.MAX_HOLD_SECS
MIN_TARGET_HOLD_SECONDS = ps.MIN_TARGET_HOLD_SECONDS
HISTORY_BARS = 240            # 4h lookback (covers HTF_k=60 + warmup)
PROGRESS_TICKS = 5_000_000


# ============================================================================
# Variant definition
# ============================================================================
@dataclass
class VariantConfig:
    name: str
    # Strategy params (override defaults of detect_pullback_setup)
    impulse_pts: float = 5.0
    impulse_bars: int = 4
    pull_pct: float = 0.236
    stop_pts: float = 10.0
    target_pts: float = 20.0
    # Execution
    arming: bool = True           # False = original phantom-firing trigger
    marketable_limit: bool = True # False = strict LIMIT (paper at entry level)
    # Filters
    htf_filter: bool = False
    htf_k: int = 30
    atr_min: Optional[float] = None       # block setups when 20-bar ATR < x
    atr_max: Optional[float] = None       # block when 20-bar ATR > x
    skip_open: bool = False               # block first 30min after 22:00 UTC
    skip_close: bool = False              # block last 30 min before 21:00 UTC
    ny_session_only: bool = False         # 13:30-20:00 UTC only
    avoid_lunch: bool = False             # block 16:00-17:00 UTC
    cb_n_losses: Optional[int] = None     # circuit breaker after N consec losses
    cb_pause_mins: int = 30
    daily_dd_stop: Optional[float] = None # stop trading the day after -$X
    cooldown_secs: int = 10

    def params_dict(self) -> dict:
        return {
            "IMPULSE_PTS": self.impulse_pts,
            "IMPULSE_WINDOW_BARS": self.impulse_bars,
            "PULLBACK_PCT": self.pull_pct,
            "STOP_PTS": self.stop_pts,
            "TARGET_PTS": self.target_pts,
            "INVERT": True,
        }


# ============================================================================
# Variant runtime state
# ============================================================================
@dataclass
class VariantState:
    cfg: VariantConfig
    pending_setups: list = field(default_factory=list)
    active_trade: Optional[dict] = None    # {entry_ts, side, entry_px, stop, tgt, ...}
    completed_trades: list = field(default_factory=list)
    recent_keys: deque = field(default_factory=lambda: deque(maxlen=200))
    last_close_ts: Optional[datetime] = None
    consecutive_losses: int = 0
    pause_until_ts: Optional[datetime] = None
    daily_pnl: float = 0.0
    daily_dd_tripped: bool = False
    cur_day: Optional[str] = None
    # cached HTF trend computed once per bar (lazy)
    cached_htf_trend: str = "FLAT"
    cached_htf_at: Optional[datetime] = None


# ============================================================================
# Tick parsing (vectorized over a pandas chunk)
# ============================================================================
# Unit constants for the timestamp arithmetic. We use MICROSECONDS as
# the integer unit everywhere because pandas stores datetime64[us] and
# microsecond ints comfortably fit in int64.
US_PER_SEC = 1_000_000
US_PER_MIN = 60 * US_PER_SEC


def iter_tick_chunks(path: str, *, start_offset: int = 0):
    """Yield parsed chunks, each with ts(us-since-epoch int64), bid, ask, mid.

    Returns a dict of numpy arrays (avoid building a DataFrame per chunk
    which is slow).
    """
    # Approach: read CSV with a custom sep regex won't work; use sep=';'
    # then split the first column with vectorized numpy ops.
    # The line format: "YYYYMMDD HHMMSS uuuuuuu;mid;bid;ask;vol"
    # The first field is a fixed-width 22-char string:
    #   8 (date) + 1 (space) + 6 (time) + 1 (space) + 7 (us-extra) = 23
    # but only first 6 digits of the 7 are microseconds.
    # We can slice fixed positions.
    f = open(path, "r")
    if start_offset > 0:
        f.seek(start_offset)
        f.readline()   # discard partial line
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
        dt = raw["dt"].values   # numpy array of strings
        # Vectorized fixed-position parse via numpy
        # Convert each "YYYYMMDD HHMMSS uuuuuuu" -> us int.
        # Using np.frombuffer trick: each string is variable length but
        # fixed 23 chars in this dataset. View as a 2D byte array.
        n = len(dt)
        # Convert to fixed-length numpy bytes
        dt_arr = np.array(dt, dtype="S23")
        # View as 2D byte array (n, 23)
        b = dt_arr.view(np.uint8).reshape(n, 23)
        # Date YYYYMMDD: positions 0-7
        # Time HHMMSS:   positions 9-14
        # Us extra:      positions 16-22 (7 digits, use first 6)
        # Build integers using byte arithmetic (subtract '0' = 48)
        def digits_to_int(slc):
            # slc: (n, k) byte array of ASCII digits
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
        us = digits_to_int(b[:, 16:22])   # 6 microsec digits
        # Build a YYYYMMDDHHMMSS string array efficiently — better:
        # we compute epoch microseconds directly. But months-to-days is
        # variable. Use pandas to handle the date-portion once via a
        # SHARED conversion per unique YYYYMMDD value (typically <= 5-7
        # unique dates per 1M-tick chunk since 1M ticks span ~5 days).
        # Compute date_int = yr*10000 + mo*100 + dy
        date_int = (yr * 10000 + mo * 100 + dy).astype(np.int64)
        # Cache date_int -> epoch_us_for_midnight
        unique_dates = np.unique(date_int)
        date_us_map = {}
        for di in unique_dates:
            di_str = str(int(di))
            tsmid = pd.Timestamp(di_str, tz="UTC")
            date_us_map[int(di)] = int(tsmid.value // 1000)  # ns->us
        # Map each row's date_int to its midnight-us
        midnight_us = np.empty(n, dtype=np.int64)
        # Build by lookup; use np.searchsorted if many unique
        sorted_keys = np.array(sorted(date_us_map.keys()), dtype=np.int64)
        vals = np.array([date_us_map[int(k)] for k in sorted_keys], dtype=np.int64)
        idx = np.searchsorted(sorted_keys, date_int)
        midnight_us = vals[idx]
        # Total us = midnight + (h*3600 + m*60 + s)*1e6 + us
        ts_us = midnight_us + (hr * 3600 + mn * 60 + sc) * US_PER_SEC + us
        yield {
            "ts": ts_us,
            "bid": raw["bid"].values.astype(np.float64),
            "ask": raw["ask"].values.astype(np.float64),
            "mid": raw["mid"].values.astype(np.float64),
        }


# ============================================================================
# Bar building (1-min OHLC from ticks)
# ============================================================================
class BarBuilder:
    """Roll ticks into 1-min OHLC bars. Emits a bar when ts crosses minute.

    Keeps a rolling DataFrame of the last `keep` bars. Designed for repeated
    appends and tail-slice reads.
    """
    def __init__(self, keep: int = HISTORY_BARS):
        self.keep = keep
        self.cur_minute: Optional[int] = None  # epoch minute
        self.cur_o = self.cur_h = self.cur_l = self.cur_c = np.nan
        self.cur_v = 0
        # Pre-allocated arrays for speed
        self._buf = []         # list of (ts_ns, o, h, l, c, v)
        # Cached DataFrame view (rebuilt lazily)
        self._df_cache: Optional[pd.DataFrame] = None
        self._dirty = False

    def add_tick(self, ts_ns: int, mid: float) -> Optional[pd.Series]:
        """Add a tick. If it closes a previous bar, return that bar series."""
        minute = ts_ns // US_PER_MIN
        if self.cur_minute is None:
            self.cur_minute = minute
            self.cur_o = self.cur_h = self.cur_l = self.cur_c = mid
            self.cur_v = 1
            return None
        if minute == self.cur_minute:
            if mid > self.cur_h: self.cur_h = mid
            if mid < self.cur_l: self.cur_l = mid
            self.cur_c = mid
            self.cur_v += 1
            return None
        # Minute rolled: emit closed bar.
        closed_ts_ns = self.cur_minute * US_PER_MIN
        closed = (closed_ts_ns, self.cur_o, self.cur_h, self.cur_l, self.cur_c, self.cur_v)
        self._buf.append(closed)
        if len(self._buf) > self.keep:
            self._buf = self._buf[-self.keep:]
        self._dirty = True
        # Start new bar (may span multiple gap minutes — for our purposes
        # we just start the new bar on this minute).
        self.cur_minute = minute
        self.cur_o = self.cur_h = self.cur_l = self.cur_c = mid
        self.cur_v = 1
        # Return closed as a Series for ps.detect_pullback_setup compat.
        # closed_ts_ns is in microseconds; convert to ns for pd.Timestamp.
        ts = pd.Timestamp(closed_ts_ns * 1000, tz="UTC")
        return pd.Series(
            {"open": closed[1], "high": closed[2], "low": closed[3],
             "close": closed[4], "volume": closed[5]}, name=ts)

    def as_dataframe(self) -> pd.DataFrame:
        # Cheap path: cached and not dirty
        if self._df_cache is not None and not self._dirty:
            return self._df_cache
        if not self._buf:
            self._df_cache = pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"])
            self._dirty = False
            return self._df_cache
        # Full rebuild when buf size changed or first build
        arr = np.asarray(self._buf, dtype=np.float64)
        idx = pd.to_datetime(arr[:, 0].astype(np.int64) * 1000, utc=True)
        self._df_cache = pd.DataFrame({
            "open":   arr[:, 1],
            "high":   arr[:, 2],
            "low":    arr[:, 3],
            "close":  arr[:, 4],
            "volume": arr[:, 5],
        }, index=idx)
        self._dirty = False
        return self._df_cache

    def numpy_arrays(self) -> dict:
        """Return raw numpy arrays — cheap, no DataFrame construction.

        For helpers that don't need pandas (HTF trend, ATR), this is
        much faster.
        """
        if not self._buf:
            return {"high": np.array([]), "low": np.array([]),
                    "close": np.array([]), "open": np.array([])}
        arr = np.asarray(self._buf, dtype=np.float64)
        return {
            "open":  arr[:, 1],
            "high":  arr[:, 2],
            "low":   arr[:, 3],
            "close": arr[:, 4],
        }


# ============================================================================
# Helpers — ATR, HTF trend, time-of-day filters
# ============================================================================
def atr_n(bars: pd.DataFrame, n: int = 20) -> float:
    if len(bars) < n + 1:
        return float("nan")
    h = bars["high"].to_numpy()[-(n+1):]
    l = bars["low"].to_numpy()[-(n+1):]
    c = bars["close"].to_numpy()[-(n+1):]
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    return float(tr[1:].mean())


def _utc_hm(ts: datetime) -> tuple:
    return ts.hour, ts.minute


def _time_blocked(cfg: VariantConfig, ts: datetime) -> bool:
    """Apply time-of-day filters. ts is UTC."""
    hh, mm = _utc_hm(ts)
    dow = ts.weekday()  # 0=Mon ... 6=Sun
    if cfg.ny_session_only:
        # 13:30 - 20:00 UTC
        t = hh * 60 + mm
        if t < 13 * 60 + 30 or t >= 20 * 60:
            return True
    if cfg.skip_open:
        # CME open Sun 22:00 UTC, weekdays 22:00 UTC. Block 22:00 - 22:30.
        if hh == 22 and mm < 30:
            return True
    if cfg.skip_close:
        # CME close 21:00 UTC. Block 20:30 - 21:00.
        if hh == 20 and mm >= 30:
            return True
    if cfg.avoid_lunch:
        # Block 16:00 - 17:00 UTC
        if hh == 16:
            return True
    return False


# ============================================================================
# Bar-close handlers — shared work + per-variant filtering
# ============================================================================
def detect_setups_for_param_groups(bars_df: pd.DataFrame, now: datetime,
                                    param_groups: dict) -> dict:
    """Call ps.detect_pullback_setup once per unique (impulse_pts,
    impulse_bars, pull_pct, stop_pts, target_pts) param tuple. Returns
    {tuple_key: setup_or_None}.
    """
    out = {}
    for k, sample_cfg in param_groups.items():
        out[k] = ps.detect_pullback_setup(bars_df, now,
                                          params=sample_cfg.params_dict())
    return out


# Pre-computed per-bar helpers
@dataclass
class BarContext:
    """Bundle of derived metrics computed ONCE per closed bar,
    shared across all variants."""
    atr20: float = float("nan")
    htf_k15: str = "FLAT"
    htf_k30: str = "FLAT"
    htf_k60: str = "FLAT"
    setups_by_param_key: dict = field(default_factory=dict)


def _htf_trend_numpy(highs, lows, k):
    """Vectorized fractal-pivot HTF trend.

    For each t in [k, n-k), bar t is a "pivot high" iff highs[t] equals
    the max of highs[t-k:t+k+1]. Same logic for pivot low.

    Use scipy maxima or numpy stride tricks for speed.
    """
    n = len(highs)
    if n < 2 * k + 1:
        return "FLAT"
    # Use numpy's lib.stride_tricks for rolling windows.
    from numpy.lib.stride_tricks import sliding_window_view
    win_h = sliding_window_view(highs, 2 * k + 1)
    win_l = sliding_window_view(lows,  2 * k + 1)
    # Center index is k in each window
    centers_h = highs[k:n - k]
    centers_l = lows[k:n - k]
    is_pivot_h = (centers_h == win_h.max(axis=1))
    is_pivot_l = (centers_l == win_l.min(axis=1))
    # Find last pivot high and last pivot low
    idx_h = np.where(is_pivot_h)[0]
    idx_l = np.where(is_pivot_l)[0]
    if len(idx_h) == 0 or len(idx_l) == 0:
        return "FLAT"
    last_h_src = int(idx_h[-1]) + k
    last_h_val = float(highs[last_h_src])
    last_l_src = int(idx_l[-1]) + k
    last_l_val = float(lows[last_l_src])
    if last_h_src > last_l_src and last_h_val > last_l_val:
        return "UP"
    if last_l_src > last_h_src and last_l_val < last_h_val:
        return "DOWN"
    return "FLAT"


def build_bar_context(bars_df: pd.DataFrame, now: datetime,
                      param_groups: dict, need_htf_k: set) -> BarContext:
    ctx = BarContext()
    ctx.atr20 = atr_n(bars_df, 20)
    # numpy arrays for HTF
    arr = bars_df["high"].to_numpy()
    arr_lo = bars_df["low"].to_numpy()
    if 15 in need_htf_k:
        ctx.htf_k15 = _htf_trend_numpy(arr, arr_lo, 15)
    if 30 in need_htf_k:
        ctx.htf_k30 = _htf_trend_numpy(arr, arr_lo, 30)
    if 60 in need_htf_k:
        ctx.htf_k60 = _htf_trend_numpy(arr, arr_lo, 60)
    ctx.setups_by_param_key = detect_setups_for_param_groups(
        bars_df, now, param_groups)
    return ctx


def on_closed_bar(vs: VariantState, ctx: BarContext, now: datetime,
                  param_key):
    """Per-variant filtering. ctx is shared across variants for this bar."""
    cfg = vs.cfg

    # Day roll for daily DD tracking
    ny_day = now.date().isoformat()
    if vs.cur_day != ny_day:
        vs.cur_day = ny_day
        vs.daily_pnl = 0.0
        vs.daily_dd_tripped = False

    # ATR filter
    if cfg.atr_min is not None or cfg.atr_max is not None:
        atr = ctx.atr20
        if not math.isnan(atr):
            if cfg.atr_min is not None and atr < cfg.atr_min:
                return
            if cfg.atr_max is not None and atr > cfg.atr_max:
                return

    setup = ctx.setups_by_param_key.get(param_key)
    if setup is None:
        return

    # HTF filter
    if cfg.htf_filter:
        if cfg.htf_k == 15:
            t = ctx.htf_k15
        elif cfg.htf_k == 30:
            t = ctx.htf_k30
        elif cfg.htf_k == 60:
            t = ctx.htf_k60
        else:
            t = "FLAT"
        if t == "FLAT":
            return
        if t == "UP" and setup.side != "LONG":
            return
        if t == "DOWN" and setup.side != "SHORT":
            return

    # Expire old setups on every closed bar (cheap, prevents unbounded
    # accumulation when sticky gates suppress segment processing).
    if vs.pending_setups:
        cutoff = now - timedelta(seconds=MAX_WAIT_SECS)
        vs.pending_setups = [s for s in vs.pending_setups
                              if not s.used and s.detected_at > cutoff]

    # Dedupe
    key = (round(setup.impulse_high, 1), round(setup.impulse_low, 1), setup.side)
    if key in vs.recent_keys:
        return
    # Only dedupe against ACTIVE pending setups
    for s in vs.pending_setups:
        if s.used:
            continue
        if (round(s.impulse_high, 1), round(s.impulse_low, 1), s.side) == key:
            return
    # Each variant needs its OWN copy of the setup (so per-variant
    # entry_armed / used / etc. don't bleed across variants).
    import copy
    vs.pending_setups.append(copy.copy(setup))


def on_tick(vs: VariantState, ts: datetime, bid: float, ask: float):
    """Per-tick handler: manages active trade exit + try-fire pending setups."""
    cfg = vs.cfg

    # Day roll for daily DD tracking (so the per-day P&L resets even
    # without a closed bar firing on that minute).
    ny_day = ts.date().isoformat()
    if vs.cur_day != ny_day:
        vs.cur_day = ny_day
        vs.daily_pnl = 0.0
        vs.daily_dd_tripped = False

    # Exit active trade?
    at = vs.active_trade
    if at is not None:
        hold_s = (ts - at["entry_ts"]).total_seconds()
        exit_px = None
        exit_reason = None
        if at["side"] == "LONG":
            # stop MARKET (bid touches stop) -> filled at bid - slip
            if bid <= at["stop_px"]:
                exit_px = at["stop_px"] - STOP_SLIP_PTS
                exit_reason = "stop"
            elif bid >= at["target_px"] and hold_s >= MIN_TARGET_HOLD_SECONDS:
                # LIMIT SELL fills at target exactly
                exit_px = at["target_px"]
                exit_reason = "target"
        else:  # SHORT
            if ask >= at["stop_px"]:
                exit_px = at["stop_px"] + STOP_SLIP_PTS
                exit_reason = "stop"
            elif ask <= at["target_px"] and hold_s >= MIN_TARGET_HOLD_SECONDS:
                exit_px = at["target_px"]
                exit_reason = "target"
        if exit_px is None and hold_s >= MAX_HOLD_SECS:
            # timeout at mid
            exit_px = (bid + ask) / 2.0
            exit_reason = "timeout"
        if exit_px is not None:
            # Compute P&L
            if at["side"] == "LONG":
                pnl_pts = exit_px - at["entry_px"]
            else:
                pnl_pts = at["entry_px"] - exit_px
            pnl_usd = pnl_pts * N_MNQ * MNQ_PER_PT - COMMISSION_RT
            rec = {
                "entry_ts": at["entry_ts"],
                "exit_ts": ts,
                "side": at["side"],
                "entry_px": at["entry_px"],
                "exit_px": exit_px,
                "stop_px": at["stop_px"],
                "target_px": at["target_px"],
                "exit_reason": exit_reason,
                "hold_s": hold_s,
                "pnl_pts": pnl_pts,
                "pnl_usd": pnl_usd,
            }
            vs.completed_trades.append(rec)
            vs.active_trade = None
            vs.last_close_ts = ts
            vs.daily_pnl += pnl_usd

            # Track loss streak / CB
            if pnl_usd < 0:
                vs.consecutive_losses += 1
                if (cfg.cb_n_losses is not None
                        and vs.consecutive_losses >= cfg.cb_n_losses):
                    vs.pause_until_ts = ts + timedelta(minutes=cfg.cb_pause_mins)
                    vs.consecutive_losses = 0
            else:
                vs.consecutive_losses = 0

            # Daily DD trip
            if cfg.daily_dd_stop is not None and vs.daily_pnl <= -cfg.daily_dd_stop:
                vs.daily_dd_tripped = True
            return

    # Already in trade? -> can't open another
    if vs.active_trade is not None:
        return

    # No pending setups? Nothing to do.
    if not vs.pending_setups:
        return

    # Expire stale setups
    cutoff = ts - timedelta(seconds=MAX_WAIT_SECS)
    vs.pending_setups = [
        s for s in vs.pending_setups
        if (not s.used) and (s.detected_at > cutoff)
    ]
    if not vs.pending_setups:
        return

    # Pause gates
    if vs.pause_until_ts is not None and ts < vs.pause_until_ts:
        return
    if vs.daily_dd_tripped:
        return

    # Cooldown
    if vs.last_close_ts is not None:
        if (ts - vs.last_close_ts).total_seconds() < cfg.cooldown_secs:
            return

    # Time-of-day gate
    if _time_blocked(cfg, ts):
        return

    # Iterate setups; arming + trigger
    fired = None
    mid = (bid + ask) / 2.0
    for setup in vs.pending_setups:
        if setup.used:
            continue
        approach = setup.orig_side or setup.side
        # Use mid for arming/trigger (same as live which uses live_price)
        live_px = mid
        if cfg.arming:
            if not setup.entry_armed:
                if approach == "LONG" and live_px > setup.pullback_entry:
                    setup.entry_armed = True
                    setup.armed_at_ts = ts
                elif approach == "SHORT" and live_px < setup.pullback_entry:
                    setup.entry_armed = True
                    setup.armed_at_ts = ts
                continue
        # Trigger
        if approach == "LONG" and live_px <= setup.pullback_entry:
            fired = setup
            break
        if approach == "SHORT" and live_px >= setup.pullback_entry:
            fired = setup
            break

    if fired is None:
        return

    # Open the trade — entry fill model
    if cfg.marketable_limit:
        # MARKETABLE LIMIT: LONG bumps to ask+1, fills at ask. SHORT bumps
        # to bid-1, fills at bid. So paper books at ask/bid.
        if fired.side == "LONG":
            entry_px = float(ask)
        else:
            entry_px = float(bid)
    else:
        # Strict LIMIT at the pullback level (paper books at the level).
        entry_px = float(fired.pullback_entry)

    vs.active_trade = {
        "entry_ts": ts,
        "side": fired.side,
        "entry_px": entry_px,
        "stop_px": fired.stop_px_val,
        "target_px": fired.target_px_val,
    }
    fired.used = True
    vs.recent_keys.append(
        (round(fired.impulse_high, 1), round(fired.impulse_low, 1), fired.side))


# ============================================================================
# Streaming driver — bar-aligned segment processing
#
# Key insight: between bar closes (1-min boundaries) the pending setups
# and active-trade state don't CHANGE (new setups are only added at bar
# close). So per segment between two bar closes:
#   - if a variant has no active trade AND no pending setups -> ENTIRE
#     segment is a no-op
#   - if a variant has an active trade -> we can scan the segment with
#     numpy to find the FIRST tick where stop or target is hit
#   - if a variant has pending setups (no trade) -> scan for the first
#     tick where ANY setup arms+triggers
#
# Bar history is shared across all variants; setup detection on closed
# bar runs the cheap detect_pullback_setup once per variant.
# ============================================================================
def _check_trade_exit_vectorized(at, bid_arr, ask_arr, ts_ns_arr,
                                  start_idx):
    """Scan bid/ask arrays from start_idx for trade exit. Returns
    (exit_idx, exit_px, exit_reason) or (None, None, None) if no exit
    in this segment.

    Respects MIN_TARGET_HOLD_SECONDS for target fills.
    """
    side = at["side"]
    entry_ts_ns = at["entry_ts_ns"]
    stop_px = at["stop_px"]
    tgt_px = at["target_px"]
    n = len(bid_arr)
    if side == "LONG":
        # stop: bid <= stop_px
        stop_hit = (bid_arr[start_idx:] <= stop_px)
        tgt_hit = (bid_arr[start_idx:] >= tgt_px)
    else:
        stop_hit = (ask_arr[start_idx:] >= stop_px)
        tgt_hit = (ask_arr[start_idx:] <= tgt_px)
    # Find first stop and first target
    stop_idxs = np.argmax(stop_hit) if stop_hit.any() else -1
    tgt_idxs = np.argmax(tgt_hit) if tgt_hit.any() else -1
    # Map relative to absolute
    stop_idx = (start_idx + stop_idxs) if stop_idxs != -1 else None
    tgt_idx = (start_idx + tgt_idxs) if tgt_idxs != -1 else None
    # Target needs hold >= MIN_TARGET_HOLD_SECONDS
    if tgt_idx is not None:
        hold_ns = ts_ns_arr[tgt_idx] - entry_ts_ns
        if hold_ns < MIN_TARGET_HOLD_SECONDS * US_PER_SEC:
            # Find later tgt hit with sufficient hold
            min_ts = entry_ts_ns + MIN_TARGET_HOLD_SECONDS * US_PER_SEC
            # Find first idx where ts >= min_ts AND tgt_hit
            valid = (ts_ns_arr[start_idx:] >= min_ts) & tgt_hit
            if valid.any():
                tgt_idx = start_idx + int(np.argmax(valid))
            else:
                tgt_idx = None
    # Timeout?
    timeout_ns = entry_ts_ns + MAX_HOLD_SECS * US_PER_SEC
    timeout_arr = ts_ns_arr[start_idx:] >= timeout_ns
    timeout_idx = (start_idx + int(np.argmax(timeout_arr))) if timeout_arr.any() else None
    # Pick earliest event
    candidates = []
    if stop_idx is not None:
        candidates.append((stop_idx, "stop"))
    if tgt_idx is not None:
        candidates.append((tgt_idx, "target"))
    if timeout_idx is not None:
        candidates.append((timeout_idx, "timeout"))
    if not candidates:
        return (None, None, None)
    candidates.sort(key=lambda x: x[0])
    idx, reason = candidates[0]
    if reason == "stop":
        if side == "LONG":
            exit_px = float(stop_px) - STOP_SLIP_PTS
        else:
            exit_px = float(stop_px) + STOP_SLIP_PTS
    elif reason == "target":
        exit_px = float(tgt_px)
    else:
        # timeout = mid at that tick
        exit_px = float((bid_arr[idx] + ask_arr[idx]) / 2.0)
    return (idx, exit_px, reason)


def _check_setup_arm_trigger(setup, mid_arr, start_idx, arming: bool):
    """Scan mid_arr from start_idx for arming + trigger event of ONE
    setup. Returns idx of first trigger (relative to chunk) or None.

    Updates setup.entry_armed / armed_at_ts inline.
    """
    approach = setup.orig_side or setup.side
    pe = setup.pullback_entry
    n_remain = len(mid_arr) - start_idx
    if n_remain <= 0:
        return None
    seg = mid_arr[start_idx:]
    if arming:
        if not setup.entry_armed:
            # Find first index where the approach side is satisfied
            if approach == "LONG":
                arm = (seg > pe)
            else:
                arm = (seg < pe)
            if not arm.any():
                return None
            arm_idx = int(np.argmax(arm))
            setup.entry_armed = True
            # After arm_idx, look for trigger from arm_idx+1 onward
            trig_start = arm_idx + 1
        else:
            trig_start = 0
    else:
        trig_start = 0
    if trig_start >= n_remain:
        return None
    seg2 = seg[trig_start:]
    if approach == "LONG":
        trig = (seg2 <= pe)
    else:
        trig = (seg2 >= pe)
    if not trig.any():
        return None
    return start_idx + trig_start + int(np.argmax(trig))


def _record_trade_exit(vs, ts_ns_exit_int, exit_px, exit_reason):
    """Book the trade exit into vs.completed_trades and update state."""
    at = vs.active_trade
    side = at["side"]
    if side == "LONG":
        pnl_pts = exit_px - at["entry_px"]
    else:
        pnl_pts = at["entry_px"] - exit_px
    pnl_usd = pnl_pts * N_MNQ * MNQ_PER_PT - COMMISSION_RT
    entry_ts = at["entry_ts"]
    exit_ts = datetime.fromtimestamp(ts_ns_exit_int / 1e6, tz=timezone.utc)
    hold_s = (exit_ts - entry_ts).total_seconds()
    rec = {
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "side": side,
        "entry_px": at["entry_px"],
        "exit_px": exit_px,
        "stop_px": at["stop_px"],
        "target_px": at["target_px"],
        "exit_reason": exit_reason,
        "hold_s": hold_s,
        "pnl_pts": pnl_pts,
        "pnl_usd": pnl_usd,
    }
    vs.completed_trades.append(rec)
    vs.active_trade = None
    vs.last_close_ts = exit_ts
    vs.daily_pnl += pnl_usd
    cfg = vs.cfg
    if pnl_usd < 0:
        vs.consecutive_losses += 1
        if cfg.cb_n_losses is not None and vs.consecutive_losses >= cfg.cb_n_losses:
            vs.pause_until_ts = exit_ts + timedelta(minutes=cfg.cb_pause_mins)
            vs.consecutive_losses = 0
    else:
        vs.consecutive_losses = 0
    if cfg.daily_dd_stop is not None and vs.daily_pnl <= -cfg.daily_dd_stop:
        vs.daily_dd_tripped = True


def _try_open_trade(vs, setup, fire_idx, bid_arr, ask_arr, ts_ns_arr):
    """Open a new trade at fire_idx. Updates vs.active_trade."""
    cfg = vs.cfg
    ts = datetime.fromtimestamp(ts_ns_arr[fire_idx] / 1e6, tz=timezone.utc)
    # Time-of-day gate (cheap once we have ts)
    if _time_blocked(cfg, ts):
        return False
    # Pause / daily DD / cooldown
    if vs.pause_until_ts is not None and ts < vs.pause_until_ts:
        return False
    if vs.daily_dd_tripped:
        return False
    if vs.last_close_ts is not None:
        if (ts - vs.last_close_ts).total_seconds() < cfg.cooldown_secs:
            return False
    # Day roll
    ny_day = ts.date().isoformat()
    if vs.cur_day != ny_day:
        vs.cur_day = ny_day
        vs.daily_pnl = 0.0
        vs.daily_dd_tripped = False
    # Entry price
    if cfg.marketable_limit:
        if setup.side == "LONG":
            entry_px = float(ask_arr[fire_idx])
        else:
            entry_px = float(bid_arr[fire_idx])
    else:
        entry_px = float(setup.pullback_entry)
    vs.active_trade = {
        "entry_ts": ts,
        "entry_ts_ns": int(ts_ns_arr[fire_idx]),
        "side": setup.side,
        "entry_px": entry_px,
        "stop_px": setup.stop_px_val,
        "target_px": setup.target_px_val,
    }
    setup.used = True
    vs.recent_keys.append(
        (round(setup.impulse_high, 1), round(setup.impulse_low, 1), setup.side))
    return True


def _process_segment(vs, bid_arr, ask_arr, mid_arr, ts_ns_arr,
                     seg_start, seg_end):
    """Process a segment of ticks [seg_start, seg_end) for one variant.
    Segment is bar-aligned: no new setups appear inside it.

    Returns nothing — mutates vs in place.
    """
    cfg = vs.cfg
    # Sticky-gate fast path: if daily DD tripped OR a long pause is
    # active that fully spans this segment, we know the variant won't
    # fire any new trade in this segment. We still must process active
    # trade exit, but pending setups can be ignored.
    sticky_blocked = False
    if vs.daily_dd_tripped:
        sticky_blocked = True
    elif vs.pause_until_ts is not None and vs.pending_setups:
        # Compare in epoch us: ts_ns_arr is us-since-epoch
        pause_us = int(vs.pause_until_ts.timestamp() * US_PER_SEC)
        if int(ts_ns_arr[seg_end - 1]) <= pause_us:
            sticky_blocked = True

    cur = seg_start
    while cur < seg_end:
        # If there's an active trade, scan for exit
        if vs.active_trade is not None:
            exit_idx, exit_px, exit_reason = _check_trade_exit_vectorized(
                vs.active_trade, bid_arr[:seg_end], ask_arr[:seg_end],
                ts_ns_arr[:seg_end], cur)
            if exit_idx is None:
                # No exit in this segment — trade rides through
                return
            _record_trade_exit(vs, int(ts_ns_arr[exit_idx]), exit_px, exit_reason)
            cur = exit_idx + 1
            continue
        # Sticky-block fast path: no new setups can fire this segment
        if sticky_blocked:
            return
        # No active trade — try to fire pending setups
        if not vs.pending_setups:
            return
        # Expire stale setups (cheap)
        now_ns = ts_ns_arr[cur]
        cutoff_ns = now_ns - MAX_WAIT_SECS * US_PER_SEC
        vs.pending_setups = [
            s for s in vs.pending_setups
            if (not s.used)
            and (s.detected_at.timestamp() * US_PER_SEC > cutoff_ns)
        ]
        if not vs.pending_setups:
            return
        # Find earliest fire across pending setups
        earliest_idx = None
        earliest_setup = None
        for setup in vs.pending_setups:
            if setup.used:
                continue
            fi = _check_setup_arm_trigger(
                setup, mid_arr[:seg_end], cur, cfg.arming)
            if fi is not None and (earliest_idx is None or fi < earliest_idx):
                earliest_idx = fi
                earliest_setup = setup
        if earliest_idx is None:
            return
        opened = _try_open_trade(vs, earliest_setup, earliest_idx,
                                  bid_arr, ask_arr, ts_ns_arr)
        if not opened:
            # Gate blocked. For transient gates (cooldown/time-of-day)
            # the setup should re-fire later. But to avoid O(seg^2) on
            # retries within this segment, we mark setup used here —
            # accepting that some "would-have-fired-after-cooldown"
            # setups get skipped. In practice cooldown is short (10s)
            # and setups expire after MAX_WAIT_SECS=300s, so most retries
            # would have fired in the SAME segment anyway.
            earliest_setup.used = True
            cur = earliest_idx + 1
            continue
        cur = earliest_idx + 1


def run_battery(variants: list[VariantConfig], *,
                start_offset: int = 0,
                end_after_ticks: Optional[int] = None,
                label: str = "BATTERY"):
    """Single-pass tick stream over all variants. Returns dict
    variant_name -> VariantState."""
    print(f"\n[{label}] starting {len(variants)} variants, offset={start_offset:,}",
          flush=True)
    states = {v.name: VariantState(cfg=v) for v in variants}
    bar_builder = BarBuilder(keep=HISTORY_BARS)

    n_ticks = 0
    n_bars = 0
    t0 = time.time()
    last_progress = t0
    states_list = list(states.values())
    min_bars_for_setup = max(5, max(v.impulse_bars for v in variants))
    ticks_since_progress = 0

    # Param groups: variants sharing setup-detection params share one
    # detect_pullback_setup call per bar.
    def _pkey(v: VariantConfig):
        return (v.impulse_pts, v.impulse_bars, v.pull_pct,
                v.stop_pts, v.target_pts)
    param_groups = {}        # pkey -> sample VariantConfig
    variant_param_key = {}   # name -> pkey
    for v in variants:
        k = _pkey(v)
        param_groups.setdefault(k, v)
        variant_param_key[v.name] = k
    print(f"[{label}] {len(variants)} variants in {len(param_groups)} setup groups",
          flush=True)
    # Which HTF k values are actually needed?
    need_htf_k = set(v.htf_k for v in variants if v.htf_filter)

    for chunk in iter_tick_chunks(TICK_CSV, start_offset=start_offset):
        ts_ns_arr = chunk["ts"]
        bid_arr = chunk["bid"]
        ask_arr = chunk["ask"]
        mid_arr = chunk["mid"]
        chunk_len = len(ts_ns_arr)
        # Find bar-close boundaries within this chunk
        minutes_arr = ts_ns_arr // US_PER_MIN
        # Mark indices where minute changes (i.e., where the prior bar
        # closes and a new bar begins at index i).
        if bar_builder.cur_minute is None:
            prev_minute = minutes_arr[0]
        else:
            prev_minute = bar_builder.cur_minute
        # Build close-points: indices where minutes_arr[i] != prev_minute
        # (just before we step into a new minute)
        diff_idxs = np.where(np.diff(np.concatenate([[prev_minute], minutes_arr])) != 0)[0]
        # diff_idxs[k] is the FIRST index of a NEW minute. The bar that
        # CLOSED is the prior one. We process bar-aware in segments:
        # [seg_start ... diff_idxs[0]-1] (prior bar continues),
        # at diff_idxs[0] a new bar opens => emit closed bar and detect setups.
        # Then segment continues until next diff_idx.
        seg_start = 0
        for new_min_idx in diff_idxs:
            # Update bar builder for all ticks in [seg_start, new_min_idx)
            # — they all belong to the prior minute. We just need to track
            # OHLC. For speed, we can do this vectorized.
            if seg_start < new_min_idx:
                slice_mids = mid_arr[seg_start:new_min_idx]
                if bar_builder.cur_minute is None:
                    bar_builder.cur_minute = int(minutes_arr[seg_start])
                    bar_builder.cur_o = float(slice_mids[0])
                    bar_builder.cur_h = float(slice_mids.max())
                    bar_builder.cur_l = float(slice_mids.min())
                    bar_builder.cur_c = float(slice_mids[-1])
                    bar_builder.cur_v = int(len(slice_mids))
                else:
                    bar_builder.cur_h = max(bar_builder.cur_h, float(slice_mids.max()))
                    bar_builder.cur_l = min(bar_builder.cur_l, float(slice_mids.min()))
                    bar_builder.cur_c = float(slice_mids[-1])
                    bar_builder.cur_v += int(len(slice_mids))
            # Now process the segment [seg_start, new_min_idx) per variant
            # (using state created from PRIOR bar close, since the bar
            # we're closing fires after this segment).
            for vs in states_list:
                _process_segment(vs, bid_arr, ask_arr, mid_arr, ts_ns_arr,
                                  seg_start, new_min_idx)
            # Emit closed bar at new_min_idx
            closed_ts_ns = bar_builder.cur_minute * US_PER_MIN
            closed = (closed_ts_ns, bar_builder.cur_o, bar_builder.cur_h,
                      bar_builder.cur_l, bar_builder.cur_c, bar_builder.cur_v)
            bar_builder._buf.append(closed)
            if len(bar_builder._buf) > bar_builder.keep:
                bar_builder._buf = bar_builder._buf[-bar_builder.keep:]
            bar_builder._dirty = True
            n_bars += 1
            # Start new bar
            bar_builder.cur_minute = int(minutes_arr[new_min_idx])
            bar_builder.cur_o = float(mid_arr[new_min_idx])
            bar_builder.cur_h = bar_builder.cur_o
            bar_builder.cur_l = bar_builder.cur_o
            bar_builder.cur_c = bar_builder.cur_o
            bar_builder.cur_v = 1
            # Detect setups across variants — SHARED bar context
            bars_df = bar_builder.as_dataframe()
            if len(bars_df) >= min_bars_for_setup:
                bar_now_us = bar_builder.cur_minute * US_PER_MIN  # this is wrong - we just started new bar; use closed_ts_ns
                # Actually use closed_ts_ns from before we rolled to new bar
                # We can recover it from bars_df.index[-1]
                last_bar_ts = bars_df.index[-1].to_pydatetime()
                if last_bar_ts.tzinfo is None:
                    last_bar_ts = last_bar_ts.replace(tzinfo=timezone.utc)
                ctx = build_bar_context(bars_df, last_bar_ts,
                                         param_groups, need_htf_k)
                for vs in states_list:
                    pk = variant_param_key[vs.cfg.name]
                    on_closed_bar(vs, ctx, last_bar_ts, pk)
            seg_start = new_min_idx
        # Tail segment: [seg_start, chunk_len) belongs to cur_minute
        if seg_start < chunk_len:
            slice_mids = mid_arr[seg_start:chunk_len]
            if bar_builder.cur_minute is None:
                bar_builder.cur_minute = int(minutes_arr[seg_start])
                bar_builder.cur_o = float(slice_mids[0])
                bar_builder.cur_h = float(slice_mids.max())
                bar_builder.cur_l = float(slice_mids.min())
                bar_builder.cur_c = float(slice_mids[-1])
                bar_builder.cur_v = int(len(slice_mids))
            else:
                bar_builder.cur_h = max(bar_builder.cur_h, float(slice_mids.max()))
                bar_builder.cur_l = min(bar_builder.cur_l, float(slice_mids.min()))
                bar_builder.cur_c = float(slice_mids[-1])
                bar_builder.cur_v += int(len(slice_mids))
            for vs in states_list:
                _process_segment(vs, bid_arr, ask_arr, mid_arr, ts_ns_arr,
                                  seg_start, chunk_len)
        n_ticks += chunk_len
        ticks_since_progress += chunk_len
        if ticks_since_progress >= PROGRESS_TICKS:
            now = time.time()
            rate = ticks_since_progress / max(0.001, now - last_progress)
            last_progress = now
            ticks_since_progress = 0
            tc = {k: len(s.completed_trades) for k, s in states.items()}
            best = max(tc.items(), key=lambda kv: kv[1])
            print(f"  [{label}] {n_ticks/1e6:.1f}M ticks  "
                  f"{n_bars:,} bars  rate={rate/1e6:.2f}M/s  "
                  f"best_var={best[0]}({best[1]} tr)  "
                  f"elapsed={now-t0:.0f}s",
                  flush=True)
        if end_after_ticks is not None and n_ticks >= end_after_ticks:
            print(f"  [{label}] reached end_after_ticks={end_after_ticks:,}",
                  flush=True)
            return states
    print(f"[{label}] done. ticks={n_ticks:,} bars={n_bars:,} "
          f"elapsed={time.time()-t0:.0f}s", flush=True)
    return states


# ============================================================================
# Reporting
# ============================================================================
def summarize(vs: VariantState) -> dict:
    trades = vs.completed_trades
    if not trades:
        return {
            "name": vs.cfg.name, "trades": 0, "wr": 0.0,
            "pnl": 0.0, "per_day": 0.0, "per_trade": 0.0,
            "n_days": 0, "max_dd": 0.0, "worst_day": 0.0, "best_day": 0.0,
            "trades_per_day": 0.0, "sharpe": 0.0,
        }
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
    trades_per_day = n / max(1, n_days)
    # Running drawdown (per-trade equity curve)
    eq = df["pnl_usd"].cumsum().to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak).min() if len(eq) else 0.0
    sharpe = (daily.mean() / daily.std()) if (len(daily) > 1 and daily.std() > 0) else 0.0
    return {
        "name": vs.cfg.name, "trades": n, "wr": wr,
        "pnl": pnl, "per_day": per_day, "per_trade": per_trade,
        "n_days": n_days, "max_dd": float(dd),
        "worst_day": float(daily.min()), "best_day": float(daily.max()),
        "trades_per_day": trades_per_day, "sharpe": float(sharpe),
    }


def behavior_paragraph(s: dict, baseline: Optional[dict] = None) -> str:
    if s["trades"] == 0:
        return f"{s['name']}: NO TRADES fired (all setups filtered out)."
    base = ""
    if baseline is not None and baseline["trades"] > 0:
        pnl_delta = s["pnl"] - baseline["pnl"]
        tr_delta = s["trades"] - baseline["trades"]
        wr_delta = (s["wr"] - baseline["wr"]) * 100
        base = (f"vs baseline: pnl {pnl_delta:+,.0f}$ "
                f"({(s['pnl']/max(1,abs(baseline['pnl']))*100 if baseline['pnl']!=0 else 0):+.0f}% rel.), "
                f"trades {tr_delta:+,} ({tr_delta/max(1,baseline['trades'])*100:+.0f}%), "
                f"WR {wr_delta:+.1f}pp. ")
    tr = s["trades"]
    wr = s["wr"] * 100
    return (f"{tr:,} trades, WR {wr:.1f}%, ${s['per_day']:,.0f}/day, "
            f"${s['per_trade']:.2f}/trade, "
            f"trades/day {s['trades_per_day']:.1f}, "
            f"max DD ${s['max_dd']:,.0f}, "
            f"worst day ${s['worst_day']:,.0f}, "
            f"best day ${s['best_day']:,.0f}, "
            f"Sharpe-ish {s['sharpe']:.2f}. " + base)


def write_report(results_60d: dict, results_full: Optional[dict],
                 outpath: str):
    lines = []
    lines.append("# Comprehensive Backtest Battery — MNQ Inverse-Fade Pullback Bot\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append("Strategy: INVERSE pullback fade (STRAT_INVERT=1), 1 MNQ, "
                 "marketable LIMIT entries, stop-MARKET exits (0.5pt slip), "
                 "LIMIT targets (exact fill), 10s cooldown, $0.74 round-trip "
                 "commission.\n")
    lines.append("## 60-day subset results\n")
    if results_60d:
        baseline = next((summarize(v) for k, v in results_60d.items()
                         if k == "BASELINE"), None)
        sums = [summarize(v) for v in results_60d.values()]
        # Sort by P&L desc
        sums.sort(key=lambda s: s["pnl"], reverse=True)
        lines.append("| Variant | Trades | WR | P&L $ | $/day | $/trade | "
                     "Trades/day | Max DD | Worst day | Best day | Sharpe-ish |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for s in sums:
            lines.append(
                f"| {s['name']} | {s['trades']:,} | {s['wr']*100:.1f}% | "
                f"${s['pnl']:,.0f} | ${s['per_day']:,.0f} | ${s['per_trade']:.2f} | "
                f"{s['trades_per_day']:.1f} | ${s['max_dd']:,.0f} | "
                f"${s['worst_day']:,.0f} | ${s['best_day']:,.0f} | "
                f"{s['sharpe']:.2f} |\n")
        lines.append("\n### Per-variant behaviour\n")
        for s in sums:
            lines.append(f"- **{s['name']}**: {behavior_paragraph(s, baseline)}\n")
    if results_full:
        lines.append("\n## Top-5 refined variants — FULL data set\n")
        baseline_f = next((summarize(v) for k, v in results_full.items()
                           if k == "BASELINE"), None)
        sums = [summarize(v) for v in results_full.values()]
        sums.sort(key=lambda s: s["pnl"], reverse=True)
        lines.append("| Variant | Trades | WR | P&L $ | $/day | $/trade | "
                     "Trades/day | Max DD | Worst day | Best day | Sharpe-ish |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for s in sums:
            lines.append(
                f"| {s['name']} | {s['trades']:,} | {s['wr']*100:.1f}% | "
                f"${s['pnl']:,.0f} | ${s['per_day']:,.0f} | ${s['per_trade']:.2f} | "
                f"{s['trades_per_day']:.1f} | ${s['max_dd']:,.0f} | "
                f"${s['worst_day']:,.0f} | ${s['best_day']:,.0f} | "
                f"{s['sharpe']:.2f} |\n")
        lines.append("\n### Per-variant behaviour (FULL data)\n")
        for s in sums:
            lines.append(f"- **{s['name']}**: {behavior_paragraph(s, baseline_f)}\n")

    # Build the recommendation section using whichever data set is richer.
    lines.append("\n## Recommendation\n")
    src_label = "FULL data" if results_full else "60-day subset"
    source = results_full if results_full else results_60d
    if source:
        sums = [summarize(v) for v in source.values()]
        baseline = next((s for s in sums if s["name"] == "BASELINE"), None)
        # Rank by P&L
        ranked = sorted(sums, key=lambda s: s["pnl"], reverse=True)
        top = ranked[0]
        # Better than baseline?
        if baseline is not None:
            lines.append(f"_Source: {src_label}_\n\n")
            lines.append(f"**Baseline (current live config)**: "
                         f"{baseline['trades']:,} trades, "
                         f"${baseline['pnl']:,.0f} P&L, "
                         f"${baseline['per_day']:,.0f}/day, "
                         f"WR {baseline['wr']*100:.1f}%, "
                         f"{baseline['trades_per_day']:.1f} trades/day.\n\n")
            # Top-5
            lines.append("**Top 5 by P&L**:\n\n")
            for r in ranked[:5]:
                delta = r['pnl'] - baseline['pnl']
                tr_delta = r['trades'] - baseline['trades']
                lines.append(
                    f"1. **{r['name']}** — ${r['pnl']:,.0f} "
                    f"(vs baseline {delta:+,.0f}$), "
                    f"{r['trades']:,} trades "
                    f"({tr_delta:+,} vs baseline), "
                    f"${r['per_day']:,.0f}/day, "
                    f"WR {r['wr']*100:.1f}%, "
                    f"{r['trades_per_day']:.1f} tr/day, "
                    f"max DD ${r['max_dd']:,.0f}\n")
            lines.append("\n")
            # Honest verdict — multiple branches
            any_positive = any(s['pnl'] > 0 for s in sums)
            baseline_negative = baseline['pnl'] < 0
            top_pnl = top['pnl']
            top_trades_per_day = top['trades_per_day']
            top_trade_change = ((top['trades'] - baseline['trades'])
                                / max(1, baseline['trades']) * 100)

            if not any_positive and baseline_negative:
                lines.append(
                    "**HONEST VERDICT — STOP TRADING**: Every single variant "
                    "tested loses money over the test window, including the "
                    "current live BASELINE config. The original validation "
                    "that showed +$1,952/day was on tick data WITHOUT arming "
                    "(phantom fires inflated the win rate), and likely also "
                    "used optimistic exit modelling (bar-high target wicks "
                    "fill paper but never fill the real broker LIMIT).\n\n"
                    "With arming + marketable LIMIT exec + STOP-MARKET slip + "
                    "tight LIMIT target requirements (broker reality), the "
                    "strategy has a structural NEGATIVE edge:\n\n"
                    f"  - BASELINE:           ${baseline['per_day']:+,.0f}/day  "
                    f"({baseline['trades_per_day']:.0f} tr/day, WR {baseline['wr']*100:.1f}%)\n"
                    f"  - Best variant ({top['name']}): "
                    f"${top['per_day']:+,.0f}/day  "
                    f"({top['trades_per_day']:.0f} tr/day, WR {top['wr']*100:.1f}%)\n\n"
                    "The filters reduce the bleed by trading less, but the "
                    "per-trade expectancy is negative on every config — "
                    "you cannot filter your way out of a negative edge.\n\n"
                    "**Recommended actions:**\n\n"
                    "1. PAUSE the live bot. It is currently losing money "
                    "in real time and the backtest confirms this is the "
                    "expected behaviour, not bad luck.\n"
                    "2. Investigate why the original validated +$1,952/day "
                    "config doesn't reproduce. The two biggest suspects are "
                    "(a) the OOS-validation period (Dec'25-Feb'26) was a "
                    "specific bear-volatility regime not present in the "
                    "full data; (b) the arming-vs-phantom and "
                    "marketable-LIMIT exec fixes (correct as of June '26) "
                    "remove the implicit edge that older paper accounting "
                    "was double-counting.\n"
                    "3. Re-validate on the original Dec'25-Feb'26 window "
                    "with the CURRENT execution model. If P&L is still "
                    "positive there but negative on the full 766-day data, "
                    "the strategy is a regime-specific bet, not a "
                    "persistent edge.\n"
                    "4. Consider whether the strategy needs a fundamental "
                    "redesign — the bake-off catalogue in research/ has "
                    "many alternatives (cumdelta, large-print fade, ORB, "
                    "SMC sweep, etc.) that may have a real edge.\n\n"
                    "**If forced to keep trading right now**: the "
                    f"{top['name']} variant loses the LEAST money "
                    f"(${top['per_day']:+,.0f}/day vs baseline "
                    f"${baseline['per_day']:+,.0f}/day) but cuts trade "
                    f"volume to {top_trades_per_day:.0f}/day "
                    f"({top_trade_change:+.0f}% vs baseline). It is a "
                    "damage-control mode, not a winning strategy.\n")
            elif top['name'] == "BASELINE":
                lines.append(
                    "**Verdict (honest)**: No add-on beats the baseline on "
                    "P&L in this run. The filters that improve win rate do "
                    "so by REDUCING trade volume — which kills total P&L. "
                    "The strategy's edge per-trade is small; volume is what "
                    "makes money. Stick with BASELINE.\n")
            else:
                trade_pct_change = top_trade_change
                pnl_pct = ((top['pnl'] - baseline['pnl'])
                           / max(1, abs(baseline['pnl'])) * 100)
                if abs(trade_pct_change) < 25 and top['pnl'] > baseline['pnl']:
                    verdict = (f"**{top['name']}** wins on P&L "
                               f"({pnl_pct:+.0f}% vs baseline) while changing "
                               f"trade count by only {trade_pct_change:+.0f}%. "
                               "This meets the user's '200+/day, minimal "
                               "trade reduction' goal.")
                elif top['trades'] < baseline['trades'] * 0.5:
                    verdict = (f"**{top['name']}** has the best P&L but only "
                               f"{top['trades_per_day']:.1f} trades/day "
                               "(massive trade reduction). It improves "
                               "P&L/trade but is NOT a fit for the user's "
                               "high-volume goal.")
                else:
                    verdict = (f"**{top['name']}** edges out baseline. "
                               "Modest improvement — recommend A/B testing live "
                               "before committing.")
                lines.append(f"**Verdict**: {verdict}\n")

    Path(outpath).write_text("".join(lines))
    print(f"[REPORT] wrote {outpath}")


# ============================================================================
# Variant catalogue
# ============================================================================
def build_variants_full() -> list[VariantConfig]:
    V = []
    # Category A
    V.append(VariantConfig("BASELINE"))
    V.append(VariantConfig("NO_ARMING", arming=False))
    V.append(VariantConfig("STRICT_LIMIT", marketable_limit=False))
    # Category B — HTF trend filter
    V.append(VariantConfig("HTF_k30", htf_filter=True, htf_k=30))
    V.append(VariantConfig("HTF_k15", htf_filter=True, htf_k=15))
    V.append(VariantConfig("HTF_k60", htf_filter=True, htf_k=60))
    # Category C — ATR
    V.append(VariantConfig("ATR_min5", atr_min=5.0))
    V.append(VariantConfig("ATR_min8", atr_min=8.0))
    V.append(VariantConfig("ATR_max25", atr_max=25.0))
    V.append(VariantConfig("ATR_range8to20", atr_min=8.0, atr_max=20.0))
    # Category D — time-of-day
    V.append(VariantConfig("SKIP_OPEN", skip_open=True))
    V.append(VariantConfig("SKIP_CLOSE", skip_close=True))
    V.append(VariantConfig("NY_SESSION_ONLY", ny_session_only=True))
    V.append(VariantConfig("AVOID_LUNCH", avoid_lunch=True))
    # Category E — circuit breakers
    V.append(VariantConfig("CB_3losses_30min", cb_n_losses=3, cb_pause_mins=30))
    V.append(VariantConfig("CB_4losses_60min", cb_n_losses=4, cb_pause_mins=60))
    V.append(VariantConfig("CB_daily_dd200", daily_dd_stop=200.0))
    # Category F — parameter variants
    V.append(VariantConfig("STOP_8_TARGET_24", stop_pts=8.0, target_pts=24.0))
    V.append(VariantConfig("STOP_12_TARGET_18", stop_pts=12.0, target_pts=18.0))
    V.append(VariantConfig("PULL_0382", pull_pct=0.382))
    V.append(VariantConfig("PULL_050", pull_pct=0.5))
    V.append(VariantConfig("IMPULSE_8", impulse_pts=8.0))
    # Category G — combinations
    V.append(VariantConfig("HTF_k30_CB3", htf_filter=True, htf_k=30,
                            cb_n_losses=3, cb_pause_mins=30))
    V.append(VariantConfig("ATR_min5_SKIP_OPEN_CB3",
                            atr_min=5.0, skip_open=True,
                            cb_n_losses=3, cb_pause_mins=30))
    V.append(VariantConfig("HTF_k30_ATR_min5_NY",
                            htf_filter=True, htf_k=30,
                            atr_min=5.0, ny_session_only=True))
    # Refined extras (5 more)
    V.append(VariantConfig("ATR_min5_CB3",
                            atr_min=5.0, cb_n_losses=3, cb_pause_mins=30))
    V.append(VariantConfig("ATR_min5_AVOID_LUNCH",
                            atr_min=5.0, avoid_lunch=True))
    V.append(VariantConfig("SKIP_OPEN_CB3",
                            skip_open=True, cb_n_losses=3, cb_pause_mins=30))
    V.append(VariantConfig("NY_SESSION_CB3",
                            ny_session_only=True, cb_n_losses=3, cb_pause_mins=30))
    V.append(VariantConfig("DDSTOP_AVOID_LUNCH",
                            daily_dd_stop=200.0, avoid_lunch=True))
    return V


# ============================================================================
# Main
# ============================================================================
def get_60d_offset() -> int:
    """Binary search for the start of the last 60 days in the tick CSV."""
    path = TICK_CSV
    size = os.path.getsize(path)
    # End date is 20260617; 60 days back = 20260418
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
                        help="Run all variants on full data (slow)")
    parser.add_argument("--top5-full", action="store_true",
                        help="Run only top-5 (manually configured) on full data")
    parser.add_argument("--out-dir", default="/home/user/HFTBot/research")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = build_variants_full()
    print(f"Built {len(variants)} variants")

    # Phase 1: 60-day subset
    offset_60 = get_60d_offset()
    print(f"60-day offset: {offset_60:,}")

    results_60d = run_battery(variants,
                              start_offset=offset_60,
                              label="60D-SUBSET")

    # Save CSV summary
    rows = [summarize(vs) for vs in results_60d.values()]
    df = pd.DataFrame(rows).sort_values("pnl", ascending=False)
    df.to_csv(out_dir / "backtest_summary_60d.csv", index=False)
    print(f"\nTop 10 variants (60d subset):")
    print(df.head(10).to_string())

    # Phase 2: pick top-5 by P&L for full run (if asked)
    results_full = None
    if args.full or args.top5_full:
        # Always include BASELINE for comparison
        top5_names = list(df.head(5)["name"]) if not args.full else \
                     [v.name for v in variants]
        if "BASELINE" not in top5_names:
            top5_names.insert(0, "BASELINE")
        top_variants = [v for v in variants if v.name in top5_names]
        print(f"\nFull-data run on: {[v.name for v in top_variants]}")
        results_full = run_battery(top_variants,
                                   start_offset=0,
                                   label="FULL-DATA")
        rows_f = [summarize(vs) for vs in results_full.values()]
        df_f = pd.DataFrame(rows_f).sort_values("pnl", ascending=False)
        df_f.to_csv(out_dir / "backtest_summary_full.csv", index=False)
        print(f"\nFull-data results:")
        print(df_f.to_string())

    # Write markdown report
    write_report(results_60d, results_full,
                 str(out_dir / "backtest_results.md"))


if __name__ == "__main__":
    main()

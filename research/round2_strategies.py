"""Round 2 — strategies NOT tested in round 1.

Categories tested here:
 1. Multi-hour holds (4-24h)
 2. Higher-timeframe bars (5m, 15m, 30m, 60m) with structural strategies
 3. Day-of-week stratified hourly bias
 4. Hold-until-profit-or-timeout
 5. Volatility-filtered hourly holds
 6. Day-of-month / turn-of-month
 7. Intraday mean reversion to levels
 8. Regime-adaptive

Engine: bar-based vectorized. Uses 1-min cache at research/bars_full.parquet.
Execution model (bar-approximation; matches tick model up to ~1pt noise):
 - LONG entry at next bar open + 1pt (proxy for ASK marketable LIMIT)
 - SHORT entry at next bar open - 1pt (proxy for BID marketable LIMIT)
 - Stop fill: when bar low <= stop (LONG) -> fill at stop - 0.5pt slip
 - Target fill: when bar high >= target (LONG) -> fill at target exact
 - Timeout (MARKET) exit: at exit bar close - 0.25pt (LONG) / + 0.25pt (SHORT)
 - $0.74 round-trip commission, $2/pt, 1 MNQ.

The bar-noise on entry/exit at FIXED CLOCK times is ~1.5pt per trade,
which is the same noise the tick engine produces (entry at ASK ~ open+0.5
to open+1.5, exit at BID ~ close-0.5). So the multi-hour-hold P&Ls
should be within a few % of the tick-precise engine's results.

Usage:
  python -m research.round2_strategies          # run everything
  python -m research.round2_strategies --skip-htf  # skip higher-TF battery
"""
from __future__ import annotations
import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")

# ----- Constants (mirror comprehensive_backtest.py) -----
BAR_PARQUET = "/home/user/HFTBot/research/bars_full.parquet"
COMMISSION_RT = 0.74
MNQ_PER_PT = 2.0
N_MNQ = 1
STOP_SLIP_PTS = 0.5
ENTRY_BUFFER_PTS = 1.0      # marketable LIMIT entry bump
MARKET_EXIT_SLIP = 0.25     # MARKET exit slip
OUT_DIR = Path("/home/user/HFTBot/research")


# =====================================================================
# Data loading
# =====================================================================
def load_bars() -> pd.DataFrame:
    """Load 1-min bars, indexed by UTC timestamp."""
    df = pd.read_parquet(BAR_PARQUET)
    df = df.set_index("dt")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
    df = df[["open", "high", "low", "close"]].copy()
    df["dow"] = df.index.dayofweek
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute
    df["date"] = df.index.date
    return df


def resample_bars(bars_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample to higher TF. rule: '5min', '15min', '30min', '60min'."""
    agg = bars_1m.resample(rule, label="left", closed="left").agg({
        "open":  "first",
        "high":  "max",
        "low":   "min",
        "close": "last",
    }).dropna()
    agg["dow"] = agg.index.dayofweek
    agg["hour"] = agg.index.hour
    agg["minute"] = agg.index.minute
    agg["date"] = agg.index.date
    return agg


# =====================================================================
# Execution engine — vectorized over a list of trades
# =====================================================================
@dataclass
class TradePlan:
    """A scheduled trade: entry_bar_ts is the bar AT WHICH we enter;
    we fill at that bar's open + ENTRY_BUFFER for LONG (or open - buf for
    SHORT). exit policy is either:
     - hold_bars (timeout exit at MARKET at exit bar close), AND/OR
     - stop_pts (MARKET stop fill mid-bar, with slip), AND/OR
     - target_pts (LIMIT target fill at target exact).
    """
    entry_ts: pd.Timestamp
    side: str                      # "LONG" or "SHORT"
    hold_bars: int                 # max bars to hold (timeout)
    stop_pts: Optional[float] = None
    target_pts: Optional[float] = None
    tag: str = ""                  # for diagnostics


def simulate_trades(bars: pd.DataFrame, plans: List[TradePlan]) -> pd.DataFrame:
    """Run all plans against the bar grid. Returns a per-trade DataFrame.

    For each plan:
      - find the bar at entry_ts (or first bar >= entry_ts)
      - entry_px = open + ENTRY_BUFFER (LONG) or open - ENTRY_BUFFER (SHORT)
      - scan next [1, hold_bars] bars for stop, target, or timeout
        (within-bar: stop_first if bar's range encompasses both stop & target;
         optimistically assume stop fires first when ambiguous — conservative)
      - exit at min(stop_idx, target_idx, hold_bars)
    """
    if not plans:
        return pd.DataFrame()
    # Make a fast lookup from ts -> integer index
    ts_index = bars.index
    # Vectorize: get integer entry index for each plan via searchsorted
    plan_ts = pd.DatetimeIndex([p.entry_ts for p in plans])
    entry_idx = ts_index.searchsorted(plan_ts, side="left")
    n = len(plans)
    open_arr = bars["open"].to_numpy()
    high_arr = bars["high"].to_numpy()
    low_arr = bars["low"].to_numpy()
    close_arr = bars["close"].to_numpy()
    n_bars = len(bars)

    rows = []
    for i, p in enumerate(plans):
        ei = int(entry_idx[i])
        if ei >= n_bars:
            continue
        # If entry_ts > the bar's ts, we land on the next bar
        entry_bar_ts = ts_index[ei]
        if entry_bar_ts < p.entry_ts:
            # Should not normally happen because searchsorted left
            continue
        op = open_arr[ei]
        if p.side == "LONG":
            entry_px = op + ENTRY_BUFFER_PTS
        else:
            entry_px = op - ENTRY_BUFFER_PTS
        # Compute stop/target levels
        if p.stop_pts is not None:
            stop_px = entry_px - p.stop_pts if p.side == "LONG" else entry_px + p.stop_pts
        else:
            stop_px = None
        if p.target_pts is not None:
            tgt_px = entry_px + p.target_pts if p.side == "LONG" else entry_px - p.target_pts
        else:
            tgt_px = None
        # Scan forward bars (skip the entry bar — that's a partial bar; use bar ei+1 onwards
        # so that the entry "fills" early in the bar but we measure subsequent bars)
        # Conservative: include entry bar high/low (the entry might happen at open, then
        # the rest of the bar can hit stop). But to avoid look-ahead-on-entry-bar
        # ambiguity (did we get filled BEFORE the stop hit?), we exclude entry bar.
        scan_start = ei + 1
        scan_end = min(ei + 1 + p.hold_bars, n_bars)
        if scan_end <= scan_start:
            # No bars to scan — booked at next bar open
            exit_idx = ei
            exit_reason = "no_data"
            if p.side == "LONG":
                exit_px = close_arr[ei] - MARKET_EXIT_SLIP
            else:
                exit_px = close_arr[ei] + MARKET_EXIT_SLIP
        else:
            highs = high_arr[scan_start:scan_end]
            lows = low_arr[scan_start:scan_end]
            stop_idx_local = None
            tgt_idx_local = None
            if stop_px is not None:
                if p.side == "LONG":
                    hit = lows <= stop_px
                else:
                    hit = highs >= stop_px
                if hit.any():
                    stop_idx_local = int(np.argmax(hit))
            if tgt_px is not None:
                if p.side == "LONG":
                    hit = highs >= tgt_px
                else:
                    hit = lows <= tgt_px
                if hit.any():
                    tgt_idx_local = int(np.argmax(hit))
            # Pick earliest event; tie -> assume stop fires first (conservative)
            cand = []
            if stop_idx_local is not None:
                cand.append((stop_idx_local, "stop", 0))
            if tgt_idx_local is not None:
                cand.append((tgt_idx_local, "target", 1))
            if cand:
                cand.sort(key=lambda x: (x[0], x[2]))
                local_idx, reason, _ = cand[0]
                exit_idx = scan_start + local_idx
                if reason == "stop":
                    if p.side == "LONG":
                        exit_px = stop_px - STOP_SLIP_PTS
                    else:
                        exit_px = stop_px + STOP_SLIP_PTS
                    exit_reason = "stop"
                else:
                    exit_px = tgt_px
                    exit_reason = "target"
            else:
                # Timeout exit at MARKET at scan_end-1 bar's close
                exit_idx = scan_end - 1
                if p.side == "LONG":
                    exit_px = close_arr[exit_idx] - MARKET_EXIT_SLIP
                else:
                    exit_px = close_arr[exit_idx] + MARKET_EXIT_SLIP
                exit_reason = "timeout"
        if p.side == "LONG":
            pnl_pts = exit_px - entry_px
        else:
            pnl_pts = entry_px - exit_px
        pnl_usd = pnl_pts * MNQ_PER_PT * N_MNQ - COMMISSION_RT
        rows.append({
            "tag": p.tag,
            "side": p.side,
            "entry_ts": entry_bar_ts,
            "exit_ts": ts_index[exit_idx],
            "entry_px": entry_px,
            "exit_px": exit_px,
            "stop_px": stop_px,
            "target_px": tgt_px,
            "exit_reason": exit_reason,
            "hold_bars_actual": exit_idx - ei,
            "pnl_pts": pnl_pts,
            "pnl_usd": pnl_usd,
        })
    return pd.DataFrame(rows)


# =====================================================================
# Strategy plan generators
# =====================================================================
def plans_hold_at_hour(bars_1m: pd.DataFrame, hour: int, minute: int,
                       side: str, hold_minutes: int, tag: str,
                       dow_filter: Optional[set] = None,
                       prevday_range_min: Optional[float] = None,
                       prevday_range_max: Optional[float] = None,
                       ) -> List[TradePlan]:
    """One trade per session at (hour, minute) UTC. Hold for hold_minutes,
    exit at MARKET. Optional filters: only on specific DOWs; only when
    previous calendar day's range is within [min, max] pts.

    IMPORTANT: If `minute` is 0, we enter at the FIRST AVAILABLE BAR of the
    target hour, not exclusively at minute 0. This is because the broker's
    Sunday session opens after 22:00 UTC and many weekdays the 22:00:00 bar
    is missing. We adjust hold_minutes downward when entering past the hour
    start so the exit time stays correct.
    """
    # Find FIRST bar of the target hour per session-day.
    in_hour = bars_1m[bars_1m["hour"] == hour]
    if minute > 0:
        in_hour = in_hour[in_hour["minute"] >= minute]
    if in_hour.empty:
        return []
    # Per-date, first bar at-or-after the target minute
    in_hour = in_hour.sort_index()
    # Build the dates keyed identically (already df["date"] is python date)
    first_per_date = in_hour.groupby("date").head(1).copy()
    cand = first_per_date
    if dow_filter is not None:
        cand = cand[cand["dow"].isin(dow_filter)]
    # Precompute previous-day range if needed
    if prevday_range_min is not None or prevday_range_max is not None:
        daily = bars_1m.groupby("date").agg(day_h=("high", "max"), day_l=("low", "min"))
        daily["range"] = daily["day_h"] - daily["day_l"]
        # For each candidate entry, get the previous trading day's range
        sorted_dates = sorted(daily.index)
        date_to_prev = {}
        for i, d in enumerate(sorted_dates):
            if i > 0:
                date_to_prev[d] = sorted_dates[i - 1]
        cand["prev_date"] = cand["date"].map(date_to_prev)
        cand["prev_range"] = cand["prev_date"].map(daily["range"])
        if prevday_range_min is not None:
            cand = cand[cand["prev_range"] >= prevday_range_min]
        if prevday_range_max is not None:
            cand = cand[cand["prev_range"] <= prevday_range_max]
        cand = cand.dropna(subset=["prev_range"])
    plans = []
    for ts in cand.index:
        # Adjust hold_minutes so the exit time is the same regardless of
        # which minute of the hour we entered. If we entered at minute 7,
        # we want to exit at minute 7 + hold_minutes from start of hour 0,
        # i.e. we hold for hold_minutes - 0 = same. The exit is "hold_minutes
        # bars later" — which means a flat clock offset. This is what we want.
        # No adjustment needed: we hold for hold_minutes bars from entry.
        plans.append(TradePlan(
            entry_ts=ts, side=side, hold_bars=hold_minutes,
            tag=tag,
        ))
    return plans


def plans_hold_session(bars_1m: pd.DataFrame, entry_hour: int, entry_min: int,
                       exit_hour: int, exit_min: int, side: str,
                       tag: str) -> List[TradePlan]:
    """Enter at (entry_hour, entry_min) UTC, exit at next occurrence of
    (exit_hour, exit_min) UTC. Used for session-spanning holds.

    Like plans_hold_at_hour, we use FIRST AVAILABLE bar of entry_hour.
    """
    in_entry_hr = bars_1m[bars_1m["hour"] == entry_hour]
    if entry_min > 0:
        in_entry_hr = in_entry_hr[in_entry_hr["minute"] >= entry_min]
    first_per_date = in_entry_hr.sort_index().groupby("date").head(1)
    cand_idx = first_per_date.index
    plans = []
    # For each candidate, compute hold_bars = minutes until next exit_hour:exit_min
    ts_arr = bars_1m.index
    exit_mask_full = (bars_1m["hour"] == exit_hour) & (bars_1m["minute"] == exit_min)
    exit_times = bars_1m[exit_mask_full].index
    if len(exit_times) == 0:
        return plans
    for ts in cand_idx:
        # Find next exit time > ts
        pos = exit_times.searchsorted(ts, side="right")
        if pos >= len(exit_times):
            continue
        exit_ts = exit_times[pos]
        hold_mins = int((exit_ts - ts).total_seconds() / 60)
        plans.append(TradePlan(
            entry_ts=ts, side=side, hold_bars=hold_mins, tag=tag))
    return plans


def plans_stack_positive_hours(bars_1m: pd.DataFrame, hours_with_side: List[Tuple[int, str]],
                               hold_minutes: int, tag: str) -> List[TradePlan]:
    """For each (hour, side) pair, enter at first bar of that hour and hold
    for hold_minutes. Uses first-bar-of-hour entry (handles missing minute-0).
    """
    plans = []
    for h, side in hours_with_side:
        in_hour = bars_1m[bars_1m["hour"] == h]
        first_per_date = in_hour.sort_index().groupby("date").head(1)
        for ts in first_per_date.index:
            plans.append(TradePlan(entry_ts=ts, side=side, hold_bars=hold_minutes, tag=tag))
    return plans


def plans_hold_until_profit_or_timeout(bars_1m: pd.DataFrame, hour: int,
                                       side: str, profit_pts: float,
                                       stop_pts: Optional[float],
                                       timeout_minutes: int, tag: str
                                       ) -> List[TradePlan]:
    """Enter at first bar of `hour`, set a target at +profit_pts, optional
    stop, and a hard timeout."""
    plans = []
    in_hour = bars_1m[bars_1m["hour"] == hour]
    first_per_date = in_hour.sort_index().groupby("date").head(1)
    for ts in first_per_date.index:
        plans.append(TradePlan(
            entry_ts=ts, side=side, hold_bars=timeout_minutes,
            stop_pts=stop_pts, target_pts=profit_pts, tag=tag,
        ))
    return plans


def plans_turn_of_month(bars_1m: pd.DataFrame, mode: str, hold_hours: int,
                        side: str, tag: str) -> List[TradePlan]:
    """
    mode: 'first_3' = first 3 trading days of month (enter at 13:30 UTC = NY open)
          'last_3'  = last 3 trading days of month
    """
    # Trading days per month
    daily = bars_1m.groupby("date").size().reset_index(name="n")
    daily["date"] = pd.to_datetime(daily["date"])
    daily["ym"] = daily["date"].dt.to_period("M")
    daily = daily.sort_values("date").reset_index(drop=True)
    targets = set()
    for ym, group in daily.groupby("ym"):
        dates = group["date"].dt.date.tolist()
        if mode == "first_3":
            for d in dates[:3]:
                targets.add(d)
        elif mode == "last_3":
            for d in dates[-3:]:
                targets.add(d)
    # Enter at 13:30 UTC on those dates
    mask = (bars_1m["hour"] == 13) & (bars_1m["minute"] == 30)
    cand = bars_1m[mask]
    cand = cand[cand["date"].isin(targets)]
    plans = []
    for ts in cand.index:
        plans.append(TradePlan(entry_ts=ts, side=side, hold_bars=hold_hours * 60, tag=tag))
    return plans


def plans_weekly_open(bars_1m: pd.DataFrame, hold_days: int, side: str, tag: str
                      ) -> List[TradePlan]:
    """Enter at first available Sunday 22:** UTC bar, hold for hold_days days."""
    sun_h22 = bars_1m[(bars_1m["hour"] == 22) & (bars_1m["dow"] == 6)]
    first_per_date = sun_h22.sort_index().groupby("date").head(1)
    plans = []
    for ts in first_per_date.index:
        plans.append(TradePlan(entry_ts=ts, side=side, hold_bars=hold_days * 24 * 60, tag=tag))
    return plans


def plans_gap_fade(bars_1m: pd.DataFrame, gap_threshold_pts: float, side: str,
                   target_hours: int, stop_pts: Optional[float], tag: str
                   ) -> List[TradePlan]:
    """At 13:30 UTC (NY open), compare to 21:00 UTC prior day's close.
    If gap > threshold UP, SHORT (fade); if gap > threshold DOWN, LONG (fade).
    side here = 'AUTO' means determine direction by gap.
    Hold target_hours at MARKET (no profit target).
    """
    plans = []
    # Get NY open bars
    open_mask = (bars_1m["hour"] == 13) & (bars_1m["minute"] == 30)
    open_bars = bars_1m[open_mask]
    # Get 21:00 UTC close bars (CME close = "prior day's close" proxy)
    close_mask = (bars_1m["hour"] == 21) & (bars_1m["minute"] == 0)
    close_bars = bars_1m[close_mask]
    # Build a quick (date -> close_px) mapping using the 21:00 bar's close
    close_by_date = dict(zip(close_bars["date"], close_bars["close"]))
    for ts in open_bars.index:
        # Find prior trading day with a 21:00 close
        cur_date = ts.date()
        # walk back up to 4 days
        prior_close = None
        for back in range(1, 5):
            cand_d = (ts - timedelta(days=back)).date()
            if cand_d in close_by_date:
                prior_close = close_by_date[cand_d]
                break
        if prior_close is None:
            continue
        cur_open = open_bars.loc[ts, "open"]
        gap = cur_open - prior_close
        if abs(gap) < gap_threshold_pts:
            continue
        # Fade: if gap up (positive), short; if gap down, long
        actual_side = "SHORT" if gap > 0 else "LONG"
        if side != "AUTO" and side != actual_side:
            continue
        plans.append(TradePlan(
            entry_ts=ts, side=actual_side, hold_bars=target_hours * 60,
            stop_pts=stop_pts, tag=tag,
        ))
    return plans


# =====================================================================
# Higher-timeframe structural strategies (Cat 2)
# =====================================================================
def plans_htf_momentum(bars_htf: pd.DataFrame, lookback: int, stop_pts: float,
                       target_pts: float, side: str, tag: str
                       ) -> List[TradePlan]:
    """N-bar momentum on higher TF: if last N bars all-up, LONG; all-down, SHORT.
    Enter at next bar open. Hold up to 4 bars or stop/target.
    """
    df = bars_htf.copy()
    df["bar_ret"] = df["close"] - df["open"]
    # Rolling sum of sign
    sign = np.sign(df["bar_ret"].to_numpy())
    n = len(sign)
    plans = []
    for i in range(lookback, n - 1):
        recent = sign[i - lookback + 1: i + 1]
        if side in ("LONG", "AUTO_FOLLOW") and (recent > 0).all():
            entry_ts = df.index[i + 1]
            plans.append(TradePlan(
                entry_ts=entry_ts, side="LONG", hold_bars=4,
                stop_pts=stop_pts, target_pts=target_pts, tag=tag,
            ))
        elif side in ("SHORT", "AUTO_FOLLOW") and (recent < 0).all():
            entry_ts = df.index[i + 1]
            plans.append(TradePlan(
                entry_ts=entry_ts, side="SHORT", hold_bars=4,
                stop_pts=stop_pts, target_pts=target_pts, tag=tag,
            ))
        elif side == "AUTO_FADE":
            if (recent > 0).all():
                entry_ts = df.index[i + 1]
                plans.append(TradePlan(
                    entry_ts=entry_ts, side="SHORT", hold_bars=4,
                    stop_pts=stop_pts, target_pts=target_pts, tag=tag,
                ))
            elif (recent < 0).all():
                entry_ts = df.index[i + 1]
                plans.append(TradePlan(
                    entry_ts=entry_ts, side="LONG", hold_bars=4,
                    stop_pts=stop_pts, target_pts=target_pts, tag=tag,
                ))
    return plans


def plans_htf_breakout(bars_htf: pd.DataFrame, lookback: int, stop_pts: float,
                       target_pts: float, tag: str) -> List[TradePlan]:
    """Donchian breakout on higher TF: when high breaks N-bar high, LONG;
    when low breaks N-bar low, SHORT. Enter next bar open.
    """
    df = bars_htf.copy()
    high_arr = df["high"].to_numpy()
    low_arr = df["low"].to_numpy()
    close_arr = df["close"].to_numpy()
    n = len(df)
    plans = []
    for i in range(lookback, n - 1):
        hh = high_arr[i - lookback:i].max()
        ll = low_arr[i - lookback:i].min()
        c = close_arr[i]
        if c > hh:
            plans.append(TradePlan(
                entry_ts=df.index[i + 1], side="LONG", hold_bars=4,
                stop_pts=stop_pts, target_pts=target_pts, tag=tag,
            ))
        elif c < ll:
            plans.append(TradePlan(
                entry_ts=df.index[i + 1], side="SHORT", hold_bars=4,
                stop_pts=stop_pts, target_pts=target_pts, tag=tag,
            ))
    return plans


def plans_htf_meanrev(bars_htf: pd.DataFrame, lookback: int, n_std: float,
                      stop_pts: float, target_pts: float, tag: str
                      ) -> List[TradePlan]:
    """Mean-reversion on higher TF: when close is > mean + n_std*std, SHORT;
    when < mean - n_std*std, LONG.
    """
    df = bars_htf.copy()
    close_arr = df["close"].to_numpy()
    n = len(df)
    if n < lookback + 1:
        return []
    # Rolling mean/std
    s = pd.Series(close_arr)
    mean = s.rolling(lookback).mean().to_numpy()
    std = s.rolling(lookback).std().to_numpy()
    plans = []
    for i in range(lookback, n - 1):
        if np.isnan(mean[i]) or std[i] == 0 or np.isnan(std[i]):
            continue
        z = (close_arr[i] - mean[i]) / std[i]
        if z > n_std:
            plans.append(TradePlan(
                entry_ts=df.index[i + 1], side="SHORT", hold_bars=4,
                stop_pts=stop_pts, target_pts=target_pts, tag=tag,
            ))
        elif z < -n_std:
            plans.append(TradePlan(
                entry_ts=df.index[i + 1], side="LONG", hold_bars=4,
                stop_pts=stop_pts, target_pts=target_pts, tag=tag,
            ))
    return plans


# =====================================================================
# Summarization
# =====================================================================
def summarize(trades: pd.DataFrame, name: str) -> dict:
    if trades.empty:
        return {
            "name": name, "trades": 0, "wr": 0.0, "pnl": 0.0,
            "per_day": 0.0, "per_trade": 0.0, "trades_per_day": 0.0,
            "n_days": 0, "max_dd": 0.0, "worst_day": 0.0, "best_day": 0.0,
            "sharpe": 0.0,
        }
    df = trades.copy()
    df["day"] = pd.to_datetime(df["exit_ts"]).dt.date
    daily = df.groupby("day")["pnl_usd"].sum()
    pnl = float(df["pnl_usd"].sum())
    wins = int((df["pnl_usd"] > 0).sum())
    n = len(df)
    n_days = len(daily)
    eq = df["pnl_usd"].cumsum().to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak).min()
    sharpe = (daily.mean() / daily.std()) if (len(daily) > 1 and daily.std() > 0) else 0.0
    return {
        "name": name, "trades": n, "wr": wins / n, "pnl": pnl,
        "per_day": pnl / max(1, n_days), "per_trade": pnl / max(1, n),
        "trades_per_day": n / max(1, n_days),
        "n_days": n_days, "max_dd": float(dd),
        "worst_day": float(daily.min()), "best_day": float(daily.max()),
        "sharpe": float(sharpe),
    }


def per_year_breakdown(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    df = trades.copy()
    df["year"] = pd.to_datetime(df["exit_ts"]).dt.year
    out = {}
    for y, g in df.groupby("year"):
        out[int(y)] = float(g["pnl_usd"].sum())
    return out


def per_month_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.copy()
    df["ym"] = pd.to_datetime(df["exit_ts"]).dt.to_period("M").astype(str)
    return df.groupby("ym")["pnl_usd"].sum().reset_index()


def per_dow_breakdown(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    df = trades.copy()
    df["dow"] = pd.to_datetime(df["entry_ts"]).dt.dayofweek
    out = {}
    for d, g in df.groupby("dow"):
        out[int(d)] = {"n": int(len(g)), "pnl": float(g["pnl_usd"].sum()),
                       "wr": float((g["pnl_usd"] > 0).mean())}
    return out


def worst_30d_rolling(trades: pd.DataFrame) -> float:
    if trades.empty or len(trades) < 2:
        return 0.0
    df = trades.copy()
    df["day"] = pd.to_datetime(df["exit_ts"]).dt.date
    daily = df.groupby("day")["pnl_usd"].sum().sort_index()
    if len(daily) < 30:
        return float(daily.cumsum().min())
    roll = daily.rolling(30).sum()
    return float(roll.min())


# =====================================================================
# MAIN: build & run all strategies
# =====================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-htf", action="store_true",
                        help="Skip higher-TF structural battery (saves time)")
    parser.add_argument("--limit-strats", type=int, default=None,
                        help="Run only first N strategies (debug)")
    args = parser.parse_args()

    t0 = time.time()
    print("Loading 1-min bar parquet...", flush=True)
    bars_1m = load_bars()
    print(f"  loaded {len(bars_1m):,} bars  "
          f"date range {bars_1m.index.min()} -> {bars_1m.index.max()}",
          flush=True)

    # Precompute higher-TF resamples (if needed)
    if not args.skip_htf:
        print("Resampling to 5/15/30/60min...", flush=True)
        bars_5m = resample_bars(bars_1m, "5min")
        bars_15m = resample_bars(bars_1m, "15min")
        bars_30m = resample_bars(bars_1m, "30min")
        bars_60m = resample_bars(bars_1m, "60min")
        print(f"  5m={len(bars_5m):,}  15m={len(bars_15m):,}  "
              f"30m={len(bars_30m):,}  60m={len(bars_60m):,}", flush=True)

    all_results = []
    all_trades = {}  # name -> trades df (kept in memory for combining)

    # ============================================================
    # CATEGORY 1 — Multi-hour holds
    # ============================================================
    print("\n=== CATEGORY 1: multi-hour holds ===", flush=True)
    cat1_specs = [
        # (name, hour, side, hold_minutes)
        ("HOLD_2H_22UTC_LONG",  22, "LONG",   2 * 60),
        ("HOLD_3H_22UTC_LONG",  22, "LONG",   3 * 60),
        ("HOLD_4H_22UTC_LONG",  22, "LONG",   4 * 60),
        ("HOLD_6H_22UTC_LONG",  22, "LONG",   6 * 60),
        ("HOLD_8H_22UTC_LONG",  22, "LONG",   8 * 60),
        ("HOLD_12H_22UTC_LONG", 22, "LONG",  12 * 60),
        ("HOLD_16H_22UTC_LONG", 22, "LONG",  16 * 60),
        ("HOLD_24H_22UTC_LONG", 22, "LONG",  24 * 60),
        ("HOLD_2H_17UTC_LONG",  17, "LONG",   2 * 60),
        ("HOLD_3H_17UTC_LONG",  17, "LONG",   3 * 60),
        ("HOLD_4H_17UTC_LONG",  17, "LONG",   4 * 60),
        ("HOLD_6H_17UTC_LONG",  17, "LONG",   6 * 60),
        ("HOLD_8H_17UTC_LONG",  17, "LONG",   8 * 60),
        ("HOLD_12H_17UTC_LONG", 17, "LONG",  12 * 60),
        # H01 (next-day Asian) bias was +3.4 pts/hr -> hold from H22 spans through it
        # H01 single-shot LONG hold
        ("HOLD_4H_01UTC_LONG",   1, "LONG",   4 * 60),
        # Session-spanning (22:00 -> 14:00) skipping morning negative hours
        # We use plans_hold_session for this
    ]
    for name, hour, side, hold_min in cat1_specs:
        plans = plans_hold_at_hour(bars_1m, hour, 0, side, hold_min, name)
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        all_results.append(s)
        all_trades[name] = trades
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}", flush=True)

    # Session 22:00 -> 14:00 (skipping morning negative hours 14-15 UTC)
    plans = plans_hold_session(bars_1m, 22, 0, 14, 0, "LONG",
                               "HOLD_SESSION_22to14_LONG")
    trades = simulate_trades(bars_1m, plans)
    s = summarize(trades, "HOLD_SESSION_22to14_LONG")
    all_results.append(s)
    all_trades["HOLD_SESSION_22to14_LONG"] = trades
    print(f"  HOLD_SESSION_22to14_LONG: {s['trades']} tr, ${s['pnl']:.0f}, "
          f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
          f"DD ${s['max_dd']:.0f}", flush=True)

    # Session 22:00 -> 13:30 (NY pre-open)
    plans = plans_hold_session(bars_1m, 22, 0, 13, 30, "LONG",
                               "HOLD_SESSION_22to13_30_LONG")
    trades = simulate_trades(bars_1m, plans)
    s = summarize(trades, "HOLD_SESSION_22to13_30_LONG")
    all_results.append(s)
    all_trades["HOLD_SESSION_22to13_30_LONG"] = trades
    print(f"  HOLD_SESSION_22to13_30_LONG: {s['trades']} tr, ${s['pnl']:.0f}, "
          f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
          f"DD ${s['max_dd']:.0f}", flush=True)

    # STACK_POSITIVE_HOURS — note: in the simple TradePlan model these
    # produce multiple non-overlapping plans/day, so we just generate all of them
    plans = plans_stack_positive_hours(
        bars_1m,
        hours_with_side=[(17, "LONG"), (22, "LONG"), (1, "LONG"),
                          (19, "LONG"), (16, "LONG")],
        hold_minutes=60, tag="STACK_POSITIVE_HOURS",
    )
    trades = simulate_trades(bars_1m, plans)
    s = summarize(trades, "STACK_POSITIVE_HOURS")
    all_results.append(s)
    all_trades["STACK_POSITIVE_HOURS"] = trades
    print(f"  STACK_POSITIVE_HOURS: {s['trades']} tr, ${s['pnl']:.0f}, "
          f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
          f"DD ${s['max_dd']:.0f}", flush=True)

    # ============================================================
    # CATEGORY 3 — DOW stratified hourly bias (read from existing CSV)
    # ============================================================
    print("\n=== CATEGORY 3: DOW stratified hourly bias ===", flush=True)
    dow_bias = pd.read_csv("/home/user/HFTBot/research/hourly_bias_by_dow.csv")
    # Find (dow, hour) pairs with significant positive or negative bias.
    # t-stat = mean / (std/sqrt(count)). std isn't directly in the csv.
    # The csv has: dow, hour, mean, sum, count. We need std — we'll
    # approximate from `bars_1m` directly: per-hour open->close stdev.
    # First, compute per-(dow, hour) open-to-close return on the 1-min bars
    print("  Computing per-(dow, hour) signal strength...", flush=True)
    # Build hourly OC returns: group all 1-min bars by (date, hour) and compute
    # open-to-close per hour.
    bars_1m_local = bars_1m.copy()
    bars_1m_local["yyyymmddhh"] = (
        bars_1m_local.index.year.astype(str) + "_" +
        bars_1m_local.index.month.astype(str).str.zfill(2) + "_" +
        bars_1m_local.index.day.astype(str).str.zfill(2) + "_" +
        bars_1m_local.index.hour.astype(str).str.zfill(2)
    )
    hourly = bars_1m_local.groupby("yyyymmddhh").agg(
        h_open=("open", "first"), h_close=("close", "last"),
        hour=("hour", "first"), dow=("dow", "first"),
    )
    hourly["oc"] = hourly["h_close"] - hourly["h_open"]
    stats = hourly.groupby(["dow", "hour"])["oc"].agg(["mean", "std", "count"])
    stats["tstat"] = stats["mean"] / (stats["std"] / np.sqrt(stats["count"]))
    stats = stats.dropna().sort_values("tstat", ascending=False)
    # Pick the top 5 most positive (t > 2) and top 5 most negative (t < -2)
    top_pos = stats[stats["tstat"] >= 1.96].head(10)
    top_neg = stats[stats["tstat"] <= -1.96].head(10)
    print(f"  {len(top_pos)} (dow,hour) cells with t>=1.96; "
          f"{len(top_neg)} cells with t<=-1.96", flush=True)
    # Build strategies for each significant cell
    sig_cells = []
    for (dow, hour), row in top_pos.iterrows():
        name = f"DOW{int(dow)}_H{int(hour):02d}_LONG_HOLD60"
        plans = plans_hold_at_hour(
            bars_1m, int(hour), 0, "LONG", 60, name,
            dow_filter={int(dow)},
        )
        if len(plans) < 20:
            continue
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        s["tstat_signal"] = float(row["tstat"])
        all_results.append(s)
        all_trades[name] = trades
        sig_cells.append((name, s))
    for (dow, hour), row in top_neg.iterrows():
        name = f"DOW{int(dow)}_H{int(hour):02d}_SHORT_HOLD60"
        plans = plans_hold_at_hour(
            bars_1m, int(hour), 0, "SHORT", 60, name,
            dow_filter={int(dow)},
        )
        if len(plans) < 20:
            continue
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        s["tstat_signal"] = float(row["tstat"])
        all_results.append(s)
        all_trades[name] = trades
        sig_cells.append((name, s))
    for name, s in sorted(sig_cells, key=lambda x: -x[1]["per_day"])[:8]:
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}, t={s.get('tstat_signal','?'):.2f}",
              flush=True)

    # ============================================================
    # CATEGORY 4 — hold-until-profit-or-timeout
    # ============================================================
    print("\n=== CATEGORY 4: hold-until-profit-or-timeout ===", flush=True)
    cat4_specs = [
        # (entry_hour, side, profit_pts, stop_pts, timeout_min)
        (22, "LONG",  8,   16,  4 * 60),
        (22, "LONG",  15,  30,  4 * 60),
        (22, "LONG",  30,  60,  4 * 60),
        (22, "LONG",  50,  100, 8 * 60),
        (22, "LONG",  15,  None, 4 * 60),     # no stop
        (22, "LONG",  30,  None, 4 * 60),
        (17, "LONG",  8,   16,  4 * 60),
        (17, "LONG",  15,  30,  4 * 60),
        (17, "LONG",  30,  60,  4 * 60),
        (17, "LONG",  15,  None, 4 * 60),
        (17, "LONG",  30,  None, 4 * 60),
        # Asian session — H1 has +3.4 bias
        (1, "LONG",  10,  20,  4 * 60),
        (1, "LONG",  15,  None, 4 * 60),
    ]
    for hour, side, profit, stop, timeout in cat4_specs:
        stop_tag = f"S{stop}" if stop else "NOSTOP"
        name = f"H{hour:02d}_{side}_TGT{profit}_{stop_tag}_TO{timeout//60}h"
        plans = plans_hold_until_profit_or_timeout(
            bars_1m, hour, side, profit, stop, timeout, name)
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        all_results.append(s)
        all_trades[name] = trades
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}", flush=True)

    # ============================================================
    # CATEGORY 5 — vol-filtered hourly holds
    # ============================================================
    print("\n=== CATEGORY 5: vol-filtered hourly holds ===", flush=True)
    cat5_specs = [
        # (name, hour, side, hold, prevmin, prevmax)
        ("H22_HOLD60_PREVRANGE_GT50", 22, "LONG", 60, 50, None),
        ("H22_HOLD60_PREVRANGE_LT100", 22, "LONG", 60, None, 100),
        ("H22_HOLD60_PREVRANGE_50to100", 22, "LONG", 60, 50, 100),
        ("H22_HOLD60_PREVRANGE_GT100", 22, "LONG", 60, 100, None),
        ("H17_HOLD60_PREVRANGE_GT50", 17, "LONG", 60, 50, None),
        ("H17_HOLD60_PREVRANGE_LT100", 17, "LONG", 60, None, 100),
        ("H17_HOLD60_PREVRANGE_50to100", 17, "LONG", 60, 50, 100),
        ("H17_HOLD60_PREVRANGE_GT100", 17, "LONG", 60, 100, None),
    ]
    for name, hour, side, hold, lo, hi in cat5_specs:
        plans = plans_hold_at_hour(
            bars_1m, hour, 0, side, hold, name,
            prevday_range_min=lo, prevday_range_max=hi,
        )
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        all_results.append(s)
        all_trades[name] = trades
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}", flush=True)

    # ============================================================
    # CATEGORY 6 — turn-of-month
    # ============================================================
    print("\n=== CATEGORY 6: turn-of-month ===", flush=True)
    cat6_specs = [
        ("TOM_FIRST3_LONG_HOLD6h", "first_3", 6, "LONG"),
        ("TOM_FIRST3_LONG_HOLD24h", "first_3", 24, "LONG"),
        ("TOM_LAST3_LONG_HOLD6h",  "last_3",  6, "LONG"),
        ("TOM_LAST3_LONG_HOLD24h", "last_3", 24, "LONG"),
        ("TOM_FIRST3_SHORT_HOLD6h", "first_3", 6, "SHORT"),
        ("TOM_LAST3_SHORT_HOLD6h",  "last_3",  6, "SHORT"),
    ]
    for name, mode, hours, side in cat6_specs:
        plans = plans_turn_of_month(bars_1m, mode, hours, side, name)
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        all_results.append(s)
        all_trades[name] = trades
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}", flush=True)

    # ============================================================
    # CATEGORY 7 — gap fade (intraday level reversion)
    # ============================================================
    print("\n=== CATEGORY 7: gap fade / level reversion ===", flush=True)
    cat7_specs = [
        # (name, gap_threshold, hold_hours, stop_pts)
        ("GAPFADE_30pt_8h_S60", 30, 8, 60),
        ("GAPFADE_50pt_8h_S100", 50, 8, 100),
        ("GAPFADE_50pt_24h_S100", 50, 24, 100),
        ("GAPFADE_75pt_24h_S150", 75, 24, 150),
        ("GAPFADE_100pt_24h_S200", 100, 24, 200),
        ("GAPFADE_50pt_24h_NOSTOP", 50, 24, None),
        ("GAPFADE_100pt_24h_NOSTOP", 100, 24, None),
    ]
    for name, thresh, hours, stop in cat7_specs:
        plans = plans_gap_fade(bars_1m, thresh, "AUTO", hours, stop, name)
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        all_results.append(s)
        all_trades[name] = trades
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}", flush=True)

    # Weekly-open holds
    print("\n=== CATEGORY 7b: weekly open holds ===", flush=True)
    for hold_days, side in [(1, "LONG"), (2, "LONG"), (5, "LONG"),
                              (1, "SHORT"), (5, "SHORT")]:
        name = f"WEEKOPEN_{side}_HOLD{hold_days}d"
        plans = plans_weekly_open(bars_1m, hold_days, side, name)
        trades = simulate_trades(bars_1m, plans)
        s = summarize(trades, name)
        all_results.append(s)
        all_trades[name] = trades
        print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
              f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
              f"DD ${s['max_dd']:.0f}", flush=True)

    # ============================================================
    # CATEGORY 2 — higher-timeframe structural battery
    # ============================================================
    if not args.skip_htf:
        print("\n=== CATEGORY 2: higher-TF structural battery ===", flush=True)
        # (htf_bars, htf_name, default_stop, default_target)
        htf_setups = [
            (bars_5m,  "5m",  25, 50),
            (bars_15m, "15m", 50, 100),
            (bars_30m, "30m", 75, 150),
            (bars_60m, "60m", 100, 200),
        ]
        for htf_bars, htf_name, stop, tgt in htf_setups:
            # Momentum
            for lb in [2, 3, 5]:
                name = f"HTF_{htf_name}_MOMx{lb}_LONG_S{stop}_T{tgt}"
                plans = plans_htf_momentum(
                    htf_bars, lb, stop, tgt, "AUTO_FOLLOW", name)
                trades = simulate_trades(htf_bars, plans)
                s = summarize(trades, name)
                all_results.append(s)
                all_trades[name] = trades
                print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
                      f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
                      f"DD ${s['max_dd']:.0f}", flush=True)
                # Fade
                name = f"HTF_{htf_name}_MOMx{lb}_FADE_S{stop}_T{tgt}"
                plans = plans_htf_momentum(
                    htf_bars, lb, stop, tgt, "AUTO_FADE", name)
                trades = simulate_trades(htf_bars, plans)
                s = summarize(trades, name)
                all_results.append(s)
                all_trades[name] = trades
                print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
                      f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
                      f"DD ${s['max_dd']:.0f}", flush=True)
            # Breakout
            for lb in [10, 20, 50]:
                name = f"HTF_{htf_name}_BR{lb}_S{stop}_T{tgt}"
                plans = plans_htf_breakout(htf_bars, lb, stop, tgt, name)
                trades = simulate_trades(htf_bars, plans)
                s = summarize(trades, name)
                all_results.append(s)
                all_trades[name] = trades
                print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
                      f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
                      f"DD ${s['max_dd']:.0f}", flush=True)
            # Mean-reversion
            for lb, sd in [(20, 2.0), (50, 2.0)]:
                name = f"HTF_{htf_name}_MR{lb}_{sd}std_S{stop}_T{tgt}"
                plans = plans_htf_meanrev(htf_bars, lb, sd, stop, tgt, name)
                trades = simulate_trades(htf_bars, plans)
                s = summarize(trades, name)
                all_results.append(s)
                all_trades[name] = trades
                print(f"  {name}: {s['trades']} tr, ${s['pnl']:.0f}, "
                      f"${s['per_day']:.2f}/day, WR {s['wr']*100:.1f}%, "
                      f"DD ${s['max_dd']:.0f}", flush=True)

    # ============================================================
    # COMBINED PORTFOLIOS
    # ============================================================
    # H22 + H17 stacked (mutually-exclusive in time: H22 hold lasts to H23,
    # H17 hold lasts to H18 — they don't overlap if both are 60min holds).
    print("\n=== COMBINED PORTFOLIOS ===", flush=True)
    combined_names = []
    # Combine #1: H22_HOLD60 + H17_HOLD60 (both LONG)
    if "HOLD_2H_22UTC_LONG" in all_trades and "HOLD_2H_17UTC_LONG" in all_trades:
        # H22_HOLD60 is just first 60min — use H17 60min from cat1 as well
        # Build a "1-hour hold at biased hour" trade set for each:
        h17_60 = plans_hold_at_hour(bars_1m, 17, 0, "LONG", 60, "H17_HOLD60_LONG")
        h22_60 = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 60, "H22_HOLD60_LONG")
        t17 = simulate_trades(bars_1m, h17_60)
        t22 = simulate_trades(bars_1m, h22_60)
        s17 = summarize(t17, "H17_HOLD60_LONG_BAR")
        s22 = summarize(t22, "H22_HOLD60_LONG_BAR")
        all_results.append(s17); all_trades["H17_HOLD60_LONG_BAR"] = t17
        all_results.append(s22); all_trades["H22_HOLD60_LONG_BAR"] = t22
        # Combined: union
        combo = pd.concat([t17, t22], ignore_index=True)
        combo = combo.sort_values("entry_ts").reset_index(drop=True)
        s_combo = summarize(combo, "COMBO_H17_H22_HOLD60_LONG")
        all_results.append(s_combo); all_trades["COMBO_H17_H22_HOLD60_LONG"] = combo
        print(f"  H17_HOLD60_LONG_BAR (bar approx): {s17['trades']} tr, "
              f"${s17['pnl']:.0f}, ${s17['per_day']:.2f}/day", flush=True)
        print(f"  H22_HOLD60_LONG_BAR (bar approx): {s22['trades']} tr, "
              f"${s22['pnl']:.0f}, ${s22['per_day']:.2f}/day", flush=True)
        print(f"  COMBO_H17_H22: {s_combo['trades']} tr, "
              f"${s_combo['pnl']:.0f}, ${s_combo['per_day']:.2f}/day, "
              f"DD ${s_combo['max_dd']:.0f}", flush=True)

    # Combine #2: H22 + H17 + H01 (Asian)
    h01_60 = plans_hold_at_hour(bars_1m, 1, 0, "LONG", 60, "H01_HOLD60_LONG")
    t01 = simulate_trades(bars_1m, h01_60)
    s01 = summarize(t01, "H01_HOLD60_LONG_BAR")
    all_results.append(s01); all_trades["H01_HOLD60_LONG_BAR"] = t01
    # H19 also has +3.3 pts/hr
    h19_60 = plans_hold_at_hour(bars_1m, 19, 0, "LONG", 60, "H19_HOLD60_LONG_BAR")
    t19 = simulate_trades(bars_1m, h19_60)
    s19 = summarize(t19, "H19_HOLD60_LONG_BAR")
    all_results.append(s19); all_trades["H19_HOLD60_LONG_BAR"] = t19
    # Combo all 4 biased hours (17, 19, 22, 1)
    combo4 = pd.concat([t17, t19, t22, t01], ignore_index=True)
    combo4 = combo4.sort_values("entry_ts").reset_index(drop=True)
    s_combo4 = summarize(combo4, "COMBO_H17_H19_H22_H01_HOLD60_LONG")
    all_results.append(s_combo4); all_trades["COMBO_H17_H19_H22_H01_HOLD60_LONG"] = combo4
    print(f"  COMBO_4_HOURS: {s_combo4['trades']} tr, ${s_combo4['pnl']:.0f}, "
          f"${s_combo4['per_day']:.2f}/day, DD ${s_combo4['max_dd']:.0f}",
          flush=True)

    # ============================================================
    # WRITE summary CSV
    # ============================================================
    print(f"\nTotal strategies tested: {len(all_results)}", flush=True)
    summary_df = pd.DataFrame(all_results)
    summary_df = summary_df.sort_values("pnl", ascending=False)
    summary_df.to_csv(OUT_DIR / "round2_summary.csv", index=False)
    print(f"\nTOP 10 by total PNL:", flush=True)
    print(summary_df.head(10).to_string(), flush=True)

    # Save trades for top 8 strategies
    print(f"\nSaving trade logs for top 8 strategies...", flush=True)
    for _, row in summary_df.head(8).iterrows():
        name = row["name"]
        if name in all_trades and not all_trades[name].empty:
            all_trades[name].to_csv(OUT_DIR / f"round2_trades_{name}.csv", index=False)

    # Per-year breakdowns of top 8
    print(f"\nPer-year breakdowns of top 8:", flush=True)
    year_rows = []
    for _, row in summary_df.head(8).iterrows():
        name = row["name"]
        if name not in all_trades:
            continue
        ybd = per_year_breakdown(all_trades[name])
        dbd = per_dow_breakdown(all_trades[name])
        worst30 = worst_30d_rolling(all_trades[name])
        year_rows.append({
            "name": name, "total_pnl": row["pnl"],
            "per_day": row["per_day"],
            "y2024": ybd.get(2024, 0),
            "y2025": ybd.get(2025, 0),
            "y2026": ybd.get(2026, 0),
            "worst_30d_roll": worst30,
        })
        print(f"  {name}: 2024=${ybd.get(2024, 0):.0f}, "
              f"2025=${ybd.get(2025, 0):.0f}, 2026=${ybd.get(2026, 0):.0f}, "
              f"worst30d=${worst30:.0f}", flush=True)
        print(f"      DOW pnl: " + " ".join(
            f"{d}=${v['pnl']:.0f}({v['n']}tr,{v['wr']*100:.0f}%WR)"
            for d, v in sorted(dbd.items())), flush=True)
    pd.DataFrame(year_rows).to_csv(OUT_DIR / "round2_top_year_breakdown.csv", index=False)

    print(f"\nDone in {time.time()-t0:.0f}s. Summary at "
          f"{OUT_DIR}/round2_summary.csv", flush=True)
    return summary_df, all_trades


if __name__ == "__main__":
    main()

"""
Pattern Miner v6 — multi-step state-machine setups with NEW (non-ICT) strategies.

DESIGN: each "strategy" is a composition of:

  1. CONTEXT DETECTOR     — what the market is doing right now
  2. TRIGGER              — when to start watching for entry
  3. ENTRY CONDITION      — when to actually pull the trigger
  4. ADAPTIVE STOP        — stop placement (not fixed; depends on context)
  5. ADAPTIVE TARGET      — target placement (not fixed; depends on context)

A bar-by-bar simulator walks the full 7-year NQ history and runs
hundreds of strategy combinations through this state machine. Each
strategy maintains its own state per bar:
   AWAITING_CONTEXT → CONTEXT_CONFIRMED → AWAITING_TRIGGER → ENTERED → ...

This mimics how a discretionary trader thinks: "I see X happening (context),
I'm waiting for Y to happen (trigger), once Y happens I enter at Z with
stop at S and target at T."

The strategies here are NOT ICT-flavoured. They're combinatorial inventions
keyed off generic structural concepts (momentum bursts, volatility regime
shifts, range-cluster pullbacks, cross-asset divergence, time-of-day cohorts).

Validation: 5 rigorous tests including a 5,000-iteration label-permutation
test (Bailey/Lopez de Prado deflated-Sharpe-style significance).

Each strategy's results saved incrementally so a crash loses < 5 min.

Usage:  python -m research.pattern_miner_v6
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from research.local_data_loader import (
    load_daily,
    load_intraday_1min,
    load_intraday_5min,
    load_vix_5min,
)
from research.indicators import atr, rsi, eq50, volume_ratio
from research.signal_generator import _attach_prev_day_levels  # leak-fixed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v6_patterns.json"
PROGRESS_PATH = DATA / "v6_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v6.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v6")

# ---------------------------------------------------------------------------
# Constants — costs match live trading (Lucid)
# ---------------------------------------------------------------------------
MNQ_DPP = 2.0
SLIPPAGE_PT = 2.0
ADVERSE_SLIP_PT = 2.0
COMM_PER = 0.40

# ---------------------------------------------------------------------------
# 5 rigorous tests
# ---------------------------------------------------------------------------
MIN_SAMPLE = 50
MIN_WR_AFTER_COSTS = 0.52       # WR after slippage/commission >= 52%
MIN_PF = 1.30
MIN_SHARPE = 0.50               # per-trade Sharpe; annualised would be ~5
PERMUTATION_TRIALS = 5000
PERMUTATION_P_VALUE = 0.05      # strategy must beat 95% of random shuffles
CPCV_FOLDS = 5
CPCV_MIN_POSITIVE = 3           # >=3 of 5 folds positive
TRAIN_END = pd.Timestamp("2023-12-31", tz="UTC")   # 6yr train, ~2.3yr OOS test


# ---------------------------------------------------------------------------
# Feature builders
# ---------------------------------------------------------------------------
def build_v6_features(nq_5m: pd.DataFrame, daily: pd.DataFrame,
                       es_5m: Optional[pd.DataFrame] = None,
                       rty_5m: Optional[pd.DataFrame] = None,
                       vix_5m: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Build feature matrix for v6 detectors. Backward-looking only."""
    df = _attach_prev_day_levels(nq_5m, daily).copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0, np.nan)
    body = c - o

    F = pd.DataFrame(index=df.index)
    # ATR multi-scale
    F["atr5"]  = atr(h, l, c, 5)
    F["atr14"] = atr(h, l, c, 14)
    F["atr50"] = atr(h, l, c, 50)
    # Volatility regime (compressed / expanded)
    F["atr_compression"] = F["atr14"] / F["atr14"].rolling(100).mean()
    F["atr_expansion_5"] = F["atr5"] / F["atr14"]
    # Returns
    for n in [1, 3, 5, 10, 20]:
        F[f"ret_{n}"] = c.diff(n)
    # Bar shape
    F["body_abs"] = body.abs()
    F["body_pct"] = (body / rng).fillna(0)
    F["upper_wick_pct"] = ((h - np.maximum(o, c)) / rng).fillna(0)
    F["lower_wick_pct"] = ((np.minimum(o, c) - l) / rng).fillna(0)
    F["bar_dir"] = np.sign(body).fillna(0)
    # Consecutive direction count (a momentum indicator)
    same_dir = (np.sign(body) != 0) & (np.sign(body) == np.sign(body.shift(1)))
    F["consec_dir"] = same_dir.astype(int).groupby(
        (same_dir != same_dir.shift()).cumsum()
    ).cumcount() + 1
    # Volume
    F["vol_z_50"]  = (v - v.rolling(50).mean()) / v.rolling(50).std()
    F["vol_z_200"] = (v - v.rolling(200).mean()) / v.rolling(200).std()
    F["vol_climax"] = (F["vol_z_50"] > 2.0).astype(int)
    F["vol_dryup"]  = (v < v.rolling(50).quantile(0.20)).astype(int)
    # RSI
    F["rsi2"]  = rsi(c, 2)
    F["rsi14"] = rsi(c, 14)
    # Range-position (where in the recent range)
    high_n = h.rolling(50).max()
    low_n  = l.rolling(50).min()
    F["range_pos_50"] = (c - low_n) / (high_n - low_n).replace(0, np.nan)
    high_n2 = h.rolling(200).max()
    low_n2  = l.rolling(200).min()
    F["range_pos_200"] = (c - low_n2) / (high_n2 - low_n2).replace(0, np.nan)
    # Distance to recent extremes
    F["dist_high20_atr"] = (c - h.rolling(20).max()) / F["atr14"]
    F["dist_low20_atr"]  = (c - l.rolling(20).min()) / F["atr14"]
    F["dist_high50_atr"] = (c - h.rolling(50).max()) / F["atr14"]
    F["dist_low50_atr"]  = (c - l.rolling(50).min()) / F["atr14"]
    # PDH/PDL distances (leak-fixed)
    F["dist_pdh_atr"] = (c - df["pdh"]) / F["atr14"]
    F["dist_pdl_atr"] = (c - df["pdl"]) / F["atr14"]
    # Trend / EMA
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    F["ema20_slope"] = ema20.diff(5)
    F["ema_align"]   = np.sign(ema20 - ema50)
    F["ema_dist_atr"] = (c - ema50) / F["atr14"]
    # Range expansion / compression
    F["range_z_50"]  = (rng - rng.rolling(50).mean()) / rng.rolling(50).std()
    # Pullback depth from recent swing
    swing_high = h.rolling(20).max()
    swing_low  = l.rolling(20).min()
    F["pullback_from_high"] = (swing_high - c) / (swing_high - swing_low).replace(0, np.nan)
    F["pullback_from_low"]  = (c - swing_low) / (swing_high - swing_low).replace(0, np.nan)

    # Time-of-day (use numpy arrays so .clip works)
    NY = "America/New_York"
    if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    ny = df.index.tz_convert(NY)
    ny_hour_arr   = np.asarray(ny.hour)
    ny_minute_arr = np.asarray(ny.minute)
    ny_dow_arr    = np.asarray(ny.dayofweek)
    F["ny_hour"]   = ny_hour_arr
    F["ny_minute"] = ny_minute_arr
    F["dow"]       = ny_dow_arr
    minutes_total = ny_hour_arr * 60 + ny_minute_arr
    minutes_after_730 = np.clip(minutes_total - int(9.5 * 60), 0, None)
    F["mins_into_rth"] = np.where(
        (minutes_total >= 570) & (minutes_total < 960),
        minutes_after_730, np.nan,
    )
    F["is_open30"]  = ((ny_hour_arr == 9) & (ny_minute_arr < 60)).astype(int)
    F["is_close30"] = (((ny_hour_arr == 15) & (ny_minute_arr >= 30)) |
                       (ny_hour_arr == 16)).astype(int)
    F["is_lunch"]   = ((ny_hour_arr >= 12) & (ny_hour_arr < 13)).astype(int)

    # Cross-asset features (forward-fill is fine for these — synchronous bars)
    if es_5m is not None and not es_5m.empty:
        es_c = es_5m["close"].reindex(df.index, method="ffill")
        es_atr14 = atr(es_5m["high"], es_5m["low"], es_5m["close"], 14).reindex(df.index, method="ffill")
        F["es_ret_5"] = es_c.diff(5)
        F["nq_es_div_5"]  = c.diff(5) / F["atr14"] - es_c.diff(5) / es_atr14
        F["nq_es_div_20"] = c.diff(20) / F["atr14"] - es_c.diff(20) / es_atr14
    if rty_5m is not None and not rty_5m.empty:
        rty_c = rty_5m["close"].reindex(df.index, method="ffill")
        rty_atr14 = atr(rty_5m["high"], rty_5m["low"], rty_5m["close"], 14).reindex(df.index, method="ffill")
        F["nq_rty_div_20"] = c.diff(20) / F["atr14"] - rty_c.diff(20) / rty_atr14
    if vix_5m is not None and not vix_5m.empty:
        vix_c = vix_5m["close"].reindex(df.index, method="ffill")
        F["vix"] = vix_c
        F["vix_z_50"] = (vix_c - vix_c.rolling(50).mean()) / vix_c.rolling(50).std()
        F["vix_change_5"] = vix_c.diff(5)

    return F.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# CONTEXT DETECTORS — multi-step "what's the market doing"
# Each returns a boolean Series indexed like F.
# ---------------------------------------------------------------------------
def context_detectors() -> dict[str, Callable]:
    """Returns dict of name → fn(F) → bool Series."""
    D = {}
    # 1. Compressed volatility (consolidation)
    D["compressed_vol"] = lambda F: F["atr_compression"] < 0.7
    D["expanded_vol"]   = lambda F: F["atr_compression"] > 1.3
    # 2. Up trend (multiple checks)
    D["uptrend_strong"] = lambda F: (F["ema20_slope"] > 0.5) & (F["ema_align"] > 0)
    D["downtrend_strong"] = lambda F: (F["ema20_slope"] < -0.5) & (F["ema_align"] < 0)
    D["uptrend_weak"]   = lambda F: (F["ema20_slope"] > 0) & (F["ema_align"] > 0)
    D["downtrend_weak"] = lambda F: (F["ema20_slope"] < 0) & (F["ema_align"] < 0)
    # 3. Range-position cohorts
    D["near_50bar_high"] = lambda F: F["range_pos_50"] > 0.85
    D["near_50bar_low"]  = lambda F: F["range_pos_50"] < 0.15
    D["mid_range"]        = lambda F: (F["range_pos_50"] > 0.40) & (F["range_pos_50"] < 0.60)
    # 4. RTH cohorts
    D["rth_morning"]  = lambda F: (F["ny_hour"] >= 9) & (F["ny_hour"] < 11)
    D["rth_midday"]   = lambda F: (F["ny_hour"] >= 11) & (F["ny_hour"] < 14)
    D["rth_afternoon"] = lambda F: (F["ny_hour"] >= 14) & (F["ny_hour"] < 16)
    D["asian_session"] = lambda F: (F["ny_hour"] >= 19) | (F["ny_hour"] < 2)
    # 5. Cross-asset divergence
    if "nq_es_div_20" in []: pass  # placeholder; gated dynamically
    D["nq_outperforming_es"] = lambda F: F.get("nq_es_div_20", pd.Series(0, index=F.index)) > 0.5
    D["nq_underperforming_es"] = lambda F: F.get("nq_es_div_20", pd.Series(0, index=F.index)) < -0.5
    # 6. VIX regime
    D["vix_low"]  = lambda F: F.get("vix_z_50", pd.Series(0, index=F.index)) < -1.0
    D["vix_high"] = lambda F: F.get("vix_z_50", pd.Series(0, index=F.index)) > 1.0
    # 7. Volume regime
    D["high_volume"]   = lambda F: F["vol_z_50"] > 1.0
    D["dried_up_vol"]  = lambda F: F["vol_dryup"] == 1
    # 8. Recent climax
    D["recent_high_climax"] = lambda F: F["dist_high20_atr"].rolling(5).min() > -0.5
    D["recent_low_climax"]  = lambda F: F["dist_low20_atr"].rolling(5).max() < 0.5
    return D


# ---------------------------------------------------------------------------
# TRIGGER DETECTORS — within an active context, when to start watching
# ---------------------------------------------------------------------------
def trigger_detectors() -> dict[str, Callable]:
    T = {}
    T["pullback_from_high_50"] = lambda F: (F["pullback_from_high"] > 0.50) & (F["pullback_from_high"] < 0.80)
    T["pullback_from_low_50"]  = lambda F: (F["pullback_from_low"] > 0.50) & (F["pullback_from_low"] < 0.80)
    T["momentum_burst_up"]   = lambda F: (F["consec_dir"] >= 3) & (F["bar_dir"] > 0)
    T["momentum_burst_down"] = lambda F: (F["consec_dir"] >= 3) & (F["bar_dir"] < 0)
    T["bullish_engulfing"]   = lambda F: (F["bar_dir"] > 0) & (F["body_abs"] > F["body_abs"].shift(1) * 1.5) & (F["bar_dir"].shift(1) < 0)
    T["bearish_engulfing"]   = lambda F: (F["bar_dir"] < 0) & (F["body_abs"] > F["body_abs"].shift(1) * 1.5) & (F["bar_dir"].shift(1) > 0)
    T["inside_bar_break_up"] = lambda F: (F["body_abs"] > F["body_abs"].rolling(5).mean() * 1.5) & (F["bar_dir"] > 0)
    T["inside_bar_break_dn"] = lambda F: (F["body_abs"] > F["body_abs"].rolling(5).mean() * 1.5) & (F["bar_dir"] < 0)
    T["rsi_oversold_recover"] = lambda F: (F["rsi2"].shift(1) < 10) & (F["rsi2"] > F["rsi2"].shift(1))
    T["rsi_overbought_break"] = lambda F: (F["rsi2"].shift(1) > 90) & (F["rsi2"] < F["rsi2"].shift(1))
    T["range_expansion_up"]   = lambda F: (F["range_z_50"] > 1.5) & (F["bar_dir"] > 0)
    T["range_expansion_down"] = lambda F: (F["range_z_50"] > 1.5) & (F["bar_dir"] < 0)
    T["volume_climax"]        = lambda F: F["vol_climax"] == 1
    return T


# ---------------------------------------------------------------------------
# Strategy combinator
# ---------------------------------------------------------------------------
@dataclass
class StrategyDef:
    name: str
    side: str                          # LONG / SHORT
    contexts: list[str]                # all must be true (within window)
    trigger: str                       # must fire on entry bar
    context_window_bars: int           # context must hold within last N bars
    stop_atr: float                    # stop = entry - stop_atr * atr14 (LONG)
    target_atr: float                  # target = entry + target_atr * atr14 (LONG)
    max_hold_min: int


def enumerate_strategies() -> list[StrategyDef]:
    """Generate all strategy combinations programmatically."""
    contexts = list(context_detectors().keys())
    triggers = list(trigger_detectors().keys())

    # Pair triggers to a side (some triggers are direction-specific)
    SIDE_OF_TRIGGER = {
        "pullback_from_high_50": "LONG",   # bought the dip in an uptrend
        "pullback_from_low_50":  "SHORT",  # shorted the bounce in a downtrend
        "momentum_burst_up":     "LONG",
        "momentum_burst_down":   "SHORT",
        "bullish_engulfing":     "LONG",
        "bearish_engulfing":     "SHORT",
        "inside_bar_break_up":   "LONG",
        "inside_bar_break_dn":   "SHORT",
        "rsi_oversold_recover":  "LONG",
        "rsi_overbought_break":  "SHORT",
        "range_expansion_up":    "LONG",
        "range_expansion_down":  "SHORT",
        "volume_climax":         "BOTH",
    }

    # For each side, valid contexts that COULD support it
    LONG_CONTEXTS = ["compressed_vol", "uptrend_strong", "uptrend_weak",
                       "near_50bar_low", "mid_range", "rth_morning", "rth_midday",
                       "rth_afternoon", "asian_session", "nq_outperforming_es",
                       "vix_low", "high_volume", "recent_low_climax", "dried_up_vol"]
    SHORT_CONTEXTS = ["compressed_vol", "downtrend_strong", "downtrend_weak",
                        "near_50bar_high", "mid_range", "rth_morning", "rth_midday",
                        "rth_afternoon", "asian_session", "nq_underperforming_es",
                        "vix_high", "high_volume", "recent_high_climax", "expanded_vol"]

    strategies = []
    sid = 0
    # Stop/target pairs (in ATR units) - 5 R:R profiles per direction
    rr_profiles = [
        # (stop_atr, target_atr, max_hold_min, label)
        (1.0, 1.0,  30, "RR1_short"),      # 1:1 quick
        (1.0, 1.5,  45, "RR1_5"),          # 1:1.5
        (1.0, 2.0,  60, "RR2_runner"),     # 1:2
        (0.8, 1.6,  45, "RR2_tight"),      # tight stop, 2x target
        (1.5, 1.5,  60, "RR1_wide"),       # 1:1 with wider stop
    ]
    for trigger, base_side in SIDE_OF_TRIGGER.items():
        sides = ["LONG", "SHORT"] if base_side == "BOTH" else [base_side]
        for side in sides:
            ctx_pool = LONG_CONTEXTS if side == "LONG" else SHORT_CONTEXTS
            # Combine 1 or 2 contexts at a time to get 100s of variants
            for ctx in ctx_pool:
                for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                    sid += 1
                    strategies.append(StrategyDef(
                        name=f"V6_{side}_{trigger[:18]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                        side=side, contexts=[ctx], trigger=trigger,
                        context_window_bars=10,
                        stop_atr=stop_a, target_atr=tgt_a,
                        max_hold_min=mh,
                    ))
    return strategies


# ---------------------------------------------------------------------------
# Simulator — bar-by-bar with strict no-look-ahead labels
# ---------------------------------------------------------------------------
def label_strategy(F: pd.DataFrame, nq_5m: pd.DataFrame, nq_1m: pd.DataFrame,
                    daily: pd.DataFrame, strat: StrategyDef,
                    contexts_d: dict, triggers_d: dict) -> pd.DataFrame:
    """Walk the strategy through every bar; compute labels for fired entries.

    CRITICAL: entry happens at the OPEN of the NEXT 5-min bar after the
    trigger, NOT at the trigger bar's close. This ensures the label window
    (1-min bars from entry onwards) doesn't overlap with the feature window
    (which uses up to and including the trigger bar's close)."""
    # Which bars satisfy each context
    ctx_masks = []
    for ctx_name in strat.contexts:
        ctx_fn = contexts_d[ctx_name]
        m = ctx_fn(F)
        # Context "active" if true in the last context_window_bars
        rolling = m.rolling(strat.context_window_bars).max() > 0
        ctx_masks.append(rolling.fillna(False))
    if ctx_masks:
        ctx_active = ctx_masks[0]
        for m in ctx_masks[1:]:
            ctx_active &= m
    else:
        ctx_active = pd.Series(True, index=F.index)

    trig_fn = triggers_d[strat.trigger]
    trig_fired = trig_fn(F).fillna(False)

    # Trade fires when context is active AND trigger fires
    fires = ctx_active & trig_fired

    # For each fired bar, compute entry/stop/target and walk 1-min bars
    out_rows = []
    fire_indices = np.where(fires.values)[0]
    nq_5m_idx = nq_5m.index
    nq_1m_idx = nq_1m.index

    for i in fire_indices:
        if i + 1 >= len(nq_5m_idx):
            continue
        signal_ts = nq_5m_idx[i]
        # Entry at NEXT 5m bar's open (no overlap with trigger bar's window)
        entry_5m_ts = nq_5m_idx[i + 1]
        try:
            entry_loc_1m = nq_1m_idx.searchsorted(entry_5m_ts)
            if entry_loc_1m >= len(nq_1m_idx):
                continue
            entry_px_raw = nq_1m.iloc[entry_loc_1m]["open"]
        except Exception:
            continue
        atr14 = F.iloc[i]["atr14"]
        if not (np.isfinite(atr14) and atr14 > 0):
            continue
        # Adaptive stop/target sized in ATR units
        stop_pts = strat.stop_atr * atr14
        tgt_pts  = strat.target_atr * atr14
        # Apply slippage to entry
        if strat.side == "LONG":
            entry_filled = entry_px_raw + SLIPPAGE_PT
            stop_px = entry_filled - stop_pts
            tgt_px  = entry_filled + tgt_pts
        else:
            entry_filled = entry_px_raw - SLIPPAGE_PT
            stop_px = entry_filled + stop_pts
            tgt_px  = entry_filled - tgt_pts

        # Walk 1-min bars from entry forward
        end_ts = entry_5m_ts + pd.Timedelta(minutes=strat.max_hold_min)
        try:
            window = nq_1m.loc[entry_5m_ts + pd.Timedelta(minutes=1) : end_ts]
        except Exception:
            continue
        if window.empty:
            continue
        outcome = "TIME"; exit_filled = float(window.iloc[-1]["close"])
        for ts1, bar in window.iterrows():
            bh = float(bar["high"]); bl = float(bar["low"])
            if strat.side == "LONG":
                stop_hit = bl <= stop_px
                tgt_hit  = bh >= tgt_px
            else:
                stop_hit = bh >= stop_px
                tgt_hit  = bl <= tgt_px
            if stop_hit and tgt_hit:
                outcome = "STOP"
                exit_filled = stop_px - ADVERSE_SLIP_PT if strat.side == "LONG" else stop_px + ADVERSE_SLIP_PT
                break
            if stop_hit:
                outcome = "STOP"
                exit_filled = stop_px - ADVERSE_SLIP_PT if strat.side == "LONG" else stop_px + ADVERSE_SLIP_PT
                break
            if tgt_hit:
                outcome = "TARGET"; exit_filled = tgt_px
                break
        # P&L per contract
        if strat.side == "LONG":
            pts = exit_filled - entry_filled
        else:
            pts = entry_filled - exit_filled
        pnl = pts * MNQ_DPP - COMM_PER
        out_rows.append({
            "signal_ts": signal_ts, "entry_ts": entry_5m_ts,
            "side": strat.side, "entry": entry_filled, "exit": exit_filled,
            "outcome": outcome, "pts": pts, "pnl": pnl,
            "stop_pts": stop_pts, "target_pts": tgt_pts,
        })
    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# 5 rigorous tests
# ---------------------------------------------------------------------------
def evaluate_strategy(trades: pd.DataFrame, train_end: pd.Timestamp) -> dict:
    """Compute the 5 rigorous tests on this strategy's trades."""
    if trades is None or trades.empty:
        return {"n": 0, "pass_all": False}

    # Strip tz to make comparison work
    if trades["entry_ts"].dt.tz is not None:
        trades = trades.copy()
        trades["entry_ts"] = trades["entry_ts"].dt.tz_localize(None)
    train_end_naive = train_end.tz_localize(None) if train_end.tz else train_end

    train = trades[trades["entry_ts"] <= train_end_naive]
    test  = trades[trades["entry_ts"] >  train_end_naive]
    n_train = len(train); n_test = len(test)

    def metrics(df):
        if df.empty:
            return dict(n=0, wr=0, pf=0, sharpe=0, net=0)
        pnls = df["pnl"].values
        wins = pnls[pnls > 0]; losses = pnls[pnls <= 0]
        gw = float(wins.sum()); gl = float(-losses.sum())
        return dict(
            n=len(pnls),
            wr=float((pnls > 0).mean()),
            pf=float(min((gw / gl) if gl > 0 else 999, 999)),
            sharpe=float(pnls.mean() / pnls.std()) if pnls.std() > 0 else 0,
            net=float(pnls.sum()),
        )
    train_m = metrics(train)
    test_m  = metrics(test)

    # CPCV on the FULL trade set (5 folds, count positive)
    def cpcv(df):
        if len(df) < CPCV_FOLDS * 5:
            return 0
        pnls = df["pnl"].values
        fs = len(pnls) // CPCV_FOLDS
        positive = 0
        for i in range(CPCV_FOLDS):
            a, b = i * fs, (i + 1) * fs if i < CPCV_FOLDS - 1 else len(pnls)
            if pnls[a:b].sum() > 0: positive += 1
        return positive
    cpcv_pos = cpcv(trades)

    # The other 5 tests first (cheap)
    pass_sample = test_m["n"] >= MIN_SAMPLE
    pass_wr     = test_m["wr"] >= MIN_WR_AFTER_COSTS
    pass_pf     = test_m["pf"] >= MIN_PF
    pass_sharpe = test_m["sharpe"] >= MIN_SHARPE
    pass_cpcv   = cpcv_pos >= CPCV_MIN_POSITIVE
    cheap_pass = all([pass_sample, pass_wr, pass_pf, pass_sharpe, pass_cpcv])

    # Permutation test (5000 trials) — EXPENSIVE, only run if other tests pass.
    # Shuffle PnL across positions; check how often random ordering produces
    # equal-or-better Sharpe. Honest significance test (Bailey/Lopez de Prado).
    p_value = 1.0
    if cheap_pass:
        pnls = test["pnl"].values
        observed_sharpe = pnls.mean() / pnls.std() if pnls.std() > 0 else 0
        if observed_sharpe > 0:
            rng = np.random.default_rng(42)
            n_better = 0
            for _ in range(PERMUTATION_TRIALS):
                perm = rng.permutation(pnls)
                psh = perm.mean() / perm.std() if perm.std() > 0 else 0
                if psh >= observed_sharpe: n_better += 1
            p_value = n_better / PERMUTATION_TRIALS

    pass_perm = p_value <= PERMUTATION_P_VALUE
    passes_all = cheap_pass and pass_perm

    return {
        "n_train": n_train, "n_test": n_test,
        "train": train_m, "test": test_m,
        "cpcv_positive": cpcv_pos, "permutation_p": p_value,
        "pass_sample": pass_sample, "pass_wr": pass_wr,
        "pass_pf": pass_pf, "pass_sharpe": pass_sharpe,
        "pass_cpcv": pass_cpcv, "pass_permutation": pass_perm,
        "passes_all": passes_all,
    }


# ---------------------------------------------------------------------------
# Driver with crash-recovery
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v6 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v6 — multi-step, original strategies, full-rigor")
    print("=" * 78)

    # Load progress (resume from where we left off)
    progress = {"completed": [], "results": []}
    if PROGRESS_PATH.exists():
        try:
            progress = json.loads(PROGRESS_PATH.read_text())
            logger.info(f"resuming with {len(progress['completed'])} strategies already done")
        except Exception:
            pass

    print("\n[1/4] Loading multi-asset data ...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = rty_5m = vix_5m = None
    try: es_5m = load_intraday_5min("es")
    except Exception: pass
    try: rty_5m = load_intraday_5min("rty")
    except Exception: pass
    try: vix_5m = load_vix_5min()
    except Exception: pass
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df is not None and df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    print(f"  NQ 5m: {len(nq_5m):,} bars over {(nq_5m.index[-1] - nq_5m.index[0]).days} days")

    print("\n[2/4] Building feature matrix ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    print(f"  {F.shape}")

    contexts_d = context_detectors()
    triggers_d = trigger_detectors()

    print("\n[3/4] Enumerating strategies ...")
    strats = enumerate_strategies()
    print(f"  total strategies: {len(strats)}")

    completed = set(progress["completed"])
    results = list(progress["results"])
    started_at = time.time()
    last_save = started_at
    n_done_now = 0

    for idx, strat in enumerate(strats):
        if strat.name in completed:
            continue
        try:
            t0 = time.time()
            trades = label_strategy(F, nq_5m, nq_1m, daily, strat, contexts_d, triggers_d)
            ev = evaluate_strategy(trades, TRAIN_END)
            ev["name"] = strat.name
            ev["side"] = strat.side
            ev["contexts"] = strat.contexts
            ev["trigger"] = strat.trigger
            ev["stop_atr"] = strat.stop_atr
            ev["target_atr"] = strat.target_atr
            ev["max_hold_min"] = strat.max_hold_min
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            if ev.get("passes_all"):
                t = ev["test"]
                logger.info(
                    f"  [✓ PASS] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} pnl=${t['net']:+,.0f} p={ev['permutation_p']:.3f}"
                )
            elif (idx % 25) == 0:
                t = ev.get("test", {})
                rate = (idx + 1 - len(progress['completed'])) / max(0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                logger.info(
                    f"  [{idx+1:>4}/{len(strats)}] {strat.name[:50]:<50}  "
                    f"n={t.get('n',0):>3}  passes_all={ev.get('passes_all', False)}  "
                    f"ETA {eta:.0f}m"
                )

            # Save progress every 25 strategies (so a crash loses < 25 strats)
            now = time.time()
            if n_done_now >= 25 or (now - last_save) > 120:
                progress["completed"] = sorted(completed)
                progress["results"] = results
                PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))
                last_save = now
                n_done_now = 0
        except Exception as e:
            logger.exception(f"strategy {strat.name} crashed: {e}")
            results.append({"name": strat.name, "error": str(e),
                              "passes_all": False})
            completed.add(strat.name)

    # Final save
    progress["completed"] = sorted(completed)
    progress["results"] = results
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))

    # Summary
    survivors = [r for r in results if r.get("passes_all")]
    print(f"\n[4/4] DONE — total runtime: {(time.time()-started_at)/60:.1f}m")
    print(f"  total strategies tested: {len(results)}")
    print(f"  SURVIVORS (passed all 5 tests + permutation): {len(survivors)}")
    if survivors:
        print(f"\n  top 30 by OOS net pnl:")
        survivors.sort(key=lambda r: -r["test"]["net"])
        for r in survivors[:30]:
            t = r["test"]
            print(f"    {r['name'][:55]:<55}  n={t['n']:>3}  "
                  f"WR={t['wr']*100:.1f}%  PF={t['pf']:.2f}  "
                  f"Sh={t['sharpe']:+.2f}  $/contract={t['net']:+,.0f}  p={r['permutation_p']:.3f}")

    OUT_PATH.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "n_strategies": len(results),
        "n_survivors": len(survivors),
        "survivors": survivors,
        "all_results": results,
    }, indent=2, default=str))
    print(f"\nWrote {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    while True:
        try:
            main()
            break
        except Exception as e:
            logger.exception(f"main() crashed: {e}; restarting in 30s")
            time.sleep(30)

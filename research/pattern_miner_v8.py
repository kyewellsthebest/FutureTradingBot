"""
Pattern Miner v8 — 1000+ strategies, ALL with 1:3 RR minimum.

User-specified minimum requirements:
  * 1:3 RR or better (target_atr / stop_atr >= 3.0)
  * 55% win rate or better (after costs)
  * 1+ trade per week (>= 100 trades over the ~2.3yr OOS window)

Strategy categories (target ~1000+ unique strategies):
  TC — Trend Continuation: strong trend + pullback to support
  SA — Stat-Arb Reversion:  NQ-ES divergence beyond Z-threshold
  LL — Lead-Lag:            ES/RTY moves first, NQ catches up
  VB — Volatility Breakout: range compression then break
  MC — Multi-Confluence:    3+ orthogonal conditions aligned
  TA — Time-Anchored:       specific high-edge time windows
  HM — Higher-Timeframe:    1h trend + 5m entry alignment

Bar-by-bar simulator (re-uses v6 label_strategy with no-leak entries),
5 rigorous tests + 5,000-trial permutation, CPCV folds.

Auto-recovery: progress saved every 10 strategies; bash watchdog restarts
the process on crash; module reloads pick up code edits between attempts.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, evaluate_strategy, StrategyDef,
    MNQ_DPP, SLIPPAGE_PT, ADVERSE_SLIP_PT, COMM_PER,
    MIN_SAMPLE, MIN_PF, MIN_SHARPE,
    PERMUTATION_TRIALS, PERMUTATION_P_VALUE,
    CPCV_FOLDS, CPCV_MIN_POSITIVE, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.indicators import atr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v8_patterns.json"
PROGRESS_PATH = DATA / "v8_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v8.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v8")

# User-specified minimum requirements
USER_MIN_WR = 0.55
USER_MIN_RR = 3.0          # target_atr / stop_atr >= 3
USER_MIN_TRADES = 100      # ~1 trade/week over 2.3yr OOS


# ---------------------------------------------------------------------------
# v8 feature additions: VWAP, pivot points, ADX, higher-timeframe
# ---------------------------------------------------------------------------
def build_v8_extras(F: pd.DataFrame, nq_5m: pd.DataFrame,
                     daily: pd.DataFrame) -> pd.DataFrame:
    F = F.copy()
    o, h, l, c, v = nq_5m["open"], nq_5m["high"], nq_5m["low"], nq_5m["close"], nq_5m["volume"]

    # Session VWAP (resets daily NY-time)
    NY = "America/New_York"
    idx_ny = nq_5m.index.tz_convert(NY)
    session_date = pd.Series(idx_ny.date, index=nq_5m.index)
    typical = (h + l + c) / 3.0
    pv = (typical * v).groupby(session_date).cumsum()
    cv = v.groupby(session_date).cumsum().replace(0, np.nan)
    F["vwap"] = pv / cv
    F["dist_vwap_atr"] = (c - F["vwap"]) / F["atr14"]

    # 1H aggregation (with strict shift to avoid lookahead)
    h1 = nq_5m.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    h1_ema20 = h1["close"].ewm(span=20, adjust=False).mean()
    h1_ema50 = h1["close"].ewm(span=50, adjust=False).mean()
    h1_align = np.sign(h1_ema20 - h1_ema50)
    h1_slope = h1_ema20.diff(5)
    h1_atr = atr(h1["high"], h1["low"], h1["close"], 14)
    h1_dist_ema = (h1["close"] - h1_ema50) / h1_atr
    # Reindex to 5m bars, SHIFT by 1 hour to avoid leak (1h bar at 13:00 closes at 14:00)
    F["h1_align"] = h1_align.shift(1).reindex(F.index, method="ffill")
    F["h1_slope"] = h1_slope.shift(1).reindex(F.index, method="ffill")
    F["h1_dist_ema_atr"] = h1_dist_ema.shift(1).reindex(F.index, method="ffill")

    # Pivot points (from previous DAILY session — leak-safe via shift)
    # Use UTC trading-day key to avoid the original tz_convert leak
    daily_idx_utc_date = pd.to_datetime(daily.index).tz_convert("UTC").date if daily.index.tz else pd.to_datetime(daily.index).date
    daily2 = daily.copy()
    daily2.index = pd.DatetimeIndex(daily_idx_utc_date)
    pivot = (daily2["high"] + daily2["low"] + daily2["close"]) / 3.0
    r1 = 2 * pivot - daily2["low"]
    s1 = 2 * pivot - daily2["high"]
    r2 = pivot + (daily2["high"] - daily2["low"])
    s2 = pivot - (daily2["high"] - daily2["low"])
    pivots = pd.DataFrame({"pivot": pivot, "r1": r1, "s1": s1, "r2": r2, "s2": s2})
    pivots = pivots.shift(1)  # prev day pivots

    nq_utc_date = pd.DatetimeIndex(F.index.tz_convert("UTC").date if F.index.tz else F.index.date)
    F["pivot_dist_atr"] = (c.values - pivots["pivot"].reindex(nq_utc_date).values) / F["atr14"].values
    F["r1_dist_atr"]    = (c.values - pivots["r1"].reindex(nq_utc_date).values)    / F["atr14"].values
    F["s1_dist_atr"]    = (c.values - pivots["s1"].reindex(nq_utc_date).values)    / F["atr14"].values
    F["r2_dist_atr"]    = (c.values - pivots["r2"].reindex(nq_utc_date).values)    / F["atr14"].values
    F["s2_dist_atr"]    = (c.values - pivots["s2"].reindex(nq_utc_date).values)    / F["atr14"].values

    # ADX-like trend strength (simple proxy: |EMA20 - EMA50| / ATR)
    F["trend_strength"] = (c.ewm(span=20, adjust=False).mean() -
                            c.ewm(span=50, adjust=False).mean()).abs() / F["atr14"]

    # Range compression (Bollinger-like)
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    F["bb_width_atr"] = (4 * bb_std) / F["atr14"]
    F["bb_pos"] = (c - bb_mid) / (2 * bb_std).replace(0, np.nan)

    # Pullback structure (where in the swing range)
    F["above_vwap"] = (F["dist_vwap_atr"] > 0).astype(int)
    F["below_vwap"] = (F["dist_vwap_atr"] < 0).astype(int)

    return F.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# v8 trigger detectors — pre-compute everything as boolean Series
# ---------------------------------------------------------------------------
def v8_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    T = {}
    # ---- Trend Continuation triggers ----
    T["pullback_to_vwap_long"]  = (F["dist_vwap_atr"].abs() < 0.3) & (F["bar_dir"] > 0) & (F["dist_vwap_atr"].shift(1) < -0.3)
    T["pullback_to_vwap_short"] = (F["dist_vwap_atr"].abs() < 0.3) & (F["bar_dir"] < 0) & (F["dist_vwap_atr"].shift(1) > 0.3)
    T["pullback_to_ema50_long"] = (F["ema_dist_atr"].abs() < 0.3) & (F["bar_dir"] > 0)
    T["pullback_to_ema50_short"] = (F["ema_dist_atr"].abs() < 0.3) & (F["bar_dir"] < 0)
    T["pullback_38_long"]  = (F["pullback_from_high"] > 0.30) & (F["pullback_from_high"] < 0.50) & (F["bar_dir"] > 0)
    T["pullback_38_short"] = (F["pullback_from_low"] > 0.30) & (F["pullback_from_low"] < 0.50) & (F["bar_dir"] < 0)
    T["pullback_50_long"]  = (F["pullback_from_high"] > 0.45) & (F["pullback_from_high"] < 0.65) & (F["bar_dir"] > 0)
    T["pullback_50_short"] = (F["pullback_from_low"] > 0.45) & (F["pullback_from_low"] < 0.65) & (F["bar_dir"] < 0)
    T["pullback_61_long"]  = (F["pullback_from_high"] > 0.55) & (F["pullback_from_high"] < 0.75) & (F["bar_dir"] > 0)
    T["pullback_61_short"] = (F["pullback_from_low"] > 0.55) & (F["pullback_from_low"] < 0.75) & (F["bar_dir"] < 0)

    # ---- Pivot point reactions ----
    T["bounce_off_s1"] = (F["s1_dist_atr"].abs() < 0.3) & (F["bar_dir"] > 0) & (F["s1_dist_atr"].shift(1) < -0.3)
    T["reject_at_r1"]  = (F["r1_dist_atr"].abs() < 0.3) & (F["bar_dir"] < 0) & (F["r1_dist_atr"].shift(1) > 0.3)
    T["bounce_off_s2"] = (F["s2_dist_atr"].abs() < 0.3) & (F["bar_dir"] > 0) & (F["s2_dist_atr"].shift(1) < -0.3)
    T["reject_at_r2"]  = (F["r2_dist_atr"].abs() < 0.3) & (F["bar_dir"] < 0) & (F["r2_dist_atr"].shift(1) > 0.3)
    T["break_above_r1"] = (F["r1_dist_atr"] > 0.3) & (F["r1_dist_atr"].shift(1) < 0.3) & (F["bar_dir"] > 0)
    T["break_below_s1"] = (F["s1_dist_atr"] < -0.3) & (F["s1_dist_atr"].shift(1) > -0.3) & (F["bar_dir"] < 0)
    T["break_above_pdh"] = (F["dist_pdh_atr"] > 0.3) & (F["dist_pdh_atr"].shift(1) < 0.3) & (F["bar_dir"] > 0)
    T["break_below_pdl"] = (F["dist_pdl_atr"] < -0.3) & (F["dist_pdl_atr"].shift(1) > -0.3) & (F["bar_dir"] < 0)

    # ---- Volatility breakout triggers ----
    T["bb_squeeze_break_up"]   = (F["bb_width_atr"].shift(1) < 1.0) & (F["bar_dir"] > 0) & (F["body_abs"] > F["atr14"] * 0.6)
    T["bb_squeeze_break_down"] = (F["bb_width_atr"].shift(1) < 1.0) & (F["bar_dir"] < 0) & (F["body_abs"] > F["atr14"] * 0.6)
    T["range_expansion_long"]  = (F["range_z_50"] > 1.5) & (F["bar_dir"] > 0) & (F["consec_dir"] >= 2)
    T["range_expansion_short"] = (F["range_z_50"] > 1.5) & (F["bar_dir"] < 0) & (F["consec_dir"] >= 2)

    # ---- Stat-arb (NQ-ES) ----
    if "nq_es_div_z_20" in F.columns:
        for w in [20, 60]:
            for thr in [1.5, 2.0, 2.5]:
                T[f"sa_short_{w}_{int(thr*10)}"] = F[f"nq_es_div_z_{w}"] > thr
                T[f"sa_long_{w}_{int(thr*10)}"]  = F[f"nq_es_div_z_{w}"] < -thr

    # ---- Lead-lag ----
    if "lag_nq_es_z_5" in F.columns:
        for k in [3, 5, 10]:
            for thr in [1.0, 1.5, 2.0]:
                T[f"ll_long_{k}_{int(thr*10)}"]  = (F[f"es_move_z_{k}"] > thr) & (F[f"lag_nq_es_z_{k}"] > 0.5)
                T[f"ll_short_{k}_{int(thr*10)}"] = (F[f"es_move_z_{k}"] < -thr) & (F[f"lag_nq_es_z_{k}"] < -0.5)

    return {k: v.fillna(False) for k, v in T.items()}


# ---------------------------------------------------------------------------
# v8 context detectors
# ---------------------------------------------------------------------------
def v8_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    C = {}
    # Trend strength contexts
    C["trend_up_strong"]   = (F["ema_align"] > 0) & (F["trend_strength"] > 0.5) & (F["ema20_slope"] > 0)
    C["trend_down_strong"] = (F["ema_align"] < 0) & (F["trend_strength"] > 0.5) & (F["ema20_slope"] < 0)
    C["trend_up_weak"]     = (F["ema_align"] > 0) & (F["ema20_slope"] > 0)
    C["trend_down_weak"]   = (F["ema_align"] < 0) & (F["ema20_slope"] < 0)
    C["h1_up"]             = F["h1_align"] > 0
    C["h1_down"]           = F["h1_align"] < 0
    C["h1_strong_up"]      = (F["h1_align"] > 0) & (F["h1_slope"] > 0)
    C["h1_strong_down"]    = (F["h1_align"] < 0) & (F["h1_slope"] < 0)

    # Volatility regime
    C["vol_compressed"] = F["atr_compression"] < 0.7
    C["vol_normal"]     = (F["atr_compression"] >= 0.7) & (F["atr_compression"] <= 1.3)
    C["vol_expanded"]   = F["atr_compression"] > 1.3
    C["bb_squeeze"]     = F["bb_width_atr"] < 1.0

    # Position vs VWAP / EMA
    C["above_vwap"] = F["dist_vwap_atr"] > 0
    C["below_vwap"] = F["dist_vwap_atr"] < 0
    C["above_ema50"] = F["ema_dist_atr"] > 0
    C["below_ema50"] = F["ema_dist_atr"] < 0

    # Time-of-day
    C["am_open"]   = (F["ny_hour"] == 9) & (F["ny_minute"] >= 30)
    C["am"]        = (F["ny_hour"] >= 9) & (F["ny_hour"] < 11)
    C["midday"]    = (F["ny_hour"] >= 11) & (F["ny_hour"] < 14)
    C["pm"]        = (F["ny_hour"] >= 14) & (F["ny_hour"] < 16)
    C["rth"]       = (F["ny_hour"] >= 9) & (F["ny_hour"] < 16)
    C["overnight"] = (F["ny_hour"] >= 18) | (F["ny_hour"] < 9)

    # VIX regime
    if "vix_z_50" in F.columns:
        C["vix_low"]  = F["vix_z_50"] < -0.5
        C["vix_med"]  = (F["vix_z_50"] >= -0.5) & (F["vix_z_50"] <= 0.5)
        C["vix_high"] = F["vix_z_50"] > 0.5

    # Volume regime
    C["vol_high"]  = F["vol_z_50"] > 1.0
    C["vol_low"]   = F["vol_z_50"] < -0.5

    return {k: v.fillna(False) for k, v in C.items()}


# ---------------------------------------------------------------------------
# v8 strategy enumeration: target ~1000+ strategies, ALL with 1:3 RR minimum
# ---------------------------------------------------------------------------
def enumerate_v8_strategies(F: pd.DataFrame) -> list[StrategyDef]:
    has_es = "nq_es_div_z_20" in F.columns

    # RR profiles — ALL 1:3 RR or better (target_atr / stop_atr >= 3.0)
    rr_profiles = [
        # (stop_atr, target_atr, max_hold_min, label)
        (1.0, 3.0,  60, "RR3_std"),
        (1.0, 3.5,  75, "RR3_5"),
        (1.0, 4.0,  90, "RR4"),
        (0.8, 2.5,  60, "RR3_tight"),
        (1.5, 4.5,  90, "RR3_wide"),
    ]

    strategies = []
    sid = 0

    # ---- TC: Trend Continuation (~250 strategies) ----
    TC_PULLBACKS = [
        ("pullback_to_vwap_long",   "LONG",  ["trend_up_strong"]),
        ("pullback_to_vwap_long",   "LONG",  ["trend_up_weak"]),
        ("pullback_to_vwap_long",   "LONG",  ["h1_strong_up"]),
        ("pullback_to_vwap_short",  "SHORT", ["trend_down_strong"]),
        ("pullback_to_vwap_short",  "SHORT", ["trend_down_weak"]),
        ("pullback_to_vwap_short",  "SHORT", ["h1_strong_down"]),
        ("pullback_to_ema50_long",  "LONG",  ["trend_up_strong"]),
        ("pullback_to_ema50_long",  "LONG",  ["h1_up"]),
        ("pullback_to_ema50_short", "SHORT", ["trend_down_strong"]),
        ("pullback_to_ema50_short", "SHORT", ["h1_down"]),
        ("pullback_38_long",        "LONG",  ["trend_up_strong"]),
        ("pullback_38_long",        "LONG",  ["trend_up_weak"]),
        ("pullback_38_short",       "SHORT", ["trend_down_strong"]),
        ("pullback_38_short",       "SHORT", ["trend_down_weak"]),
        ("pullback_50_long",        "LONG",  ["trend_up_strong"]),
        ("pullback_50_long",        "LONG",  ["h1_up"]),
        ("pullback_50_short",       "SHORT", ["trend_down_strong"]),
        ("pullback_50_short",       "SHORT", ["h1_down"]),
        ("pullback_61_long",        "LONG",  ["trend_up_strong", "h1_up"]),
        ("pullback_61_short",       "SHORT", ["trend_down_strong", "h1_down"]),
    ]
    TC_SESSIONS = ["am", "midday", "pm", "rth"]
    for trig, side, base_ctx in TC_PULLBACKS:
        for sess in TC_SESSIONS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                ctxs = base_ctx + [sess]
                strategies.append(StrategyDef(
                    name=f"V8TC_{side}_{trig[:14]}_x_{'_'.join(c[:5] for c in ctxs)}_{rrlabel}_{sid:04d}",
                    side=side, contexts=ctxs, trigger=trig,
                    context_window_bars=10,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    # ---- VB: Volatility Breakout (~150 strategies) ----
    VB_TRIGGERS = [
        ("bb_squeeze_break_up",   "LONG"),
        ("bb_squeeze_break_down", "SHORT"),
        ("range_expansion_long",  "LONG"),
        ("range_expansion_short", "SHORT"),
    ]
    VB_CONTEXTS = ["vol_compressed", "vol_low", "am", "midday", "pm",
                    "h1_up", "h1_down", "above_vwap", "below_vwap"]
    for trig, side in VB_TRIGGERS:
        for ctx in VB_CONTEXTS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"V8VB_{side}_{trig[:14]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=5,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    # ---- PIV: Pivot point reactions (~150 strategies) ----
    PIV_TRIGGERS = [
        ("bounce_off_s1",   "LONG"),
        ("reject_at_r1",    "SHORT"),
        ("bounce_off_s2",   "LONG"),
        ("reject_at_r2",    "SHORT"),
        ("break_above_r1",  "LONG"),
        ("break_below_s1",  "SHORT"),
        ("break_above_pdh", "LONG"),
        ("break_below_pdl", "SHORT"),
    ]
    PIV_CONTEXTS = ["am", "midday", "pm", "h1_up", "h1_down"]
    for trig, side in PIV_TRIGGERS:
        for ctx in PIV_CONTEXTS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"V8PIV_{side}_{trig[:14]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=5,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    # ---- SA: Stat-Arb (~180 strategies) ----
    if has_es:
        SA_TRIGGERS = []
        for w in [20, 60]:
            for thr in [15, 20, 25]:
                SA_TRIGGERS.append((f"sa_short_{w}_{thr}", "SHORT"))
                SA_TRIGGERS.append((f"sa_long_{w}_{thr}",  "LONG"))
        SA_CONTEXTS = ["am", "midday", "pm"]
        for trig, side in SA_TRIGGERS:
            for ctx in SA_CONTEXTS:
                for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                    sid += 1
                    strategies.append(StrategyDef(
                        name=f"V8SA_{side}_{trig[:14]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                        side=side, contexts=[ctx], trigger=trig,
                        context_window_bars=5,
                        stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                    ))

    # ---- LL: Lead-Lag (~120 strategies) ----
    if has_es:
        LL_TRIGGERS = []
        for k in [3, 5, 10]:
            for thr in [10, 15, 20]:
                LL_TRIGGERS.append((f"ll_long_{k}_{thr}",  "LONG"))
                LL_TRIGGERS.append((f"ll_short_{k}_{thr}", "SHORT"))
        LL_CONTEXTS = ["am", "midday", "pm", "h1_up", "h1_down"]
        # Lead-lag wants quicker exits even at 1:3 RR
        ll_rrs = [
            (1.0, 3.0,  30, "RR3_fast"),
            (0.8, 2.5,  30, "RR3_tight"),
            (1.0, 3.0,  60, "RR3_med"),
        ]
        for trig, side in LL_TRIGGERS:
            for ctx in LL_CONTEXTS:
                for stop_a, tgt_a, mh, rrlabel in ll_rrs:
                    sid += 1
                    strategies.append(StrategyDef(
                        name=f"V8LL_{side}_{trig[:14]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                        side=side, contexts=[ctx], trigger=trig,
                        context_window_bars=3,
                        stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                    ))

    # ---- MC: Multi-Confluence (~120 strategies) ----
    MC_PAIRS = [
        ("pullback_to_vwap_long",   "LONG",  ["h1_strong_up", "vol_normal"]),
        ("pullback_to_vwap_short",  "SHORT", ["h1_strong_down", "vol_normal"]),
        ("pullback_to_ema50_long",  "LONG",  ["h1_up", "vix_low"]),
        ("pullback_to_ema50_short", "SHORT", ["h1_down", "vix_low"]),
        ("bb_squeeze_break_up",     "LONG",  ["vol_compressed", "h1_up"]),
        ("bb_squeeze_break_down",   "SHORT", ["vol_compressed", "h1_down"]),
        ("break_above_pdh",         "LONG",  ["h1_up", "am"]),
        ("break_below_pdl",         "SHORT", ["h1_down", "am"]),
        ("range_expansion_long",    "LONG",  ["above_vwap", "h1_up"]),
        ("range_expansion_short",   "SHORT", ["below_vwap", "h1_down"]),
        ("pullback_38_long",        "LONG",  ["h1_strong_up", "vix_low"]),
        ("pullback_38_short",       "SHORT", ["h1_strong_down", "vix_high"]),
    ]
    MC_SESSIONS = ["am", "midday", "pm", "rth"]
    for trig, side, base_ctx in MC_PAIRS:
        for sess in MC_SESSIONS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                ctxs = base_ctx + [sess]
                strategies.append(StrategyDef(
                    name=f"V8MC_{side}_{trig[:14]}_x_{'_'.join(c[:5] for c in ctxs)}_{rrlabel}_{sid:04d}",
                    side=side, contexts=ctxs, trigger=trig,
                    context_window_bars=10,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    # ---- HM: Higher-Timeframe alignment (~100 strategies) ----
    HM_PAIRS = [
        ("pullback_38_long",  "LONG",  ["h1_strong_up", "above_ema50"]),
        ("pullback_50_long",  "LONG",  ["h1_strong_up", "above_ema50"]),
        ("pullback_61_long",  "LONG",  ["h1_strong_up", "above_ema50"]),
        ("pullback_38_short", "SHORT", ["h1_strong_down", "below_ema50"]),
        ("pullback_50_short", "SHORT", ["h1_strong_down", "below_ema50"]),
        ("pullback_61_short", "SHORT", ["h1_strong_down", "below_ema50"]),
        ("break_above_pdh",   "LONG",  ["h1_strong_up"]),
        ("break_below_pdl",   "SHORT", ["h1_strong_down"]),
    ]
    HM_SESSIONS = ["am", "midday", "pm"]
    for trig, side, base_ctx in HM_PAIRS:
        for sess in HM_SESSIONS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                ctxs = base_ctx + [sess]
                strategies.append(StrategyDef(
                    name=f"V8HM_{side}_{trig[:12]}_x_{'_'.join(c[:5] for c in ctxs)}_{rrlabel}_{sid:04d}",
                    side=side, contexts=ctxs, trigger=trig,
                    context_window_bars=10,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    return strategies


def make_v8_detector_dicts(F: pd.DataFrame):
    contexts_d_series = v8_context_detectors(F)
    triggers_d_series = v8_trigger_detectors(F)
    def make_fn(s):
        return lambda F, _s=s: _s
    contexts_d = {k: make_fn(v) for k, v in contexts_d_series.items()}
    triggers_d = {k: make_fn(v) for k, v in triggers_d_series.items()}
    return contexts_d, triggers_d


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main(enumerate_only: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v8 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v8 — 1000+ strategies @ 1:3 RR minimum")
    print("=" * 78)

    progress = {"completed": [], "results": []}
    if PROGRESS_PATH.exists():
        try:
            progress = json.loads(PROGRESS_PATH.read_text())
            logger.info(f"resuming with {len(progress['completed'])} done")
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
    print(f"  NQ 5m: {len(nq_5m):,} bars over {(nq_5m.index[-1]-nq_5m.index[0]).days} days")

    print("\n[2/4] Building v8 features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    print(f"  {F.shape}")

    print("\n[3/4] Enumerating strategies ...")
    strats = enumerate_v8_strategies(F)
    print(f"  TOTAL STRATEGIES: {len(strats)}")
    from collections import Counter
    cats = Counter(s.name[:5] for s in strats)
    for cat, n in sorted(cats.items()):
        print(f"  {cat}: {n}")
    # Verify ALL strategies have 1:3+ RR
    bad_rr = [s for s in strats if (s.target_atr / s.stop_atr) < 3.0]
    print(f"  Strategies with RR < 3:1: {len(bad_rr)} (should be 0)")
    assert len(bad_rr) == 0, "RR constraint violated!"

    if enumerate_only:
        # Save the enumeration without running tests
        PROGRESS_PATH.write_text(json.dumps({
            "ENUMERATION_ONLY": True,
            "total_strategies": len(strats),
            "categories": dict(cats),
            "strategies_preview": [s.__dict__ for s in strats[:5]],
        }, indent=2, default=str))
        print(f"\n[ENUM-ONLY] saved enumeration to {PROGRESS_PATH}")
        return

    contexts_d, triggers_d = make_v8_detector_dicts(F)

    completed = set(progress.get("completed", []))
    results = list(progress.get("results", []))
    started_at = time.time()
    last_save = started_at
    n_done_now = 0

    print(f"\n[4/4] Mining {len(strats)} strategies ...")
    for idx, strat in enumerate(strats):
        if strat.name in completed:
            continue
        try:
            trades = label_strategy(F, nq_5m, nq_1m, daily, strat,
                                      contexts_d, triggers_d)
            ev = evaluate_strategy(trades, TRAIN_END)
            ev["name"] = strat.name
            ev["side"] = strat.side
            ev["contexts"] = strat.contexts
            ev["trigger"] = strat.trigger
            ev["stop_atr"] = strat.stop_atr
            ev["target_atr"] = strat.target_atr
            ev["max_hold_min"] = strat.max_hold_min
            # User-defined pass: WR>=55%, RR>=3, n>=100
            t = ev.get("test", {})
            ev["user_pass"] = (
                t.get("wr", 0) >= USER_MIN_WR
                and (strat.target_atr / strat.stop_atr) >= USER_MIN_RR
                and t.get("n", 0) >= USER_MIN_TRADES
            )
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            if ev.get("user_pass"):
                logger.info(
                    f"  [USER-PASS] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} pnl=${t['net']:+,.0f}"
                )
            elif ev.get("passes_all"):
                logger.info(f"  [STRICT-PASS] {strat.name}")
            elif (idx % 25) == 0:
                rate = (idx + 1 - len(progress.get('completed', []))) / max(0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                u_pass = sum(1 for r in results if r.get('user_pass'))
                logger.info(
                    f"  [{idx+1:>4}/{len(strats)}] {strat.name[:55]:<55}  "
                    f"n={t.get('n',0):>3}  WR={t.get('wr',0)*100:.1f}%  "
                    f"user_pass_total={u_pass}  ETA {eta:.0f}m"
                )

            now = time.time()
            if n_done_now >= 10 or (now - last_save) > 60:
                progress["completed"] = sorted(completed)
                progress["results"] = results
                PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))
                last_save = now
                n_done_now = 0
        except Exception as e:
            logger.exception(f"strategy {strat.name} crashed: {e}")
            results.append({"name": strat.name, "error": str(e),
                              "passes_all": False, "user_pass": False})
            completed.add(strat.name)

    progress["completed"] = sorted(completed)
    progress["results"] = results
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))

    user_passers = [r for r in results if r.get("user_pass")]
    strict_passers = [r for r in results if r.get("passes_all")]
    print(f"\n[DONE] runtime: {(time.time()-started_at)/60:.1f}m")
    print(f"  total tested: {len(results)}")
    print(f"  USER-PASS (WR>=55, RR>=3, n>=100): {len(user_passers)}")
    print(f"  STRICT-PASS (5 tests + permutation): {len(strict_passers)}")

    if user_passers:
        user_passers.sort(key=lambda r: -r["test"]["net"])
        print(f"\n  Top USER-PASS by OOS net pnl:")
        for r in user_passers[:30]:
            t = r["test"]
            print(f"    {r['name'][:55]:<55}  n={t['n']:>4}  "
                  f"WR={t['wr']*100:.1f}%  PF={t['pf']:.2f}  "
                  f"$/contract={t['net']:+,.0f}")

    OUT_PATH.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "n_strategies": len(results),
        "n_user_pass": len(user_passers),
        "n_strict_pass": len(strict_passers),
        "user_passers": user_passers,
        "strict_passers": strict_passers,
        "all_results": results,
    }, indent=2, default=str))
    print(f"\nWrote {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    enum_only = "--enumerate-only" in sys.argv
    try:
        main(enumerate_only=enum_only)
    except Exception as e:
        logger.exception(f"main() crashed: {e}")
        raise

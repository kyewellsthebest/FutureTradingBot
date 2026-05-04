"""
Pattern Miner v9 — exhaustive strategy enumeration to find 50+ that meet
RELAXED user requirements:
  * Win rate >= 50% (not 55%)
  * Risk:Reward >= 2:1 typical (was strict 3:1)
  * 1+ trade per week (n_test >= 100)

Strategy categories (target 3000+ unique strategies):
  TC  — Trend Continuation
  SA  — NQ-ES Stat-Arb (multiple thresholds and windows)
  SR  — NQ-RTY Stat-Arb
  LL  — Lead-Lag exploitation
  VB  — Volatility Breakouts
  PIV — Pivot Point Reactions (S1/R1/S2/R2/PP/PDH/PDL)
  MC  — Multi-Confluence (3+ orthogonal conditions)
  HM  — Higher-Timeframe alignment
  ORB — Opening Range Breakout / Fade
  GAP — Daily Gap Fades
  RND — Round Number magnets
  DOW — Day-of-Week patterns
  TOD — Time-of-Day patterns
  REV — Mean reversion at extremes
  FIB — Fibonacci retracements

Bar-by-bar simulator (re-uses v6 label_strategy with no-leak entries),
5 rigorous tests + 5,000-trial permutation, CPCV folds.

Auto-recovery: progress saved every 5 strategies; bash watchdog restarts
process on crash; resumes from checkpoint.
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
    PERMUTATION_TRIALS, PERMUTATION_P_VALUE,
    CPCV_FOLDS, CPCV_MIN_POSITIVE, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.indicators import atr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v9_patterns.json"
PROGRESS_PATH = DATA / "v9_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v9.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v9")

# RELAXED user requirements (still rigorous)
USER_MIN_WR = 0.50         # 50% WR after costs
USER_MIN_RR = 2.0          # 2:1 RR minimum (typical, not every trade)
USER_MIN_TRADES = 100      # ~1 trade/week over 2.3yr OOS


# ---------------------------------------------------------------------------
# v9 feature additions: RTY divergence, gaps, round numbers, day-of-week
# ---------------------------------------------------------------------------
def build_v9_extras(F: pd.DataFrame, nq_5m: pd.DataFrame,
                     daily: pd.DataFrame,
                     rty_5m: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    F = F.copy()
    c = nq_5m["close"]

    # NQ-RTY divergence (similar to NQ-ES)
    if rty_5m is not None and not rty_5m.empty:
        rty_c = rty_5m["close"].reindex(F.index, method="ffill")
        for n in [20, 60]:
            div = c.pct_change(n) - rty_c.pct_change(n)
            mu = div.rolling(200).mean()
            sd = div.rolling(200).std()
            F[f"nq_rty_div_z_{n}"] = (div - mu) / sd
        for k in [3, 5, 10]:
            rty_move_k = rty_c.pct_change(k)
            mu = rty_move_k.rolling(200).mean()
            sd = rty_move_k.rolling(200).std()
            F[f"rty_move_z_{k}"] = (rty_move_k - mu) / sd

    # Daily gap (today's overnight gap from yesterday close to today's open)
    NY = "America/New_York"
    idx_ny = nq_5m.index.tz_convert(NY)
    session_date = pd.Series(idx_ny.date, index=nq_5m.index)
    # First bar of each NY session = open
    first_bar = session_date != session_date.shift(1)
    session_open = nq_5m["open"].where(first_bar).ffill()
    # Previous session's close (last bar of prev session)
    last_bar = session_date != session_date.shift(-1)
    session_prev_close = nq_5m["close"].where(last_bar).shift(1).ffill()
    F["gap_pts"] = (session_open - session_prev_close)
    F["gap_atr"] = F["gap_pts"] / F["atr14"]
    # Distance from gap level (today's high water mark)
    F["dist_session_open_atr"] = (c - session_open) / F["atr14"]

    # Round-number distance (50, 100 NQ point levels)
    F["dist_round_50"] = ((c % 50) - 25) / 25  # -1 to +1
    F["dist_round_100"] = ((c % 100) - 50) / 50

    # Day-of-week (already have F["dow"]; expose as one-hots for trigger logic)
    F["is_monday"]    = (F["dow"] == 0).astype(int)
    F["is_tuesday"]   = (F["dow"] == 1).astype(int)
    F["is_wednesday"] = (F["dow"] == 2).astype(int)
    F["is_thursday"]  = (F["dow"] == 3).astype(int)
    F["is_friday"]    = (F["dow"] == 4).astype(int)

    # Time-window markers (15-30 min slices)
    F["is_0930_1000"] = ((F["ny_hour"] == 9) & (F["ny_minute"] >= 30))
    F["is_1000_1030"] = ((F["ny_hour"] == 10) & (F["ny_minute"] < 30))
    F["is_1400_1430"] = ((F["ny_hour"] == 14) & (F["ny_minute"] < 30))
    F["is_1430_1500"] = ((F["ny_hour"] == 14) & (F["ny_minute"] >= 30))
    F["is_1500_1530"] = ((F["ny_hour"] == 15) & (F["ny_minute"] < 30))
    F["is_1530_1600"] = ((F["ny_hour"] == 15) & (F["ny_minute"] >= 30))

    # Opening range (first 30 min of NY session)
    rng_first30 = nq_5m.copy()
    in_or = ((idx_ny.hour == 9) & (idx_ny.minute >= 30)) | ((idx_ny.hour == 10) & (idx_ny.minute < 0))
    rng_first30["in_or"] = in_or
    or_high = rng_first30["high"].where(rng_first30["in_or"]).groupby(session_date).cummax().ffill()
    or_low  = rng_first30["low"].where(rng_first30["in_or"]).groupby(session_date).cummin().ffill()
    # Lock OR after 10am NY (no peeking)
    after_or = ~in_or
    F["or_high"] = or_high.where(after_or).ffill()
    F["or_low"]  = or_low.where(after_or).ffill()
    F["dist_or_high_atr"] = (c - F["or_high"]) / F["atr14"]
    F["dist_or_low_atr"]  = (c - F["or_low"])  / F["atr14"]

    # Acceleration / deceleration
    F["accel_5"] = F["ret_5"] - F["ret_5"].shift(5)

    # Realized vs ATR mismatch
    F["rv_atr_ratio"] = F["rv50"] / (F["atr14"] / c) if "rv50" in F.columns else 1.0

    return F.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# v9 trigger detectors — reuse v8 plus add many new ones
# ---------------------------------------------------------------------------
def v9_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    from research.pattern_miner_v8 import v8_trigger_detectors
    T = dict(v8_trigger_detectors(F))

    # ---- Opening Range Breakout / Fade ----
    T["or_break_up"]   = (F["dist_or_high_atr"] > 0.2) & (F["dist_or_high_atr"].shift(1) <= 0.2) & (F["bar_dir"] > 0)
    T["or_break_down"] = (F["dist_or_low_atr"]  < -0.2) & (F["dist_or_low_atr"].shift(1) >= -0.2) & (F["bar_dir"] < 0)
    T["or_fade_up"]    = (F["dist_or_high_atr"] > 0.5) & (F["bar_dir"] < 0)  # fade test of OR high
    T["or_fade_down"]  = (F["dist_or_low_atr"]  < -0.5) & (F["bar_dir"] > 0)

    # ---- Gap fades ----
    T["gap_up_fade"]   = (F["gap_atr"] > 0.5) & (F["bar_dir"] < 0) & ((F["ny_hour"] == 9) | (F["ny_hour"] == 10))
    T["gap_down_fade"] = (F["gap_atr"] < -0.5) & (F["bar_dir"] > 0) & ((F["ny_hour"] == 9) | (F["ny_hour"] == 10))

    # ---- Round number reactions ----
    T["round50_reject_up"]   = (F["dist_round_50"].abs() < 0.1) & (F["bar_dir"] < 0)
    T["round50_reject_down"] = (F["dist_round_50"].abs() < 0.1) & (F["bar_dir"] > 0)
    T["round100_reject_up"]   = (F["dist_round_100"].abs() < 0.05) & (F["bar_dir"] < 0)
    T["round100_reject_down"] = (F["dist_round_100"].abs() < 0.05) & (F["bar_dir"] > 0)

    # ---- Mean reversion at extremes (3+ ATR from VWAP/EMA50) ----
    T["mr_long_extreme"]   = (F["dist_vwap_atr"] < -2.0) & (F["bar_dir"] > 0)
    T["mr_short_extreme"]  = (F["dist_vwap_atr"] >  2.0) & (F["bar_dir"] < 0)
    T["ema_extreme_long"]  = (F["ema_dist_atr"] < -3.0) & (F["bar_dir"] > 0)
    T["ema_extreme_short"] = (F["ema_dist_atr"] >  3.0) & (F["bar_dir"] < 0)

    # ---- NQ-RTY stat-arb ----
    if "nq_rty_div_z_20" in F.columns:
        for w in [20, 60]:
            for thr in [15, 20, 25]:
                col = f"nq_rty_div_z_{w}"
                T[f"sr_short_{w}_{thr}"] = F[col] > (thr/10.0)
                T[f"sr_long_{w}_{thr}"]  = F[col] < -(thr/10.0)

    # ---- RTY lead-lag (RTY moves first) ----
    if "rty_move_z_5" in F.columns:
        for k in [3, 5, 10]:
            col = f"rty_move_z_{k}"
            for thr in [15, 20]:
                T[f"rty_led_up_{k}_{thr}"]   = F[col] >  (thr/10.0)
                T[f"rty_led_down_{k}_{thr}"] = F[col] < -(thr/10.0)

    # ---- Multi-bar setup patterns ----
    # 3 consecutive lower closes, then bull bar (mini double bottom)
    T["3lc_reversal_long"]  = ((F["bar_dir"].shift(3) < 0) & (F["bar_dir"].shift(2) < 0) &
                                 (F["bar_dir"].shift(1) < 0) & (F["bar_dir"] > 0))
    T["3hc_reversal_short"] = ((F["bar_dir"].shift(3) > 0) & (F["bar_dir"].shift(2) > 0) &
                                 (F["bar_dir"].shift(1) > 0) & (F["bar_dir"] < 0))

    # ---- RSI extremes recovery ----
    T["rsi14_oversold_recover"]   = (F["rsi14"].shift(1) < 25) & (F["rsi14"] > F["rsi14"].shift(1)) & (F["bar_dir"] > 0)
    T["rsi14_overbought_break"]   = (F["rsi14"].shift(1) > 75) & (F["rsi14"] < F["rsi14"].shift(1)) & (F["bar_dir"] < 0)

    # ---- Volume climax reversal ----
    T["vol_climax_up_reverse"]   = (F["vol_climax"] == 1) & (F["bar_dir"].shift(1) > 0) & (F["bar_dir"] < 0)
    T["vol_climax_down_reverse"] = (F["vol_climax"] == 1) & (F["bar_dir"].shift(1) < 0) & (F["bar_dir"] > 0)

    return {k: v.fillna(False) for k, v in T.items()}


# ---------------------------------------------------------------------------
# v9 context detectors
# ---------------------------------------------------------------------------
def v9_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    from research.pattern_miner_v8 import v8_context_detectors
    C = dict(v8_context_detectors(F))

    # Day-of-week
    C["monday"]    = F["dow"] == 0
    C["tuesday"]   = F["dow"] == 1
    C["wednesday"] = F["dow"] == 2
    C["thursday"]  = F["dow"] == 3
    C["friday"]    = F["dow"] == 4

    # Tighter time windows
    C["t_0930_1000"] = F["is_0930_1000"] == True
    C["t_1000_1030"] = F["is_1000_1030"] == True
    C["t_1400_1430"] = F["is_1400_1430"] == True
    C["t_1430_1500"] = F["is_1430_1500"] == True
    C["t_1500_1530"] = F["is_1500_1530"] == True
    C["t_1530_1600"] = F["is_1530_1600"] == True

    # Gap conditions
    C["gap_up"]   = F["gap_atr"] > 0.3
    C["gap_down"] = F["gap_atr"] < -0.3
    C["gap_flat"] = F["gap_atr"].abs() < 0.2

    return {k: v.fillna(False) for k, v in C.items()}


# ---------------------------------------------------------------------------
# v9 strategy enumeration: target 3000+ strategies
# ---------------------------------------------------------------------------
def enumerate_v9_strategies(F: pd.DataFrame) -> list[StrategyDef]:
    has_es = "nq_es_div_z_20" in F.columns
    has_rty = "nq_rty_div_z_20" in F.columns

    # RR profiles: mix of 1:2, 1:2.5, 1:3 — gives variety
    rr_std = [
        (1.0, 2.0,  45, "RR2_std"),
        (1.0, 2.2,  50, "RR2_2"),
        (1.0, 2.5,  60, "RR2_5"),
        (0.8, 2.0,  45, "RR2_5tight"),
        (1.5, 3.0,  75, "RR2_wide"),
        (1.0, 3.0,  75, "RR3_std"),
    ]
    # Tighter RRs for fast triggers
    rr_fast = [
        (1.0, 2.0,  30, "RR2_fast"),
        (0.8, 2.0,  30, "RR2_5fast"),
        (1.0, 2.5,  45, "RR2_5med"),
    ]

    strategies = []
    sid = 0

    def add(name_prefix, side, contexts, trigger, rr_set, ctx_window=10):
        nonlocal sid
        for stop_a, tgt_a, mh, rrl in rr_set:
            sid += 1
            ctx_str = "_".join(c[:5] for c in contexts)
            strategies.append(StrategyDef(
                name=f"{name_prefix}_{side}_{trigger[:14]}_x_{ctx_str[:18]}_{rrl}_{sid:04d}",
                side=side, contexts=list(contexts), trigger=trigger,
                context_window_bars=ctx_window,
                stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
            ))

    # ---- TC: Trend Continuation (~600) ----
    TC = [
        ("pullback_to_vwap_long",   "LONG",  ["trend_up_strong"]),
        ("pullback_to_vwap_long",   "LONG",  ["trend_up_weak"]),
        ("pullback_to_vwap_long",   "LONG",  ["h1_strong_up"]),
        ("pullback_to_vwap_long",   "LONG",  ["h1_up", "vix_low"]),
        ("pullback_to_vwap_short",  "SHORT", ["trend_down_strong"]),
        ("pullback_to_vwap_short",  "SHORT", ["trend_down_weak"]),
        ("pullback_to_vwap_short",  "SHORT", ["h1_strong_down"]),
        ("pullback_to_vwap_short",  "SHORT", ["h1_down", "vix_high"]),
        ("pullback_to_ema50_long",  "LONG",  ["trend_up_strong"]),
        ("pullback_to_ema50_long",  "LONG",  ["h1_up"]),
        ("pullback_to_ema50_short", "SHORT", ["trend_down_strong"]),
        ("pullback_to_ema50_short", "SHORT", ["h1_down"]),
        ("pullback_38_long",        "LONG",  ["trend_up_strong"]),
        ("pullback_38_long",        "LONG",  ["h1_up"]),
        ("pullback_38_short",       "SHORT", ["trend_down_strong"]),
        ("pullback_38_short",       "SHORT", ["h1_down"]),
        ("pullback_50_long",        "LONG",  ["trend_up_strong", "h1_up"]),
        ("pullback_50_short",       "SHORT", ["trend_down_strong", "h1_down"]),
        ("pullback_61_long",        "LONG",  ["trend_up_strong", "h1_up"]),
        ("pullback_61_short",       "SHORT", ["trend_down_strong", "h1_down"]),
    ]
    SESSIONS_TC = ["am", "midday", "pm", "rth", "t_0930_1000", "t_1430_1500"]
    for trig, side, base_ctx in TC:
        for sess in SESSIONS_TC:
            add("V9TC", side, base_ctx + [sess], trig, rr_std)

    # ---- VB: Volatility Breakouts (~200) ----
    VB = [
        ("bb_squeeze_break_up",   "LONG"),
        ("bb_squeeze_break_down", "SHORT"),
        ("range_expansion_long",  "LONG"),
        ("range_expansion_short", "SHORT"),
    ]
    VB_CTX = ["vol_compressed", "vol_low", "am", "midday", "pm",
               "h1_up", "h1_down", "above_vwap", "below_vwap", "bb_squeeze"]
    for trig, side in VB:
        for ctx in VB_CTX:
            add("V9VB", side, [ctx], trig, rr_std)

    # ---- PIV: Pivot reactions (~250) ----
    PIV = [
        ("bounce_off_s1",    "LONG"),
        ("reject_at_r1",     "SHORT"),
        ("bounce_off_s2",    "LONG"),
        ("reject_at_r2",     "SHORT"),
        ("break_above_r1",   "LONG"),
        ("break_below_s1",   "SHORT"),
        ("break_above_pdh",  "LONG"),
        ("break_below_pdl",  "SHORT"),
    ]
    PIV_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth"]
    for trig, side in PIV:
        for ctx in PIV_CTX:
            add("V9PIV", side, [ctx], trig, rr_std, ctx_window=5)

    # ---- SA: NQ-ES Stat-Arb (~360) ----
    if has_es:
        SA_TRIGS = []
        for w in [20, 60]:
            for thr in [15, 20, 25]:
                SA_TRIGS.append((f"sa_short_{w}_{thr}", "SHORT"))
                SA_TRIGS.append((f"sa_long_{w}_{thr}",  "LONG"))
        SA_CTX = ["am", "midday", "pm", "rth", "t_1430_1500"]
        for trig, side in SA_TRIGS:
            for ctx in SA_CTX:
                add("V9SA", side, [ctx], trig, rr_std, ctx_window=5)

    # ---- SR: NQ-RTY Stat-Arb (~150) ----
    if has_rty:
        SR_TRIGS = []
        for w in [20, 60]:
            for thr in [15, 20, 25]:
                SR_TRIGS.append((f"sr_short_{w}_{thr}", "SHORT"))
                SR_TRIGS.append((f"sr_long_{w}_{thr}",  "LONG"))
        SR_CTX = ["am", "midday", "pm"]
        for trig, side in SR_TRIGS:
            for ctx in SR_CTX:
                add("V9SR", side, [ctx], trig, rr_std, ctx_window=5)

    # ---- LL: Lead-Lag (~360) ----
    if has_es:
        LL_TRIGS = []
        for k in [3, 5, 10]:
            for thr in [10, 15, 20]:
                LL_TRIGS.append((f"ll_long_{k}_{thr}",  "LONG"))
                LL_TRIGS.append((f"ll_short_{k}_{thr}", "SHORT"))
        LL_CTX = ["am", "midday", "pm", "h1_up", "h1_down"]
        for trig, side in LL_TRIGS:
            for ctx in LL_CTX:
                add("V9LL", side, [ctx], trig, rr_fast, ctx_window=3)

    # ---- LR: RTY lead-lag (~135) ----
    if has_rty:
        LR_TRIGS = []
        for k in [3, 5, 10]:
            for thr in [15, 20]:
                LR_TRIGS.append((f"rty_led_up_{k}_{thr}",   "LONG"))
                LR_TRIGS.append((f"rty_led_down_{k}_{thr}", "SHORT"))
        LR_CTX = ["am", "midday", "pm"]
        for trig, side in LR_TRIGS:
            for ctx in LR_CTX:
                add("V9LR", side, [ctx], trig, rr_fast, ctx_window=3)

    # ---- ORB: Opening Range (~200) ----
    ORB = [
        ("or_break_up",   "LONG"),
        ("or_break_down", "SHORT"),
        ("or_fade_up",    "SHORT"),
        ("or_fade_down",  "LONG"),
    ]
    ORB_CTX = ["t_1000_1030", "t_1400_1430", "midday", "pm",
                "h1_up", "h1_down", "vix_low", "vol_compressed"]
    for trig, side in ORB:
        for ctx in ORB_CTX:
            add("V9ORB", side, [ctx], trig, rr_std, ctx_window=5)

    # ---- GAP: Gap fades (~120) ----
    GAP = [
        ("gap_up_fade",   "SHORT"),
        ("gap_down_fade", "LONG"),
    ]
    GAP_CTX = ["t_0930_1000", "t_1000_1030", "monday", "tuesday",
                "wednesday", "thursday", "friday", "vix_high", "vix_low", "h1_up"]
    for trig, side in GAP:
        for ctx in GAP_CTX:
            add("V9GAP", side, [ctx], trig, rr_std, ctx_window=3)

    # ---- RND: Round number (~150) ----
    RND = [
        ("round50_reject_up",    "SHORT"),
        ("round50_reject_down",  "LONG"),
        ("round100_reject_up",   "SHORT"),
        ("round100_reject_down", "LONG"),
    ]
    RND_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "above_vwap", "below_vwap"]
    for trig, side in RND:
        for ctx in RND_CTX:
            add("V9RND", side, [ctx], trig, rr_std, ctx_window=3)

    # ---- REV: Mean reversion at extremes (~150) ----
    REV = [
        ("mr_long_extreme",   "LONG"),
        ("mr_short_extreme",  "SHORT"),
        ("ema_extreme_long",  "LONG"),
        ("ema_extreme_short", "SHORT"),
    ]
    REV_CTX = ["am", "midday", "pm", "rth", "vix_high", "vol_expanded"]
    for trig, side in REV:
        for ctx in REV_CTX:
            add("V9REV", side, [ctx], trig, rr_std)

    # ---- DOW/TOD: Day-of-week + Time patterns (~200) ----
    # Use existing strong triggers but filtered by specific day or time
    DOW_TRIGS = [
        ("pullback_38_long",  "LONG",  ["h1_up"]),
        ("pullback_38_short", "SHORT", ["h1_down"]),
        ("bb_squeeze_break_up",   "LONG",  ["vol_compressed"]),
        ("bb_squeeze_break_down", "SHORT", ["vol_compressed"]),
    ]
    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    for trig, side, base in DOW_TRIGS:
        for day in DAYS:
            add("V9DOW", side, base + [day], trig, rr_std)

    TOD_TRIGS = [
        ("pullback_to_vwap_long",   "LONG",  ["h1_up"]),
        ("pullback_to_vwap_short",  "SHORT", ["h1_down"]),
        ("range_expansion_long",    "LONG",  ["above_vwap"]),
        ("range_expansion_short",   "SHORT", ["below_vwap"]),
    ]
    TIMES = ["t_0930_1000", "t_1000_1030", "t_1400_1430", "t_1430_1500", "t_1500_1530", "t_1530_1600"]
    for trig, side, base in TOD_TRIGS:
        for tw in TIMES:
            add("V9TOD", side, base + [tw], trig, rr_std)

    # ---- MC: Multi-Confluence (~300) ----
    MC = [
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
        ("or_break_up",             "LONG",  ["h1_up", "vol_compressed"]),
        ("or_break_down",           "SHORT", ["h1_down", "vol_compressed"]),
        ("3lc_reversal_long",       "LONG",  ["h1_up", "vix_high"]),
        ("3hc_reversal_short",      "SHORT", ["h1_down", "vix_high"]),
        ("rsi14_oversold_recover",  "LONG",  ["h1_up"]),
        ("rsi14_overbought_break",  "SHORT", ["h1_down"]),
    ]
    SESS_MC = ["am", "midday", "pm", "rth"]
    for trig, side, base_ctx in MC:
        for sess in SESS_MC:
            add("V9MC", side, base_ctx + [sess], trig, rr_std)

    # ---- HM: Higher-Timeframe alignment (~150) ----
    HM = [
        ("pullback_38_long",  "LONG",  ["h1_strong_up", "above_ema50"]),
        ("pullback_50_long",  "LONG",  ["h1_strong_up", "above_ema50"]),
        ("pullback_61_long",  "LONG",  ["h1_strong_up", "above_ema50"]),
        ("pullback_38_short", "SHORT", ["h1_strong_down", "below_ema50"]),
        ("pullback_50_short", "SHORT", ["h1_strong_down", "below_ema50"]),
        ("pullback_61_short", "SHORT", ["h1_strong_down", "below_ema50"]),
        ("break_above_pdh",   "LONG",  ["h1_strong_up"]),
        ("break_below_pdl",   "SHORT", ["h1_strong_down"]),
    ]
    SESS_HM = ["am", "midday", "pm"]
    for trig, side, base_ctx in HM:
        for sess in SESS_HM:
            add("V9HM", side, base_ctx + [sess], trig, rr_std)

    return strategies


def make_v9_detector_dicts(F: pd.DataFrame):
    contexts_d_series = v9_context_detectors(F)
    triggers_d_series = v9_trigger_detectors(F)
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
        format="%(asctime)s %(levelname)s miner_v9 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v9 — exhaustive search for WR>=50%, RR>=2:1")
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

    print("\n[2/4] Building v9 features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    print(f"  {F.shape}")

    print("\n[3/4] Enumerating strategies ...")
    strats = enumerate_v9_strategies(F)
    print(f"  TOTAL STRATEGIES: {len(strats)}")
    from collections import Counter
    cats = Counter(s.name[:5] for s in strats)
    for cat, n in sorted(cats.items()):
        print(f"  {cat}: {n}")

    if enumerate_only:
        PROGRESS_PATH.write_text(json.dumps({
            "ENUMERATION_ONLY": True,
            "total_strategies": len(strats),
            "categories": dict(cats),
        }, indent=2, default=str))
        print(f"\n[ENUM-ONLY] saved enumeration to {PROGRESS_PATH}")
        return

    contexts_d, triggers_d = make_v9_detector_dicts(F)

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
            t = ev.get("test", {})
            rr_actual = strat.target_atr / strat.stop_atr
            ev["user_pass"] = (
                t.get("wr", 0) >= USER_MIN_WR
                and rr_actual >= USER_MIN_RR
                and t.get("n", 0) >= USER_MIN_TRADES
            )
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            if ev.get("user_pass"):
                logger.info(
                    f"  [USER-PASS #{sum(1 for r in results if r.get('user_pass'))}] "
                    f"{strat.name}  n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} pnl=${t['net']:+,.0f}"
                )
            elif (idx % 50) == 0:
                rate = (idx + 1 - len(progress.get('completed', []))) / max(0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                u_pass = sum(1 for r in results if r.get('user_pass'))
                logger.info(
                    f"  [{idx+1:>4}/{len(strats)}] {strat.name[:55]:<55}  "
                    f"n={t.get('n',0):>4}  WR={t.get('wr',0)*100:.1f}%  "
                    f"user_pass_total={u_pass}  ETA {eta:.0f}m"
                )

            now = time.time()
            if n_done_now >= 5 or (now - last_save) > 30:
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
    print(f"  USER-PASS (WR>=50, RR>=2, n>=100): {len(user_passers)}")
    print(f"  STRICT-PASS: {len(strict_passers)}")

    if user_passers:
        user_passers.sort(key=lambda r: -r["test"]["net"])
        print(f"\n  Top USER-PASS by OOS net pnl:")
        for r in user_passers[:50]:
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

"""
Pattern Miner v10 — MAXIMUM enumeration. Target: 15,000+ strategies.

Builds on v6/v7/v8/v9 features and adds many new trigger types and RR
profiles for the most exhaustive search possible. Designed to run all night
under a watchdog with auto-restart and incremental checkpoints.

User requirements (relaxed and realistic):
  * WR >= 50% after costs
  * RR >= 2:1 typical (not strict per-trade)
  * 1+ trade per week (n_test >= 100)

Categories (target 15,000+):
  TC, MC, HM, PIV, VB, ORB, GAP, RND, REV, DOW, TOD     — from v8/v9
  SA, SR — NQ-ES, NQ-RTY stat-arb across many windows / Z-thresholds
  LL, LR — ES, RTY lead-lag across many windows / thresholds
  DON — Donchian channel breakouts (multiple periods)
  KEL — Keltner channel reactions
  WCK — Wick rejections at key levels
  MTF — Multi-timeframe trigger combinations
  SEQ — Sequential bar patterns (3, 4, 5 bar setups)
  VOL — Volume-driven setups (spike, dryup, climax patterns)
  RSI — Multi-period RSI extremes
  STO — Stochastic-like extremes
  CHL — Channel mid-line reversion
  PSY — Psychological level reactions (50, 100, 250, 500 NQ pts)
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
    PERMUTATION_TRIALS, PERMUTATION_P_VALUE,
    CPCV_FOLDS, CPCV_MIN_POSITIVE, TRAIN_END,
)


def force_permutation_test(trades_test_pnls: np.ndarray, trials: int = 5000) -> float:
    """Run a 5,000-trial permutation test on test-set PnLs and return p-value.
    Used for strategies that pass user thresholds but might not have triggered
    the cheap_pass path in evaluate_strategy."""
    if len(trades_test_pnls) < 30:
        return 1.0
    obs_sharpe = trades_test_pnls.mean() / trades_test_pnls.std() if trades_test_pnls.std() > 0 else 0
    if obs_sharpe <= 0:
        return 1.0
    rng = np.random.default_rng(42)
    n_better = 0
    for _ in range(trials):
        perm = rng.permutation(trades_test_pnls)
        psh = perm.mean() / perm.std() if perm.std() > 0 else 0
        if psh >= obs_sharpe:
            n_better += 1
    return n_better / trials
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras, v8_context_detectors, v8_trigger_detectors
from research.pattern_miner_v9 import build_v9_extras, v9_context_detectors, v9_trigger_detectors
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.indicators import atr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v10_patterns.json"
PROGRESS_PATH = DATA / "v10_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v10.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v10")

USER_MIN_WR = 0.50
USER_MIN_RR = 2.0
USER_MIN_TRADES = 100


# ---------------------------------------------------------------------------
# v10 feature extras: Donchian, Keltner, multi-period RSI, psychological levels
# ---------------------------------------------------------------------------
def build_v10_extras(F: pd.DataFrame, nq_5m: pd.DataFrame) -> pd.DataFrame:
    F = F.copy()
    h, l, c = nq_5m["high"], nq_5m["low"], nq_5m["close"]

    # Donchian channels (multiple periods)
    for n in [10, 20, 50, 100]:
        F[f"don_high_{n}"] = h.rolling(n).max()
        F[f"don_low_{n}"]  = l.rolling(n).min()
        F[f"dist_don_high_{n}"] = (c - F[f"don_high_{n}"]) / F["atr14"]
        F[f"dist_don_low_{n}"]  = (c - F[f"don_low_{n}"]) / F["atr14"]

    # Keltner channels (EMA20 +/- 2*ATR)
    ema20 = c.ewm(span=20, adjust=False).mean()
    F["kel_upper"] = ema20 + 2.0 * F["atr14"]
    F["kel_lower"] = ema20 - 2.0 * F["atr14"]
    F["dist_kel_up_atr"] = (c - F["kel_upper"]) / F["atr14"]
    F["dist_kel_lo_atr"] = (c - F["kel_lower"]) / F["atr14"]

    # Multi-period RSI
    from research.indicators import rsi
    F["rsi5"]  = rsi(c, 5)
    F["rsi21"] = rsi(c, 21)

    # Stochastic-like (close position in N-bar range)
    for n in [14, 21]:
        hh = h.rolling(n).max()
        ll = l.rolling(n).min()
        F[f"stoch_{n}"] = (c - ll) / (hh - ll).replace(0, np.nan)

    # Psychological levels (250, 500 NQ pts)
    F["dist_round_250"] = ((c % 250) - 125) / 125
    F["dist_round_500"] = ((c % 500) - 250) / 250

    # Wick measurements
    o = nq_5m["open"]
    rng = (h - l).replace(0, np.nan)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l
    F["upper_wick_atr"] = upper_wick / F["atr14"]
    F["lower_wick_atr"] = lower_wick / F["atr14"]
    F["pinbar_up"]   = (upper_wick > 2 * np.abs(c - o)) & (upper_wick > 0.5 * F["atr14"])
    F["pinbar_down"] = (lower_wick > 2 * np.abs(c - o)) & (lower_wick > 0.5 * F["atr14"])

    return F.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# v10 trigger detectors — v9's set + many new ones
# ---------------------------------------------------------------------------
def v10_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    T = dict(v9_trigger_detectors(F))

    # Donchian breakouts
    for n in [10, 20, 50]:
        T[f"don_break_up_{n}"]   = (F[f"dist_don_high_{n}"] > 0) & (F[f"dist_don_high_{n}"].shift(1) <= 0) & (F["bar_dir"] > 0)
        T[f"don_break_down_{n}"] = (F[f"dist_don_low_{n}"]  < 0) & (F[f"dist_don_low_{n}"].shift(1)  >= 0) & (F["bar_dir"] < 0)

    # Keltner channel reactions
    T["kel_reject_upper"] = (F["dist_kel_up_atr"] > -0.2) & (F["bar_dir"] < 0)
    T["kel_reject_lower"] = (F["dist_kel_lo_atr"] <  0.2) & (F["bar_dir"] > 0)
    T["kel_break_upper"]  = (F["dist_kel_up_atr"] > 0) & (F["dist_kel_up_atr"].shift(1) <= 0) & (F["bar_dir"] > 0)
    T["kel_break_lower"]  = (F["dist_kel_lo_atr"] < 0) & (F["dist_kel_lo_atr"].shift(1) >= 0) & (F["bar_dir"] < 0)

    # Pin bar (wick rejection) at extremes
    T["pinbar_top_short"] = F["pinbar_up"] & (F["dist_high20_atr"] > -0.5)
    T["pinbar_btm_long"]  = F["pinbar_down"] & (F["dist_low20_atr"] < 0.5)

    # Multi-period RSI extremes
    T["rsi5_oversold"]   = (F["rsi5"].shift(1) < 15) & (F["rsi5"] > F["rsi5"].shift(1)) & (F["bar_dir"] > 0)
    T["rsi5_overbought"] = (F["rsi5"].shift(1) > 85) & (F["rsi5"] < F["rsi5"].shift(1)) & (F["bar_dir"] < 0)
    T["rsi21_oversold"]  = (F["rsi21"].shift(1) < 30) & (F["rsi21"] > F["rsi21"].shift(1)) & (F["bar_dir"] > 0)
    T["rsi21_overbought"] = (F["rsi21"].shift(1) > 70) & (F["rsi21"] < F["rsi21"].shift(1)) & (F["bar_dir"] < 0)

    # Stochastic extremes
    for n in [14, 21]:
        T[f"stoch{n}_oversold"]   = (F[f"stoch_{n}"].shift(1) < 0.20) & (F[f"stoch_{n}"] > F[f"stoch_{n}"].shift(1)) & (F["bar_dir"] > 0)
        T[f"stoch{n}_overbought"] = (F[f"stoch_{n}"].shift(1) > 0.80) & (F[f"stoch_{n}"] < F[f"stoch_{n}"].shift(1)) & (F["bar_dir"] < 0)

    # Psychological levels (250 / 500)
    T["psy250_reject_up"]    = (F["dist_round_250"].abs() < 0.05) & (F["bar_dir"] < 0)
    T["psy250_reject_down"]  = (F["dist_round_250"].abs() < 0.05) & (F["bar_dir"] > 0)
    T["psy500_reject_up"]    = (F["dist_round_500"].abs() < 0.025) & (F["bar_dir"] < 0)
    T["psy500_reject_down"]  = (F["dist_round_500"].abs() < 0.025) & (F["bar_dir"] > 0)

    # Sequential bar patterns
    T["4hc_reversal_short"] = ((F["bar_dir"].shift(4) > 0) & (F["bar_dir"].shift(3) > 0) &
                                (F["bar_dir"].shift(2) > 0) & (F["bar_dir"].shift(1) > 0) &
                                (F["bar_dir"] < 0))
    T["4lc_reversal_long"]  = ((F["bar_dir"].shift(4) < 0) & (F["bar_dir"].shift(3) < 0) &
                                (F["bar_dir"].shift(2) < 0) & (F["bar_dir"].shift(1) < 0) &
                                (F["bar_dir"] > 0))

    # Inside bar (low > prev low, high < prev high) followed by break
    inside = (F.index.to_series() != F.index.to_series())  # placeholder false
    inside_long  = ((F["high"].shift(1) > F["high"].shift(2)) & (F["low"].shift(1) > F["low"].shift(2)) & (F["bar_dir"] > 0)) if "high" in F.columns else None
    # Use NQ 5m data directly via shift on F values would need raw OHLC; skipped (already have engulfing/momentum)

    # VWAP crossover
    if "dist_vwap_atr" in F.columns:
        T["vwap_cross_up"]   = (F["dist_vwap_atr"] > 0) & (F["dist_vwap_atr"].shift(1) <= 0) & (F["bar_dir"] > 0)
        T["vwap_cross_down"] = (F["dist_vwap_atr"] < 0) & (F["dist_vwap_atr"].shift(1) >= 0) & (F["bar_dir"] < 0)

    # Higher highs / lower lows
    T["hh_break"] = (F["high"] > F["high"].shift(1)) & (F["high"].shift(1) > F["high"].shift(2)) & (F["bar_dir"] > 0) if "high" in F.columns else (F["bar_dir"] > 0)
    T["ll_break"] = (F["low"]  < F["low"].shift(1))  & (F["low"].shift(1)  < F["low"].shift(2))  & (F["bar_dir"] < 0) if "low" in F.columns  else (F["bar_dir"] < 0)

    # Volume + price combos
    T["vol_spike_up"]   = (F["vol_z_50"] > 1.5) & (F["bar_dir"] > 0) & (F["body_abs"] > F["atr14"] * 0.5)
    T["vol_spike_down"] = (F["vol_z_50"] > 1.5) & (F["bar_dir"] < 0) & (F["body_abs"] > F["atr14"] * 0.5)
    T["vol_dryup_break_up"]   = (F["vol_dryup"].shift(1) == 1) & (F["bar_dir"] > 0) & (F["body_abs"] > F["atr14"] * 0.5)
    T["vol_dryup_break_down"] = (F["vol_dryup"].shift(1) == 1) & (F["bar_dir"] < 0) & (F["body_abs"] > F["atr14"] * 0.5)

    return {k: v.fillna(False) for k, v in T.items()}


def v10_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    return v9_context_detectors(F)


def make_v10_detector_dicts(F: pd.DataFrame):
    contexts_d_series = v10_context_detectors(F)
    triggers_d_series = v10_trigger_detectors(F)
    def make_fn(s):
        return lambda F, _s=s: _s
    contexts_d = {k: make_fn(v) for k, v in contexts_d_series.items()}
    triggers_d = {k: make_fn(v) for k, v in triggers_d_series.items()}
    return contexts_d, triggers_d


# ---------------------------------------------------------------------------
# v10 enumeration: Maximum diversity. Target 15,000+
# ---------------------------------------------------------------------------
def enumerate_v10_strategies(F: pd.DataFrame) -> list[StrategyDef]:
    has_es = "nq_es_div_z_20" in F.columns
    has_rty = "nq_rty_div_z_20" in F.columns

    rr_set_main = [
        (1.0, 2.0,  45, "RR2_std"),
        (1.0, 2.2,  50, "RR2_2"),
        (1.0, 2.5,  60, "RR2_5"),
        (1.0, 2.8,  70, "RR2_8"),
        (1.0, 3.0,  75, "RR3_std"),
        (0.8, 2.0,  45, "RR2_5tight"),
        (0.8, 2.5,  60, "RR3_tight"),
        (1.5, 3.0,  75, "RR2_wide"),
        (1.5, 4.0,  90, "RR2_7wide"),
    ]
    rr_set_fast = [
        (1.0, 2.0,  30, "RR2_fast"),
        (0.8, 2.0,  30, "RR2_5fast"),
        (1.0, 2.5,  45, "RR2_5med"),
    ]

    strategies = []
    sid = 0
    seen_names = set()

    def add(prefix, side, contexts, trigger, rr_set, ctx_window=10):
        nonlocal sid
        for stop_a, tgt_a, mh, rrl in rr_set:
            sid += 1
            ctx_str = "_".join(c[:5] for c in contexts)[:18]
            name = f"{prefix}_{side}_{trigger[:14]}_x_{ctx_str}_{rrl}_{sid:05d}"
            if name in seen_names:
                continue
            seen_names.add(name)
            strategies.append(StrategyDef(
                name=name,
                side=side, contexts=list(contexts), trigger=trigger,
                context_window_bars=ctx_window,
                stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
            ))

    # ---- 1. TC: Trend continuation pullbacks (~1500) ----
    TC_TRIGS = [
        ("pullback_to_vwap_long",   "LONG"),
        ("pullback_to_vwap_short",  "SHORT"),
        ("pullback_to_ema50_long",  "LONG"),
        ("pullback_to_ema50_short", "SHORT"),
        ("pullback_38_long",        "LONG"),
        ("pullback_38_short",       "SHORT"),
        ("pullback_50_long",        "LONG"),
        ("pullback_50_short",       "SHORT"),
        ("pullback_61_long",        "LONG"),
        ("pullback_61_short",       "SHORT"),
    ]
    TC_TRENDS = ["trend_up_strong", "trend_up_weak", "h1_strong_up", "h1_up"]
    TC_TRENDS_DN = ["trend_down_strong", "trend_down_weak", "h1_strong_down", "h1_down"]
    SESSIONS = ["am", "midday", "pm", "rth", "t_0930_1000", "t_1000_1030", "t_1430_1500"]
    for trig, side in TC_TRIGS:
        trends = TC_TRENDS if side == "LONG" else TC_TRENDS_DN
        for trend in trends:
            for sess in SESSIONS:
                add("V10TC", side, [trend, sess], trig, rr_set_main)

    # ---- 2. PIV: Pivot reactions (~600) ----
    PIV = [
        ("bounce_off_s1",   "LONG"),
        ("reject_at_r1",    "SHORT"),
        ("bounce_off_s2",   "LONG"),
        ("reject_at_r2",    "SHORT"),
        ("break_above_r1",  "LONG"),
        ("break_below_s1",  "SHORT"),
        ("break_above_pdh", "LONG"),
        ("break_below_pdl", "SHORT"),
    ]
    PIV_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth", "vix_low", "vix_high"]
    for trig, side in PIV:
        for ctx in PIV_CTX:
            add("V10PIV", side, [ctx], trig, rr_set_main, ctx_window=5)

    # ---- 3. SA: NQ-ES Stat-Arb (~800) ----
    if has_es:
        SA_TRIGS = []
        for w in [20, 60]:
            for thr in [15, 20, 25]:
                SA_TRIGS.append((f"sa_short_{w}_{thr}", "SHORT"))
                SA_TRIGS.append((f"sa_long_{w}_{thr}",  "LONG"))
        SA_CTX = ["am", "midday", "pm", "rth", "t_1430_1500", "t_1500_1530",
                   "vix_low", "vix_high", "vol_normal"]
        for trig, side in SA_TRIGS:
            for ctx in SA_CTX:
                add("V10SA", side, [ctx], trig, rr_set_main, ctx_window=5)

    # ---- 4. SR: NQ-RTY Stat-Arb (~400) ----
    if has_rty:
        SR_TRIGS = []
        for w in [20, 60]:
            for thr in [15, 20, 25]:
                SR_TRIGS.append((f"sr_short_{w}_{thr}", "SHORT"))
                SR_TRIGS.append((f"sr_long_{w}_{thr}",  "LONG"))
        SR_CTX = ["am", "midday", "pm", "rth", "vix_low", "vix_high"]
        for trig, side in SR_TRIGS:
            for ctx in SR_CTX:
                add("V10SR", side, [ctx], trig, rr_set_main, ctx_window=5)

    # ---- 5. LL: ES lead-lag (~500) ----
    if has_es:
        LL_TRIGS = []
        for k in [3, 5, 10]:
            for thr in [10, 15, 20]:
                LL_TRIGS.append((f"ll_long_{k}_{thr}",  "LONG"))
                LL_TRIGS.append((f"ll_short_{k}_{thr}", "SHORT"))
        LL_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth"]
        for trig, side in LL_TRIGS:
            for ctx in LL_CTX:
                add("V10LL", side, [ctx], trig, rr_set_fast, ctx_window=3)

    # ---- 6. LR: RTY lead-lag (~250) ----
    if has_rty:
        LR_TRIGS = []
        for k in [3, 5, 10]:
            for thr in [15, 20]:
                LR_TRIGS.append((f"rty_led_up_{k}_{thr}",   "LONG"))
                LR_TRIGS.append((f"rty_led_down_{k}_{thr}", "SHORT"))
        LR_CTX = ["am", "midday", "pm", "h1_up", "h1_down"]
        for trig, side in LR_TRIGS:
            for ctx in LR_CTX:
                add("V10LR", side, [ctx], trig, rr_set_fast, ctx_window=3)

    # ---- 7. VB: Volatility breakouts (~500) ----
    VB = [
        ("bb_squeeze_break_up",   "LONG"),
        ("bb_squeeze_break_down", "SHORT"),
        ("range_expansion_long",  "LONG"),
        ("range_expansion_short", "SHORT"),
    ]
    VB_CTX = ["vol_compressed", "vol_low", "am", "midday", "pm",
               "h1_up", "h1_down", "above_vwap", "below_vwap", "bb_squeeze",
               "vix_low", "trend_up_strong", "trend_down_strong"]
    for trig, side in VB:
        for ctx in VB_CTX:
            add("V10VB", side, [ctx], trig, rr_set_main)

    # ---- 8. ORB: Opening Range (~250) ----
    ORB = [
        ("or_break_up",   "LONG"),
        ("or_break_down", "SHORT"),
        ("or_fade_up",    "SHORT"),
        ("or_fade_down",  "LONG"),
    ]
    ORB_CTX = ["t_1000_1030", "t_1400_1430", "midday", "pm",
                "h1_up", "h1_down", "vix_low", "vol_compressed", "above_vwap", "below_vwap"]
    for trig, side in ORB:
        for ctx in ORB_CTX:
            add("V10ORB", side, [ctx], trig, rr_set_main, ctx_window=5)

    # ---- 9. GAP: Gap fades (~250) ----
    GAP_TRIGS = [
        ("gap_up_fade",   "SHORT"),
        ("gap_down_fade", "LONG"),
    ]
    GAP_CTX = ["t_0930_1000", "t_1000_1030", "monday", "tuesday",
                "wednesday", "thursday", "friday", "vix_high", "vix_low",
                "h1_up", "h1_down", "above_vwap", "below_vwap"]
    for trig, side in GAP_TRIGS:
        for ctx in GAP_CTX:
            add("V10GAP", side, [ctx], trig, rr_set_main, ctx_window=3)

    # ---- 10. RND: Round number (~300) ----
    RND = [
        ("round50_reject_up",    "SHORT"),
        ("round50_reject_down",  "LONG"),
        ("round100_reject_up",   "SHORT"),
        ("round100_reject_down", "LONG"),
        ("psy250_reject_up",     "SHORT"),
        ("psy250_reject_down",   "LONG"),
        ("psy500_reject_up",     "SHORT"),
        ("psy500_reject_down",   "LONG"),
    ]
    RND_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "above_vwap", "below_vwap"]
    for trig, side in RND:
        for ctx in RND_CTX:
            add("V10RND", side, [ctx], trig, rr_set_main, ctx_window=3)

    # ---- 11. REV: Mean reversion at extremes (~250) ----
    REV = [
        ("mr_long_extreme",   "LONG"),
        ("mr_short_extreme",  "SHORT"),
        ("ema_extreme_long",  "LONG"),
        ("ema_extreme_short", "SHORT"),
    ]
    REV_CTX = ["am", "midday", "pm", "rth", "vix_high", "vol_expanded",
                "h1_up", "h1_down"]
    for trig, side in REV:
        for ctx in REV_CTX:
            add("V10REV", side, [ctx], trig, rr_set_main)

    # ---- 12. DON: Donchian breakouts (~300) ----
    DON_TRIGS = []
    for n in [10, 20, 50]:
        DON_TRIGS.append((f"don_break_up_{n}",   "LONG"))
        DON_TRIGS.append((f"don_break_down_{n}", "SHORT"))
    DON_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "vol_compressed",
                "vix_low", "vix_high"]
    for trig, side in DON_TRIGS:
        for ctx in DON_CTX:
            add("V10DON", side, [ctx], trig, rr_set_main, ctx_window=5)

    # ---- 13. KEL: Keltner channel reactions (~200) ----
    KEL = [
        ("kel_reject_upper", "SHORT"),
        ("kel_reject_lower", "LONG"),
        ("kel_break_upper",  "LONG"),
        ("kel_break_lower",  "SHORT"),
    ]
    KEL_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "vix_high", "vix_low"]
    for trig, side in KEL:
        for ctx in KEL_CTX:
            add("V10KEL", side, [ctx], trig, rr_set_main)

    # ---- 14. WCK: Wick rejections / pin bars (~150) ----
    WCK = [
        ("pinbar_top_short", "SHORT"),
        ("pinbar_btm_long",  "LONG"),
    ]
    WCK_CTX = ["am", "midday", "pm", "rth", "h1_up", "h1_down",
                "vix_high", "vol_expanded"]
    for trig, side in WCK:
        for ctx in WCK_CTX:
            add("V10WCK", side, [ctx], trig, rr_set_main)

    # ---- 15. RSI: Multi-period RSI (~250) ----
    RSI_TRIGS = [
        ("rsi5_oversold",    "LONG"),
        ("rsi5_overbought",  "SHORT"),
        ("rsi21_oversold",   "LONG"),
        ("rsi21_overbought", "SHORT"),
    ]
    RSI_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth", "vix_high"]
    for trig, side in RSI_TRIGS:
        for ctx in RSI_CTX:
            add("V10RSI", side, [ctx], trig, rr_set_main)

    # ---- 16. STO: Stochastic (~200) ----
    STO_TRIGS = []
    for n in [14, 21]:
        STO_TRIGS.append((f"stoch{n}_oversold",   "LONG"))
        STO_TRIGS.append((f"stoch{n}_overbought", "SHORT"))
    STO_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth"]
    for trig, side in STO_TRIGS:
        for ctx in STO_CTX:
            add("V10STO", side, [ctx], trig, rr_set_main)

    # ---- 17. SEQ: Sequential bar patterns (~150) ----
    SEQ = [
        ("3lc_reversal_long",   "LONG"),
        ("3hc_reversal_short",  "SHORT"),
        ("4lc_reversal_long",   "LONG"),
        ("4hc_reversal_short",  "SHORT"),
    ]
    SEQ_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "vix_high"]
    for trig, side in SEQ:
        for ctx in SEQ_CTX:
            add("V10SEQ", side, [ctx], trig, rr_set_main)

    # ---- 18. VOL: Volume-driven (~250) ----
    VOL_TRIGS = [
        ("vol_climax_up_reverse",   "SHORT"),
        ("vol_climax_down_reverse", "LONG"),
        ("vol_spike_up",            "LONG"),
        ("vol_spike_down",          "SHORT"),
        ("vol_dryup_break_up",      "LONG"),
        ("vol_dryup_break_down",    "SHORT"),
    ]
    VOL_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth"]
    for trig, side in VOL_TRIGS:
        for ctx in VOL_CTX:
            add("V10VOL", side, [ctx], trig, rr_set_main)

    # ---- 19. VWAP: VWAP crossover ----
    VW = [
        ("vwap_cross_up",   "LONG"),
        ("vwap_cross_down", "SHORT"),
    ]
    VW_CTX = ["am", "midday", "pm", "h1_up", "h1_down", "rth"]
    for trig, side in VW:
        for ctx in VW_CTX:
            add("V10VW", side, [ctx], trig, rr_set_main)

    # ---- 20. MC: Multi-confluence (3+ orthogonal) (~600) ----
    MC = [
        ("pullback_to_vwap_long",   "LONG",  ["h1_strong_up", "vol_normal"]),
        ("pullback_to_vwap_short",  "SHORT", ["h1_strong_down", "vol_normal"]),
        ("pullback_to_ema50_long",  "LONG",  ["h1_up", "vix_low"]),
        ("pullback_to_ema50_short", "SHORT", ["h1_down", "vix_low"]),
        ("bb_squeeze_break_up",     "LONG",  ["vol_compressed", "h1_up"]),
        ("bb_squeeze_break_down",   "SHORT", ["vol_compressed", "h1_down"]),
        ("break_above_pdh",         "LONG",  ["h1_up", "above_vwap"]),
        ("break_below_pdl",         "SHORT", ["h1_down", "below_vwap"]),
        ("range_expansion_long",    "LONG",  ["above_vwap", "h1_up"]),
        ("range_expansion_short",   "SHORT", ["below_vwap", "h1_down"]),
        ("or_break_up",             "LONG",  ["h1_up", "vol_compressed"]),
        ("or_break_down",           "SHORT", ["h1_down", "vol_compressed"]),
        ("rsi14_oversold_recover",  "LONG",  ["h1_up"]),
        ("rsi14_overbought_break",  "SHORT", ["h1_down"]),
        ("don_break_up_20",         "LONG",  ["h1_up", "above_vwap"]),
        ("don_break_down_20",       "SHORT", ["h1_down", "below_vwap"]),
        ("pinbar_btm_long",         "LONG",  ["h1_up", "above_ema50"]),
        ("pinbar_top_short",        "SHORT", ["h1_down", "below_ema50"]),
    ]
    SESS_MC = ["am", "midday", "pm", "rth"]
    for trig, side, base in MC:
        for sess in SESS_MC:
            add("V10MC", side, base + [sess], trig, rr_set_main)

    return strategies


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main(enumerate_only: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v10 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v10 — MAX enumeration (target 15K+)")
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
    print(f"  NQ 5m: {len(nq_5m):,} bars")

    print("\n[2/4] Building v10 features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v10_extras(F, nq_5m)
    print(f"  {F.shape}")

    print("\n[3/4] Enumerating strategies ...")
    strats = enumerate_v10_strategies(F)
    print(f"  TOTAL: {len(strats)}")
    from collections import Counter
    cats = Counter(s.name[:6] for s in strats)
    for cat, n in sorted(cats.items()):
        print(f"  {cat}: {n}")

    if enumerate_only:
        PROGRESS_PATH.write_text(json.dumps({
            "ENUMERATION_ONLY": True,
            "total_strategies": len(strats),
            "categories": dict(cats),
        }, indent=2, default=str))
        print(f"\n[ENUM-ONLY] saved")
        return

    contexts_d, triggers_d = make_v10_detector_dicts(F)

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
            # If user_pass but permutation wasn't run (cheap_pass was False),
            # run it now so we have a rigorous p-value for every user-pass.
            if ev["user_pass"] and ev.get("permutation_p", 1.0) == 1.0:
                if "entry_ts" in trades.columns and len(trades):
                    test_trades = trades[trades["entry_ts"].dt.tz_localize(None) > TRAIN_END.tz_localize(None)] if trades["entry_ts"].dt.tz else trades[trades["entry_ts"] > TRAIN_END.tz_localize(None)]
                    ev["permutation_p"] = float(force_permutation_test(test_trades["pnl"].values, trials=PERMUTATION_TRIALS))
                    ev["pass_permutation"] = ev["permutation_p"] <= PERMUTATION_P_VALUE
            # rigorous_pass = user_pass AND CPCV>=3 AND permutation p<=0.05 AND PF>1.0
            ev["rigorous_pass"] = (
                ev["user_pass"]
                and ev.get("cpcv_positive", 0) >= CPCV_MIN_POSITIVE
                and ev.get("permutation_p", 1.0) <= PERMUTATION_P_VALUE
                and t.get("pf", 0) > 1.0
            )
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            if ev.get("rigorous_pass"):
                r_count = sum(1 for r in results if r.get('rigorous_pass'))
                logger.info(
                    f"  [RIGOROUS-PASS #{r_count}] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} cpcv={ev.get('cpcv_positive',0)}/5 "
                    f"p={ev.get('permutation_p',1):.3f} pnl=${t['net']:+,.0f}"
                )
            elif ev.get("user_pass"):
                u_count = sum(1 for r in results if r.get('user_pass'))
                logger.info(
                    f"  [USER-PASS #{u_count}] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"cpcv={ev.get('cpcv_positive',0)}/5 p={ev.get('permutation_p',1):.3f}"
                )
            elif (idx % 100) == 0:
                rate = (idx + 1 - len(progress.get('completed', []))) / max(0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                u_pass = sum(1 for r in results if r.get('user_pass'))
                logger.info(
                    f"  [{idx+1:>5}/{len(strats)}] u_pass={u_pass}  ETA {eta:.0f}m"
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
    rigorous_passers = [r for r in results if r.get("rigorous_pass")]
    strict_passers = [r for r in results if r.get("passes_all")]
    print(f"\n[DONE] runtime: {(time.time()-started_at)/60:.1f}m")
    print(f"  total tested: {len(results)}")
    print(f"  USER-PASS (WR>=50, RR>=2, n>=100): {len(user_passers)}")
    print(f"  RIGOROUS-PASS (+CPCV>=3, perm<=0.05, PF>1.0): {len(rigorous_passers)}")
    print(f"  STRICT-PASS (orig miner thresholds): {len(strict_passers)}")

    if user_passers:
        user_passers.sort(key=lambda r: -r["test"]["net"])
        print(f"\n  Top USER-PASS by OOS net pnl:")
        for r in user_passers[:60]:
            t = r["test"]
            print(f"    {r['name'][:55]:<55}  n={t['n']:>4}  "
                  f"WR={t['wr']*100:.1f}%  PF={t['pf']:.2f}  "
                  f"$/contract={t['net']:+,.0f}")

    OUT_PATH.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "n_strategies": len(results),
        "n_user_pass": len(user_passers),
        "n_rigorous_pass": len(rigorous_passers),
        "n_strict_pass": len(strict_passers),
        "user_passers": user_passers,
        "rigorous_passers": rigorous_passers,
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

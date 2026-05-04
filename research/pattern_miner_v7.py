"""
Pattern Miner v7 — strategies built around STATISTICAL EDGES, not patterns.

After v6 produced 0 survivors from 488 classical-pattern strategies (with a
striking 36-37% mean WR — i.e. WORSE than random), we abandoned classical TA
patterns and built v7 around five types of strategies that have real
mathematical or microstructural reasoning behind them:

  Cat A — INVERSE FADE: take the OPPOSITE side of v6 triggers. Pullback,
            momentum, engulfing all loseed at WR ~36%; the opposite side
            implicitly wins at ~64%. We re-enumerate inverted directions
            and re-validate honestly.

  Cat B — NQ-ES STAT ARB: when NQ-ES divergence Z-score exceeds threshold,
            fade the divergence. Cointegration of NQ-ES has been documented
            since the 1990s; modern execution still has ms-scale noise.

  Cat C — LEAD-LAG: ES often moves a few bars before NQ on macro news.
            When ES has moved >X% in last N bars and NQ hasn't caught up,
            trade NQ in direction of ES.

  Cat D — VOL REGIME GATING: low-VIX + ATR compression + breakout →
            trend continuation. High-VIX + extended price → mean revert.

  Cat E — MULTI-CONFIRMATION (3+ orthogonal): require trend AND vol regime
            AND cross-asset agreement before trading.

We keep v6's bar-by-bar simulator, no-leak labeling (entry at next 5m bar's
open), and the 5 rigorous tests including 5,000-trial permutation.

Usage:  python -m research.pattern_miner_v7
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

# Re-use v6 infrastructure
from research.pattern_miner_v6 import (
    build_v6_features,
    label_strategy,
    evaluate_strategy,
    StrategyDef,
    MNQ_DPP, SLIPPAGE_PT, ADVERSE_SLIP_PT, COMM_PER,
    MIN_SAMPLE, MIN_WR_AFTER_COSTS, MIN_PF, MIN_SHARPE,
    PERMUTATION_TRIALS, PERMUTATION_P_VALUE,
    CPCV_FOLDS, CPCV_MIN_POSITIVE, TRAIN_END,
)
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v7_patterns.json"
PROGRESS_PATH = DATA / "v7_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v7.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v7")


# ---------------------------------------------------------------------------
# Extra v7 features that v6 doesn't have
# ---------------------------------------------------------------------------
def build_v7_extras(F: pd.DataFrame, nq_5m: pd.DataFrame,
                     es_5m: Optional[pd.DataFrame] = None,
                     vix_5m: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Add stat-arb / lead-lag / regime features on top of v6's matrix."""
    F = F.copy()
    c = nq_5m["close"]
    # NQ-ES divergence Z-scores at multiple horizons
    if es_5m is not None and not es_5m.empty:
        es_c = es_5m["close"].reindex(F.index, method="ffill")
        # Returns
        nq_r = c.pct_change(1)
        es_r = es_c.pct_change(1)
        for n in [5, 20, 60]:
            div = (c.pct_change(n) - es_c.pct_change(n))
            mu = div.rolling(200).mean()
            sd = div.rolling(200).std()
            F[f"nq_es_div_z_{n}"] = (div - mu) / sd
        # Lead-lag: ES move in last K bars, NQ move so far
        for k in [3, 5, 10]:
            es_move_k = es_c.pct_change(k)
            nq_move_k = c.pct_change(k)
            # Z-scored ES move vs its own history
            mu = es_move_k.rolling(200).mean()
            sd = es_move_k.rolling(200).std()
            F[f"es_move_z_{k}"] = (es_move_k - mu) / sd
            # Lag = ES has moved big but NQ hasn't kept up
            F[f"lag_nq_es_{k}"] = es_move_k - nq_move_k
            # Z-score the lag
            mu2 = F[f"lag_nq_es_{k}"].rolling(200).mean()
            sd2 = F[f"lag_nq_es_{k}"].rolling(200).std()
            F[f"lag_nq_es_z_{k}"] = (F[f"lag_nq_es_{k}"] - mu2) / sd2
    # Realized vol regime (rolling std of 1-bar returns)
    rv = c.pct_change(1).rolling(50).std()
    F["rv50"] = rv
    F["rv50_z"] = (rv - rv.rolling(200).mean()) / rv.rolling(200).std()
    # Vol regime: ATR_compression < 0.7 AND vix_z < -0.5 = "tight regime"
    F["regime_tight"] = ((F["atr_compression"] < 0.7) &
                          (F.get("vix_z_50", pd.Series(-1, index=F.index)) < -0.5)).astype(int)
    F["regime_loose"] = ((F["atr_compression"] > 1.3) &
                          (F.get("vix_z_50", pd.Series(1, index=F.index)) > 0.5)).astype(int)
    # Distance from VWAP-like rolling mean (mean-revert anchor)
    sma50 = c.rolling(50).mean()
    F["dist_sma50_atr"] = (c - sma50) / F["atr14"]
    return F.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# v7 trigger detectors — built on top of v6 + new statistical triggers
# ---------------------------------------------------------------------------
def v7_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    """Return dict of trigger name -> bool series. Pre-computed for speed."""
    T = {}
    # --- v6 inverse fades (the 36% WR triggers, but flipped direction) ---
    # We use the SAME trigger condition but assign opposite side via StrategyDef.
    T["pullback_from_high_50"] = (F["pullback_from_high"] > 0.50) & (F["pullback_from_high"] < 0.80)
    T["pullback_from_low_50"]  = (F["pullback_from_low"] > 0.50) & (F["pullback_from_low"] < 0.80)
    T["momentum_burst_up"]     = (F["consec_dir"] >= 3) & (F["bar_dir"] > 0)
    T["momentum_burst_down"]   = (F["consec_dir"] >= 3) & (F["bar_dir"] < 0)
    T["bullish_engulfing"]     = (F["bar_dir"] > 0) & (F["body_abs"] > F["body_abs"].shift(1) * 1.5) & (F["bar_dir"].shift(1) < 0)
    T["bearish_engulfing"]     = (F["bar_dir"] < 0) & (F["body_abs"] > F["body_abs"].shift(1) * 1.5) & (F["bar_dir"].shift(1) > 0)

    # --- NQ-ES stat-arb triggers ---
    if "nq_es_div_z_20" in F.columns:
        # NQ over-extended vs ES → fade DOWN (SHORT NQ)
        T["nqes_overextended_20"]  = F["nq_es_div_z_20"] >  2.0
        # NQ under-extended → bounce UP (LONG NQ)
        T["nqes_underextended_20"] = F["nq_es_div_z_20"] < -2.0
        T["nqes_overextended_5"]   = F["nq_es_div_z_5"]  >  2.0
        T["nqes_underextended_5"]  = F["nq_es_div_z_5"]  < -2.0
        T["nqes_overextended_60"]  = F["nq_es_div_z_60"] >  2.0
        T["nqes_underextended_60"] = F["nq_es_div_z_60"] < -2.0

    # --- Lead-lag triggers ---
    if "lag_nq_es_z_5" in F.columns:
        # ES moved up sharply, NQ lagging → LONG NQ (catch up)
        T["es_led_up_5"]   = (F["es_move_z_5"] > 1.5) & (F["lag_nq_es_z_5"] > 1.0)
        T["es_led_down_5"] = (F["es_move_z_5"] < -1.5) & (F["lag_nq_es_z_5"] < -1.0)
        T["es_led_up_10"]   = (F["es_move_z_10"] > 1.5) & (F["lag_nq_es_z_10"] > 1.0)
        T["es_led_down_10"] = (F["es_move_z_10"] < -1.5) & (F["lag_nq_es_z_10"] < -1.0)

    # --- Mean-reversion triggers (extended price = fade) ---
    T["price_extended_up"]   = F["dist_sma50_atr"] >  2.0
    T["price_extended_down"] = F["dist_sma50_atr"] < -2.0

    return {k: v.fillna(False) for k, v in T.items()}


# ---------------------------------------------------------------------------
# v7 strategy enumeration
# ---------------------------------------------------------------------------
def enumerate_v7_strategies(F: pd.DataFrame) -> list[StrategyDef]:
    has_es = "nq_es_div_z_20" in F.columns
    has_vix = "vix_z_50" in F.columns

    strategies = []
    sid = 0

    rr_profiles = [
        # Tighter targets favor mean-reversion (small wins, occasional losses)
        (1.5, 0.7,  20, "MR_quick"),       # mean-revert: 1.5 ATR stop, 0.7 ATR target, 20min
        (2.0, 1.0,  30, "MR_std"),
        (1.5, 1.0,  30, "MR_balanced"),
        (1.0, 1.0,  30, "RR1"),            # 1:1 baseline
        (1.0, 1.5,  45, "RR1_5"),
    ]

    # ---- Cat A: Inverse v6 triggers (the 36% WR pattern, flipped side) ----
    INVERTED_TRIGGERS = [
        ("pullback_from_high_50", "SHORT"),  # was LONG losing
        ("pullback_from_low_50",  "LONG"),   # was SHORT losing
        ("momentum_burst_up",     "SHORT"),  # was LONG losing → fade
        ("momentum_burst_down",   "LONG"),   # was SHORT losing → fade
        ("bullish_engulfing",     "SHORT"),  # was LONG losing → fade
        ("bearish_engulfing",     "LONG"),   # was SHORT losing → fade
    ]
    A_CONTEXTS = ["rth_morning", "rth_midday", "rth_afternoon", "mid_range",
                   "vix_low", "vix_high"]
    for trig, side in INVERTED_TRIGGERS:
        for ctx in A_CONTEXTS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"V7A_{side}_{trig[:18]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=10,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    # ---- Cat B: NQ-ES stat-arb fades ----
    if has_es:
        STAT_ARB_TRIGGERS = [
            ("nqes_overextended_5",  "SHORT"),
            ("nqes_underextended_5", "LONG"),
            ("nqes_overextended_20", "SHORT"),
            ("nqes_underextended_20","LONG"),
            ("nqes_overextended_60", "SHORT"),
            ("nqes_underextended_60","LONG"),
        ]
        B_CONTEXTS = ["rth_morning", "rth_midday", "rth_afternoon"]
        for trig, side in STAT_ARB_TRIGGERS:
            for ctx in B_CONTEXTS:
                for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                    sid += 1
                    strategies.append(StrategyDef(
                        name=f"V7B_{side}_{trig[:18]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                        side=side, contexts=[ctx], trigger=trig,
                        context_window_bars=5,
                        stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                    ))

    # ---- Cat C: Lead-lag (ES moved, NQ lagging) ----
    if has_es:
        LEAD_LAG_TRIGGERS = [
            ("es_led_up_5",    "LONG"),   # ES up, NQ catching up
            ("es_led_down_5",  "SHORT"),
            ("es_led_up_10",   "LONG"),
            ("es_led_down_10", "SHORT"),
        ]
        C_CONTEXTS = ["rth_morning", "rth_midday", "rth_afternoon"]
        # Lead-lag wants quick targets (the lag closes fast)
        ll_rrs = [
            (1.0, 0.5, 10, "fast"),
            (1.0, 0.7, 15, "med"),
            (1.5, 0.7, 20, "wide"),
        ]
        for trig, side in LEAD_LAG_TRIGGERS:
            for ctx in C_CONTEXTS:
                for stop_a, tgt_a, mh, rrlabel in ll_rrs:
                    sid += 1
                    strategies.append(StrategyDef(
                        name=f"V7C_{side}_{trig[:18]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                        side=side, contexts=[ctx], trigger=trig,
                        context_window_bars=3,
                        stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                    ))

    # ---- Cat D: Mean-reversion on extended price ----
    MR_TRIGGERS = [
        ("price_extended_up",   "SHORT"),
        ("price_extended_down", "LONG"),
    ]
    D_CONTEXTS = ["rth_morning", "rth_midday", "rth_afternoon", "vix_low",
                   "compressed_vol", "expanded_vol"]
    for trig, side in MR_TRIGGERS:
        for ctx in D_CONTEXTS:
            for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"V7D_{side}_{trig[:18]}_x_{ctx[:14]}_{rrlabel}_{sid:04d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=10,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))

    # ---- Cat E: Multi-confirmation (uses inverted v6 triggers + extra contexts) ----
    if has_es:
        E_TRIGGERS = [
            ("pullback_from_high_50", "SHORT"),
            ("pullback_from_low_50",  "LONG"),
            ("momentum_burst_up",     "SHORT"),
            ("momentum_burst_down",   "LONG"),
        ]
        # Multi-context: vol regime AND cross-asset alignment
        E_CONTEXT_PAIRS = [
            ["compressed_vol", "nq_outperforming_es"],   # vol tight + nq leading → fade up
            ["compressed_vol", "nq_underperforming_es"], # vol tight + nq lagging → fade down
            ["vix_low", "rth_midday"],                    # calm + mid-day = mean revert
            ["vix_high", "rth_morning"],                  # spike + open = fade
        ]
        for trig, side in E_TRIGGERS:
            for ctxs in E_CONTEXT_PAIRS:
                for stop_a, tgt_a, mh, rrlabel in rr_profiles:
                    sid += 1
                    strategies.append(StrategyDef(
                        name=f"V7E_{side}_{trig[:14]}_x_{'_'.join(c[:6] for c in ctxs)}_{rrlabel}_{sid:04d}",
                        side=side, contexts=ctxs, trigger=trig,
                        context_window_bars=10,
                        stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                    ))

    return strategies


# ---------------------------------------------------------------------------
# Adapter: v6's label_strategy expects context_detectors() and trigger_detectors()
# returning callables. We pre-compute the trigger masks here and wrap.
# ---------------------------------------------------------------------------
def make_v7_detector_dicts(F: pd.DataFrame):
    """Return (contexts_d, triggers_d) dicts compatible with v6's label_strategy."""
    from research.pattern_miner_v6 import context_detectors as v6_contexts
    contexts_d = v6_contexts()
    # Pre-compute v7 triggers as series, then expose as identity-functions
    v7_trigs_series = v7_trigger_detectors(F)
    def make_fn(s):
        return lambda F: s
    triggers_d = {name: make_fn(s) for name, s in v7_trigs_series.items()}
    return contexts_d, triggers_d


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v7 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v7 — stat-arb / lead-lag / vol-regime / inverse-fade")
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

    print("\n[2/4] Building v7 features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    print(f"  {F.shape}")

    contexts_d, triggers_d = make_v7_detector_dicts(F)

    print("\n[3/4] Enumerating strategies ...")
    strats = enumerate_v7_strategies(F)
    print(f"  total strategies: {len(strats)}")
    # Show distribution
    from collections import Counter
    cats = Counter(s.name[:4] for s in strats)
    for cat, n in sorted(cats.items()):
        print(f"  {cat}: {n}")

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
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            t = ev.get("test", {})
            if ev.get("passes_all"):
                logger.info(
                    f"  [✓ PASS] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} pnl=${t['net']:+,.0f} p={ev['permutation_p']:.3f}"
                )
            elif (idx % 10) == 0:
                rate = (idx + 1 - len(progress['completed'])) / max(0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                logger.info(
                    f"  [{idx+1:>3}/{len(strats)}] {strat.name[:55]:<55}  "
                    f"n={t.get('n',0):>3}  WR={t.get('wr',0)*100:.1f}%  "
                    f"PF={t.get('pf',0):.2f}  passes={ev.get('passes_all',False)}  "
                    f"ETA {eta:.0f}m"
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
                              "passes_all": False})
            completed.add(strat.name)

    progress["completed"] = sorted(completed)
    progress["results"] = results
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, default=str))

    survivors = [r for r in results if r.get("passes_all")]
    print(f"\n[4/4] DONE — total runtime: {(time.time()-started_at)/60:.1f}m")
    print(f"  total strategies tested: {len(results)}")
    print(f"  SURVIVORS (passed all 5 tests + permutation): {len(survivors)}")
    if survivors:
        print(f"\n  top survivors by OOS net pnl:")
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
    try:
        main()
    except Exception as e:
        logger.exception(f"main() crashed: {e}")
        raise

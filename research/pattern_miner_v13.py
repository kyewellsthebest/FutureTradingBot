"""
Pattern Miner v13 — Technical/statistical strategies BEYOND NQ-ES stat-arb.

Three new families with different alpha mechanisms than v11/v12:

  A. NQ-VIX residual Z-score
     NQ and VIX have a structural negative correlation (~-0.7). When the
     residual (NQ_return + beta*VIX_return) deviates from rolling mean by
     a large Z-score, that's a "correlation break" — often institutional
     hedging flow (NQ up + VIX up = panic hedging during rally) or relief
     (NQ down + VIX down = exhaustion). Trade the resolution.

  B. NQ-RTY rotation Z-score
     Nasdaq vs Russell 2000 ratio is the canonical "growth-vs-value" or
     "tech-vs-cyclicals" rotation gauge. When the NQ/RTY return spread
     deviates significantly, that's rotation flow which historically
     mean-reverts within hours.

  C. VIX-regime-gated NQ-ES stat-arb
     Same NQ-ES return divergence trigger as v11, but contextualized by
     the VIX percentile regime: low VIX (<25th pct), mid VIX (25-75th),
     high VIX (>75th). Mean-reversion edge is regime-dependent — high
     VIX days produce more extreme dislocations that mean-revert harder.

All strategies use the same 11 rigorous tests as v11/v12 (CPCV, perm,
OOS train/test, slippage, etc.). Same user-pass thresholds. Output to
data/mined_v13_patterns.json.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, evaluate_strategy, StrategyDef, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import (
    USER_MIN_WR, USER_MIN_RR, USER_MIN_TRADES, build_v11_extras,
)
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v13_patterns.json"
PROGRESS_PATH = DATA / "v13_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v13.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v13")


# ---------------------------------------------------------------------------
# Feature builders — cross-asset Z-scores beyond NQ-ES
# ---------------------------------------------------------------------------
def build_v13_extras(F: pd.DataFrame, nq_5m: pd.DataFrame,
                       rty_5m: pd.DataFrame | None,
                       vix_5m: pd.DataFrame | None) -> pd.DataFrame:
    """Add NQ-VIX, NQ-RTY residual Z-scores at multiple windows + VIX percentile."""
    F = F.copy()
    c = nq_5m["close"]

    # NQ-VIX residual Z-scores. VIX moves inverse to NQ; we use a regression-
    # based residual: residual = NQ_pct_change - beta*VIX_pct_change.
    # Beta is estimated rolling. Then Z-score the residual.
    if vix_5m is not None and not vix_5m.empty:
        vix_c = vix_5m["close"].reindex(F.index, method="ffill")
        for n in [10, 20, 30, 60, 90, 120]:
            nq_ret = c.pct_change(n)
            vix_ret = vix_c.pct_change(n)
            # rolling beta (200 bars)
            cov = nq_ret.rolling(200).cov(vix_ret)
            var = vix_ret.rolling(200).var()
            beta = cov / var.where(var.abs() > 1e-12, np.nan)
            residual = nq_ret - beta * vix_ret
            mu = residual.rolling(200).mean()
            sd = residual.rolling(200).std()
            F[f"nq_vix_resid_z_{n}"] = (residual - mu) / sd

        # VIX absolute percentile (rolling 500 bars ~ 2 trading days)
        F["vix_level"] = vix_c
        F["vix_pct_500"] = vix_c.rolling(500).rank(pct=True)
        # VIX z-score (level vs rolling mean)
        vix_mu = vix_c.rolling(200).mean()
        vix_sd = vix_c.rolling(200).std()
        F["vix_z_200"] = (vix_c - vix_mu) / vix_sd

    # NQ-RTY rotation Z-scores
    if rty_5m is not None and not rty_5m.empty:
        rty_c = rty_5m["close"].reindex(F.index, method="ffill")
        for n in [10, 20, 30, 60, 90, 120]:
            nq_ret = c.pct_change(n)
            rty_ret = rty_c.pct_change(n)
            div = nq_ret - rty_ret
            mu = div.rolling(200).mean()
            sd = div.rolling(200).std()
            F[f"nq_rty_div_z_{n}"] = (div - mu) / sd

    return F.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# Triggers — Z-score crossings on cross-asset residuals
# ---------------------------------------------------------------------------
def v13_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    T = {}
    # Family A: NQ-VIX residual Z
    for w in [10, 20, 30, 60, 90, 120]:
        col = f"nq_vix_resid_z_{w}"
        if col not in F.columns:
            continue
        for thr in [15, 17, 20, 22, 25, 27, 30]:
            t = thr / 10.0
            T[f"vix_long_{w}_{thr}"]  = F[col] < -t   # NQ underperforming vs VIX-implied → LONG
            T[f"vix_short_{w}_{thr}"] = F[col] >  t   # NQ overperforming vs VIX-implied → SHORT
    # Family B: NQ-RTY rotation Z
    for w in [10, 20, 30, 60, 90, 120]:
        col = f"nq_rty_div_z_{w}"
        if col not in F.columns:
            continue
        for thr in [15, 17, 20, 22, 25, 27, 30]:
            t = thr / 10.0
            T[f"rty_long_{w}_{thr}"]  = F[col] < -t
            T[f"rty_short_{w}_{thr}"] = F[col] >  t
    # Family C: NQ-ES stat-arb (same triggers as v11) — reused for VIX-regime gating
    for w in [15, 20, 30, 45, 60, 90, 120]:
        col = f"nq_es_div_z_{w}"
        if col not in F.columns:
            continue
        for thr in [15, 20, 25, 30]:
            t = thr / 10.0
            T[f"sa_long_{w}_{thr}"]  = F[col] < -t
            T[f"sa_short_{w}_{thr}"] = F[col] >  t
    return {k: v.fillna(False) for k, v in T.items()}


# ---------------------------------------------------------------------------
# Contexts — combine time-of-day with VIX regime
# ---------------------------------------------------------------------------
def v13_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    C = {}
    h = F["ny_hour"]; m = F["ny_minute"]
    # Time-of-day buckets covering 24h NY (same as v11+v12 combined)
    C["pm_full"]      = (h >= 14) & (h < 16)
    C["t_1330_1530"]  = ((h == 13) & (m >= 30)) | (h == 14) | ((h == 15) & (m < 30))
    C["evening_us"]   = (h >= 19) & (h <= 22)
    C["overnight"]    = (h >= 23) | (h <= 2)
    C["t_0200_0300"]  = (h == 2)
    C["t_2000_2100"]  = (h == 20)

    # VIX regime contexts (only available if vix features were built)
    if "vix_pct_500" in F.columns:
        C["vix_low"]   = F["vix_pct_500"] < 0.25
        C["vix_mid"]   = (F["vix_pct_500"] >= 0.25) & (F["vix_pct_500"] < 0.75)
        C["vix_high"]  = F["vix_pct_500"] >= 0.75
    if "vix_z_200" in F.columns:
        C["vix_spike"]   = F["vix_z_200"] > 2.0    # VIX 2 std above mean
        C["vix_collapse"] = F["vix_z_200"] < -2.0  # VIX collapsing

    # Combined regime + time contexts (more selective)
    if "vix_high" in C:
        C["pm_vix_high"]  = C["pm_full"] & C["vix_high"]
        C["pm_vix_mid"]   = C["pm_full"] & C["vix_mid"]
        C["pm_vix_low"]   = C["pm_full"] & C["vix_low"]
    return {k: v.fillna(False) for k, v in C.items()}


def make_v13_detector_dicts(F: pd.DataFrame):
    contexts_d_series = v13_context_detectors(F)
    triggers_d_series = v13_trigger_detectors(F)
    def make_fn(s):
        return lambda F, _s=s: _s
    contexts_d = {k: make_fn(v) for k, v in contexts_d_series.items()}
    triggers_d = {k: make_fn(v) for k, v in triggers_d_series.items()}
    return contexts_d, triggers_d


# ---------------------------------------------------------------------------
# Strategy enumeration
# ---------------------------------------------------------------------------
def enumerate_v13_strategies(F: pd.DataFrame) -> list[StrategyDef]:
    rr_profiles = [
        (1.0, 2.0,  45, "RR2_std"),
        (1.0, 2.5,  60, "RR2_5"),
        (1.0, 3.0,  75, "RR3_std"),
        (1.5, 3.0,  75, "RR2_wide"),
        (1.5, 4.0,  90, "RR2_7wide"),
    ]

    strategies = []
    sid = 0
    seen = set()

    # Family A: NQ-VIX residual Z (broad time + VIX regime contexts)
    A_contexts = ["pm_full", "evening_us", "overnight", "vix_high", "vix_mid", "vix_low",
                    "pm_vix_high", "pm_vix_mid", "pm_vix_low", "vix_spike", "vix_collapse"]
    A_windows = [20, 30, 60, 90, 120]
    A_thresholds = [15, 20, 25]
    for w in A_windows:
        for thr in A_thresholds:
            for side in ("long", "short"):
                trig = f"vix_{side}_{w}_{thr}"
                for ctx in A_contexts:
                    for stop_a, tgt_a, mh, rrl in rr_profiles:
                        sid += 1
                        name = f"V13A_{side.upper()}_{trig[:14]}_x_{ctx[:14]}_{rrl}_{sid:05d}"
                        if name in seen:
                            continue
                        seen.add(name)
                        strategies.append(StrategyDef(
                            name=name, side=side.upper(), contexts=[ctx], trigger=trig,
                            context_window_bars=5, stop_atr=stop_a, target_atr=tgt_a,
                            max_hold_min=mh,
                        ))

    # Family B: NQ-RTY rotation
    B_contexts = ["pm_full", "evening_us", "overnight", "vix_high", "vix_low",
                    "pm_vix_high", "pm_vix_mid", "vix_spike"]
    B_windows = [20, 30, 60, 90]
    B_thresholds = [15, 20, 25]
    for w in B_windows:
        for thr in B_thresholds:
            for side in ("long", "short"):
                trig = f"rty_{side}_{w}_{thr}"
                for ctx in B_contexts:
                    for stop_a, tgt_a, mh, rrl in rr_profiles:
                        sid += 1
                        name = f"V13B_{side.upper()}_{trig[:14]}_x_{ctx[:14]}_{rrl}_{sid:05d}"
                        if name in seen:
                            continue
                        seen.add(name)
                        strategies.append(StrategyDef(
                            name=name, side=side.upper(), contexts=[ctx], trigger=trig,
                            context_window_bars=5, stop_atr=stop_a, target_atr=tgt_a,
                            max_hold_min=mh,
                        ))

    # Family C: VIX-regime-gated NQ-ES stat-arb (REFINEMENT of v11)
    C_contexts = ["pm_vix_high", "pm_vix_mid", "pm_vix_low", "vix_spike", "vix_collapse"]
    C_windows = [20, 45, 60, 120]
    C_thresholds = [15, 20, 25]
    for w in C_windows:
        for thr in C_thresholds:
            for side in ("long", "short"):
                trig = f"sa_{side}_{w}_{thr}"
                for ctx in C_contexts:
                    for stop_a, tgt_a, mh, rrl in rr_profiles:
                        sid += 1
                        name = f"V13C_{side.upper()}_{trig[:14]}_x_{ctx[:14]}_{rrl}_{sid:05d}"
                        if name in seen:
                            continue
                        seen.add(name)
                        strategies.append(StrategyDef(
                            name=name, side=side.upper(), contexts=[ctx], trigger=trig,
                            context_window_bars=5, stop_atr=stop_a, target_atr=tgt_a,
                            max_hold_min=mh,
                        ))
    return strategies


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v13 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v13 — cross-asset technical/statistical strategies")
    print("=" * 78)

    progress = {"completed": [], "results": []}
    if PROGRESS_PATH.exists():
        try:
            progress = json.loads(PROGRESS_PATH.read_text())
            logger.info(f"resuming with {len(progress['completed'])} done")
        except Exception:
            pass

    print("\n[1/4] Loading data ...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = vix_5m = None
    try: rty_5m = load_intraday_5min("rty")
    except Exception: pass
    try: vix_5m = load_vix_5min()
    except Exception: pass
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df is not None and df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    print(f"  NQ 5m: {len(nq_5m):,}  RTY: {len(rty_5m) if rty_5m is not None else 0:,}  "
            f"VIX: {len(vix_5m) if vix_5m is not None else 0:,}")

    print("\n[2/4] Building features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    F = build_v13_extras(F, nq_5m, rty_5m, vix_5m)
    print(f"  {F.shape}")
    new_cols = [c for c in F.columns if c.startswith(("nq_vix_resid", "nq_rty_div", "vix_pct", "vix_z", "vix_level"))]
    print(f"  v13 features: {new_cols}")

    print("\n[3/4] Enumerating strategies ...")
    strats = enumerate_v13_strategies(F)
    print(f"  TOTAL: {len(strats)}")

    contexts_d, triggers_d = make_v13_detector_dicts(F)

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
            rr = strat.target_atr / strat.stop_atr
            ev["user_pass"] = (
                t.get("wr", 0) >= USER_MIN_WR
                and rr >= USER_MIN_RR
                and t.get("n", 0) >= USER_MIN_TRADES
            )
            results.append(ev)
            completed.add(strat.name)
            n_done_now += 1

            if ev.get("user_pass"):
                u = sum(1 for r in results if r.get('user_pass'))
                logger.info(
                    f"  [USER-PASS #{u}] {strat.name}  n={t['n']:>4} WR={t['wr']*100:.1f}% "
                    f"PF={t['pf']:.2f} cpcv={ev.get('cpcv_positive',0)}/5 pnl=${t['net']:+,.0f}"
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
                PROGRESS_PATH.write_text(json.dumps(progress))
                last_save = now
                n_done_now = 0
        except Exception as e:
            logger.warning(f"  {strat.name} crashed: {e}")
            continue

    progress["completed"] = sorted(completed)
    progress["results"] = results
    PROGRESS_PATH.write_text(json.dumps(progress))

    user_passers = [r for r in results if r.get('user_pass')]
    out = {
        "n_strategies": len(strats),
        "n_evaluated": len(results),
        "n_user_pass": len(user_passers),
        "user_passers": user_passers,
        "all_results": results,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    logger.info(f"\nDone. {len(user_passers)} user-pass / {len(results)} tested.")
    logger.info(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

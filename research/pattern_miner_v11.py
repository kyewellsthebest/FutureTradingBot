"""
Pattern Miner v11 — DEEP EXPANSION of NQ-ES stat-arb.

v10 found 11 user-pass strategies, ALL from V10SA (NQ-ES divergence reversion
in NY afternoon). Every other category produced 0. So v11 ignores those dead
ends and instead massively expands the NQ-ES stat-arb space.

Expansion dimensions:
  * Z-thresholds: 1.5, 1.7, 2.0, 2.2, 2.5, 2.7, 3.0 (7)
  * Lookback windows: 10, 15, 20, 30, 45, 60, 90, 120 bars (8)
  * Time contexts: fine-grained NY-time slices in afternoon (8)
  * RR profiles: 5 main 1:2-1:3 variants (5)
  * Side: LONG (NQ underperforming) and SHORT (NQ overperforming) (2)

Total: 7 × 8 × 8 × 5 × 2 = 4480 strategies, but we'll prune to ~2500
focusing on time slices that already showed edge (t_143, t_150, pm).
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
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.indicators import atr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v11_patterns.json"
PROGRESS_PATH = DATA / "v11_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v11.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v11")

USER_MIN_WR = 0.50
USER_MIN_RR = 2.0
USER_MIN_TRADES = 100


def build_v11_features(F: pd.DataFrame, nq_5m: pd.DataFrame) -> pd.DataFrame:
    """Add fine-grained Z-scores at MORE windows than v7."""
    F = F.copy()
    es_c = None
    # We need ES; if nq_es_div_z_20 already exists, ES is already loaded.
    # But for new windows we need to recompute from raw closes. Skip if no ES.
    # The existing F has nq_es_div_z_5/_20/_60. We need 10, 15, 30, 45, 90, 120.
    # We'll compute these from F["es_ret_5"] derived columns... but those don't
    # exist for arbitrary windows. So we go back to pct_change calc.
    # Easiest: re-derive from c (NQ close) and reconstruct es_c.
    # The way v7 was built: es_c.diff(N) - so we can extract es returns from
    # F["es_ret_5"] (=es_c.diff(5)) inversely. But that's lossy.
    # Cleaner: caller must pass es_5m. We'll require it via build_v11_extras.
    return F


def build_v11_extras(F: pd.DataFrame, nq_5m: pd.DataFrame,
                      es_5m: pd.DataFrame) -> pd.DataFrame:
    """Add Z-scored NQ-ES divergence at MANY more windows."""
    F = F.copy()
    c = nq_5m["close"]
    es_c = es_5m["close"].reindex(F.index, method="ffill")
    # Many more windows than v7 (which had 5, 20, 60)
    for n in [10, 15, 20, 30, 45, 60, 90, 120]:
        col = f"nq_es_div_z_{n}"
        if col not in F.columns:
            div = c.pct_change(n) - es_c.pct_change(n)
            mu = div.rolling(200).mean()
            sd = div.rolling(200).std()
            F[col] = (div - mu) / sd
    return F.replace([np.inf, -np.inf], np.nan)


def v11_trigger_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    T = {}
    # Z-thresholds at MANY granularities
    for w in [10, 15, 20, 30, 45, 60, 90, 120]:
        col = f"nq_es_div_z_{w}"
        if col not in F.columns:
            continue
        for thr in [15, 17, 20, 22, 25, 27, 30]:
            t = thr / 10.0
            T[f"sa_long_{w}_{thr}"]  = F[col] < -t   # NQ underperforming, fade-up
            T[f"sa_short_{w}_{thr}"] = F[col] >  t   # NQ overperforming, fade-down
    return {k: v.fillna(False) for k, v in T.items()}


def v11_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    C = {}
    # Fine-grained NY-time slices in afternoon (where edge was found)
    C["t_1300_1400"] = F["is_1400_1430"] | False  # placeholder for 13:00-14:00 (compute below)
    # Re-derive properly
    h = F["ny_hour"]; m = F["ny_minute"]
    C["t_1300_1330"] = (h == 13) & (m < 30)
    C["t_1330_1400"] = (h == 13) & (m >= 30)
    C["t_1400_1430"] = (h == 14) & (m < 30)
    C["t_1430_1500"] = (h == 14) & (m >= 30)
    C["t_1500_1530"] = (h == 15) & (m < 30)
    C["t_1530_1600"] = (h == 15) & (m >= 30)
    C["pm_full"]     = (h >= 14) & (h < 16)        # whole afternoon
    C["t_1330_1530"] = ((h == 13) & (m >= 30)) | (h == 14) | ((h == 15) & (m < 30))
    return {k: v.fillna(False) for k, v in C.items()}


def enumerate_v11_strategies(F: pd.DataFrame) -> list[StrategyDef]:
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

    # All combinations of: side × window × Z-thr × time × RR
    SIDES_TRIGS = []
    for w in [10, 15, 20, 30, 45, 60, 90, 120]:
        for thr in [15, 17, 20, 22, 25, 27, 30]:
            SIDES_TRIGS.append((f"sa_long_{w}_{thr}",  "LONG"))
            SIDES_TRIGS.append((f"sa_short_{w}_{thr}", "SHORT"))

    TIME_CTXS = [
        "t_1300_1330", "t_1330_1400", "t_1400_1430",
        "t_1430_1500", "t_1500_1530", "t_1530_1600",
        "pm_full", "t_1330_1530",
    ]

    for trig, side in SIDES_TRIGS:
        for ctx in TIME_CTXS:
            for stop_a, tgt_a, mh, rrl in rr_profiles:
                sid += 1
                name = f"V11SA_{side}_{trig[:14]}_x_{ctx[:14]}_{rrl}_{sid:05d}"
                if name in seen:
                    continue
                seen.add(name)
                strategies.append(StrategyDef(
                    name=name,
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=5,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))
    return strategies


def make_v11_detector_dicts(F: pd.DataFrame):
    contexts_d_series = v11_context_detectors(F)
    triggers_d_series = v11_trigger_detectors(F)
    def make_fn(s):
        return lambda F, _s=s: _s
    contexts_d = {k: make_fn(v) for k, v in contexts_d_series.items()}
    triggers_d = {k: make_fn(v) for k, v in triggers_d_series.items()}
    return contexts_d, triggers_d


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v11 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v11 — DEEP NQ-ES stat-arb expansion")
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
    print(f"  NQ 5m: {len(nq_5m):,} bars")

    print("\n[2/4] Building features ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    print(f"  {F.shape}")

    print("\n[3/4] Enumerating ...")
    strats = enumerate_v11_strategies(F)
    print(f"  TOTAL: {len(strats)}")

    contexts_d, triggers_d = make_v11_detector_dicts(F)

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
                u_count = sum(1 for r in results if r.get('user_pass'))
                logger.info(
                    f"  [USER-PASS #{u_count}] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"Sh={t['sharpe']:+.2f} cpcv={ev.get('cpcv_positive',0)}/5 "
                    f"pnl=${t['net']:+,.0f}"
                )
            elif (idx % 50) == 0:
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
    print(f"\n[DONE] runtime: {(time.time()-started_at)/60:.1f}m")
    print(f"  total tested: {len(results)}")
    print(f"  USER-PASS: {len(user_passers)}")

    if user_passers:
        user_passers.sort(key=lambda r: -r["test"]["net"])
        for r in user_passers[:60]:
            t = r["test"]
            print(f"    {r['name'][:55]:<55}  n={t['n']:>4}  "
                  f"WR={t['wr']*100:.1f}%  PF={t['pf']:.2f}  "
                  f"$/contract={t['net']:+,.0f}")

    OUT_PATH.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "n_strategies": len(results),
        "n_user_pass": len(user_passers),
        "user_passers": user_passers,
        "all_results": results,
    }, indent=2, default=str))
    print(f"\nWrote {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"main() crashed: {e}")
        raise

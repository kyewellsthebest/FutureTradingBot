"""
Pattern Miner SR — S/R level-fade family.

A fundamentally different paradigm from v11/v12/v13/v15 (all NQ-ES return-
divergence Z-score mean reversion). Here we fade a STRUCTURAL price level —
the most recent confirmed swing high/low inside a recency window — with a
small stop just past the level and a wide target. This is the coded version
of the discretionary 4H swing short shown in the user's screenshot, ported
to 5-min bars and a multi-hour intraday hold.

Honest framing: this is a new attempt at a new family. It runs through the
EXACT SAME gauntlet that just killed v15 and the meta-model — purged CPCV,
5000-trial permutation, no goalposts moved. If S/R fading has real edge on
NQ, it earns deployment. If not, it doesn't ship.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, evaluate_strategy, StrategyDef, TRAIN_END,
)
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.sr_signals import build_sr_triggers, SWING_K, LEVEL_RECENCY, PROX_BPS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
SMOKE = bool(os.environ.get("SR_SMOKE"))
OUT_PATH = DATA / ("mined_sr_patterns_smoke.json" if SMOKE
                   else "mined_sr_patterns.json")
PROGRESS_PATH = DATA / ("sr_progress_smoke.json" if SMOKE
                        else "sr_progress.json")
LOG_PATH = PROJECT_ROOT / "logs" / "miner_sr.log"
LOG_PATH.parent.mkdir(exist_ok=True)
logger = logging.getLogger("miner_sr")

USER_MIN_WR = 0.50
USER_MIN_RR = 2.0
USER_MIN_TRADES = 100


def sr_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    """Wide intraday/session contexts the S/R triggers can fire inside.
    Includes the 16-19 ET gap the user flagged ('5-8 AM AEST')."""
    h, m = F["ny_hour"], F["ny_minute"]
    rth = ((h == 9) & (m >= 30)) | ((h >= 10) & (h < 16))
    C = {
        "t_pm_full":     (h >= 14) & (h < 16),
        "t_rth_full":    rth,
        "t_1600_1900":   (h >= 16) & (h < 19),   # the user-flagged gap
        "t_evening_us":  (h >= 19) & (h <= 22),
    }
    return {k: v.fillna(False) for k, v in C.items()}


def enumerate_sr_strategies() -> list[StrategyDef]:
    """S/R-fade RR profiles: small structural stop, wide target — opposite
    of the v11 1:2 RR which suits mean-reversion. max_hold up to ~6 h keeps
    these strictly intraday (the bot has no overnight-risk infrastructure)."""
    rr_profiles = [
        (0.4, 3.0, 180, "RR_sr_a"),
        (0.5, 4.0, 360, "RR_sr_b"),
        (0.3, 5.0, 240, "RR_sr_c"),
        (0.6, 5.0, 360, "RR_sr_d"),
    ]
    contexts = ["t_pm_full", "t_rth_full", "t_1600_1900", "t_evening_us"]

    triggers: list[tuple[str, str]] = []
    for k in SWING_K:
        for n in LEVEL_RECENCY:
            for p in PROX_BPS:
                triggers.append((f"sr_short_REJ_{k}_{n}_{p}", "SHORT"))
                triggers.append((f"sr_long_REJ_{k}_{n}_{p}",  "LONG"))

    strategies: list[StrategyDef] = []
    sid = 0
    for trig, side in triggers:
        for ctx in contexts:
            for stop_a, tgt_a, mh, rrl in rr_profiles:
                sid += 1
                strategies.append(StrategyDef(
                    name=f"SR_{side}_{trig[3:]}_x_{ctx[2:14]}_{rrl}_{sid:05d}",
                    side=side, contexts=[ctx], trigger=trig,
                    context_window_bars=5,
                    stop_atr=stop_a, target_atr=tgt_a, max_hold_min=mh,
                ))
    return strategies


def make_sr_detector_dicts(F: pd.DataFrame, nq_5m: pd.DataFrame):
    ctx_series = sr_context_detectors(F)
    trig_series = build_sr_triggers(nq_5m)
    # ensure trigger Series share F's index
    trig_series = {k: v.reindex(F.index).fillna(False)
                   for k, v in trig_series.items()}

    def make_fn(s):
        return lambda F, _s=s: _s

    return ({k: make_fn(v) for k, v in ctx_series.items()},
            {k: make_fn(v) for k, v in trig_series.items()})


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s miner_sr %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_PATH)])
    print("=" * 78)
    print(f"PATTERN MINER SR — S/R level-fade family"
          f"{'  [SMOKE]' if SMOKE else ''}")
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
    print(f"  NQ 5m: {len(nq_5m):,} bars   NQ 1m: {len(nq_1m):,}")

    print("\n[2/4] Building v6 features (gauntlet needs atr14, time cols) ...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    print(f"  {F.shape}")

    print("\n[3/4] Enumerating S/R strategies ...")
    strats = enumerate_sr_strategies()
    if SMOKE:
        strats = strats[:6]
    print(f"  TOTAL: {len(strats)}")

    contexts_d, triggers_d = make_sr_detector_dicts(F, nq_5m)

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
                u_count = sum(1 for r in results if r.get("user_pass"))
                logger.info(
                    f"  [USER-PASS #{u_count}] {strat.name}  "
                    f"n={t['n']:>4} WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"cpcv={ev.get('cpcv_positive',0)}/5 pnl=${t['net']:+,.0f}"
                )
            elif (idx % 25) == 0:
                rate = (idx + 1 - len(progress.get("completed", []))) / max(
                    0.01, time.time() - started_at)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                u_pass = sum(1 for r in results if r.get("user_pass"))
                logger.info(
                    f"  [{idx+1:>5}/{len(strats)}] u_pass={u_pass}  ETA {eta:.0f}m")

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
                  f"$/c={t['net']:+,.0f}")

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

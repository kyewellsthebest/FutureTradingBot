"""
Pattern Miner v12 — overnight + Australian-daytime time slices.

Same engine as v11 but adds time contexts that map to Australian daytime
(roughly 9 AM - 5 PM AEST = 7 PM previous day - 3 AM ET in summer-EDT).

NQ trades almost 24h on Globex but liquidity is 5-10% of regular hours
overnight. So even strategies that pass backtest may underperform live
because of wider spreads. Same 5 rigorous tests as v11 (CPCV, permutation,
user-pass thresholds).

New time contexts (NY ET, on the same calendar day Globex session):
  t_1900_2000  7-8 PM ET     → AEST 9-10 AM next day
  t_2000_2100  8-9 PM ET     → AEST 10-11 AM
  t_2100_2200  9-10 PM ET    → AEST 11 AM-12 PM
  t_2200_2300  10-11 PM ET   → AEST 12-1 PM
  t_2300_2400  11 PM-12 AM   → AEST 1-2 PM
  t_0000_0100  12-1 AM ET    → AEST 2-3 PM
  t_0100_0200  1-2 AM ET     → AEST 3-4 PM
  t_0200_0300  2-3 AM ET     → AEST 4-5 PM
  evening_us   7-11 PM ET    → AEST 9 AM-1 PM (broad)
  overnight    11 PM-3 AM ET → AEST 1 AM-5 PM (broad)
  t_0300_0900  3-9 AM ET     → AEST 5-11 AM (Asia/Europe overlap)

Total: 8 windows × 7 thresholds × 11 time contexts × 5 RR × 2 sides = 6160 strategies.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, evaluate_strategy, StrategyDef, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import (
    USER_MIN_WR, USER_MIN_RR, USER_MIN_TRADES,
    build_v11_extras, v11_trigger_detectors,
)
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v12_patterns.json"
PROGRESS_PATH = DATA / "v12_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v12.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("miner_v12")


def v12_context_detectors(F: pd.DataFrame) -> dict[str, pd.Series]:
    """Time contexts targeting AEST daytime (NY overnight session)."""
    C = {}
    h = F["ny_hour"]
    m = F["ny_minute"]
    # 1-hour buckets through the overnight session
    C["t_1900_2000"] = (h == 19)
    C["t_2000_2100"] = (h == 20)
    C["t_2100_2200"] = (h == 21)
    C["t_2200_2300"] = (h == 22)
    C["t_2300_2400"] = (h == 23)
    C["t_0000_0100"] = (h == 0)
    C["t_0100_0200"] = (h == 1)
    C["t_0200_0300"] = (h == 2)
    # Broad sessions
    C["evening_us"] = (h >= 19) & (h <= 22)            # 7-11 PM ET
    C["overnight"]  = (h >= 23) | (h <= 2)             # 11 PM - 3 AM ET
    C["t_0300_0900"] = (h >= 3) & (h <= 8)             # 3-9 AM ET (Asia/Europe overlap)
    return {k: v.fillna(False) for k, v in C.items()}


def enumerate_v12_strategies(F: pd.DataFrame) -> list[StrategyDef]:
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

    SIDES_TRIGS = []
    for w in [10, 15, 20, 30, 45, 60, 90, 120]:
        for thr in [15, 17, 20, 22, 25, 27, 30]:
            SIDES_TRIGS.append((f"sa_long_{w}_{thr}",  "LONG"))
            SIDES_TRIGS.append((f"sa_short_{w}_{thr}", "SHORT"))

    TIME_CTXS = [
        "t_1900_2000", "t_2000_2100", "t_2100_2200", "t_2200_2300",
        "t_2300_2400", "t_0000_0100", "t_0100_0200", "t_0200_0300",
        "evening_us", "overnight", "t_0300_0900",
    ]

    for trig, side in SIDES_TRIGS:
        for ctx in TIME_CTXS:
            for stop_a, tgt_a, mh, rrl in rr_profiles:
                sid += 1
                name = f"V12SA_{side}_{trig[:14]}_x_{ctx[:14]}_{rrl}_{sid:05d}"
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


def make_v12_detector_dicts(F: pd.DataFrame):
    contexts_d_series = v12_context_detectors(F)
    triggers_d_series = v11_trigger_detectors(F)
    def make_fn(s):
        return lambda F, _s=s: _s
    contexts_d = {k: make_fn(v) for k, v in contexts_d_series.items()}
    triggers_d = {k: make_fn(v) for k, v in triggers_d_series.items()}
    return contexts_d, triggers_d


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v12 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v12 — overnight + Australian-daytime expansion")
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
    strats = enumerate_v12_strategies(F)
    print(f"  TOTAL: {len(strats)}")

    contexts_d, triggers_d = make_v12_detector_dicts(F)

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

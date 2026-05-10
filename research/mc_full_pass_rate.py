"""
Monte Carlo pass-rate analysis for the FULL v11+v12+v13 deployment set.

Loads every strategy in data/deployed_strategies.json (97 total: 59 LONG /
38 SHORT). For each strategy, re-runs label_strategy through the mining
engine to enumerate its trades over 2024-2026, then merges all trade-fires
chronologically and walks 100 random 180-day funded-account windows
under Lucid 50K rules + the $1K per-trade max-loss cap.

Reports:
  * Pass rate (% of accounts that survived 180 days without busting trail)
  * Average / median / max survivor profit
  * Time-to-bust distribution
  * EV per attempt
"""
from __future__ import annotations
import json
import logging
import random
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, StrategyDef, MNQ_DPP, COMM_PER,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import build_v11_extras, make_v11_detector_dicts
from research.pattern_miner_v12 import make_v12_detector_dicts
from research.pattern_miner_v13 import build_v13_extras, make_v13_detector_dicts
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
logger = logging.getLogger("mc_full")

INITIAL_BALANCE = 50000.0
INITIAL_TRAIL = 48000.0
DLL = 1200.0
TRAIL_DROP = 2000.0
TRAIL_LOCK_AT = 51000.0
TRAIL_LOCKED_FLOOR = 50000.0
BASE_SIZE = 25
MAX_LOSS_PER_TRADE = 1000.0
COOLDOWN_BARS = 5
FEE_PER_ATTEMPT = 165.0


def adaptive_qty_factor(buffer: float) -> float:
    if buffer < 200:    return 0.0
    if buffer < 500:    return 0.20
    if buffer < 1000:   return 0.40
    if buffer < 2000:   return 0.60
    if buffer < 4000:   return 0.85
    return 1.0


def cap_qty_by_max_loss(qty: int, stop_pts: float) -> int:
    if stop_pts <= 0:  return qty
    per_contract_loss = (stop_pts + 1.0) * 2.0
    max_qty = int(MAX_LOSS_PER_TRADE / per_contract_loss)
    return min(qty, max(1, max_qty))


def load_deployed_strategy_specs() -> list[dict]:
    """Load deployed strategy names + look up their full specs in mining JSONs."""
    deployed = set(json.loads((DATA / "deployed_strategies.json").read_text()).get("names", []))
    out = []
    for fname in ["mined_v11_patterns.json", "mined_v12_patterns.json", "mined_v13_patterns.json"]:
        p = DATA / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for s in d.get("user_passers", []):
            if s["name"] in deployed:
                out.append(s)
    return out


def build_signal_universe(strategies, F, nq_5m, nq_1m, daily,
                            contexts_d, triggers_d) -> pd.DataFrame:
    all_sigs = []
    for i, s in enumerate(strategies):
        if i % 10 == 0:
            logger.info(f"  labeling {i+1}/{len(strategies)}...")
        strat = StrategyDef(
            name=s["name"], side=s["side"], contexts=s["contexts"],
            trigger=s["trigger"], context_window_bars=5,
            stop_atr=s["stop_atr"], target_atr=s["target_atr"],
            max_hold_min=s["max_hold_min"],
        )
        try:
            tr = label_strategy(F, nq_5m, nq_1m, daily, strat, contexts_d, triggers_d)
        except Exception as e:
            logger.warning(f"  {s['name']} skipped: {e}")
            continue
        if tr.empty:
            continue
        tr = tr.copy()
        tr["name"] = s["name"]; tr["side"] = s["side"]
        tr["max_hold_min"] = s["max_hold_min"]
        ets = pd.to_datetime(tr["entry_ts"])
        if ets.dt.tz is None:
            ets = ets.dt.tz_localize("UTC")
        tr["entry_ts"] = ets
        all_sigs.append(tr)
    if not all_sigs:
        return pd.DataFrame()
    return pd.concat(all_sigs, ignore_index=True).sort_values("entry_ts").reset_index(drop=True)


def run_one(sigs: pd.DataFrame, start_ts, end_ts, base_size: int = BASE_SIZE):
    balance = INITIAL_BALANCE
    trail = INITIAL_TRAIL
    daily_pnl = 0.0
    current_session = None
    last_exit_ts = None
    cooldown_until = None
    halted = False
    halt_ts = None
    n_trades = n_wins = 0
    window = sigs[(sigs["entry_ts"] >= start_ts) & (sigs["entry_ts"] <= end_ts)]
    for _, sig in window.iterrows():
        if halted: break
        sig_ts = sig["entry_ts"]
        sess = sig_ts.tz_convert("America/New_York").date()
        if current_session != str(sess):
            current_session = str(sess); daily_pnl = 0.0
        if last_exit_ts is not None and sig_ts < last_exit_ts: continue
        if cooldown_until is not None and sig_ts < cooldown_until: continue
        if daily_pnl <= -DLL: continue
        buffer = balance - trail
        factor = adaptive_qty_factor(buffer)
        qty = max(1, int(base_size * factor)) if factor > 0 else 0
        if qty == 0: continue
        # Apply $1K max-loss cap
        stop_pts = float(sig.get("stop_pts", 0))
        if stop_pts > 0:
            qty = cap_qty_by_max_loss(qty, stop_pts)
        max_hold = int(sig.get("max_hold_min", 75))
        pts = float(sig.get("pts", 0))
        pnl = pts * MNQ_DPP * qty - COMM_PER * 2 * qty
        if daily_pnl + pnl < -DLL:
            pnl = -DLL - daily_pnl
        balance += pnl
        daily_pnl += pnl
        if balance >= TRAIL_LOCK_AT:
            trail = max(trail, TRAIL_LOCKED_FLOOR)
        else:
            trail = max(trail, balance - TRAIL_DROP)
        last_exit_ts = sig_ts + pd.Timedelta(minutes=max_hold)
        if pnl < 0:
            cooldown_until = last_exit_ts + pd.Timedelta(minutes=25)
        if balance < trail:
            halted = True; halt_ts = sig_ts
        n_trades += 1
        if pnl > 0: n_wins += 1
    return {"halted": halted, "halt_ts": halt_ts, "balance": balance,
              "profit": balance - INITIAL_BALANCE, "n_trades": n_trades, "n_wins": n_wins}


def main():
    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(message)s",
                          handlers=[logging.StreamHandler(sys.stdout)])
    logger.info("Loading data + features...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = load_intraday_5min("rty")
    vix_5m = load_vix_5min()
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    F = build_v13_extras(F, nq_5m, rty_5m, vix_5m)

    contexts_d_v11, triggers_d_v11 = make_v11_detector_dicts(F)
    contexts_d_v12, _ = make_v12_detector_dicts(F)
    contexts_d_v13, triggers_d_v13 = make_v13_detector_dicts(F)
    contexts_d = {**contexts_d_v11, **contexts_d_v12, **contexts_d_v13}
    triggers_d = {**triggers_d_v11, **triggers_d_v13}

    deployed = load_deployed_strategy_specs()
    logger.info(f"Loaded {len(deployed)} deployed strategies")

    sigs = build_signal_universe(deployed, F, nq_5m, nq_1m, daily,
                                     contexts_d, triggers_d)
    logger.info(f"Generated {len(sigs)} candidate signals")
    if sigs.empty:
        logger.error("No signals; aborting"); return

    rng = random.Random(7)
    start_pool = pd.date_range("2025-01-01", "2025-06-30", freq="3D", tz="UTC")
    trials = []
    bust_days = []
    for i in range(100):
        sd = start_pool[rng.randint(0, len(start_pool)-1)]
        ed = sd + pd.Timedelta(days=180)
        r = run_one(sigs, sd, ed)
        trials.append(r)
        if r["halted"] and r["halt_ts"] is not None:
            bust_days.append((r["halt_ts"] - sd).total_seconds() / 86400)

    n_passed = sum(1 for r in trials if not r["halted"])
    survivors = [r for r in trials if not r["halted"]]
    pass_rate = n_passed / 100
    avg_p = np.mean([r["profit"] for r in survivors]) if survivors else 0
    med_p = np.median([r["profit"] for r in survivors]) if survivors else 0
    max_p = max([r["profit"] for r in survivors]) if survivors else 0
    avg_bust = np.mean(bust_days) if bust_days else 0
    med_bust = np.median(bust_days) if bust_days else 0
    ev = pass_rate * avg_p - (1 - pass_rate) * FEE_PER_ATTEMPT
    avg_n_trades = np.mean([r["n_trades"] for r in trials])
    avg_n_trades_survivors = np.mean([r["n_trades"] for r in survivors]) if survivors else 0

    out = {
        "n_strategies": len(deployed),
        "n_signals": len(sigs),
        "pass_rate": float(pass_rate),
        "avg_survivor_profit": float(avg_p),
        "median_survivor_profit": float(med_p),
        "max_survivor_profit": float(max_p),
        "avg_bust_days": float(avg_bust),
        "median_bust_days": float(med_bust),
        "avg_trades_per_180d_run": float(avg_n_trades),
        "avg_trades_survivors": float(avg_n_trades_survivors),
        "ev_per_attempt": float(ev),
    }
    (DATA / "mc_full_results.json").write_text(json.dumps(out, indent=2))

    print("\n" + "="*70)
    print("MONTE CARLO — Full v11+v12+v13 deployment @ 50K Lucid / 25 MNQ")
    print(f"  $1K per-trade max-loss cap ACTIVE")
    print("="*70)
    print(f"  Strategies trading: {len(deployed)}")
    print(f"  Total candidate signals: {len(sigs):,}")
    print(f"  Pass rate (100 trials, 180-day each): {pass_rate*100:.0f}%")
    print(f"  Median survivor profit: ${med_p:,.0f}")
    print(f"  Average survivor profit: ${avg_p:,.0f}")
    print(f"  Max survivor profit: ${max_p:,.0f}")
    print(f"  Avg trades / 180-day run: {avg_n_trades:.0f}")
    print(f"  Median time to bust (when failed): {med_bust:.1f} days")
    print(f"  EV per attempt (after $165 fee): ${ev:,.0f}")


if __name__ == "__main__":
    main()

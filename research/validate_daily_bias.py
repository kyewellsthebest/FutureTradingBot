"""
Re-validate the 97 deployed strategies through the live-sim Monte Carlo
WITH the daily-bias filter — and compare against bias-off.

The filter: before taking any trade, compute the daily bias (Smart-Money
top-down analysis from research/daily_bias.py). If the daily bias
recommends LONG, only LONG strategies fire that day; if SHORT, only
SHORT; if BOTH, no filtering.

Runs the same 100-trial 180-day Monte Carlo as mc_full_pass_rate.py,
twice — bias OFF and bias ON — and prints the side-by-side comparison.
"""
from __future__ import annotations
import json
import logging
import random
import sys
from pathlib import Path

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
from research.daily_bias import compute_daily_bias
from research.mc_full_pass_rate import (
    INITIAL_BALANCE, INITIAL_TRAIL, DLL, TRAIL_DROP, TRAIL_LOCK_AT,
    TRAIL_LOCKED_FLOOR, BASE_SIZE, MAX_LOSS_PER_TRADE, TRAIL_SAFETY_MARGIN,
    FEE_PER_ATTEMPT, adaptive_qty_factor, cap_qty_by_max_loss,
    load_deployed_strategy_specs, build_signal_universe,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
logger = logging.getLogger("validate_bias")


def run_one(sigs: pd.DataFrame, start_ts, end_ts, bias_by_date: dict | None):
    """One 180-day funded-account run. If bias_by_date is given, skip trades
    whose side conflicts with that day's daily bias."""
    balance = INITIAL_BALANCE
    trail = INITIAL_TRAIL
    daily_pnl = 0.0
    current_session = None
    last_exit_ts = None
    cooldown_until = None
    halted = False
    n_trades = n_wins = n_bias_skipped = 0
    window = sigs[(sigs["entry_ts"] >= start_ts) & (sigs["entry_ts"] <= end_ts)]
    for _, sig in window.iterrows():
        if halted:
            break
        sig_ts = sig["entry_ts"]
        sess = sig_ts.tz_convert("America/New_York").date()
        if current_session != str(sess):
            current_session = str(sess); daily_pnl = 0.0
        if last_exit_ts is not None and sig_ts < last_exit_ts:
            continue
        if cooldown_until is not None and sig_ts < cooldown_until:
            continue
        if daily_pnl <= -DLL:
            continue

        # ---- daily-bias filter ----------------------------------------
        if bias_by_date is not None:
            rec = bias_by_date.get(str(sess), "BOTH")
            side = sig["side"]
            if rec == "LONG" and side == "SHORT":
                n_bias_skipped += 1
                continue
            if rec == "SHORT" and side == "LONG":
                n_bias_skipped += 1
                continue

        buffer = balance - trail
        factor = adaptive_qty_factor(buffer)
        qty = max(1, int(BASE_SIZE * factor)) if factor > 0 else 0
        if qty == 0:
            continue
        stop_pts = float(sig.get("stop_pts", 0))
        if stop_pts > 0:
            qty = cap_qty_by_max_loss(qty, stop_pts)
        worst_loss = stop_pts * MNQ_DPP * qty + COMM_PER * 2 * qty
        if balance - worst_loss <= trail + TRAIL_SAFETY_MARGIN:
            continue
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
            halted = True
        n_trades += 1
        if pnl > 0:
            n_wins += 1
    return {"halted": halted, "balance": balance, "profit": balance - INITIAL_BALANCE,
              "n_trades": n_trades, "n_wins": n_wins, "n_bias_skipped": n_bias_skipped}


def monte_carlo(sigs, bias_by_date, n=100):
    rng = random.Random(7)
    pool = pd.date_range("2025-01-01", "2025-06-30", freq="3D", tz="UTC")
    trials = []
    for _ in range(n):
        sd = pool[rng.randint(0, len(pool) - 1)]
        ed = sd + pd.Timedelta(days=180)
        trials.append(run_one(sigs, sd, ed, bias_by_date))
    n_pass = sum(1 for r in trials if not r["halted"])
    survs = [r for r in trials if not r["halted"]]
    profits = [r["profit"] for r in survs]
    wr_all = ([r["n_wins"] / r["n_trades"] for r in trials if r["n_trades"] > 0])
    return {
        "pass_rate": n_pass / n,
        "avg_profit": float(np.mean(profits)) if profits else 0.0,
        "median_profit": float(np.median(profits)) if profits else 0.0,
        "avg_trades": float(np.mean([r["n_trades"] for r in trials])),
        "avg_wr": float(np.mean(wr_all)) if wr_all else 0.0,
        "ev": (n_pass / n) * (float(np.mean(profits)) if profits else 0.0)
                - (1 - n_pass / n) * FEE_PER_ATTEMPT,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
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
    cd11, td11 = make_v11_detector_dicts(F)
    cd12, _ = make_v12_detector_dicts(F)
    cd13, td13 = make_v13_detector_dicts(F)
    contexts_d = {**cd11, **cd12, **cd13}
    triggers_d = {**td11, **td13}

    deployed = load_deployed_strategy_specs()
    logger.info(f"Loaded {len(deployed)} deployed strategies")
    sigs = build_signal_universe(deployed, F, nq_5m, nq_1m, daily,
                                     contexts_d, triggers_d)
    logger.info(f"Generated {len(sigs)} candidate signals")

    # Precompute daily bias for every NY date in the test span
    logger.info("Computing daily bias for every trading day...")
    bias_by_date = {}
    span = pd.date_range("2024-12-01", "2026-01-15", freq="D")
    for d in span:
        b = compute_daily_bias(daily, d)
        bias_by_date[str(d.date())] = b.recommended_side
    from collections import Counter
    logger.info(f"Daily bias distribution: {dict(Counter(bias_by_date.values()))}")

    logger.info("Running Monte Carlo — bias OFF...")
    off = monte_carlo(sigs, None)
    logger.info("Running Monte Carlo — bias ON...")
    on = monte_carlo(sigs, bias_by_date)

    (DATA / "validate_daily_bias.json").write_text(
        json.dumps({"bias_off": off, "bias_on": on}, indent=2))

    print("\n" + "=" * 70)
    print("DAILY-BIAS FILTER — validation (100 trials, 180-day, 50K Lucid)")
    print("=" * 70)
    print(f"{'Metric':<26}{'Bias OFF':>20}{'Bias ON':>20}")
    print("-" * 66)
    def row(label, k, fmt):
        print(f"{label:<26}{fmt(off[k]):>20}{fmt(on[k]):>20}")
    row("Pass rate",        "pass_rate",      lambda x: f"{x*100:.0f}%")
    row("Avg survivor profit","avg_profit",   lambda x: f"${x:,.0f}")
    row("Median profit",    "median_profit",  lambda x: f"${x:,.0f}")
    row("Avg win rate",     "avg_wr",         lambda x: f"{x*100:.1f}%")
    row("Avg trades/run",   "avg_trades",     lambda x: f"{x:.0f}")
    row("EV per attempt",   "ev",             lambda x: f"${x:,.0f}")


if __name__ == "__main__":
    main()

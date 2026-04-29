"""
True out-of-sample walk-forward validation.

The portfolio_selector picked 38 patterns that worked across 8 years of
data. But the test windows OVERLAP the selection data — that's look-ahead
bias. A pattern can survive multi-window stability simply because the
selector knew the future.

This script does the honest test:
    1. Take all 210 originally-validated patterns
    2. Use ONLY 2018-01 → 2023-12 for portfolio selection (training window)
    3. Lock the resulting whitelist
    4. Apply it to 2024-01 → 2026-04 (out-of-sample = the bot's real future)
    5. Report grid + scenarios

If the OOS performance matches in-sample, the strategy generalizes.
If OOS is much worse, the selector overfit.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

CACHE_PATH = DATA_DIR / "scenarios_trades_cache.json"
VAL_PATH = DATA_DIR / "validation_results.json"
LOG_PATH = DATA_DIR / "walk_forward_validation.json"

# Train/test split
TRAIN_END = pd.Timestamp("2023-12-31", tz="UTC")
TEST_START = pd.Timestamp("2024-01-01", tz="UTC")


def _gate(trades_sorted: list[dict], excluded: set[str] | None = None) -> list[dict]:
    excluded = excluded or set()
    open_until = pd.Timestamp.min.tz_localize("UTC")
    today = None
    n_today = 0
    taken = []
    for t in trades_sorted:
        if t["name"] in excluded:
            continue
        ts = t["ts"]
        if today != ts.date():
            today = ts.date()
            n_today = 0
        if n_today >= 8 or ts < open_until:
            continue
        taken.append(t)
        lockout = t["max_hold"] * (5 if t["tf"] == "5m" else 1)
        open_until = ts + pd.Timedelta(minutes=lockout)
        n_today += 1
    return taken


def _pnl(taken: list[dict]) -> tuple[float, dict[str, float], int]:
    total = 0.0
    per_strat: dict[str, float] = defaultdict(float)
    n_wins = 0
    for t in taken:
        contracts = 5 if t["tf"] == "1m" else 30
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl = t["pts"] * dpp - comm
        total += pnl
        per_strat[t["name"]] += pnl
        if t["pts"] > 0: n_wins += 1
    return total, dict(per_strat), n_wins


def _greedy_select(train_trades: list[dict], all_names: set[str]) -> tuple[set[str], list[dict]]:
    """Iteratively drop patterns that hurt combined P&L on training data."""
    active = set(all_names)
    drop_log = []
    for it in range(1, 11):
        excl = all_names - active
        taken = _gate(train_trades, excluded=excl)
        pnl, per_strat, _ = _pnl(taken)
        # "loser" = fired AND lost; "unfired" = never won a slot
        losers = [p for p in active if p in per_strat and per_strat[p] <= 0]
        unfired = [p for p in active if p not in per_strat]
        for p in losers:
            drop_log.append({"iter": it, "name": p, "reason": "neg_in_combined", "pnl": per_strat[p]})
            active.discard(p)
        for p in unfired:
            drop_log.append({"iter": it, "name": p, "reason": "never_fired_in_gate"})
            active.discard(p)
        print(f"    iter {it}: train P&L=${pnl:+,.0f}  dropped {len(losers)+len(unfired)}  → {len(active)}")
        if not losers and not unfired:
            break
    return active, drop_log


def _multi_window_filter(active: set[str], train_trades: list[dict], n_windows: int = 12) -> set[str]:
    """Drop patterns not positive in ≥75% of training windows."""
    if not train_trades:
        return active
    t0 = train_trades[0]["ts"]
    t1 = train_trades[-1]["ts"]
    span = (t1 - t0) / n_windows
    per_strat_by_window: dict[str, list[float]] = defaultdict(list)
    for wi in range(n_windows):
        wstart = t0 + span * wi
        wend = t0 + span * (wi + 1)
        wt = [t for t in train_trades if wstart <= t["ts"] < wend]
        excl = (set(t["name"] for t in train_trades) - active)
        wtaken = _gate(wt, excluded=excl)
        _, wps, _ = _pnl(wtaken)
        for p in active:
            per_strat_by_window[p].append(wps.get(p, 0.0))

    stable = set()
    for p in active:
        active_w = [v for v in per_strat_by_window[p] if abs(v) > 0.01]
        if not active_w:
            continue
        n_pos = sum(1 for v in active_w if v > 0)
        if n_pos / len(active_w) >= 0.75:
            stable.add(p)
    return stable


def main() -> int:
    print("=" * 80)
    print("WALK-FORWARD VALIDATION  —  out-of-sample test")
    print(f"  Train:  2018-02 → {TRAIN_END.date()}")
    print(f"  Test:   {TEST_START.date()} → 2026-04 (UNSEEN by selector)")
    print("=" * 80)

    print(f"\n[1/4] Loading cached trades + initial whitelist ...", flush=True)
    cache = json.loads(CACHE_PATH.read_text())
    val = json.loads(VAL_PATH.read_text())
    sigs = val["signals"]
    # Use ALL 210 originally-validated patterns (Tier A + Tier B)
    initial = {n for n, s in sigs.items() if s.get("tier") in ("A", "B")}
    print(f"  {len(cache['trades']):,} cached signals, {len(initial)} initial whitelist")

    trades = []
    for t in cache["trades"]:
        if t["name"] in initial:
            t["ts"] = pd.Timestamp(t["ts"])
            trades.append(t)
    trades.sort(key=lambda t: t["ts"])

    train_trades = [t for t in trades if t["ts"] <= TRAIN_END]
    test_trades = [t for t in trades if t["ts"] >= TEST_START]
    print(f"  train: {len(train_trades):,} signals     test: {len(test_trades):,} signals")
    print(f"  train span: {train_trades[0]['ts'].date()} → {train_trades[-1]['ts'].date()}")
    print(f"  test span:  {test_trades[0]['ts'].date()} → {test_trades[-1]['ts'].date()}")

    # ---- 2. Greedy selection on TRAIN only ----
    print(f"\n[2/4] Greedy iterative selection on TRAIN window ...")
    active, drop_log = _greedy_select(train_trades, initial)
    print(f"  After greedy: {len(active)} patterns")

    # ---- 3. Multi-window stability on TRAIN only ----
    print(f"\n[3/4] Multi-window stability filter on TRAIN window (12 windows) ...")
    stable = _multi_window_filter(active, train_trades, n_windows=12)
    print(f"  Stable: {len(stable)} patterns survive")

    # ---- 4. Apply LOCKED whitelist to TEST window ----
    print(f"\n[4/4] OUT-OF-SAMPLE TEST — apply locked whitelist to UNSEEN test data")
    test_excl = initial - stable
    test_taken = _gate(test_trades, excluded=test_excl)
    test_pnl, test_per_strat, test_wins = _pnl(test_taken)
    test_wr = test_wins / max(1, len(test_taken))
    print(f"  TEST P&L: ${test_pnl:+,.0f}   trades={len(test_taken):,}   WR={test_wr*100:.1f}%")

    # Compare to TRAIN P&L on same locked whitelist
    train_taken = _gate(train_trades, excluded=test_excl)
    train_pnl, _, train_wins = _pnl(train_taken)
    train_wr = train_wins / max(1, len(train_taken))
    train_yrs = (train_trades[-1]["ts"] - train_trades[0]["ts"]).days / 365.25
    test_yrs = (test_trades[-1]["ts"] - test_trades[0]["ts"]).days / 365.25
    print(f"  TRAIN P&L:    ${train_pnl:+,.0f}   trades={len(train_taken):,}   WR={train_wr*100:.1f}%")
    print(f"  TRAIN $/yr:   ${train_pnl/train_yrs:+,.0f}/yr  ({train_yrs:.1f} yrs)")
    print(f"  TEST  $/yr:   ${test_pnl/test_yrs:+,.0f}/yr   ({test_yrs:.1f} yrs)")
    degrade_pct = (1 - (test_pnl/test_yrs) / (train_pnl/train_yrs)) * 100 if train_pnl > 0 else 100.0
    print(f"  OOS degradation: {degrade_pct:+.1f}%  (positive = test worse than train)")

    # Per-month grid on TEST set
    by_month: dict[tuple[int,int], float] = defaultdict(float)
    for t, pnl in zip(test_taken, [_pnl([t])[0] for t in test_taken]):
        ym = (t["ts"].year, t["ts"].month)
        by_month[ym] += pnl
    monthly = sorted(by_month.items())
    print(f"\n  TEST monthly P&L (locked whitelist, every trade taken):")
    print(f"    {'month':<10} {'P&L':>12}")
    cum = 50000.0
    for (y, m), p in monthly:
        cum += p
        print(f"    {y}-{m:02d}    ${p:>+10,.0f}    bal=${cum:>10,.0f}")

    # Update validation_results to use the WALK-FORWARD whitelist
    for n, info in sigs.items():
        if n in stable:
            info["recommended"] = True
            info["selection_method"] = "walk_forward_OOS_2024_2026"
            info.pop("dropped_reason", None)
        elif n in initial:
            info["recommended"] = False
            info["dropped_reason"] = "failed_walk_forward_train_2018_2023"
    val["last_updated"] = datetime.now(timezone.utc).isoformat()
    VAL_PATH.write_text(json.dumps(val, indent=2, default=str))
    print(f"\n  Updated -> data/validation_results.json   ({len(stable)} active)")

    LOG_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "train_end": TRAIN_END.isoformat(),
        "test_start": TEST_START.isoformat(),
        "n_initial": len(initial),
        "n_after_greedy": len(active),
        "n_final_stable": len(stable),
        "train_pnl": train_pnl,
        "train_pnl_per_year": train_pnl / train_yrs,
        "test_pnl": test_pnl,
        "test_pnl_per_year": test_pnl / test_yrs,
        "test_trades": len(test_taken),
        "test_wr": test_wr,
        "oos_degradation_pct": degrade_pct,
        "test_monthly": [
            {"month": f"{y}-{m:02d}", "pnl": p} for (y, m), p in monthly
        ],
        "final_whitelist": sorted(stable),
    }, indent=2, default=str))
    print(f"  Wrote -> data/walk_forward_validation.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

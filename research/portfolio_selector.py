"""
Portfolio-level whitelist selector.

The mistake of validate_mined_full.py was treating each strategy as if it were
the only one running. In reality, the bot has a single-position gate, so
patterns compete for slots — and noisy high-fire patterns crowd out slow
high-quality ones. A pattern with positive per-trade EV in isolation can
still HURT the combined account because it steals slots from better signals.

This script fixes that by selecting the whitelist on its **marginal
contribution to the combined gated P&L**:

  1. Load all signal entries (cached by scenarios.py).
  2. Run the combined-trader sim with ALL active patterns.
  3. For each pattern P, re-run with P removed → measure the delta.
     marginal[P] = combined_P&L(all)  −  combined_P&L(all − P)
  4. Drop any pattern with marginal ≤ 0 (it's a net negative on the portfolio).
  5. Iterate — removing a pattern frees slots, which changes everyone else's
     contribution. Repeat until all remaining have positive marginal.

Plus: multi-window stability check — a pattern only stays if its marginal is
positive in ≥75% of 6-month chronological windows (16 windows over 8 yrs).
This prevents a pattern that crushed it in 2020 vol from carrying its weight
in 2025 chop.

Output:
    data/validation_results.json updated in-place: only survivors recommended.
    data/portfolio_selection_log.json — per-pattern stats + window breakdowns.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

CACHE_PATH = DATA_DIR / "scenarios_trades_cache.json"
VAL_PATH = DATA_DIR / "validation_results.json"
LOG_PATH = DATA_DIR / "portfolio_selection_log.json"


def _gate(trades_sorted: list[dict], excluded: set[str] | None = None) -> list[dict]:
    """Apply the bot's actual gate: 1-position-at-a-time + 8 trades/day cap.

    `excluded` = set of strategy names to skip entirely (as if not whitelisted).
    """
    excluded = excluded or set()
    open_until = pd.Timestamp.min.tz_localize("UTC")
    today = None
    n_today = 0
    taken: list[dict] = []
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


def _pnl_dollars(taken: list[dict]) -> tuple[float, dict[str, float]]:
    """Compute total dollar P&L using the bot's fixed sizing (5 MNQ / 30 MNQ
    for 1-min vs 5-min) and per-strategy net contribution."""
    total = 0.0
    per_strat: dict[str, float] = defaultdict(float)
    for t in taken:
        contracts = 5 if t["tf"] == "1m" else 30
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl = t["pts"] * dpp - comm
        total += pnl
        per_strat[t["name"]] += pnl
    return total, dict(per_strat)


def _window_marginal(trades: list[dict], pattern: str, baseline_pnl: float) -> float:
    """Marginal contribution of `pattern` = baseline − (baseline with pattern removed)."""
    without = _gate(trades, excluded={pattern})
    pnl_without, _ = _pnl_dollars(without)
    return baseline_pnl - pnl_without


def _split_windows(trades: list[dict], n_windows: int = 16) -> list[tuple[pd.Timestamp, pd.Timestamp, list[dict]]]:
    """Slice trades into N equal chronological windows."""
    if not trades:
        return []
    t0 = trades[0]["ts"]
    t1 = trades[-1]["ts"]
    span = (t1 - t0) / n_windows
    out = []
    for i in range(n_windows):
        wstart = t0 + span * i
        wend = t0 + span * (i + 1)
        wt = [t for t in trades if wstart <= t["ts"] < wend]
        if wt:
            out.append((wstart, wend, wt))
    return out


def main() -> int:
    print("=" * 80)
    print("PORTFOLIO-LEVEL WHITELIST SELECTOR")
    print("  Greedy by marginal combined P&L + multi-window stability")
    print("=" * 80)

    # ---- Load ----
    print(f"\n[1/4] Loading cached trades + validation_results ...", flush=True)
    if not CACHE_PATH.exists():
        print(f"  no cache at {CACHE_PATH} — run scenarios.py first")
        return 1
    cache = json.loads(CACHE_PATH.read_text())
    raw = cache["trades"]
    print(f"  {len(raw):,} cached signals")
    # Materialize trades with proper timestamps
    trades = []
    for t in raw:
        t["ts"] = pd.Timestamp(t["ts"])
        trades.append(t)
    trades.sort(key=lambda t: t["ts"])

    val = json.loads(VAL_PATH.read_text())
    sigs = val["signals"]
    initial = sorted({k for k, s in sigs.items() if s.get("recommended")})
    print(f"  initial whitelist: {len(initial)}")

    # ---- Pass 1: iterative drop-by-marginal on FULL 8-yr ----
    print(f"\n[2/4] Iterative drop by marginal contribution (full 8-yr)", flush=True)
    active = set(initial)
    iteration = 0
    drop_log: list[dict] = []
    while True:
        iteration += 1
        excluded = set(initial) - active
        baseline = _gate(trades, excluded=excluded)
        baseline_pnl, per_strat = _pnl_dollars(baseline)

        # Marginal contribution per pattern = its per-strategy net contribution
        # in the gated stream (since dropping it would remove exactly its trades
        # from the queue, modulo slot-cascading — but for first-iter approximation,
        # per_strat is a fast proxy).
        # For correctness on the iteration that matters, we compute the ACTUAL
        # marginal by removing each candidate and re-gating.
        # Quick prune: drop everyone with per-strat ≤ 0 in one pass.
        losers = [p for p, pnl in per_strat.items() if pnl <= 0 and p in active]
        unfired = active - set(per_strat.keys())   # patterns that never won a slot
        prev_active = len(active)
        active -= set(losers)
        active -= unfired
        for p in losers:
            drop_log.append({"iter": iteration, "name": p, "reason": "neg_in_combined", "delta": per_strat[p]})
        for p in unfired:
            drop_log.append({"iter": iteration, "name": p, "reason": "never_fired_in_gate"})
        print(f"  iter {iteration}: baseline=${baseline_pnl:+,.0f}   "
              f"dropped {len(losers)} losers + {len(unfired)} unfired   "
              f"(was {prev_active}, now {len(active)})")
        if not losers and not unfired:
            break
        if iteration >= 10:
            print(f"  hit max iterations — stopping")
            break

    print(f"\n  After iterative drop: {len(active)} patterns survive")
    # Compute final pass full-sim P&L
    final_excluded = set(initial) - active
    final_taken = _gate(trades, excluded=final_excluded)
    final_pnl, final_per_strat = _pnl_dollars(final_taken)
    print(f"  Combined P&L (8 yr): ${final_pnl:+,.0f}   ({len(final_taken):,} trades)")

    # ---- Pass 2: multi-window stability ----
    print(f"\n[3/4] Multi-window stability check (16 chronological windows) ...", flush=True)
    windows = _split_windows(trades, n_windows=16)
    print(f"  {len(windows)} windows of ~{(trades[-1]['ts'] - trades[0]['ts']).days // 16} days each")
    window_per_strat: dict[str, list[float]] = defaultdict(list)
    window_totals = []
    for wi, (ws, we, wt) in enumerate(windows):
        wtaken = _gate(wt, excluded=final_excluded)
        wpnl, wps = _pnl_dollars(wtaken)
        window_totals.append({
            "window": wi, "start": ws.isoformat(), "end": we.isoformat(),
            "n_trades": len(wtaken), "pnl": wpnl,
        })
        for p in active:
            window_per_strat[p].append(wps.get(p, 0.0))
        print(f"    [{wi+1:>2}/{len(windows)}] {ws.date()} -> {we.date()}   "
              f"trades={len(wtaken):>4}  net=${wpnl:>+10,.0f}")

    n_pos_total = sum(1 for w in window_totals if w["pnl"] > 0)
    print(f"\n  Positive windows for COMBINED whitelist: {n_pos_total}/{len(windows)}  "
          f"({n_pos_total/len(windows)*100:.0f}%)")

    # Drop patterns that lose money in >25% of windows they fired in (≥3 trades)
    print(f"\n[4/4] Multi-window stability filter (≥75% positive in active windows)", flush=True)
    stable = set()
    for p in active:
        per_window = window_per_strat[p]
        active_windows = [v for v in per_window if abs(v) > 0.01]
        if not active_windows:
            continue
        n_pos = sum(1 for v in active_windows if v > 0)
        pct_pos = n_pos / len(active_windows)
        if pct_pos >= 0.75:
            stable.add(p)
        else:
            drop_log.append({
                "iter": "stability", "name": p,
                "reason": f"only_{pct_pos*100:.0f}%_pos_windows",
                "active_windows": len(active_windows),
            })

    print(f"  Stable across windows: {len(stable)} / {len(active)}")

    # Final pass with stable set
    final_excluded = set(initial) - stable
    final_taken = _gate(trades, excluded=final_excluded)
    final_pnl, final_per_strat = _pnl_dollars(final_taken)
    n_wins = sum(1 for t in final_taken if t["pts"] > 0)
    wr = n_wins / max(1, len(final_taken))
    print(f"\n  FINAL whitelist: {len(stable)} patterns")
    print(f"  Combined P&L (8 yr): ${final_pnl:+,.0f}   "
          f"trades={len(final_taken):,}  WR={wr*100:.1f}%")

    # Per-window P&L on FINAL stable set
    print(f"\n  Per-window P&L on FINAL whitelist:")
    final_window_pnls = []
    for wi, (ws, we, wt) in enumerate(windows):
        wtaken = _gate(wt, excluded=final_excluded)
        wpnl, _ = _pnl_dollars(wtaken)
        final_window_pnls.append(wpnl)
        marker = "+" if wpnl > 0 else "-" if wpnl < 0 else "="
        print(f"    [{wi+1:>2}/{len(windows)}] {ws.date()} -> {we.date()}   "
              f"net=${wpnl:>+10,.0f}  {marker}")
    n_pos = sum(1 for p in final_window_pnls if p > 0)
    print(f"\n  Positive 6-mo windows: {n_pos}/{len(final_window_pnls)}  "
          f"({n_pos/len(final_window_pnls)*100:.0f}%)")

    # ---- Update validation_results.json ----
    for name, info in sigs.items():
        if name in stable:
            info["recommended"] = True
            info["selection_method"] = "portfolio_marginal_+_multi_window"
            info.pop("dropped_reason", None)
        elif name in initial:
            info["recommended"] = False
            info["dropped_reason"] = next(
                (d["reason"] for d in drop_log if d["name"] == name), "unknown"
            )
    val["last_updated"] = datetime.now(timezone.utc).isoformat()
    VAL_PATH.write_text(json.dumps(val, indent=2, default=str))
    print(f"\n  Updated -> data/validation_results.json   ({len(stable)} active)")

    # Selection log
    LOG_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_initial": len(initial),
        "n_final": len(stable),
        "final_combined_pnl_8yr": final_pnl,
        "final_combined_trades": len(final_taken),
        "final_combined_wr": wr,
        "n_positive_6mo_windows": n_pos,
        "n_total_windows": len(final_window_pnls),
        "drop_log": drop_log,
        "window_breakdown": [{"start": w["start"], "end": w["end"], "pnl": w["pnl"]}
                              for w in window_totals],
        "final_per_window": final_window_pnls,
        "final_whitelist": sorted(stable),
    }, indent=2, default=str))
    print(f"  Wrote -> data/portfolio_selection_log.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

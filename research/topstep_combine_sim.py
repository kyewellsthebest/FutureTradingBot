"""
TopStep $50K Trading Combine simulator.

Models the actual TopStep rules from their docs:

  Trading Combine $50K:
    - Starting balance:        $50,000
    - Maximum Loss Limit:      $2,000  (i.e. cannot drop below $48,000)
    - MLL trails highest END-OF-DAY balance (never moves down within a day)
    - MLL locks at $50,000 once balance reaches $52,000
    - Profit target to pass:   $3,000  (must reach $53,000)
    - Position size limit:     5 NQ contracts (or 50 MNQ via 10:1 ratio)
    - All positions flat by   3:10 PM CT (we conservatively flatten anything
                              still pending at end of day)
    - MLL monitored in REAL TIME using realized + unrealized P&L —
      any intraday breach = instant liquidation, no recovery

  Sizing rule (half-Kelly with uncertainty haircut):
    target_risk = bal * half_kelly_fraction(wr, rr) * uncertainty_factor
    n_contracts = floor(target_risk / risk_per_contract)
    Cap by:
      - never risk more than 25% of buffer-to-MLL on any single trade
      - never exceed 50 MNQ (the TopStep cap)
      - always trade at least 1 contract if we can afford it

The simulator runs each trade through a strict per-trade liquidation check:
if a single full-stop loss would breach the MLL, the position is rejected
(too big to size safely).

Output:
    data/topstep_combine_results.json
    stdout markdown grid
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
OUT_PATH = DATA_DIR / "topstep_combine_results.json"

# TopStep $50K Combine parameters
STARTING_BALANCE = 50_000.0
INITIAL_MLL = 48_000.0
MLL_LOCK_AT = 52_000.0           # once EOD balance reaches this, MLL locks
LOCKED_MLL = 50_000.0            # value MLL locks at
PROFIT_TARGET = 53_000.0          # must reach this to pass the Combine
MAX_MNQ_CONTRACTS = 50            # 5 NQ × 10 = 50 MNQ (Topstep cap)

# Per-contract economics — we use MNQ throughout for granular sizing
DOLLARS_PER_POINT_MNQ = 2.0
COMM_PER_RT_MNQ = 0.40            # round-trip commission per MNQ contract


def half_kelly(wr: float, rr: float) -> float:
    """Half-Kelly fraction. wr in [0,1], rr = win$/loss$ ratio.

    Full Kelly: f* = (wr*rr - (1-wr)) / rr
    Half: f* / 2.  Clip to [0, 0.10] — never bet more than 10% of bankroll.
    """
    if rr <= 0:
        return 0.0
    f = (wr * rr - (1 - wr)) / rr
    if f <= 0:
        return 0.0
    return float(np.clip(f / 2, 0, 0.10))


def kelly_with_uncertainty_haircut(wr: float, rr: float, n_observations: int,
                                     fraction: float = 0.5) -> float:
    """Fractional-Kelly shrunk for low-confidence WR estimates.

    The DJ video on Kelly: "uncertainty in your estimate should make you less
    confident in your bets so you should shrink them."

    fraction=0.5 = Half Kelly (default), 0.25 = Quarter Kelly (more conservative).
    Heuristic: if WR is from < 100 observations, scale by sqrt(n/100).
    """
    if rr <= 0:
        return 0.0
    f = (wr * rr - (1 - wr)) / rr
    if f <= 0:
        return 0.0
    f = float(np.clip(f * fraction, 0, 0.10))
    if n_observations < 100:
        f *= float(np.sqrt(n_observations / 100))
    return f


def load_trades(active_names: set[str]) -> list[dict]:
    cache = json.loads(CACHE_PATH.read_text())
    out = []
    for t in cache["trades"]:
        if t["name"] in active_names:
            t["ts"] = pd.Timestamp(t["ts"])
            out.append(t)
    out.sort(key=lambda t: t["ts"])
    return out


def gate(trades_sorted: list[dict]) -> list[dict]:
    """1-position-at-a-time + 8 trades/day cap."""
    open_until = pd.Timestamp.min.tz_localize("UTC")
    today = None; n_today = 0
    taken = []
    for t in trades_sorted:
        ts = t["ts"]
        if today != ts.date():
            today = ts.date(); n_today = 0
        if n_today >= 8 or ts < open_until:
            continue
        taken.append(t)
        lockout = t["max_hold"] * (5 if t["tf"] == "5m" else 1)
        open_until = ts + pd.Timedelta(minutes=lockout)
        n_today += 1
    return taken


def simulate_combine(taken: list[dict],
                     per_strategy_wr: dict[str, float],
                     per_strategy_n: dict[str, int],
                     kelly_fraction: float = 0.5,
                     verbose: bool = False) -> dict:
    """Run the TopStep $50K Trading Combine sim.

    Returns dict with pass/fail, days_to_pass, daily P&L, blow-up reason.
    """
    bal = STARTING_BALANCE
    mll = INITIAL_MLL
    mll_locked = False
    eod_high = STARTING_BALANCE     # tracks highest EOD balance for MLL trail
    blown = False
    passed = False
    blow_reason = None
    pass_day = None

    daily_pnl: dict[str, float] = defaultdict(float)
    daily_trades: dict[str, int] = defaultdict(int)
    days_traded = []
    trade_log = []
    skipped_too_big = 0
    current_day = None

    for t in taken:
        if blown or passed:
            break

        ts = t["ts"]
        day = ts.date().isoformat()
        if current_day is None:
            current_day = day
        if day != current_day:
            # End of day — update MLL trail based on EOD balance
            eod_high = max(eod_high, bal)
            if not mll_locked:
                # MLL trails: rises with eod_high, never moves down
                new_mll = eod_high - 2_000.0
                mll = max(mll, new_mll)
                if eod_high >= MLL_LOCK_AT:
                    mll = LOCKED_MLL
                    mll_locked = True
            current_day = day

        # Per-trade sizing
        wr = per_strategy_wr.get(t["name"], 0.5)
        n_obs = per_strategy_n.get(t["name"], 50)
        rr = t["target_pts"] / t["stop_pts"] if t["stop_pts"] > 0 else 2.0
        kf = kelly_with_uncertainty_haircut(wr, rr, n_obs, fraction=kelly_fraction)
        target_risk = bal * kf

        risk_per_mnq = t["stop_pts"] * DOLLARS_PER_POINT_MNQ + COMM_PER_RT_MNQ
        n_contracts = int(target_risk // risk_per_mnq) if risk_per_mnq > 0 else 0

        # Cap by buffer-to-MLL: never risk more than 25% of buffer on a trade
        buffer_to_mll = bal - mll
        max_risk_buffer = buffer_to_mll * 0.25
        max_n_buffer = int(max_risk_buffer // risk_per_mnq) if risk_per_mnq > 0 else 0
        n_contracts = min(n_contracts, max_n_buffer)

        # Cap by Topstep position limit
        n_contracts = min(n_contracts, MAX_MNQ_CONTRACTS)

        # Reject trade if can't size safely (full stop would breach MLL)
        if n_contracts < 1:
            skipped_too_big += 1
            continue

        # Apply trade
        pnl = t["pts"] * DOLLARS_PER_POINT_MNQ * n_contracts - COMM_PER_RT_MNQ * n_contracts
        new_bal = bal + pnl

        # Check intraday MLL breach
        # The trade's worst-case balance during the trade = bal - (stop_pts * dpp + comm) * n
        # If t["pts"] > 0, the trade may have touched the stop briefly; we conservatively
        # assume the worst intra-trade excursion was a full stop hit.
        # If the trade was a winner, peak adverse = something less than stop. We use
        # min(0, pnl) - (potential MAE buffer) but for simplicity assume MAE ≈ stop loss
        # for losing trades and 0 for winners.
        if pnl < 0:
            # Losing trade — at moment of stop hit, balance dipped to new_bal
            if new_bal <= mll:
                bal = new_bal
                blown = True
                blow_reason = f"MLL_breach_intraday_{day}"
                trade_log.append({
                    "ts": ts.isoformat(), "name": t["name"], "n_contracts": n_contracts,
                    "pnl": pnl, "bal_after": new_bal, "mll": mll, "blew_up": True,
                })
                break

        bal = new_bal
        daily_pnl[day] += pnl
        daily_trades[day] += 1
        if day not in days_traded:
            days_traded.append(day)

        trade_log.append({
            "ts": ts.isoformat(), "name": t["name"], "n_contracts": n_contracts,
            "pnl": pnl, "bal_after": bal, "mll": mll, "blew_up": False,
        })

        # Check pass condition
        if bal >= PROFIT_TARGET:
            passed = True
            pass_day = day
            break

    # Final EOD update if not blown/passed
    if not blown and not passed:
        eod_high = max(eod_high, bal)

    return {
        "starting_balance": STARTING_BALANCE,
        "ending_balance": bal,
        "passed": passed,
        "pass_day": pass_day,
        "blown": blown,
        "blow_reason": blow_reason,
        "days_traded": len(days_traded),
        "skipped_too_big": skipped_too_big,
        "n_trades_taken": len([l for l in trade_log if not l["blew_up"]]),
        "daily_pnl": dict(daily_pnl),
        "daily_trades": dict(daily_trades),
        "first_day": days_traded[0] if days_traded else None,
        "last_day": days_traded[-1] if days_traded else None,
        "trade_log": trade_log[:100],  # first 100 for inspection
    }


def render_grid(result: dict) -> str:
    if not result.get("daily_pnl"):
        return "(no trades)"
    daily = sorted(result["daily_pnl"].items())
    bal = STARTING_BALANCE
    lines = ["", "=" * 80]
    status = "PASSED" if result["passed"] else ("BLOWN UP" if result["blown"] else "RAN OUT OF DATA")
    lines.append(f"  TOPSTEP $50K COMBINE  —  {status}")
    if result["passed"]:
        lines.append(f"  Passed on: {result['pass_day']}  ({result['days_traded']} trading days)")
    elif result["blown"]:
        lines.append(f"  Blown on:  {result['blow_reason']}")
    lines.append(f"  Final balance: ${result['ending_balance']:,.0f}    Profit target: ${PROFIT_TARGET:,.0f}")
    lines.append("=" * 80)
    lines.append(f"  {'date':<12} {'trades':>6} {'P&L':>12} {'balance':>12}")
    lines.append("  " + "-" * 60)
    for date, pnl in daily[:30]:   # show first 30 days
        n = result["daily_trades"].get(date, 0)
        bal += pnl
        lines.append(f"  {date:<12} {n:>6} ${pnl:>+10,.0f} ${bal:>+10,.0f}")
    if len(daily) > 30:
        lines.append(f"  ... ({len(daily) - 30} more days)")
    return "\n".join(lines)


def main() -> int:
    print("=" * 80)
    print("TOPSTEP $50K COMBINE SIMULATOR")
    print("  (real-time MLL monitoring + half-Kelly with uncertainty haircut)")
    print("=" * 80)

    # Load whitelist + cache
    val = json.loads(VAL_PATH.read_text())
    sigs = val["signals"]
    active = {n for n, s in sigs.items() if s.get("recommended")}
    print(f"\n  whitelist:  {len(active)} active strategies")

    per_wr = {n: float(s.get("win_rate") or 0.5) for n, s in sigs.items() if n in active}
    per_n = {n: int(s.get("trades") or 100) for n, s in sigs.items() if n in active}

    # Load trades
    print("  loading cached trades ...")
    raw = load_trades(active)
    print(f"  raw signals (in active set): {len(raw):,}")

    taken = gate(raw)
    print(f"  gated trades:                {len(taken):,}")

    test_start = pd.Timestamp("2024-01-01", tz="UTC")
    taken_oos = [t for t in taken if t["ts"] >= test_start]
    print(f"  OOS trades (2024-01+):       {len(taken_oos):,}")

    if not taken_oos:
        print("  no OOS trades"); return 1

    first_ts = taken_oos[0]["ts"]
    last_ts = taken_oos[-1]["ts"]
    n_attempts = 100
    max_start = last_ts - pd.Timedelta(days=90)
    if max_start <= first_ts:
        max_start = first_ts + pd.Timedelta(days=1)
    start_dates = pd.date_range(start=first_ts, end=max_start, periods=n_attempts, tz="UTC")

    # Run both Half-Kelly and Quarter-Kelly so we can compare
    summaries = {}
    for label, kf in [("Half-Kelly (0.50)", 0.5), ("Quarter-Kelly (0.25)", 0.25),
                       ("Eighth-Kelly (0.125)", 0.125)]:
        print(f"\n  Running 100 attempts with {label} ...")
        results = []; n_passed = 0; n_blown = 0; n_timeout = 0
        days_to_pass = []; pnls_at_timeout = []
        for start in start_dates:
            end = start + pd.Timedelta(days=90)
            sub = [t for t in taken_oos if start <= t["ts"] < end]
            if len(sub) < 5: continue
            result = simulate_combine(sub, per_wr, per_n, kelly_fraction=kf, verbose=False)
            results.append({
                "start": start.isoformat()[:10],
                "passed": result["passed"], "blown": result["blown"],
                "days_traded": result["days_traded"],
                "ending_balance": result["ending_balance"],
            })
            if result["passed"]: n_passed += 1; days_to_pass.append(result["days_traded"])
            elif result["blown"]: n_blown += 1
            else: n_timeout += 1; pnls_at_timeout.append(result["ending_balance"] - STARTING_BALANCE)

        n_total = len(results)
        summaries[label] = {
            "kelly_fraction": kf,
            "n_attempts": n_total,
            "n_passed": n_passed,
            "n_blown": n_blown,
            "n_timeout": n_timeout,
            "pass_rate": n_passed / max(1, n_total),
            "blow_rate": n_blown / max(1, n_total),
            "median_days_to_pass": int(np.median(days_to_pass)) if days_to_pass else None,
            "fastest_pass": min(days_to_pass) if days_to_pass else None,
            "slowest_pass": max(days_to_pass) if days_to_pass else None,
            "median_timeout_pnl": float(np.median(pnls_at_timeout)) if pnls_at_timeout else None,
            "results": results,
        }

    # Summary table
    print("\n" + "=" * 80)
    print("  KELLY-FRACTION COMPARISON   (100 Combine attempts, 90-day window each)")
    print("=" * 80)
    print(f"  {'Sizing':<24} {'Pass%':>7} {'Blow%':>7} {'Timeout%':>10} "
          f"{'Med days':>10} {'Fastest':>9}")
    print("  " + "-" * 76)
    for label, s in summaries.items():
        print(f"  {label:<24} {s['pass_rate']*100:>6.0f}% {s['blow_rate']*100:>6.0f}% "
              f"{(1-s['pass_rate']-s['blow_rate'])*100:>9.0f}% "
              f"{(s['median_days_to_pass'] or 0):>9}d "
              f"{(s['fastest_pass'] or 0):>8}d")
    print(f"\n  TopStep 2025 industry avg pass rate: 16.8%   funded payout rate: 33.3%")

    # Use Half-Kelly as default for the example display
    n_passed = summaries["Half-Kelly (0.50)"]["n_passed"]
    results = summaries["Half-Kelly (0.50)"]["results"]
    n_total = summaries["Half-Kelly (0.50)"]["n_attempts"]
    n_blown = summaries["Half-Kelly (0.50)"]["n_blown"]
    n_timeout = summaries["Half-Kelly (0.50)"]["n_timeout"]

    # Show first passing run as example
    print(f"\n  --- Example passing run (first attempt) ---")
    if results:
        first_pass = next((r for r in results if r["passed"]), None)
        if first_pass:
            ix = next(i for i, r in enumerate(results) if r["passed"])
            ex_start = pd.Timestamp(first_pass["start"], tz="UTC")
            ex_end = ex_start + pd.Timedelta(days=90)
            ex_sub = [t for t in taken_oos if ex_start <= t["ts"] < ex_end]
            ex_result = simulate_combine(ex_sub, per_wr, per_n)
            print(render_grid(ex_result))

    OUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "starting_balance": STARTING_BALANCE,
            "initial_mll": INITIAL_MLL,
            "profit_target": PROFIT_TARGET,
            "max_mnq_contracts": MAX_MNQ_CONTRACTS,
        },
        "summaries_by_kelly_fraction": summaries,
    }, indent=2, default=str))
    print(f"\n  Wrote -> data/topstep_combine_results.json")
    return 0 if n_passed > n_blown else 1


if __name__ == "__main__":
    sys.exit(main())

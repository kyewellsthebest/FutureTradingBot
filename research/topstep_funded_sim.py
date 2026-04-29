"""
TopStep $50K Express Funded Account 6-month projection.

Simulates what happens AFTER you pass the Combine, on the actual Express
Funded Account (XFA) per Topstep's docs:

  Starting state:
    - Balance:  $0  (XFA always starts at $0; the "$50K" label is buying power)
    - MLL:      -$2,000  (trails up as you make money)
    - MLL lock: $0  (once balance reaches $2,000, MLL locks at $0)
    - After first payout: MLL is set to $0 and balance must stay > $0

  Position cap:    50 MNQ (= 5 NQ)
  All positions flat by 3:10 PM CT

Payout strategy modelled here:
    Once balance > $2,500, withdraw 50% on the last trading day of each
    month, leaving 50% as buffer to keep trading. (Typical Topstep payout
    cadence — actual minimum/maximum are negotiable.)

  Sizing rule (same as Combine sim): half-Kelly with uncertainty haircut,
  capped at 25% of buffer-to-MLL per trade, capped at 50 MNQ.

Output:
    data/topstep_funded_results.json
    stdout markdown grid with monthly P&L + cumulative payouts + balance
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
OUT_PATH = DATA_DIR / "topstep_funded_results.json"

# Express Funded Account $50K
INITIAL_BALANCE = 0.0
INITIAL_MLL = -2_000.0
MLL_LOCK_BALANCE = 2_000.0     # once balance reaches this, MLL locks at $0
LOCKED_MLL = 0.0
MAX_MNQ_CONTRACTS = 50
PAYOUT_THRESHOLD = 2_500.0     # only take a payout if balance > this
PAYOUT_FRACTION = 0.50         # withdraw 50% of balance on payout

DPP_MNQ = 2.0
COMM_MNQ = 0.40


def half_kelly_haircut(wr: float, rr: float, n_obs: int, fraction: float = 0.5) -> float:
    if rr <= 0:
        return 0.0
    f = (wr * rr - (1 - wr)) / rr
    if f <= 0:
        return 0.0
    f = float(np.clip(f * fraction, 0, 0.10))
    if n_obs < 100:
        f *= float(np.sqrt(n_obs / 100))
    return f


def gate(trades_sorted: list[dict]) -> list[dict]:
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


def simulate_funded_6mo(taken: list[dict],
                         per_wr: dict[str, float],
                         per_n: dict[str, int],
                         start_ts: pd.Timestamp,
                         duration_days: int = 183) -> dict:
    """6-month forward projection on Express Funded Account."""
    end_ts = start_ts + pd.Timedelta(days=duration_days)
    sub = [t for t in taken if start_ts <= t["ts"] < end_ts]
    if not sub:
        return {"error": "no trades in window"}

    bal = INITIAL_BALANCE
    mll = INITIAL_MLL
    mll_locked = False
    eod_high = INITIAL_BALANCE
    blown = False
    blow_reason = None
    daily_pnl: dict[str, float] = defaultdict(float)
    monthly_pnl: dict[str, float] = defaultdict(float)
    monthly_trades: dict[str, int] = defaultdict(int)
    payouts: list[dict] = []
    cum_payout = 0.0
    current_day = None
    last_month_ym = None
    skipped = 0
    n_taken = 0

    for t in sub:
        if blown:
            break
        ts = t["ts"]
        day = ts.date().isoformat()
        ym = (ts.year, ts.month)

        # End-of-day update + monthly payout check
        if current_day is None:
            current_day = day
            last_month_ym = ym
        if day != current_day:
            eod_high = max(eod_high, bal)
            if not mll_locked:
                new_mll = eod_high - 2_000.0
                mll = max(mll, new_mll)
                if eod_high >= MLL_LOCK_BALANCE:
                    mll = LOCKED_MLL
                    mll_locked = True
            current_day = day

            # Monthly payout sweep on month rollover
            if ym != last_month_ym:
                if mll_locked and bal > PAYOUT_THRESHOLD:
                    payout_amount = bal * PAYOUT_FRACTION
                    payouts.append({
                        "month": f"{last_month_ym[0]}-{last_month_ym[1]:02d}",
                        "amount": payout_amount,
                        "balance_before": bal,
                        "balance_after": bal - payout_amount,
                    })
                    bal -= payout_amount
                    cum_payout += payout_amount
                last_month_ym = ym

        # Sizing
        wr = per_wr.get(t["name"], 0.5)
        n_obs = per_n.get(t["name"], 100)
        rr = t["target_pts"] / t["stop_pts"] if t["stop_pts"] > 0 else 2.0
        kf = half_kelly_haircut(wr, rr, n_obs, fraction=0.5)

        # Use absolute risk room (balance - MLL = buffer)
        buffer_to_mll = bal - mll
        target_risk = max(0.0, buffer_to_mll * kf)
        risk_per_mnq = t["stop_pts"] * DPP_MNQ + COMM_MNQ
        n_contracts = int(target_risk // risk_per_mnq) if risk_per_mnq > 0 else 0
        # 25% buffer cap per trade
        n_contracts = min(n_contracts, int((buffer_to_mll * 0.25) // risk_per_mnq))
        n_contracts = min(n_contracts, MAX_MNQ_CONTRACTS)
        if n_contracts < 1:
            skipped += 1
            continue

        pnl = t["pts"] * DPP_MNQ * n_contracts - COMM_MNQ * n_contracts
        new_bal = bal + pnl
        # Real-time MLL check on losing trades
        if pnl < 0 and new_bal <= mll:
            bal = new_bal
            blown = True
            blow_reason = f"MLL_breach_{day}"
            break

        bal = new_bal
        n_taken += 1
        daily_pnl[day] += pnl
        ymk = f"{ym[0]}-{ym[1]:02d}"
        monthly_pnl[ymk] += pnl
        monthly_trades[ymk] += 1

    # Final EOD + last-month payout
    if not blown:
        eod_high = max(eod_high, bal)
        if mll_locked and bal > PAYOUT_THRESHOLD:
            ym = last_month_ym
            payout_amount = bal * PAYOUT_FRACTION
            payouts.append({
                "month": f"{ym[0]}-{ym[1]:02d}",
                "amount": payout_amount,
                "balance_before": bal,
                "balance_after": bal - payout_amount,
            })
            bal -= payout_amount
            cum_payout += payout_amount

    return {
        "start": start_ts.isoformat()[:10],
        "end": end_ts.isoformat()[:10],
        "blown": blown,
        "blow_reason": blow_reason,
        "n_trades_taken": n_taken,
        "skipped_too_big": skipped,
        "ending_balance": bal,
        "cumulative_payouts": cum_payout,
        "total_take_home": cum_payout + max(0, bal),
        "monthly_pnl": dict(monthly_pnl),
        "monthly_trades": dict(monthly_trades),
        "payouts": payouts,
    }


def render_grid(result: dict) -> str:
    if result.get("error"):
        return f"  ERROR: {result['error']}"
    months = sorted(result["monthly_pnl"].keys())
    lines = ["", "=" * 88]
    lines.append(f"  TOPSTEP $50K EXPRESS FUNDED — 6-month projection")
    lines.append(f"  Window: {result['start']} → {result['end']}")
    lines.append("=" * 88)
    if result["blown"]:
        lines.append(f"  BLEW UP: {result['blow_reason']}")
    lines.append("")
    lines.append(f"  {'month':<10} {'trades':>7} {'gross P&L':>12} "
                 f"{'payout':>10} {'balance':>11}  {'cum payout':>12}")
    lines.append("  " + "-" * 80)
    bal_running = INITIAL_BALANCE
    cum_payout = 0.0
    payouts_by_month = {p["month"]: p["amount"] for p in result["payouts"]}
    for m in months:
        gross = result["monthly_pnl"][m]
        n_trades = result["monthly_trades"][m]
        bal_running += gross
        payout = payouts_by_month.get(m, 0.0)
        bal_running -= payout
        cum_payout += payout
        lines.append(
            f"  {m:<10} {n_trades:>7} ${gross:>+10,.0f} ${payout:>+8,.0f} "
            f"${bal_running:>+9,.0f}  ${cum_payout:>+10,.0f}"
        )
    lines.append("  " + "-" * 80)
    lines.append(
        f"  {'TOTAL':<10} {sum(result['monthly_trades'].values()):>7} "
        f"${sum(result['monthly_pnl'].values()):>+10,.0f} "
        f"${cum_payout:>+8,.0f} ${result['ending_balance']:>+9,.0f}  "
        f"${cum_payout:>+10,.0f}"
    )
    lines.append("")
    lines.append(f"  Total take-home (payouts + remaining balance): "
                 f"${result['total_take_home']:,.0f}")
    return "\n".join(lines)


def main() -> int:
    print("=" * 80)
    print("TOPSTEP $50K EXPRESS FUNDED — 6-MONTH PROJECTION")
    print("  (Half-Kelly sizing, 25% buffer cap, monthly 50% payout)")
    print("=" * 80)

    val = json.loads(VAL_PATH.read_text())
    sigs = val["signals"]
    active = {n for n, s in sigs.items() if s.get("recommended")}
    per_wr = {n: float(s.get("win_rate") or 0.5) for n, s in sigs.items() if n in active}
    per_n = {n: int(s.get("trades") or 100) for n, s in sigs.items() if n in active}
    print(f"\n  whitelist: {len(active)} active strategies")

    cache = json.loads(CACHE_PATH.read_text())
    raw = []
    for t in cache["trades"]:
        if t["name"] in active:
            t["ts"] = pd.Timestamp(t["ts"])
            raw.append(t)
    raw.sort(key=lambda t: t["ts"])
    taken = gate(raw)
    print(f"  gated trades: {len(taken):,}")

    # Run a 6-month projection from each of the last 12 calendar starts
    # so we average out which month you happened to start on.
    last_ts = taken[-1]["ts"]
    starts = [last_ts - pd.Timedelta(days=183 + 30 * i) for i in range(12)]
    starts = sorted(starts)

    print(f"\n  Running 12 staggered 6-month projections ...")
    all_results = []
    for s in starts:
        r = simulate_funded_6mo(taken, per_wr, per_n, s)
        if r.get("error"):
            continue
        all_results.append(r)

    # Aggregate stats
    take_homes = [r["total_take_home"] for r in all_results if not r["blown"]]
    n_blown = sum(1 for r in all_results if r["blown"])
    n_total = len(all_results)
    print(f"\n  {n_total} 6-month projections:")
    print(f"    Blow-ups:     {n_blown}/{n_total}")
    if take_homes:
        print(f"    Take-home (payouts + bal):")
        print(f"      Median:    ${np.median(take_homes):>10,.0f}")
        print(f"      Mean:      ${np.mean(take_homes):>10,.0f}")
        print(f"      Best:      ${max(take_homes):>10,.0f}")
        print(f"      Worst:     ${min(take_homes):>10,.0f}")

    # Show the most-recent 6-month grid (Oct 2025 → Apr 2026, the one the
    # user originally asked about)
    target_start = pd.Timestamp("2025-10-07", tz="UTC")
    closest = min(all_results,
                  key=lambda r: abs((pd.Timestamp(r["start"], tz="UTC") - target_start).total_seconds()))
    print(render_grid(closest))

    OUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_projections": n_total,
        "n_blown": n_blown,
        "median_take_home": float(np.median(take_homes)) if take_homes else None,
        "results": all_results,
    }, indent=2, default=str))
    print(f"\n  Wrote -> data/topstep_funded_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

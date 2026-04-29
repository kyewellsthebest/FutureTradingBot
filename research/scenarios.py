"""
Two demo scenarios for the rebuilt whitelist:

  Scenario A: $50,000 demo account — what's the monthly P&L over the most
              recent 6 months, taking every trade the bot fires?

  Scenario B: $1,000 live account — how fast does the equity compound when
              the bot scales contract size as the account grows?

Both scenarios use the SAME combined-trader logic:
    - One open position at a time (global lock by max_hold)
    - 8 trades/day cap (matches paper_trading.py)
    - All whitelist patterns from data/validation_results.json

Sizing:
    Scenario A — fixed: 5 MNQ for 1-min strats, 30 MNQ for 5-min strats
    Scenario B — equity-scaled, risk-per-trade ~2% of account:
        - Use MNQ ($2/pt) until equity covers ≥1 NQ ($20/pt) at 2% risk
        - Once equity ≥ stop_dollars × 50 — upgrade to NQ contract sizing
        - n_contracts = max(1, floor(equity * 0.02 / (stop_pts * dpp)))

Outputs:
    data/scenarios.json
    stdout markdown tables
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_daily, load_intraday_1min, load_intraday_5min
from research.validate_mined_full import fixed_target_stop_simulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NY = "America/New_York"


def gather_trades(use_cache: bool = True) -> list[dict]:
    """Regenerate every whitelist pattern's entries on 8-yr data and return a
    chronologically sorted list of trade dicts (one per signal entry, before
    any combined-trader gating).

    Optimization: compute the 50-feature DataFrame ONCE (not per-strategy)
    and apply each pattern's constraints as a numpy mask. If a cache file
    exists at data/scenarios_trades_cache.json AND its whitelist hash matches
    the current validation_results.json, reuse it (instant).
    """
    import hashlib
    val_path = PROJECT_ROOT / "data" / "validation_results.json"
    val = json.loads(val_path.read_text())
    whitelist = {k: v for k, v in val["signals"].items() if v.get("recommended")}
    whitelist = {k: v for k, v in whitelist.items() if (v.get("win_rate") or 0) > 0}
    print(f"  whitelist signals: {len(whitelist)}")

    wl_hash = hashlib.md5(",".join(sorted(whitelist.keys())).encode()).hexdigest()
    cache = PROJECT_ROOT / "data" / "scenarios_trades_cache.json"
    if use_cache and cache.exists():
        try:
            cached = json.loads(cache.read_text())
            cached_names = {t["name"] for t in cached["trades"]}
            current_names = set(whitelist.keys())
            if cached["whitelist_hash"] == wl_hash:
                print(f"  using cached trades (hash match) — {cached['n_trades']:,} signals")
                trades = []
                for t in cached["trades"]:
                    t["ts"] = pd.Timestamp(t["ts"])
                    trades.append(t)
                return trades
            elif current_names.issubset(cached_names):
                print(f"  filtering cache: {len(cached_names)} cached names → "
                      f"{len(current_names)} active")
                trades = []
                for t in cached["trades"]:
                    if t["name"] in current_names:
                        t["ts"] = pd.Timestamp(t["ts"])
                        trades.append(t)
                trades.sort(key=lambda t: t["ts"])
                print(f"  filtered to {len(trades):,} signals")
                return trades
        except Exception as e:
            print(f"  cache load failed ({e!r}) — rebuilding")
    print("  loading 1-min + 5-min + daily ...", flush=True)
    t_load = time.time()
    m1 = load_intraday_1min("nq")
    m5 = load_intraday_5min("nq")
    daily = load_daily("nq")
    h1, l1, c1 = (m1[c].to_numpy(dtype=np.float64) for c in ("high", "low", "close"))
    h5, l5, c5 = (m5[c].to_numpy(dtype=np.float64) for c in ("high", "low", "close"))
    print(f"  loaded in {time.time()-t_load:.1f}s")

    print("  building V3 features once over 2.8M bars ...", flush=True)
    t_feat = time.time()
    from research.pattern_miner_v3 import build_v3_features
    X1 = build_v3_features(m1, daily)
    print(f"  features built in {time.time()-t_feat:.1f}s")

    # Pre-cache numpy columns to avoid pandas overhead inside the loop
    feat_cols: dict[str, np.ndarray] = {col: X1[col].to_numpy() for col in X1.columns}
    nan_lookup: dict[str, np.ndarray] = {col: np.isnan(arr) for col, arr in feat_cols.items()}

    from research.signal_generator import ALL_SIGNALS
    from research.mined_wr_signals import ALL_WR_SIGNALS
    from research.mined_v3_signals import ALL_V3_SIGNALS
    sig_objs = {}
    for s in list(ALL_SIGNALS) + list(ALL_WR_SIGNALS) + list(ALL_V3_SIGNALS):
        if hasattr(s, "name"):
            sig_objs[s.name] = s

    trades = []
    skipped = 0
    t_loop = time.time()
    for k_idx, (name, info) in enumerate(whitelist.items(), 1):
        sig = sig_objs.get(name)
        if sig is None:
            skipped += 1
            continue
        is_v3 = name.startswith("V3_") or name.startswith("WR_")
        if is_v3:
            tf = "1m"; intraday = m1; h, l, c = h1, l1, c1
        else:
            # Non-V3: fall back to .generate() (5-min path, only PDH_TOUCH likely)
            tf = "5m"; intraday = m5; h, l, c = h5, l5, c5
        stop = float(info.get("stop_pts") or getattr(sig, "stop_pts", 15.0))
        target = float(info.get("target_pts") or getattr(sig, "target_pts", 30.0))
        max_hold = int(getattr(sig, "max_hold_bars", 80))
        side = info.get("side") or getattr(sig, "side", "LONG")

        if is_v3 and hasattr(sig, "constraints"):
            # Fast path — apply constraints to pre-built features
            n_bars = len(m1)
            mask = np.ones(n_bars, dtype=bool)
            for col, op, thr in sig.constraints:
                if col not in feat_cols:
                    mask[:] = False; break
                v = feat_cols[col]
                if op == "<=":
                    mask &= (v <= thr)
                elif op == ">":
                    mask &= (v > thr)
                else:
                    mask[:] = False; break
                mask &= ~nan_lookup[col]
            end_cap = n_bars - max_hold - 1
            mask[end_cap:] = False
            entries = np.where(mask)[0].tolist()
        else:
            try:
                df = sig.generate(intraday, daily)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            sig_times = pd.DatetimeIndex(df["signal_time"])
            pos = intraday.index.get_indexer(sig_times)
            entries = [int(p) for p in pos if p >= 0 and p < len(intraday) - max_hold - 1]
        if not entries:
            continue
        pts = fixed_target_stop_simulate(h, l, c, entries, side, stop, target, max_hold)
        if not pts:
            continue
        pts_arr = np.asarray(pts)
        n = len(pts_arr)
        ts_idx = intraday.index
        for i in range(n):
            trades.append({
                "name": name, "side": side, "tf": tf,
                "ts": ts_idx[entries[i]],
                "pts": float(pts_arr[i]),
                "stop_pts": stop, "target_pts": target,
                "max_hold": max_hold,
            })
        if k_idx % 25 == 0:
            print(f"    [{k_idx}/{len(whitelist)}] {name:<28} entries={n:>6}   "
                  f"elapsed={time.time()-t_loop:.0f}s", flush=True)
    print(f"  raw signals: {len(trades):,}   strategies skipped (no class): {skipped}")
    trades.sort(key=lambda t: t["ts"])

    # Persist cache so subsequent runs (e.g. re-tuning Scenario B) are instant
    serialisable = [
        {**t, "ts": t["ts"].isoformat()}
        for t in trades
    ]
    cache.write_text(json.dumps({
        "whitelist_hash": wl_hash,
        "n_trades": len(trades),
        "trades": serialisable,
    }, indent=2, default=str))
    print(f"  cached -> data/scenarios_trades_cache.json")
    return trades


def gate(trades: list[dict]) -> list[dict]:
    """Apply one-position-at-a-time + 8 trades/day cap. Returns the trades
    that would actually be taken in live."""
    open_until = pd.Timestamp.min.tz_localize("UTC")
    today = None
    n_today = 0
    taken = []
    for t in trades:
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


def scenario_a(trades: list[dict]) -> dict:
    """Fixed 5/30 MNQ sizing, last 6 months of data."""
    if not trades:
        return {}
    last_ts = trades[-1]["ts"]
    six_mo_ago = last_ts - pd.Timedelta(days=183)
    sub = [t for t in trades if t["ts"] >= six_mo_ago]
    if not sub:
        return {}
    print(f"\n  ScenarioA window: {six_mo_ago.date()} → {last_ts.date()}   "
          f"trades in window: {len(sub):,}")

    bal = 50000.0
    starting = bal
    eq_curve = [(sub[0]["ts"], bal)]
    months_pnl = {}
    peak = bal
    max_dd = 0.0
    n_wins = n_losses = 0
    for t in sub:
        contracts = 5 if t["tf"] == "1m" else 30
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl = t["pts"] * dpp - comm
        bal += pnl
        peak = max(peak, bal)
        max_dd = max(max_dd, peak - bal)
        eq_curve.append((t["ts"], bal))
        ym = (t["ts"].year, t["ts"].month)
        months_pnl[ym] = months_pnl.get(ym, 0.0) + pnl
        if pnl > 0: n_wins += 1
        else: n_losses += 1

    monthly_table = sorted(months_pnl.items())
    final = bal
    pnl_total = final - starting
    return {
        "starting_balance": starting,
        "final_balance": final,
        "total_pnl": pnl_total,
        "total_pnl_pct": pnl_total / starting * 100,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd / starting * 100,
        "n_trades": len(sub),
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": n_wins / max(1, n_wins + n_losses),
        "monthly_pnl": [
            {"month": f"{y}-{m:02d}", "pnl": p, "pct": p / starting * 100}
            for (y, m), p in monthly_table
        ],
    }


def scenario_b(trades: list[dict]) -> dict:
    """$1k → compounding over the LAST 6 MONTHS: contracts scale with equity.

    Realistic caps:
      - MNQ day-trade margin ≈ $500/contract (broker like AMP, NinjaTrader)
      - NQ  day-trade margin ≈ $5,000/contract
      - Max position size: 20 MNQ or 5 NQ (retail liquidity ceiling)

    Sizing rule:
        risk_per_unit = stop_pts × dpp + commission
        target_risk = equity * 0.02
        n_units = floor(target_risk / risk_per_unit), clamped by margin + cap
        if equity ≥ 25k:  switch from MNQ to NQ
        if equity drops < 20k after NQ: switch back to MNQ
    """
    if not trades:
        return {}
    # Use the SAME 6-month window as Scenario A
    last_ts = trades[-1]["ts"]
    six_mo_ago = last_ts - pd.Timedelta(days=183)
    sub = [t for t in trades if t["ts"] >= six_mo_ago]
    if not sub:
        return {}
    print(f"  ScenarioB window: {six_mo_ago.date()} → {last_ts.date()}   "
          f"trades in window: {len(sub):,}")

    bal = 1000.0
    starting = bal
    contract_type = "MNQ"   # $2/pt
    n_blowups = 0
    eq_curve = [(trades[0]["ts"], bal)]
    months_pnl = {}
    peak = bal
    max_dd = 0.0
    n_wins = n_losses = 0
    skipped_no_size = 0
    contract_changes: list[tuple] = []
    for t in sub:
        if bal <= 0:
            n_blowups += 1
            break
        # Decide contract type
        new_type = contract_type
        if contract_type == "MNQ" and bal >= 25000:
            new_type = "NQ"
        elif contract_type == "NQ" and bal < 20000:
            new_type = "MNQ"
        if new_type != contract_type:
            contract_changes.append((t["ts"].isoformat(), contract_type, new_type, bal))
            contract_type = new_type

        dpp = 2.0 if contract_type == "MNQ" else 20.0   # $/pt per contract
        comm = 2.0 if contract_type == "MNQ" else 4.0   # round-turn $ per contract
        # Day-trade margin (most common discount-broker rate, e.g. AMP, NinjaTrader)
        margin_per_unit = 500.0 if contract_type == "MNQ" else 5000.0
        max_units = 20 if contract_type == "MNQ" else 5    # retail liquidity ceiling
        risk_per_unit = t["stop_pts"] * dpp + comm
        # Sizing: target 2% risk
        target_risk = bal * 0.02
        n_units = max(0, int(target_risk // risk_per_unit))
        # Cap by margin requirement (must be able to post margin AND have buffer)
        max_by_margin = max(0, int((bal - margin_per_unit) // margin_per_unit) + 1)
        n_units = min(n_units, max_by_margin)
        # Cap by liquidity ceiling
        n_units = min(n_units, max_units)
        # Allow 1 unit if we can absorb 5 consecutive max-stop losses AND post margin
        if n_units < 1 and risk_per_unit <= bal / 5.0 and bal >= margin_per_unit:
            n_units = 1
        if n_units < 1:
            skipped_no_size += 1
            continue
        pnl = t["pts"] * dpp * n_units - comm * n_units
        bal += pnl
        peak = max(peak, bal)
        max_dd = max(max_dd, peak - bal)
        eq_curve.append((t["ts"], bal))
        ym = (t["ts"].year, t["ts"].month)
        months_pnl[ym] = months_pnl.get(ym, 0.0) + pnl
        if pnl > 0: n_wins += 1
        else: n_losses += 1

    monthly_table = sorted(months_pnl.items())
    return {
        "starting_balance": starting,
        "final_balance": bal,
        "peak_balance": peak,
        "n_trades": n_wins + n_losses,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": n_wins / max(1, n_wins + n_losses),
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd / max(1, peak) * 100,
        "skipped_no_size": skipped_no_size,
        "blew_up": bal <= 0,
        "contract_changes": contract_changes,
        "monthly_pnl": [
            {"month": f"{y}-{m:02d}", "pnl": p}
            for (y, m), p in monthly_table
        ],
        "equity_milestones": _milestones(eq_curve),
    }


def _milestones(eq_curve: list[tuple]) -> list[dict]:
    """When did the account first cross $2k, $5k, $10k, $25k, $50k, $100k?"""
    targets = [2_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 1_000_000]
    out = []
    hit = set()
    for ts, eq in eq_curve:
        for t in targets:
            if eq >= t and t not in hit:
                hit.add(t)
                out.append({"target": t, "ts": ts.isoformat(), "equity": float(eq)})
    return out


def render_grid(a: dict, b: dict, n_strategies: int) -> str:
    """Side-by-side month-by-month grid for both scenarios."""
    # Build a unified month list from whichever has more rows
    months_a = {r["month"]: r for r in (a.get("monthly_pnl") or [])}
    months_b = {r["month"]: r for r in (b.get("monthly_pnl") or [])}
    all_months = sorted(set(months_a) | set(months_b))

    lines = ["", "=" * 96]
    lines.append(f"  6-MONTH FORECAST — {n_strategies} validated strategies, take every trade")
    lines.append("=" * 96)
    lines.append("")
    lines.append(f"  {'':<10}  {'$50,000 demo':^32}    {'$1,000 live (compounding)':^32}")
    lines.append(f"  {'month':<10}  {'P&L':>12}  {'balance':>12}    {'P&L':>12}  {'balance':>12}")
    lines.append(f"  {'-'*10}  {'-'*12}  {'-'*12}    {'-'*12}  {'-'*12}")
    bal_a = a.get("starting_balance", 50000)
    bal_b = b.get("starting_balance", 1000)
    for m in all_months:
        pa = months_a.get(m, {}).get("pnl", 0.0)
        pb = months_b.get(m, {}).get("pnl", 0.0)
        bal_a += pa
        bal_b += pb
        lines.append(
            f"  {m:<10}  ${pa:>+10,.0f}  ${bal_a:>10,.0f}    ${pb:>+10,.0f}  ${bal_b:>10,.0f}"
        )
    lines.append(f"  {'-'*10}  {'-'*12}  {'-'*12}    {'-'*12}  {'-'*12}")
    lines.append(
        f"  {'TOTAL':<10}  ${a.get('total_pnl',0):>+10,.0f}  ${a.get('final_balance',0):>10,.0f}"
        f"    ${b.get('final_balance',0)-b.get('starting_balance',0):>+10,.0f}  ${b.get('final_balance',0):>10,.0f}"
    )
    lines.append("")
    lines.append(f"  Trades: {a.get('n_trades',0)} ($50k) / {b.get('n_trades',0)} taken ($1k, "
                 f"{b.get('skipped_no_size',0)} skipped due to size)")
    lines.append(f"  Win rate: {a.get('win_rate',0)*100:.1f}% / {b.get('win_rate',0)*100:.1f}%")
    lines.append(f"  Max DD:   ${a.get('max_drawdown',0):,.0f} ({a.get('max_drawdown_pct',0):.1f}%) / "
                 f"${b.get('max_drawdown',0):,.0f} ({b.get('max_drawdown_pct',0):.1f}% of peak)")
    return "\n".join(lines)


def render_markdown(a: dict, b: dict) -> str:
    lines = ["", "=" * 80]
    lines.append("SCENARIO A: $50,000 demo, 6 months, take every trade")
    lines.append("=" * 80)
    if not a:
        lines.append("(no trades in window)")
    else:
        lines.append(f"  Starting:        ${a['starting_balance']:>12,.0f}")
        lines.append(f"  Final:           ${a['final_balance']:>12,.0f}")
        lines.append(f"  Total P&L:       ${a['total_pnl']:>+12,.0f}    "
                     f"({a['total_pnl_pct']:+.1f}%)")
        lines.append(f"  Max drawdown:    ${a['max_drawdown']:>12,.0f}    "
                     f"({a['max_drawdown_pct']:.1f}% of start)")
        lines.append(f"  Trades:          {a['n_trades']:>13,}    "
                     f"WR={a['win_rate']*100:.1f}%")
        lines.append("")
        lines.append("  Monthly breakdown:")
        lines.append(f"    {'month':<10} {'P&L':>14} {'%':>8}")
        for r in a["monthly_pnl"]:
            lines.append(f"    {r['month']:<10} ${r['pnl']:>+12,.0f} {r['pct']:>+7.1f}%")
    lines.append("")
    lines.append("=" * 80)
    lines.append("SCENARIO B: $1,000 live, 8 yrs, compounding contract size")
    lines.append("=" * 80)
    if not b:
        lines.append("(no trades)")
    else:
        lines.append(f"  Starting:        ${b['starting_balance']:>12,.0f}")
        lines.append(f"  Peak:            ${b['peak_balance']:>12,.0f}")
        lines.append(f"  Final:           ${b['final_balance']:>12,.0f}")
        lines.append(f"  Trades taken:    {b['n_trades']:>13,}    "
                     f"WR={b['win_rate']*100:.1f}%")
        lines.append(f"  Skipped (size):  {b['skipped_no_size']:>13,}")
        lines.append(f"  Blew up?         {'YES' if b['blew_up'] else 'no'}")
        lines.append(f"  Max drawdown:    ${b['max_drawdown']:>12,.0f}    "
                     f"({b['max_drawdown_pct']:.1f}% of peak)")
        if b["contract_changes"]:
            lines.append("\n  Contract upgrades:")
            for ts, old, new, eq in b["contract_changes"]:
                lines.append(f"    {ts[:10]}   {old} -> {new}   @ ${eq:,.0f}")
        lines.append("\n  Equity milestones:")
        for m in b["equity_milestones"]:
            lines.append(f"    ${m['target']:>10,}   {m['ts'][:10]}   ${m['equity']:,.0f}")
        if not b["equity_milestones"]:
            lines.append("    (none)")
    return "\n".join(lines)


def main() -> int:
    print("=" * 80)
    print("SCENARIO RUNNER — A: $50k demo 6mo,  B: $1k compounding 8yr")
    print("=" * 80)
    t0 = time.time()
    trades = gather_trades()
    if not trades:
        print("No trades — aborting"); return 1
    taken = gate(trades)
    print(f"  gated trades (live-equivalent): {len(taken):,}  "
          f"({len(taken)/len(trades)*100:.0f}% of raw)")
    print(f"  trade-gathering took {time.time()-t0:.1f}s")

    a = scenario_a(taken)
    b = scenario_b(taken)

    val = json.loads((PROJECT_ROOT / "data" / "validation_results.json").read_text())
    n_active = sum(1 for s in val["signals"].values() if s.get("recommended"))
    print(render_grid(a, b, n_active))
    print(render_markdown(a, b))

    out_path = PROJECT_ROOT / "data" / "scenarios.json"
    out_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_a": a, "scenario_b": b,
        "n_raw_signals": len(trades),
        "n_taken": len(taken),
    }, indent=2, default=str))
    print(f"\n  Wrote -> {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

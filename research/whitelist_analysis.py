"""
Per-strategy time-of-day analysis + combined-trader revenue projection.

Reads the live whitelist from data/validation_results.json, regenerates each
strategy's entries on 8 yrs of NQ, computes per-NY-session WR / EV / net P&L,
then runs a realistic combined-trader simulation (one position at a time,
8 trades/day cap, per-signal contract sizing) to project monthly revenue
on a $50k account.

Output:
    data/whitelist_analysis.json    (full machine-readable)
    stdout                          (markdown tables)
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
from research.validate_mined_full import _sim_inner, fixed_target_stop_simulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NY = "America/New_York"

# Kill zones (NY time, minutes-from-midnight)
SESSIONS = [
    ("ASIA",       18 * 60, 27 * 60),     # 18:00 prev day → 03:00 NY (wraps)
    ("LONDON",     3 * 60,  8 * 60),       # 03:00 → 08:00
    ("NY_OPEN",    9 * 60 + 30, 11 * 60),  # 09:30 → 11:00 (kill zone)
    ("NY_MIDDAY",  11 * 60, 14 * 60),     # 11:00 → 14:00
    ("NY_PM",      14 * 60, 16 * 60),     # 14:00 → 16:00 (close kill zone)
    ("NY_AH",      16 * 60, 18 * 60),     # 16:00 → 18:00
]


def session_for(ny_min: int) -> str:
    """Return session name for a given NY minute-of-day."""
    if ny_min >= 18 * 60 or ny_min < 3 * 60:
        return "ASIA"
    if ny_min < 8 * 60:
        return "LONDON"
    if ny_min < 11 * 60:
        return "NY_OPEN"
    if ny_min < 14 * 60:
        return "NY_MIDDAY"
    if ny_min < 16 * 60:
        return "NY_PM"
    return "NY_AH"


def run() -> int:
    print("=" * 80)
    print("WHITELIST ANALYSIS — time-of-day + combined revenue projection")
    print("=" * 80)

    print("\n[1/4] Loading data + whitelist ...", flush=True)
    t0 = time.time()
    m1 = load_intraday_1min("nq")
    m5 = load_intraday_5min("nq")
    daily = load_daily("nq")
    print(f"  1-min: {len(m1):,}  5-min: {len(m5):,}  daily: {len(daily):,}   "
          f"({time.time()-t0:.1f}s)")

    val = json.loads((PROJECT_ROOT / "data" / "validation_results.json").read_text())
    whitelist = {k: v for k, v in val["signals"].items() if v.get("recommended")}
    # Drop entries with no win_rate set (e.g. legacy WR_* with empty stats)
    whitelist = {k: v for k, v in whitelist.items() if (v.get("win_rate") or 0) > 0}
    print(f"  whitelist signals: {len(whitelist)}")

    # Regenerate trades for each strategy
    print("\n[2/4] Regenerating trades per strategy on 8yr ...", flush=True)
    all_trades = []   # list of {strategy, side, entry_ts, exit_ts, pnl_dollars}
    per_strategy: dict[str, dict] = {}

    # We need each strategy as a Signal object so we can call .generate()
    from research.signal_generator import ALL_SIGNALS
    from research.mined_wr_signals import ALL_WR_SIGNALS
    from research.mined_v3_signals import ALL_V3_SIGNALS

    sig_objs: dict[str, object] = {}
    for s in list(ALL_SIGNALS) + list(ALL_WR_SIGNALS) + list(ALL_V3_SIGNALS):
        if hasattr(s, "name"):
            sig_objs[s.name] = s

    h_arr_1m = m1["high"].to_numpy(dtype=np.float64)
    l_arr_1m = m1["low"].to_numpy(dtype=np.float64)
    c_arr_1m = m1["close"].to_numpy(dtype=np.float64)
    h_arr_5m = m5["high"].to_numpy(dtype=np.float64)
    l_arr_5m = m5["low"].to_numpy(dtype=np.float64)
    c_arr_5m = m5["close"].to_numpy(dtype=np.float64)

    for name, info in whitelist.items():
        sig = sig_objs.get(name)
        if sig is None:
            print(f"  [{name}] NO Signal class found — skipping")
            continue
        # WR + V3 are 1-min, 5-min strategies are 5-min
        if name.startswith("V3_") or name.startswith("WR_"):
            tf = "1m"
            intraday = m1; h, l, c = h_arr_1m, l_arr_1m, c_arr_1m
            contracts = 5
        else:
            tf = "5m"
            intraday = m5; h, l, c = h_arr_5m, l_arr_5m, c_arr_5m
            contracts = 30

        stop = float(info.get("stop_pts") or getattr(sig, "stop_pts", 15.0))
        target = float(info.get("target_pts") or getattr(sig, "target_pts", 30.0))
        max_hold = int(getattr(sig, "max_hold_bars", 80))
        side = info.get("side") or getattr(sig, "side", "LONG")

        try:
            df = sig.generate(intraday, daily)
        except Exception as e:
            print(f"  [{name}] generate failed: {e}")
            continue
        if df is None or df.empty:
            print(f"  [{name}] no entries"); continue
        sig_times = pd.DatetimeIndex(df["signal_time"])
        pos = intraday.index.get_indexer(sig_times)
        entries = [int(p) for p in pos if p >= 0 and p < len(intraday) - max_hold - 1]
        if not entries:
            continue

        pts = fixed_target_stop_simulate(h, l, c, entries, side, stop, target, max_hold)
        if not pts:
            continue
        pts_arr = np.asarray(pts)
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl_d = pts_arr * dpp - comm

        ny_idx = intraday.index[entries[: len(pts_arr)]].tz_convert(NY)
        ny_min = ny_idx.hour * 60 + ny_idx.minute

        wins = (pts_arr > 0).sum()
        wr = wins / len(pts_arr)
        per_strategy[name] = {
            "tier": info.get("tier"),
            "side": side,
            "tf": tf,
            "stop": stop, "target": target, "max_hold": max_hold,
            "contracts": contracts,
            "n_trades": int(len(pts_arr)),
            "win_rate": float(wr),
            "ev_dollars": float(pnl_d.mean()),
            "net_pnl": float(pnl_d.sum()),
            "rr": target / stop,
            "entries": entries[: len(pts_arr)],
            "pts": pts_arr.tolist(),
            "pnl": pnl_d.tolist(),
            "ny_min": ny_min.tolist(),
            "ts": ny_idx.tolist(),
        }
        for t_idx, p, pn, m, ts in zip(
            entries[: len(pts_arr)], pts_arr, pnl_d, ny_min, ny_idx
        ):
            all_trades.append({
                "strategy": name, "side": side,
                "entry_ts": ts, "pnl": float(pn),
                "ny_min": int(m), "session": session_for(int(m)),
                "tf": tf, "contracts": contracts,
            })
        print(f"  [{name:<25}] n={len(pts_arr):>5}  WR={wr*100:>5.1f}%  "
              f"net=${pnl_d.sum():+,.0f}")

    if not per_strategy:
        print("No strategies generated entries. Aborting.")
        return 1

    weeks = (m1.index[-1] - m1.index[0]).days / 7.0
    months = (m1.index[-1] - m1.index[0]).days / 30.4375

    # Strategy-level summary
    print("\n[3/4] Per-strategy frequency + time-of-day:\n", flush=True)
    print(f"{'name':<25} {'tier':<5} {'side':<6} {'WR':>6} {'RR':>5} "
          f"{'#trades':>8} {'/wk':>5} {'/mo':>5} {'net':>12} {'best session':>15}")
    print("-" * 102)

    strat_summary = {}
    for name, s in per_strategy.items():
        sessions: dict[str, list] = {}
        for m, p in zip(s["ny_min"], s["pnl"]):
            sess = session_for(m)
            sessions.setdefault(sess, []).append(p)

        sess_stats = {}
        for sess, pnls in sessions.items():
            arr = np.asarray(pnls)
            sess_stats[sess] = {
                "n_trades": int(len(arr)),
                "win_rate": float((arr > 0).mean()),
                "ev_dollars": float(arr.mean()),
                "net_pnl": float(arr.sum()),
                "share_of_volume": len(arr) / s["n_trades"],
            }
        # Best session = highest EV with at least 30 trades (so it's not noise)
        sized = [(sess, st) for sess, st in sess_stats.items() if st["n_trades"] >= 30]
        if sized:
            best = max(sized, key=lambda x: x[1]["ev_dollars"])
            best_label = f"{best[0]} (${best[1]['ev_dollars']:+.0f}/t)"
        else:
            best_label = "—"
        per_wk = s["n_trades"] / weeks
        per_mo = s["n_trades"] / months
        print(f"{name:<25} {s['tier']:<5} {s['side']:<6} {s['win_rate']*100:>5.1f}% "
              f"{s['rr']:>4.1f} {s['n_trades']:>8} {per_wk:>5.1f} {per_mo:>5.0f} "
              f"${s['net_pnl']:>+11,.0f} {best_label:>15}")
        strat_summary[name] = {
            "tier": s["tier"], "side": s["side"], "tf": s["tf"],
            "win_rate": s["win_rate"], "rr": s["rr"],
            "n_trades": s["n_trades"], "per_week": per_wk, "per_month": per_mo,
            "net_pnl": s["net_pnl"], "ev_dollars": s["ev_dollars"],
            "sessions": sess_stats,
            "best_session": best_label,
        }

    # Combined-trader simulation
    print("\n[4/4] Combined-trader simulation (one-position-at-a-time, 8 trades/day cap) ...",
          flush=True)
    # Sort all trades by entry time
    all_trades.sort(key=lambda t: t["entry_ts"])

    # Per-strategy approximate trade duration in MINUTES for the bot's lockout.
    durations = {n: per_strategy[n]["max_hold"] for n in per_strategy}
    # 5-min bars: max_hold=80 means 80 × 5 = 400 minutes; 1-min bars: minutes=max_hold
    def lockout_minutes(name):
        return durations[name] * (5 if per_strategy[name]["tf"] == "5m" else 1)

    open_until = pd.Timestamp.min.tz_localize("UTC")
    trades_today = 0
    today_date = None
    taken: list[dict] = []
    for t in all_trades:
        ts = t["entry_ts"]
        if today_date != ts.date():
            today_date = ts.date()
            trades_today = 0
        if trades_today >= 8:
            continue
        if ts < open_until:
            continue
        # Take the trade
        taken.append(t)
        open_until = ts + pd.Timedelta(minutes=lockout_minutes(t["strategy"]))
        trades_today += 1

    print(f"  raw signals across all strategies: {len(all_trades):,}")
    print(f"  realized trades after overlap + 8/day cap: {len(taken):,}  "
          f"({len(taken)/len(all_trades)*100:.0f}% of raw)")

    # Build monthly P&L series
    months_pnl = {}
    monthly_dd_sums = {}
    cum_eq = 50000.0
    eq_curve = [(taken[0]["entry_ts"] if taken else pd.Timestamp.now(tz="UTC"), cum_eq)]
    peak = cum_eq
    max_dd = 0.0
    for t in taken:
        cum_eq += t["pnl"]
        eq_curve.append((t["entry_ts"], cum_eq))
        peak = max(peak, cum_eq)
        dd = peak - cum_eq
        max_dd = max(max_dd, dd)
        ym = (t["entry_ts"].year, t["entry_ts"].month)
        months_pnl[ym] = months_pnl.get(ym, 0.0) + t["pnl"]

    n_months = len(months_pnl)
    monthly_pnls = list(months_pnl.values())
    median_month = float(np.median(monthly_pnls))
    mean_month = float(np.mean(monthly_pnls))
    p10_month = float(np.percentile(monthly_pnls, 10))
    p90_month = float(np.percentile(monthly_pnls, 90))
    best_month = float(np.max(monthly_pnls))
    worst_month = float(np.min(monthly_pnls))
    n_pos_months = sum(1 for x in monthly_pnls if x > 0)
    final_equity = cum_eq
    total_pnl = final_equity - 50000.0

    print(f"\n  starting equity   : $50,000")
    print(f"  final equity (8yr): ${final_equity:>12,.0f}")
    print(f"  total P&L          : ${total_pnl:>+12,.0f}")
    print(f"  max drawdown       : ${max_dd:>12,.0f}  ({max_dd/50000*100:.1f}% of starting)")
    print()
    print(f"  Monthly P&L distribution ({n_months} months):")
    print(f"    median month     : ${median_month:>+12,.0f}  ({median_month/50000*100:+.1f}%)")
    print(f"    mean month       : ${mean_month:>+12,.0f}  ({mean_month/50000*100:+.1f}%)")
    print(f"    p10 worst month  : ${p10_month:>+12,.0f}  ({p10_month/50000*100:+.1f}%)")
    print(f"    p90 best month   : ${p90_month:>+12,.0f}  ({p90_month/50000*100:+.1f}%)")
    print(f"    best month       : ${best_month:>+12,.0f}  ({best_month/50000*100:+.1f}%)")
    print(f"    worst month      : ${worst_month:>+12,.0f}  ({worst_month/50000*100:+.1f}%)")
    print(f"    positive months  : {n_pos_months}/{n_months}  ({n_pos_months/n_months*100:.0f}%)")

    # Combined session analysis
    print("\n  Realized trades by session (from combined-trader sim):")
    print(f"    {'session':<12} {'n':>6} {'WR':>6} {'EV/trade':>10} {'net':>12}")
    sess_taken: dict[str, list] = {}
    for t in taken:
        sess_taken.setdefault(t["session"], []).append(t["pnl"])
    for sess in ["NY_OPEN", "NY_MIDDAY", "NY_PM", "NY_AH", "ASIA", "LONDON"]:
        pnls = sess_taken.get(sess, [])
        if not pnls:
            continue
        arr = np.asarray(pnls)
        print(f"    {sess:<12} {len(arr):>6} {(arr>0).mean()*100:>5.1f}% "
              f"${arr.mean():>+9,.0f} ${arr.sum():>+11,.0f}")

    # Realized frequency
    days_traded = (taken[-1]["entry_ts"] - taken[0]["entry_ts"]).days if taken else 1
    real_per_wk = len(taken) * 7 / max(1, days_traded)
    real_per_mo = len(taken) * 30 / max(1, days_traded)
    print(f"\n  Realized trade frequency: ~{real_per_wk:.1f}/week  "
          f"(~{real_per_mo:.0f}/month)")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "starting_equity": 50000.0,
        "final_equity": final_equity,
        "total_pnl": total_pnl,
        "max_drawdown_dollars": max_dd,
        "max_drawdown_pct": max_dd / 50000 * 100,
        "n_months": n_months,
        "monthly_median": median_month,
        "monthly_mean": mean_month,
        "monthly_p10": p10_month,
        "monthly_p90": p90_month,
        "monthly_best": best_month,
        "monthly_worst": worst_month,
        "n_positive_months": n_pos_months,
        "raw_signals": len(all_trades),
        "realized_trades": len(taken),
        "realized_per_week": real_per_wk,
        "realized_per_month": real_per_mo,
        "per_strategy": strat_summary,
        "session_breakdown": {sess: {
            "n_trades": len(p), "win_rate": float((np.asarray(p) > 0).mean()),
            "ev_dollars": float(np.mean(p)), "net_pnl": float(np.sum(p)),
        } for sess, p in sess_taken.items()},
    }
    out_path = PROJECT_ROOT / "data" / "whitelist_analysis.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Wrote -> {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(run())

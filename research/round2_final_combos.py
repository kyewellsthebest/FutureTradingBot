"""Final combos and scaling for the winners. After round2 found:
  - WEEKOPEN_LONG_HOLD2d: $283/day per Sunday, DD $-2.3K — best risk/reward weekly
  - HOLD_24H_22UTC_LONG: $84/day, DD $-8.3K
  - HOLD_16H_22UTC_LONG: $51/day, DD $-2.9K — best daily risk/reward

Test:
  1. Optimal weekly hold parameter (sweep 1, 2, 3, 4, 5 days; LONG side)
  2. WEEKOPEN with different entry hours (24, 0, 1, 2)
  3. The combination: WEEKOPEN_LONG_HOLD2d on Sun + HOLD_24H on Mon-Thu
     (since Sun's 2-day hold ends Tue 22 UTC, the Tue 24h hold starts at Tue 22 UTC
     — they could be sequenced)
  4. Per-month consistency for combos
  5. Scaled position tests (2, 5, 10 MNQ)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")
from research.round2_strategies import (
    load_bars, simulate_trades,
    plans_hold_at_hour, plans_hold_session, plans_weekly_open,
    summarize, per_year_breakdown, per_dow_breakdown, per_month_breakdown,
    worst_30d_rolling,
    COMMISSION_RT, MNQ_PER_PT, OUT_DIR, TradePlan,
)


def plans_hold_at_hour_dow(bars_1m, hour, side, hold_minutes, tag, dow_set):
    """Helper: hold at hour, restrict to specific DOW set."""
    return plans_hold_at_hour(
        bars_1m, hour, 0, side, hold_minutes, tag,
        dow_filter=dow_set,
    )


def main():
    bars_1m = load_bars()
    print(f"Bars: {len(bars_1m):,} 1m")

    lines = []
    lines.append("# Round 2 Final Combos & Scaling\n\n")

    # ============================================================
    # 1. Weekly-open hold-duration sweep
    # ============================================================
    print("\n=== Weekly-open hold sweep ===")
    lines.append("## Weekly-open hold-duration sweep (Sun 22:00 UTC LONG)\n\n")
    lines.append("| Hold | trades | WR | PNL | per_day | DD | Sharpe | 2024 | 2025 | 2026 | worst30d |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    sweep_rows = []
    for hold_d in [1, 2, 3, 4, 5, 7, 10, 14, 21, 28]:
        plans = plans_weekly_open(bars_1m, hold_d, "LONG", f"WK_HOLD{hold_d}d")
        t = simulate_trades(bars_1m, plans)
        s = summarize(t, f"WK_HOLD{hold_d}d")
        y = per_year_breakdown(t)
        w30 = worst_30d_rolling(t)
        lines.append(
            f"| {hold_d}d | {s['trades']} | {s['wr']*100:.1f}% | ${s['pnl']:,.0f} | "
            f"${s['per_day']:.2f} | ${s['max_dd']:,.0f} | {s['sharpe']:.2f} | "
            f"${y.get(2024, 0):,.0f} | ${y.get(2025, 0):,.0f} | "
            f"${y.get(2026, 0):,.0f} | ${w30:,.0f} |\n")
        sweep_rows.append({"hold_d": hold_d, "pnl": s['pnl'], "per_day": s['per_day'],
                           "wr": s['wr'], "dd": s['max_dd']})
    lines.append("\n")
    pd.DataFrame(sweep_rows).to_csv(OUT_DIR / "round2_weekopen_sweep.csv", index=False)

    # ============================================================
    # 2. HOLD_24H_22UTC with various DOW filters
    # ============================================================
    print("\n=== HOLD_24H DOW filter sweep ===")
    lines.append("## HOLD_24H_22UTC_LONG with DOW filters\n\n")
    lines.append("From the unfiltered analysis: Sun has 72% WR ($17K), Tue has 63% WR ($10K), "
                 "Mon 59%, Wed 51%, Thu 61% but NEGATIVE ($-2K).\n\n")
    lines.append("| Filter | trades | WR | PNL | per_day | DD | Sharpe |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")
    dow_filters = {
        "ALL": None,
        "NO_THU (skip dow=3)": {0, 1, 2, 4, 6},
        "MON+SUN": {0, 6},
        "SUN+TUE+WED": {6, 1, 2},
        "WEEKDAYS_ONLY (skip Sun)": {0, 1, 2, 3, 4},
        "SUN_ONLY": {6},
        "TUE_ONLY": {1},
        "MON_ONLY": {0},
    }
    dow_filter_trades = {}
    for nm, dset in dow_filters.items():
        plans = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                    f"H24_{nm}", dow_filter=dset)
        t = simulate_trades(bars_1m, plans)
        s = summarize(t, nm)
        dow_filter_trades[nm] = t
        lines.append(
            f"| {nm} | {s['trades']} | {s['wr']*100:.1f}% | ${s['pnl']:,.0f} | "
            f"${s['per_day']:.2f} | ${s['max_dd']:,.0f} | {s['sharpe']:.2f} |\n")
    lines.append("\n")

    # ============================================================
    # 3. WEEKOPEN + WEEKDAY HOLD_24H combination
    # ============================================================
    print("\n=== WEEKOPEN + weekday HOLD_24H combination ===")
    # Sun 22:00 entry held 2d exits Tue 22:00. Then enter Tue 22:00 24h hold (exits Wed 22:00).
    # Then enter Wed 22:00 24h hold (exits Thu 22:00). Etc.
    # Or: Sun 22:00 held 5 days; this dominates the week — no extra trades.

    # Let me build a sequential strategy that:
    #  - On Sundays, enter LONG at first 22:00 UTC bar, hold for 2 days (exit Tue 22 UTC).
    #  - On Tue 22:00 UTC, enter LONG, hold 24h (exit Wed 22).
    #  - On Wed 22:00, enter LONG, hold 24h (exit Thu 22). SKIP Thu entry.
    # This gives 1 Sun trade + 2 weekday trades per week, with all 3 holding LONG bias.
    # But Sun's 2-day hold OVERLAPS Mon 22:00 — if we DO Mon 22 entry too we'd
    # need 2 contracts. Let's just do the SEQUENTIAL version: stop the Sun
    # hold's "effective hold" at 2d, then sequentially trade Tue, Wed.

    plans_sun = plans_weekly_open(bars_1m, 2, "LONG", "SUN_HOLD2d")
    plans_tue = plans_hold_at_hour(
        bars_1m, 22, 0, "LONG", 24*60, "TUE22_HOLD24h", dow_filter={1})
    plans_wed = plans_hold_at_hour(
        bars_1m, 22, 0, "LONG", 24*60, "WED22_HOLD24h", dow_filter={2})
    # Combine
    t_sun = simulate_trades(bars_1m, plans_sun)
    t_tue = simulate_trades(bars_1m, plans_tue)
    t_wed = simulate_trades(bars_1m, plans_wed)
    combo_seq = pd.concat([t_sun, t_tue, t_wed], ignore_index=True).sort_values("entry_ts")
    s_combo_seq = summarize(combo_seq, "SUN_HOLD2d_TUE24h_WED24h")
    lines.append("## SEQUENTIAL combo: Sun(2d) + Tue(24h) + Wed(24h)\n\n")
    lines.append(
        f"- Sun_HOLD2d alone: {len(t_sun)} tr, ${t_sun['pnl_usd'].sum():,.0f}\n"
        f"- Tue_HOLD24h alone: {len(t_tue)} tr, ${t_tue['pnl_usd'].sum():,.0f}\n"
        f"- Wed_HOLD24h alone: {len(t_wed)} tr, ${t_wed['pnl_usd'].sum():,.0f}\n\n"
    )
    lines.append(
        f"COMBO: {s_combo_seq['trades']} trades, WR {s_combo_seq['wr']*100:.1f}%, "
        f"PNL ${s_combo_seq['pnl']:,.0f}, "
        f"${s_combo_seq['per_day']:.2f}/trading-day, DD ${s_combo_seq['max_dd']:,.0f}, "
        f"Sharpe {s_combo_seq['sharpe']:.2f}\n\n"
    )
    ybd_seq = per_year_breakdown(combo_seq)
    lines.append("Per-year: " + ", ".join(
        f"{y}=${v:,.0f}" for y, v in sorted(ybd_seq.items())) + "\n\n")

    # ============================================================
    # 4. Per-month consistency of WEEKOPEN_2d
    # ============================================================
    print("\n=== WEEKOPEN_2d per-month ===")
    plans_wk2 = plans_weekly_open(bars_1m, 2, "LONG", "WK_HOLD2d")
    t_wk2 = simulate_trades(bars_1m, plans_wk2)
    s_wk2 = summarize(t_wk2, "WK_HOLD2d")
    lines.append("## WEEKOPEN_LONG_HOLD2d per-month\n\n")
    lines.append(f"Top contender at $283/day per Sunday with DD $-2,311 (small).\n\n")
    mb = per_month_breakdown(t_wk2)
    pos = (mb["pnl_usd"] > 0).sum()
    neg = (mb["pnl_usd"] < 0).sum()
    lines.append(f"**{pos} positive months, {neg} negative months.**\n\n")
    lines.append("| Month | PNL |\n|---|---:|\n")
    for _, row in mb.iterrows():
        lines.append(f"| {row['ym']} | ${row['pnl_usd']:,.0f} |\n")
    lines.append("\n")

    # ============================================================
    # 5. SCALING
    # ============================================================
    print("\n=== Scaling 1, 2, 5, 10 MNQ ===")
    lines.append("## Position scaling — Sharpe stays the same, DD scales linearly\n\n")
    scale_strats = [
        ("WEEKOPEN_LONG_HOLD2d (best Sharpe weekly)", t_wk2),
        ("HOLD_24H_22UTC_LONG", simulate_trades(bars_1m,
            plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60, "H24"))),
        ("HOLD_16H_22UTC_LONG (best daily Sharpe)", simulate_trades(bars_1m,
            plans_hold_at_hour(bars_1m, 22, 0, "LONG", 16*60, "H16"))),
        ("SUN_HOLD2d+TUE24h+WED24h", combo_seq),
        ("HOLD_24H NO_THU", dow_filter_trades["NO_THU (skip dow=3)"]),
    ]
    lines.append("| Strategy | 1 MNQ /day | 1 MNQ DD | $200/day MNQ | $200 DD | Sharpe |\n")
    lines.append("|---|---:|---:|---:|---:|---:|\n")
    for nm, tt in scale_strats:
        if tt.empty: continue
        ss = summarize(tt, nm)
        per_day = ss["per_day"]
        dd = ss["max_dd"]
        sharpe = ss["sharpe"]
        if per_day <= 0:
            continue
        mnq_200 = max(1, int(np.ceil(200 / per_day)))
        lines.append(
            f"| {nm} | ${per_day:.2f} | ${dd:,.0f} | "
            f"{mnq_200} | ${dd * mnq_200:,.0f} | {sharpe:.2f} |\n")
    lines.append("\n")

    # ============================================================
    # 6. The "pure Sunday-only" portfolio at scaled size
    # ============================================================
    print("\n=== Pure Sunday-only at scaled size ===")
    lines.append("## Pure Sunday-only WEEKOPEN_HOLD2d at scaled size\n\n")
    s_wk2_summary = summarize(t_wk2, "WK_HOLD2d")
    lines.append(f"Backtest result (1 MNQ): {s_wk2_summary['trades']} trades, "
                 f"WR {s_wk2_summary['wr']*100:.1f}%, "
                 f"${s_wk2_summary['pnl']:,.0f} total, "
                 f"${s_wk2_summary['per_day']:.2f}/trade-day, "
                 f"DD ${s_wk2_summary['max_dd']:,.0f}, "
                 f"Sharpe {s_wk2_summary['sharpe']:.2f}\n\n")
    lines.append("At N MNQ contracts, all P&L and DD multiply by N:\n\n")
    lines.append("| MNQ | $/Sunday | Total PNL | DD | weekly avg $ |\n")
    lines.append("|---:|---:|---:|---:|---:|\n")
    weeks = s_wk2_summary['n_days']
    for n_mnq in [1, 2, 3, 5, 7, 10]:
        wk_avg = s_wk2_summary['pnl'] / weeks * n_mnq
        lines.append(
            f"| {n_mnq} | ${s_wk2_summary['per_day'] * n_mnq:.2f} | "
            f"${s_wk2_summary['pnl'] * n_mnq:,.0f} | "
            f"${s_wk2_summary['max_dd'] * n_mnq:,.0f} | "
            f"${wk_avg:,.0f} |\n"
        )
    lines.append("\n")

    # Save the doc
    with open(OUT_DIR / "round2_final_combos.md", "w") as f:
        f.writelines(lines)
    print(f"\nWrote {OUT_DIR}/round2_final_combos.md")


if __name__ == "__main__":
    main()

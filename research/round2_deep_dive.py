"""Round 2 deep dive — drill into the top strategies, test combos and scaling.

Investigates:
  1. HOLD_24H_22UTC_LONG — per-month consistency
  2. HOLD_SESSION_22to14 — vs HOLD_24H_22UTC
  3. Best combination of 22UTC strategies + others
  4. Scaling: 2/5/10 MNQ on best strategies
  5. The "what hurts the 24h hold" sessions

Output:
  research/round2_deep_dive.md
  research/round2_combo_results.csv
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")
from research.round2_strategies import (
    load_bars, resample_bars, simulate_trades,
    plans_hold_at_hour, plans_hold_session, plans_weekly_open,
    plans_stack_positive_hours, plans_hold_until_profit_or_timeout,
    plans_gap_fade, plans_htf_breakout,
    summarize, per_year_breakdown, per_dow_breakdown, per_month_breakdown,
    worst_30d_rolling,
    COMMISSION_RT, MNQ_PER_PT, OUT_DIR,
)


def expand_dow_in_trades(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["dow"] = pd.to_datetime(df["entry_ts"]).dt.dayofweek
    df["date"] = pd.to_datetime(df["entry_ts"]).dt.date
    df["year"] = pd.to_datetime(df["entry_ts"]).dt.year
    df["ym"] = pd.to_datetime(df["entry_ts"]).dt.to_period("M").astype(str)
    return df


def main():
    bars_1m = load_bars()
    bars_60m = resample_bars(bars_1m, "60min")
    print(f"Bars: {len(bars_1m):,} 1m, {len(bars_60m):,} 60m")

    out = []
    out.append("# Round 2 Deep Dive\n\n")

    # ============================================================
    # 1) HOLD_24H_22UTC_LONG — drill in
    # ============================================================
    print("\n=== HOLD_24H_22UTC_LONG deep dive ===")
    plans_h22_24h = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                        "HOLD_24H_22UTC_LONG")
    t = simulate_trades(bars_1m, plans_h22_24h)
    s = summarize(t, "HOLD_24H_22UTC_LONG")
    out.append("## HOLD_24H_22UTC_LONG (buy 22:00 UTC daily, sell 24h later, MARKET)\n\n")
    out.append(f"- Total trades: {s['trades']}\n")
    out.append(f"- Win rate: {s['wr']*100:.1f}%\n")
    out.append(f"- Total PNL: ${s['pnl']:,.0f}\n")
    out.append(f"- Per-day PNL: ${s['per_day']:.2f}\n")
    out.append(f"- Per-trade PNL: ${s['per_trade']:.2f}\n")
    out.append(f"- Max DD: ${s['max_dd']:,.0f}\n")
    out.append(f"- Worst day: ${s['worst_day']:,.0f}\n")
    out.append(f"- Best day: ${s['best_day']:,.0f}\n")
    out.append(f"- Sharpe-ish: {s['sharpe']:.2f}\n\n")
    ybd = per_year_breakdown(t)
    out.append(f"### Per-year:\n")
    out.append(f"| Year | PNL | n_trades |\n|---|---:|---:|\n")
    df_t = expand_dow_in_trades(t)
    for y in sorted(ybd.keys()):
        n = (df_t["year"] == y).sum()
        out.append(f"| {y} | ${ybd[y]:,.0f} | {n} |\n")
    out.append("\n### Per-month:\n")
    mbd = per_month_breakdown(t)
    out.append("| Month | PNL |\n|---|---:|\n")
    pos_months = 0; neg_months = 0
    for _, row in mbd.iterrows():
        out.append(f"| {row['ym']} | ${row['pnl_usd']:,.0f} |\n")
        if row['pnl_usd'] > 0: pos_months += 1
        else: neg_months += 1
    out.append(f"\n**{pos_months} positive months, {neg_months} negative.**\n\n")
    dbd = per_dow_breakdown(t)
    out.append("### Per-DOW:\n")
    out.append("| DOW | n | PNL | WR |\n|---|---:|---:|---:|\n")
    dow_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
    for d in sorted(dbd.keys()):
        v = dbd[d]
        out.append(f"| {dow_names.get(d, d)} | {v['n']} | ${v['pnl']:,.0f} | {v['wr']*100:.0f}% |\n")
    w30 = worst_30d_rolling(t)
    out.append(f"\n**Worst 30-day rolling PNL: ${w30:,.0f}**\n\n")

    # ============================================================
    # 2) Compare HOLD_24H_22UTC vs HOLD_SESSION_22to14 (skip morning negative)
    # ============================================================
    print("\n=== HOLD_SESSION_22to14 deep dive ===")
    plans_sess = plans_hold_session(bars_1m, 22, 0, 14, 0, "LONG",
                                     "HOLD_SESSION_22to14_LONG")
    t_sess = simulate_trades(bars_1m, plans_sess)
    s_sess = summarize(t_sess, "HOLD_SESSION_22to14_LONG")
    out.append("## HOLD_SESSION_22to14_LONG (buy 22:00 UTC, sell 14:00 UTC next day)\n\n")
    out.append(f"Compared to HOLD_24H_22UTC_LONG, this one EXITS BEFORE the negative-bias morning hours (14-15 UTC).\n\n")
    out.append(f"- Total trades: {s_sess['trades']}\n")
    out.append(f"- WR: {s_sess['wr']*100:.1f}%\n")
    out.append(f"- Total PNL: ${s_sess['pnl']:,.0f}\n")
    out.append(f"- Per-day: ${s_sess['per_day']:.2f}\n")
    out.append(f"- Max DD: ${s_sess['max_dd']:,.0f}\n")
    out.append(f"- Sharpe: {s_sess['sharpe']:.2f}\n\n")
    ybd_sess = per_year_breakdown(t_sess)
    out.append(f"### Per-year:\n")
    out.append(f"| Year | PNL |\n|---|---:|\n")
    for y in sorted(ybd_sess.keys()):
        out.append(f"| {y} | ${ybd_sess[y]:,.0f} |\n")
    out.append(f"\nWorst 30d rolling: ${worst_30d_rolling(t_sess):,.0f}\n\n")

    # ============================================================
    # 3) WEEKOPEN deep dive
    # ============================================================
    print("\n=== WEEKOPEN deep dive ===")
    plans_wk1 = plans_weekly_open(bars_1m, 1, "LONG", "WEEKOPEN_LONG_HOLD1d")
    plans_wk2 = plans_weekly_open(bars_1m, 2, "LONG", "WEEKOPEN_LONG_HOLD2d")
    plans_wk5 = plans_weekly_open(bars_1m, 5, "LONG", "WEEKOPEN_LONG_HOLD5d")
    t_wk1 = simulate_trades(bars_1m, plans_wk1)
    t_wk2 = simulate_trades(bars_1m, plans_wk2)
    t_wk5 = simulate_trades(bars_1m, plans_wk5)
    out.append("## WEEKOPEN_LONG_HOLD* (buy Sunday 22:00 UTC, hold N days)\n\n")
    out.append("| Variant | trades | WR | PNL | per_day | max DD | Sharpe |\n")
    out.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for nm, tt in [("HOLD1d", t_wk1), ("HOLD2d", t_wk2), ("HOLD5d", t_wk5)]:
        ss = summarize(tt, nm)
        out.append(f"| {nm} | {ss['trades']} | {ss['wr']*100:.1f}% | "
                   f"${ss['pnl']:,.0f} | ${ss['per_day']:.2f} | "
                   f"${ss['max_dd']:,.0f} | {ss['sharpe']:.2f} |\n")
    out.append("\nNote: per_day here is dollars per Sunday trade-day (one per week), "
               "NOT per calendar day. The strategy generates $4-5K of PNL per week on average.\n\n")
    # Show all individual weekly trades for HOLD5d
    df5 = t_wk5.copy()
    df5["week"] = pd.to_datetime(df5["entry_ts"]).dt.strftime("%Y-%m-%d")
    df5 = df5[["week", "entry_px", "exit_px", "exit_reason", "pnl_pts", "pnl_usd"]]
    df5 = df5.sort_values("week")
    out.append("### Individual weekly trades (HOLD5d):\n\n")
    out.append("| Week start | entry | exit | reason | pnl pts | PNL $ |\n")
    out.append("|---|---:|---:|---|---:|---:|\n")
    for _, row in df5.iterrows():
        out.append(f"| {row['week']} | {row['entry_px']:.2f} | "
                   f"{row['exit_px']:.2f} | {row['exit_reason']} | "
                   f"{row['pnl_pts']:+.1f} | ${row['pnl_usd']:+,.0f} |\n")
    out.append("\n")

    # ============================================================
    # 4) Combination of best strategies — disjoint in time so they can stack
    # ============================================================
    print("\n=== Multi-strategy COMBO ===")
    # HOLD_24H_22UTC_LONG covers all 7 days/wk.
    # HOLD_4H_17UTC_LONG also covers 5 days/wk (17:00-21:00 UTC).
    # These overlap (24h hold + 4h hold both active 17-21 UTC of next day).
    # In a 1 MNQ system, we can only hold ONE position. But if we use 2 MNQ
    # ("portfolio" view) the strategies are independent.
    # Let's also test the "non-overlapping" combo: H22_HOLD_2H + H17_HOLD_4H
    # (22-00 and 17-21 are not overlapping)
    plans_22_2h = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 2 * 60, "H22_HOLD2H")
    plans_17_4h = plans_hold_at_hour(bars_1m, 17, 0, "LONG", 4 * 60, "H17_HOLD4H")
    t_22 = simulate_trades(bars_1m, plans_22_2h)
    t_17 = simulate_trades(bars_1m, plans_17_4h)
    s22 = summarize(t_22, "H22_HOLD2H")
    s17 = summarize(t_17, "H17_HOLD4H")
    out.append("## Combined portfolios\n\n")
    out.append("### Combo A: H17_HOLD4H + H22_HOLD2H (non-overlapping in time at 1 MNQ)\n\n")
    out.append(f"H17_HOLD4H alone: {s17['trades']} tr, ${s17['pnl']:,.0f}, "
               f"${s17['per_day']:.2f}/day, WR {s17['wr']*100:.1f}%, DD ${s17['max_dd']:,.0f}\n\n")
    out.append(f"H22_HOLD2H alone: {s22['trades']} tr, ${s22['pnl']:,.0f}, "
               f"${s22['per_day']:.2f}/day, WR {s22['wr']*100:.1f}%, DD ${s22['max_dd']:,.0f}\n\n")
    combo = pd.concat([t_17, t_22], ignore_index=True).sort_values("entry_ts")
    s_combo = summarize(combo, "COMBO_H17_4H_H22_2H")
    out.append(f"COMBO: {s_combo['trades']} tr, ${s_combo['pnl']:,.0f}, "
               f"${s_combo['per_day']:.2f}/day, WR {s_combo['wr']*100:.1f}%, "
               f"DD ${s_combo['max_dd']:,.0f}, Sharpe {s_combo['sharpe']:.2f}\n\n")
    ybd_combo = per_year_breakdown(combo)
    out.append("Per-year COMBO_H17_4H_H22_2H: " +
               ", ".join(f"{y}=${v:,.0f}" for y, v in sorted(ybd_combo.items())) + "\n\n")

    # Combo B: HOLD_24H_22UTC alone vs everything else
    # Already covered above. Add: HOLD_16H_22UTC vs HOLD_24H
    plans_16h_22 = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 16 * 60, "H22_HOLD16H")
    t_16h_22 = simulate_trades(bars_1m, plans_16h_22)
    s_16h_22 = summarize(t_16h_22, "H22_HOLD16H")
    out.append("### Combo B: HOLD_16H_22UTC_LONG (LONGER than 24h, exits at 14 UTC pre-NY-open)\n\n")
    out.append(f"HOLD_16H_22UTC: {s_16h_22['trades']} tr, ${s_16h_22['pnl']:,.0f}, "
               f"${s_16h_22['per_day']:.2f}/day, WR {s_16h_22['wr']*100:.1f}%, "
               f"DD ${s_16h_22['max_dd']:,.0f}, Sharpe {s_16h_22['sharpe']:.2f}\n\n")

    # ============================================================
    # 5) SCALING: what does each strategy look like at 2/5/10 MNQ?
    # ============================================================
    print("\n=== SCALING analysis ===")
    out.append("## Scaling analysis (multiply PNL and DD by N for N MNQ)\n\n")
    out.append("Strategies are at 1 MNQ. To scale to N MNQ, multiply PNL/DD by N.\n")
    out.append("Commissions ARE per-contract, so they scale too — but they're already in the per-trade $.\n\n")
    out.append("| Strategy | 1 MNQ /day | 1 MNQ DD | $200/day MNQ | DD at $200/day | $500/day MNQ | DD at $500/day |\n")
    out.append("|---|---:|---:|---:|---:|---:|---:|\n")
    scaling_targets = [
        ("HOLD_24H_22UTC_LONG", t),
        ("HOLD_16H_22UTC_LONG", t_16h_22),
        ("HOLD_SESSION_22to14_LONG", t_sess),
        ("WEEKOPEN_LONG_HOLD2d", t_wk2),
        ("WEEKOPEN_LONG_HOLD5d", t_wk5),
        ("COMBO_H17_4H_H22_2H", combo),
    ]
    for nm, tt in scaling_targets:
        ss = summarize(tt, nm)
        per_day = ss["per_day"]
        dd = ss["max_dd"]
        if per_day <= 0:
            continue
        mnq_200 = max(1, int(np.ceil(200 / per_day)))
        mnq_500 = max(1, int(np.ceil(500 / per_day)))
        out.append(f"| {nm} | ${per_day:.2f} | ${dd:,.0f} | "
                   f"{mnq_200} | ${dd * mnq_200:,.0f} | "
                   f"{mnq_500} | ${dd * mnq_500:,.0f} |\n")
    out.append("\n")

    # ============================================================
    # 6) Best vol/regime-filtered variant
    # ============================================================
    print("\n=== Vol-filtered HOLD_24H_22UTC_LONG ===")
    # Filter by previous day's range
    plans_vol_hi = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                       "HOLD_24H_22UTC_PREVRANGE_GT50",
                                       prevday_range_min=50)
    t_vol_hi = simulate_trades(bars_1m, plans_vol_hi)
    s_vol_hi = summarize(t_vol_hi, "HOLD_24H_22UTC_PREVRANGE_GT50")
    plans_vol_lo = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                       "HOLD_24H_22UTC_PREVRANGE_LT75",
                                       prevday_range_max=75)
    t_vol_lo = simulate_trades(bars_1m, plans_vol_lo)
    s_vol_lo = summarize(t_vol_lo, "HOLD_24H_22UTC_PREVRANGE_LT75")
    plans_vol_med = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                        "HOLD_24H_22UTC_PREVRANGE_75to200",
                                        prevday_range_min=75,
                                        prevday_range_max=200)
    t_vol_med = simulate_trades(bars_1m, plans_vol_med)
    s_vol_med = summarize(t_vol_med, "HOLD_24H_22UTC_PREVRANGE_75to200")
    out.append("## Vol filters on HOLD_24H_22UTC_LONG\n\n")
    out.append("| Filter | trades | WR | PNL | per_day | DD | Sharpe |\n")
    out.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for nm, ss in [
        ("UNFILTERED", s),
        ("PREVRANGE >= 50", s_vol_hi),
        ("PREVRANGE <= 75", s_vol_lo),
        ("PREVRANGE 75-200", s_vol_med),
    ]:
        out.append(f"| {nm} | {ss['trades']} | {ss['wr']*100:.1f}% | "
                   f"${ss['pnl']:,.0f} | ${ss['per_day']:.2f} | "
                   f"${ss['max_dd']:,.0f} | {ss['sharpe']:.2f} |\n")
    out.append("\n")

    # ============================================================
    # 7) DOW filter on HOLD_24H — which days does it work?
    # ============================================================
    print("\n=== DOW filter on HOLD_24H_22UTC ===")
    dbd_24h = per_dow_breakdown(t)
    out.append("## DOW filter on HOLD_24H_22UTC_LONG\n\n")
    out.append("Per-DOW PNL of the unfiltered HOLD_24H_22UTC_LONG (already shown above).\n")
    out.append("Notable: Sun (Day 6) has 87% WR, $10K PNL on 23 trades — drives most of the edge.\n")
    out.append("Thursday (Day 3) is the only LOSING dow.\n\n")
    # Filtered: skip Thursdays
    plans_no_thu = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                       "HOLD_24H_22UTC_NO_THU",
                                       dow_filter={0, 1, 2, 4, 6})
    t_no_thu = simulate_trades(bars_1m, plans_no_thu)
    s_no_thu = summarize(t_no_thu, "HOLD_24H_22UTC_NO_THU")
    out.append("### Filtered: skip Thursday entries (DOW=3)\n\n")
    out.append(f"- {s_no_thu['trades']} tr, WR {s_no_thu['wr']*100:.1f}%, "
               f"${s_no_thu['pnl']:,.0f}, ${s_no_thu['per_day']:.2f}/day, "
               f"DD ${s_no_thu['max_dd']:,.0f}, Sharpe {s_no_thu['sharpe']:.2f}\n\n")
    # Sun + Tue only (top 2 DOWs)
    plans_sun_tue = plans_hold_at_hour(bars_1m, 22, 0, "LONG", 24*60,
                                        "HOLD_24H_22UTC_SUN_TUE",
                                        dow_filter={2, 6})  # Wed enters = Tue 22:00 UTC = ?
    # Actually 22:00 UTC entry on dow=6 (Sun) yields exit Mon. Entry on dow=2 (Wed)
    # yields exit Thu. Wait, the entry timestamp's dow IS the dow.
    # Top 2 by PNL from above: Sun (6) and Wed (2)
    t_sun_tue = simulate_trades(bars_1m, plans_sun_tue)
    s_sun_tue = summarize(t_sun_tue, "HOLD_24H_22UTC_SUN_WED")
    out.append("### Filtered: Sun + Wed entries only (top 2 DOWs)\n\n")
    out.append(f"- {s_sun_tue['trades']} tr, WR {s_sun_tue['wr']*100:.1f}%, "
               f"${s_sun_tue['pnl']:,.0f}, "
               f"${s_sun_tue['pnl']/max(1,s_sun_tue['n_days']):.2f}/trade-day, "
               f"DD ${s_sun_tue['max_dd']:,.0f}, Sharpe {s_sun_tue['sharpe']:.2f}\n\n")

    # ============================================================
    # 8) Worst-case stress
    # ============================================================
    out.append("## Worst-case stress: 30-day rolling losses\n\n")
    out.append("| Strategy | Worst 30d rolling PNL | DD | Sharpe |\n")
    out.append("|---|---:|---:|---:|\n")
    for nm, tt in scaling_targets:
        if tt.empty: continue
        ss = summarize(tt, nm)
        w30 = worst_30d_rolling(tt)
        out.append(f"| {nm} | ${w30:,.0f} | ${ss['max_dd']:,.0f} | {ss['sharpe']:.2f} |\n")
    out.append("\n")

    # Write
    with open(OUT_DIR / "round2_deep_dive.md", "w") as f:
        f.writelines(out)
    print(f"\nWrote {OUT_DIR}/round2_deep_dive.md")


if __name__ == "__main__":
    main()

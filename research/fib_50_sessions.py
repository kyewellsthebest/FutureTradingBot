"""Coarser cuts of the time-of-day analysis: 2-hr session blocks + DOW."""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

from research.fib_50_time_of_day import (
    DATA_FILE, PIVOT_K, HTF_PIVOT_K, find_pivots, build_pivot_track,
    build_htf_trend, run_strategy,
)


SESSIONS = [
    ("Asia",        (18, 0), (3, 0)),     # 18:00 ET prev → 03:00 ET (overnight)
    ("EU pre",      (3, 0),  (7, 0)),
    ("EU late",     (7, 0),  (9, 30)),
    ("NY open",     (9, 30), (11, 0)),
    ("NY mid",      (11, 0), (13, 0)),
    ("NY pm",       (13, 0), (15, 0)),
    ("NY close",    (15, 0), (16, 30)),
    ("Post close",  (16, 30),(18, 0)),
]


def in_session(ts_ny, start, end) -> bool:
    """Return True if ts_ny.time() ∈ [start, end). Handles wrap-around."""
    s_min = start[0] * 60 + start[1]
    e_min = end[0]   * 60 + end[1]
    t_min = ts_ny.hour * 60 + ts_ny.minute
    if s_min < e_min:
        return s_min <= t_min < e_min
    return t_min >= s_min or t_min < e_min   # wraps midnight


def session_label(ts):
    ny = ts.tz_convert("America/New_York") if ts.tz is not None \
         else ts.tz_localize("UTC").tz_convert("America/New_York")
    for name, s, e in SESSIONS:
        if in_session(ny, s, e):
            return name
    return "other"


def main() -> None:
    print("Loading 1-min NQ data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    print(f"  bars: {len(nq):,}")

    h = nq["high"].to_numpy(); l = nq["low"].to_numpy()
    highs3, lows3 = find_pivots(h, l, PIVOT_K)
    highs5, lows5 = find_pivots(h, l, HTF_PIVOT_K)
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs3, lows3, PIVOT_K, len(nq))
    htf = build_htf_trend(highs5, lows5, HTF_PIVOT_K, len(nq))
    trades = run_strategy(nq, rh_src, rh_val, rl_src, rl_val, htf)
    print(f"  trades: {len(trades):,}\n")

    tdf = pd.DataFrame(trades)
    et = pd.to_datetime(tdf["entry_ts"])
    if et.dt.tz is None:
        et = et.dt.tz_localize("UTC")
    ny = et.dt.tz_convert("America/New_York")
    tdf["session"] = ny.apply(lambda x: session_label(x))
    tdf["dow"]     = ny.dt.day_name()

    def report(label, df_grp):
        print(f"\n{label}")
        print("-" * 80)
        print(f"{'Bucket':<14} {'n':>6} {'WR':>7} {'PF':>6} "
              f"{'$/tr':>9} {'Total':>11}")
        for name, g in df_grp:
            n = len(g)
            wr = (g['pnl_usd'] > 0).mean()
            gw = g[g['pnl_usd'] > 0]['pnl_usd'].sum()
            gl = abs(g[g['pnl_usd'] < 0]['pnl_usd'].sum())
            pf = gw/gl if gl else float('inf')
            tot = g['pnl_usd'].sum()
            print(f"{name:<14} {n:>6} {wr*100:>6.1f}% {pf:>5.2f} "
                  f"${tot/n:>+7,.0f} ${tot:>+9,.0f}")

    order = [s[0] for s in SESSIONS]
    by_sess = sorted(tdf.groupby("session"), key=lambda kv: order.index(kv[0]) if kv[0] in order else 999)
    report("BY SESSION (2-hr+ blocks, NY time)", by_sess)

    dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Sunday"]
    by_dow = sorted(tdf.groupby("dow"), key=lambda kv: dow_order.index(kv[0]) if kv[0] in dow_order else 999)
    report("BY DAY OF WEEK", by_dow)

    # Trend-strength of HTF — strong trend hours vs weak
    print("\n\nDAY-LEVEL EFFICIENCY VS BOT P&L")
    print("-" * 80)
    # compute per-day directional efficiency on RTH (9:30-16:00 NY)
    nq_ny = nq.copy()
    nq_ny.index = nq_ny.index.tz_convert("America/New_York")
    rth = nq_ny.between_time("09:30", "16:00").copy()
    rth["date"] = rth.index.date
    eff_by_day = []
    for date, g in rth.groupby("date"):
        if len(g) < 30:
            continue
        net = abs(float(g["close"].iloc[-1]) - float(g["open"].iloc[0]))
        path = float(g["close"].diff().abs().sum())
        if path == 0: continue
        eff_by_day.append({"date": date, "efficiency": net/path,
                           "net_pts": net})
    eff_df = pd.DataFrame(eff_by_day)
    eff_df["bin"] = pd.cut(
        eff_df["efficiency"],
        bins=[-0.01, 0.10, 0.20, 0.30, 0.50, 1.01],
        labels=["very_chop(<.10)", "chop(.10-.20)", "mixed(.20-.30)",
                "trendy(.30-.50)", "strong(>.50)"],
    )
    et_dates = ny.dt.date
    tdf["date"] = et_dates
    tdf = tdf.merge(eff_df[["date","bin","efficiency"]], on="date", how="left")
    by_bin = tdf.dropna(subset=["bin"]).groupby("bin", observed=False)
    print(f"{'Day type':<22} {'n':>6} {'WR':>7} {'PF':>6} {'$/tr':>9} {'Total':>11}")
    for name, g in by_bin:
        if len(g) == 0: continue
        wr = (g['pnl_usd'] > 0).mean()
        gw = g[g['pnl_usd'] > 0]['pnl_usd'].sum()
        gl = abs(g[g['pnl_usd'] < 0]['pnl_usd'].sum())
        pf = gw/gl if gl else float('inf')
        tot = g['pnl_usd'].sum()
        print(f"{str(name):<22} {len(g):>6} {wr*100:>6.1f}% {pf:>5.2f} "
              f"${tot/len(g):>+7,.0f} ${tot:>+9,.0f}")

if __name__ == "__main__":
    main()

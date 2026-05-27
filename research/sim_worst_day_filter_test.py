"""Worst-trending-day analysis — find the 5 worst pure-trend days in the
3-month tick dataset (analogues to last night's bull run), show baseline
losses on those days, then test multiple filters and report savings.

Approach:
  1. Compute each NY-date's net move (close[-1] - close[0]) in absolute pt
  2. Take top 10 by abs(net_move) — these are the "trending days"
  3. Slice the dataset to ONLY those days, run baseline + each filter
  4. Report per-day baseline P&L vs filtered P&L

User's suggestion: "3 continuous candles 10-15pt each" momentum lock —
implemented as `trend_consecutive_bars`. Plus daily-net-move + EMA filters
from sim_trend_filter_sweep.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)
from research.sim_trend_filter_sweep import (
    trend_netmove, trend_ema_slope, trend_breadth, apply_filter
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/worst_day_filter_test.json")


def trend_consecutive_bars(bars: pd.DataFrame, n_bars: int, min_pts: float):
    """User's idea: N consecutive 1-min bars all moving in same direction
    by at least min_pts each = strong momentum lock. Bias persists for the
    next 30 minutes after detection so the filter doesn't oscillate."""
    o = bars["open"].to_numpy(); c = bars["close"].to_numpy()
    bias = np.zeros(len(bars), dtype=np.int8)
    move = c - o
    hold_bars = 30   # how long the lock persists after the signal
    locked_until = -1; locked_dir = 0
    for i in range(n_bars, len(bars)):
        # check last n_bars all moved >= min_pts in same direction
        recent = move[i - n_bars + 1:i + 1]
        if np.all(recent >= min_pts):
            locked_until = i + hold_bars; locked_dir = 1
        elif np.all(recent <= -min_pts):
            locked_until = i + hold_bars; locked_dir = -1
        if i <= locked_until:
            bias[i] = locked_dir
    return bias


def worst_day_test():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)
    print(f"Loaded {len(df):,} ticks, {len(bars):,} 1-min bars ({period_days:.0f}d)")

    # Find worst-trending days (by abs net move per NY date)
    bars_ny = bars.tz_convert("America/New_York")
    bars_ny["ny_date"] = bars_ny.index.date
    daily = bars_ny.groupby("ny_date").agg(open=("open", "first"),
                                            close=("close", "last"),
                                            high=("high", "max"),
                                            low=("low", "min"))
    daily["net_pts"] = daily["close"] - daily["open"]
    daily["abs_net"] = daily["net_pts"].abs()
    daily = daily.sort_values("abs_net", ascending=False)
    top_days = daily.head(10).index.tolist()
    print(f"\nTop 10 trending days (NY date, |net_move|):")
    for d in top_days:
        row = daily.loc[d]
        direction = "UP" if row["net_pts"] > 0 else "DN"
        print(f"  {d}  {direction}  net={row['net_pts']:>+7.1f}pt  "
              f"range={row['high']-row['low']:>5.1f}pt")

    # Setups produced by baseline (account 2 target=18 — the riskier config)
    print("\nRunning baseline target=18 sim over full period...")
    base_setups_t18 = []
    for s in baseline_setups(bars):
        side = s["side"]; entry = s["entry_px"]
        target = entry + 18.0 if side == 1 else entry - 18.0
        base_setups_t18.append({**s, "target_px": target})

    # Filter variants to test
    filters = {
        "BASELINE (no filter)":              None,
        "daily_netmove(8h,>=60pt)":          trend_netmove(bars, lookback=8*60, threshold_pts=60),
        "daily_netmove(8h,>=100pt)":         trend_netmove(bars, lookback=8*60, threshold_pts=100),
        "daily_netmove(16h,>=150pt)":        trend_netmove(bars, lookback=16*60, threshold_pts=150),
        "ema_slope(60,60,>=3*ATR)":          trend_ema_slope(bars, ema_span=60, lookback=60, atr_mult=3.0),
        # User's idea: N consecutive bars all moving X pts same dir
        "consec(3 bars,>=10pt each)":        trend_consecutive_bars(bars, n_bars=3, min_pts=10.0),
        "consec(3 bars,>=15pt each)":        trend_consecutive_bars(bars, n_bars=3, min_pts=15.0),
        "consec(5 bars,>=8pt each)":         trend_consecutive_bars(bars, n_bars=5, min_pts=8.0),
        "consec(4 bars,>=12pt each)":        trend_consecutive_bars(bars, n_bars=4, min_pts=12.0),
    }

    # For each filter, compute the trades + per-day P&L breakdown
    print(f"\n{'Filter':<40}{'OVERALL':>20}{'WORST 10 DAYS':>22}")
    print(f"{'':<40}{'ret/mo':>10}{'DD%':>10}{'baseline':>12}{'filtered':>10}")
    print("-" * 95)
    bar_ts = bars.index.astype("int64").to_numpy()
    results = {}
    for name, bias in filters.items():
        if bias is None:
            setups = base_setups_t18
        else:
            setups = apply_filter(base_setups_t18, bias, bars)
        trades = simulate(setups, price, ts_ns)
        if not trades:
            print(f"{name:<40}  no trades after filter")
            continue
        # Overall stats
        s = score(trades, period_days)
        # Per-day P&L on worst-10 days
        tdf = pd.DataFrame(trades)
        tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True).dt.tz_convert("America/New_York")
        tdf["ny_date"] = tdf["exit_dt"].dt.date
        day_pnl = tdf.groupby("ny_date")["pnl_usd"].sum()
        worst_day_pnl = sum(day_pnl.get(d, 0) for d in top_days)
        results[name] = {"overall": s, "worst10_pnl": round(worst_day_pnl, 0)}
        # For BASELINE, store baseline_worst for later comparison
        if name.startswith("BASELINE"):
            baseline_worst = worst_day_pnl
        savings = worst_day_pnl - baseline_worst if name != "BASELINE (no filter)" else 0
        sav_str = f"({savings:>+6,.0f})" if name != "BASELINE (no filter)" else ""
        print(f"{name:<40}{s['ret_mo']:>+9.2f}%{s['max_dd_pct']:>9.2f}%"
              f"{baseline_worst:>+12,.0f}{worst_day_pnl:>+10,.0f} {sav_str}")

    print("\n\nPer-day breakdown on the 10 worst trending days:")
    print(f"{'NY date':<14}{'net pt':>9}", end="")
    for name in filters:
        print(f"{name[:18]:>20}", end="")
    print()
    print("-" * (14 + 9 + 20 * len(filters)))
    # rebuild per-day pnl per filter
    perfilter_daily = {}
    for name, bias in filters.items():
        if bias is None: setups = base_setups_t18
        else: setups = apply_filter(base_setups_t18, bias, bars)
        trades = simulate(setups, price, ts_ns)
        tdf = pd.DataFrame(trades)
        tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True).dt.tz_convert("America/New_York")
        tdf["ny_date"] = tdf["exit_dt"].dt.date
        perfilter_daily[name] = tdf.groupby("ny_date")["pnl_usd"].sum().to_dict()
    for d in top_days:
        row = daily.loc[d]
        print(f"{str(d):<14}{row['net_pts']:>+8.0f} ", end="")
        for name in filters:
            v = perfilter_daily[name].get(d, 0)
            print(f"{v:>+19,.0f} ", end="")
        print()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "top_days": [{"date": str(d), **daily.loc[d].to_dict()} for d in top_days],
        "filters": {k: {**v["overall"], "worst10_pnl": v["worst10_pnl"]}
                    for k, v in results.items() if isinstance(v, dict)},
    }, indent=2, default=str))
    print(f"\nTotal: {time.time()-t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    worst_day_test()

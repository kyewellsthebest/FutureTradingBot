"""Worst-P&L-day forensics — flip the analysis: find the days the bot
actually LOST money on in the backtest, then characterize what they look
like pre-trade so we can build a filter that catches THEM.

The earlier worst-trending-days analysis showed baseline made money on
8/10 of the biggest move days. So the user is right -- the enemy isn't
"big move" days, it's something different. This script finds out what.

Outputs:
  1. Top 20 worst P&L days for baseline target=12 AND target=18
  2. Their characteristics: net move, range, ATR, # whipsaws, trend strength
  3. Comparison: how would those days have looked with different stop widths,
     setup filters, or pre-trade signals?
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, STARTING_BAL
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/worst_pnl_day_forensics.json")


def daily_characteristics(bars_1m: pd.DataFrame, ny_date) -> dict:
    """Pre-trade characterisable features for a single NY trading day."""
    bars_ny = bars_1m.tz_convert("America/New_York")
    day = bars_ny[bars_ny.index.date == ny_date]
    if len(day) < 30:
        return {}
    o, h, l, c = day["open"], day["high"], day["low"], day["close"]
    net = float(c.iloc[-1] - o.iloc[0])
    rng = float(h.max() - l.min())
    # ATR (14-bar rolling avg true range)
    tr = np.maximum.reduce([h.values - l.values,
                             np.abs(h.values - np.r_[c.iloc[0], c.values[:-1]]),
                             np.abs(l.values - np.r_[c.iloc[0], c.values[:-1]])])
    atr = float(pd.Series(tr).rolling(14).mean().iloc[-1])
    # Whipsaw count: how many times did 5-bar EMA reverse direction?
    ema = c.ewm(span=5, adjust=False).mean()
    slope_sign = np.sign(ema.diff(5)).fillna(0).to_numpy()
    reversals = int(np.sum(np.diff(slope_sign) != 0))
    # Body-vs-shadow ratio (trend bars vs noise bars)
    body = (c - o).abs()
    shadow = (h - l) - body
    body_pct = float(body.sum() / max(shadow.sum() + body.sum(), 1e-9))
    # Trend strength: |net| / range (high = clean trend, low = chop)
    trend_strength = abs(net) / max(rng, 1e-9)
    return {
        "net_pts": round(net, 1),
        "range_pts": round(rng, 1),
        "atr": round(atr, 2),
        "reversals_5bar_ema": reversals,
        "body_pct": round(body_pct * 100, 1),
        "trend_strength": round(trend_strength, 2),
        "n_bars": len(day),
    }


def daily_pnl_breakdown(trades, bars_1m):
    """Per-NY-date P&L from the trade list."""
    if not trades: return {}
    tdf = pd.DataFrame(trades)
    tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    tdf["ny_date"] = tdf["exit_dt"].dt.date
    return tdf.groupby("ny_date")["pnl_usd"].agg(["sum", "count"]).to_dict("index")


def run_baseline(bars, price, ts_ns, target_pts: float):
    setups = []
    for s in baseline_setups(bars):
        side = s["side"]; entry = s["entry_px"]
        tgt = entry + target_pts if side == 1 else entry - target_pts
        setups.append({**s, "target_px": tgt})
    return simulate(setups, price, ts_ns)


def main():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)
    print(f"Loaded {len(df):,} ticks, {len(bars):,} bars  ({time.time()-t0:.0f}s)")

    # Run both account configs
    for target_pts in (12.0, 18.0):
        label = "Account 1 (target=12)" if target_pts == 12.0 else "Account 2 (target=18)"
        print(f"\n=== {label} ===")
        trades = run_baseline(bars, price, ts_ns, target_pts)
        day_pnl = daily_pnl_breakdown(trades, bars)
        # Sort by P&L (worst first)
        days_sorted = sorted(day_pnl.items(), key=lambda kv: kv[1]["sum"])
        n_pos = sum(1 for k, v in days_sorted if v["sum"] > 0)
        n_neg = sum(1 for k, v in days_sorted if v["sum"] < 0)
        print(f"  {len(days_sorted)} trading days: {n_pos} winners, {n_neg} losers")
        print(f"\n  Top 15 WORST P&L days:")
        print(f"  {'NY date':<12}{'P&L':>10}{'n_tr':>6}  {'net':>7}{'rng':>7}{'atr':>6}"
              f"{'rev':>5}{'body%':>7}{'strength':>10}")
        for d, info in days_sorted[:15]:
            ch = daily_characteristics(bars, d)
            if not ch: continue
            print(f"  {str(d):<12}{info['sum']:>+10,.0f}{int(info['count']):>6}  "
                  f"{ch['net_pts']:>+7.0f}{ch['range_pts']:>7.0f}{ch['atr']:>6.1f}"
                  f"{ch['reversals_5bar_ema']:>5}{ch['body_pct']:>6.1f}%{ch['trend_strength']:>10.2f}")
        # Also show top 5 best for comparison
        print(f"\n  Top 5 BEST P&L days (for contrast):")
        for d, info in sorted(day_pnl.items(), key=lambda kv: -kv[1]["sum"])[:5]:
            ch = daily_characteristics(bars, d)
            if not ch: continue
            print(f"  {str(d):<12}{info['sum']:>+10,.0f}{int(info['count']):>6}  "
                  f"{ch['net_pts']:>+7.0f}{ch['range_pts']:>7.0f}{ch['atr']:>6.1f}"
                  f"{ch['reversals_5bar_ema']:>5}{ch['body_pct']:>6.1f}%{ch['trend_strength']:>10.2f}")

    # Look at the relationship between intraday volatility (ATR) and per-day P&L
    print("\n=== ATR vs P&L correlation (target=18) ===")
    trades_18 = run_baseline(bars, price, ts_ns, 18.0)
    day_pnl_18 = daily_pnl_breakdown(trades_18, bars)
    rows = []
    for d, info in day_pnl_18.items():
        ch = daily_characteristics(bars, d)
        if ch:
            rows.append({"date": d, "pnl": info["sum"], **ch})
    cmp_df = pd.DataFrame(rows)
    # Bucket by ATR ranges and report avg P&L per bucket
    cmp_df["atr_bucket"] = pd.cut(cmp_df["atr"],
                                   bins=[0, 4, 6, 8, 10, 12, 15, 100],
                                   labels=["<4", "4-6", "6-8", "8-10", "10-12", "12-15", ">15"])
    print(cmp_df.groupby("atr_bucket")["pnl"].agg(["mean", "count", "sum"]).to_string())

    # Trend-strength bucketing
    print("\n=== Trend-strength vs P&L correlation (target=18) ===")
    cmp_df["ts_bucket"] = pd.cut(cmp_df["trend_strength"],
                                  bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
                                  labels=["chop <.2", ".2-.4", ".4-.6", ".6-.8", "strong >.8"])
    print(cmp_df.groupby("ts_bucket")["pnl"].agg(["mean", "count", "sum"]).to_string())

    # Bucket by # of EMA reversals (proxy for noise)
    print("\n=== Reversals vs P&L correlation (target=18) ===")
    cmp_df["rev_bucket"] = pd.cut(cmp_df["reversals_5bar_ema"],
                                   bins=[0, 5, 10, 15, 20, 30, 100],
                                   labels=["<5", "5-10", "10-15", "15-20", "20-30", ">30"])
    print(cmp_df.groupby("rev_bucket")["pnl"].agg(["mean", "count", "sum"]).to_string())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(cmp_df.to_json(orient="records", indent=2, default_handler=str))
    print(f"\nTotal: {time.time()-t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()

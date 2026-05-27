"""Pivot strategies — when a strong sustained trend is detected, change the
bot's behavior instead of continuing to fade reversals.

Tested:
  A) BASELINE                   -- target=18, no filter (Account 2)
  B) ATR>=4                     -- current Account 3
  C) sustained-move filter      -- if last 4-8h net move > X pt, skip
                                   counter-trend entries
  D) ATR>=4 + sustained-move    -- combined safety
  E) WITH-TREND INVERT mode     -- in strong trend, flip entry side
                                   (LONG on up-impulse, SHORT on down)
  F) STOP-WIDEN in strong trend -- widen stops 6pt -> 10pt when in
                                   strong trend, target stays at 18
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)
from research.sim_trend_filter_sweep import trend_netmove, apply_filter

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/pivot_strategies.json")


def main():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)
    bar_ts = bars.index.astype("int64").to_numpy()

    h = bars["high"].to_numpy(); l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    tr = np.maximum.reduce([h - l, np.abs(h - np.r_[c[0], c[:-1]]),
                            np.abs(l - np.r_[c[0], c[:-1]])])
    atr14 = pd.Series(tr).rolling(14).mean().to_numpy()

    def base_setups_t18():
        out = []
        for s in baseline_setups(bars):
            side = s["side"]; entry = s["entry_px"]
            tgt = entry + 18.0 if side == 1 else entry - 18.0
            out.append({**s, "target_px": tgt})
        return out

    setups_base = base_setups_t18()

    def filter_min_atr(setups, min_atr):
        out = []
        for s in setups:
            i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
            if 0 <= i < len(atr14) and np.isfinite(atr14[i]) and atr14[i] >= min_atr:
                out.append(s)
        return out

    def invert_in_strong_trend(setups, bias):
        """When bias[i] != 0 (strong trend detected), FLIP the setup side
        so the bot trades WITH the trend instead of fading it."""
        out = []
        for s in setups:
            i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
            if i < 0 or i >= len(bias):
                continue
            b = bias[i]
            if b == 0:
                out.append(s)
                continue
            # FLIP: stop and target swap sides
            new_side = b   # bias=+1 -> long, -1 -> short  (with trend)
            if new_side == s["side"]:
                out.append(s)  # already with trend
            else:
                # Invert: same impulse range, opposite direction
                entry = s["entry_px"]
                if new_side == 1:
                    new_stop = entry - 6.0; new_tgt = entry + 18.0
                else:
                    new_stop = entry + 6.0; new_tgt = entry - 18.0
                out.append({**s, "side": new_side, "stop_px": new_stop, "target_px": new_tgt})
        return out

    def widen_stops_in_strong_trend(setups, bias, new_stop_pts=10.0):
        """When in strong trend, widen counter-trend entries' stops so the
        bot doesn't get whipped out as fast. Stop goes from 6pt -> Xpt."""
        out = []
        for s in setups:
            i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
            if i < 0 or i >= len(bias):
                continue
            b = bias[i]
            if b != 0 and b != s["side"]:
                # Counter-trend in strong trend -- widen stop
                entry = s["entry_px"]
                if s["side"] == 1:
                    new_stop = entry - new_stop_pts
                else:
                    new_stop = entry + new_stop_pts
                out.append({**s, "stop_px": new_stop})
            else:
                out.append(s)
        return out

    # Per-day P&L breakdown helper
    def per_day_metrics(trades):
        if not trades: return {}
        tdf = pd.DataFrame(trades)
        tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True).dt.tz_convert("America/New_York")
        tdf["ny_date"] = tdf["exit_dt"].dt.date
        daily = tdf.groupby("ny_date")["pnl_usd"].sum()
        return {"worst_day": float(daily.min()),
                "best_day":  float(daily.max()),
                "n_losing_days": int((daily < 0).sum()),
                "n_winning_days": int((daily > 0).sum())}

    print(f"{'Strategy':<40}{'n':>7}{'WR':>7}{'Ret/mo':>10}{'DD%':>7}{'Worst$':>10}{'-days':>7}")
    print("-" * 92)

    def run(label, setups):
        trades = simulate(setups, price, ts_ns)
        s = score(trades, period_days)
        d = per_day_metrics(trades)
        worst = d.get("worst_day", 0)
        n_lose = d.get("n_losing_days", 0)
        print(f"{label:<40}{s.get('n',0):>7}{s.get('wr',0):>6.1f}%"
              f"{s.get('ret_mo',0):>+9.2f}%{s.get('max_dd_pct',0):>6.2f}%"
              f"{worst:>+10,.0f}{n_lose:>7}")
        return s, worst, n_lose

    print("--- References ---")
    run("A) BASELINE target=18", setups_base)
    run("B) ATR>=4", filter_min_atr(setups_base, 4.0))

    print("\n--- C) Sustained-move filter only (skip counter-trend) ---")
    for hours, thr in [(4, 30), (4, 50), (4, 80), (8, 60), (8, 100), (8, 150), (12, 100)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        run(f"sustained({hours}h,>={thr}pt) skip-counter", apply_filter(setups_base, bias, bars))

    print("\n--- D) ATR>=4 + sustained-move (combined safety) ---")
    for hours, thr in [(4, 50), (8, 100), (8, 150), (12, 100)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        s1 = filter_min_atr(setups_base, 4.0)
        s2 = apply_filter(s1, bias, bars)
        run(f"ATR>=4 + sustained({hours}h,>={thr}pt)", s2)

    print("\n--- E) WITH-TREND INVERT mode (FLIP side in strong trend) ---")
    for hours, thr in [(4, 50), (4, 80), (8, 100), (8, 150)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        run(f"invert({hours}h,>={thr}pt)", invert_in_strong_trend(setups_base, bias))

    print("\n--- F) WIDEN STOPS in strong trend (6pt -> 10pt) ---")
    for hours, thr in [(4, 50), (4, 80), (8, 100), (8, 150)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        run(f"widen_stops_to_10({hours}h,>={thr}pt)", widen_stops_in_strong_trend(setups_base, bias, 10.0))
    for hours, thr in [(4, 50), (8, 100)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        run(f"widen_stops_to_12({hours}h,>={thr}pt)", widen_stops_in_strong_trend(setups_base, bias, 12.0))

    print(f"\nTotal: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

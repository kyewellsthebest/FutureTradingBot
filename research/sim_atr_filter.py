"""ATR-regime filter test — based on the worst-day forensics finding
that baseline LOSES money on low-ATR drift days and WINS on high-ATR
volatile days. Test:
  - Skip new entries when ATR is below threshold (X = 2.0, 2.5, 3.0, 3.5)
  - ATR computed at the moment of setup detection (last 14 1-min bars)
  - Compare overall return + DD AND specifically per-day P&L on the worst
    20 days from the forensics output."""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/atr_filter_test.json")


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
    # Build target=18 baseline setups once
    base_setups = []
    for s in baseline_setups(bars):
        side = s["side"]; entry = s["entry_px"]
        tgt = entry + 18.0 if side == 1 else entry - 18.0
        base_setups.append({**s, "target_px": tgt})

    def filter_by_min_atr(setups, min_atr):
        out = []
        for s in setups:
            i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
            if 0 <= i < len(atr14) and np.isfinite(atr14[i]) and atr14[i] >= min_atr:
                out.append(s)
        return out

    print(f"{'Filter':<32}{'n':>7}{'WR':>7}{'Ret/mo':>10}{'DD%':>7}{'Worst day':>12}")
    print("-" * 78)

    def run(label, setups):
        trades = simulate(setups, price, ts_ns)
        s = score(trades, period_days)
        # Worst-day P&L
        tdf = pd.DataFrame(trades)
        tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True).dt.tz_convert("America/New_York")
        tdf["ny_date"] = tdf["exit_dt"].dt.date
        daily = tdf.groupby("ny_date")["pnl_usd"].sum()
        worst = float(daily.min())
        print(f"{label:<32}{s['n']:>7}{s['wr']:>6.1f}%{s['ret_mo']:>+9.2f}%"
              f"{s['max_dd_pct']:>6.2f}%{worst:>+12,.0f}")
        return s, worst

    # Reference
    run("BASELINE target=18 (no ATR)", base_setups)

    # ATR filters
    for atr_min in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        run(f"min_atr >= {atr_min}", filter_by_min_atr(base_setups, atr_min))

    # Combine ATR filter with daily-trend filter from earlier sweep
    print("\n--- Combined: ATR + 16h trend filter ---")
    from research.sim_trend_filter_sweep import trend_netmove, apply_filter
    for atr_min, trend_thr in [(2.5, 100), (2.5, 150), (3.0, 100), (3.0, 150)]:
        bias = trend_netmove(bars, lookback=16*60, threshold_pts=trend_thr)
        # Two-stage: first ATR filter, then trend filter
        s1 = filter_by_min_atr(base_setups, atr_min)
        s2 = apply_filter(s1, bias, bars)
        run(f"ATR>={atr_min} + trend({trend_thr}pt)", s2)

    print(f"\nTotal: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

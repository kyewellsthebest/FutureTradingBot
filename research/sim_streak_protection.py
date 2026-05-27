"""Streak protection candidates:
  1. Skip trades where vol_ratio_5_60 < 0.5 (calm-before-storm zone:
     69.6% loss rate, NEGATIVE total P&L)
  2. Post-streak pause: after N losses in a row, pause M minutes
  3. Combinations
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)
from research.sim_loss_forensics import find_losing_streaks

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/streak_protection.json")


def filter_setups_with_features(bars, setups, *, atr14_min=None,
                                 vol_ratio_min=None, skip_hours=None):
    """Apply pre-trade feature filters."""
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    tr = np.maximum.reduce([h - l, np.abs(h - np.r_[c[0], c[:-1]]),
                            np.abs(l - np.r_[c[0], c[:-1]])])
    atr5  = pd.Series(tr).rolling(5).mean().to_numpy()
    atr14 = pd.Series(tr).rolling(14).mean().to_numpy()
    atr60 = pd.Series(tr).rolling(60).mean().to_numpy()
    out = []
    for s in setups:
        i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
        if i < 60: continue
        if atr14_min is not None and (not np.isfinite(atr14[i]) or atr14[i] < atr14_min):
            continue
        if vol_ratio_min is not None:
            if not (np.isfinite(atr5[i]) and np.isfinite(atr60[i]) and atr60[i] > 0):
                continue
            if atr5[i] / atr60[i] < vol_ratio_min:
                continue
        if skip_hours is not None:
            ny = pd.Timestamp(s["sig_ts"], tz="UTC").tz_convert("America/New_York")
            if ny.hour in skip_hours:
                continue
        out.append(s)
    return out


def apply_post_streak_pause(setups, price, ts_ns, *,
                            losses_to_trigger=3, pause_mins=30):
    """Simulate a 'cool-off' rule: after N losses in a row, skip new
    entries for M minutes. Implemented by iteratively pruning."""
    pause_ns = pause_mins * 60 * 1_000_000_000
    # First do an initial simulation, then walk forward applying pauses
    # by removing setups that fall in the cooldown window.
    sorted_setups = sorted(setups, key=lambda s: s["sig_ts"])
    accepted = []
    cooldown_until = -1
    consec = 0

    # We need to simulate sequentially with cooldown. To do this cleanly:
    # simulate ALL initial trades, then for each, decide if it's allowed.
    initial_trades = simulate(sorted_setups, price, ts_ns)
    # Walk through initial_trades in order, track streak + cooldown
    allowed_entries = []
    for t in initial_trades:
        if t["entry_ts"] < cooldown_until:
            continue
        allowed_entries.append(t["entry_ts"])
        if t["pnl_usd"] < 0:
            consec += 1
            if consec >= losses_to_trigger:
                cooldown_until = t["exit_ts"] + pause_ns
                consec = 0
        else:
            consec = 0
    # Now filter setups whose sig_ts produced an allowed entry. Match by
    # entry being near the setup's sig_ts (within 5min window).
    allowed_set = set(allowed_entries)
    filtered_setups = []
    for s in sorted_setups:
        # Find the trade that started after this setup within 5 min
        window_end = s["sig_ts"] + 300 * 1_000_000_000
        match = next((et for et in allowed_set if s["sig_ts"] < et <= window_end), None)
        if match:
            filtered_setups.append(s)
    final_trades = simulate(filtered_setups, price, ts_ns)
    return final_trades


def score_full(trades, period_days):
    if not trades: return {"n":0}
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    months = period_days / 30.44
    st = find_losing_streaks(trades)
    tdf2 = pd.DataFrame(trades)
    tdf2["exit_dt"] = pd.to_datetime(tdf2["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    tdf2["ny_date"] = tdf2["exit_dt"].dt.date
    daily = tdf2.groupby("ny_date")["pnl_usd"].sum()
    return {
        "n": len(pnls),
        "wr": round(len(wins)/len(pnls)*100, 1),
        "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
        "max_dd_pct": round(abs(maxdd/STARTING_BAL*100), 2),
        "worst_day": round(float(daily.min()), 0),
        "max_streak": st["max_streak"],
        "n_streaks_ge6": st["n_streaks_ge6"],
        "n_streaks_ge10": st["n_streaks_ge10"],
        "worst_streak_pnl": st["worst_streak_pnl"],
    }


def main():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)

    # Build baseline target=18 setups (with adaptive stops on)
    bar_ts = bars.index.astype("int64").to_numpy()
    base_setups = []
    for s in baseline_setups(bars):
        side = s["side"]; entry = s["entry_px"]
        tgt = entry + 18.0 if side == 1 else entry - 18.0
        # Adaptive stop: if in strong trend, counter-trend gets 10pt
        i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
        stop_pts = 6.0
        if i >= 240:
            c_arr = bars["close"].to_numpy()
            trend_net = c_arr[i] - c_arr[i - 240]
            if abs(trend_net) >= 80 and ((trend_net > 0) != (side == 1)):
                stop_pts = 10.0
        new_stop = entry - stop_pts if side == 1 else entry + stop_pts
        base_setups.append({**s, "stop_px": new_stop, "target_px": tgt})

    print(f"{'Filter':<55}{'n':>5}{'WR':>6}{'Ret/mo':>9}{'DD%':>6}{'WorstDay':>10}{'MaxStrk':>9}{'>=6':>5}{'>=10':>6}")
    print("-" * 111)
    def run(label, setups, *, post_streak=None):
        if post_streak:
            trades = apply_post_streak_pause(setups, price, ts_ns,
                                              losses_to_trigger=post_streak[0],
                                              pause_mins=post_streak[1])
        else:
            trades = simulate(setups, price, ts_ns)
        sc = score_full(trades, period_days)
        print(f"{label:<55}{sc.get('n',0):>5}{sc.get('wr',0):>5.1f}%{sc.get('ret_mo',0):>+8.2f}%"
              f"{sc.get('max_dd_pct',0):>5.2f}%{sc.get('worst_day',0):>+10,.0f}"
              f"{sc.get('max_streak',0):>9}{sc.get('n_streaks_ge6',0):>5}{sc.get('n_streaks_ge10',0):>6}")
        return sc

    print("=== REFERENCE ===")
    run("BASELINE target=18 + adaptive stops (current Account 3)", base_setups)
    run("+ ATR14 >= 4 (current Account 3)",
        filter_setups_with_features(bars, base_setups, atr14_min=4.0))

    print("\n=== NEW: vol-ratio filter (skip 'calm-before-storm') ===")
    run("+ vol_ratio_5_60 >= 0.5",
        filter_setups_with_features(bars, base_setups, vol_ratio_min=0.5))
    run("+ vol_ratio_5_60 >= 0.6",
        filter_setups_with_features(bars, base_setups, vol_ratio_min=0.6))
    run("+ vol_ratio_5_60 >= 0.7",
        filter_setups_with_features(bars, base_setups, vol_ratio_min=0.7))

    print("\n=== NEW: post-streak pause ===")
    for n_loss, pause in [(3, 15), (3, 30), (3, 60), (4, 30), (4, 60), (5, 60)]:
        run(f"+ post-streak: {n_loss} losses -> pause {pause}min",
            base_setups, post_streak=(n_loss, pause))

    print("\n=== NEW: COMBINED ATR + vol_ratio + post-streak ===")
    s1 = filter_setups_with_features(bars, base_setups, atr14_min=4.0, vol_ratio_min=0.5)
    run("ATR>=4 + vol_ratio>=0.5", s1)
    run("ATR>=4 + vol_ratio>=0.5 + post-streak(3, 30min)", s1, post_streak=(3, 30))
    run("ATR>=4 + vol_ratio>=0.5 + post-streak(3, 60min)", s1, post_streak=(3, 60))
    s2 = filter_setups_with_features(bars, base_setups, atr14_min=4.0, vol_ratio_min=0.6)
    run("ATR>=4 + vol_ratio>=0.6 + post-streak(3, 60min)", s2, post_streak=(3, 60))

    print(f"\nTotal: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

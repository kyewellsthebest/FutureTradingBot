"""
Fib 50% — definitive hold-time clarity + 10-min entry test.

Counts hold time as 1-min BARS between entry and exit (which is the most
precise we can get without tick data). Compares 5-min vs 10-min entries.

For each (entry_tf × size), reports:
  * full bar-count distribution of hold times
  * shortest / median / mean / longest hold
  * Lucid microscalp WORST-CASE analysis:
      assume every same-bar exit (hold_bars=0) is ≤5s. This is the most
      conservative possible interpretation and gives a true compliance
      floor — if we're under 50% here, we are DEFINITELY compliant in
      reality.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min, load_intraday_1min

# Lucid constants
START_BAL = 50_000.0
INITIAL_TRAIL = 48_000.0
TRAIL_DROP = 2_000.0
TRAIL_LOCK_AT = 52_000.0
TRAIL_LOCKED_FLOOR = 50_000.0
DLL = 1_200.0
TRAIL_SAFETY = 300.0
NY = "America/New_York"

# Strategy / costs
PIVOT_K = 5
MIN_LEG_PTS = 20
TARGET_REWARD_RATIO = 1.00
MAX_HOLD_1M_BARS = 480
MNQ_PER_PT = 2.0
COMM_PER_MNQ_RT = 1.0
SLIP_PT_PER_SIDE = 0.25


def find_pivots_vec(high, low, k):
    h = high.to_numpy(); l = low.to_numpy()
    rmax = pd.Series(h).rolling(2*k+1, center=True).max().to_numpy()
    rmin = pd.Series(l).rolling(2*k+1, center=True).min().to_numpy()
    is_h = (h == rmax) & np.isfinite(rmax)
    is_l = (l == rmin) & np.isfinite(rmin)
    return ([(int(i), float(h[i])) for i in np.where(is_h)[0]],
            [(int(i), float(l[i])) for i in np.where(is_l)[0]])


def build_pivot_track(highs, lows, k, n):
    rh_src = np.full(n, -1, dtype=np.int32); rh_val = np.full(n, np.nan)
    rl_src = np.full(n, -1, dtype=np.int32); rl_val = np.full(n, np.nan)
    h_idx = l_idx = 0
    cur_h_src, cur_h_val = -1, np.nan
    cur_l_src, cur_l_val = -1, np.nan
    for t in range(n):
        while h_idx < len(highs) and highs[h_idx][0] + k <= t:
            cur_h_src, cur_h_val = highs[h_idx]; h_idx += 1
        while l_idx < len(lows) and lows[l_idx][0] + k <= t:
            cur_l_src, cur_l_val = lows[l_idx]; l_idx += 1
        rh_src[t] = cur_h_src; rh_val[t] = cur_h_val
        rl_src[t] = cur_l_src; rl_val[t] = cur_l_val
    return rh_src, rh_val, rl_src, rl_val


def simulate_1m(entry_loc, side, entry_px, stop_px, target_px, arr_1m,
                max_hold_bars):
    n = len(arr_1m)
    end = min(entry_loc + max_hold_bars, n - 1)
    for j in range(entry_loc, end + 1):
        _, h, l, c = arr_1m[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,  "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,  "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr_1m[end, 3]), "timeout"


def cost_per_trade(n_mnq):
    return n_mnq * COMM_PER_MNQ_RT + n_mnq * SLIP_PT_PER_SIDE * 2.0 * MNQ_PER_PT


def run_sim(nq_entries, nq1, n_mnq, max_setup_age):
    """Run Fib 50% w/ entries on nq_entries (any TF), exits on nq1. Returns
    detailed trade list."""
    highs, lows = find_pivots_vec(nq_entries["high"], nq_entries["low"], PIVOT_K)
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs, lows, PIVOT_K,
                                                       len(nq_entries))
    arr_e = nq_entries[["open", "high", "low", "close"]].to_numpy()
    arr_1 = nq1[["open", "high", "low", "close"]].to_numpy()
    idx_e = nq_entries.index
    idx_1 = nq1.index
    ny_dates = pd.DatetimeIndex(idx_e.tz_convert(NY)).date
    n_e = len(nq_entries)
    n_1 = len(nq1)

    balance = START_BAL
    peak_eod = START_BAL
    trail_floor = INITIAL_TRAIL
    trail_locked = False
    daily_pnl = 0.0
    current_date = ny_dates[0]
    account_blown = False
    blocked_dll = blocked_trail = 0
    active_until_1m = -1
    used = set()
    cpt = cost_per_trade(n_mnq)
    dollar_per_pt = n_mnq * MNQ_PER_PT
    trades = []

    for t in range(n_e - 1):
        bd = ny_dates[t]
        if bd != current_date:
            if balance > peak_eod: peak_eod = balance
            if not trail_locked and peak_eod >= TRAIL_LOCK_AT:
                trail_locked = True; trail_floor = TRAIL_LOCKED_FLOOR
            if not trail_locked:
                nf = balance - TRAIL_DROP
                if nf > trail_floor: trail_floor = nf
            current_date = bd; daily_pnl = 0.0
        if account_blown: continue
        if daily_pnl <= -DLL: continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]: continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS: continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > max_setup_age: continue
        key = (int(rh_src[t]), int(rl_src[t]))
        if key in used: continue
        level50 = (rh_val[t] + rl_val[t]) / 2.0
        side = None
        if rh_src[t] < rl_src[t]:
            if arr_e[t, 1] >= level50: side = "SHORT"
        else:
            if arr_e[t, 2] <= level50: side = "LONG"
        if side is None: continue

        entry_ts = idx_e[t + 1]
        entry_px = float(arr_e[t + 1, 0])
        if side == "SHORT":
            stop_px = float(rh_val[t]); risk = stop_px - level50
            target_px = level50 - TARGET_REWARD_RATIO * risk
        else:
            stop_px = float(rl_val[t]); risk = level50 - stop_px
            target_px = level50 + TARGET_REWARD_RATIO * risk

        entry_1m = idx_1.searchsorted(entry_ts)
        if entry_1m >= n_1: continue
        if entry_1m < active_until_1m: continue
        risk_pts = abs(stop_px - entry_px)
        worst = risk_pts * dollar_per_pt + cpt
        if daily_pnl - worst <= -DLL:
            blocked_dll += 1; used.add(key); continue
        if balance - worst <= trail_floor + TRAIL_SAFETY:
            blocked_trail += 1; used.add(key); continue

        exit_1m, exit_px, exit_r = simulate_1m(entry_1m, side, entry_px,
                                               stop_px, target_px, arr_1,
                                               MAX_HOLD_1M_BARS)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        net = pnl_pts * dollar_per_pt - cpt
        balance += net; daily_pnl += net
        hold_bars = int(exit_1m - entry_1m)        # number of 1-min bars
        trades.append({"side": side, "hold_bars": hold_bars,
                       "net_pnl": float(net), "exit_reason": exit_r})
        if balance <= trail_floor: account_blown = True
        active_until_1m = exit_1m + 1
        used.add(key)

    return {"trades": trades, "final_balance": balance,
            "account_blown": account_blown, "blocked_dll": blocked_dll,
            "blocked_trail": blocked_trail, "n_mnq": n_mnq}


def report(result, label):
    trades = result["trades"]
    if not trades:
        print(f"\n{label}: no trades"); return
    df = pd.DataFrame(trades)
    n = len(df)
    wins = int((df["net_pnl"] > 0).sum())
    total = float(df["net_pnl"].sum())
    hb = df["hold_bars"]

    print(f"\n{'='*88}\n{label}  —  {result['n_mnq']} MNQ\n{'='*88}")
    print(f"  Final balance      : ${result['final_balance']:>10,.0f}")
    print(f"  Net P&L            : ${result['final_balance']-START_BAL:>+10,.0f}")
    print(f"  Total trades       : {n:,}")
    print(f"  Trades/month       : {n/(8.1*12):.1f}")
    print(f"  Win rate           : {wins/n*100:.1f}%")
    print(f"  Account blown      : {result['account_blown']}")
    print(f"  Lucid blocks (DLL/trail): {result['blocked_dll']}/{result['blocked_trail']}")

    print(f"\n  --- Hold-time distribution (in 1-min bars) ---")
    buckets = [(0, 0, "0 bars (same minute)"),
               (1, 1, "1 bar  (~1 min)"),
               (2, 4, "2-4 bars (~2-4 min)"),
               (5, 9, "5-9 bars (~5-9 min)"),
               (10, 29, "10-29 bars (10-29 min)"),
               (30, 59, "30-59 bars (~30-59 min)"),
               (60, 119, "60-119 bars (~1-2 h)"),
               (120, MAX_HOLD_1M_BARS, "120+ bars (>2 h)")]
    for lo, hi, blab in buckets:
        m = (hb >= lo) & (hb <= hi)
        cnt = int(m.sum())
        pct = cnt / n * 100
        bucket_pnl = df.loc[m, "net_pnl"].sum()
        bucket_profit = df.loc[m & (df["net_pnl"] > 0), "net_pnl"].sum()
        print(f"    {blab:<26} : {cnt:>6,} ({pct:>5.1f}% of trades)  "
              f"P&L ${bucket_pnl:>+10,.0f}  profit ${bucket_profit:>+9,.0f}")

    print(f"\n  --- Hold extremes (1-min bars) ---")
    print(f"    Shortest hold      : {int(hb.min())} bars")
    print(f"    Median   hold      : {int(hb.median())} bars")
    print(f"    Mean     hold      : {hb.mean():.1f} bars")
    print(f"    P75      hold      : {int(hb.quantile(0.75))} bars")
    print(f"    P95      hold      : {int(hb.quantile(0.95))} bars")
    print(f"    Longest  hold      : {int(hb.max())} bars")

    # Lucid microscalp WORST CASE
    sb = (hb == 0)
    sb_cnt = int(sb.sum())
    sb_pnl = df.loc[sb, "net_pnl"].sum()
    sb_profit = df.loc[sb & (df["net_pnl"] > 0), "net_pnl"].sum()
    total_profit = df.loc[df["net_pnl"] > 0, "net_pnl"].sum()
    worst_ratio = sb_profit / total_profit if total_profit > 0 else 0
    print(f"\n  --- Lucid microscalp WORST-CASE (assume every same-bar = ≤5s) ---")
    print(f"    Same-bar exits        : {sb_cnt:>6,} ({sb_cnt/n*100:>5.1f}% of trades)")
    print(f"    Same-bar profit       : ${sb_profit:>+10,.0f}")
    print(f"    Total profit          : ${total_profit:>+10,.0f}")
    print(f"    WORST-CASE micro ratio: {worst_ratio*100:.1f}%")
    print(f"    Lucid threshold       : 50.0%")
    margin = (0.50 - worst_ratio) * 100
    if worst_ratio < 0.50:
        print(f"    Compliance margin     : {margin:+.1f} pts BELOW threshold (compliant)")
        print(f"    STATUS                : COMPLIANT ✓ (even in worst case)")
    else:
        print(f"    Above threshold by    : {-margin:+.1f} pts (VIOLATION ✗)")


def resample(nq5, freq):
    return nq5.resample(freq).agg({"open":"first", "high":"max", "low":"min",
                                   "close":"last", "volume":"sum"}).dropna()


def main():
    print("=" * 88)
    print("FIB 50% — HOLD-TIME CLARITY + 10-min ENTRY TEST")
    print("=" * 88)
    nq5 = load_intraday_5min("nq")
    nq1 = load_intraday_1min("nq")
    if nq5.index.tz is None: nq5.index = nq5.index.tz_localize("UTC")
    if nq1.index.tz is None: nq1.index = nq1.index.tz_localize("UTC")
    nq5 = nq5.sort_index(); nq1 = nq1.sort_index()
    nq10 = resample(nq5, "10min")
    print(f"5-min bars: {len(nq5):,}   10-min bars: {len(nq10):,}   "
          f"1-min bars: {len(nq1):,}")

    print("\n" + "#" * 88)
    print("#  5-MIN ENTRIES (current preferred)")
    print("#" * 88)
    for n_mnq in (1, 5):
        res = run_sim(nq5, nq1, n_mnq, max_setup_age=50)
        report(res, f"5-min entries / full-pivot target")

    print("\n" + "#" * 88)
    print("#  10-MIN ENTRIES (test for more compliance margin)")
    print("#" * 88)
    for n_mnq in (1, 5):
        res = run_sim(nq10, nq1, n_mnq, max_setup_age=25)
        report(res, f"10-min entries / full-pivot target")


if __name__ == "__main__":
    main()

"""
Fib 50% strategy — minimum-hold-time rule for Lucid microscalp compliance.

Setup detection stays on 5-min bars (same as before). EXIT simulation uses
1-min bars so we can measure real hold times and enforce a minimum-hold
gate before exit is allowed.

Minimum-hold semantics:
  * 0 s   : no gate — exit at first stop/target hit (baseline)
  * 30 s  : force-hold first 1-min bar (60s of forced hold)
  * 60 s  : force-hold first 1-min bar
  * 120 s : force-hold first 2 1-min bars
  * 300 s : force-hold first 5 1-min bars

If a stop/target was technically hit during the force-hold period, the
trade exits at the OPEN of the first bar AFTER min-hold expires —
realistic worst-case: price could have continued past stop while we
held. Tagged 'stop_held' / 'target_held' in the exit reason.

Strategy config: 5-min entries, full-pivot target (best 1 MNQ from sweep).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min, load_intraday_1min

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Lucid + costs (same as before)
START_BAL = 50_000.0
INITIAL_TRAIL = 48_000.0
TRAIL_DROP = 2_000.0
TRAIL_LOCK_AT = 52_000.0
TRAIL_LOCKED_FLOOR = 50_000.0
DLL = 1_200.0
TRAIL_SAFETY = 300.0
NY = "America/New_York"
MNQ_PER_PT = 2.0
COMM_PER_MNQ_RT = 1.00
SLIP_PT_PER_SIDE = 0.25

# Strategy
PIVOT_K = 5
MIN_LEG_PTS = 20
TARGET_REWARD_RATIO = 1.00     # full-pivot target
MAX_HOLD_MIN_BARS = 480        # 8h
MAX_SETUP_AGE_5M = 50          # 4h on 5-min


def find_pivots_vec(high, low, k):
    h = high.to_numpy(); l = low.to_numpy()
    rmax = pd.Series(h).rolling(2 * k + 1, center=True).max().to_numpy()
    rmin = pd.Series(l).rolling(2 * k + 1, center=True).min().to_numpy()
    is_h = (h == rmax) & np.isfinite(rmax)
    is_l = (l == rmin) & np.isfinite(rmin)
    highs = [(int(i), float(h[i])) for i in np.where(is_h)[0]]
    lows = [(int(i), float(l[i])) for i in np.where(is_l)[0]]
    return highs, lows


def build_pivot_track(highs, lows, k, n):
    rh_src = np.full(n, -1, dtype=np.int32)
    rl_src = np.full(n, -1, dtype=np.int32)
    rh_val = np.full(n, np.nan)
    rl_val = np.full(n, np.nan)
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


def cost_per_trade(n_mnq):
    return n_mnq * COMM_PER_MNQ_RT + n_mnq * SLIP_PT_PER_SIDE * 2.0 * MNQ_PER_PT


def simulate_1m(entry_loc, side, entry_px, stop_px, target_px,
                arr_1m, max_hold_bars, min_hold_bars):
    """Walk 1-min bars; force-hold first min_hold_bars; then normal stop/target.
    If stop/target was technically breached during the hold window, exit at the
    open of the first bar AFTER the hold window — realistic worst case."""
    n = len(arr_1m)
    end = min(entry_loc + max_hold_bars, n - 1)
    check_start = entry_loc + min_hold_bars

    if min_hold_bars > 0 and check_start <= end:
        # check if open of bar at check_start has already gone past stop or target
        open_px = float(arr_1m[check_start, 0])
        if side == "LONG":
            if open_px <= stop_px:
                return check_start, open_px, "stop_held"
            if open_px >= target_px:
                return check_start, open_px, "target_held"
        else:
            if open_px >= stop_px:
                return check_start, open_px, "stop_held"
            if open_px <= target_px:
                return check_start, open_px, "target_held"

    # normal walk from check_start onward
    for j in range(check_start, end + 1):
        _, h, l, c = arr_1m[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,  "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,  "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr_1m[end, 3]), "timeout"


def run_sim(nq5, nq1, n_mnq, min_hold_s):
    """Setup detection on 5-min, exit walk on 1-min."""
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(
        *find_pivots_vec(nq5["high"], nq5["low"], PIVOT_K), PIVOT_K, len(nq5))
    arr5 = nq5[["open", "high", "low", "close"]].to_numpy()
    arr1 = nq1[["open", "high", "low", "close"]].to_numpy()
    idx5 = nq5.index
    idx1 = nq1.index
    ny_dates5 = pd.DatetimeIndex(idx5.tz_convert(NY)).date
    n5 = len(nq5)
    n1 = len(nq1)

    balance = START_BAL
    peak_eod = START_BAL
    trail_floor = INITIAL_TRAIL
    trail_locked = False
    daily_pnl = 0.0
    current_date = ny_dates5[0]
    account_blown = False
    blocked_dll = 0
    blocked_trail = 0
    active_until_1m = -1
    used = set()
    cpt = cost_per_trade(n_mnq)
    dollar_per_pt = n_mnq * MNQ_PER_PT

    min_hold_bars = 0 if min_hold_s == 0 else max(1, (min_hold_s + 59) // 60)

    trades = []
    for t in range(n5 - 1):
        bar_date = ny_dates5[t]
        if bar_date != current_date:
            if balance > peak_eod: peak_eod = balance
            if not trail_locked and peak_eod >= TRAIL_LOCK_AT:
                trail_locked = True; trail_floor = TRAIL_LOCKED_FLOOR
            if not trail_locked:
                new_floor = balance - TRAIL_DROP
                if new_floor > trail_floor: trail_floor = new_floor
            current_date = bar_date
            daily_pnl = 0.0
        if account_blown: continue
        if daily_pnl <= -DLL: continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]: continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS: continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > MAX_SETUP_AGE_5M: continue
        key = (int(rh_src[t]), int(rl_src[t]))
        if key in used: continue
        level50 = (rh_val[t] + rl_val[t]) / 2.0
        side = None
        if rh_src[t] < rl_src[t]:
            if arr5[t, 1] >= level50: side = "SHORT"
        else:
            if arr5[t, 2] <= level50: side = "LONG"
        if side is None: continue

        entry_5m_ts = idx5[t + 1]
        entry_px = float(arr5[t + 1, 0])
        if side == "SHORT":
            stop_px = float(rh_val[t])
            risk = stop_px - level50
            target_px = level50 - TARGET_REWARD_RATIO * risk
        else:
            stop_px = float(rl_val[t])
            risk = level50 - stop_px
            target_px = level50 + TARGET_REWARD_RATIO * risk

        # locate the 1-min bar at entry_5m_ts
        entry_1m_loc = idx1.searchsorted(entry_5m_ts)
        if entry_1m_loc >= n1:
            continue
        if entry_1m_loc < active_until_1m:
            continue

        risk_pts = abs(stop_px - entry_px)
        worst_loss = risk_pts * dollar_per_pt + cpt
        if daily_pnl - worst_loss <= -DLL:
            blocked_dll += 1; used.add(key); continue
        if balance - worst_loss <= trail_floor + TRAIL_SAFETY:
            blocked_trail += 1; used.add(key); continue

        exit_loc_1m, exit_px, exit_r = simulate_1m(
            entry_1m_loc, side, entry_px, stop_px, target_px,
            arr1, MAX_HOLD_MIN_BARS, min_hold_bars)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        gross = pnl_pts * dollar_per_pt
        net = gross - cpt
        balance += net
        daily_pnl += net
        hold_s = (idx1[exit_loc_1m] - idx1[entry_1m_loc]).total_seconds()
        trades.append({
            "side": side, "entry_ts": idx1[entry_1m_loc],
            "exit_ts": idx1[exit_loc_1m],
            "hold_s": float(hold_s),
            "net_pnl": float(net),
            "exit_reason": exit_r,
        })
        if balance <= trail_floor:
            account_blown = True
        active_until_1m = exit_loc_1m + 1
        used.add(key)

    if not trades:
        return None
    tdf = pd.DataFrame(trades)
    pnl = tdf["net_pnl"].to_numpy()
    n_t = len(pnl)
    wins = int((pnl > 0).sum())
    wpn = pnl[pnl > 0]; lpn = pnl[pnl < 0]
    pf = wpn.sum() / -lpn.sum() if len(lpn) and lpn.sum() < 0 else float("inf")
    cum = np.cumsum(pnl)
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_win = float(wpn.mean()) if len(wpn) else 0.0
    avg_loss = float(lpn.mean()) if len(lpn) else 0.0
    rr = abs(avg_win / avg_loss) if avg_loss < 0 else 0.0

    # hold-time stats
    hs = tdf["hold_s"]
    micro_n = int((hs <= 5).sum())
    micro_profit = float(tdf[(hs <= 5) & (pnl > 0)]["net_pnl"].sum())
    total_profit = float(wpn.sum())
    micro_ratio = (micro_profit / total_profit) if total_profit > 0 else 0.0
    micro_compliant = micro_ratio < 0.50

    reasons = tdf["exit_reason"].value_counts().to_dict()

    return {
        "n_mnq": n_mnq, "min_hold_s": min_hold_s,
        "n": n_t, "wr": wins / n_t, "pf": pf,
        "total": float(pnl.sum()),
        "avg_win": avg_win, "avg_loss": avg_loss,
        "realized_rr": rr,
        "maxdd": maxdd, "final_balance": balance,
        "blocked_dll": blocked_dll, "blocked_trail": blocked_trail,
        "account_blown": account_blown,
        "hold_min": hs.min(), "hold_median": hs.median(),
        "hold_mean": hs.mean(), "hold_p25": hs.quantile(0.25),
        "hold_p75": hs.quantile(0.75), "hold_max": hs.max(),
        "micro_trades": micro_n, "micro_pct": micro_n / n_t,
        "micro_profit": micro_profit, "micro_ratio": micro_ratio,
        "micro_compliant": micro_compliant,
        "exit_reasons": reasons,
    }


def main():
    print("=" * 96)
    print("FIB 50% — 1-min EXIT SIM + MIN-HOLD RULE for Lucid microscalp safety")
    print("=" * 96)
    print(f"Strategy: 5-min entries, full-pivot target (TARGET_REWARD_RATIO={TARGET_REWARD_RATIO})")
    print(f"Loading 5-min and 1-min NQ data ...")
    nq5 = load_intraday_5min("nq")
    nq1 = load_intraday_1min("nq")
    if nq5.index.tz is None: nq5.index = nq5.index.tz_localize("UTC")
    if nq1.index.tz is None: nq1.index = nq1.index.tz_localize("UTC")
    nq5 = nq5.sort_index(); nq1 = nq1.sort_index()
    print(f"  5-min bars: {len(nq5):,}   1-min bars: {len(nq1):,}")

    sizes = (1, 5)
    min_holds = (0, 30, 60, 120, 300)

    rows = []
    for n_mnq in sizes:
        print(f"\n{'='*96}\n{n_mnq} MNQ\n{'='*96}")
        print(f"  {'min_hold':>9}{'trades':>8}{'win%':>7}{'realRR':>9}"
              f"{'PF':>6}{'total':>13}{'maxDD':>12}"
              f"{'medHold':>10}{'micro%':>8}{'microRatio':>12}{'compliant':>11}")
        for mh in min_holds:
            r = run_sim(nq5, nq1, n_mnq, mh)
            if r is None:
                print(f"  {mh:>7}s  (no trades)")
                continue
            rows.append(r)
            mh_str = f"{mh}s"
            print(f"  {mh_str:>9}{r['n']:>8}{r['wr']*100:>6.1f}%"
                  f"  1:{r['realized_rr']:>5.2f}{r['pf']:>6.2f}"
                  f"${r['total']:>+11,.0f}${r['maxdd']:>+10,.0f}"
                  f"{r['hold_median']/60:>9.1f}m"
                  f"{r['micro_pct']*100:>7.1f}%"
                  f"{r['micro_ratio']*100:>10.1f}%"
                  f"{'YES' if r['micro_compliant'] else 'NO':>11}")

    print("\n" + "=" * 96)
    print("Key takeaway: where does the P&L cost of min-hold start to bite?")
    print("=" * 96)


if __name__ == "__main__":
    main()

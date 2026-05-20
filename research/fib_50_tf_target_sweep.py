"""
Fib 50% strategy — timeframe + target-stretch sweep under Lucid rules.

Goal: improve realized R:R while keeping the win rate >55%.

Sweeps:
  Timeframes  : 5-min, 10-min, 15-min
  Target      : 50% (default = leg/4),  75%,  100% (= full prior pivot)
  Sizes       : 1 MNQ, 5 MNQ

Target parameter "reward_ratio" = reward as fraction of risk:
  0.50  - default target at midpoint between entry and opposite pivot
  0.75  - target 75% of the way back to opposite pivot
  1.00  - target IS the opposite pivot itself
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Lucid constants (same as fib_50_lucid_full.py)
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
MNQ_PER_PT = 2.0
COMM_PER_MNQ_RT = 1.00
SLIP_PT_PER_SIDE = 0.25


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


def simulate_trade(entry_loc, side, entry_px, stop_px, target_px, arr, max_hold):
    n = len(arr)
    end = min(entry_loc + max_hold, n - 1)
    for j in range(entry_loc, end + 1):
        _, h, l, c = arr[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,  "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,  "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr[end, 3]), "timeout"


def cost_per_trade(n_mnq):
    return n_mnq * COMM_PER_MNQ_RT + n_mnq * SLIP_PT_PER_SIDE * 2.0 * MNQ_PER_PT


def run_sim(nq, n_mnq, reward_ratio, max_hold_bars, max_setup_age):
    """Run Fib 50% with parameterized target and timeframe-specific hold/age."""
    highs, lows = find_pivots_vec(nq["high"], nq["low"], PIVOT_K)
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs, lows, PIVOT_K, len(nq))
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    ny_dates = pd.DatetimeIndex(nq.index.tz_convert(NY)).date
    n = len(nq)

    balance = START_BAL
    peak_eod = START_BAL
    trail_floor = INITIAL_TRAIL
    trail_locked = False
    daily_pnl = 0.0
    current_date = ny_dates[0]
    account_blown = False

    trades = []
    blocked_dll = 0
    blocked_trail = 0
    active_until = -1
    used = set()
    cpt = cost_per_trade(n_mnq)
    dollar_per_pt = n_mnq * MNQ_PER_PT

    for t in range(n - 1):
        bar_date = ny_dates[t]
        if bar_date != current_date:
            if balance > peak_eod: peak_eod = balance
            if not trail_locked and peak_eod >= TRAIL_LOCK_AT:
                trail_locked = True
                trail_floor = TRAIL_LOCKED_FLOOR
            if not trail_locked:
                new_floor = balance - TRAIL_DROP
                if new_floor > trail_floor: trail_floor = new_floor
            current_date = bar_date
            daily_pnl = 0.0
        if account_blown: continue
        if daily_pnl <= -DLL: continue
        if t < active_until: continue
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
            if arr[t, 1] >= level50: side = "SHORT"
        else:
            if arr[t, 2] <= level50: side = "LONG"
        if side is None: continue

        entry_px = float(arr[t + 1, 0])

        # reward_ratio determines target distance from entry (as fraction of risk).
        # Risk = entry - opposite stop = leg/2 (entry near level50, stop at extreme).
        # target_distance = reward_ratio * (leg/2).
        if side == "SHORT":
            stop_px = float(rh_val[t])              # original swing high
            risk = stop_px - level50                # leg/2
            target_px = level50 - reward_ratio * risk
        else:
            stop_px = float(rl_val[t])
            risk = level50 - stop_px
            target_px = level50 + reward_ratio * risk

        risk_pts = abs(stop_px - entry_px)
        worst_loss = risk_pts * dollar_per_pt + cpt
        if daily_pnl - worst_loss <= -DLL:
            blocked_dll += 1; used.add(key); continue
        if balance - worst_loss <= trail_floor + TRAIL_SAFETY:
            blocked_trail += 1; used.add(key); continue

        exit_loc, exit_px, exit_r = simulate_trade(t + 1, side, entry_px,
                                                   stop_px, target_px, arr,
                                                   max_hold_bars)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        gross = pnl_pts * dollar_per_pt
        net = gross - cpt
        balance += net
        daily_pnl += net
        trades.append({"net_pnl": net, "exit_reason": exit_r,
                       "risk_pts": risk_pts})
        if balance <= trail_floor:
            account_blown = True
        active_until = exit_loc + 1
        used.add(key)

    if not trades:
        return None
    tdf = pd.DataFrame(trades)
    pnl = tdf["net_pnl"].to_numpy()
    n_t = len(pnl)
    wins_mask = pnl > 0
    losses_mask = pnl < 0
    wins = int(wins_mask.sum())
    win_pnl = pnl[wins_mask]
    loss_pnl = pnl[losses_mask]
    avg_win = float(win_pnl.mean()) if len(win_pnl) else 0.0
    avg_loss = float(loss_pnl.mean()) if len(loss_pnl) else 0.0
    gw = float(win_pnl.sum())
    gl = float(-loss_pnl.sum())
    pf = gw / gl if gl > 0 else float("inf")
    realized_rr = abs(avg_win / avg_loss) if avg_loss < 0 else 0.0
    cum = np.cumsum(pnl)
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    targets = int((tdf["exit_reason"] == "target").sum())
    stops = int((tdf["exit_reason"] == "stop").sum())
    timeouts = int((tdf["exit_reason"] == "timeout").sum())
    return {
        "n": n_t, "wr": wins / n_t, "pf": pf,
        "total": float(pnl.sum()),
        "avg_win": avg_win, "avg_loss": avg_loss,
        "realized_rr": realized_rr,
        "maxdd": maxdd, "final_balance": balance,
        "blocked_dll": blocked_dll, "blocked_trail": blocked_trail,
        "n_target": targets, "n_stop": stops, "n_timeout": timeouts,
        "account_blown": account_blown,
    }


def resample(nq5, freq):
    return nq5.resample(freq).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"}).dropna()


def main() -> None:
    print("=" * 100)
    print("FIB 50%  —  TIMEFRAME × TARGET-RR  sweep  under Lucid rules + costs")
    print("=" * 100)
    nq5 = load_intraday_5min("nq")
    if nq5.index.tz is None: nq5.index = nq5.index.tz_localize("UTC")
    nq5 = nq5.sort_index()

    # (label, freq, max_hold_bars=8h, max_setup_age~4h)
    tfs = [("5-min",  None,    96,  50),
           ("10-min", "10min", 48,  25),
           ("15-min", "15min", 32,  17)]
    targets = [(0.50, "default (leg/4)"),
               (0.75, "stretched 75%"),
               (1.00, "full pivot 100%")]
    sizes = [1, 5]

    rows = []
    for tf_label, freq, max_h, max_a in tfs:
        nq = nq5 if freq is None else resample(nq5, freq)
        print(f"\n>>> {tf_label}  ({len(nq):,} bars)")
        for rr, rr_label in targets:
            for n_mnq in sizes:
                r = run_sim(nq, n_mnq, rr, max_h, max_a)
                if r is None:
                    rows.append({"tf": tf_label, "rr": rr, "size": n_mnq, "n": 0})
                    continue
                rows.append({"tf": tf_label, "rr": rr, "rr_label": rr_label,
                             "size": n_mnq, **r})
                print(f"  tgt={rr_label:<18} size={n_mnq:>2} MNQ:  "
                      f"n={r['n']:>5}  win={r['wr']*100:>4.1f}%  "
                      f"realRR=1:{r['realized_rr']:>4.2f}  "
                      f"PF={r['pf']:>4.2f}  "
                      f"total=${r['total']:>+10,.0f}  "
                      f"maxDD=${r['maxdd']:>+9,.0f}  "
                      f"T/S/X={r['n_target']}/{r['n_stop']}/{r['n_timeout']}  "
                      f"Lucid block (DLL/trail)={r['blocked_dll']}/{r['blocked_trail']}")

    print("\n" + "=" * 100)
    print("SUMMARY  (sorted by total P&L within each size)")
    print("=" * 100)
    for sz in sizes:
        subset = [r for r in rows if r.get("size") == sz and r.get("n", 0) > 0]
        subset.sort(key=lambda r: -r["total"])
        print(f"\n--- {sz} MNQ ---")
        print(f"  {'tf':<8}{'target':<22}{'n':>7}{'win%':>7}{'realRR':>9}"
              f"{'PF':>6}{'total':>14}{'maxDD':>13}")
        for r in subset:
            print(f"  {r['tf']:<8}{r['rr_label']:<22}{r['n']:>7}"
                  f"{r['wr']*100:>6.1f}%  1:{r['realized_rr']:>5.2f}"
                  f"{r['pf']:>6.2f}${r['total']:>+12,.0f}${r['maxdd']:>+11,.0f}")


if __name__ == "__main__":
    main()

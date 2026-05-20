"""
Fibonacci 50% retracement — stop-size sweep + timeframe comparison.

The base strategy already runs on 5-min (see fib_50_retrace_sim.py — that
produced the $3M / 61% / $15k-DD result with the wide swing-extreme stop).

This script sweeps:
  * stop variants on 5-min: from very tight (5 pt) to wide (P0 swing extreme)
    + ATR multiples + trigger-bar-extreme (a natural tight structural stop)
  * timeframes for comparison: 1-min, 5-min, 15-min, 1-hour

Same engine, same entries, same targets — only the stop changes.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_1min, load_intraday_5min

SIZE = 10
MNQ_PER_PT = 2.0
PIVOT_K = 5
MIN_LEG_PTS = 20


def find_pivots_vec(high: pd.Series, low: pd.Series, k: int):
    """Vectorised fractal pivots — much faster than the loop version."""
    h = high.to_numpy(); l = low.to_numpy()
    rmax = pd.Series(h).rolling(2 * k + 1, center=True).max().to_numpy()
    rmin = pd.Series(l).rolling(2 * k + 1, center=True).min().to_numpy()
    is_h = (h == rmax) & np.isfinite(rmax)
    is_l = (l == rmin) & np.isfinite(rmin)
    highs = [(int(i), float(h[i])) for i in np.where(is_h)[0]]
    lows  = [(int(i), float(l[i])) for i in np.where(is_l)[0]]
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


def compute_stop(stop_type, stop_value, side, entry_px,
                 swing_extreme, trigger_bar_extreme, atr_val):
    if stop_type == "wide_swing":
        return swing_extreme
    if stop_type == "trigger_bar":
        return trigger_bar_extreme
    if stop_type.startswith("fixed_"):
        return entry_px + stop_value if side == "SHORT" else entry_px - stop_value
    if stop_type.startswith("atr_"):
        a = atr_val if (np.isfinite(atr_val) and atr_val > 0) else 5.0
        return entry_px + stop_value * a if side == "SHORT" else entry_px - stop_value * a
    raise ValueError(stop_type)


def simulate_trade(entry_loc, side, entry_px, stop_px, target_px, arr, max_hold):
    n = len(arr)
    end = min(entry_loc + max_hold, n - 1)
    for j in range(entry_loc, end + 1):
        _, h, l, c = arr[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,   "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,   "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr[end, 3]), "timeout"


def run_strategy(nq, stop_type, stop_value, max_hold_bars, max_setup_age, pivots, atr):
    rh_src, rh_val, rl_src, rl_val = pivots
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(nq)
    trades = []
    active_until = -1
    used = set()
    for t in range(n - 1):
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
        if side == "SHORT":
            swing_ext = float(rh_val[t])
            target_px = (level50 + rl_val[t]) / 2.0
            trig_ext = float(arr[t, 1])
        else:
            swing_ext = float(rl_val[t])
            target_px = (level50 + rh_val[t]) / 2.0
            trig_ext = float(arr[t, 2])
        stop_px = compute_stop(stop_type, stop_value, side, entry_px,
                               swing_ext, trig_ext, atr[t])
        exit_loc, exit_px, exit_r = simulate_trade(
            t + 1, side, entry_px, stop_px, target_px, arr, max_hold_bars)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        trades.append({"pnl_usd": pnl_pts * SIZE * MNQ_PER_PT,
                       "exit_reason": exit_r})
        active_until = exit_loc + 1
        used.add(key)
    return trades


def stats(trades):
    if not trades:
        return None
    pnl = np.array([t["pnl_usd"] for t in trades])
    reasons = [t["exit_reason"] for t in trades]
    n = len(pnl)
    wins = int((pnl > 0).sum())
    gw = float(pnl[pnl > 0].sum())
    gl = float(-pnl[pnl < 0].sum())
    cum = np.cumsum(pnl)
    return {
        "n": n,
        "wr": wins / n,
        "pf": gw / gl if gl > 0 else float("inf"),
        "total": float(pnl.sum()),
        "avg": float(pnl.mean()),
        "maxdd": float((cum - np.maximum.accumulate(cum)).min()),
        "n_target": reasons.count("target"),
        "n_stop":   reasons.count("stop"),
        "n_timeout": reasons.count("timeout"),
    }


def resample(nq5, freq):
    return nq5.resample(freq).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"}).dropna()


def prep(nq):
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    highs, lows = find_pivots_vec(nq["high"], nq["low"], PIVOT_K)
    pivots = build_pivot_track(highs, lows, PIVOT_K, len(nq))
    atr = (nq["high"] - nq["low"]).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    return nq, pivots, atr, len(highs), len(lows)


def run_grid(label, nq, pivots, atr, max_hold, max_age, variants, rows):
    print(f"\n>>> {label}  (max_hold={max_hold}, max_setup_age={max_age})")
    print(f"    {'stop':<15}{'n':>8}{'win%':>7}{'PF':>6}"
          f"{'total':>14}{'avg':>9}{'maxDD':>13}{'T/S/X':>14}")
    for stop_name, stop_val in variants:
        t0 = time.time()
        trades = run_strategy(nq, stop_name, stop_val, max_hold, max_age, pivots, atr)
        s = stats(trades)
        elapsed = time.time() - t0
        if s is None:
            print(f"    {stop_name:<15}  (no trades) [{elapsed:.1f}s]")
            rows.append({"tf": label, "stop": stop_name, "n": 0})
            continue
        rows.append({"tf": label, "stop": stop_name, **s})
        print(f"    {stop_name:<15}{s['n']:>8}{s['wr']*100:>6.1f}%"
              f"{s['pf']:>6.2f}${s['total']:>+12,.0f}${s['avg']:>+7,.0f}"
              f"${s['maxdd']:>+11,.0f}"
              f"{s['n_target']}/{s['n_stop']}/{s['n_timeout']:>3}"
              f" [{elapsed:.1f}s]")


def main():
    print("=" * 100)
    print("FIB 50% RETRACEMENT — STOP-SIZE & TIMEFRAME SWEEP — NQ, 10 MNQ ($20/pt)")
    print("=" * 100)
    rows = []

    stop_variants_full = [
        ("fixed_5pt",   5.0),
        ("fixed_10pt", 10.0),
        ("fixed_20pt", 20.0),
        ("fixed_50pt", 50.0),
        ("atr_0.5",     0.5),
        ("atr_1.0",     1.0),
        ("atr_1.5",     1.5),
        ("trigger_bar", None),
        ("wide_swing",  None),
    ]
    stop_variants_short = [("wide_swing", None), ("fixed_10pt", 10.0)]

    # 5-MIN — full sweep
    print("\n>>> Loading 5-min ...")
    nq5, pv5, atr5, nh5, nl5 = prep(load_intraday_5min("nq"))
    print(f"    bars: {len(nq5):,}  highs: {nh5:,}  lows: {nl5:,}")
    run_grid("5-min", nq5, pv5, atr5, 96, 50, stop_variants_full, rows)

    # 15-MIN
    print("\n>>> Building 15-min (resampled from 5-min) ...")
    nq15, pv15, atr15, nh15, nl15 = prep(resample(nq5, "15min"))
    print(f"    bars: {len(nq15):,}  highs: {nh15:,}  lows: {nl15:,}")
    run_grid("15-min", nq15, pv15, atr15, 32, 16, stop_variants_short, rows)

    # 1-HOUR
    print("\n>>> Building 1-h (resampled from 5-min) ...")
    nq1h, pv1h, atr1h, nh1h, nl1h = prep(resample(nq5, "1h"))
    print(f"    bars: {len(nq1h):,}  highs: {nh1h:,}  lows: {nl1h:,}")
    run_grid("1-hour", nq1h, pv1h, atr1h, 8, 4, stop_variants_short, rows)

    # 1-MIN (heaviest — run last)
    print("\n>>> Loading 1-min ...")
    nq1, pv1, atr1, nh1, nl1 = prep(load_intraday_1min("nq"))
    print(f"    bars: {len(nq1):,}  highs: {nh1:,}  lows: {nl1:,}")
    run_grid("1-min", nq1, pv1, atr1, 480, 250, stop_variants_short, rows)

    # final summary
    print("\n" + "=" * 100)
    print("FINAL SUMMARY  (all timeframes, all stops)")
    print("=" * 100)
    print(f"{'tf':<8}{'stop':<14}{'n':>8}{'win%':>7}{'PF':>6}"
          f"{'total':>14}{'avg':>9}{'maxDD':>13}")
    print("-" * 100)
    for r in rows:
        if r.get("n", 0) == 0:
            print(f"{r['tf']:<8}{r['stop']:<14}  (no trades)")
            continue
        print(f"{r['tf']:<8}{r['stop']:<14}{r['n']:>8}{r['wr']*100:>6.1f}%"
              f"{r['pf']:>6.2f}${r['total']:>+12,.0f}${r['avg']:>+7,.0f}"
              f"${r['maxdd']:>+11,.0f}")


if __name__ == "__main__":
    main()

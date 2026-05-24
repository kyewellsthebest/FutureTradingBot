"""Cumulative-delta strategy — FAST vectorized version.

Per-config compute:
  1. Vectorized rolling cumdelta: one cumsum + one searchsorted call
  2. Vectorized trigger detection: where(|cd| >= thresh)
  3. Loop only over triggers (small N), enforce cooldown
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT       = 2.0
TARGET_RISK_USD  = 50.0
MAX_CONTRACTS    = 5
LATENCY_MS       = 200
SLIPPAGE_PTS     = 0.25
DEFAULT_COMM     = 1.00


def _size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def precompute_global(price, ts_ns, signed_vol):
    """One-time computations shared across configs."""
    n = len(price)
    cum_signed = np.empty(n + 1, dtype=np.int64)
    cum_signed[0] = 0
    cum_signed[1:] = np.cumsum(signed_vol.astype(np.int64))
    return cum_signed


def run_cumdelta_fast(price, ts_ns, cum_signed,
                      window_secs: int,
                      delta_thresh: int,
                      init_stop_pts: float,
                      trail_activate_pts: float,
                      trail_distance_pts: float,
                      max_hold_secs: int,
                      cooldown_secs: int,
                      comm_per_contract: float = DEFAULT_COMM,
                      latency_ms: int = LATENCY_MS,
                      slippage_pts: float = SLIPPAGE_PTS):
    n = len(price)
    window_ns = window_secs * 1_000_000_000
    hold_ns = max_hold_secs * 1_000_000_000
    cd_ns = cooldown_secs * 1_000_000_000
    latency_ns = latency_ms * 1_000_000
    size = _size(init_stop_pts)

    # Vectorized rolling delta: for each i, find earliest j s.t. ts_ns[j] >= ts_ns[i] - window_ns
    win_start = np.searchsorted(ts_ns, ts_ns - window_ns, side="left")
    # window_delta[i] = cum_signed[i+1] - cum_signed[win_start[i]]
    window_delta = cum_signed[1:n+1] - cum_signed[win_start[:n]]

    # Trigger detection: |delta| >= threshold
    trigger_mask = np.abs(window_delta) >= delta_thresh
    trigger_idx = np.where(trigger_mask)[0]
    if len(trigger_idx) == 0:
        return np.array([], dtype=np.float32)

    pnls = []
    last_exit_ts = -1

    for trig_i in trigger_idx:
        trig_ts = ts_ns[trig_i]
        if last_exit_ts > 0 and trig_ts - last_exit_ts < cd_ns:
            continue

        side = 1 if window_delta[trig_i] > 0 else -1

        # Latency: find first tick after trig_ts + latency
        fill_deadline = trig_ts + latency_ns
        entry_idx = np.searchsorted(ts_ns, fill_deadline, side="left")
        if entry_idx >= n: break
        entry_ts = ts_ns[entry_idx]
        raw_entry_px = float(price[entry_idx])

        if side == 1:
            entry_px = raw_entry_px + slippage_pts
            stop_px = entry_px - init_stop_pts
        else:
            entry_px = raw_entry_px - slippage_pts
            stop_px = entry_px + init_stop_pts

        deadline_ts = entry_ts + hold_ns
        end_idx = min(np.searchsorted(ts_ns, deadline_ts, side="left"), n - 1)
        if end_idx <= entry_idx: continue

        best_fav = entry_px
        exit_px = None
        exit_ts = None
        # Slice for forward scan
        # Vectorize the inner loop somewhat by walking with numpy
        for j in range(entry_idx, end_idx + 1):
            p = float(price[j])
            if side == 1:
                if p > best_fav:
                    best_fav = p
                    if best_fav >= entry_px + trail_activate_pts:
                        new_stop = best_fav - trail_distance_pts
                        if new_stop > stop_px:
                            stop_px = new_stop
                if p <= stop_px:
                    exit_px = stop_px - slippage_pts
                    exit_ts = ts_ns[j]
                    break
            else:
                if p < best_fav:
                    best_fav = p
                    if best_fav <= entry_px - trail_activate_pts:
                        new_stop = best_fav + trail_distance_pts
                        if new_stop < stop_px:
                            stop_px = new_stop
                if p >= stop_px:
                    exit_px = stop_px + slippage_pts
                    exit_ts = ts_ns[j]
                    break

        if exit_px is None:
            last_px = float(price[end_idx])
            exit_px = last_px - slippage_pts if side == 1 else last_px + slippage_pts
            exit_ts = ts_ns[end_idx]

        pnl_pts = (exit_px - entry_px) if side == 1 else (entry_px - exit_px)
        pnl = pnl_pts * size * MNQ_PER_PT - comm_per_contract * size
        pnls.append(pnl)
        last_exit_ts = exit_ts

    return np.array(pnls, dtype=np.float32)


def summarize(pnls, period_days):
    n = len(pnls)
    if n == 0: return None
    wins = int((pnls > 0).sum())
    gw = float(pnls[pnls > 0].sum())
    gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if wins < n else 0
    streak = max_streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    months = period_days / 30.44
    return {
        "n": n, "wr": wins/n, "pf": pf,
        "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
        "total": float(pnls.sum()), "per": float(pnls.mean()),
        "trades_per_day": n/period_days,
        "trades_per_mo": n/months,
        "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
        "max_streak": max_streak,
        "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months,
    }


def hits_spec(s):
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0 and abs(s["maxdd_pct"]) <= 2.0)


def main():
    t0 = time.time()
    print("Loading...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    signed_vol = (volume * aggressor).astype(np.int64)
    del df
    print(f"  {len(price):,} ticks, {period_days:.0f} days  ({time.time()-t0:.0f}s)")

    print("Precomputing cumulative signed volume...")
    cum_signed = precompute_global(price, ts_ns, signed_vol)
    print(f"  done ({time.time()-t0:.0f}s)\n")

    results = []
    cfg_count = 0
    print(f"{'Win':>4} {'Thrsh':>6} {'Stop':>5} {'Tract':>5} {'Trdst':>5} {'Hold':>5} "
          f"{'n':>5} {'/d':>4} {'/mo':>4} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>6} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}")
    print("-" * 120)
    for window in [15, 30, 60, 120]:
        for thresh in [50, 100, 200, 400, 800]:
            for istop in [1.0, 2.0, 3.0]:
                for tract in [1.0, 2.0]:
                    for trdist in [0.5, 1.0]:
                        for hold in [60, 180]:
                            cfg_count += 1
                            pnls = run_cumdelta_fast(price, ts_ns, cum_signed,
                                                      window, thresh, istop, tract,
                                                      trdist, hold, cooldown_secs=10)
                            s = summarize(pnls, period_days)
                            if not s or s["n"] < 30: continue
                            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                            tag = ""
                            if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                            elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 2: tag = " ★★"
                            elif s["wr"] >= 0.55: tag = " ★ WR"
                            elif s["ret_per_mo"] >= 1: tag = " ★"
                            elif s["total"] > 0: tag = " +"
                            print(f"{window:>3}s {thresh:>6} {istop:>5.1f} "
                                  f"{tract:>5.1f} {trdist:>5.1f} {hold:>4}s "
                                  f"{s['n']:>5} {s['trades_per_day']:>3.1f} "
                                  f"{s['trades_per_mo']:>4.0f} "
                                  f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                                  f"${s['per']:>+4,.0f} ${s['total']:>+7,.0f} "
                                  f"{abs(s['maxdd_pct']):>4.1f}% {s['ret_per_mo']:>+5.2f}%{tag}")
                            results.append({**s, "window": window, "thresh": thresh,
                                            "istop": istop, "tract": tract,
                                            "trdist": trdist, "hold": hold})

    print(f"\n{cfg_count} configs tested, elapsed {time.time()-t0:.0f}s")
    print("\n" + "=" * 100)
    print("TOP 15 BY RET/MO  (REALISTIC: 200ms latency, 0.25pt slippage, $1 comm)")
    print("=" * 100)
    results.sort(key=lambda x: -x["ret_per_mo"])
    for r in results[:15]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = " ★★★★ HITS SPEC!" if hits_spec(r) else ""
        print(f"  win={r['window']:>3}s thrsh={r['thresh']:>3} istop={r['istop']:.1f} "
              f"tract={r['tract']:.1f} trdist={r['trdist']:.1f} hold={r['hold']}s | "
              f"n={r['n']:>4} ({r['trades_per_mo']:.0f}/mo) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% → {r['ret_per_mo']:+.2f}%/mo{flag}")


if __name__ == "__main__":
    main()

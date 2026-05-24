"""CumDelta strategy — FULLY VECTORIZED inner loop using cumulative max/min.

The trailing-stop logic for each trade is vectorized using cummax/cummin
+ argmax of first stop-hit condition. ~50x faster than Python loop.

Realistic execution baked in: 200ms latency, 0.25pt slippage, $1 comm.
"""
from __future__ import annotations
import time
import sys
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


def run_cumdelta_v2(price, ts_ns, cum_signed,
                    window_secs: int, delta_thresh: int,
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

    # Rolling window delta (vectorized)
    win_start = np.searchsorted(ts_ns, ts_ns - window_ns, side="left")
    window_delta = cum_signed[1:n+1] - cum_signed[win_start]

    # Trigger detection: signal first appears when |delta| crosses threshold
    # (edge-detect to avoid trigger spam on each consecutive tick)
    is_trig = np.abs(window_delta) >= delta_thresh
    # edge: trig now but not trig prev
    edge = is_trig.copy()
    edge[1:] &= ~is_trig[:-1]
    trigger_idx = np.where(edge)[0]
    if len(trigger_idx) == 0:
        return np.array([], dtype=np.float32)

    # Cooldown filtering: drop triggers within cd_ns of previous exit
    # We'll filter on-the-fly during processing instead since exit time
    # depends on trade outcome.

    pnls = []
    last_exit_ts = -1

    for trig_i in trigger_idx:
        trig_ts = ts_ns[trig_i]
        if last_exit_ts > 0 and trig_ts - last_exit_ts < cd_ns:
            continue
        side = 1 if window_delta[trig_i] > 0 else -1

        # latency
        fill_deadline = trig_ts + latency_ns
        entry_idx = int(np.searchsorted(ts_ns, fill_deadline, side="left"))
        if entry_idx >= n: break
        raw_entry_px = float(price[entry_idx])
        entry_ts = ts_ns[entry_idx]

        # apply entry slippage
        if side == 1:
            entry_px = raw_entry_px + slippage_pts
        else:
            entry_px = raw_entry_px - slippage_pts

        # End of hold
        deadline_ts = entry_ts + hold_ns
        end_idx = min(int(np.searchsorted(ts_ns, deadline_ts, side="left")), n - 1)
        if end_idx <= entry_idx: continue

        # Slice price for the trade window
        seg = price[entry_idx:end_idx + 1].astype(np.float32)
        seg_ts = ts_ns[entry_idx:end_idx + 1]

        # Vectorized trailing-stop computation
        if side == 1:
            # cumulative max of price during the trade
            cum_max = np.maximum.accumulate(seg)
            # trail stop: when cum_max >= entry+trail_activate, stop = cum_max - trail_dist
            trail_active = cum_max >= entry_px + trail_activate_pts
            trail_stop = cum_max - trail_distance_pts
            # effective stop: max(initial_stop, trail_stop where activated)
            init_stop_arr = np.full_like(seg, entry_px - init_stop_pts)
            stop_arr = np.where(trail_active, np.maximum(init_stop_arr, trail_stop), init_stop_arr)
            # also ensure stop only moves UP, not down (use cummax of stop)
            stop_arr = np.maximum.accumulate(stop_arr)
            # find first index where price <= stop
            hits = seg <= stop_arr
        else:
            cum_min = np.minimum.accumulate(seg)
            trail_active = cum_min <= entry_px - trail_activate_pts
            trail_stop = cum_min + trail_distance_pts
            init_stop_arr = np.full_like(seg, entry_px + init_stop_pts)
            stop_arr = np.where(trail_active, np.minimum(init_stop_arr, trail_stop), init_stop_arr)
            stop_arr = np.minimum.accumulate(stop_arr)
            hits = seg >= stop_arr

        if hits.any():
            hit_idx = int(np.argmax(hits))
            stop_at_hit = float(stop_arr[hit_idx])
            if side == 1:
                exit_px = stop_at_hit - slippage_pts
            else:
                exit_px = stop_at_hit + slippage_pts
            exit_ts = int(seg_ts[hit_idx])
        else:
            # timeout — exit at last price with slippage
            last_px = float(seg[-1])
            exit_px = last_px - slippage_pts if side == 1 else last_px + slippage_pts
            exit_ts = int(seg_ts[-1])

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
    print("Loading...", flush=True)
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    signed_vol = (volume * aggressor).astype(np.int64)
    del df
    print(f"  {len(price):,} ticks, {period_days:.0f} days, {time.time()-t0:.0f}s",
          flush=True)

    cum_signed = np.empty(len(price) + 1, dtype=np.int64)
    cum_signed[0] = 0
    cum_signed[1:] = np.cumsum(signed_vol)
    print(f"  cumsum done {time.time()-t0:.0f}s\n", flush=True)

    print(f"{'Win':>4} {'Thrsh':>6} {'Stop':>5} {'Tract':>5} {'Trdst':>5} {'Hold':>5} "
          f"{'n':>5} {'/d':>4} {'/mo':>4} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>6} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}", flush=True)
    print("-" * 120, flush=True)
    results = []
    cfg_count = 0
    cfg_done = 0
    for window in [15, 30, 60, 120]:
        for thresh in [100, 200, 400, 800, 1500]:
            for istop in [1.0, 2.0, 3.0]:
                for tract in [1.0, 2.0]:
                    for trdist in [0.5, 1.0]:
                        for hold in [60, 180]:
                            cfg_count += 1
                            t1 = time.time()
                            pnls = run_cumdelta_v2(price, ts_ns, cum_signed,
                                                    window, thresh, istop, tract,
                                                    trdist, hold, cooldown_secs=10)
                            cfg_done += 1
                            elapsed = time.time() - t1
                            s = summarize(pnls, period_days)
                            if not s or s["n"] < 30:
                                if cfg_count % 20 == 0:
                                    print(f"  [progress {cfg_count}/480, "
                                          f"total {time.time()-t0:.0f}s]",
                                          flush=True)
                                continue
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
                                  f"{abs(s['maxdd_pct']):>4.1f}% {s['ret_per_mo']:>+5.2f}%{tag}",
                                  flush=True)
                            results.append({**s, "window": window, "thresh": thresh,
                                            "istop": istop, "tract": tract,
                                            "trdist": trdist, "hold": hold})

    print(f"\n{cfg_count} configs tested, elapsed {time.time()-t0:.0f}s",
          flush=True)
    print("\n" + "=" * 100, flush=True)
    print("TOP 15 BY RET/MO  (REALISTIC: 200ms latency, 0.25pt slippage, $1 comm)",
          flush=True)
    print("=" * 100, flush=True)
    results.sort(key=lambda x: -x["ret_per_mo"])
    for r in results[:15]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = " ★★★★ HITS SPEC!" if hits_spec(r) else ""
        print(f"  win={r['window']:>3}s thrsh={r['thresh']:>3} istop={r['istop']:.1f} "
              f"tract={r['tract']:.1f} trdist={r['trdist']:.1f} hold={r['hold']}s | "
              f"n={r['n']:>4} ({r['trades_per_mo']:.0f}/mo) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% → {r['ret_per_mo']:+.2f}%/mo{flag}",
              flush=True)


if __name__ == "__main__":
    main()

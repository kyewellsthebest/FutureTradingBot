"""Volume-profile rejection — vectorized cross detection.

Same strategy as v1 but cross detection done with numpy:
  - For each HVN, find all tick indices where price crosses through it
  - Process only cross events (small N), not all ticks
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


def build_daily_profiles(price, volume, date_arr, bin_width: float = 1.0):
    unique_days = np.unique(date_arr)
    profiles = {}
    for d in unique_days:
        mask = date_arr == d
        if mask.sum() < 100: continue
        p = price[mask]
        v = volume[mask].astype(np.int64)
        bins = np.round(p / bin_width).astype(np.int32) * bin_width
        unique_bins, idx = np.unique(bins, return_inverse=True)
        vol_at_bin = np.zeros(len(unique_bins), dtype=np.int64)
        np.add.at(vol_at_bin, idx, v)
        order = np.argsort(-vol_at_bin)
        profiles[d] = unique_bins[order]
    return profiles


def find_cross_events(price, hvn_levels):
    """For an array of price ticks, find all (index, hvn_level, side) where
    price crosses through any HVN. side=+1 if crossed up, -1 if crossed down.
    """
    n = len(price)
    if n < 2 or len(hvn_levels) == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float32), np.array([], dtype=np.int8)

    # vectorized cross detection
    prev = price[:-1]
    cur = price[1:]
    events_idx = []
    events_lvl = []
    events_side = []
    for lvl in hvn_levels:
        cross_up = (prev < lvl) & (cur >= lvl)
        cross_dn = (prev > lvl) & (cur <= lvl)
        # +1 indexing because cross detected from prev->cur, cur is at i+1
        up_idx = np.where(cross_up)[0] + 1
        dn_idx = np.where(cross_dn)[0] + 1
        events_idx.append(up_idx); events_lvl.append(np.full(len(up_idx), lvl, dtype=np.float32)); events_side.append(np.full(len(up_idx), 1, dtype=np.int8))
        events_idx.append(dn_idx); events_lvl.append(np.full(len(dn_idx), lvl, dtype=np.float32)); events_side.append(np.full(len(dn_idx), -1, dtype=np.int8))
    if not events_idx:
        return np.array([]), np.array([]), np.array([])
    all_idx = np.concatenate(events_idx)
    all_lvl = np.concatenate(events_lvl)
    all_side = np.concatenate(events_side)
    # sort by index
    order = np.argsort(all_idx)
    return all_idx[order], all_lvl[order], all_side[order]


def run_vp_rejection_fast(price, ts_ns, volume, date_arr,
                          n_hvn: int = 5,
                          init_stop_pts: float = 3.0,
                          trail_activate_pts: float = 2.0,
                          trail_distance_pts: float = 1.0,
                          max_hold_secs: int = 600,
                          cooldown_secs: int = 60,
                          bin_width: float = 1.0,
                          comm_per_contract: float = DEFAULT_COMM,
                          latency_ms: int = LATENCY_MS,
                          slippage_pts: float = SLIPPAGE_PTS):
    n = len(price)
    hold_ns = max_hold_secs * 1_000_000_000
    cd_ns = cooldown_secs * 1_000_000_000
    latency_ns = latency_ms * 1_000_000
    size = _size(init_stop_pts)

    profiles = build_daily_profiles(price, volume, date_arr, bin_width)

    unique_days = sorted(set(date_arr.tolist()))
    day_to_prev = {}
    for i in range(1, len(unique_days)):
        day_to_prev[unique_days[i]] = unique_days[i-1]

    # Build per-day cross events
    all_events_idx = []
    all_events_side = []
    for d in unique_days:
        prev_d = day_to_prev.get(d, None)
        if prev_d is None or prev_d not in profiles: continue
        hvns = profiles[prev_d][:n_hvn]
        # mask for this day
        day_mask = date_arr == d
        day_indices = np.where(day_mask)[0]
        if len(day_indices) < 2: continue
        day_price = price[day_indices]
        ev_idx_rel, _, ev_side = find_cross_events(day_price, hvns)
        # convert relative to absolute indices
        if len(ev_idx_rel) > 0:
            all_events_idx.append(day_indices[ev_idx_rel])
            all_events_side.append(ev_side)

    if not all_events_idx:
        return np.array([], dtype=np.float32)
    events_idx = np.concatenate(all_events_idx)
    events_side = np.concatenate(all_events_side)

    pnls = []
    last_exit_ts = -1

    for ev_i, ev_side in zip(events_idx, events_side):
        # fade the cross: side = opposite
        side = -1 if ev_side == 1 else 1

        trig_ts = ts_ns[ev_i]
        if last_exit_ts > 0 and trig_ts - last_exit_ts < cd_ns:
            continue

        fill_deadline = trig_ts + latency_ns
        entry_idx = int(np.searchsorted(ts_ns, fill_deadline, side="left"))
        if entry_idx >= n: break
        raw_entry_px = float(price[entry_idx])
        entry_ts = ts_ns[entry_idx]

        if side == 1:
            entry_px = raw_entry_px + slippage_pts
        else:
            entry_px = raw_entry_px - slippage_pts

        deadline_ts = entry_ts + hold_ns
        end_idx = min(int(np.searchsorted(ts_ns, deadline_ts, side="left")), n - 1)
        if end_idx <= entry_idx: continue

        seg = price[entry_idx:end_idx + 1].astype(np.float32)
        seg_ts = ts_ns[entry_idx:end_idx + 1]
        if side == 1:
            cum_max = np.maximum.accumulate(seg)
            trail_active = cum_max >= entry_px + trail_activate_pts
            trail_stop = cum_max - trail_distance_pts
            init_stop_arr = np.full_like(seg, entry_px - init_stop_pts)
            stop_arr = np.where(trail_active, np.maximum(init_stop_arr, trail_stop), init_stop_arr)
            stop_arr = np.maximum.accumulate(stop_arr)
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
            exit_px = stop_at_hit - slippage_pts if side == 1 else stop_at_hit + slippage_pts
            exit_ts = int(seg_ts[hit_idx])
        else:
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
    months = period_days / 30.44
    return {
        "n": n, "wr": wins/n, "pf": pf,
        "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
        "total": float(pnls.sum()), "per": float(pnls.mean()),
        "trades_per_day": n/period_days, "trades_per_mo": n/months,
        "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
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
    ts_ns = df["ts"].astype("int64").to_numpy()
    date_arr = df["ts"].dt.tz_convert("America/New_York").dt.date.to_numpy()
    del df
    print(f"  {len(price):,} ticks, {period_days:.0f} days, {time.time()-t0:.0f}s",
          flush=True)

    print(f"\n{'NHV':>3} {'Stop':>5} {'Trct':>5} {'Trdst':>5} {'Hold':>5} {'CD':>4} "
          f"{'n':>5} {'/d':>4} {'/mo':>4} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>6} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}", flush=True)
    print("-" * 120, flush=True)
    results = []
    cfg_count = 0
    for n_hvn in [3, 5, 8, 12]:
        for istop in [1.5, 2.5, 4.0]:
            for tract in [1.0, 2.0, 3.0]:
                for trdist in [0.5, 1.0]:
                    for hold in [120, 300, 900]:
                        for cd in [30, 120]:
                            cfg_count += 1
                            pnls = run_vp_rejection_fast(price, ts_ns, volume,
                                                         date_arr, n_hvn,
                                                         istop, tract, trdist,
                                                         hold, cd)
                            s = summarize(pnls, period_days)
                            if not s or s["n"] < 20: continue
                            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                            tag = ""
                            if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                            elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 2: tag = " ★★"
                            elif s["wr"] >= 0.55: tag = " ★ WR"
                            elif s["ret_per_mo"] >= 1: tag = " ★"
                            elif s["total"] > 0: tag = " +"
                            print(f"{n_hvn:>3} {istop:>5.1f} {tract:>5.1f} "
                                  f"{trdist:>5.1f} {hold:>4}s {cd:>3}s "
                                  f"{s['n']:>5} {s['trades_per_day']:>3.1f} "
                                  f"{s['trades_per_mo']:>4.0f} "
                                  f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                                  f"${s['per']:>+4,.0f} ${s['total']:>+7,.0f} "
                                  f"{abs(s['maxdd_pct']):>4.1f}% {s['ret_per_mo']:>+5.2f}%{tag}",
                                  flush=True)
                            results.append({**s, "n_hvn": n_hvn, "istop": istop,
                                            "tract": tract, "trdist": trdist,
                                            "hold": hold, "cd": cd})

    print(f"\n{cfg_count} configs tested, elapsed {time.time()-t0:.0f}s", flush=True)
    print("\nTOP 10 BY RET/MO:")
    results.sort(key=lambda x: -x["ret_per_mo"])
    for r in results[:10]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = " ★★★★" if hits_spec(r) else ""
        print(f"  n_hvn={r['n_hvn']} istop={r['istop']} tract={r['tract']} "
              f"trdist={r['trdist']} hold={r['hold']}s cd={r['cd']}s | "
              f"n={r['n']} WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% → {r['ret_per_mo']:+.2f}%/mo{flag}",
              flush=True)


if __name__ == "__main__":
    main()

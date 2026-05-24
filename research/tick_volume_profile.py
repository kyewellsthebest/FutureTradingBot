"""Volume-profile rejection strategy with realistic execution.

CONCEPT:
  Build daily volume profile — sum of volume at each NQ price level.
  High-Volume Nodes (HVN) = price levels where the most volume traded.
  These act as MAGNETS and SUPPORT/RESISTANCE.

STRATEGY:
  - Each day, compute volume profile from yesterday's data
  - Identify top N HVNs (price levels with most volume)
  - When today's price approaches an HVN from outside, expect rejection
  - Enter SHORT if price wicks above HVN and closes back below
  - Enter LONG if price wicks below HVN and closes back above
  - Stop: through the level by buffer_pts
  - Target: next HVN in direction of trade

Tick data is used to:
  - Build accurate volume profile (every trade at every price)
  - Detect intrabar wicks of HVN levels in realtime

REALISTIC EXECUTION: 200ms latency, 0.25pt slippage, $1 commission.
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
NQ_TICK          = 0.25      # NQ tick size


def _size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def build_daily_profiles(price, volume, ts_ns, date_arr,
                         bin_width: float = 1.0):
    """For each calendar day, return list of HVN prices sorted by volume desc."""
    unique_days = np.unique(date_arr)
    profiles = {}  # date → list of (price, volume) sorted by volume desc
    for d in unique_days:
        mask = date_arr == d
        if mask.sum() < 100: continue
        p = price[mask]
        v = volume[mask].astype(np.int64)
        # bin prices to bin_width
        bins = np.round(p / bin_width).astype(np.int32) * bin_width
        # group by bin and sum volume
        unique_bins, idx = np.unique(bins, return_inverse=True)
        vol_at_bin = np.zeros(len(unique_bins), dtype=np.int64)
        np.add.at(vol_at_bin, idx, v)
        # sort by volume desc
        order = np.argsort(-vol_at_bin)
        profiles[d] = [(float(unique_bins[i]), int(vol_at_bin[i])) for i in order]
    return profiles


def run_vp_rejection(price, ts_ns, volume, aggressor, date_arr,
                     n_hvn: int = 5,
                     hvn_tolerance: float = 1.0,    # how close to HVN to consider "test"
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

    # Build daily profiles from prior day (no look-ahead)
    print(f"  Building daily volume profiles...", flush=True)
    profiles = build_daily_profiles(price, volume, ts_ns, date_arr, bin_width)
    print(f"  {len(profiles)} day profiles built", flush=True)

    pnls = []
    last_exit_ts = -1
    unique_days = np.unique(date_arr)
    day_to_prev = {}
    sorted_days = sorted(unique_days)
    for i in range(1, len(sorted_days)):
        day_to_prev[sorted_days[i]] = sorted_days[i-1]

    # Walk through ticks; for each, check if we touch yesterday's top HVNs
    prev_price = price[0]
    cur_date = None
    cur_hvns = []   # list of (level_price, level_idx) for today's tracking

    for i in range(n - 1):
        d = date_arr[i]
        if d != cur_date:
            cur_date = d
            prev_d = day_to_prev.get(d, None)
            if prev_d is not None and prev_d in profiles:
                cur_hvns = [p for p, _ in profiles[prev_d][:n_hvn]]
            else:
                cur_hvns = []
            prev_price = price[i]
            continue

        if not cur_hvns:
            prev_price = price[i]
            continue

        p_cur = float(price[i])
        # check each HVN — did we cross it (prev_price one side, cur on other)?
        for hvn_px in cur_hvns:
            if abs(p_cur - hvn_px) > hvn_tolerance:
                continue
            # We're near HVN. Check for rejection pattern over last ~30 sec
            # Simpler: SHORT if price crossed UP through HVN, LONG if crossed DOWN
            crossed_up = prev_price < hvn_px and p_cur >= hvn_px
            crossed_down = prev_price > hvn_px and p_cur <= hvn_px

            if not (crossed_up or crossed_down):
                continue

            # Cooldown
            if last_exit_ts > 0 and ts_ns[i] - last_exit_ts < cd_ns:
                continue

            # Determine side: fade the HVN
            side = -1 if crossed_up else 1   # cross up → expect reject down → SHORT

            # Latency
            fill_deadline = ts_ns[i] + latency_ns
            entry_idx = int(np.searchsorted(ts_ns, fill_deadline, side="left"))
            if entry_idx >= n: break
            raw_entry_px = float(price[entry_idx])
            entry_ts = ts_ns[entry_idx]
            # Slippage
            if side == 1:
                entry_px = raw_entry_px + slippage_pts
                stop_px = entry_px - init_stop_pts
            else:
                entry_px = raw_entry_px - slippage_pts
                stop_px = entry_px + init_stop_pts

            deadline_ts = entry_ts + hold_ns
            end_idx = min(int(np.searchsorted(ts_ns, deadline_ts, side="left")), n - 1)
            if end_idx <= entry_idx: break

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
                if side == 1:
                    exit_px = stop_at_hit - slippage_pts
                else:
                    exit_px = stop_at_hit + slippage_pts
                exit_ts = int(seg_ts[hit_idx])
            else:
                last_px = float(seg[-1])
                exit_px = last_px - slippage_pts if side == 1 else last_px + slippage_pts
                exit_ts = int(seg_ts[-1])

            pnl_pts = (exit_px - entry_px) if side == 1 else (entry_px - exit_px)
            pnl = pnl_pts * size * MNQ_PER_PT - comm_per_contract * size
            pnls.append(pnl)
            last_exit_ts = exit_ts
            # Break out of HVN inner loop after taking a trade
            break

        prev_price = p_cur

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
    date_arr = df["ts"].dt.tz_convert("America/New_York").dt.date.to_numpy()
    del df
    print(f"  {len(price):,} ticks, {period_days:.0f} days, {time.time()-t0:.0f}s",
          flush=True)

    print(f"\n{'NHV':>3} {'Tol':>4} {'Stop':>5} {'Trct':>5} {'Trdst':>5} {'Hold':>5} {'CD':>4} "
          f"{'n':>5} {'/d':>4} {'/mo':>4} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>6} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}", flush=True)
    print("-" * 120, flush=True)
    results = []
    cfg_count = 0
    for n_hvn in [3, 5, 10]:
        for tol in [0.5, 1.0, 2.0]:
            for istop in [2.0, 3.0, 5.0]:
                for tract in [1.5, 2.5]:
                    for trdist in [0.5, 1.0]:
                        for hold in [300, 900]:
                            for cd in [30, 120]:
                                cfg_count += 1
                                pnls = run_vp_rejection(price, ts_ns, volume, aggressor,
                                                         date_arr, n_hvn, tol, istop,
                                                         tract, trdist, hold, cd)
                                s = summarize(pnls, period_days)
                                if not s or s["n"] < 20: continue
                                pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                                tag = ""
                                if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                                elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 2: tag = " ★★"
                                elif s["wr"] >= 0.55: tag = " ★ WR"
                                elif s["ret_per_mo"] >= 1: tag = " ★"
                                elif s["total"] > 0: tag = " +"
                                print(f"{n_hvn:>3} {tol:>4.1f} {istop:>5.1f} "
                                      f"{tract:>5.1f} {trdist:>5.1f} {hold:>4}s "
                                      f"{cd:>3}s {s['n']:>5} {s['trades_per_day']:>3.1f} "
                                      f"{s['trades_per_mo']:>4.0f} "
                                      f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                                      f"${s['per']:>+4,.0f} ${s['total']:>+7,.0f} "
                                      f"{abs(s['maxdd_pct']):>4.1f}% {s['ret_per_mo']:>+5.2f}%{tag}",
                                      flush=True)
                                results.append({**s, "n_hvn": n_hvn, "tol": tol,
                                                "istop": istop, "tract": tract,
                                                "trdist": trdist, "hold": hold, "cd": cd})

    print(f"\n{cfg_count} configs tested, elapsed {time.time()-t0:.0f}s", flush=True)
    results.sort(key=lambda x: -x["ret_per_mo"])
    print("\nTOP 10 BY RET/MO:")
    for r in results[:10]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = " ★★★★" if hits_spec(r) else ""
        print(f"  n_hvn={r['n_hvn']} tol={r['tol']} istop={r['istop']} "
              f"tract={r['tract']} trdist={r['trdist']} hold={r['hold']}s cd={r['cd']}s | "
              f"n={r['n']} WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% → {r['ret_per_mo']:+.2f}%/mo{flag}",
              flush=True)


if __name__ == "__main__":
    main()

"""Large-Trade Continuation with TRAILING STOP — let winners run.

Hypothesis: 78% WR signal exists at thresh>=200 but RR is too small at
fixed 1.5pt target. Use trailing stop to capture larger moves when
they occur.

Logic:
  - Enter at next tick AFTER large print (continuation direction)
  - Initial stop at entry +/- init_stop
  - As price moves favorably:
      - When unrealized profit reaches `trail_activate_pts`, move stop to
        entry (breakeven)
      - As favorable price moves further, trail stop at `trail_distance_pts`
        behind highest favorable price
  - Time stop: exit at end of `max_hold_secs`
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD = 50.0
MAX_CONTRACTS = 5


def _size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def run_trail(price, ts_ns, volume, aggressor,
              large_threshold,
              init_stop_pts: float,
              trail_activate_pts: float,
              trail_distance_pts: float,
              max_hold_secs: int,
              cooldown_secs: int,
              comm_per_contract: float = 2.0):
    n = len(price)
    hold_ns = max_hold_secs * 1_000_000_000
    cd_ns = cooldown_secs * 1_000_000_000
    size = _size(init_stop_pts)

    trigger_mask = (volume >= large_threshold) & (aggressor != 0)
    trigger_idx = np.where(trigger_mask)[0]
    if len(trigger_idx) == 0:
        return np.array([], dtype=np.float32)

    pnls = []
    last_exit_ts = -1

    for trig_i in trigger_idx:
        trig_ts = ts_ns[trig_i]
        if last_exit_ts > 0 and trig_ts - last_exit_ts < cd_ns:
            continue
        if trig_i + 1 >= n: continue

        entry_idx = trig_i + 1
        entry_px = float(price[entry_idx])
        entry_ts = ts_ns[entry_idx]
        side = 1 if aggressor[trig_i] == 1 else -1   # continuation

        if side == 1:
            stop_px = entry_px - init_stop_pts
        else:
            stop_px = entry_px + init_stop_pts

        # find end-of-hold idx
        deadline_ts = entry_ts + hold_ns
        end_idx = min(np.searchsorted(ts_ns, deadline_ts, side="left"), n - 1)
        if end_idx <= entry_idx: continue

        # iterate forward through ticks; trail stop
        best_favorable = entry_px
        exit_px = None
        exit_ts = None
        scan_range = range(entry_idx, end_idx + 1)
        for j in scan_range:
            p = float(price[j])
            # update best favorable
            if side == 1 and p > best_favorable:
                best_favorable = p
            elif side == -1 and p < best_favorable:
                best_favorable = p
            # trailing activation: move stop to entry once we've reached
            # trail_activate_pts in profit
            if side == 1:
                if best_favorable >= entry_px + trail_activate_pts:
                    # trail stop = best_favorable - trail_distance_pts, but never worse than BE
                    new_stop = best_favorable - trail_distance_pts
                    if new_stop > stop_px:
                        stop_px = new_stop
            else:
                if best_favorable <= entry_px - trail_activate_pts:
                    new_stop = best_favorable + trail_distance_pts
                    if new_stop < stop_px:
                        stop_px = new_stop
            # exit check
            if side == 1 and p <= stop_px:
                exit_px = stop_px
                exit_ts = ts_ns[j]
                break
            elif side == -1 and p >= stop_px:
                exit_px = stop_px
                exit_ts = ts_ns[j]
                break

        if exit_px is None:
            # timeout
            exit_px = float(price[end_idx])
            exit_ts = ts_ns[end_idx]

        pnl_pts = (exit_px - entry_px) if side == 1 else (entry_px - exit_px)
        pnl = pnl_pts * size * MNQ_PER_PT - comm_per_contract * size
        pnls.append(pnl)
        last_exit_ts = exit_ts

    return np.array(pnls, dtype=np.float32)


def summarize(pnls, n_days):
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
    months = n_days / 30.44
    return {
        "n": n, "wr": wins/n, "pf": pf,
        "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
        "total": float(pnls.sum()), "per": float(pnls.mean()),
        "trades_per_mo": n/months, "trades_per_day": n/n_days,
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
    n_days = df["ts"].dt.tz_convert("America/New_York").dt.date.nunique()
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    del df
    print(f"  {len(price):,} ticks, {n_days} days\n")

    print(f"{'Thresh':>7} {'IStop':>6} {'TrAct':>6} {'TrDist':>6} {'Hold':>5} {'Comm':>5} "
          f"{'n':>5} {'/mo':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>6} {'Total':>9} {'DD%':>5} {'Strk':>4} {'Ret/mo':>7}")
    print("-" * 130)

    all_results = []
    for thresh in [50, 100, 200, 300]:
        for istop in [1.0, 2.0]:
            for tract in [0.5, 1.0, 1.5, 2.0]:
                for trdist in [0.5, 1.0, 1.5]:
                    for hold in [60, 180, 600]:
                        for comm in [2.0, 0.5]:   # try realistic vs cheaper broker
                            pnls = run_trail(price, ts_ns, volume, aggressor,
                                             thresh, istop, tract, trdist, hold,
                                             cooldown_secs=10,
                                             comm_per_contract=comm)
                            s = summarize(pnls, n_days)
                            if not s or s["n"] < 30: continue
                            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                            tag = ""
                            if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                            elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 1: tag = " ★★"
                            elif s["wr"] >= 0.55: tag = " ★ WR"
                            elif s["ret_per_mo"] >= 0.5: tag = " ★"
                            elif s["total"] > 0: tag = " +"
                            print(f"{thresh:>7} {istop:>5.1f} {tract:>5.1f} "
                                  f"{trdist:>5.1f} {hold:>4}s ${comm:>3.1f} "
                                  f"{s['n']:>5} {s['trades_per_mo']:>4.1f} "
                                  f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                                  f"${s['per']:>+4,.0f} ${s['total']:>+7,.0f} "
                                  f"{abs(s['maxdd_pct']):>4.1f}% "
                                  f"{s['max_streak']:>3} {s['ret_per_mo']:>+5.2f}%{tag}")
                            all_results.append({**s, "thresh": thresh, "istop": istop,
                                                "tract": tract, "trdist": trdist,
                                                "hold": hold, "comm": comm})

    print(f"\nElapsed: {time.time()-t0:.0f}s, {len(all_results)} valid configs\n")
    print("=" * 100)
    print("TOP 15 BY RET/MO")
    print("=" * 100)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:15]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = " ★★★★ HITS SPEC!" if hits_spec(r) else ""
        print(f"  thresh={r['thresh']:>3} istop={r['istop']:.1f} tract={r['tract']:.1f} "
              f"trdist={r['trdist']:.1f} hold={r['hold']:>3}s ${r['comm']:.1f} | "
              f"n={r['n']:>3} ({r['trades_per_mo']:.0f}/mo) WR={r['wr']*100:.1f}% "
              f"PF={pf} RR={r['rr']:.2f} DD={abs(r['maxdd_pct']):.1f}% "
              f"strk={r['max_streak']} → {r['ret_per_mo']:+.2f}%/mo{flag}")


if __name__ == "__main__":
    main()

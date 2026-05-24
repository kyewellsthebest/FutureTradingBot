"""Large-trade fade — FAST version using trigger-then-scan algorithm.

Algorithm:
  1. Pre-compute trigger indices: where volume >= threshold (vectorized)
  2. For each trigger, scan forward only the small window needed to find exit
  3. Cooldown handled by skipping triggers within window of previous exit
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


def run_fade(price, ts_ns, volume, aggressor,
             large_threshold, stop_pts, target_pts,
             hold_secs, cooldown_secs):
    """Trigger-then-scan. Returns array of P&L per trade + summary."""
    n = len(price)
    hold_ns = hold_secs * 1_000_000_000
    cd_ns = cooldown_secs * 1_000_000_000
    size = _size(stop_pts)

    # 1. find trigger indices (vol >= threshold AND non-zero aggressor)
    trigger_mask = (volume >= large_threshold) & (aggressor != 0)
    trigger_idx = np.where(trigger_mask)[0]
    if len(trigger_idx) == 0:
        return np.array([], dtype=np.float32)

    pnls = []
    last_exit_ts = -1

    # for fast forward-scan, we need to find the index range corresponding to
    # `hold_ns` after each trigger. We can binary-search ts_ns.
    for trig_i in trigger_idx:
        # cooldown check
        trig_ts = ts_ns[trig_i]
        if last_exit_ts > 0 and trig_ts - last_exit_ts < cd_ns:
            continue
        if trig_i + 1 >= n: continue

        # Entry at next tick
        entry_idx = trig_i + 1
        entry_px = float(price[entry_idx])
        entry_ts = ts_ns[entry_idx]
        # CONTINUATION mode: trade WITH the large flow
        side = 1 if aggressor[trig_i] == 1 else -1
        if side == 1:
            stop_px = entry_px - stop_pts
            target_px = entry_px + target_pts
        else:
            stop_px = entry_px + stop_pts
            target_px = entry_px - target_pts

        # find the index just past hold_ns
        deadline_ts = entry_ts + hold_ns
        end_idx = np.searchsorted(ts_ns, deadline_ts, side="left")
        end_idx = min(end_idx, n - 1)
        if end_idx <= entry_idx:
            continue

        # scan forward — find first stop or target hit
        scan = price[entry_idx:end_idx + 1]
        if side == 1:
            stop_hits = scan <= stop_px
            tgt_hits  = scan >= target_px
        else:
            stop_hits = scan >= stop_px
            tgt_hits  = scan <= target_px

        # earliest exit
        stop_first = np.argmax(stop_hits) if stop_hits.any() else len(scan)
        tgt_first  = np.argmax(tgt_hits)  if tgt_hits.any()  else len(scan)
        first = min(stop_first, tgt_first)
        if first < len(scan):
            if stop_first <= tgt_first:
                exit_px = stop_px
            else:
                exit_px = target_px
            exit_ts = ts_ns[entry_idx + first]
        else:
            # timeout
            exit_px = float(scan[-1])
            exit_ts = ts_ns[entry_idx + len(scan) - 1]

        if side == 1:
            pnl_pts = exit_px - entry_px
        else:
            pnl_pts = entry_px - exit_px
        pnl = pnl_pts * size * MNQ_PER_PT - COMM_PER_CONTRACT_RT * size
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
    print(f"  {len(price):,} ticks, {n_days} days, loaded in {time.time()-t0:.1f}s\n")

    print(f"{'Thresh':>7} {'Stop':>5} {'Tgt':>5} {'Hold':>6} {'CD':>4} "
          f"{'n':>6} {'/mo':>5} {'/day':>5} {'WR':>6} {'PF':>5} "
          f"{'RR':>5} {'$/tr':>6} {'Total':>9} {'DD%':>5} {'Strk':>4} {'Ret/mo':>7}")
    print("-" * 130)

    all_results = []
    cfg_count = 0
    for thresh in [30, 50, 100, 200]:
        for stop in [1.0, 2.0, 3.0, 5.0]:
            for tgt_mult in [1.2, 1.5, 2.0]:
                tgt = stop * tgt_mult
                for hold_s in [30, 60, 180]:
                    for cd_s in [10, 30]:
                        cfg_count += 1
                        t1 = time.time()
                        pnls = run_fade(price, ts_ns, volume, aggressor,
                                        thresh, stop, tgt, hold_s, cd_s)
                        s = summarize(pnls, n_days)
                        if not s or s["n"] < 30: continue
                        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                        tag = ""
                        if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                        elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 1: tag = " ★★"
                        elif s["wr"] >= 0.55: tag = " ★ WR"
                        elif s["ret_per_mo"] >= 0.5: tag = " ★"
                        elif s["total"] > 0: tag = " +"
                        print(f"{thresh:>7} {stop:>5.1f} {tgt:>5.1f} {hold_s:>5}s "
                              f"{cd_s:>3}s {s['n']:>6} {s['trades_per_mo']:>4.1f} "
                              f"{s['trades_per_day']:>4.1f} {s['wr']*100:>5.1f}% "
                              f"{pf:>5} {s['rr']:>4.2f} ${s['per']:>+4,.0f} "
                              f"${s['total']:>+7,.0f} {abs(s['maxdd_pct']):>4.1f}% "
                              f"{s['max_streak']:>3} {s['ret_per_mo']:>+5.2f}%{tag}")
                        all_results.append({**s, "thresh": thresh, "stop": stop,
                                            "tgt": tgt, "hold": hold_s, "cd": cd_s})

    print(f"\nTotal configs tested: {cfg_count}, elapsed: {time.time()-t0:.0f}s")

    print("\n" + "=" * 100)
    print("TOP 15 BY MONTHLY RETURN")
    print("=" * 100)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:15]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = " ★★★★ HITS SPEC!" if hits_spec(r) else ""
        print(f"  thresh={r['thresh']:>3} stop={r['stop']:.1f} tgt={r['tgt']:.1f} "
              f"hold={r['hold']:>3}s cd={r['cd']:>2}s | "
              f"n={r['n']:>4} ({r['trades_per_mo']:.0f}/mo) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% strk={r['max_streak']} "
              f"→ {r['ret_per_mo']:+.2f}%/mo{flag}")


if __name__ == "__main__":
    main()

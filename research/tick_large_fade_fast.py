"""Large-Trade Fade strategy on NQ tick data — FAST numba version.

Same logic as tick_large_fade.py but with @njit for 100x+ speedup.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from numba import njit

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD = 50.0
MAX_CONTRACTS = 5


@njit(cache=True)
def _run(price, ts_ns, volume, aggressor,
         large_threshold: int,
         stop_pts: float, target_pts: float,
         hold_ns: int, cooldown_ns: int):
    n = len(price)
    # Pre-allocate output arrays (oversized; truncate later)
    max_trades = n // 100   # safety upper bound
    out_side = np.zeros(max_trades, dtype=np.int8)        # +1 LONG, -1 SHORT
    out_size = np.zeros(max_trades, dtype=np.int8)
    out_entry_ts = np.zeros(max_trades, dtype=np.int64)
    out_exit_ts = np.zeros(max_trades, dtype=np.int64)
    out_entry_px = np.zeros(max_trades, dtype=np.float32)
    out_exit_px = np.zeros(max_trades, dtype=np.float32)
    out_pnl = np.zeros(max_trades, dtype=np.float32)
    out_reason = np.zeros(max_trades, dtype=np.int8)  # 0=stop 1=target 2=time
    out_trig_vol = np.zeros(max_trades, dtype=np.int32)

    n_trades = 0
    last_trade_ts = -1
    active = False
    a_side = 0   # +1 LONG, -1 SHORT
    a_size = 0
    a_entry = 0.0
    a_stop = 0.0
    a_target = 0.0
    a_entry_ts = 0
    a_trig_vol = 0

    # pre-compute size for each possible stop_pts (just one value here)
    if stop_pts <= 0:
        size_per_trade = 1
    else:
        raw = TARGET_RISK_USD / (stop_pts * MNQ_PER_PT)
        size_per_trade = int(max(1, min(MAX_CONTRACTS, int(raw))))

    for i in range(n - 1):
        # Manage active trade
        if active:
            cur_px = price[i]
            cur_ts = ts_ns[i]
            stop_hit = (a_side == 1 and cur_px <= a_stop) or \
                       (a_side == -1 and cur_px >= a_stop)
            tgt_hit = (a_side == 1 and cur_px >= a_target) or \
                      (a_side == -1 and cur_px <= a_target)
            time_up = (cur_ts - a_entry_ts) >= hold_ns
            exit_now = False
            exit_px = 0.0
            reason = 0
            if stop_hit:
                exit_px = a_stop; reason = 0; exit_now = True
            elif tgt_hit:
                exit_px = a_target; reason = 1; exit_now = True
            elif time_up:
                exit_px = cur_px; reason = 2; exit_now = True
            if exit_now:
                if a_side == 1:
                    pnl_pts = exit_px - a_entry
                else:
                    pnl_pts = a_entry - exit_px
                pnl = pnl_pts * a_size * MNQ_PER_PT - COMM_PER_CONTRACT_RT * a_size
                # store
                out_side[n_trades] = a_side
                out_size[n_trades] = a_size
                out_entry_ts[n_trades] = a_entry_ts
                out_exit_ts[n_trades] = cur_ts
                out_entry_px[n_trades] = a_entry
                out_exit_px[n_trades] = exit_px
                out_pnl[n_trades] = pnl
                out_reason[n_trades] = reason
                out_trig_vol[n_trades] = a_trig_vol
                n_trades += 1
                last_trade_ts = cur_ts
                active = False

        # New entry?
        if not active and volume[i] >= large_threshold:
            if last_trade_ts > 0 and ts_ns[i] - last_trade_ts < cooldown_ns:
                continue
            agg = aggressor[i]
            if agg == 0:
                continue
            entry_px = price[i + 1]
            if agg == 1:
                # large BUY → SHORT (fade)
                a_side = -1
                a_stop = entry_px + stop_pts
                a_target = entry_px - target_pts
            else:
                # large SELL → LONG (fade)
                a_side = 1
                a_stop = entry_px - stop_pts
                a_target = entry_px + target_pts
            a_size = size_per_trade
            a_entry = entry_px
            a_entry_ts = ts_ns[i + 1]
            a_trig_vol = volume[i]
            active = True

    return (out_side[:n_trades], out_size[:n_trades],
            out_entry_ts[:n_trades], out_exit_ts[:n_trades],
            out_entry_px[:n_trades], out_exit_px[:n_trades],
            out_pnl[:n_trades], out_reason[:n_trades],
            out_trig_vol[:n_trades])


def stats(pnls, max_streak_in, n_calendar_days):
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
    months = n_calendar_days / 30.44
    return {
        "n": n, "wr": wins/n, "pf": pf,
        "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
        "total": float(pnls.sum()), "per": float(pnls.mean()),
        "trades_per_mo": n/months, "trades_per_day": n/n_calendar_days,
        "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
        "max_streak": max_streak_in,
        "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months,
    }


def calc_max_streak(pnls):
    streak = max_streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else:
            streak = 0
    return max_streak


def hits_spec(s):
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0 and abs(s["maxdd_pct"]) <= 2.0)


def main():
    print("Loading tick parquet...")
    df = pd.read_parquet(SRC)
    n_days = df["ts"].dt.tz_convert("America/New_York").dt.date.nunique()
    print(f"  ticks: {len(df):,}   days: {n_days}")

    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    del df

    # Warm up JIT with tiny call
    print("Warming JIT...")
    _ = _run(price[:100], ts_ns[:100], volume[:100], aggressor[:100],
             1, 1.0, 1.0, 10_000_000_000, 1_000_000_000)
    print("OK\n")

    print(f"{'Thresh':>7} {'Stop':>5} {'Tgt':>5} {'Hold':>6} {'CD':>4} "
          f"{'Trades':>7} {'/mo':>5} {'/day':>5} {'WR':>6} {'PF':>5} "
          f"{'RR':>5} {'$/tr':>6} {'Total':>9} {'DD%':>5} {'Strk':>4} {'Ret/mo':>7}")
    print("-" * 130)

    all_results = []
    for thresh in [30, 50, 100, 200]:
        for stop in [1.0, 2.0, 3.0, 5.0]:
            for tgt_mult in [1.2, 1.5, 2.0, 3.0]:
                tgt = stop * tgt_mult
                for hold_s in [30, 60, 180]:
                    for cd_s in [10, 30]:
                        hold_ns = hold_s * 1_000_000_000
                        cd_ns = cd_s * 1_000_000_000
                        out = _run(price, ts_ns, volume, aggressor,
                                   thresh, stop, tgt, hold_ns, cd_ns)
                        pnls = out[6]   # out_pnl
                        if len(pnls) < 30: continue
                        streak = calc_max_streak(pnls)
                        s = stats(pnls, streak, n_days)
                        if not s: continue
                        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                        tag = ""
                        if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                        elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 1: tag = " ★★"
                        elif s["wr"] >= 0.55: tag = " ★ WR ok"
                        elif s["ret_per_mo"] >= 0.5: tag = " ★"
                        elif s["total"] > 0: tag = " +"
                        print(f"{thresh:>7} {stop:>5.1f} {tgt:>5.1f} {hold_s:>5}s "
                              f"{cd_s:>3}s {s['n']:>7} {s['trades_per_mo']:>4.1f} "
                              f"{s['trades_per_day']:>4.1f} {s['wr']*100:>5.1f}% "
                              f"{pf:>5} {s['rr']:>4.2f} ${s['per']:>+4,.0f} "
                              f"${s['total']:>+7,.0f} {abs(s['maxdd_pct']):>4.1f}% "
                              f"{streak:>3} {s['ret_per_mo']:>+5.2f}%{tag}")
                        all_results.append({**s, "thresh": thresh, "stop": stop,
                                            "tgt": tgt, "hold": hold_s, "cd": cd_s})

    print("\n" + "=" * 80)
    print("TOP 15 BY MONTHLY RETURN")
    print("=" * 80)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:15]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        flag = "★★★★ HITS SPEC!" if hits_spec(r) else ""
        print(f"  thresh={r['thresh']} stop={r['stop']:.1f} tgt={r['tgt']:.1f} "
              f"hold={r['hold']}s cd={r['cd']}s | "
              f"n={r['n']} ({r['trades_per_mo']:.0f}/mo) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% → {r['ret_per_mo']:+.2f}%/mo {flag}")


if __name__ == "__main__":
    main()

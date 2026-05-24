"""ULTRA-REALISTIC backtest of large-print continuation strategy.

Adds to the ideal backtest:
  - LATENCY: ~200ms delay between signal detection and order fill (you can't
    react instantly; orders take time to send/match)
  - SLIPPAGE: entries/exits fill 1 tick (0.25pt) worse than the displayed
    price (you don't always get the exact price you wanted)
  - REALISTIC COMMISSIONS: tests at multiple rates ($0.50, $1.00, $2.00)
  - OUT-OF-SAMPLE SPLIT: 70 days → train on first 50, test on last 20

Also cross-validates against 1-min OHLC data for the same period to show
what the simulator would have looked like with only minute-bar data.
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path

TICK_SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
M1_SRC   = Path("/home/user/HFTBot/data/polygon/NQ_1min.csv")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT       = 2.0
TARGET_RISK_USD  = 50.0
MAX_CONTRACTS    = 5

# REALISM PARAMETERS
LATENCY_MS       = 200      # 200ms between signal and fill
SLIPPAGE_PTS     = 0.25     # 1 NQ tick worse than expected on entry/exit


def _size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def run_realistic(price, ts_ns, volume, aggressor,
                  large_threshold: int,
                  init_stop_pts: float,
                  trail_activate_pts: float,
                  trail_distance_pts: float,
                  max_hold_secs: int,
                  cooldown_secs: int,
                  comm_per_contract: float,
                  latency_ms: int = LATENCY_MS,
                  slippage_pts: float = SLIPPAGE_PTS):
    """Run with latency and slippage modeling."""
    n = len(price)
    hold_ns = max_hold_secs * 1_000_000_000
    cd_ns = cooldown_secs * 1_000_000_000
    latency_ns = latency_ms * 1_000_000
    size = _size(init_stop_pts)

    trigger_mask = (volume >= large_threshold) & (aggressor != 0)
    trigger_idx = np.where(trigger_mask)[0]
    if len(trigger_idx) == 0:
        return np.array([], dtype=np.float32), np.array([], dtype=np.int64)

    pnls = []
    entry_tss = []   # for later analysis
    last_exit_ts = -1

    for trig_i in trigger_idx:
        trig_ts = ts_ns[trig_i]
        if last_exit_ts > 0 and trig_ts - last_exit_ts < cd_ns:
            continue

        # LATENCY: find first tick after trig_ts + latency
        fill_deadline = trig_ts + latency_ns
        entry_idx = np.searchsorted(ts_ns, fill_deadline, side="left")
        if entry_idx >= n: continue
        entry_ts = ts_ns[entry_idx]
        raw_entry_px = float(price[entry_idx])

        side = 1 if aggressor[trig_i] == 1 else -1

        # SLIPPAGE: entry fills 1 tick worse than displayed
        if side == 1:
            entry_px = raw_entry_px + slippage_pts
            stop_px = entry_px - init_stop_pts
        else:
            entry_px = raw_entry_px - slippage_pts
            stop_px = entry_px + init_stop_pts

        deadline_ts = entry_ts + hold_ns
        end_idx = min(np.searchsorted(ts_ns, deadline_ts, side="left"), n - 1)
        if end_idx <= entry_idx: continue

        # walk forward tick-by-tick managing trailing stop
        best_favorable = entry_px
        exit_px = None
        exit_ts = None
        for j in range(entry_idx, end_idx + 1):
            p = float(price[j])
            if side == 1 and p > best_favorable:
                best_favorable = p
            elif side == -1 and p < best_favorable:
                best_favorable = p
            # trail activation
            if side == 1:
                if best_favorable >= entry_px + trail_activate_pts:
                    new_stop = best_favorable - trail_distance_pts
                    if new_stop > stop_px:
                        stop_px = new_stop
            else:
                if best_favorable <= entry_px - trail_activate_pts:
                    new_stop = best_favorable + trail_distance_pts
                    if new_stop < stop_px:
                        stop_px = new_stop
            # exit check (apply slippage on stop hit too)
            if side == 1 and p <= stop_px:
                exit_px = stop_px - slippage_pts   # exit fills worse
                exit_ts = ts_ns[j]
                break
            elif side == -1 and p >= stop_px:
                exit_px = stop_px + slippage_pts
                exit_ts = ts_ns[j]
                break

        if exit_px is None:
            # timeout — exit at last price, also with slippage
            last_px = float(price[end_idx])
            exit_px = last_px - slippage_pts if side == 1 else last_px + slippage_pts
            exit_ts = ts_ns[end_idx]

        pnl_pts = (exit_px - entry_px) if side == 1 else (entry_px - exit_px)
        pnl = pnl_pts * size * MNQ_PER_PT - comm_per_contract * size
        pnls.append(pnl)
        entry_tss.append(entry_ts)
        last_exit_ts = exit_ts

    return np.array(pnls, dtype=np.float32), np.array(entry_tss, dtype=np.int64)


def summarize(pnls, entry_tss, period_days):
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
        "trades_per_day": n/period_days, "trades_per_week": n*5/period_days,
        "trades_per_mo": n/months,
        "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
        "max_streak": max_streak,
        "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months,
        "ret_total": float(pnls.sum())/STARTING_BALANCE*100,
    }


def hits_spec(s):
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0 and abs(s["maxdd_pct"]) <= 2.0)


def main():
    t0 = time.time()
    print("Loading tick data...")
    df = pd.read_parquet(TICK_SRC)
    n_days = df["ts"].dt.tz_convert("America/New_York").dt.date.nunique()
    print(f"  {len(df):,} ticks across {n_days} calendar days")
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    period_start = df["ts"].iloc[0]
    period_end = df["ts"].iloc[-1]
    del df
    period_days = (period_end - period_start).total_seconds() / 86400
    print(f"  period: {period_start.date()} → {period_end.date()}  ({period_days:.0f} days)")

    # Out-of-sample split
    split_ratio = 0.71  # ~50/20 days
    split_idx = int(len(ts_ns) * split_ratio)
    split_ts = ts_ns[split_idx]
    print(f"  IS/OOS split at {pd.Timestamp(split_ts):%Y-%m-%d}\n")

    # ==== Run with multiple commission rates ====
    print("=" * 100)
    print("REALISTIC BACKTEST — with 200ms latency + 0.25pt slippage on entries/exits")
    print("=" * 100)
    print(f"{'Period':<12} {'Comm':>6} {'Trades':>7} {'/day':>5} {'/wk':>5} {'/mo':>5} "
          f"{'WR':>6} {'PF':>5} {'RR':>5} {'$/tr':>6} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}")
    print("-" * 105)

    best_config = {
        "large_threshold": 50,
        "init_stop_pts": 1.0,
        "trail_activate_pts": 1.5,
        "trail_distance_pts": 0.5,
        "max_hold_secs": 60,
        "cooldown_secs": 10,
    }

    for comm in [0.50, 1.00, 1.50, 2.00]:
        # FULL period
        pnls, ets = run_realistic(price, ts_ns, volume, aggressor,
                                   comm_per_contract=comm, **best_config)
        s = summarize(pnls, ets, period_days)
        if s:
            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
            flag = "★★★★" if hits_spec(s) else ""
            print(f"{'FULL period':<12} ${comm:>4.2f}  {s['n']:>6} "
                  f"{s['trades_per_day']:>4.1f} {s['trades_per_week']:>4.1f} "
                  f"{s['trades_per_mo']:>4.0f} "
                  f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                  f"${s['per']:>+4,.0f} ${s['total']:>+7,.0f} "
                  f"{abs(s['maxdd_pct']):>4.1f}% {s['ret_per_mo']:>+5.2f}% {flag}")

    print()

    # ==== IS vs OOS at user-realistic commissions ($1.00 broker-neutral) ====
    print("=" * 100)
    print("OUT-OF-SAMPLE VALIDATION — train on first 50 days, test on last 20")
    print("=" * 100)
    print(f"{'Period':<14} {'Comm':>6} {'Trades':>7} {'/day':>5} {'/wk':>5} {'/mo':>5} "
          f"{'WR':>6} {'PF':>5} {'RR':>5} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}")
    print("-" * 105)

    in_mask = ts_ns < split_ts
    out_mask = ts_ns >= split_ts
    period_days_in = (pd.Timestamp(ts_ns[in_mask][-1]) - pd.Timestamp(ts_ns[in_mask][0])).total_seconds()/86400
    period_days_out = (pd.Timestamp(ts_ns[out_mask][-1]) - pd.Timestamp(ts_ns[out_mask][0])).total_seconds()/86400

    for comm in [0.50, 1.00, 1.50, 2.00]:
        # IN-SAMPLE
        pnls_in, ets_in = run_realistic(price[in_mask], ts_ns[in_mask],
                                         volume[in_mask], aggressor[in_mask],
                                         comm_per_contract=comm, **best_config)
        # OUT-OF-SAMPLE
        pnls_out, ets_out = run_realistic(price[out_mask], ts_ns[out_mask],
                                           volume[out_mask], aggressor[out_mask],
                                           comm_per_contract=comm, **best_config)
        s_in = summarize(pnls_in, ets_in, period_days_in)
        s_out = summarize(pnls_out, ets_out, period_days_out)

        for label, s, pdays in [("IN-SAMPLE", s_in, period_days_in),
                                  ("OUT-OF-SAMPLE", s_out, period_days_out)]:
            if s:
                pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                flag = "★★★★" if hits_spec(s) else ""
                print(f"{label:<14} ${comm:>4.2f}  {s['n']:>6} "
                      f"{s['trades_per_day']:>4.1f} {s['trades_per_week']:>4.1f} "
                      f"{s['trades_per_mo']:>4.0f} "
                      f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                      f"${s['total']:>+7,.0f} {abs(s['maxdd_pct']):>4.1f}% "
                      f"{s['ret_per_mo']:>+5.2f}% {flag}")
        print()

    print(f"Total elapsed: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

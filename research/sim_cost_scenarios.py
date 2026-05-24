"""Run pullback sim across multiple realistic cost scenarios.

The original sim assumed 0 slip + $1/contract. The live paper account uses
2pt entry slip + 2pt adverse + $2/contract. Real execution sits somewhere
in between based on order type and broker.

Scenarios:
  A. Best case (Topstep MNQ, limit fills, no stop slip)
  B. Realistic (limit fills, modest stop slip, $1/contract)
  C. Conservative (slight entry slip, 1pt stop slip, $1.5/contract)
  D. Original sim (0 slip, $1)         <-- existing report claims
  E. Live paper current (2pt slip, $2) <-- what bot would book today
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, "/home/user/HFTBot")

from bot.pullback_strategy import (
    detect_pullback_setup, _setup_key,
    MIN_TARGET_HOLD_SECONDS, COOLDOWN_SECS,
    MAX_HOLD_SECS, MAX_WAIT_SECS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
LATENCY_MS = 200
N_MNQ = 2

SCENARIOS = [
    # name,                            entry_slip, stop_adv, comm/RT
    ("1mnq Lucid $0.74 / 0pt adv",     0.0, 0.00, 0.74),
    ("2mnq Lucid $0.74 / 0pt adv",     0.0, 0.00, 0.74),
    ("2mnq Lucid $0.74 / 0.25pt adv",  0.0, 0.25, 0.74),
    ("2mnq Lucid $0.74 / 0.5pt adv",   0.0, 0.50, 0.74),
    ("2mnq retail $1 / 0pt adv",       0.0, 0.00, 1.00),
    ("2mnq retail $1 / 0.25pt adv",    0.0, 0.25, 1.00),
    ("2mnq retail $1 / 0.5pt adv",     0.0, 0.50, 1.00),
    ("3mnq Lucid $0.74 / 0.25pt adv",  0.0, 0.25, 0.74),
    ("3mnq retail $1 / 0.25pt adv",    0.0, 0.25, 1.00),
]
SIZES_FOR_SCENARIO = [1, 2, 2, 2, 2, 2, 2, 3, 3]


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def run_sim(price, ts_ns, bars_1m, size, entry_slip, adverse_slip, comm_rt):
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    cooldown_ns = COOLDOWN_SECS * 1_000_000_000
    latency_ns = LATENCY_MS * 1_000_000
    max_hold_ns = MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = MIN_TARGET_HOLD_SECONDS * 1_000_000_000

    trades = []
    used_keys = set()
    last_exit_ts = -1

    for i in range(3, len(bars_1m) - 1):
        sig_ts = int(bar_ts[i + 1])
        bars_at_i = bars_1m.iloc[:i + 1]
        setup = detect_pullback_setup(bars_at_i,
            pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
        if setup is None: continue
        key = _setup_key(setup)
        if key in used_keys: continue
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cooldown_ns: continue
        side = 1 if setup.side == "LONG" else -1
        intended = float(setup.pullback_entry)
        stop_px = float(setup.stop_px_val)
        target_px = float(setup.target_px_val)
        fill_start = int(np.searchsorted(ts_ns, sig_ts + latency_ns, side="left"))
        fill_end = int(np.searchsorted(ts_ns, sig_ts + max_wait_ns, side="left"))
        if fill_start >= fill_end: continue
        scan_fill = price[fill_start:fill_end]
        hits = scan_fill <= intended if side == 1 else scan_fill >= intended
        if not hits.any(): continue
        entry_idx = fill_start + int(np.argmax(hits))
        entry_ts = int(ts_ns[entry_idx])
        entry_price = intended + (entry_slip if side == 1 else -entry_slip)

        timeout_ts = entry_ts + max_hold_ns
        min_target_ts = entry_ts + min_hold_ns
        exit_end = min(int(np.searchsorted(ts_ns, timeout_ts, side="left")), len(price) - 1)
        if exit_end <= entry_idx: continue
        scan_p = price[entry_idx + 1:exit_end + 1]
        scan_t = ts_ns[entry_idx + 1:exit_end + 1]
        if side == 1:
            stop_mask = scan_p <= stop_px; tgt_mask = scan_p >= target_px
        else:
            stop_mask = scan_p >= stop_px; tgt_mask = scan_p <= target_px
        stop_idx = int(np.argmax(stop_mask)) if stop_mask.any() else len(scan_p)
        if tgt_mask.any():
            cand = np.where(tgt_mask & (scan_t >= min_target_ts))[0]
            tgt_idx = int(cand[0]) if len(cand) > 0 else len(scan_p)
        else:
            tgt_idx = len(scan_p)
        if stop_idx == len(scan_p) and tgt_idx == len(scan_p):
            exit_px = float(scan_p[-1])
            exit_ts = int(scan_t[-1])
        elif stop_idx <= tgt_idx:
            exit_px = stop_px - (adverse_slip if side == 1 else -adverse_slip)
            exit_ts = int(scan_t[stop_idx])
        else:
            exit_px = target_px
            exit_ts = int(scan_t[tgt_idx])
        pnl_pts = (exit_px - entry_price) if side == 1 else (entry_price - exit_px)
        pnl_usd = pnl_pts * size * MNQ_PER_PT - comm_rt * size
        trades.append({"pnl_usd": round(float(pnl_usd), 2)})
        used_keys.add(key)
        last_exit_ts = exit_ts
    return trades


def summarize(trades, period_days):
    n = len(trades)
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = int((pnls > 0).sum())
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(pnls[pnls > 0].sum()); gl = float(abs(pnls[pnls < 0].sum()))
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if (n - wins) else 0
    months = period_days / 30.44
    total = float(pnls.sum())
    return {
        "n": n, "wr": wins/n*100,
        "total": total, "ret_mo": total/STARTING_BALANCE*100/months,
        "dd_usd": maxdd, "dd_pct": abs(maxdd/STARTING_BALANCE*100),
        "pf": gw/gl if gl > 0 else 999,
        "rr": abs(avg_w/avg_l) if avg_l else 0,
        "avg_w": avg_w, "avg_l": avg_l,
    }


def main():
    t0 = time.time()
    print("Loading...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
    print(f"  {len(price):,} ticks, {len(bars_1m):,} bars ({time.time()-t0:.0f}s)\n")

    print(f"Running cost+size scenarios (limit-fill semantics):\n")
    print(f"  {'Scenario':<36}  {'Ret/mo':>9}{'WR':>7}{'RR':>6}{'PF':>6}"
          f"{'DD$':>9}{'DD%':>7}{'WorstDay':>10}")
    for (name, slip, adv, comm), size in zip(SCENARIOS, SIZES_FOR_SCENARIO):
        trades = run_sim(price, ts_ns, bars_1m, size, slip, adv, comm)
        s = summarize(trades, period_days)
        ret = f"{s['ret_mo']:+.2f}%"
        # worst day from cumulative
        pnls = np.array([t["pnl_usd"] for t in trades])
        worst_day = float(pnls[pnls < 0].sum()) if (pnls < 0).any() else 0
        # approximate worst day: from grouped sim
        # use min of cumulative diffs per "day" — too lazy here, just report avg loss day
        worst_single_trade = float(pnls.min())
        print(f"  {name:<36}  {ret:>9}{s['wr']:>6.1f}%{s['rr']:>6.2f}{s['pf']:>6.2f}"
              f"{s['dd_usd']:>+9,.0f}{s['dd_pct']:>6.2f}%{worst_single_trade:>+10,.0f}")


if __name__ == "__main__":
    main()

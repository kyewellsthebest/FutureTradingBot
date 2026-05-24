"""Re-simulate the pullback strategy using the LIVE paper_account cost model.

Live model (from research/signal_filters.py + bot/paper_trading.py):
  SLIPPAGE_POINTS = 2.0           applied always at entry (entry_px += 2 LONG / -= 2 SHORT)
  ADVERSE_SLIPPAGE_POINTS = 2.0   extra slip on stop fills (exit -= 2 LONG / += 2 SHORT)
  COMMISSION_ROUND_TRIP = 60.0    for CONTRACTS=30 => $2/contract RT
  DOLLARS_PER_POINT = 60.0        for CONTRACTS=30 => $2/contract/pt

Previous sim model used 0 entry slip, 0 adverse slip, $1/contract RT.
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
    IMPULSE_PTS, IMPULSE_WINDOW_BARS, PULLBACK_PCT,
    STOP_PTS, TARGET_PTS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
LATENCY_MS = 200
N_MNQ = 2

# LIVE cost model (matches paper_trading.py at runtime)
ENTRY_SLIP_PTS = 2.0
ADVERSE_SLIP_PTS = 2.0
COMM_PER_CONTRACT_RT = 2.0  # was $1 in earlier sim, real live is $60/30=$2


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def run_sim_live_costs(price, ts_ns, bars_1m, size):
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
        intended_entry = float(setup.pullback_entry)
        stop_px = float(setup.stop_px_val)
        target_px = float(setup.target_px_val)
        fill_start = int(np.searchsorted(ts_ns, sig_ts + latency_ns, side="left"))
        fill_end = int(np.searchsorted(ts_ns, sig_ts + max_wait_ns, side="left"))
        if fill_start >= fill_end: continue
        scan_fill = price[fill_start:fill_end]
        hits = scan_fill <= intended_entry if side == 1 else scan_fill >= intended_entry
        if not hits.any(): continue
        entry_idx = fill_start + int(np.argmax(hits))
        entry_ts = int(ts_ns[entry_idx])

        # LIVE COST MODEL: +2pt entry slip
        entry_price = intended_entry + (ENTRY_SLIP_PTS if side == 1 else -ENTRY_SLIP_PTS)

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
            exit_px_raw = float(scan_p[-1]); exit_ts = int(scan_t[-1]); reason = "timeout"
            exit_px = exit_px_raw  # no adverse on timeout
        elif stop_idx <= tgt_idx:
            exit_px_raw = stop_px; exit_ts = int(scan_t[stop_idx]); reason = "stop"
            # LIVE COST MODEL: +2pt adverse on stops
            exit_px = exit_px_raw - (ADVERSE_SLIP_PTS if side == 1 else -ADVERSE_SLIP_PTS)
        else:
            exit_px_raw = target_px; exit_ts = int(scan_t[tgt_idx]); reason = "target"
            exit_px = exit_px_raw  # no adverse on targets (limit fills)

        pnl_pts = (exit_px - entry_price) if side == 1 else (entry_price - exit_px)
        # LIVE COST MODEL: $2/contract RT commission
        pnl_usd = pnl_pts * size * MNQ_PER_PT - COMM_PER_CONTRACT_RT * size
        trades.append({
            "side": setup.side, "size": size,
            "entry_ts": entry_ts, "exit_ts": exit_ts,
            "entry_px": round(float(entry_price), 2),
            "exit_px": round(float(exit_px), 2),
            "hold_s": round((exit_ts - entry_ts) / 1e9, 2),
            "exit_reason": reason,
            "pnl_usd": round(float(pnl_usd), 2),
        })
        used_keys.add(key)
        last_exit_ts = exit_ts
    return trades


def summarize(trades, period_days, starting_bal=STARTING_BALANCE):
    n = len(trades)
    if n == 0: return None
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = int((pnls > 0).sum())
    losses = int((pnls < 0).sum())
    gw = float(pnls[pnls > 0].sum())
    gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else 999
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if losses else 0
    months = period_days / 30.44
    total = float(pnls.sum())
    return {
        "n_trades": n, "wins": wins, "losses": losses,
        "wr_pct": round(wins/n*100, 2),
        "pf": round(pf, 3),
        "rr": round(abs(avg_w/avg_l) if avg_l else 0, 2),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "total_pnl": round(total, 2),
        "return_pct_per_mo": round(total/starting_bal*100/months, 2),
        "max_dd_usd": round(maxdd, 2),
        "max_dd_pct": round(abs(maxdd/starting_bal*100), 2),
        "trades_per_month": round(n/months, 1),
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
    print(f"  {len(price):,} ticks, {len(bars_1m):,} bars ({time.time()-t0:.0f}s)")

    print(f"\nRunning sim at size={N_MNQ} MNQ with LIVE cost model...")
    print(f"  entry_slip={ENTRY_SLIP_PTS}pt, adverse_slip={ADVERSE_SLIP_PTS}pt, comm=${COMM_PER_CONTRACT_RT}/contract RT")
    trades = run_sim_live_costs(price, ts_ns, bars_1m, size=N_MNQ)
    print(f"  {len(trades)} trades in {time.time()-t0:.0f}s")

    s = summarize(trades, period_days)
    print(f"\n=== LIVE COSTS @ {N_MNQ} MNQ ===")
    for k, v in s.items():
        print(f"  {k:30s} {v}")
    print(f"\nFor comparison the IDEAL (no entry slip, no adverse, $1/contract):")
    print(f"  At 2 MNQ: ret=+10.90%/mo, DD=2.58%, WR=43.9%, RR=1.42, PF=1.12")


if __name__ == "__main__":
    main()

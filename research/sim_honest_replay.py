"""HONEST live-replay simulator.

Calls the bot's ACTUAL strategy code (bot.pullback_strategy.on_new_1m_bar)
bar by bar, exactly as the live runtime does. No look-ahead. No batch
trade generation. Each bar, the bot sees only bars[0:i+1] and decides.

This is the ground truth answer to "would the bot actually have made
this much money on this data?"
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, "/home/user/HFTBot")

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

# Make sure auto-DLL is OFF so it doesn't interfere with the validation.
# (We're testing strategy edge, not the failsafe.)
os.environ["FIB_AUTO_DLL"] = "0"
# Set account context so persistence calls go to account 1's dir.
from bot.account_ctx import set_account, get_strategy_params, _LEGACY_DATA
set_account("1")

# Pause file may exist from earlier tests -- clear it.
pf = _LEGACY_DATA / "manual_pause.json"
if pf.exists():
    pf.unlink()

from bot.pullback_strategy import (
    FibStrategyState, on_new_1m_bar, _in_lucid_closed_window,
    COOLDOWN_SECS, MAX_HOLD_SECS, MAX_WAIT_SECS, DEFAULT_SIZE
)
from research.lucid_guard import LucidState


CSV = "/home/user/HFTBot/data/polygon/NQ_1min.csv"
N_MNQ = 2
STARTING_BALANCE = 50_000.0
HISTORY_BARS = 240   # bot keeps a long lookback for impulse + trend filters
COMM_RT = 0.74       # $/MNQ round trip (from research.lucid_guard)
MNQ_PER_PT = 2.0


def run_replay(bars_df: pd.DataFrame, *, label: str = "REPLAY",
               start_bar: int = HISTORY_BARS):
    """Replay bar by bar. Returns trades list + summary stats."""
    print(f"\n=== {label} ===")
    print(f"  Replay window: {bars_df.index[start_bar]} -> {bars_df.index[-1]}")
    print(f"  Bars to replay: {len(bars_df) - start_bar:,}")

    # Fresh bot state (mirrors what fib_main.FibRuntime would have on startup).
    state = FibStrategyState()
    # Fresh Lucid state. today_pnl starts at 0, no trades yet.
    lucid = LucidState()
    # Strategy params -- account 1 (target=12 legacy).
    params = get_strategy_params("1")

    last_ny_date = None
    trades = []
    # Skip the first HISTORY_BARS so we have lookback context.
    bar_index = bars_df.index
    bar_open = bars_df["open"].to_numpy()
    bar_high = bars_df["high"].to_numpy()
    bar_low = bars_df["low"].to_numpy()
    bar_close = bars_df["close"].to_numpy()
    bar_volume = bars_df["volume"].to_numpy()
    n = len(bars_df)

    progress_every = max(1, (n - start_bar) // 20)
    for i in range(start_bar, n):
        now = bar_index[i].to_pydatetime()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # NY-day roll: matches lucid_account.LucidAccount._maybe_roll_eod.
        # When the NY date changes, fold today_pnl into cum_pnl and reset.
        try:
            from bot.lucid_account import _ny_date_iso
            ny_today = _ny_date_iso(now)
        except Exception:
            ny_today = now.date().isoformat()
        if last_ny_date is not None and ny_today != last_ny_date:
            lucid.cum_pnl += lucid.today_pnl
            lucid.today_pnl = 0.0
        last_ny_date = ny_today

        last_1m_bar = pd.Series({
            "open":  float(bar_open[i]),
            "high":  float(bar_high[i]),
            "low":   float(bar_low[i]),
            "close": float(bar_close[i]),
            "volume": float(bar_volume[i]),
        }, name=bar_index[i])
        bars_history = bars_df.iloc[max(0, i - HISTORY_BARS + 1):i + 1]

        # Drive the strategy.
        trade = on_new_1m_bar(
            state=state, lucid=lucid,
            bars_setup=bars_history, last_1m_bar=last_1m_bar,
            now=now, n_mnq=N_MNQ, bars_trend=bars_history, params=params,
        )
        if trade is not None:
            # Bot returned a closed trade. Apply Lucid bookkeeping like the
            # LucidAccount._close override would: add the realized pnl to
            # today_pnl. Subtract commission too (paper_account net of comm).
            pnl_usd = float(trade["pnl_usd"])
            pnl_after_comm = pnl_usd - COMM_RT * N_MNQ
            lucid.today_pnl += pnl_after_comm
            trades.append({
                "entry_ts": trade["entry_ts"],
                "exit_ts":  trade["exit_ts"],
                "side":     trade["side"],
                "entry_px": trade["entry_px"],
                "exit_px":  trade["exit_px"],
                "stop_px":  trade["stop_px"],
                "target_px": trade["target_px"],
                "exit_reason": trade["exit_reason"],
                "hold_s":   trade["hold_s"],
                "pnl_usd":  round(pnl_after_comm, 2),
            })

        if (i - start_bar) % progress_every == 0:
            pct = 100 * (i - start_bar) / max(1, n - start_bar - 1)
            print(f"    progress {pct:5.1f}%  bar {now}  trades_so_far={len(trades)}  cum=${sum(t['pnl_usd'] for t in trades):+,.0f}",
                  flush=True)

    return trades


def summarize(trades, label):
    if not trades:
        print(f"\n  {label}: 0 trades")
        return
    n = len(trades)
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    total = sum(t["pnl_usd"] for t in trades)
    wr = 100 * len(wins) / n
    avg_w = np.mean([t["pnl_usd"] for t in wins]) if wins else 0
    avg_l = np.mean([t["pnl_usd"] for t in losses]) if losses else 0
    rr = -avg_w / avg_l if avg_l else 0
    expectancy = total / n
    eq = np.cumsum([t["pnl_usd"] for t in trades])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq).max()
    span = (trades[-1]["entry_ts"] - trades[0]["entry_ts"]).total_seconds()
    months = span / (30.44 * 86400)
    monthly = (total / STARTING_BALANCE) * 100 / months if months > 0 else 0
    daily = defaultdict(float)
    for t in trades:
        daily[t["exit_ts"].date()] += t["pnl_usd"]
    worst_day = min(daily.values()) if daily else 0
    n_dll = sum(1 for v in daily.values() if v <= -1200)
    # fast stops
    fast_stops = sum(1 for t in trades if t["exit_reason"] == "stop" and t["hold_s"] <= 10)
    all_stops = sum(1 for t in trades if t["exit_reason"] == "stop")
    print(f"\n  === {label} ===")
    print(f"  Trades:        {n:,}")
    print(f"  Win rate:      {wr:.1f}%")
    print(f"  Realized RR:   {rr:.2f}")
    print(f"  Expectancy:    ${expectancy:+.2f}/trade")
    print(f"  Total P&L:     ${total:+,.0f}")
    print(f"  Months:        {months:.1f}")
    print(f"  Monthly ret:   {monthly:+.2f}%")
    print(f"  Max DD:        ${dd:,.0f}")
    print(f"  Worst day:     ${worst_day:+,.0f}")
    print(f"  DLL breaches:  {n_dll}")
    if all_stops > 0:
        print(f"  Fast stops:    {fast_stops}/{all_stops} = {100*fast_stops/all_stops:.1f}%")


def main():
    print("Loading 1-min Polygon NQ data...")
    df = pd.read_csv(CSV, parse_dates=["ts"], index_col="ts").sort_index()
    df = df[(df["high"] >= df["low"])]
    print(f"  {len(df):,} bars over {(df.index.max()-df.index.min()).days} days")

    # Test 1: last 6 months (most relevant to current regime)
    cutoff = df.index.max() - timedelta(days=180)
    last6m = df[df.index >= cutoff]
    trades = run_replay(last6m, label="LAST 6 MONTHS (bot's actual code)")
    summarize(trades, "LAST 6 MONTHS")

    # Test 2: last 30 days (closest to the live week regime)
    cutoff = df.index.max() - timedelta(days=30)
    last30 = df[df.index >= cutoff]
    trades = run_replay(last30, label="LAST 30 DAYS")
    summarize(trades, "LAST 30 DAYS")

    # Test 3: last 7 days (proxy for the live week regime)
    cutoff = df.index.max() - timedelta(days=7)
    last7 = df[df.index >= cutoff]
    trades = run_replay(last7, label="LAST 7 DAYS")
    summarize(trades, "LAST 7 DAYS")


if __name__ == "__main__":
    main()

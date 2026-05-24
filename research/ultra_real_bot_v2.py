"""ULTRA-REAL bot simulation — VECTORIZED for speed.

Uses the EXACT bot logic for setup detection (detect_pullback_setup from
bot/pullback_strategy.py) and replicates the should_exit rule:
  - stops fire immediately
  - targets require hold >= MIN_TARGET_HOLD_SECONDS (10s)
  - 10-min timeout

But vectorizes the tick walk for performance (no Python loop per tick).
Same numbers as the slow tick-by-tick sim, just 100x faster.
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
    DEFAULT_SIZE, MIN_TARGET_HOLD_SECONDS, COOLDOWN_SECS,
    MAX_HOLD_SECS, MAX_WAIT_SECS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 1.0
LATENCY_MS = 200


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def main():
    t0 = time.time()
    print(f"DEFAULT_SIZE: {DEFAULT_SIZE} MNQ (from bot/pullback_strategy.py)")
    print(f"MIN_TARGET_HOLD_SECONDS: {MIN_TARGET_HOLD_SECONDS}s (targets only)")
    print(f"COOLDOWN_SECS: {COOLDOWN_SECS}s")
    print(f"MAX_HOLD_SECS: {MAX_HOLD_SECS}s")
    print(f"MAX_WAIT_SECS: {MAX_WAIT_SECS}s")
    print()

    print("Loading...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    print(f"  {len(price):,} ticks, {len(bars_1m):,} bars  ({time.time()-t0:.0f}s)\n")

    # ========================================================================
    # Simulate: scan each bar, detect setup, simulate trade outcome
    # ========================================================================
    cooldown_ns = COOLDOWN_SECS * 1_000_000_000
    latency_ns = LATENCY_MS * 1_000_000
    max_hold_ns = MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = MIN_TARGET_HOLD_SECONDS * 1_000_000_000

    trades = []
    used_keys = set()
    last_exit_ts = -1

    n_bars = len(bars_1m)
    print(f"Scanning {n_bars} bars for setups...")
    for i in range(3, n_bars - 1):   # need at least 3 prior bars for impulse
        # Signal fires at bar i+1 START (i.e., bar i CLOSE)
        sig_ts = int(bar_ts[i + 1])
        bars_at_i = bars_1m.iloc[:i + 1]

        setup = detect_pullback_setup(bars_at_i, pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
        if setup is None: continue
        key = _setup_key(setup)
        if key in used_keys: continue

        # Cooldown check
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cooldown_ns:
            continue

        side = 1 if setup.side == "LONG" else -1
        entry_price = float(setup.pullback_entry)
        stop_px = float(setup.stop_px_val)
        target_px = float(setup.target_px_val)

        # ---- LIMIT FILL: walk ticks until price reaches entry_price ----
        # Latency-adjusted earliest possible fill time
        earliest_fill_ts = sig_ts + latency_ns
        expire_ts = sig_ts + max_wait_ns

        fill_start_idx = int(np.searchsorted(ts_ns, earliest_fill_ts, side="left"))
        fill_end_idx = int(np.searchsorted(ts_ns, expire_ts, side="left"))
        if fill_start_idx >= fill_end_idx: continue

        scan_fill = price[fill_start_idx:fill_end_idx]
        if side == 1:
            fill_hits = scan_fill <= entry_price
        else:
            fill_hits = scan_fill >= entry_price
        if not fill_hits.any(): continue

        fill_offset = int(np.argmax(fill_hits))
        entry_idx = fill_start_idx + fill_offset
        entry_ts = int(ts_ns[entry_idx])

        # ---- TRADE MANAGEMENT: vectorized exit detection ----
        timeout_ts = entry_ts + max_hold_ns
        # 10s min-hold timestamp for target exits
        min_target_ts = entry_ts + min_hold_ns

        exit_search_end_idx = min(
            int(np.searchsorted(ts_ns, timeout_ts, side="left")),
            len(price) - 1
        )
        if exit_search_end_idx <= entry_idx:
            continue

        scan_prices = price[entry_idx + 1:exit_search_end_idx + 1]
        scan_ts = ts_ns[entry_idx + 1:exit_search_end_idx + 1]

        # Stop hits (fire immediately, any hold time)
        if side == 1:
            stop_mask = scan_prices <= stop_px
            tgt_mask = scan_prices >= target_px
        else:
            stop_mask = scan_prices >= stop_px
            tgt_mask = scan_prices <= target_px

        # Stop earliest tick index
        if stop_mask.any():
            stop_idx = int(np.argmax(stop_mask))
        else:
            stop_idx = len(scan_prices)

        # Target earliest tick that's also past min_target_ts
        if tgt_mask.any():
            tgt_candidates = np.where(tgt_mask & (scan_ts >= min_target_ts))[0]
            tgt_idx = int(tgt_candidates[0]) if len(tgt_candidates) > 0 else len(scan_prices)
        else:
            tgt_idx = len(scan_prices)

        # Take earliest exit
        if stop_idx == len(scan_prices) and tgt_idx == len(scan_prices):
            # Timeout
            exit_px = float(scan_prices[-1])
            exit_ts = int(scan_ts[-1])
            exit_reason = "timeout"
        elif stop_idx <= tgt_idx:
            exit_px = stop_px
            exit_ts = int(scan_ts[stop_idx])
            exit_reason = "stop"
        else:
            exit_px = target_px
            exit_ts = int(scan_ts[tgt_idx])
            exit_reason = "target"

        # P&L
        n_mnq = DEFAULT_SIZE
        if side == 1:
            pnl_pts = exit_px - entry_price
        else:
            pnl_pts = entry_price - exit_px
        pnl_usd = pnl_pts * n_mnq * MNQ_PER_PT - COMM_PER_CONTRACT_RT * n_mnq
        hold_s = (exit_ts - entry_ts) / 1e9

        trades.append({
            "side": setup.side, "n_mnq": n_mnq,
            "entry_ts": entry_ts, "exit_ts": exit_ts,
            "entry_px": entry_price, "exit_px": exit_px,
            "stop_px": stop_px, "target_px": target_px,
            "hold_s": hold_s, "exit_reason": exit_reason,
            "pnl_usd": float(pnl_usd),
        })
        used_keys.add(key)
        last_exit_ts = exit_ts

        if len(trades) % 1000 == 0:
            print(f"  [trades={len(trades)}  bar={i}/{n_bars}  "
                  f"elapsed={time.time()-t0:.0f}s]")

    print(f"\nTotal trades: {len(trades)}  elapsed: {time.time()-t0:.0f}s\n")

    if not trades:
        print("No trades."); return

    # ========================================================================
    # Stats
    # ========================================================================
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    pnls = tdf["pnl_usd"].to_numpy()
    wins = int((pnls > 0).sum())
    gw = float(pnls[pnls > 0].sum())
    gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if wins < n else 0
    rr = abs(avg_w/avg_l) if avg_l != 0 else 0
    streak = max_streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    months = period_days / 30.44

    print("=" * 100)
    print("ULTRA-REAL BOT-CODE SIMULATION (using bot/pullback_strategy.py)")
    print("=" * 100)
    print(f"Period:           {period_days:.0f} days ({months:.2f} months)")
    print(f"Position size:    {DEFAULT_SIZE} MNQ fixed")
    print(f"Commission:       ${COMM_PER_CONTRACT_RT}/contract round trip")
    print(f"Min target hold:  {MIN_TARGET_HOLD_SECONDS}s  (stops fire fast)")
    print(f"Latency:          {LATENCY_MS}ms")
    print()
    print(f"Total trades:     {n}")
    print(f"  per day:        {n/period_days:.1f}")
    print(f"  per week:       {n*5/period_days:.0f}")
    print(f"  per month:      {n/months:.0f}")
    print(f"  per hour (avg): {n/period_days/24:.1f}")
    print()
    print(f"Win rate:         {wins/n*100:.2f}%")
    print(f"Profit factor:    {pf:.2f}")
    print(f"RR (actual):      {rr:.2f}")
    print(f"Avg win:          ${avg_w:+.2f}")
    print(f"Avg loss:         ${avg_l:+.2f}")
    print()
    print(f"Total P&L:        ${pnls.sum():+,.0f}")
    print(f"Return:           {pnls.sum()/STARTING_BALANCE*100:+.2f}%")
    print(f"Return per month: {pnls.sum()/STARTING_BALANCE*100/months:+.2f}%")
    print()
    print(f"Max drawdown:     ${maxdd:+,.0f} ({abs(maxdd/STARTING_BALANCE*100):.2f}%)")
    print(f"Max losing streak: {max_streak}")
    print()

    # By exit reason
    print("BY EXIT REASON:")
    for reason in ["target", "stop", "timeout"]:
        g = tdf[tdf["exit_reason"] == reason]
        if len(g) == 0: continue
        wr_g = int((g["pnl_usd"] > 0).sum()) / len(g) * 100
        print(f"  {reason:<10} n={len(g):>5}  WR={wr_g:>5.1f}%  "
              f"avg=${g['pnl_usd'].mean():+.2f}  total=${g['pnl_usd'].sum():+,.0f}")

    # Hold distribution
    print(f"\nHOLD-TIME DISTRIBUTION:")
    holds = tdf["hold_s"].to_numpy()
    print(f"  <10s:    {(holds < 10).sum():>5}  (all should be stops — 10s rule applies to targets)")
    print(f"  10-30s:  {((holds>=10)&(holds<30)).sum():>5}")
    print(f"  30-60s:  {((holds>=30)&(holds<60)).sum():>5}")
    print(f"  1-5m:    {((holds>=60)&(holds<300)).sum():>5}")
    print(f"  5-10m:   {((holds>=300)&(holds<600)).sum():>5}")
    print(f"  10m+:    {(holds>=600).sum():>5}")

    # Verify no target exits under 10s
    fast_targets = tdf[(tdf["exit_reason"] == "target") & (tdf["hold_s"] < 10)]
    if len(fast_targets) > 0:
        print(f"\n  ⚠️ {len(fast_targets)} TARGET trades closed <10s (RULE VIOLATION)")
    else:
        print(f"\n  ✓ All target exits >= 10s hold (rule enforced correctly)")

    # Microscalp check
    target_trades = tdf[tdf["exit_reason"] == "target"]
    if len(target_trades) > 0:
        target_profit_pos = target_trades[target_trades["pnl_usd"] > 0]["pnl_usd"].sum()
        scalp_profit = target_trades[(target_trades["hold_s"] <= 5) &
                                      (target_trades["pnl_usd"] > 0)]["pnl_usd"].sum()
        ratio = scalp_profit / target_profit_pos * 100 if target_profit_pos > 0 else 0
        print(f"\nLUCID MICROSCALP CHECK:")
        print(f"  Profit from <=5s target trades: ${scalp_profit:+.0f} ({ratio:.1f}% of total target profit)")
        print(f"  Lucid violates at 50%, bot circuit-breaker at 40%")

    # Per-week
    print(f"\nPER-WEEK CONSISTENCY:")
    tdf["entry_ts_dt"] = pd.to_datetime(tdf["entry_ts"], utc=True)
    tdf["week"] = tdf["entry_ts_dt"].dt.to_period("W-MON")
    weekly = tdf.groupby("week").agg(
        trades=("pnl_usd", "size"),
        wins=("pnl_usd", lambda x: (x > 0).sum()),
        pnl=("pnl_usd", "sum"),
    )
    weekly["wr"] = weekly["wins"] / weekly["trades"] * 100
    weekly["ret%"] = weekly["pnl"] / STARTING_BALANCE * 100
    print(f"  {'Week':<22} {'n':>5} {'WR':>6} {'P&L':>10} {'Ret%':>7}")
    for w, r in weekly.iterrows():
        print(f"  {str(w):<22} {int(r['trades']):>5} {r['wr']:>5.1f}% "
              f"${r['pnl']:>+8,.0f} {r['ret%']:>+6.2f}%")
    pos_wks = (weekly['pnl'] > 0).sum()
    print(f"\n  {pos_wks}/{len(weekly)} weeks profitable ({pos_wks/len(weekly)*100:.0f}%)")

    # Spec
    print("\nSPEC CHECK:")
    rpm = pnls.sum() / STARTING_BALANCE * 100 / months
    dd_pct = abs(maxdd / STARTING_BALANCE * 100)
    specs = [
        ("WR >= 55%", wins/n*100 >= 55, f"{wins/n*100:.1f}%"),
        ("RR >= 1.2", rr >= 1.2, f"{rr:.2f}"),
        ("Trades >= 100/mo", n/months >= 100, f"{n/months:.0f}/mo"),
        ("Return >= 3%/mo", rpm >= 3, f"{rpm:+.2f}%/mo"),
        ("Max DD <= 2%", dd_pct <= 2, f"{dd_pct:.2f}%"),
    ]
    print()
    for spec, passed, val in specs:
        mark = "✅" if passed else "❌"
        print(f"  {mark} {spec:<22} → {val}")
    if all(p for _, p, _ in specs):
        print("\n  ★★★★ ALL SPECS HIT ★★★★")


if __name__ == "__main__":
    main()

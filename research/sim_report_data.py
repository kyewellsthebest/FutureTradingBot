"""Run the ultra-real bot simulation and dump trades to JSON for the
HTML report. Also produces daily P&L breakdown for the animation."""
from __future__ import annotations
import json
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
    IMPULSE_PTS, IMPULSE_WINDOW_BARS, PULLBACK_PCT,
    STOP_PTS, TARGET_PTS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT_JSON = Path("/home/user/HFTBot/dashboard/static/sim_report.json")

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
    print("Loading tick data...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    print(f"  {len(price):,} ticks, {len(bars_1m):,} bars ({time.time()-t0:.0f}s)\n")

    # Simulate
    cooldown_ns = COOLDOWN_SECS * 1_000_000_000
    latency_ns = LATENCY_MS * 1_000_000
    max_hold_ns = MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = MIN_TARGET_HOLD_SECONDS * 1_000_000_000

    trades = []
    used_keys = set()
    last_exit_ts = -1
    n_bars = len(bars_1m)

    print(f"Simulating {n_bars} 1-min bars...")
    for i in range(3, n_bars - 1):
        sig_ts = int(bar_ts[i + 1])
        bars_at_i = bars_1m.iloc[:i + 1]
        setup = detect_pullback_setup(bars_at_i, pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
        if setup is None: continue
        key = _setup_key(setup)
        if key in used_keys: continue
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cooldown_ns: continue

        side = 1 if setup.side == "LONG" else -1
        entry_price = float(setup.pullback_entry)
        stop_px = float(setup.stop_px_val)
        target_px = float(setup.target_px_val)

        # Find limit fill
        earliest_fill_ts = sig_ts + latency_ns
        expire_ts = sig_ts + max_wait_ns
        fill_start = int(np.searchsorted(ts_ns, earliest_fill_ts, side="left"))
        fill_end = int(np.searchsorted(ts_ns, expire_ts, side="left"))
        if fill_start >= fill_end: continue

        scan_fill = price[fill_start:fill_end]
        if side == 1: fill_hits = scan_fill <= entry_price
        else: fill_hits = scan_fill >= entry_price
        if not fill_hits.any(): continue
        entry_idx = fill_start + int(np.argmax(fill_hits))
        entry_ts = int(ts_ns[entry_idx])

        # Exit detection
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
            exit_px = float(scan_p[-1]); exit_ts = int(scan_t[-1]); reason = "timeout"
        elif stop_idx <= tgt_idx:
            exit_px = stop_px; exit_ts = int(scan_t[stop_idx]); reason = "stop"
        else:
            exit_px = target_px; exit_ts = int(scan_t[tgt_idx]); reason = "target"

        pnl_pts = (exit_px - entry_price) if side == 1 else (entry_price - exit_px)
        pnl_usd = pnl_pts * DEFAULT_SIZE * MNQ_PER_PT - COMM_PER_CONTRACT_RT * DEFAULT_SIZE
        hold_s = (exit_ts - entry_ts) / 1e9

        trades.append({
            "side": setup.side,
            "size": DEFAULT_SIZE,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "entry_px": round(float(entry_price), 2),
            "exit_px": round(float(exit_px), 2),
            "stop_px": round(float(stop_px), 2),
            "target_px": round(float(target_px), 2),
            "hold_s": round(hold_s, 2),
            "exit_reason": reason,
            "pnl_pts": round(float(pnl_pts), 2),
            "pnl_usd": round(float(pnl_usd), 2),
        })
        used_keys.add(key)
        last_exit_ts = exit_ts

        if len(trades) % 1000 == 0:
            print(f"  {len(trades)} trades  bar {i}/{n_bars}  {time.time()-t0:.0f}s")

    print(f"\nSimulation done: {len(trades)} trades in {time.time()-t0:.0f}s\n")

    # ========================================================================
    # Aggregate stats for the HTML report
    # ========================================================================
    tdf = pd.DataFrame(trades)
    tdf["entry_dt"] = pd.to_datetime(tdf["entry_ts"], utc=True)
    tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True)
    tdf["date"] = tdf["entry_dt"].dt.tz_convert("America/New_York").dt.date
    tdf["week"] = tdf["entry_dt"].dt.to_period("W-MON").astype(str)

    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    losses = int((tdf["pnl_usd"] < 0).sum())
    scratches = int((tdf["pnl_usd"] == 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    pnls = tdf["pnl_usd"].to_numpy()
    cum = pnls.cumsum()
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    maxdd = float(dd.min())
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if losses else 0
    rr = abs(avg_w/avg_l) if avg_l != 0 else 0
    max_streak = streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    months = period_days / 30.44

    # Per-day breakdown for animation
    daily = tdf.groupby("date").agg(
        trades=("pnl_usd", "size"),
        wins=("pnl_usd", lambda x: int((x > 0).sum())),
        pnl=("pnl_usd", "sum"),
    ).reset_index()
    daily["date_str"] = daily["date"].astype(str)
    daily["cum_pnl"] = daily["pnl"].cumsum()
    daily_records = daily[["date_str", "trades", "wins", "pnl", "cum_pnl"]].to_dict(orient="records")

    # Per-week summary
    weekly = tdf.groupby("week").agg(
        trades=("pnl_usd", "size"),
        wins=("pnl_usd", lambda x: int((x > 0).sum())),
        pnl=("pnl_usd", "sum"),
    ).reset_index()
    weekly["wr"] = weekly["wins"] / weekly["trades"] * 100
    weekly_records = weekly.to_dict(orient="records")

    # Hold-time histogram bins
    holds = tdf["hold_s"].to_numpy()
    hold_bins = [
        ("<10s", int((holds < 10).sum())),
        ("10-30s", int(((holds >= 10) & (holds < 30)).sum())),
        ("30-60s", int(((holds >= 30) & (holds < 60)).sum())),
        ("1-5m", int(((holds >= 60) & (holds < 300)).sum())),
        ("5-10m", int(((holds >= 300) & (holds < 600)).sum())),
        ("10m+", int((holds >= 600).sum())),
    ]

    # Win/loss distribution bins
    wl_bins_data = []
    for label, lo, hi in [
        ("≤-15$", -1e9, -15),
        ("-15 to -10$", -15, -10),
        ("-10 to -5$", -10, -5),
        ("-5 to 0$", -5, 0),
        ("0 to 5$", 0, 5),
        ("5 to 10$", 5, 10),
        ("10 to 15$", 10, 15),
        ("15 to 20$", 15, 20),
        (">20$", 20, 1e9),
    ]:
        wl_bins_data.append({
            "label": label,
            "count": int(((pnls >= lo) & (pnls < hi)).sum()),
        })

    # Trade-by-trade for table (cap to ~all but trimmed)
    trade_rows = []
    for r in trades:
        trade_rows.append({
            "entry_ts": r["entry_ts"],
            "side": r["side"], "entry_px": r["entry_px"], "exit_px": r["exit_px"],
            "stop_px": r["stop_px"], "target_px": r["target_px"],
            "hold_s": r["hold_s"], "exit_reason": r["exit_reason"],
            "pnl_usd": r["pnl_usd"],
        })

    # Equity curve points (one per trade for smooth chart)
    equity_curve = []
    bal = STARTING_BALANCE
    for r in trades:
        bal += r["pnl_usd"]
        equity_curve.append({
            "ts": r["exit_ts"],
            "balance": round(bal, 2),
        })

    # By exit reason breakdown
    by_exit = {}
    for reason in ["target", "stop", "timeout"]:
        g = tdf[tdf["exit_reason"] == reason]
        if len(g) == 0: continue
        by_exit[reason] = {
            "count": int(len(g)),
            "wr": float((g["pnl_usd"] > 0).mean() * 100),
            "avg": float(g["pnl_usd"].mean()),
            "total": float(g["pnl_usd"].sum()),
        }

    out = {
        "meta": {
            "period_start": str(tdf["entry_dt"].min()),
            "period_end": str(tdf["exit_dt"].max()),
            "period_days": round(period_days, 1),
            "period_months": round(months, 2),
            "starting_balance": STARTING_BALANCE,
            "strategy": "Pullback Impulse",
            "default_size": DEFAULT_SIZE,
            "impulse_pts": IMPULSE_PTS,
            "impulse_window_bars": IMPULSE_WINDOW_BARS,
            "pullback_pct": PULLBACK_PCT,
            "stop_pts": STOP_PTS,
            "target_pts": TARGET_PTS,
            "max_hold_secs": MAX_HOLD_SECS,
            "min_target_hold_secs": MIN_TARGET_HOLD_SECONDS,
            "cooldown_secs": COOLDOWN_SECS,
            "comm_per_contract": COMM_PER_CONTRACT_RT,
            "latency_ms": LATENCY_MS,
        },
        "summary": {
            "n_trades": n,
            "wins": wins, "losses": losses, "scratches": scratches,
            "wr_pct": round(wins/n*100, 2),
            "pf": round(pf, 3) if pf < 99 else None,
            "rr": round(rr, 2),
            "avg_win": round(avg_w, 2),
            "avg_loss": round(avg_l, 2),
            "total_pnl": round(float(pnls.sum()), 2),
            "return_pct": round(float(pnls.sum()/STARTING_BALANCE*100), 2),
            "return_pct_per_mo": round(float(pnls.sum()/STARTING_BALANCE*100/months), 2),
            "max_dd_usd": round(maxdd, 2),
            "max_dd_pct": round(abs(maxdd/STARTING_BALANCE*100), 2),
            "max_losing_streak": int(max_streak),
            "trades_per_day": round(n/period_days, 1),
            "trades_per_week": round(n*5/period_days, 1),
            "trades_per_month": round(n/months, 1),
        },
        "by_exit": by_exit,
        "hold_distribution": [{"bin": l, "count": c} for l, c in hold_bins],
        "winloss_distribution": wl_bins_data,
        "daily": daily_records,
        "weekly": weekly_records,
        "equity_curve": equity_curve,
        "trades": trade_rows,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, default=str))
    size_mb = OUT_JSON.stat().st_size / 1e6
    print(f"Wrote {OUT_JSON}  ({size_mb:.2f} MB)")
    print(f"  trades: {n}  daily rows: {len(daily_records)}  weekly: {len(weekly_records)}")
    print(f"  equity points: {len(equity_curve)}")
    print(f"\nSummary:")
    print(f"  Total P&L: ${out['summary']['total_pnl']:+,.0f}  ({out['summary']['return_pct_per_mo']:+.2f}%/mo)")
    print(f"  WR: {out['summary']['wr_pct']:.1f}%  PF: {out['summary']['pf']}  RR: {out['summary']['rr']}")
    print(f"  Max DD: ${out['summary']['max_dd_usd']:+.0f}  ({out['summary']['max_dd_pct']:.2f}%)")


if __name__ == "__main__":
    main()

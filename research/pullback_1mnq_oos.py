"""OOS validation of best 1 MNQ pullback config.

Strategy: pullback_impulse (impulse=5, window=3, pullback=0.618,
                            stop=6, target=10, 1 MNQ fixed)

Train: first 2/3 of data (~53 days, Dec 10 - early Feb)
Test:  last 1/3 of data (~26 days, early Feb - Feb 27)

This validates the +10.26%/mo IS result is not curve-fit to the period.
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, "/home/user/HFTBot")
from research.strategies_1mnq import (
    build_bars, strategy_pullback_1mnq, summarize, hits_spec, STARTING_BALANCE,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

# Best config
CONFIG = {
    "impulse_pts": 5.0,
    "window_bars": 3,
    "pullback_pct": 0.618,
    "stop_pts": 6.0,
    "target_pts": 10.0,
    "max_hold_secs": 600,
    "cooldown_secs": 60,
    "max_wait_secs": 300,
}


def equity_curve_stats(pnls, label):
    cum = np.cumsum(pnls)
    # find longest drawdown duration
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    print(f"\n  {label} EQUITY-CURVE PROFILE:")
    print(f"    Trades: {len(pnls)}")
    print(f"    Winning trades: {(pnls > 0).sum()}")
    print(f"    Losing trades: {(pnls < 0).sum()}")
    print(f"    Largest single win: ${pnls.max():+,.0f}")
    print(f"    Largest single loss: ${pnls.min():+,.0f}")
    # Top 10% of trades
    sorted_desc = np.sort(pnls)[::-1]
    n_top10 = max(1, int(len(pnls) * 0.1))
    top10_sum = sorted_desc[:n_top10].sum()
    total = pnls.sum()
    print(f"    Top 10% of trades contribute: ${top10_sum:+,.0f} "
          f"({top10_sum/total*100 if total else 0:.1f}% of total)")


def main():
    t0 = time.time()
    print("Loading...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    print(f"  {len(price):,} ticks, {period_days:.0f} days  ({time.time()-t0:.0f}s)")

    bars_1m = build_bars(price, ts_ns, volume, aggressor, "1min")
    print(f"  {len(bars_1m):,} 1-min bars  ({time.time()-t0:.0f}s)\n")

    # ==== FULL PERIOD baseline ====
    print("=" * 100)
    print("FULL PERIOD BASELINE")
    print("=" * 100)
    full_trades = strategy_pullback_1mnq(bars_1m, price, ts_ns, **CONFIG)
    s_full = summarize(full_trades, period_days)
    if s_full:
        flag = " ★★★★ HITS SPEC!" if hits_spec(s_full) else ""
        print(f"  n={s_full['n']}, {s_full['trades_per_mo']:.0f}/mo, "
              f"{s_full['trades_per_day']:.1f}/day")
        print(f"  WR={s_full['wr']*100:.2f}%  PF={s_full['pf']:.2f}  "
              f"RR={s_full['rr']:.2f}")
        print(f"  Total=${s_full['total']:+,.0f}  $/tr=${s_full['per']:+.2f}")
        print(f"  Max DD=${s_full['maxdd']:+,.0f} ({abs(s_full['maxdd_pct']):.2f}%)")
        print(f"  Max losing streak: {s_full['max_streak']}")
        print(f"  RETURN: {s_full['ret_per_mo']:+.2f}%/mo{flag}")

    # ==== 2-WAY SPLIT ====
    print("\n" + "=" * 100)
    print("TRAIN / TEST SPLIT (2/3 vs 1/3)")
    print("=" * 100)
    split_idx = int(len(ts_ns) * 0.667)
    split_ts = ts_ns[split_idx]
    in_mask = ts_ns < split_ts
    out_mask = ~in_mask

    in_days = (pd.Timestamp(ts_ns[in_mask][-1]) - pd.Timestamp(ts_ns[in_mask][0])).total_seconds() / 86400
    out_days = (pd.Timestamp(ts_ns[out_mask][-1]) - pd.Timestamp(ts_ns[out_mask][0])).total_seconds() / 86400
    in_bars = bars_1m[bars_1m.index < pd.Timestamp(split_ts, tz="UTC")]
    out_bars = bars_1m[bars_1m.index >= pd.Timestamp(split_ts, tz="UTC")]

    print(f"  Split @ {pd.Timestamp(split_ts).date()}  "
          f"IS={in_days:.0f}d  OOS={out_days:.0f}d")

    print(f"\n  --- IN-SAMPLE (training period) ---")
    in_trades = strategy_pullback_1mnq(in_bars, price[in_mask], ts_ns[in_mask], **CONFIG)
    s_in = summarize(in_trades, in_days)
    if s_in:
        flag = " ★★★★ HITS SPEC!" if hits_spec(s_in) else ""
        print(f"    n={s_in['n']}  WR={s_in['wr']*100:.2f}%  PF={s_in['pf']:.2f}  "
              f"RR={s_in['rr']:.2f}")
        print(f"    Total=${s_in['total']:+,.0f}  DD={abs(s_in['maxdd_pct']):.2f}%")
        print(f"    Return: {s_in['ret_per_mo']:+.2f}%/mo{flag}")

    print(f"\n  --- OUT-OF-SAMPLE (test period — UNSEEN DATA) ---")
    out_trades = strategy_pullback_1mnq(out_bars, price[out_mask], ts_ns[out_mask], **CONFIG)
    s_out = summarize(out_trades, out_days)
    if s_out:
        flag = " ★★★★ HITS SPEC!" if hits_spec(s_out) else ""
        print(f"    n={s_out['n']}  WR={s_out['wr']*100:.2f}%  PF={s_out['pf']:.2f}  "
              f"RR={s_out['rr']:.2f}")
        print(f"    Total=${s_out['total']:+,.0f}  DD={abs(s_out['maxdd_pct']):.2f}%")
        print(f"    Return: {s_out['ret_per_mo']:+.2f}%/mo{flag}")

    print("\n  --- DELTA (does the edge survive?) ---")
    if s_in and s_out:
        wr_delta = (s_out['wr'] - s_in['wr']) * 100
        pf_ratio = s_out['pf'] / s_in['pf'] if s_in['pf'] > 0 else 0
        ret_ratio = s_out['ret_per_mo'] / s_in['ret_per_mo'] if s_in['ret_per_mo'] > 0 else 0
        print(f"    WR change: {wr_delta:+.1f}pp")
        print(f"    PF ratio (OOS/IS): {pf_ratio:.2f}")
        print(f"    Return ratio (OOS/IS): {ret_ratio:.2f}")

    # ==== Per-week consistency ====
    print("\n" + "=" * 100)
    print("PER-WEEK BREAKDOWN OF FULL PERIOD")
    print("=" * 100)
    if full_trades:
        tdf = pd.DataFrame(full_trades)
        tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"], utc=True)
        tdf["week"] = tdf["entry_ts"].dt.to_period("W-MON")
        weekly = tdf.groupby("week").agg(
            trades=("pnl_usd", "size"),
            wins=("pnl_usd", lambda x: (x > 0).sum()),
            pnl=("pnl_usd", "sum"),
        )
        weekly["wr"] = weekly["wins"] / weekly["trades"] * 100
        weekly["ret_pct"] = weekly["pnl"] / STARTING_BALANCE * 100
        print(f"  {'Week':<22} {'n':>5} {'WR':>6} {'P&L':>10} {'Ret%':>7}")
        for w, r in weekly.iterrows():
            print(f"  {str(w):<22} {int(r['trades']):>5} "
                  f"{r['wr']:>5.1f}% ${r['pnl']:>+8,.0f} {r['ret_pct']:>+6.2f}%")
        wins_weeks = (weekly['pnl'] > 0).sum()
        print(f"\n  {wins_weeks}/{len(weekly)} weeks profitable "
              f"({wins_weeks/len(weekly)*100:.0f}%)")

    # ==== Trade distribution sanity ====
    print("\n" + "=" * 100)
    print("TRADE DISTRIBUTION (looking for lottery-ticket bias)")
    print("=" * 100)
    if full_trades:
        pnls = np.array([t["pnl_usd"] for t in full_trades])
        equity_curve_stats(pnls, "FULL")
        # if top 10% contribute >80% of total, it's lottery
        sorted_desc = np.sort(pnls)[::-1]
        top10_n = max(1, int(len(pnls) * 0.1))
        top10_contrib_pct = sorted_desc[:top10_n].sum() / pnls.sum() * 100 if pnls.sum() else 0
        if top10_contrib_pct > 80:
            print(f"\n  ⚠️ WARNING: Top 10% of trades = {top10_contrib_pct:.0f}% of total")
            print(f"    Strategy is lottery-ticket-dependent.")
        else:
            print(f"\n  ✓ Top 10% contribute {top10_contrib_pct:.0f}% — broadly distributed edge.")


if __name__ == "__main__":
    main()

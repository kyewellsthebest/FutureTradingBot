"""Out-of-sample validation + sanity checks for the pullback strategy.

If the strategy works as backtest claims (+97%/mo, 5.6% DD), it should:
  1. Show similar results on first half (IS) and second half (OOS)
  2. Survive on individual weeks/months separately
  3. Have realistic trade-by-trade equity curve (not one mega-winner)
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, "/home/user/HFTBot")
from research.tick_precise_framework import (
    build_1m_bars, strategy_pullback_impulse, summarize, hits_spec,
    STARTING_BALANCE,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

# THE config we're validating
BEST_CONFIG = {
    "impulse_pts": 5.0,
    "impulse_window_bars": 3,
    "pullback_pct": 0.618,
    "max_wait_secs": 300,
    "init_stop_pts": 4.0,
    "target_pts": 6.0,
    "max_hold_secs": 600,
    "cooldown_secs": 60,
}


def split_data(df, fraction):
    n = len(df)
    cut = int(n * fraction)
    return df.iloc[:cut], df.iloc[cut:]


def slice_arrays(ts_ns, *arrs, mask):
    return [a[mask] for a in arrs]


def main():
    t0 = time.time()
    print("Loading tick data...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    print(f"  {len(df):,} ticks over {period_days:.0f} days")

    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    print(f"  Loaded in {time.time()-t0:.0f}s")

    bars_1m = build_1m_bars(price, ts_ns, volume, aggressor)
    print(f"  Built {len(bars_1m):,} 1-min bars in {time.time()-t0:.0f}s\n")

    # ==== TEST 1: FULL period baseline ====
    print("=" * 100)
    print("TEST 1: FULL PERIOD")
    print("=" * 100)
    trades = strategy_pullback_impulse(price, ts_ns, volume, aggressor,
                                        bars_1m, **BEST_CONFIG)
    s = summarize(trades, period_days)
    if s:
        flag = "★★★★ HITS SPEC!" if hits_spec(s) else ""
        print(f"  n={s['n']} ({s['trades_per_mo']:.0f}/mo, {s['trades_per_day']:.1f}/day)")
        print(f"  WR={s['wr']*100:.1f}% PF={s['pf']:.2f} RR={s['rr']:.2f}")
        print(f"  $/trade=${s['per']:+.2f}  Total=${s['total']:+,.0f}")
        print(f"  Max DD=${s['maxdd']:,.0f} ({abs(s['maxdd_pct']):.1f}%)")
        print(f"  Max losing streak: {s['max_streak']}")
        print(f"  RETURN: {s['ret_per_mo']:+.2f}%/mo  {flag}")
    print()

    # ==== TEST 2: IS / OOS split ====
    print("=" * 100)
    print("TEST 2: IN-SAMPLE (first 60%) vs OUT-OF-SAMPLE (last 40%)")
    print("=" * 100)
    split_idx = int(len(ts_ns) * 0.6)
    split_ts = pd.Timestamp(ts_ns[split_idx])
    in_mask = ts_ns < ts_ns[split_idx]
    out_mask = ~in_mask

    in_days = (pd.Timestamp(ts_ns[in_mask][-1]) - pd.Timestamp(ts_ns[in_mask][0])).total_seconds() / 86400
    out_days = (pd.Timestamp(ts_ns[out_mask][-1]) - pd.Timestamp(ts_ns[out_mask][0])).total_seconds() / 86400
    print(f"  IS: {pd.Timestamp(ts_ns[0]).date()} → {split_ts.date()}  ({in_days:.0f} days)")
    print(f"  OOS: {split_ts.date()} → {pd.Timestamp(ts_ns[-1]).date()}  ({out_days:.0f} days)")

    in_bars = bars_1m[bars_1m.index < split_ts]
    out_bars = bars_1m[bars_1m.index >= split_ts]

    print("\n  Running IS...")
    is_trades = strategy_pullback_impulse(price[in_mask], ts_ns[in_mask],
                                           volume[in_mask], aggressor[in_mask],
                                           in_bars, **BEST_CONFIG)
    is_s = summarize(is_trades, in_days)
    print("  Running OOS...")
    out_trades = strategy_pullback_impulse(price[out_mask], ts_ns[out_mask],
                                            volume[out_mask], aggressor[out_mask],
                                            out_bars, **BEST_CONFIG)
    out_s = summarize(out_trades, out_days)

    for label, s in [("IS", is_s), ("OOS", out_s)]:
        if not s:
            print(f"  {label}: no trades"); continue
        flag = "★★★★ HITS SPEC!" if hits_spec(s) else ""
        print(f"  {label:>4}: n={s['n']} ({s['trades_per_mo']:.0f}/mo) "
              f"WR={s['wr']*100:.1f}% PF={s['pf']:.2f} RR={s['rr']:.2f} "
              f"DD={abs(s['maxdd_pct']):.1f}% → {s['ret_per_mo']:+.2f}%/mo {flag}")
    print()

    # ==== TEST 3: per-week breakdown ====
    print("=" * 100)
    print("TEST 3: PER-WEEK CONSISTENCY (full-period trades broken down)")
    print("=" * 100)
    tdf = pd.DataFrame(trades)
    if len(tdf) > 0:
        tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"], utc=True)
        tdf["week"] = tdf["entry_ts"].dt.to_period("W")
        weekly = tdf.groupby("week").agg(
            trades=("pnl_usd", "size"),
            wins=("pnl_usd", lambda x: (x > 0).sum()),
            pnl=("pnl_usd", "sum"),
        )
        weekly["wr"] = weekly["wins"] / weekly["trades"] * 100
        weekly["ret_pct"] = weekly["pnl"] / STARTING_BALANCE * 100
        print(f"  {'Week':<22} {'Trades':>7} {'Wins':>5} {'WR':>6} {'PnL':>10} {'Ret%':>7}")
        for w, r in weekly.iterrows():
            tag = " WIN" if r['pnl'] > 0 else " LOSS"
            print(f"  {str(w):<22} {int(r['trades']):>7} {int(r['wins']):>5} "
                  f"{r['wr']:>5.1f}% ${r['pnl']:>+8,.0f} {r['ret_pct']:>+6.2f}%{tag}")
        winning_weeks = (weekly['pnl'] > 0).sum()
        print(f"\n  Winning weeks: {winning_weeks}/{len(weekly)} "
              f"({winning_weeks/len(weekly)*100:.0f}%)")
    print()

    # ==== TEST 4: Trade equity curve sanity ====
    print("=" * 100)
    print("TEST 4: EQUITY CURVE PROFILE (looking for one-mega-winner bias)")
    print("=" * 100)
    if len(tdf) > 0:
        pnls = tdf["pnl_usd"].to_numpy()
        cum = pnls.cumsum()
        # Top 10 biggest trades by abs value
        sorted_pnls = sorted(pnls.tolist(), key=lambda x: -abs(x))
        print(f"  Top 10 trades by |P&L|:")
        for i, p in enumerate(sorted_pnls[:10]):
            print(f"    #{i+1}: ${p:+,.0f}")
        # contribution of top 10% trades
        n_top = max(1, int(len(pnls) * 0.10))
        sorted_desc = sorted(pnls.tolist(), reverse=True)
        top10pct_sum = sum(sorted_desc[:n_top])
        total = sum(pnls)
        print(f"\n  Top 10% trades contribute: ${top10pct_sum:+,.0f} "
              f"({top10pct_sum/total*100 if total else 0:.0f}% of total)")
        # if top 10% = >90% of profit, it's a "lottery ticket" strategy
        print(f"  Distribution: avg ${pnls.mean():+.2f}, "
              f"median ${np.median(pnls):+.2f}, "
              f"std ${pnls.std():.2f}")


if __name__ == "__main__":
    main()

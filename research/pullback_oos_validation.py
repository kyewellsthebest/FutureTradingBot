"""Out-of-sample validation + sanity checks for top strategies.

If the strategies work as backtest claims, they should:
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
    build_1m_bars, strategy_pullback_impulse, strategy_momentum_cumdelta,
    summarize, hits_spec, STARTING_BALANCE,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

# Top configs from sweep
PULLBACK_CONFIG = {
    "impulse_pts": 5.0,
    "impulse_window_bars": 3,
    "pullback_pct": 0.618,
    "max_wait_secs": 300,
    "init_stop_pts": 4.0,
    "target_pts": 6.0,
    "max_hold_secs": 600,
    "cooldown_secs": 60,
}

MOMENTUM_CONFIG = {
    "n_bars_required": 2,
    "min_total_move_pts": 6.0,
    "cumdelta_confirm_window_secs": 60,
    "cumdelta_min_thresh": 800,
    "init_stop_pts": 2.0,
    "target_pts": 6.0,
    "max_hold_secs": 900,
    "cooldown_secs": 60,
}


def test_config(label, strat_func, kwargs, price, ts_ns, volume, aggressor,
                bars_1m, signed_vol, period_days):
    """Run a strategy and report stats."""
    print(f"\n--- {label} ---")
    if strat_func == strategy_pullback_impulse:
        trades = strat_func(price, ts_ns, volume, aggressor, bars_1m, **kwargs)
    elif strat_func == strategy_momentum_cumdelta:
        trades = strat_func(bars_1m, price, ts_ns, signed_vol, **kwargs)
    else:
        return None
    s = summarize(trades, period_days)
    if not s:
        print("  No trades")
        return None
    flag = " ★★★★ HITS SPEC!" if hits_spec(s) else ""
    print(f"  n={s['n']} ({s['trades_per_mo']:.0f}/mo, {s['trades_per_day']:.1f}/day)")
    print(f"  WR={s['wr']*100:.1f}% PF={s['pf']:.2f} RR={s['rr']:.2f}")
    print(f"  $/trade=${s['per']:+.2f}  Total=${s['total']:+,.0f}  Streak={s['max_streak']}")
    print(f"  Max DD=${s['maxdd']:,.0f} ({abs(s['maxdd_pct']):.1f}%)")
    print(f"  RETURN: {s['ret_per_mo']:+.2f}%/mo{flag}")
    return trades, s


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
    signed_vol = (volume * aggressor).astype(np.int64)
    bars_1m = build_1m_bars(price, ts_ns, volume, aggressor)
    print(f"  Loaded + {len(bars_1m):,} bars in {time.time()-t0:.0f}s\n")

    # ==== FULL PERIOD ====
    print("=" * 100)
    print("TEST 1: FULL PERIOD")
    print("=" * 100)
    pullback_full = test_config("PULLBACK", strategy_pullback_impulse,
                                  PULLBACK_CONFIG, price, ts_ns, volume,
                                  aggressor, bars_1m, signed_vol, period_days)
    momentum_full = test_config("MOMENTUM+CUMDELTA", strategy_momentum_cumdelta,
                                  MOMENTUM_CONFIG, price, ts_ns, volume,
                                  aggressor, bars_1m, signed_vol, period_days)

    # ==== IS / OOS SPLIT ====
    print("\n" + "=" * 100)
    print("TEST 2: IN-SAMPLE (60%) vs OUT-OF-SAMPLE (40%)")
    print("=" * 100)
    split_idx = int(len(ts_ns) * 0.6)
    split_ts = ts_ns[split_idx]
    in_mask = ts_ns < split_ts
    out_mask = ~in_mask
    in_days = (pd.Timestamp(ts_ns[in_mask][-1]) - pd.Timestamp(ts_ns[in_mask][0])).total_seconds() / 86400
    out_days = (pd.Timestamp(ts_ns[out_mask][-1]) - pd.Timestamp(ts_ns[out_mask][0])).total_seconds() / 86400
    print(f"  Split @ {pd.Timestamp(split_ts).date()}  "
          f"IS={in_days:.0f}d  OOS={out_days:.0f}d")

    in_bars = bars_1m[bars_1m.index < pd.Timestamp(split_ts, tz="UTC")]
    out_bars = bars_1m[bars_1m.index >= pd.Timestamp(split_ts, tz="UTC")]

    for label, mask, bars, pdays in [("IS", in_mask, in_bars, in_days),
                                       ("OOS", out_mask, out_bars, out_days)]:
        print(f"\n  === {label} ===")
        p = price[mask]; tn = ts_ns[mask]; v = volume[mask]; a = aggressor[mask]
        sv = signed_vol[mask]
        for strat_label, sf, kw in [("Pullback", strategy_pullback_impulse, PULLBACK_CONFIG),
                                     ("Momentum+CD", strategy_momentum_cumdelta, MOMENTUM_CONFIG)]:
            try:
                if sf == strategy_pullback_impulse:
                    trades = sf(p, tn, v, a, bars, **kw)
                else:
                    trades = sf(bars, p, tn, sv, **kw)
                s = summarize(trades, pdays)
                if not s:
                    print(f"    {strat_label}: no trades"); continue
                flag = " ★★★★" if hits_spec(s) else ""
                print(f"    {strat_label}: n={s['n']} WR={s['wr']*100:.1f}% "
                      f"PF={s['pf']:.2f} RR={s['rr']:.2f} "
                      f"DD={abs(s['maxdd_pct']):.1f}% "
                      f"→ {s['ret_per_mo']:+.2f}%/mo{flag}")
            except Exception as e:
                print(f"    {strat_label}: ERROR {e}")

    # ==== Weekly consistency for Pullback ====
    if pullback_full:
        trades, _ = pullback_full
        if trades:
            print("\n" + "=" * 100)
            print("TEST 3: PULLBACK WEEKLY CONSISTENCY")
            print("=" * 100)
            tdf = pd.DataFrame(trades)
            tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"], utc=True)
            tdf["week"] = tdf["entry_ts"].dt.to_period("W")
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
            print(f"\n  {wins_weeks}/{len(weekly)} weeks profitable")

    # ==== Top-trade contribution check ====
    if pullback_full:
        trades, _ = pullback_full
        if trades:
            print("\n" + "=" * 100)
            print("TEST 4: PULLBACK - IS THE EDGE FROM A FEW MEGA-TRADES?")
            print("=" * 100)
            pnls = np.array([t["pnl_usd"] for t in trades])
            sorted_desc = np.sort(pnls)[::-1]
            for pct in [1, 5, 10, 25, 50]:
                k = max(1, int(len(pnls) * pct / 100))
                top_k_sum = sorted_desc[:k].sum()
                total = pnls.sum()
                pct_contrib = top_k_sum / total * 100 if total else 0
                print(f"  Top {pct}% of trades ({k:>4} trades): "
                      f"${top_k_sum:>+10,.0f}  ({pct_contrib:.1f}% of total)")


if __name__ == "__main__":
    main()


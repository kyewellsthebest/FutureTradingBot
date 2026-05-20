"""
Donchian breakout momentum strategies simulation on NQ daily.

Two strategies from the user-supplied article, applied to NQ:

  1. 100-day breakout (S&P 500 version in the article)
       LONG  when close > prior 100-day high of close
       EXIT  when close < prior 100-day low of close
       long-only

  2. 25-day breakout (Bitcoin version in the article)
       LONG  when close > prior 25-day high of close
       EXIT  when close < prior 25-day low of close   (Donchian-symmetric;
             the article's literal "sell when close < 25-day high" is a
             likely typo since the close is almost always below that)
       long-only

Both compared to buy-and-hold NQ. Long-only on a market that rose ~265%
over the window — the right test is risk-adjusted (Sharpe/maxDD), not raw
return. Position is decided at day t close and earns day t+1 return —
no look-ahead.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_daily

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIZE = 10
MNQ_PER_PT = 2.0
TRADING_DAYS = 252


def maxdd(eq: pd.Series) -> float:
    return float((eq - eq.cummax()).min())


def donchian_long_only(close: pd.Series, lookback: int) -> pd.Series:
    """Long when close > prior N-day high; exit when close < prior N-day low."""
    hi = close.rolling(lookback).max().shift(1)
    lo = close.rolling(lookback).min().shift(1)
    pos = pd.Series(0.0, index=close.index)
    in_pos = False
    for i in range(len(close)):
        if not in_pos:
            if not np.isnan(hi.iloc[i]) and close.iloc[i] > hi.iloc[i]:
                in_pos = True
        else:
            if not np.isnan(lo.iloc[i]) and close.iloc[i] < lo.iloc[i]:
                in_pos = False
        pos.iloc[i] = 1.0 if in_pos else 0.0
    return pos


def stats(name: str, daily_pnl: pd.Series, pos: pd.Series) -> dict:
    eq = daily_pnl.cumsum()
    total = float(daily_pnl.sum())
    dd = maxdd(eq)
    days_in = int((pos != 0).sum())
    # trades from contiguous nonzero runs
    grp = (pos != pos.shift(1)).cumsum()
    n_trades = 0
    n_wins = 0
    for _, segp in pos.groupby(grp):
        if segp.iloc[0] == 0:
            continue
        seg_pnl = daily_pnl.loc[segp.index].sum()
        n_trades += 1
        if seg_pnl > 0:
            n_wins += 1
    in_mkt = daily_pnl[pos.shift(1) != 0]
    sharpe = (in_mkt.mean() / in_mkt.std() * np.sqrt(TRADING_DAYS)
              if len(in_mkt) > 5 and in_mkt.std() > 0 else 0.0)
    return {"name": name, "total_usd": total, "maxdd_usd": dd,
            "days_in": days_in, "n_trades": n_trades,
            "win_rate": (n_wins / n_trades) if n_trades else 0.0,
            "sharpe": float(sharpe)}


def main() -> None:
    daily = load_daily("nq")
    if daily.index.tz is None:
        daily.index = daily.index.tz_localize("UTC")
    daily = daily.sort_index()
    print("=" * 96)
    print("DONCHIAN MOMENTUM — NQ daily, 8 yrs, 10 MNQ ($20/pt)")
    print("=" * 96)
    print(f"Bars: {len(daily):,}   range: {daily.index[0].date()} -> "
          f"{daily.index[-1].date()}")

    close = daily["close"]
    daily_ret_pts = close.diff()
    long_pnl_per_day = daily_ret_pts * SIZE * MNQ_PER_PT

    # buy & hold benchmark
    bh_pos = pd.Series(1.0, index=daily.index)
    bh_pos.iloc[0] = 0.0
    bh_pnl = bh_pos.shift(1).fillna(0) * long_pnl_per_day
    bh = stats("Buy & Hold NQ", bh_pnl, bh_pos)

    # Donchian 100
    pos100 = donchian_long_only(close, 100)
    pnl100 = pos100.shift(1).fillna(0) * long_pnl_per_day
    s100 = stats("Donchian 100-day breakout", pnl100, pos100)

    # Donchian 25
    pos25 = donchian_long_only(close, 25)
    pnl25 = pos25.shift(1).fillna(0) * long_pnl_per_day
    s25 = stats("Donchian 25-day breakout", pnl25, pos25)

    print(f"\n  {'strategy':<32}{'total':>14}{'maxDD':>14}{'Sharpe':>9}"
          f"{'days in':>10}{'trades':>10}{'win%':>9}")
    print("  " + "-" * 96)
    for r in (bh, s100, s25):
        print(f"  {r['name']:<32}${r['total_usd']:>+12,.0f}"
              f"${r['maxdd_usd']:>+12,.0f}{r['sharpe']:>9.2f}"
              f"{r['days_in']:>10}{r['n_trades']:>10}"
              f"{r['win_rate']*100:>8.0f}%")
    print()
    for r in (s100, s25):
        delta = r["total_usd"] - bh["total_usd"]
        dd_better = r["maxdd_usd"] > bh["maxdd_usd"]   # both negative
        print(f"  {r['name']:<32} vs B&H: "
              f"return {delta:>+,.0f}    "
              f"drawdown {'better' if dd_better else 'worse'} "
              f"({r['maxdd_usd']:+.0f} vs {bh['maxdd_usd']:+.0f})")


if __name__ == "__main__":
    main()

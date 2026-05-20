"""
Mean-reversion + seasonal strategy simulation on NQ daily bars (8 years).

Two strategies extracted from the user-supplied article:

  1. Connors RSI(2) mean-reversion — the article's flagship example
     (originally on QQQ; NQ continuous is the underlying index).
       BUY  at close when RSI(2) closes < 10
       EXIT at close when RSI(2) closes > 70   (10-day max time stop)
       long-only

  2. Halloween effect / 'Sell in May' — the canonical equity-index
     seasonal pattern. The doc's seasonal article focuses on commodity
     spreads (heating oil winter/summer, corn Sept/Dec, soybean), which
     don't apply to NQ. Halloween is the index-applicable version.
       LONG  : Nov 1  through Apr 30
       FLAT  : May 1  through Oct 31
       long-only

Both compared to buy-and-hold NQ. Position is decided at day t's close
and earns day t+1's return (signal.shift(1)) — no look-ahead.
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


def rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    ag = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    al = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def maxdd_usd(eq_usd: pd.Series) -> float:
    return float((eq_usd - eq_usd.cummax()).min())


def stats(name: str, daily_pnl: pd.Series, pos: pd.Series) -> dict:
    eq = daily_pnl.cumsum()
    total = float(daily_pnl.sum())
    dd = maxdd_usd(eq)
    days_in = int((pos != 0).sum())
    # build a trade list — each contiguous nonzero-pos run is a trade
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
    wr = n_wins / n_trades if n_trades else 0.0
    # Sharpe (simple, daily)
    ret_in_pos = daily_pnl[pos.shift(1) != 0]
    sharpe = (ret_in_pos.mean() / ret_in_pos.std() * np.sqrt(TRADING_DAYS)
              if len(ret_in_pos) > 5 and ret_in_pos.std() > 0 else 0.0)
    return {
        "name": name, "total_usd": total, "maxdd_usd": dd,
        "days_in": days_in, "n_trades": n_trades,
        "win_rate": wr, "sharpe": float(sharpe),
    }


def main() -> None:
    daily = load_daily("nq")
    if daily.index.tz is None:
        daily.index = daily.index.tz_localize("UTC")
    daily = daily.sort_index()

    print("=" * 96)
    print("MEAN REVERSION + SEASONAL — NQ daily, 8 yrs, 10 MNQ ($20/pt)")
    print("=" * 96)
    print(f"Bars: {len(daily):,}   range: {daily.index[0].date()} -> "
          f"{daily.index[-1].date()}")

    close = daily["close"]
    daily_ret_pts = close.diff()
    long_pnl_per_day = daily_ret_pts * SIZE * MNQ_PER_PT      # $ if held long 1 day

    # ------ Buy & Hold benchmark ------
    bh_pos = pd.Series(1.0, index=daily.index)
    bh_pos.iloc[0] = 0.0
    bh_pnl = bh_pos.shift(1).fillna(0) * long_pnl_per_day
    bh = stats("Buy & Hold NQ", bh_pnl, bh_pos)

    # ------ Strategy 1: Connors RSI(2) ------
    rsi2 = rsi(close, 2)
    pos1 = pd.Series(0.0, index=daily.index)
    in_pos = False
    days_held = 0
    entries = 0
    for i in range(len(daily)):
        if not in_pos:
            if not np.isnan(rsi2.iloc[i]) and rsi2.iloc[i] < 10:
                in_pos = True
                days_held = 0
                entries += 1
        else:
            days_held += 1
            if rsi2.iloc[i] > 70 or days_held >= 10:
                in_pos = False
        pos1.iloc[i] = 1.0 if in_pos else 0.0
    pnl1 = pos1.shift(1).fillna(0) * long_pnl_per_day
    s1 = stats("Connors RSI(2)", pnl1, pos1)

    # ------ Strategy 2: Halloween effect ------
    months = daily.index.month
    pos2 = pd.Series(((months >= 11) | (months <= 4)).astype(float),
                     index=daily.index)
    pnl2 = pos2.shift(1).fillna(0) * long_pnl_per_day
    s2 = stats("Halloween effect", pnl2, pos2)

    # ------ Report ------
    print(f"\n  {'strategy':<22}{'total':>14}{'maxDD':>14}{'Sharpe':>9}"
          f"{'days in':>10}{'trades':>10}{'win%':>9}")
    print("  " + "-" * 88)
    for r in (bh, s1, s2):
        print(f"  {r['name']:<22}${r['total_usd']:>+12,.0f}"
              f"${r['maxdd_usd']:>+12,.0f}{r['sharpe']:>9.2f}"
              f"{r['days_in']:>10}{r['n_trades']:>10}"
              f"{r['win_rate']*100:>8.0f}%")
    print()
    for r in (s1, s2):
        delta = r["total_usd"] - bh["total_usd"]
        dd_better = r["maxdd_usd"] > bh["maxdd_usd"]   # dd values are negative
        print(f"  {r['name']:<22} vs B&H: "
              f"return {'+' if delta>0 else ''}{delta:>+,.0f}    "
              f"drawdown {'better' if dd_better else 'worse'}")


if __name__ == "__main__":
    main()

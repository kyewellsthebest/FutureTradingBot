"""
Live-simulation test of strategies extracted from 4 external GitHub repos
the user asked to vet, run on the local 8-year NQ daily history.

  1. pxvr-official/1   — NOT a trading repo (a text document). Nothing to test.
  2. amstrdm/mlm-trend-following — complete strategy: long if close > 200-day
       MA else short, gated by a 1.5% 20-day realised-vol filter, rebalanced
       monthly on the 25th.
  3. bideeen/Building-A-Trading-Strategy-With-Python — complete (educational)
       strategy: 40/100-day SMA crossover, long-only.
  4. sweller226/flint — ICT/volume DETECTION engines with no entry/exit rules.
       Its one actual decision rule — market-structure bias (price above the
       most recent confirmed swing low = bullish) — is reconstructed and tested.

All run on NQ daily bars vs buy-and-hold NQ. Position is decided on the prior
close and earns the next day's return (signal.shift(1)) — no look-ahead.
Swing pivots use only confirmed, lagged fractals.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_daily

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRADING_DAYS = 252


def metrics(strat_ret: pd.Series, pos: pd.Series) -> dict:
    """Performance of a daily strategy-return series + its position series."""
    r = strat_ret.dropna()
    if len(r) < 30:
        return {}
    eq = (1 + r).cumprod()
    n = len(r)
    cagr = eq.iloc[-1] ** (TRADING_DAYS / n) - 1
    sharpe = (r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    # per-holding-period trades
    p = pos.reindex(r.index).fillna(0)
    grp = (p != p.shift(1)).cumsum()
    trades = []
    for _, seg in r.groupby(grp):
        sp = p.loc[seg.index[0]]
        if sp == 0:
            continue
        trades.append((1 + seg).prod() - 1)
    wins = sum(1 for t in trades if t > 0)
    return {
        "total_return": float(eq.iloc[-1] - 1),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "max_dd": float(dd),
        "exposure": float((p != 0).mean()),
        "n_trades": len(trades),
        "win_rate": (wins / len(trades)) if trades else 0.0,
    }


def confirmed_swing_lows(low: pd.Series, k: int = 5) -> pd.Series:
    """Most recent swing low confirmed as of each bar. A swing low at t is a
    fractal min of [t-k, t+k]; it is only KNOWN at t+k, so it is stamped there
    and forward-filled — strictly no look-ahead."""
    vals = low.to_numpy()
    out = np.full(len(vals), np.nan)
    for t in range(k, len(vals) - k):
        if vals[t] == vals[t - k:t + k + 1].min():
            out[t + k] = vals[t]          # known only k bars later
    return pd.Series(out, index=low.index).ffill()


def sim_mlm(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """200-day MA trend, 1.5% 20-day vol gate, rebalanced monthly on the 25th."""
    close, ret = df["close"], df["close"].pct_change()
    ma200 = close.rolling(200).mean()
    raw_sig = np.where(close > ma200, 1.0, -1.0)
    vol = ret.rolling(20).std()
    raw_sig = pd.Series(np.where(vol > 0.015, raw_sig, 0.0), index=df.index)

    # rebalance only on the first trading day on/after the 25th of each month
    reb = pd.Series(False, index=df.index)
    months = df.index.tz_localize(None).to_period("M")
    for _, idx in pd.Series(df.index, index=df.index).groupby(months):
        cand = idx[idx.dt.day >= 25]
        if len(cand):
            reb.loc[cand.iloc[0]] = True
    sig = raw_sig.where(reb).ffill().fillna(0.0)
    pos = sig.shift(1)
    return pos * ret, pos


def sim_sma_crossover(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """40/100-day SMA crossover, long-only."""
    close, ret = df["close"], df["close"].pct_change()
    sig = (close.rolling(40).mean() > close.rolling(100).mean()).astype(float)
    pos = sig.shift(1)
    return pos * ret, pos


def sim_flint_bias(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Flint's market-structure bias: long while price is above the most
    recent confirmed swing low, flat otherwise."""
    ret = df["close"].pct_change()
    swing_low = confirmed_swing_lows(df["low"], k=5)
    sig = (df["close"] > swing_low).astype(float)
    pos = sig.shift(1)
    return pos * ret, pos


def main() -> None:
    df = load_daily("nq")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    ret = df["close"].pct_change()
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    print("=" * 78)
    print("EXTERNAL-REPO STRATEGY SIMULATION — NQ daily")
    print(f"  data: {df.index[0].date()} -> {df.index[-1].date()}  "
          f"({len(df):,} bars, {yrs:.1f} yrs)")
    print("=" * 78)

    runs = {
        "Buy & Hold NQ": (ret, pd.Series(1.0, index=df.index)),
        "MLM trend (200-MA, vol gate)": sim_mlm(df),
        "SMA 40/100 crossover": sim_sma_crossover(df),
        "Flint ICT structure-bias": sim_flint_bias(df),
    }

    hdr = (f"{'strategy':<32}{'totRet':>10}{'CAGR':>9}{'Sharpe':>9}"
           f"{'maxDD':>9}{'expo':>8}{'trades':>8}{'win%':>7}")
    print(hdr)
    print("-" * 78)
    results = {}
    for name, (sr, pos) in runs.items():
        m = metrics(sr, pos)
        results[name] = m
        if not m:
            print(f"{name:<32}  (insufficient data)")
            continue
        print(f"{name:<32}{m['total_return']*100:>9.0f}%{m['cagr']*100:>8.1f}%"
              f"{m['sharpe']:>9.2f}{m['max_dd']*100:>8.0f}%"
              f"{m['exposure']*100:>7.0f}%{m['n_trades']:>8}"
              f"{m['win_rate']*100:>6.0f}%")
    print("-" * 78)

    bh = results["Buy & Hold NQ"]
    print("\nvs buy-and-hold NQ:")
    for name, m in results.items():
        if name == "Buy & Hold NQ" or not m:
            continue
        beat_ret = "beats" if m["total_return"] > bh["total_return"] else "trails"
        beat_sh = "beats" if m["sharpe"] > bh["sharpe"] else "trails"
        print(f"  {name:<32} return {beat_ret}, Sharpe {beat_sh} "
              f"({m['sharpe']:.2f} vs {bh['sharpe']:.2f})")


if __name__ == "__main__":
    main()

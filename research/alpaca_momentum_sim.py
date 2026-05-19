"""
Live-simulation of the Alpaca momentum strategy (alpacahq/Momentum-Trading-
Example, algo.py) on NQ 5-min bars over 8 years.

Rules taken verbatim from algo.py:
  * Entry window  : 9:45-10:30 ET RTH (15-60 min after open)
  * Day move      : current price > +4% from prior session's RTH close
  * Breakout      : current close > high of first 15 min (9:30/35/40)
  * Momentum      : MACD(12,26) > 0 AND MACD increasing vs prior bar
  * Stop          : 5% below entry (the default_stop)
  * Target        : 3R = entry + 3 * (entry - stop) = entry * 1.15
  * Exit          : stop / target / EOD liquidation
  * Long-only, one trade per session

Honest expectation: the 4% intraday threshold is calibrated for individual
stocks; NQ rarely moves 4% intraday, so very few fires. The script also
reports the largest daily_pct observed so you can see how often the bar even
got close to triggering.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NY = "America/New_York"


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    ny = nq.index.tz_convert(NY)

    # MACD(12,26) computed on the full continuous 5-min series
    c = nq["close"]
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    macd_inc = macd > macd.shift(1)
    macd_pos = macd > 0

    rth_mask = (((ny.hour == 9) & (ny.minute >= 30)) |
                ((ny.hour >= 10) & (ny.hour < 16)))
    rth = nq[rth_mask].copy()
    ny_r = rth.index.tz_convert(NY)
    rth["date"] = pd.DatetimeIndex(ny_r).date
    rth["hour"] = pd.DatetimeIndex(ny_r).hour
    rth["minute"] = pd.DatetimeIndex(ny_r).minute

    last_close = rth.groupby("date")["close"].last()
    first15 = rth[(rth["hour"] == 9) & (rth["minute"].between(30, 40))]
    first15_high = first15.groupby("date")["high"].max()

    # prior session close, in order
    sessions = sorted(last_close.index)
    prev_close = {sessions[i + 1]: float(last_close.iloc[i])
                  for i in range(len(sessions) - 1)}

    trades, max_day_pct = [], 0.0
    n_pass_pct, n_pass_brk, n_pass_macd = 0, 0, 0
    for d in sessions:
        if d not in prev_close or d not in first15_high.index:
            continue
        prev_c = prev_close[d]
        f15 = float(first15_high[d])
        sess = rth[rth["date"] == d]
        in_win = (((sess["hour"] == 9) & (sess["minute"] >= 45)) |
                  ((sess["hour"] == 10) & (sess["minute"] < 30)))
        win_bars = sess[in_win]
        for ts, row in win_bars.iterrows():
            day_pct = (row["close"] - prev_c) / prev_c
            if day_pct > max_day_pct:
                max_day_pct = day_pct
            cond_pct = day_pct > 0.04
            cond_brk = row["close"] > f15
            cond_macd = bool(macd_pos.loc[ts]) and bool(macd_inc.loc[ts])
            n_pass_pct += cond_pct
            n_pass_brk += cond_brk
            n_pass_macd += cond_macd
            if cond_pct and cond_brk and cond_macd:
                pos_in_sess = sess.index.get_loc(ts)
                if pos_in_sess + 1 >= len(sess):
                    break
                entry_ts = sess.index[pos_in_sess + 1]
                entry_px = float(sess.iloc[pos_in_sess + 1]["open"])
                stop = entry_px * 0.95
                target = entry_px + 3.0 * (entry_px - stop)
                exit_px, exit_reason, exit_ts = None, None, None
                for j in range(pos_in_sess + 1, len(sess)):
                    bar = sess.iloc[j]
                    if bar["low"] <= stop:
                        exit_px, exit_reason = stop, "stop"
                        exit_ts = sess.index[j]; break
                    if bar["high"] >= target:
                        exit_px, exit_reason = target, "target"
                        exit_ts = sess.index[j]; break
                if exit_px is None:
                    exit_px = float(sess.iloc[-1]["close"])
                    exit_reason, exit_ts = "eod", sess.index[-1]
                pnl_pts = exit_px - entry_px
                trades.append({
                    "date": str(d), "entry_ts": str(entry_ts),
                    "entry_px": entry_px, "exit_px": exit_px,
                    "exit_reason": exit_reason, "day_pct": round(day_pct, 4),
                    "pnl_points": round(pnl_pts, 2),
                    "pnl_pct": round(pnl_pts / entry_px, 4),
                })
                break  # one trade per session

    print("=" * 78)
    print("Alpaca Momentum (alpacahq/Momentum-Trading-Example) — NQ 5-min, 8 yrs")
    print("=" * 78)
    print(f"sessions evaluated      : {len(sessions):,}")
    print(f"bar-checks in entry win : "
          f"{n_pass_pct + n_pass_brk + n_pass_macd:,} (across all conditions)")
    print(f"  bars passing pct>4%   : {n_pass_pct}")
    print(f"  bars passing breakout : {n_pass_brk}")
    print(f"  bars passing MACD     : {n_pass_macd}")
    print(f"  largest day_pct seen  : {max_day_pct*100:.2f}%   "
          f"(threshold 4.00%)")
    print(f"\ntrades fired            : {len(trades)}")
    if trades:
        tdf = pd.DataFrame(trades)
        wins = (tdf["pnl_points"] > 0).mean()
        print(f"win rate                : {wins*100:.1f}%")
        print(f"avg pnl per trade       : "
              f"{tdf['pnl_points'].mean():.2f} pts ({tdf['pnl_pct'].mean()*100:+.2f}%)")
        print(f"total pnl               : "
              f"{tdf['pnl_points'].sum():.0f} pts "
              f"({tdf['pnl_pct'].sum()*100:+.1f}% summed)")
        print(f"exit mix                : "
              f"{tdf['exit_reason'].value_counts().to_dict()}")
        print("\nfirst 10 trades:")
        print(tdf.head(10).to_string(index=False))
    else:
        print("Strategy NEVER fired in 8 years — the 4% intraday-gain threshold")
        print("is calibrated for individual stocks; NQ as a broad index rarely")
        print("moves 4% intraday, so the entry condition is never met.")


if __name__ == "__main__":
    main()

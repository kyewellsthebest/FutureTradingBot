"""
User-defined top-tick strategy simulation on 8 years of NQ.

Rules — exactly as the user specified:
  * SHORT entry when NQ tags yesterday's high (PDH), BUT only if both:
      - daily bias bearish   (yesterday's daily close < daily EMA20)
      - 4-hour bias bearish  (last CLOSED 4h candle close < 4h EMA20)
  * After PDH is tagged, watch the post-tag high-water mark; trigger entry
    when close drops 20 pts below that HWM.
  * Enter short at the NEXT bar's open (lookahead-safe).
  * Stop  = entry + 20 pts
  * Target = min(PDL, entry - 250)        -- the further of PDL or 250pt
  * Size   = 10 MNQ (=$20 per NQ point)
  * One trade per day; hold up to 48 hours (576 five-min bars).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NY = "America/New_York"
MNQ_PER_PT = 2.0
SIZE = 10
STOP_PTS = 20
TARGET_MIN_PTS = 250
PULLBACK_PTS = 20
MAX_HOLD_BARS = 576           # 48 h of 5-min bars


def daily_bars(nq: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLC by NY calendar day."""
    dates = pd.DatetimeIndex(nq.index.tz_convert(NY)).date
    g = nq.groupby(dates)
    return pd.DataFrame({
        "open":  g["open"].first(),
        "high":  g["high"].max(),
        "low":   g["low"].min(),
        "close": g["close"].last(),
    })


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()

    # ---- daily bias + PDH / PDL ----------------------------------------
    daily = daily_bars(nq)
    daily_ema20 = daily["close"].ewm(span=20, adjust=False).mean()
    bias_bear_today = daily["close"] < daily_ema20
    # bias known AT each day's CLOSE — for next-day decisions use shift(1)
    bias_bear_yesterday = bias_bear_today.shift(1)
    pdh = daily["high"].shift(1)
    pdl = daily["low"].shift(1)

    # map by NY calendar date onto every 5-min bar
    nq = nq.copy()
    nq["ny_date"] = pd.DatetimeIndex(nq.index.tz_convert(NY)).date
    nq["pdh"] = nq["ny_date"].map(pdh.to_dict())
    nq["pdl"] = nq["ny_date"].map(pdl.to_dict())
    nq["daily_bear"] = nq["ny_date"].map(bias_bear_yesterday.to_dict())

    # ---- 4-hour bias (most recent CLOSED 4h candle's close vs EMA20) ----
    bars_4h = nq[["open", "high", "low", "close"]].resample(
        "4h", origin="start_day").agg({"open": "first", "high": "max",
                                       "low": "min", "close": "last"}).dropna()
    h4_ema20 = bars_4h["close"].ewm(span=20, adjust=False).mean()
    h4_bear = bars_4h["close"] < h4_ema20
    # this is only KNOWN at the bar's close = bar_start + 4h
    h4_bear_known = h4_bear.copy()
    h4_bear_known.index = h4_bear_known.index + pd.Timedelta(hours=4)
    nq["h4_bear"] = h4_bear_known.reindex(nq.index, method="ffill")

    # ---- session-by-session walk --------------------------------------
    trades = []
    dates_sorted = sorted(set(nq["ny_date"]))
    nq_arr = nq[["open", "high", "low", "close"]].to_numpy()
    nq_idx = nq.index
    full_n = len(nq)

    for d in dates_sorted:
        day_bars = nq[nq["ny_date"] == d]
        if len(day_bars) == 0:
            continue
        day_pdh = day_bars["pdh"].iloc[0]
        day_pdl = day_bars["pdl"].iloc[0]
        bias_d = day_bars["daily_bear"].iloc[0]
        if (pd.isna(day_pdh) or pd.isna(day_pdl) or pd.isna(bias_d)
                or not bias_d):
            continue
        # walk the day's bars; arm on PDH tag; trigger on 20pt pullback
        armed = False
        hwm = 0.0
        for i in range(len(day_bars) - 1):     # need a next bar to enter on
            row = day_bars.iloc[i]
            if not armed:
                if row["high"] >= day_pdh:
                    armed = True
                    hwm = float(row["high"])
                continue
            hwm = max(hwm, float(row["high"]))
            if pd.isna(row["h4_bear"]) or not row["h4_bear"]:
                continue
            if row["close"] <= hwm - PULLBACK_PTS:
                # enter at NEXT bar's open (lookahead-safe)
                entry_ts = day_bars.index[i + 1]
                entry_px = float(day_bars.iloc[i + 1]["open"])
                stop = entry_px + STOP_PTS
                target = float(min(day_pdl, entry_px - TARGET_MIN_PTS))
                # walk forward up to MAX_HOLD_BARS bars
                start_loc = nq_idx.get_loc(entry_ts)
                end_loc = min(start_loc + MAX_HOLD_BARS, full_n - 1)
                exit_px = None
                exit_reason = "timeout"
                exit_ts = nq_idx[end_loc]
                for j in range(start_loc, end_loc + 1):
                    bar = nq_arr[j]      # open, high, low, close
                    if bar[1] >= stop:
                        exit_px, exit_reason, exit_ts = stop, "stop", nq_idx[j]
                        break
                    if bar[2] <= target:
                        exit_px, exit_reason, exit_ts = target, "target", nq_idx[j]
                        break
                if exit_px is None:
                    exit_px = float(nq_arr[end_loc, 3])
                pnl_pts = entry_px - exit_px   # short
                trades.append({
                    "date": str(d),
                    "entry_ts": str(entry_ts),
                    "exit_ts": str(exit_ts),
                    "entry_px": entry_px, "exit_px": exit_px,
                    "stop": stop, "target": target, "pdh": day_pdh, "pdl": day_pdl,
                    "exit_reason": exit_reason,
                    "pnl_pts": pnl_pts,
                    "pnl_usd": pnl_pts * SIZE * MNQ_PER_PT,
                })
                break    # one trade per day

    # ---- report --------------------------------------------------------
    print("=" * 78)
    print("USER TOP-TICK strategy — PDH sweep + bearish 4h/daily bias, NQ 5-min")
    print("=" * 78)
    print(f"calendar days tested : {len(dates_sorted)}")
    print(f"trades fired         : {len(trades)}")
    if not trades:
        print("Strategy never fired across 8 years.")
        return
    tdf = pd.DataFrame(trades)
    targets = (tdf["exit_reason"] == "target").sum()
    stops = (tdf["exit_reason"] == "stop").sum()
    timeouts = (tdf["exit_reason"] == "timeout").sum()
    wins = (tdf["pnl_usd"] > 0).sum()
    print(f"target hits          : {targets}   stops: {stops}   timeouts: {timeouts}")
    print(f"profitable trades    : {wins} ({wins/len(tdf)*100:.1f}%)")
    print(f"total P&L            : ${tdf['pnl_usd'].sum():+,.0f}")
    print(f"avg per trade        : ${tdf['pnl_usd'].mean():+,.0f}")
    print(f"largest win          : ${tdf['pnl_usd'].max():+,.0f}")
    print(f"largest loss         : ${tdf['pnl_usd'].min():+,.0f}")
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    peak = np.maximum.accumulate(cum)
    print(f"max drawdown         : ${(cum - peak).min():+,.0f}")
    print(f"avg hold (bars)      : "
          f"{((pd.to_datetime(tdf['exit_ts']) - pd.to_datetime(tdf['entry_ts'])).dt.total_seconds() / 300).mean():.1f}")
    print("\nfirst 10 trades:")
    print(tdf[["date", "entry_px", "exit_px", "exit_reason",
               "pnl_pts", "pnl_usd"]].head(10).to_string(index=False))
    print("\nlast 10 trades:")
    print(tdf[["date", "entry_px", "exit_px", "exit_reason",
               "pnl_pts", "pnl_usd"]].tail(10).to_string(index=False))


if __name__ == "__main__":
    main()

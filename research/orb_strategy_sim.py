"""
Opening Range Breakout (ORB) simulation on NQ 5-min, 8 years.

Rules from the user-supplied articles (CrossTrade + Futures Buddy + TradeTerminal):
  * Define opening range = first 15 min (9:30-9:45 ET) or first 30 min
    (9:30-10:00 ET) of RTH. Article 2 specifically suggests 30-min for NQ.
  * LONG  on the first bar whose CLOSE > OR-high after the OR window
  * SHORT on the first bar whose CLOSE < OR-low after the OR window
  * Entry at the next bar's open (lookahead-safe)
  * Stop  = opposite side of the opening range
  * Target = 1× OR width projected from entry (measured move)
  * Time cutoff: no new entries after 11:30 ET
  * Flatten at session close (16:00 ET)
  * One-and-done: only the FIRST valid breakout (long or short) per day
  * Size: 10 MNQ ($20/pt)

A second pass adds the two filters the articles flag as edge-improvers:
  * Higher-timeframe trend filter: long only if yesterday's close > daily
    EMA20; short only if below
  * VWAP filter: long only if entry > session VWAP; short only if below
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NY = "America/New_York"
SIZE = 10
MNQ_PER_PT = 2.0


def simulate_orb_day(day_bars: pd.DataFrame, or_minutes: int,
                     trend_filter: int = 0,
                     vwap_filter: bool = False) -> dict | None:
    """Run ORB on a single RTH session. Returns trade dict or None.

    trend_filter: 0 = off, +1 = require yesterday's close > daily EMA20 for
    longs (and below for shorts), -1 unused. vwap_filter: require entry to
    be on the breakout side of the session VWAP."""
    expected_or_bars = or_minutes // 5

    or_bars = day_bars.iloc[:expected_or_bars]
    if len(or_bars) < expected_or_bars:
        return None
    or_high = float(or_bars["high"].max())
    or_low = float(or_bars["low"].min())
    or_range = or_high - or_low
    if or_range <= 0:
        return None

    # entry window: after OR, before 11:30 ET
    h = day_bars["ny_hour"].to_numpy()
    m = day_bars["ny_minute"].to_numpy()
    after_or_idx = expected_or_bars
    cutoff_idx = len(day_bars)
    for i in range(after_or_idx, len(day_bars)):
        if h[i] > 11 or (h[i] == 11 and m[i] >= 30):
            cutoff_idx = i
            break

    if vwap_filter:
        tp = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3.0
        vwap = (tp * day_bars["volume"]).cumsum() / day_bars["volume"].cumsum()
    else:
        vwap = None

    # find first breakout
    breakout_pos = None
    side = None
    for i in range(after_or_idx, cutoff_idx):
        c = day_bars.iloc[i]["close"]
        if c > or_high:
            breakout_pos, side = i, "LONG"; break
        if c < or_low:
            breakout_pos, side = i, "SHORT"; break
    if breakout_pos is None or breakout_pos + 1 >= len(day_bars):
        return None

    entry_ts = day_bars.index[breakout_pos + 1]
    entry_px = float(day_bars.iloc[breakout_pos + 1]["open"])

    if vwap_filter:
        v = float(vwap.iloc[breakout_pos + 1])
        if side == "LONG" and entry_px <= v: return None
        if side == "SHORT" and entry_px >= v: return None

    if trend_filter != 0:
        bias = day_bars["daily_bias"].iloc[0]    # +1 / -1 set upstream
        if side == "LONG" and bias < 0: return None
        if side == "SHORT" and bias > 0: return None

    if side == "LONG":
        stop, target = or_low, entry_px + or_range
    else:
        stop, target = or_high, entry_px - or_range

    # walk forward bars in the same day until stop/target/EOD
    exit_px, exit_reason = None, "eod"
    exit_ts = day_bars.index[-1]
    for j in range(breakout_pos + 1, len(day_bars)):
        bar = day_bars.iloc[j]
        if side == "LONG":
            if bar["low"] <= stop:
                exit_px, exit_reason, exit_ts = stop, "stop", day_bars.index[j]; break
            if bar["high"] >= target:
                exit_px, exit_reason, exit_ts = target, "target", day_bars.index[j]; break
        else:
            if bar["high"] >= stop:
                exit_px, exit_reason, exit_ts = stop, "stop", day_bars.index[j]; break
            if bar["low"] <= target:
                exit_px, exit_reason, exit_ts = target, "target", day_bars.index[j]; break
    if exit_px is None:
        exit_px = float(day_bars.iloc[-1]["close"])

    pnl_pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return {
        "date": str(day_bars["ny_date"].iloc[0]),
        "side": side, "or_range": or_range,
        "entry_ts": entry_ts, "entry_px": entry_px,
        "stop": stop, "target": target,
        "exit_ts": exit_ts, "exit_px": exit_px,
        "exit_reason": exit_reason,
        "pnl_pts": pnl_pts,
        "pnl_usd": pnl_pts * SIZE * MNQ_PER_PT,
    }


def report(label: str, trades: list[dict], n_days: int) -> None:
    print(f"\n{'='*80}\n{label}\n{'='*80}")
    if not trades:
        print("  No trades fired.")
        return
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    targets = int((tdf["exit_reason"] == "target").sum())
    stops   = int((tdf["exit_reason"] == "stop").sum())
    eods    = int((tdf["exit_reason"] == "eod").sum())
    total = float(tdf["pnl_usd"].sum())
    avg = float(tdf["pnl_usd"].mean())
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    avg_win = (gw / wins) if wins else 0.0
    avg_loss = (gl / (n - wins)) if (n - wins) > 0 else 0.0
    months = n_days / 21.0
    print(f"  Trades fired         : {n}")
    print(f"  Trades per month     : {n/months:.1f}")
    print(f"  Longs / Shorts       : {(tdf['side']=='LONG').sum()} / "
          f"{(tdf['side']=='SHORT').sum()}")
    print(f"  Win rate             : {wins/n*100:.1f}%")
    print(f"  Exit mix             : target={targets}  stop={stops}  eod={eods}")
    print(f"  Total P&L            : ${total:+,.0f}")
    print(f"  Avg per trade        : ${avg:+,.0f}")
    print(f"  Avg win / Avg loss   : ${avg_win:+,.0f} / ${-avg_loss:+,.0f}  "
          f"(payoff {avg_win/avg_loss if avg_loss else 0:.2f})")
    print(f"  Profit factor        : {pf:.2f}")
    print(f"  Max drawdown         : ${maxdd:+,.0f}")
    print(f"  Largest win / loss   : ${tdf['pnl_usd'].max():+,.0f} / "
          f"${tdf['pnl_usd'].min():+,.0f}")


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    ny = pd.DatetimeIndex(nq.index.tz_convert(NY))
    nq = nq.copy()
    nq["ny_date"]   = ny.date
    nq["ny_hour"]   = ny.hour
    nq["ny_minute"] = ny.minute
    rth = (((nq["ny_hour"] == 9) & (nq["ny_minute"] >= 30)) |
           ((nq["ny_hour"] >= 10) & (nq["ny_hour"] < 16)))
    rth_df = nq[rth].copy()

    # daily bias: yesterday's daily close vs daily EMA20
    daily_close = rth_df.groupby("ny_date")["close"].last()
    ema20 = daily_close.ewm(span=20, adjust=False).mean()
    bias_today = (daily_close > ema20).astype(int) * 2 - 1   # +1 / -1
    bias_yesterday = bias_today.shift(1).fillna(0).astype(int)
    rth_df["daily_bias"] = rth_df["ny_date"].map(bias_yesterday.to_dict())

    print("=" * 80)
    print("OPENING RANGE BREAKOUT — NQ 5-min, 8 yrs, 10 MNQ ($20/pt)")
    print("=" * 80)
    print(f"RTH bars: {len(rth_df):,}   sessions: "
          f"{rth_df['ny_date'].nunique():,}   "
          f"range: {rth_df['ny_date'].min()} -> {rth_df['ny_date'].max()}")

    n_days = rth_df["ny_date"].nunique()
    days_grouped = list(rth_df.groupby("ny_date"))

    for or_min in (15, 30):
        # base
        trades = []
        for _, dbars in days_grouped:
            t = simulate_orb_day(dbars, or_min)
            if t: trades.append(t)
        report(f"{or_min}-min ORB  (no filters)", trades, n_days)

        # + trend filter
        trades_tf = []
        for _, dbars in days_grouped:
            t = simulate_orb_day(dbars, or_min, trend_filter=1)
            if t: trades_tf.append(t)
        report(f"{or_min}-min ORB  +  daily-EMA20 trend filter", trades_tf, n_days)

        # + VWAP filter
        trades_vf = []
        for _, dbars in days_grouped:
            t = simulate_orb_day(dbars, or_min, vwap_filter=True)
            if t: trades_vf.append(t)
        report(f"{or_min}-min ORB  +  VWAP filter", trades_vf, n_days)

        # + both
        trades_both = []
        for _, dbars in days_grouped:
            t = simulate_orb_day(dbars, or_min, trend_filter=1, vwap_filter=True)
            if t: trades_both.append(t)
        report(f"{or_min}-min ORB  +  trend & VWAP", trades_both, n_days)


if __name__ == "__main__":
    main()

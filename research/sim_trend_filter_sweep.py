"""Trend-filter sweep — does a higher-timeframe trend gate improve the
pullback-impulse strategy on the 3-month NQ tick data?

User's request: on days with overwhelming directional news (Trump, Iran
geopolitics, etc.), the bot should detect 'this is a clear bull/bear
regime' and ONLY take trades in the trend direction, skipping the
counter-trend entries that get eaten in trending markets.

Tests several trend metrics + thresholds:
  1. 60-bar close-vs-close NET MOVE (pt) -- simple, intuitive
  2. 30-bar EMA slope normalised by ATR -- volatility-aware
  3. % of last 60 bars closing above their open -- breadth filter

For each: skip SHORTs when trend > +threshold, skip LONGs when trend
< -threshold, take both when |trend| <= threshold.

Compares against BASELINE (no filter, current production) on the same
24.9M-tick dataset using the same fill realism. If a filter beats
baseline on BOTH return AND DD, it's a candidate for deployment."""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/trend_filter_sweep.json")


# ---------------------------------------------------------------------------
# Filter helpers — return a per-bar "trend bias" array
#   bias[i] = +1  -> STRONG UP, only allow LONG entries
#   bias[i] = -1  -> STRONG DOWN, only allow SHORT entries
#   bias[i] =  0  -> NEUTRAL, allow both
# ---------------------------------------------------------------------------
def trend_netmove(bars: pd.DataFrame, lookback: int, threshold_pts: float):
    """Net close-vs-close move over `lookback` bars. Simplest possible
    momentum filter. threshold = absolute pt move."""
    c = bars["close"].to_numpy()
    bias = np.zeros(len(bars), dtype=np.int8)
    for i in range(lookback, len(bars)):
        delta = c[i] - c[i - lookback]
        if delta >= threshold_pts: bias[i] = 1
        elif delta <= -threshold_pts: bias[i] = -1
    return bias


def trend_ema_slope(bars: pd.DataFrame, ema_span: int, lookback: int,
                    atr_mult: float):
    """EMA slope over `lookback` bars, normalised by ATR. atr_mult is the
    threshold expressed in ATR-units (e.g., 1.0 = slope >= 1 ATR per
    lookback bars to count as 'strong trend')."""
    c = bars["close"].to_numpy()
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    ema = pd.Series(c).ewm(span=ema_span, adjust=False).mean().to_numpy()
    tr = np.maximum.reduce([h - l, np.abs(h - np.r_[c[0], c[:-1]]),
                            np.abs(l - np.r_[c[0], c[:-1]])])
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    bias = np.zeros(len(bars), dtype=np.int8)
    for i in range(lookback, len(bars)):
        if not np.isfinite(atr[i]) or atr[i] <= 0: continue
        slope = (ema[i] - ema[i - lookback]) / atr[i]
        if slope >= atr_mult: bias[i] = 1
        elif slope <= -atr_mult: bias[i] = -1
    return bias


def trend_breadth(bars: pd.DataFrame, lookback: int, threshold_pct: float):
    """% of last `lookback` bars closing above their open. >threshold = up
    trend, <(1-threshold) = down trend."""
    o = bars["open"].to_numpy(); c = bars["close"].to_numpy()
    up_bars = (c > o).astype(np.int8)
    bias = np.zeros(len(bars), dtype=np.int8)
    for i in range(lookback, len(bars)):
        frac_up = up_bars[i - lookback:i].mean()
        if frac_up >= threshold_pct: bias[i] = 1
        elif frac_up <= (1 - threshold_pct): bias[i] = -1
    return bias


def apply_filter(setups: list, bias: np.ndarray, bars: pd.DataFrame) -> list:
    """Drop setups whose direction opposes the current trend bias."""
    bar_ts = bars.index.astype("int64").to_numpy()
    out = []
    for s in setups:
        # find the bar this setup was identified at
        i = np.searchsorted(bar_ts, s["sig_ts"], side="left") - 1
        if i < 0 or i >= len(bias): continue
        b = bias[i]
        if b == 0:
            out.append(s)             # neutral -- take both
        elif b == 1 and s["side"] == 1:
            out.append(s)             # up trend, taking LONGs
        elif b == -1 and s["side"] == -1:
            out.append(s)             # down trend, taking SHORTs
        # else: skip (counter-trend)
    return out


def main():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)
    print(f"Loaded {len(df):,} ticks, {len(bars):,} bars ({period_days:.0f}d)")

    # BASELINE (no filter) -- both target=12 and target=18 for comparison
    print(f"\n{'Filter':<46}{'n':>7}{'WR':>7}{'PF':>6}{'Ret/mo':>10}{'DD%':>7}")
    print("-" * 92)
    results = {}
    setups_t12 = baseline_setups(bars)
    # Override setups' target_px to use target=12 (account 1) vs target=18 (account 2)
    def with_target(tgt_pts: float):
        out = []
        for s in setups_t12:
            side = s["side"]
            entry = s["entry_px"]
            stop  = s["stop_px"]
            target = entry + tgt_pts if side == 1 else entry - tgt_pts
            out.append({**s, "target_px": target})
        return out

    def run(label, setups):
        trades = simulate(setups, price, ts_ns)
        s = score(trades, period_days)
        results[label] = s
        print(f"{label:<46}{s.get('n',0):>7}{s.get('wr',0):>6.1f}%{s.get('pf',0):>6.2f}"
              f"{s.get('ret_mo',0):>+9.2f}%{s.get('max_dd_pct',0):>6.2f}%")

    # ------------------------------------------------------------
    # Reference: baselines (no filter)
    # ------------------------------------------------------------
    print("--- BASELINES (no filter, reference) ---")
    run("BASELINE target=12 (account 1)", with_target(12.0))
    run("BASELINE target=18 (account 2)", with_target(18.0))

    # ------------------------------------------------------------
    # Filter 1: simple net-move threshold
    # ------------------------------------------------------------
    print("\n--- 60-bar NET-MOVE filter (target=18) ---")
    for thr in (15, 20, 25, 30, 40, 50):
        bias = trend_netmove(bars, lookback=60, threshold_pts=thr)
        filtered = apply_filter(with_target(18.0), bias, bars)
        run(f"netmove(60bar, >={thr}pt)", filtered)

    print("\n--- 60-bar NET-MOVE filter (target=12) ---")
    for thr in (15, 20, 30):
        bias = trend_netmove(bars, lookback=60, threshold_pts=thr)
        filtered = apply_filter(with_target(12.0), bias, bars)
        run(f"netmove(60bar, >={thr}pt) [t12]", filtered)

    # ------------------------------------------------------------
    # Filter 2: EMA slope normalised by ATR
    # ------------------------------------------------------------
    print("\n--- EMA-slope filter (target=18) ---")
    for em, lb, mult in [(30, 30, 1.5), (30, 30, 2.0), (60, 60, 1.5),
                         (60, 60, 2.0), (60, 60, 3.0)]:
        bias = trend_ema_slope(bars, ema_span=em, lookback=lb, atr_mult=mult)
        filtered = apply_filter(with_target(18.0), bias, bars)
        run(f"ema_slope(span={em},lb={lb},>= {mult}*ATR)", filtered)

    # ------------------------------------------------------------
    # Filter 3: breadth (% bars closing up)
    # ------------------------------------------------------------
    print("\n--- BREADTH filter (target=18) ---")
    for lb, p in [(30, 0.65), (60, 0.60), (60, 0.65), (60, 0.70)]:
        bias = trend_breadth(bars, lookback=lb, threshold_pct=p)
        filtered = apply_filter(with_target(18.0), bias, bars)
        run(f"breadth(lb={lb},>={p*100:.0f}%)", filtered)

    # ------------------------------------------------------------
    # MULTI-DAY trend filter: user wants to detect "this week is bull"
    # ------------------------------------------------------------
    print("\n--- DAILY trend filter (target=18) -- prev N hours net move ---")
    # 4h = 240 bars, 8h = 480, 16h = 960, 24h = 1440
    for hours, thr in [(4, 40), (4, 60), (8, 60), (8, 100), (16, 100),
                       (16, 150), (24, 100), (24, 150), (24, 200)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        filtered = apply_filter(with_target(18.0), bias, bars)
        run(f"daily_trend({hours}h, >={thr}pt)", filtered)

    print("\n--- DAILY trend filter (target=12) ---")
    for hours, thr in [(8, 60), (16, 100), (24, 150)]:
        bias = trend_netmove(bars, lookback=hours*60, threshold_pts=thr)
        filtered = apply_filter(with_target(12.0), bias, bars)
        run(f"daily_trend({hours}h, >={thr}pt) [t12]", filtered)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nTotal: {time.time()-t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()

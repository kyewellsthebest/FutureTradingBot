"""Trend-classifier shootout for the Fib 50% bot.

The user wants: bot identifies "clear uptrend" / "clear downtrend" / "chop"
based on PRICE STRUCTURE, then trades MORE in trend and NOTHING in chop.

Compares 5 trend classifiers, each computed at every 1-min bar:

A. CURRENT  — 2 HH + 2 HL on 1-min k=5 fractals (the live bot's filter)
B. STRONGER — 3 HH + 3 HL on 1-min k=5 fractals
C. 5M-HTF   — 2 HH + 2 HL on 5-min bars w/ k=3 fractals (real HTF)
D. EMA-SLOPE — 30-bar EMA's slope over last 10 bars (slope > threshold)
E. NET-DISP — net move of last 30 bars / range of last 30 bars > threshold
F. ADX-LIKE — directional movement index, threshold 25

Each classifier produces UP/DOWN/CHOP per bar. Bot fires only when
classifier matches the setup's direction. We then report trade volume and
P&L per classifier to find the one that lets the bot fire MORE often on
clean trend days and NOT at all on chop days.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
from dataclasses import dataclass

from research.fib_50_time_of_day import (
    DATA_FILE, PIVOT_K, MIN_LEG_PTS, MIN_ENTRY_RISK_FRAC,
    MAX_HOLD_BARS, MAX_SETUP_AGE_BARS,
    CONTRACTS, MNQ_PER_PT, ROUND_TRIP_COMM_PER_CONTRACT,
    find_pivots, build_pivot_track, simulate,
)


# ============================================================================
# Trend classifiers — each returns an int8 array of length n (1=UP, -1=DN, 0=CHOP)
# ============================================================================

def trend_pivot_count(highs, lows, k: int, n: int,
                      n_hh: int = 2, n_hl: int = 2) -> np.ndarray:
    """A/B: trend = (last n_hh confirmed highs all rising) AND
    (last n_hl confirmed lows all rising). Mirror for downtrend.
    """
    out = np.zeros(n, dtype=np.int8)
    hi_idx = lo_idx = 0
    seen_h: list[tuple[int, float]] = []
    seen_l: list[tuple[int, float]] = []
    for t in range(n):
        while hi_idx < len(highs) and highs[hi_idx][0] + k <= t:
            seen_h.append(highs[hi_idx]); hi_idx += 1
        while lo_idx < len(lows) and lows[lo_idx][0] + k <= t:
            seen_l.append(lows[lo_idx]); lo_idx += 1
        if len(seen_h) < n_hh or len(seen_l) < n_hl:
            continue
        hi_vals = [p[1] for p in seen_h[-n_hh:]]
        lo_vals = [p[1] for p in seen_l[-n_hl:]]
        rising_h = all(hi_vals[i] > hi_vals[i-1] for i in range(1, n_hh))
        rising_l = all(lo_vals[i] > lo_vals[i-1] for i in range(1, n_hl))
        falling_h = all(hi_vals[i] < hi_vals[i-1] for i in range(1, n_hh))
        falling_l = all(lo_vals[i] < lo_vals[i-1] for i in range(1, n_hl))
        if rising_h and rising_l:
            out[t] = 1
        elif falling_h and falling_l:
            out[t] = -1
    return out


def trend_htf_5m(nq: pd.DataFrame, n_hh: int = 2, n_hl: int = 2) -> np.ndarray:
    """C: trend = 2 HH + 2 HL on 5-min bars (k=3 fractals on 5m)."""
    nq5 = nq.resample("5min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    highs5, lows5 = find_pivots(nq5["high"].to_numpy(), nq5["low"].to_numpy(), 3)
    trend5 = trend_pivot_count(highs5, lows5, 3, len(nq5), n_hh, n_hl)
    s = pd.Series(trend5, index=nq5.index, dtype=np.int8)
    # forward-fill onto 1-min grid
    s1 = s.reindex(nq.index, method="ffill").fillna(0).astype(np.int8)
    return s1.to_numpy()


def trend_ema_slope(nq: pd.DataFrame, span: int = 30, slope_bars: int = 10,
                    min_slope_pts: float = 0.5) -> np.ndarray:
    """D: trend = sign of EMA slope over last `slope_bars`, only counts if
    |slope per bar| > min_slope_pts NQ points."""
    closes = nq["close"].to_numpy()
    ema = pd.Series(closes).ewm(span=span, adjust=False).mean().to_numpy()
    n = len(closes)
    out = np.zeros(n, dtype=np.int8)
    for t in range(slope_bars, n):
        slope = (ema[t] - ema[t - slope_bars]) / slope_bars
        if slope > min_slope_pts:
            out[t] = 1
        elif slope < -min_slope_pts:
            out[t] = -1
    return out


def trend_net_displacement(nq: pd.DataFrame, lookback: int = 30,
                           min_ratio: float = 0.4) -> np.ndarray:
    """E: trend = signed net move / range over last `lookback` bars.
    UP if ratio > +min_ratio, DOWN if < -min_ratio.
    """
    closes = nq["close"].to_numpy()
    highs = nq["high"].to_numpy()
    lows  = nq["low"].to_numpy()
    n = len(closes)
    out = np.zeros(n, dtype=np.int8)
    for t in range(lookback, n):
        net = closes[t] - closes[t - lookback]
        rng = highs[t - lookback + 1:t + 1].max() \
            - lows[t - lookback + 1:t + 1].min()
        if rng == 0:
            continue
        r = net / rng
        if r > min_ratio:
            out[t] = 1
        elif r < -min_ratio:
            out[t] = -1
    return out


def trend_adx_like(nq: pd.DataFrame, period: int = 14,
                   adx_threshold: float = 25.0) -> np.ndarray:
    """F: Wilder-style ADX. UP/DOWN if ADX > threshold AND +DI > -DI (or v.v.)."""
    h = nq["high"].to_numpy()
    l = nq["low"].to_numpy()
    c = nq["close"].to_numpy()
    n = len(c)

    up_move   = np.zeros(n); dn_move = np.zeros(n)
    for i in range(1, n):
        up   = h[i] - h[i - 1]
        down = l[i - 1] - l[i]
        up_move[i] = up   if (up > down and up > 0) else 0
        dn_move[i] = down if (down > up and down > 0) else 0

    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    # Wilder smoothing
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().to_numpy()
    plus_di_s = pd.Series(up_move).ewm(alpha=1/period, adjust=False).mean()
    minus_di_s = pd.Series(dn_move).ewm(alpha=1/period, adjust=False).mean()
    plus_di  = 100 * (plus_di_s.to_numpy()  / np.where(atr == 0, 1, atr))
    minus_di = 100 * (minus_di_s.to_numpy() / np.where(atr == 0, 1, atr))
    dx = 100 * np.abs(plus_di - minus_di) / np.where(
        (plus_di + minus_di) == 0, 1, (plus_di + minus_di)
    )
    adx = pd.Series(dx).ewm(alpha=1/period, adjust=False).mean().to_numpy()

    out = np.zeros(n, dtype=np.int8)
    for t in range(period * 2, n):
        if adx[t] > adx_threshold:
            if plus_di[t] > minus_di[t]:
                out[t] = 1
            else:
                out[t] = -1
    return out


# ============================================================================
# Strategy runner (just direction-filters, no other entry filters)
# ============================================================================

def run_with_trend(nq: pd.DataFrame, rh_src, rh_val, rl_src, rl_val,
                   trend: np.ndarray, arm_reject: bool = False,
                   realistic_fill: bool = False,
                   fill_window: int = 5,
                   live_semantics: bool = False) -> list[dict]:
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(nq)
    trades = []
    active_until = -1
    used = set()
    for t in range(n - 2):
        if t < active_until: continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]: continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS: continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > MAX_SETUP_AGE_BARS: continue
        key = (int(rh_src[t]), int(rl_src[t]))
        if key in used: continue

        level50 = (rh_val[t] + rl_val[t]) / 2.0
        if rh_src[t] < rl_src[t]:
            side = "SHORT" if arr[t, 1] >= level50 else None
        else:
            side = "LONG"  if arr[t, 2] <= level50 else None
        if side is None: continue

        tr = trend[t]
        if (side == "LONG" and tr != 1) or (side == "SHORT" and tr != -1):
            continue

        if side == "SHORT":
            stop_px, target_px = float(rh_val[t]), float(rl_val[t])
        else:
            stop_px, target_px = float(rl_val[t]), float(rh_val[t])

        # ARM-REJECT (no live_semantics): arming bar's close must be back
        # inside the leg. Look-ahead bias unless live_semantics is True.
        if arm_reject and not live_semantics:
            arm_close = float(arr[t, 3])
            if side == "SHORT" and arm_close >= level50: continue
            if side == "LONG"  and arm_close <= level50: continue

        # Realistic fill: limit only placed AFTER arm-bar closes; need
        # a subsequent bar to retouch level50 to fill.
        scratch_exit = False
        if arm_reject and realistic_fill:
            filled = False
            fill_bar = -1
            for k in range(1, fill_window + 1):
                if t + k >= n: break
                bar_h = float(arr[t + k, 1])
                bar_l = float(arr[t + k, 2])
                if side == "SHORT" and bar_h >= stop_px: break
                if side == "LONG"  and bar_l <= stop_px: break
                if side == "SHORT" and bar_h >= level50:
                    filled = True; fill_bar = t + k; break
                if side == "LONG"  and bar_l <= level50:
                    filled = True; fill_bar = t + k; break
            if not filled: continue
            entry_loc = fill_bar
            entry_bar_for_sim = fill_bar
        elif arm_reject and live_semantics:
            # Limit fills intrabar on arming bar. After bar closes, check:
            # if close is OUTSIDE the leg (bad arming), scratch-exit at
            # arming-bar close. Otherwise hold normally.
            arm_close = float(arr[t, 3])
            bad_arm = (side == "SHORT" and arm_close >= level50) \
                   or (side == "LONG"  and arm_close <= level50)
            if bad_arm:
                # We're in the trade at level50, exit at arm-bar close.
                scratch_exit = True
                entry_loc = t
                entry_bar_for_sim = t
            else:
                entry_loc = t
                entry_bar_for_sim = t + 1
        else:
            entry_loc = t + 1
            entry_bar_for_sim = t + 1

        entry_px = float(level50)
        if abs(stop_px - entry_px) < leg * MIN_ENTRY_RISK_FRAC:
            continue

        if scratch_exit:
            exit_loc = t
            exit_px = float(arr[t, 3])
            exit_reason = "scratch"
        else:
            exit_loc, exit_px, exit_reason = simulate(
                entry_bar_for_sim, side, entry_px, stop_px, target_px, arr,
            )
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        pnl_usd = pnl_pts * CONTRACTS * MNQ_PER_PT \
                  - ROUND_TRIP_COMM_PER_CONTRACT * CONTRACTS
        trades.append({
            "side": side, "pnl_usd": float(pnl_usd),
            "exit_reason": exit_reason,
            "hold_bars": int(exit_loc - entry_loc),
        })
        active_until = exit_loc + 1
        used.add(key)
    return trades


def trend_stats(trend: np.ndarray) -> dict:
    n = len(trend)
    return {
        "pct_up":   float((trend == 1).sum())  / n * 100,
        "pct_dn":   float((trend == -1).sum()) / n * 100,
        "pct_chop": float((trend == 0).sum())  / n * 100,
    }


def trade_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0, "pf": 0, "total": 0, "per_trade": 0}
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    return {
        "n": n,
        "wr": wins / n,
        "pf": pf,
        "total": float(tdf["pnl_usd"].sum()),
        "per_trade": float(tdf["pnl_usd"].mean()),
    }


def main() -> None:
    print("Loading data + pivots...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy()
    n = len(nq)
    highs3, lows3 = find_pivots(h, l, PIVOT_K)
    highs5, lows5 = find_pivots(h, l, 5)
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs3, lows3, PIVOT_K, n)
    print(f"  bars: {n:,}\n")

    classifiers = {
        "A. CURRENT (2HH+2HL on 1m k=5)": trend_pivot_count(highs5, lows5, 5, n, 2, 2),
        "B. STRONGER (3HH+3HL on 1m k=5)": trend_pivot_count(highs5, lows5, 5, n, 3, 3),
        "C. 5M-HTF (2HH+2HL on 5m k=3)":  trend_htf_5m(nq, 2, 2),
        "D. EMA-30 slope >= 0.5pt/bar":    trend_ema_slope(nq, 30, 10, 0.5),
        "D2. EMA-50 slope >= 1.0pt/bar":   trend_ema_slope(nq, 50, 15, 1.0),
        "E. NET-DISP last 30 > 0.4 range": trend_net_displacement(nq, 30, 0.4),
        "E2. NET-DISP last 60 > 0.5":      trend_net_displacement(nq, 60, 0.5),
        "F. ADX-LIKE 14, thresh 25":       trend_adx_like(nq, 14, 25),
        "F2. ADX-LIKE 14, thresh 20":      trend_adx_like(nq, 14, 20),
    }

    print(f"{'Classifier':<38} {'UP%':>5} {'DN%':>5} {'Chop%':>6} "
          f"{'Trades':>7} {'/mo':>5} {'WR':>6} {'PF':>5} {'$/tr':>7} {'Total':>10}")
    print("-" * 115)
    days = (nq.index[-1] - nq.index[0]).days
    months = days / 30.44
    for name, trend in classifiers.items():
        ts = trend_stats(trend)
        trades = run_with_trend(nq, rh_src, rh_val, rl_src, rl_val, trend)
        s = trade_stats(trades)
        pf = f"{s['pf']:>4.2f}" if np.isfinite(s['pf']) else " inf"
        print(f"{name:<38} {ts['pct_up']:>4.1f}% {ts['pct_dn']:>4.1f}% "
              f"{ts['pct_chop']:>5.1f}% {s['n']:>7} {s['n']/months:>4.1f} "
              f"{s['wr']*100:>5.1f}% {pf} ${s['per_trade']:>+5,.0f} "
              f"${s['total']:>+8,.0f}")

    # -----------------------------------------------------------------
    # COMBINE the best classifiers with ARM-REJECT
    # -----------------------------------------------------------------
    print("\n" + "=" * 115)
    print("COMBINING BEST TREND FILTERS WITH ARM-REJECT (entry@level50)")
    print("=" * 115)
    print(f"{'Combo':<48} {'Trades':>7} {'/mo':>5} {'WR':>6} {'PF':>5} "
          f"{'$/tr':>7} {'Total':>10}")
    print("-" * 110)
    combos = [
        ("E + ARM-REJECT (look-ahead bias)            ",
         classifiers["E. NET-DISP last 30 > 0.4 range"], True, False, False),
        ("E + ARM-REJECT + REALISTIC fill             ",
         classifiers["E. NET-DISP last 30 > 0.4 range"], True, True, False),
        ("E + ARM-REJECT + LIVE semantics (scratch ex)",
         classifiers["E. NET-DISP last 30 > 0.4 range"], True, False, True),
        ("E2 + ARM-REJECT + LIVE semantics             ",
         classifiers["E2. NET-DISP last 60 > 0.5"], True, False, True),
        ("D + ARM-REJECT + LIVE semantics              ",
         classifiers["D. EMA-30 slope >= 0.5pt/bar"], True, False, True),
        ("F2 + ARM-REJECT + LIVE semantics             ",
         classifiers["F2. ADX-LIKE 14, thresh 20"], True, False, True),
        ("E (NET-DISP) alone (no ARM-REJECT)           ",
         classifiers["E. NET-DISP last 30 > 0.4 range"], False, False, False),
    ]
    for label, trend, arm, real, live in combos:
        trades = run_with_trend(nq, rh_src, rh_val, rl_src, rl_val, trend,
                                arm_reject=arm, realistic_fill=real,
                                fill_window=5, live_semantics=live)
        s = trade_stats(trades)
        pf = f"{s['pf']:>4.2f}" if np.isfinite(s['pf']) else " inf"
        print(f"{label:<48} {s['n']:>7} {s['n']/months:>4.1f} "
              f"{s['wr']*100:>5.1f}% {pf} ${s['per_trade']:>+5,.0f} "
              f"${s['total']:>+8,.0f}")


if __name__ == "__main__":
    main()

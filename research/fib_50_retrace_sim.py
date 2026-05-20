"""
Fibonacci 50% retracement fade — exactly as drawn in the user's two images.

SHORT setup:
  1. Confirmed swing HIGH (P0) followed by confirmed swing LOW (P1) — a
     down-leg.
  2. Wait for price to retrace UP and touch the 50% level = (P0 + P1) / 2.
  3. SHORT entry at next bar's open.
  4. Stop  = P0 (original swing high)
  5. Target = ((P0+P1)/2 + P1) / 2 = the 50% retracement of the bounce.

LONG setup is the mirror.

Risk/reward is structurally 1 : 0.5 — risk to P0 is twice the distance to
the half-bounce target. Therefore the strategy needs >67% win rate to be
net positive. The bet is that the 50% Fib level is widely-watched enough
that price snaps back from it more than two-thirds of the time.

All pivots use confirmed 5-bar fractals — a pivot at bar t is only KNOWN
at bar t+5, so it is stamped there. No look-ahead.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# tuning
SIZE = 10
MNQ_PER_PT = 2.0
PIVOT_K = 5              # 5-bar fractal — confirmed at +5
MIN_LEG_PTS = 20         # minimum NQ points for a valid leg
MAX_HOLD_BARS = 96       # 8h hard cap (96 × 5-min)
MAX_SETUP_AGE = 50       # bars between P1-confirmation and 50% touch

# stop-loss variants to compare
STOP_VARIANTS = ("wide", "tight_2atr")


def find_pivots(high: pd.Series, low: pd.Series, k: int
                ) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    h = high.to_numpy(); l = low.to_numpy()
    n = len(h)
    highs, lows = [], []
    for t in range(k, n - k):
        if h[t] == h[t - k:t + k + 1].max():
            highs.append((t, float(h[t])))
        if l[t] == l[t - k:t + k + 1].min():
            lows.append((t, float(l[t])))
    return highs, lows


def build_pivot_track(highs, lows, k: int, n: int):
    rh_src = np.full(n, -1, dtype=np.int32)
    rl_src = np.full(n, -1, dtype=np.int32)
    rh_val = np.full(n, np.nan)
    rl_val = np.full(n, np.nan)
    h_idx = l_idx = 0
    cur_h_src, cur_h_val = -1, np.nan
    cur_l_src, cur_l_val = -1, np.nan
    for t in range(n):
        while h_idx < len(highs) and highs[h_idx][0] + k <= t:
            cur_h_src, cur_h_val = highs[h_idx]
            h_idx += 1
        while l_idx < len(lows) and lows[l_idx][0] + k <= t:
            cur_l_src, cur_l_val = lows[l_idx]
            l_idx += 1
        rh_src[t] = cur_h_src; rh_val[t] = cur_h_val
        rl_src[t] = cur_l_src; rl_val[t] = cur_l_val
    return rh_src, rh_val, rl_src, rl_val


def simulate(entry_loc: int, side: str, entry_px: float, stop_px: float,
             target_px: float, arr: np.ndarray) -> tuple[int, float, str]:
    n = len(arr)
    end = min(entry_loc + MAX_HOLD_BARS, n - 1)
    for j in range(entry_loc, end + 1):
        _, h, l, c = arr[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,  "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,  "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr[end, 3]), "timeout"


def run_strategy(nq: pd.DataFrame, stop_variant: str,
                 rh_src, rh_val, rl_src, rl_val, atr) -> list[dict]:
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(nq)
    trades = []
    active_until = -1
    used_setups = set()
    for t in range(n - 1):
        if t < active_until:
            continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]:
            continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS:
            continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > MAX_SETUP_AGE:
            continue
        setup_key = (int(rh_src[t]), int(rl_src[t]))
        if setup_key in used_setups:
            continue

        level50 = (rh_val[t] + rl_val[t]) / 2.0

        side = None
        if rh_src[t] < rl_src[t]:                # down-leg => SHORT setup
            if arr[t, 1] >= level50:              # high touched 50%
                side = "SHORT"
        else:                                     # up-leg   => LONG setup
            if arr[t, 2] <= level50:              # low touched 50%
                side = "LONG"
        if side is None:
            continue

        entry_px = float(arr[t + 1, 0])
        if side == "SHORT":
            wide_stop = float(rh_val[t])         # original swing high
            target_px = (level50 + rl_val[t]) / 2.0
        else:
            wide_stop = float(rl_val[t])
            target_px = (level50 + rh_val[t]) / 2.0

        if stop_variant == "wide":
            stop_px = wide_stop
        else:                                     # tight: 2 ATR beyond entry
            a = float(atr[t]) if not np.isnan(atr[t]) else 10.0
            stop_px = (entry_px + 2 * a) if side == "SHORT" else (entry_px - 2 * a)

        exit_loc, exit_px, exit_reason = simulate(t + 1, side, entry_px,
                                                  stop_px, target_px, arr)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        trades.append({
            "side": side, "entry_ts": nq.index[t + 1],
            "exit_ts": nq.index[exit_loc],
            "entry_px": entry_px, "exit_px": float(exit_px),
            "stop_px": float(stop_px), "target_px": float(target_px),
            "exit_reason": exit_reason,
            "pnl_pts": float(pnl_pts),
            "pnl_usd": float(pnl_pts * SIZE * MNQ_PER_PT),
            "leg_pts": float(leg),
        })
        active_until = exit_loc + 1
        used_setups.add(setup_key)
    return trades


def report(label: str, trades: list[dict]) -> None:
    print(f"\n{'=' * 80}\n{label}\n{'=' * 80}")
    if not trades:
        print("  No trades fired."); return
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins   = int((tdf["pnl_usd"] > 0).sum())
    targets= int((tdf["exit_reason"] == "target").sum())
    stops  = int((tdf["exit_reason"] == "stop").sum())
    timeouts = int((tdf["exit_reason"] == "timeout").sum())
    total  = float(tdf["pnl_usd"].sum())
    avg    = float(tdf["pnl_usd"].mean())
    cum    = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd  = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    months = 8.1 * 12     # ~97 months over 8 yrs
    print(f"  Trades fired       : {n}")
    print(f"  Trades per month   : {n/months:.1f}")
    print(f"  Longs / Shorts     : {(tdf['side']=='LONG').sum()} / "
          f"{(tdf['side']=='SHORT').sum()}")
    print(f"  Win rate           : {wins/n*100:.1f}%   "
          f"(breakeven @ 1:0.5 RR = 66.7%)")
    print(f"  Exit mix           : target={targets}  stop={stops}  "
          f"timeout={timeouts}")
    print(f"  Total P&L          : ${total:+,.0f}")
    print(f"  Avg per trade      : ${avg:+,.0f}")
    print(f"  Profit factor      : {pf:.2f}")
    print(f"  Max drawdown       : ${maxdd:+,.0f}")
    print(f"  Largest win / loss : ${tdf['pnl_usd'].max():+,.0f} / "
          f"${tdf['pnl_usd'].min():+,.0f}")


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    print("=" * 80)
    print("FIBONACCI 50% RETRACEMENT FADE — NQ 5-min, 8 yrs, 10 MNQ ($20/pt)")
    print("=" * 80)
    print(f"Bars: {len(nq):,}")

    print("\nDetecting confirmed 5-bar swing pivots ...")
    highs, lows = find_pivots(nq["high"], nq["low"], PIVOT_K)
    print(f"  swing highs: {len(highs):,}   swing lows: {len(lows):,}")
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs, lows,
                                                        PIVOT_K, len(nq))
    atr = (nq["high"] - nq["low"]).ewm(alpha=1/14, adjust=False).mean().to_numpy()

    for variant in STOP_VARIANTS:
        trades = run_strategy(nq, variant,
                              rh_src, rh_val, rl_src, rl_val, atr)
        label = (f"50% Fib fade  |  stop = swing extreme (P0)"
                 if variant == "wide" else
                 f"50% Fib fade  |  stop = 2 ATR beyond entry")
        report(label, trades)


if __name__ == "__main__":
    main()

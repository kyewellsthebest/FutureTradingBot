"""2D sweep over Fib entry levels and Fib extension targets.

User spec:
  - Trend filter: 2 higher highs AND 2 higher lows from previous (structural)
  - Min leg: 50 points between pivot high and pivot low
  - Stop: originating pivot (no change)
  - Entry: sweep every Fib retracement decimal (0.1, 0.2, ..., 0.9)
  - Target: sweep Fib extensions (0.0, -0.1, -0.272, -0.382, -0.5, -0.618, -1.0)
  - Live-style sim, no look-ahead

Convention for SHORT setup (down-leg from pivot_high to pivot_low):
  entry = pivot_low + entry_pct * (pivot_high - pivot_low)
  target = pivot_low + target_pct * (pivot_high - pivot_low)
  stop = pivot_high
  (entry_pct=0.5, target_pct=0 is the current bot config)

LONG mirror.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

# === Fixed parameters ========================================================
PIVOT_K              = 3
HTF_PIVOT_K          = 5        # for trend filter
MIN_LEG_PTS          = 50.0     # user spec
MAX_HOLD_BARS        = 120      # 2-hr hard cap
MAX_SETUP_AGE_BARS   = 60
FILL_WINDOW_BARS     = 5

CONTRACTS            = 5         # FIXED 5 MNQ for clean comparison across configs
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0


# === Pivot helpers ==========================================================
def find_pivots(high: np.ndarray, low: np.ndarray, k: int):
    n = len(high)
    highs, lows = [], []
    for t in range(k, n - k):
        if high[t] == high[t - k:t + k + 1].max():
            highs.append((t, float(high[t])))
        if low[t] == low[t - k:t + k + 1].min():
            lows.append((t, float(low[t])))
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
            cur_h_src, cur_h_val = highs[h_idx]; h_idx += 1
        while l_idx < len(lows) and lows[l_idx][0] + k <= t:
            cur_l_src, cur_l_val = lows[l_idx]; l_idx += 1
        rh_src[t] = cur_h_src; rh_val[t] = cur_h_val
        rl_src[t] = cur_l_src; rl_val[t] = cur_l_val
    return rh_src, rh_val, rl_src, rl_val


def build_trend_2hh2hl(highs_htf, lows_htf, k: int, n: int) -> np.ndarray:
    """Trend filter: requires last 2 confirmed highs both rising AND last
    2 confirmed lows both rising (for UP). Mirror for DOWN. Otherwise CHOP.
    """
    out = np.zeros(n, dtype=np.int8)
    hi_idx = lo_idx = 0
    seen_h: list[tuple[int, float]] = []
    seen_l: list[tuple[int, float]] = []
    for t in range(n):
        while hi_idx < len(highs_htf) and highs_htf[hi_idx][0] + k <= t:
            seen_h.append(highs_htf[hi_idx]); hi_idx += 1
        while lo_idx < len(lows_htf) and lows_htf[lo_idx][0] + k <= t:
            seen_l.append(lows_htf[lo_idx]); lo_idx += 1
        if len(seen_h) < 2 or len(seen_l) < 2:
            continue
        h1, h0 = seen_h[-1][1], seen_h[-2][1]
        l1, l0 = seen_l[-1][1], seen_l[-2][1]
        if h1 > h0 and l1 > l0:
            out[t] = 1
        elif h1 < h0 and l1 < l0:
            out[t] = -1
    return out


# === Simulator (single entry/target pair) ===================================
def simulate_combo(nq: pd.DataFrame, rh_src, rh_val, rl_src, rl_val,
                   trend: np.ndarray, entry_pct: float,
                   target_pct: float) -> list[dict]:
    """entry_pct: 0..1 (where 0=pivot_opposite, 1=pivot_originating)
    target_pct: typically 0..-1 (0 = opposite pivot, -X = X*leg beyond)
    """
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(nq)
    trades = []
    active_until = -1
    used: set[tuple[int, int]] = set()

    for t in range(n - 2):
        if t < active_until:
            continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]:
            continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS:
            continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > MAX_SETUP_AGE_BARS:
            continue
        key = (int(rh_src[t]), int(rl_src[t]))
        if key in used:
            continue

        # Determine side from leg direction
        if rh_src[t] < rl_src[t]:
            side = "SHORT"
        else:
            side = "LONG"

        # Trend filter: require matching direction
        tr = trend[t]
        if (side == "LONG" and tr != 1) or (side == "SHORT" and tr != -1):
            continue

        # Calculate entry, stop, target based on pcts
        if side == "SHORT":
            # entry_pct from pivot_low up to pivot_high
            entry_px  = float(rl_val[t]) + entry_pct  * (float(rh_val[t]) - float(rl_val[t]))
            target_px = float(rl_val[t]) + target_pct * (float(rh_val[t]) - float(rl_val[t]))
            stop_px   = float(rh_val[t])
        else:
            entry_px  = float(rh_val[t]) - entry_pct  * (float(rh_val[t]) - float(rl_val[t]))
            target_px = float(rh_val[t]) - target_pct * (float(rh_val[t]) - float(rl_val[t]))
            stop_px   = float(rl_val[t])

        # Sanity: stop must be on the right side of entry
        if side == "SHORT" and stop_px <= entry_px: continue
        if side == "LONG"  and stop_px >= entry_px: continue
        # Sanity: target must be on the right side of entry
        if side == "SHORT" and target_px >= entry_px: continue
        if side == "LONG"  and target_px <= entry_px: continue

        # Arming: high (SHORT) or low (LONG) on bar t must reach entry_px
        if side == "SHORT" and h[t] < entry_px: continue
        if side == "LONG"  and l[t] > entry_px: continue

        # Walk forward: look for entry fill (limit at entry_px reached)
        # then track stop / target hits.
        # Realistic fill: arming bar t triggered the limit (level was touched).
        # But for ARM-REJECT semantics, we'd want bar t to close back inside.
        # For this sweep, keep it simple — fill at bar t, simulate from t+1.
        # The relative comparison across entry/target combos is still valid.
        entry_loc = t + 1
        if entry_loc >= n: continue

        # Simulate forward
        end = min(entry_loc + MAX_HOLD_BARS, n - 1)
        exit_loc, exit_px, exit_reason = -1, 0.0, ""
        for j in range(entry_loc, end + 1):
            bar_h = h[j]; bar_l = l[j]
            if side == "LONG":
                if bar_l <= stop_px:
                    exit_loc, exit_px, exit_reason = j, stop_px, "stop"; break
                if bar_h >= target_px:
                    exit_loc, exit_px, exit_reason = j, target_px, "target"; break
            else:
                if bar_h >= stop_px:
                    exit_loc, exit_px, exit_reason = j, stop_px, "stop"; break
                if bar_l <= target_px:
                    exit_loc, exit_px, exit_reason = j, target_px, "target"; break
        if exit_loc < 0:
            exit_loc, exit_px, exit_reason = end, float(c[end]), "timeout"

        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        pnl_usd = pnl_pts * CONTRACTS * MNQ_PER_PT \
                  - COMM_PER_CONTRACT_RT * CONTRACTS

        trades.append({
            "pnl_usd": float(pnl_usd),
            "win": pnl_usd > 0,
            "exit_reason": exit_reason,
        })
        active_until = exit_loc + 1
        used.add(key)
    return trades


def stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "total": 0.0, "per": 0.0,
                "maxdd": 0.0, "targets": 0, "stops": 0, "timeouts": 0}
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int(tdf["win"].sum())
    gw = float(tdf[tdf["win"]]["pnl_usd"].sum())
    gl = float(abs(tdf[~tdf["win"]]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    return {
        "n": n,
        "wr": wins / n,
        "pf": pf,
        "total": float(tdf["pnl_usd"].sum()),
        "per": float(tdf["pnl_usd"].mean()),
        "maxdd": maxdd,
        "targets":  int((tdf["exit_reason"] == "target").sum()),
        "stops":    int((tdf["exit_reason"] == "stop").sum()),
        "timeouts": int((tdf["exit_reason"] == "timeout").sum()),
    }


def main() -> None:
    print("Loading data + pivots...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy()
    n = len(nq)
    print(f"  bars: {n:,}")
    highs3, lows3 = find_pivots(h, l, PIVOT_K)
    highs5, lows5 = find_pivots(h, l, HTF_PIVOT_K)
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs3, lows3, PIVOT_K, n)
    trend = build_trend_2hh2hl(highs5, lows5, HTF_PIVOT_K, n)
    days = (nq.index[-1] - nq.index[0]).days
    months = days / 30.44
    print(f"  months: {months:.1f}\n")

    # Entry sweep: fine-grained around the sweet spot (0.7-0.95)
    entries = [0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]
    # Target sweep: 0.0 (opposite pivot), and Fib extensions
    targets_pretty = [
        ( 0.0,   "1.0x leg (opp pivot)"),
        (-0.1,   "1.1x leg ext"),
        (-0.272, "1.272x leg ext"),
        (-0.382, "1.382x leg ext"),
        (-0.5,   "1.5x leg ext"),
        (-0.618, "1.618x leg ext"),
        (-1.0,   "2.0x leg ext"),
    ]

    print("=" * 110)
    print("HEATMAP: $ per trade  (rows=ENTRY level, cols=TARGET level)")
    print("=" * 110)
    print(f"{'Entry':<7} | " + " | ".join(f"{lab[:14]:>14}" for _, lab in targets_pretty))
    print("-" * 110)
    for e in entries:
        row = []
        for tp, _ in targets_pretty:
            trades = simulate_combo(nq, rh_src, rh_val, rl_src, rl_val,
                                     trend, e, tp)
            s = stats(trades)
            if s["n"] >= 20:
                row.append(f"${s['per']:>+6,.0f} n={s['n']:>4}")
            else:
                row.append(f"  n<20 ({s['n']})  ")
        print(f"{e:<7.1f} | " + " | ".join(f"{c:>14}" for c in row))

    print("\n" + "=" * 110)
    print("HEATMAP: Win-rate %  (min 20 trades)")
    print("=" * 110)
    print(f"{'Entry':<7} | " + " | ".join(f"{lab[:14]:>14}" for _, lab in targets_pretty))
    print("-" * 110)
    for e in entries:
        row = []
        for tp, _ in targets_pretty:
            trades = simulate_combo(nq, rh_src, rh_val, rl_src, rl_val,
                                     trend, e, tp)
            s = stats(trades)
            if s["n"] >= 20:
                row.append(f"{s['wr']*100:>5.1f}% PF{s['pf']:.2f}")
            else:
                row.append(f"   n<20      ")
        print(f"{e:<7.1f} | " + " | ".join(f"{c:>14}" for c in row))

    # Top configs by total P&L
    print("\n" + "=" * 110)
    print("TOP 10 CONFIGURATIONS BY TOTAL P&L (2 years, fixed 5 MNQ, min 30 trades)")
    print("=" * 110)
    print(f"{'Entry':>6} {'Target':>20} {'Trades':>7} {'/mo':>5} "
          f"{'WR':>6} {'PF':>5} {'$/tr':>7} {'Total':>9} {'MaxDD':>9}")
    print("-" * 110)
    results = []
    for e in entries:
        for tp, lab in targets_pretty:
            trades = simulate_combo(nq, rh_src, rh_val, rl_src, rl_val,
                                     trend, e, tp)
            s = stats(trades)
            if s["n"] >= 30:
                results.append((e, tp, lab, s))
    results.sort(key=lambda x: -x[3]["total"])
    for e, tp, lab, s in results[:10]:
        pf = f"{s['pf']:>4.2f}" if np.isfinite(s['pf']) else " inf"
        print(f"{e:>6.1f} {lab:>20} {s['n']:>7} {s['n']/months:>4.1f} "
              f"{s['wr']*100:>5.1f}% {pf} ${s['per']:>+5,.0f} "
              f"${s['total']:>+7,.0f} ${s['maxdd']:>+7,.0f}")

    print("\nBOTTOM 5 BY TOTAL P&L:")
    for e, tp, lab, s in results[-5:]:
        pf = f"{s['pf']:>4.2f}" if np.isfinite(s['pf']) else " inf"
        print(f"{e:>6.1f} {lab:>20} {s['n']:>7} {s['n']/months:>4.1f} "
              f"{s['wr']*100:>5.1f}% {pf} ${s['per']:>+5,.0f} "
              f"${s['total']:>+7,.0f} ${s['maxdd']:>+7,.0f}")


if __name__ == "__main__":
    main()

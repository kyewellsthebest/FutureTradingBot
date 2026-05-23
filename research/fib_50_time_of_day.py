"""Time-of-day analysis for the live Fib 50% bot.

Runs the live strategy logic (PIVOT_K=3, MIN_LEG=25, target=opposite pivot,
stop=originating pivot, 1:1 RR, entry at level50, HTF k=5 trend filter on
the same 1-min series) over 2 years of real Polygon 1-min NQ data, then
bins results by 30-minute window in New York time.

Outputs:
  1. Per-window strategy stats: trades, WR, PF, $/trade, $ total
  2. Per-window directional-efficiency metric (independent of strategy)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE    = PROJECT_ROOT / "data" / "polygon" / "NQ_1min.csv"

# --- Match live bot constants (bot/fib_strategy.py) ---
PIVOT_K            = 3
MIN_LEG_PTS        = 25.0
HTF_PIVOT_K        = 5
MIN_ENTRY_RISK_FRAC = 0.25
MAX_HOLD_BARS      = 120          # 2-hr hard cap on 1-min bars
MAX_SETUP_AGE_BARS = 60           # setup expires if not triggered in 60 min

# --- Sizing / commissions (match live bot) ---
CONTRACTS    = 5                  # 5 MNQ
MNQ_PER_PT   = 2.0                # $2/pt per MNQ
ROUND_TRIP_COMM_PER_CONTRACT = 2.0  # rough $2 r/t per MNQ ($10 for 5)


# --------------------------- pivots ---------------------------------------

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
            cur_h_src, cur_h_val = highs[h_idx]
            h_idx += 1
        while l_idx < len(lows) and lows[l_idx][0] + k <= t:
            cur_l_src, cur_l_val = lows[l_idx]
            l_idx += 1
        rh_src[t] = cur_h_src; rh_val[t] = cur_h_val
        rl_src[t] = cur_l_src; rl_val[t] = cur_l_val
    return rh_src, rh_val, rl_src, rl_val


def build_htf_trend(highs_htf, lows_htf, k: int, n: int) -> np.ndarray:
    """Return per-bar trend label: +1 UP, -1 DOWN, 0 FLAT.

    Live bot logic: latest 2 confirmed highs + 2 confirmed lows. If both are
    making higher highs and higher lows -> UP; lower highs lower lows -> DOWN.
    """
    out = np.zeros(n, dtype=np.int8)
    hi_idx = lo_idx = 0
    seen_h = []   # confirmed (src, val)
    seen_l = []
    for t in range(n):
        while hi_idx < len(highs_htf) and highs_htf[hi_idx][0] + k <= t:
            seen_h.append(highs_htf[hi_idx]); hi_idx += 1
        while lo_idx < len(lows_htf) and lows_htf[lo_idx][0] + k <= t:
            seen_l.append(lows_htf[lo_idx]); lo_idx += 1
        if len(seen_h) >= 2 and len(seen_l) >= 2:
            h1, h0 = seen_h[-1][1], seen_h[-2][1]
            l1, l0 = seen_l[-1][1], seen_l[-2][1]
            if h1 > h0 and l1 > l0:
                out[t] = 1
            elif h1 < h0 and l1 < l0:
                out[t] = -1
    return out


# --------------------------- trade sim ------------------------------------

def simulate(entry_loc: int, side: str, entry_px: float, stop_px: float,
             target_px: float, arr: np.ndarray) -> tuple[int, float, str]:
    n = len(arr)
    end = min(entry_loc + MAX_HOLD_BARS, n - 1)
    for j in range(entry_loc, end + 1):
        _, h, l, c = arr[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,   "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,   "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr[end, 3]), "timeout"


def run_strategy(nq: pd.DataFrame, rh_src, rh_val, rl_src, rl_val,
                 htf_trend) -> list[dict]:
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(nq)
    trades = []
    active_until = -1
    used_setups: set[tuple[int, int]] = set()

    for t in range(n - 1):
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
        setup_key = (int(rh_src[t]), int(rl_src[t]))
        if setup_key in used_setups:
            continue

        level50 = (rh_val[t] + rl_val[t]) / 2.0

        # Side from leg direction (live bot logic)
        if rh_src[t] < rl_src[t]:                # down-leg => SHORT
            side = "SHORT" if arr[t, 1] >= level50 else None
        else:                                     # up-leg => LONG
            side = "LONG"  if arr[t, 2] <= level50 else None
        if side is None:
            continue

        # HTF trend filter (match live)
        tr = htf_trend[t]
        if (side == "LONG" and tr != 1) or (side == "SHORT" and tr != -1):
            continue

        # Entry at level50 (limit), stop at originating pivot, target at opposite pivot
        if side == "SHORT":
            stop_px   = float(rh_val[t])
            target_px = float(rl_val[t])
        else:
            stop_px   = float(rl_val[t])
            target_px = float(rh_val[t])
        entry_px = float(level50)

        # MIN_ENTRY_RISK_FRAC gate
        actual_risk = abs(stop_px - entry_px)
        if actual_risk < leg * MIN_ENTRY_RISK_FRAC:
            continue

        exit_loc, exit_px, exit_reason = simulate(
            t + 1, side, entry_px, stop_px, target_px, arr,
        )

        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        pnl_usd = pnl_pts * CONTRACTS * MNQ_PER_PT \
                  - ROUND_TRIP_COMM_PER_CONTRACT * CONTRACTS

        trades.append({
            "side": side,
            "entry_ts": nq.index[t + 1],
            "exit_ts":  nq.index[exit_loc],
            "entry_px": entry_px,
            "exit_px":  float(exit_px),
            "exit_reason": exit_reason,
            "pnl_pts": float(pnl_pts),
            "pnl_usd": float(pnl_usd),
            "leg_pts": float(leg),
            "hold_bars": int(exit_loc - t),
        })
        active_until = exit_loc + 1
        used_setups.add(setup_key)

    return trades


# --------------------------- time-of-day analysis -------------------------

def directional_efficiency(nq: pd.DataFrame) -> pd.DataFrame:
    """For each (date, 30-min window), compute |last_close - first_open| /
    sum(|close-close[-1]|). 1.0 = pure trend, 0.0 = pure chop.
    """
    df = nq.copy()
    df["bucket"] = df.index.tz_convert("America/New_York").strftime("%H:%M")
    df["date"]   = df.index.tz_convert("America/New_York").date
    # 30-min buckets
    df["bucket_idx"] = (df.index.tz_convert("America/New_York").hour * 60
                        + df.index.tz_convert("America/New_York").minute) // 30

    rows = []
    grouped = df.groupby(["date", "bucket_idx"])
    for (date, b_idx), g in grouped:
        if len(g) < 5:
            continue
        first_open = float(g["open"].iloc[0])
        last_close = float(g["close"].iloc[-1])
        net = abs(last_close - first_open)
        path = float(g["close"].diff().abs().sum())
        if path == 0:
            continue
        rows.append({
            "bucket_idx": int(b_idx),
            "date":       date,
            "net_move":   net,
            "path":       path,
            "efficiency": net / path,
        })
    eff_df = pd.DataFrame(rows)
    summary = eff_df.groupby("bucket_idx").agg(
        median_eff=("efficiency", "median"),
        mean_eff=("efficiency", "mean"),
        median_net=("net_move",  "median"),
        n_days=("efficiency", "count"),
    ).reset_index()
    return summary


def bucket_label(b_idx: int) -> str:
    h = (b_idx * 30) // 60
    m = (b_idx * 30) % 60
    h2 = (h + (m + 30) // 60) % 24
    m2 = (m + 30) % 60
    return f"{h:02d}:{m:02d}–{h2:02d}:{m2:02d}"


def trades_by_bucket(trades: list[dict]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    tdf = pd.DataFrame(trades)
    et_ts = pd.to_datetime(tdf["entry_ts"])
    if et_ts.dt.tz is None:
        et_ts = et_ts.dt.tz_localize("UTC")
    et = et_ts.dt.tz_convert("America/New_York")
    tdf["bucket_idx"] = (et.dt.hour * 60 + et.dt.minute) // 30

    rows = []
    for b_idx, g in tdf.groupby("bucket_idx"):
        n = len(g)
        wins = int((g["pnl_usd"] > 0).sum())
        gw = float(g[g["pnl_usd"] > 0]["pnl_usd"].sum())
        gl = float(abs(g[g["pnl_usd"] < 0]["pnl_usd"].sum()))
        pf = gw / gl if gl > 0 else float("inf")
        total = float(g["pnl_usd"].sum())
        rows.append({
            "bucket_idx": int(b_idx),
            "trades": n,
            "win_rate": wins / n,
            "pf": pf,
            "total_pnl": total,
            "per_trade": total / n,
        })
    return pd.DataFrame(rows).sort_values("bucket_idx")


def main() -> None:
    print("Loading 1-min NQ data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"])
    nq = nq.set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    print(f"  bars: {len(nq):,}  range: {nq.index[0]} → {nq.index[-1]}")

    print("\nDetecting pivots (k=3 for setups, k=5 for HTF trend)...")
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy()
    n = len(nq)
    highs3, lows3 = find_pivots(h, l, PIVOT_K)
    highs5, lows5 = find_pivots(h, l, HTF_PIVOT_K)
    print(f"  k=3 highs/lows: {len(highs3):,} / {len(lows3):,}")
    print(f"  k=5 highs/lows: {len(highs5):,} / {len(lows5):,}")

    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs3, lows3, PIVOT_K, n)
    htf_trend = build_htf_trend(highs5, lows5, HTF_PIVOT_K, n)

    print("\nRunning strategy across full history...")
    trades = run_strategy(nq, rh_src, rh_val, rl_src, rl_val, htf_trend)
    print(f"  trades fired: {len(trades):,}")
    if trades:
        tdf = pd.DataFrame(trades)
        total = tdf["pnl_usd"].sum()
        wr = (tdf["pnl_usd"] > 0).mean()
        print(f"  overall WR: {wr*100:.1f}%   total: ${total:+,.0f}")

    print("\nBucketing by 30-min New York window...")
    bk = trades_by_bucket(trades)
    eff = directional_efficiency(nq)

    merged = bk.merge(eff, on="bucket_idx", how="outer")
    merged = merged.sort_values("bucket_idx")

    print("\n" + "=" * 96)
    print("30-MIN WINDOW ANALYSIS (New York time)")
    print("=" * 96)
    print(f"{'Window (NY)':<14} {'Trades':>7} {'WR':>7} {'PF':>6} "
          f"{'$/trade':>9} {'Total $':>10} {'Eff':>6} {'Net pts':>8} {'n_days':>7}")
    print("-" * 96)

    for _, r in merged.iterrows():
        b_idx = int(r["bucket_idx"])
        label = bucket_label(b_idx)
        n_tr = int(r["trades"]) if not pd.isna(r["trades"]) else 0
        if n_tr > 0:
            wr_s = f"{r['win_rate']*100:>6.1f}%"
            pf_s = f"{r['pf']:>5.2f}" if np.isfinite(r["pf"]) else "  inf"
            pt_s = f"${r['per_trade']:>+7,.0f}"
            tt_s = f"${r['total_pnl']:>+8,.0f}"
        else:
            wr_s = "    —"; pf_s = "    —"; pt_s = "       —"; tt_s = "        —"
        eff_s = f"{r['median_eff']:>5.2f}" if not pd.isna(r["median_eff"]) else "    —"
        net_s = f"{r['median_net']:>7.1f}" if not pd.isna(r["median_net"]) else "      —"
        nd = int(r["n_days"]) if not pd.isna(r["n_days"]) else 0
        print(f"{label:<14} {n_tr:>7} {wr_s} {pf_s} {pt_s} {tt_s} "
              f"{eff_s} {net_s} {nd:>7}")

    # Best & worst windows by per-trade P&L, then by total
    print("\n" + "=" * 96)
    print("TOP 6 WINDOWS BY PER-TRADE P&L (min 20 trades)")
    print("=" * 96)
    big = bk[bk["trades"] >= 20].sort_values("per_trade", ascending=False)
    for _, r in big.head(6).iterrows():
        print(f"  {bucket_label(int(r['bucket_idx'])):<14}  "
              f"n={int(r['trades']):>4}  WR={r['win_rate']*100:>5.1f}%  "
              f"PF={r['pf']:>4.2f}  $/tr={r['per_trade']:>+7,.0f}  "
              f"total={r['total_pnl']:>+10,.0f}")

    print("\nWORST 6 WINDOWS BY PER-TRADE P&L (min 20 trades)")
    print("=" * 96)
    for _, r in big.tail(6).iloc[::-1].iterrows():
        print(f"  {bucket_label(int(r['bucket_idx'])):<14}  "
              f"n={int(r['trades']):>4}  WR={r['win_rate']*100:>5.1f}%  "
              f"PF={r['pf']:>4.2f}  $/tr={r['per_trade']:>+7,.0f}  "
              f"total={r['total_pnl']:>+10,.0f}")


if __name__ == "__main__":
    main()

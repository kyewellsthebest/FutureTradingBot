"""ICT / SMC Liquidity Sweep Reversal backtest.

Strategy: trade against stop hunts on confirmed swing highs/lows.

  BSL (Buy-Side Liquidity) sweep:
    - Find swing high H_i (confirmed k-bar fractal)
    - If a later bar's HIGH exceeds H_i AND its CLOSE is below H_i:
        → liquidity sweep above H_i (institutions took out long stops)
        → SHORT at bar close
        → Stop: bar's high + buffer
        → Target: nearest unswept swing low (SSL) below

  SSL (Sell-Side Liquidity) sweep is the mirror.

Key insight per user spec: "avoid overlapping" — don't trade levels that
have already been swept. Once a swing high gets swept, it's "used."

Tests across multiple timeframes (1m, 3m, 5m, 10m, 15m).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from collections import deque
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

# Sizing
STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 250.0
MAX_CONTRACTS        = 5
MIN_CONTRACTS        = 1


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0:
        return MIN_CONTRACTS
    return max(MIN_CONTRACTS,
               min(MAX_CONTRACTS,
                   int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


# --- Pivot detection -------------------------------------------------------
def find_pivots(high: np.ndarray, low: np.ndarray, k: int):
    n = len(high)
    highs, lows = [], []
    for t in range(k, n - k):
        if high[t] == high[t - k:t + k + 1].max():
            highs.append((t, float(high[t])))
        if low[t] == low[t - k:t + k + 1].min():
            lows.append((t, float(low[t])))
    return highs, lows


# --- Strategy --------------------------------------------------------------
def run_sweep_strategy(arr: np.ndarray, idx,
                       pivot_k: int = 3,
                       buffer_pts: float = 2.0,
                       max_hold_bars: int = 60,
                       lookback_pivots: int = 5,
                       liquidity_age_max: int = 200) -> dict:
    """Sweep reversal backtest.
    arr: (n, 4) [open, high, low, close]
    """
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)

    raw_highs, raw_lows = find_pivots(h, l, pivot_k)
    # convert to dicts indexed by confirmation bar (src + k)
    h_at: dict[int, list[tuple[int, float]]] = {}
    l_at: dict[int, list[tuple[int, float]]] = {}
    for src, px in raw_highs:
        h_at.setdefault(src + pivot_k, []).append((src, px))
    for src, px in raw_lows:
        l_at.setdefault(src + pivot_k, []).append((src, px))

    # Liquidity pools: list of (src_idx, px, swept_at)
    # swept_at == -1 means unswept
    bsl: deque[dict] = deque()   # confirmed swing highs
    ssl: deque[dict] = deque()   # confirmed swing lows

    trades: list[dict] = []
    active = None  # active trade dict
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        # update liquidity pools from newly-confirmed pivots
        for src, px in h_at.get(t, []):
            bsl.append({"src": src, "px": px, "swept": False})
        for src, px in l_at.get(t, []):
            ssl.append({"src": src, "px": px, "swept": False})

        # prune ancient unswept liquidity (too stale to be relevant)
        while bsl and bsl[0]["src"] < t - liquidity_age_max:
            bsl.popleft()
        while ssl and ssl[0]["src"] < t - liquidity_age_max:
            ssl.popleft()

        # --- active trade management ---
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None
            reason = ""
            if stop_hit and tgt_hit:
                exit_px = active["stop"]; reason = "stop"
            elif stop_hit:
                exit_px = active["stop"]; reason = "stop"
            elif tgt_hit:
                exit_px = active["target"]; reason = "target"
            elif t - active["entry_bar"] >= max_hold_bars:
                exit_px = float(c[t]); reason = "timeout"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT \
                      - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({
                    "entry_bar": active["entry_bar"], "exit_bar": t,
                    "entry_ts": idx[active["entry_bar"]], "exit_ts": idx[t],
                    "side": active["side"], "size": active["size"],
                    "entry_px": active["entry"], "exit_px": float(exit_px),
                    "stop_px": active["stop"], "target_px": active["target"],
                    "exit_reason": reason, "pnl_usd": float(pnl),
                    "hold_bars": t - active["entry_bar"],
                })
                active = None

        # --- check for liquidity sweeps on current bar ---
        if active is None:
            # BSL sweep: current bar's high exceeds an unswept swing high,
            # AND current bar's close is below that swing high (rejection)
            best_bsl = None
            for pool in bsl:
                if pool["swept"]: continue
                if h[t] > pool["px"] and c[t] < pool["px"]:
                    # sweep + rejection
                    if best_bsl is None or pool["px"] < best_bsl["px"]:
                        best_bsl = pool
            if best_bsl is not None:
                # mark as swept
                best_bsl["swept"] = True
                # find nearest unswept SSL below current price as target
                target = None
                for pool in reversed(ssl):
                    if not pool["swept"] and pool["px"] < c[t]:
                        target = pool["px"]
                        break
                if target is not None:
                    entry_px = float(c[t])
                    stop_px = float(h[t]) + buffer_pts
                    stop_pts = stop_px - entry_px
                    if entry_px - target > stop_pts * 1.0:  # RR ≥ 1.0
                        size = dynamic_size(stop_pts)
                        active = {
                            "entry_bar": t, "side": "SHORT", "size": size,
                            "entry": entry_px, "stop": stop_px,
                            "target": target,
                        }

            # SSL sweep: mirror
            if active is None:
                best_ssl = None
                for pool in ssl:
                    if pool["swept"]: continue
                    if l[t] < pool["px"] and c[t] > pool["px"]:
                        if best_ssl is None or pool["px"] > best_ssl["px"]:
                            best_ssl = pool
                if best_ssl is not None:
                    best_ssl["swept"] = True
                    target = None
                    for pool in reversed(bsl):
                        if not pool["swept"] and pool["px"] > c[t]:
                            target = pool["px"]
                            break
                    if target is not None:
                        entry_px = float(c[t])
                        stop_px = float(l[t]) - buffer_pts
                        stop_pts = entry_px - stop_px
                        if target - entry_px > stop_pts * 1.0:
                            size = dynamic_size(stop_pts)
                            active = {
                                "entry_bar": t, "side": "LONG", "size": size,
                                "entry": entry_px, "stop": stop_px,
                                "target": target,
                            }

        equity_curve[t] = equity

    return {
        "trades": trades,
        "equity": pd.Series(equity_curve, index=idx),
        "final_equity": equity,
    }


def resample(nq: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq == "1min":
        return nq
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return nq.resample(freq).agg(agg).dropna()


def stats(trades: list[dict], equity: pd.Series, months: float) -> dict:
    if not trades:
        return {"n": 0}
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd_trade = float((cum - np.maximum.accumulate(cum)).min())
    # equity max DD
    eq_peak = equity.cummax()
    eq_dd = (equity - eq_peak).min()
    streak = max_streak = 0
    for _, row in tdf.iterrows():
        if row["pnl_usd"] < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else:
            streak = 0
    total = float(tdf["pnl_usd"].sum())
    return {
        "n": n,
        "wr": wins / n,
        "pf": gw / gl if gl > 0 else float("inf"),
        "total": total,
        "per_trade": total / n,
        "trades_per_mo": n / months,
        "maxdd": maxdd_trade,
        "eq_maxdd": float(eq_dd),
        "max_streak": max_streak,
        "ret_per_mo": total / STARTING_BALANCE * 100 / months,
        "avg_hold": float(tdf["hold_bars"].mean()),
    }


def main() -> None:
    print("Loading 1-min NQ data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    cal_days = (nq.index[-1] - nq.index[0]).days
    months = cal_days / 30.44
    print(f"  bars: {len(nq):,}   months: {months:.1f}\n")

    timeframes = ["1min", "3min", "5min", "10min", "15min"]
    pivot_ks   = [2, 3, 5]   # smaller k = more pivots = more sweeps

    print(f"{'TF':>6} {'k':>2} {'Trades':>7} {'/mo':>5} {'WR':>6} "
          f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'EqMaxDD':>9} "
          f"{'Streak':>7} {'Ret/mo':>8}")
    print("-" * 100)
    all_results = []
    for tf in timeframes:
        df = resample(nq, tf)
        arr = df[["open", "high", "low", "close"]].to_numpy()
        for k in pivot_ks:
            res = run_sweep_strategy(arr, df.index, pivot_k=k)
            s = stats(res["trades"], res["equity"], months)
            if s["n"] == 0:
                continue
            pf = f"{s['pf']:>4.2f}" if s['pf'] < 99 else " inf"
            tag = ""
            if s["ret_per_mo"] >= 5.0 and s["trades_per_mo"] >= 100:
                tag = " ★★★ HITS TARGET"
            elif s["ret_per_mo"] >= 2.0:
                tag = " ★ GOOD"
            elif s["ret_per_mo"] >= 0.5:
                tag = " ✓"
            print(f"{tf:>6} {k:>2} {s['n']:>7} {s['trades_per_mo']:>4.1f} "
                  f"{s['wr']*100:>5.1f}% {pf} ${s['per_trade']:>+5,.0f} "
                  f"${s['total']:>+7,.0f} ${s['eq_maxdd']:>+7,.0f} "
                  f"{s['max_streak']:>6} {s['ret_per_mo']:>+6.2f}%{tag}")
            all_results.append({"tf": tf, "k": k, **s})

    print("\n" + "=" * 100)
    print("TOP 5 BY MONTHLY RETURN")
    print("=" * 100)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:5]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        print(f"  {r['tf']} k={r['k']}: {r['trades_per_mo']:.1f}/mo "
              f"WR={r['wr']*100:.1f}% PF={pf} ${r['per_trade']:+.0f}/tr "
              f"Total=${r['total']:+,.0f} EqDD=${r['eq_maxdd']:+,.0f} "
              f"→ {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()

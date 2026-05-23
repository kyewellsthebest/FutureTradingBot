"""SMC Liquidity Sweep v2 — with quality filters.

Adds to v1:
  - WICK QUALITY: sweep wick must be ≥40% of bar range (real manipulation)
  - CLOSE REJECTION: close must be in lower 30% of bar range for shorts
  - KILLZONE FILTER: only trade during NY/London killzones
  - FVG CONFLUENCE: bearish FVG must exist below for shorts (mirror for longs)
  - HTF TREND: optional counter-trend filter

Tests every combination to find what actually has edge.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from collections import deque
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 250.0
MAX_CONTRACTS        = 5


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def find_pivots(high: np.ndarray, low: np.ndarray, k: int):
    n = len(high)
    highs, lows = [], []
    for t in range(k, n - k):
        if high[t] == high[t - k:t + k + 1].max():
            highs.append((t, float(high[t])))
        if low[t] == low[t - k:t + k + 1].min():
            lows.append((t, float(low[t])))
    return highs, lows


# Killzones in NY local time
KILLZONES = [
    (2*60+0,  5*60+0),    # London KZ: 02:00-05:00 ET
    (9*60+30, 11*60+0),   # NY AM KZ:  09:30-11:00 ET
    (13*60+0, 15*60+0),   # NY PM KZ:  13:00-15:00 ET
]


def in_killzone(minute_of_day: int) -> bool:
    for s, e in KILLZONES:
        if s <= minute_of_day < e:
            return True
    return False


def detect_fvgs(h: np.ndarray, l: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return arrays bullish_fvg[t] and bearish_fvg[t] flagging where each
    3-bar FVG forms (set on the THIRD bar of the pattern).
    Bullish FVG: h[t-2] < l[t]   (gap up between candle t-2 and t)
    Bearish FVG: l[t-2] > h[t]
    """
    n = len(h)
    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)
    for t in range(2, n):
        if h[t-2] < l[t]: bull[t] = True
        if l[t-2] > h[t]: bear[t] = True
    return bull, bear


def run_strategy(arr: np.ndarray, idx, ny_min: np.ndarray,
                 pivot_k: int = 3,
                 max_hold_bars: int = 60,
                 buffer_pts: float = 2.0,
                 wick_pct_min: float = 0.40,   # sweep wick / bar range
                 close_rej_pct: float = 0.30,   # close in lower (short) / upper (long) %
                 use_killzone: bool = False,
                 use_fvg: bool = False,
                 mode: str = "reversal",        # "reversal" or "continuation"
                 liquidity_age_max: int = 200,
                 min_rr: float = 1.5,
                 ) -> dict:
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    raw_highs, raw_lows = find_pivots(h, l, pivot_k)
    h_at: dict[int, list] = {}
    l_at: dict[int, list] = {}
    for src, px in raw_highs: h_at.setdefault(src + pivot_k, []).append((src, px))
    for src, px in raw_lows:  l_at.setdefault(src + pivot_k, []).append((src, px))

    bull_fvg, bear_fvg = detect_fvgs(h, l) if use_fvg else (None, None)

    bsl: deque[dict] = deque()
    ssl: deque[dict] = deque()
    trades: list[dict] = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        for src, px in h_at.get(t, []): bsl.append({"src": src, "px": px, "swept": False})
        for src, px in l_at.get(t, []): ssl.append({"src": src, "px": px, "swept": False})
        while bsl and bsl[0]["src"] < t - liquidity_age_max: bsl.popleft()
        while ssl and ssl[0]["src"] < t - liquidity_age_max: ssl.popleft()

        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"
            elif tgt_hit: exit_px = active["target"]; reason = "target"
            elif t - active["entry_bar"] >= max_hold_bars:
                exit_px = float(c[t]); reason = "timeout"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
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

        if active is None:
            # Killzone filter
            if use_killzone and not in_killzone(int(ny_min[t])):
                equity_curve[t] = equity
                continue

            bar_range = float(h[t] - l[t])
            if bar_range <= 0:
                equity_curve[t] = equity
                continue

            # --- BSL sweep (price wicks above swing high) ---
            for pool in list(bsl):
                if pool["swept"]: continue
                if h[t] <= pool["px"]: continue
                # sweep happened — check quality
                wick_above = float(h[t] - pool["px"])
                wick_pct = wick_above / bar_range
                close_in_bar = (float(c[t]) - float(l[t])) / bar_range  # 0 = at low, 1 = at high
                # close rejection: close must be in lower close_rej_pct of bar
                if mode == "reversal":
                    if c[t] >= pool["px"]: continue   # didn't reject
                    if wick_pct < wick_pct_min: continue
                    if close_in_bar > close_rej_pct: continue
                    if use_fvg:
                        # need a bearish FVG to form within last 5 bars
                        if not bear_fvg[max(0, t-5):t+1].any(): continue
                    # mark pool swept
                    pool["swept"] = True
                    # nearest unswept SSL below current close
                    target = None
                    for p in reversed(ssl):
                        if not p["swept"] and p["px"] < c[t]:
                            target = p["px"]; break
                    if target is None: continue
                    entry_px = float(c[t])
                    stop_px = float(h[t]) + buffer_pts
                    stop_pts = stop_px - entry_px
                    target_pts = entry_px - target
                    if target_pts < stop_pts * min_rr: continue
                    size = dynamic_size(stop_pts)
                    active = {"entry_bar": t, "side": "SHORT", "size": size,
                              "entry": entry_px, "stop": stop_px, "target": target}
                    break
                else:  # continuation
                    if c[t] <= pool["px"]: continue   # didn't break
                    pool["swept"] = True
                    # target: next BSL above (unswept)
                    target = None
                    for p in bsl:
                        if not p["swept"] and p["px"] > c[t]:
                            target = p["px"]; break
                    if target is None: continue
                    entry_px = float(c[t])
                    stop_px = float(pool["px"]) - buffer_pts  # just below the broken level
                    stop_pts = entry_px - stop_px
                    if stop_pts <= 0: continue
                    target_pts = target - entry_px
                    if target_pts < stop_pts * min_rr: continue
                    size = dynamic_size(stop_pts)
                    active = {"entry_bar": t, "side": "LONG", "size": size,
                              "entry": entry_px, "stop": stop_px, "target": target}
                    break

            # --- SSL sweep (price wicks below swing low) ---
            if active is None:
                for pool in list(ssl):
                    if pool["swept"]: continue
                    if l[t] >= pool["px"]: continue
                    wick_below = float(pool["px"] - l[t])
                    wick_pct = wick_below / bar_range
                    close_in_bar = (float(c[t]) - float(l[t])) / bar_range
                    if mode == "reversal":
                        if c[t] <= pool["px"]: continue
                        if wick_pct < wick_pct_min: continue
                        if close_in_bar < (1.0 - close_rej_pct): continue
                        if use_fvg:
                            if not bull_fvg[max(0, t-5):t+1].any(): continue
                        pool["swept"] = True
                        target = None
                        for p in reversed(bsl):
                            if not p["swept"] and p["px"] > c[t]:
                                target = p["px"]; break
                        if target is None: continue
                        entry_px = float(c[t])
                        stop_px = float(l[t]) - buffer_pts
                        stop_pts = entry_px - stop_px
                        target_pts = target - entry_px
                        if target_pts < stop_pts * min_rr: continue
                        size = dynamic_size(stop_pts)
                        active = {"entry_bar": t, "side": "LONG", "size": size,
                                  "entry": entry_px, "stop": stop_px, "target": target}
                        break
                    else:  # continuation
                        if c[t] >= pool["px"]: continue
                        pool["swept"] = True
                        target = None
                        for p in ssl:
                            if not p["swept"] and p["px"] < c[t]:
                                target = p["px"]; break
                        if target is None: continue
                        entry_px = float(c[t])
                        stop_px = float(pool["px"]) + buffer_pts
                        stop_pts = stop_px - entry_px
                        if stop_pts <= 0: continue
                        target_pts = entry_px - target
                        if target_pts < stop_pts * min_rr: continue
                        size = dynamic_size(stop_pts)
                        active = {"entry_bar": t, "side": "SHORT", "size": size,
                                  "entry": entry_px, "stop": stop_px, "target": target}
                        break

        equity_curve[t] = equity

    return {"trades": trades,
            "equity": pd.Series(equity_curve, index=idx),
            "final_equity": equity}


def resample(nq, freq):
    if freq == "1min": return nq
    return nq.resample(freq).agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()


def stats(trades, equity, months):
    if not trades: return {"n": 0}
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    streak = max_streak = 0
    for _, row in tdf.iterrows():
        if row["pnl_usd"] < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    total = float(tdf["pnl_usd"].sum())
    eq_dd = float((equity - equity.cummax()).min())
    return {"n": n, "wr": wins / n, "pf": gw/gl if gl > 0 else float("inf"),
            "total": total, "per": total/n, "trades_per_mo": n/months,
            "eq_maxdd": eq_dd, "max_streak": max_streak,
            "ret_per_mo": total/STARTING_BALANCE*100/months}


def main():
    print("Loading data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    months = (nq.index[-1] - nq.index[0]).days / 30.44

    timeframes = ["1min", "3min", "5min", "15min"]

    # Variants to test
    variants = [
        # (label, kw)
        ("baseline reversal",        {}),
        ("+ wick≥40%",               {"wick_pct_min": 0.40}),
        ("+ wick≥40 + close-rej",    {"wick_pct_min": 0.40, "close_rej_pct": 0.30}),
        ("+ killzone",               {"use_killzone": True}),
        ("+ killzone + FVG",         {"use_killzone": True, "use_fvg": True}),
        ("+ wick + KZ + FVG",        {"wick_pct_min": 0.40, "use_killzone": True, "use_fvg": True}),
        ("+ all filters strict",     {"wick_pct_min": 0.50, "close_rej_pct": 0.25,
                                      "use_killzone": True, "use_fvg": True}),
        ("continuation mode",        {"mode": "continuation"}),
        ("contin + killzone",        {"mode": "continuation", "use_killzone": True}),
        ("contin + wick + KZ",       {"mode": "continuation", "wick_pct_min": 0.30,
                                      "use_killzone": True}),
    ]

    all_results = []
    for tf in timeframes:
        df = resample(nq, tf)
        arr = df[["open","high","low","close"]].to_numpy()
        ny = df.index.tz_convert("America/New_York")
        ny_min = (ny.hour * 60 + ny.minute).to_numpy()
        print(f"\n--- {tf} ({len(df):,} bars) ---")
        print(f"{'Variant':<30} {'Trades':>7} {'/mo':>5} {'WR':>6} "
              f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Streak':>7} {'Ret/mo':>7}")
        for label, kw in variants:
            res = run_strategy(arr, df.index, ny_min, pivot_k=3, **kw)
            s = stats(res["trades"], res["equity"], months)
            if s["n"] < 10: continue
            pf = f"{s['pf']:>4.2f}" if s['pf'] < 99 else " inf"
            tag = ""
            if s["ret_per_mo"] >= 5.0 and s["trades_per_mo"] >= 100: tag = " ★★★"
            elif s["ret_per_mo"] >= 2.0: tag = " ★"
            elif s["ret_per_mo"] >= 0.5: tag = " ✓"
            elif s["total"] > 0: tag = " +"
            print(f"{label:<30} {s['n']:>7} {s['trades_per_mo']:>4.1f} "
                  f"{s['wr']*100:>5.1f}% {pf} ${s['per']:>+5,.0f} "
                  f"${s['total']:>+7,.0f} ${s['eq_maxdd']:>+7,.0f} "
                  f"{s['max_streak']:>6} {s['ret_per_mo']:>+5.2f}%{tag}")
            all_results.append({"tf": tf, "variant": label, **s})

    print("\n" + "=" * 110)
    print("TOP 10 ALL CONFIGS BY MONTHLY RETURN (min 50 trades)")
    print("=" * 110)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:10]:
        if r["n"] < 50: continue
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        print(f"  {r['tf']:>6} | {r['variant']:<28} | n={r['n']} "
              f"({r['trades_per_mo']:.1f}/mo) WR={r['wr']*100:.1f}% PF={pf} "
              f"${r['per']:+.0f}/tr DD${r['eq_maxdd']:+,.0f} "
              f"streak={r['max_streak']} → {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()

"""Sweep entry/target combos in REALISTIC live sim.

The simple sweep showed Entry 0.9 + Target 2.0x as the winner. But the
live sim showed breakeven — because the time gap between setup creation
and limit fill kills the edge. Let me check ALL the promising combos in
the live sim to find which (if any) actually hold up.
"""
from __future__ import annotations
import importlib, sys

# Reload the deep-retrace sim with each config to get fresh stats
import research.fib_deep_retrace_live as sim


def run_combo(entry_pct: float, target_ext: float) -> dict:
    sim.ENTRY_PCT = entry_pct
    sim.TARGET_EXT = target_ext
    import pandas as pd
    nq = pd.read_csv(sim.DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    trades, eq = sim.run_live_sim(nq)
    n = len(trades)
    if n == 0:
        return {"n": 0}
    import numpy as np
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    streak = 0; max_streak = 0
    for _, row in tdf.iterrows():
        if row["pnl_usd"] < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else:
            streak = 0
    return {
        "n": n,
        "wr": wins / n,
        "pf": gw / gl if gl > 0 else float("inf"),
        "total": float(tdf["pnl_usd"].sum()),
        "per": float(tdf["pnl_usd"].mean()),
        "maxdd": maxdd,
        "max_streak": max_streak,
    }


def main() -> None:
    combos = [
        # entry, target_ext (0 = opposite pivot, 1.0 = 1x leg beyond, etc)
        (0.7, 0.0),
        (0.7, 0.5),
        (0.7, 1.0),
        (0.8, 0.0),
        (0.8, 0.5),
        (0.8, 1.0),
        (0.85, 0.0),
        (0.85, 0.5),
        (0.85, 1.0),
        (0.9,  0.0),
        (0.9,  0.5),
        (0.9,  1.0),
        (0.92, 0.0),
        (0.92, 0.5),
        (0.92, 1.0),
        (0.95, 0.0),
        (0.95, 0.5),
        (0.95, 1.0),
        # current bot baseline
        (0.5,  0.0),
    ]
    print(f"{'Entry':>6} {'Target':>10} {'Trades':>7} {'/mo':>5} {'WR':>6} "
          f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'MaxDD':>9} {'Streak':>7}")
    print("-" * 90)
    results = []
    for e, tp in combos:
        target_label = f"{1.0 + tp:.2f}x leg"
        r = run_combo(e, tp)
        if r["n"] == 0:
            print(f"{e:>6.2f} {target_label:>10} {'0':>7}"); continue
        pf = f"{r['pf']:>4.2f}" if r['pf'] < 99 else " inf"
        print(f"{e:>6.2f} {target_label:>10} {r['n']:>7} "
              f"{r['n']/24.0:>4.1f} {r['wr']*100:>5.1f}% {pf} "
              f"${r['per']:>+5,.0f} ${r['total']:>+7,.0f} "
              f"${r['maxdd']:>+7,.0f} {r['max_streak']:>6}")
        results.append((e, tp, target_label, r))
    print()
    results.sort(key=lambda x: -x[3]["total"])
    print(f"\nTOP 5 BY TOTAL P&L:")
    for e, tp, label, r in results[:5]:
        print(f"  Entry {e:.2f}  Target {label}  →  ${r['total']:+,.0f} "
              f"(PF {r['pf']:.2f}, MaxDD ${r['maxdd']:+,.0f})")


if __name__ == "__main__":
    main()

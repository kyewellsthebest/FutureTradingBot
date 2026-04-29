"""
Recency check — split each whitelisted strategy's 8-yr trade history into
"older half" (2018-2022) and "recent half" (2023-2026) and compare P&L
per period. If a strategy was profitable historically but is dying off,
the recent-period P&L will collapse vs the older one.

Pass criteria: recent-period EV per trade ≥ 70% of older-period EV.
Otherwise the strategy is decaying and should be considered for removal.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_daily, load_intraday_1min, load_intraday_5min
from research.validate_mined_full import fixed_target_stop_simulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RECENT_CUTOFF = pd.Timestamp("2023-01-01", tz="UTC")


def main() -> int:
    print("=" * 80)
    print("RECENCY CHECK — older half (2018-2022) vs recent half (2023-2026)")
    print("=" * 80)

    print("\n[1/3] Loading data + strategies ...", flush=True)
    t0 = time.time()
    m1 = load_intraday_1min("nq")
    m5 = load_intraday_5min("nq")
    daily = load_daily("nq")

    val = json.loads((PROJECT_ROOT / "data" / "validation_results.json").read_text())
    whitelist = {k: v for k, v in val["signals"].items() if v.get("recommended")}
    print(f"  whitelist: {len(whitelist)} strategies   ({time.time()-t0:.1f}s)")

    from research.signal_generator import ALL_SIGNALS
    from research.mined_wr_signals import ALL_WR_SIGNALS
    from research.mined_v3_signals import ALL_V3_SIGNALS
    sig_objs = {}
    for s in list(ALL_SIGNALS) + list(ALL_WR_SIGNALS) + list(ALL_V3_SIGNALS):
        if hasattr(s, "name"):
            sig_objs[s.name] = s

    h1 = m1["high"].to_numpy(dtype=np.float64)
    l1 = m1["low"].to_numpy(dtype=np.float64)
    c1 = m1["close"].to_numpy(dtype=np.float64)
    h5 = m5["high"].to_numpy(dtype=np.float64)
    l5 = m5["low"].to_numpy(dtype=np.float64)
    c5 = m5["close"].to_numpy(dtype=np.float64)

    print("\n[2/3] Per-strategy old-vs-recent ...\n", flush=True)
    print(f"{'name':<32} {'side':<5} {'WR_old':>7} {'WR_new':>7} "
          f"{'EV_old':>10} {'EV_new':>10} {'verdict':>10}")
    print("-" * 95)

    results = []
    for name, info in whitelist.items():
        sig = sig_objs.get(name)
        if sig is None:
            continue
        if name.startswith("V3_") or name.startswith("WR_"):
            intraday = m1; h, l, c = h1, l1, c1
            contracts = 5
        else:
            intraday = m5; h, l, c = h5, l5, c5
            contracts = 30
        stop = float(info.get("stop_pts") or getattr(sig, "stop_pts", 15.0))
        target = float(info.get("target_pts") or getattr(sig, "target_pts", 30.0))
        max_hold = int(getattr(sig, "max_hold_bars", 80))
        side = info.get("side") or getattr(sig, "side", "LONG")

        try:
            df = sig.generate(intraday, daily)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        sig_times = pd.DatetimeIndex(df["signal_time"])
        pos = intraday.index.get_indexer(sig_times)
        all_entries = [(int(p), sig_times[i]) for i, p in enumerate(pos)
                       if p >= 0 and p < len(intraday) - max_hold - 1]
        if not all_entries:
            continue

        old_idx = [p for p, t in all_entries if t < RECENT_CUTOFF]
        new_idx = [p for p, t in all_entries if t >= RECENT_CUTOFF]
        if len(old_idx) < 30 or len(new_idx) < 30:
            continue

        old_pts = fixed_target_stop_simulate(h, l, c, old_idx, side, stop, target, max_hold)
        new_pts = fixed_target_stop_simulate(h, l, c, new_idx, side, stop, target, max_hold)
        if not old_pts or not new_pts:
            continue

        dpp = contracts * 2.0
        comm = contracts * 2.0
        old_pnl = np.asarray(old_pts) * dpp - comm
        new_pnl = np.asarray(new_pts) * dpp - comm
        old_wr = float((np.asarray(old_pts) > 0).mean())
        new_wr = float((np.asarray(new_pts) > 0).mean())
        old_ev = float(old_pnl.mean())
        new_ev = float(new_pnl.mean())

        # Verdict: is the strategy still alive in recent years?
        if old_ev <= 0 and new_ev <= 0:
            verdict = "BOTH_DEAD"
        elif old_ev > 0 and new_ev <= 0:
            verdict = "DECAYED"
        elif new_ev <= 0:
            verdict = "DECAYED"
        elif new_ev >= 0.7 * old_ev:
            verdict = "STILL_GOOD"
        elif new_ev > 0:
            verdict = "WEAKER"
        else:
            verdict = "?"
        results.append({
            "name": name, "side": side,
            "n_old": len(old_pnl), "n_new": len(new_pnl),
            "wr_old": old_wr, "wr_new": new_wr,
            "ev_old": old_ev, "ev_new": new_ev,
            "net_old": float(old_pnl.sum()), "net_new": float(new_pnl.sum()),
            "verdict": verdict,
        })
        print(f"{name:<32} {side:<5} {old_wr*100:>6.1f}% {new_wr*100:>6.1f}% "
              f"${old_ev:>+9.2f} ${new_ev:>+9.2f}  {verdict:>10}")

    # Summary
    print("\n[3/3] Summary:")
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"  Total whitelisted strategies tested: {len(results)}")
    for v in ["STILL_GOOD", "WEAKER", "DECAYED", "BOTH_DEAD"]:
        print(f"    {v:<12}: {counts.get(v, 0)}")

    # Aggregate net P&L per period
    total_old = sum(r["net_old"] for r in results)
    total_new = sum(r["net_new"] for r in results)
    print(f"\n  Combined net P&L by period (sum of independent strategy P&Ls):")
    print(f"    2018-2022 (old): ${total_old:+,.0f}")
    print(f"    2023-2026 (new): ${total_new:+,.0f}")
    print(f"    ratio new/old:   {total_new/total_old*100 if total_old else 0:.0f}%")

    out = PROJECT_ROOT / "data" / "recency_check.json"
    out.write_text(json.dumps({"results": results, "verdict_counts": counts,
                                "total_old_pnl": total_old, "total_new_pnl": total_new},
                              indent=2, default=str))
    print(f"\n  Wrote -> {out.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

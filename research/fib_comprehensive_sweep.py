"""Comprehensive entry x target Fib sweep in REALISTIC live sim.

Sweeps every entry from 0.236 to 0.886 and every target from 1.0x (opposite
pivot) to 1.618x leg extension, looking for configurations that match the
user's spec:
  - 57%+ win rate
  - 1:1.5+ reward:risk ratio
  - High trade frequency
  - Not too extreme on either axis

Stop stays at originating pivot, MIN_LEG=50, 2HH+2HL trend filter.
"""
from __future__ import annotations
import pandas as pd, numpy as np
import research.fib_deep_retrace_live as sim


def run_combo(entry_pct: float, target_ext: float, nq, trades_cache: dict) -> dict:
    """target_ext: 0 = opposite pivot (1.0x leg), 0.5 = 1.5x leg ext, etc."""
    sim.ENTRY_PCT = entry_pct
    sim.TARGET_EXT = target_ext
    trades, _ = sim.run_live_sim(nq)
    if not trades:
        return {"n": 0}
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    wins = int((tdf["pnl_usd"] > 0).sum())
    n = len(tdf)
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
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins > 0 else 0.0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0.0
    # Theoretical RR = stop_pts to target_pts ratio
    # For entry R, stop=pivot_originating, target=R+target_ext, RR = (R+target_ext-R)/(1-R) - no wait
    # For SHORT: entry at R retracement, stop at pivot_high (1-R away), target at -target_ext from pivot_low
    # stop_pts = (1-R) * leg
    # target_pts = (R + target_ext) * leg  (from entry down to target)
    # RR = target_pts / stop_pts
    theoretical_rr = (entry_pct + target_ext) / (1 - entry_pct) if entry_pct < 1 else 0
    return {
        "n": n,
        "wr": wins / n,
        "pf": gw / gl if gl > 0 else float("inf"),
        "total": float(tdf["pnl_usd"].sum()),
        "per": float(tdf["pnl_usd"].mean()),
        "maxdd": maxdd,
        "max_streak": max_streak,
        "avg_w": avg_w,
        "avg_l": avg_l,
        "rr_theory": theoretical_rr,
        "rr_actual": abs(avg_w / avg_l) if avg_l != 0 else 0,
    }


def main() -> None:
    print("Loading 1-min NQ data once...")
    nq = pd.read_csv(sim.DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    print(f"  bars: {len(nq):,}")

    # FINE-GRAINED sweep — every decimal in the user's target zone
    entries = [
        0.20, 0.236, 0.25, 0.30, 0.35, 0.382,
        0.40, 0.45, 0.50, 0.55,
    ]
    # Target extensions — fine grid from 0 to +0.60 (1.0x to 1.6x leg)
    target_exts = [
        0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.272,
        0.30, 0.35, 0.382, 0.40, 0.45, 0.50, 0.55, 0.60,
    ]

    print(f"\nSweeping {len(entries)} entries x {len(target_exts)} targets "
          f"= {len(entries) * len(target_exts)} configs")
    print(f"Each takes ~30-60s — total ~{len(entries)*len(target_exts)//2} min\n")

    results = []
    for e in entries:
        for tx in target_exts:
            r = run_combo(e, tx, nq, {})
            if r["n"] == 0: continue
            target_label = f"{1.0 + tx:.3g}x leg"
            results.append({
                "entry": e, "target_ext": tx, "target_label": target_label,
                **r,
            })
            tag = ""
            if r["wr"] >= 0.57 and r["total"] > 0 and r["rr_theory"] >= 1.5:
                tag = " ★ MATCHES SPEC"
            elif r["wr"] >= 0.57 and r["total"] > 0:
                tag = " ✓ high WR + profit"
            elif r["total"] > 0:
                tag = " profit"
            print(f"E={e:.3f} T={target_label:<10} n={r['n']:>4} "
                  f"WR={r['wr']*100:>4.1f}% PF={r['pf']:.2f} "
                  f"RR_thry={r['rr_theory']:.2f} "
                  f"${r['per']:>+5,.0f}/tr  ${r['total']:>+7,.0f}  "
                  f"DD${r['maxdd']:>+6,.0f}  streak{r['max_streak']:>3}{tag}")

    # Filter for user's spec
    print("\n" + "=" * 90)
    print("CONFIGS MATCHING USER SPEC (WR ≥ 57%, profitable, RR ≥ 1.5)")
    print("=" * 90)
    matches = [r for r in results if r["wr"] >= 0.57
               and r["total"] > 0 and r["rr_theory"] >= 1.5]
    matches.sort(key=lambda x: -x["total"])
    if not matches:
        print("  (None — spec is mathematically constrained on NQ 1-min)")
    for r in matches:
        print(f"  E={r['entry']:.3f} T={r['target_label']:<10} "
              f"n={r['n']:>4} ({r['n']/24:.1f}/mo)  "
              f"WR={r['wr']*100:.1f}% PF={r['pf']:.2f}  "
              f"$/tr=${r['per']:+,.0f}  Total=${r['total']:+,.0f}  "
              f"MaxDD=${r['maxdd']:+,.0f}  streak={r['max_streak']}")

    # All profitable configs
    print("\n" + "=" * 90)
    print("ALL PROFITABLE CONFIGS (positive total P&L)")
    print("=" * 90)
    profitable = [r for r in results if r["total"] > 0]
    profitable.sort(key=lambda x: -x["total"])
    print(f"{'Entry':>6} {'Target':>10} {'/mo':>5} {'WR':>6} {'PF':>5} "
          f"{'$/tr':>7} {'Total':>9} {'MaxDD':>9} {'Streak':>7}")
    for r in profitable[:20]:
        print(f"{r['entry']:>6.3f} {r['target_label']:>10} "
              f"{r['n']/24:>4.1f} {r['wr']*100:>5.1f}% {r['pf']:>4.2f} "
              f"${r['per']:>+5,.0f} ${r['total']:>+7,.0f} "
              f"${r['maxdd']:>+7,.0f} {r['max_streak']:>6}")

    # WR-vs-frequency tradeoff
    print("\n" + "=" * 90)
    print("HIGH-FREQUENCY CONFIGS (≥80 trades/mo) — sorted by WR")
    print("=" * 90)
    hifreq = [r for r in results if r["n"] >= 24 * 80]
    hifreq.sort(key=lambda x: -x["wr"])
    print(f"{'Entry':>6} {'Target':>10} {'/mo':>5} {'WR':>6} {'PF':>5} "
          f"{'$/tr':>7} {'Total':>9}")
    for r in hifreq[:15]:
        print(f"{r['entry']:>6.3f} {r['target_label']:>10} "
              f"{r['n']/24:>4.1f} {r['wr']*100:>5.1f}% {r['pf']:>4.2f} "
              f"${r['per']:>+5,.0f} ${r['total']:>+7,.0f}")


if __name__ == "__main__":
    main()

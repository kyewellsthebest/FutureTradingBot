"""
Ablation study: measure the contribution of each filter to the bot's
overall performance by running the combined backtest with each filter
individually disabled, then comparing to the baseline.

Tests the 6 deterministic filters that live inside combined_backtest.py:
  - bias        (3-day candle direction)
  - killzone    (time-of-day windows)
  - proximity   (distance to PDH/PDL/EQ50)
  - rr          (min risk-reward)
  - cooldown    (max trades/day, gap between)
  - vol_regime  (sizing — disabled = fixed 15pt stop)

NOT tested here (live-only filters that don't run on historical data):
  - VPIN, adverse-selection, GEX, macro, HMM regime, ML confirmation
  These require live snapshots — would need a separate synthetic
  simulator to ablate them.

Usage:
    python -m research.ablation_study           # 5-min only (fast, ~5 min/run)
    python -m research.ablation_study --full    # include WR + v3 (slower)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "ablation_results.json"
REPORT_PATH = PROJECT_ROOT / "data" / "combined_backtest_report.json"

FILTERS_TO_ABLATE = ["bias", "killzone", "proximity", "rr", "cooldown", "vol_regime"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true",
                   help="Include WR + v3 patterns (slower)")
    return p.parse_args()


def run_combined(skip_filters: list[str], include_full: bool) -> dict:
    """Run combined_backtest with given filters disabled; return parsed report."""
    cmd = [sys.executable, "-m", "research.combined_backtest", "--no-hf"]
    if not include_full:
        cmd.extend(["--no-mined", "--no-wr"])
    for f in skip_filters:
        cmd.extend(["--skip-filter", f])
    print(f"  cmd: {' '.join(cmd[2:])}", flush=True)
    t0 = time.time()
    result = subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=1800
    )
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"  FAILED in {elapsed:.0f}s")
        print(result.stderr[-2000:])
        return {"failed": True, "stderr": result.stderr[-1000:]}
    report = json.loads(REPORT_PATH.read_text())
    report["elapsed_s"] = elapsed
    # Sanitize any complex-typed fields (negative-equity edge case)
    for k in ("annualized_return", "calmar", "sharpe_daily"):
        v = report.get(k)
        if isinstance(v, str) or not isinstance(v, (int, float, type(None))):
            report[k] = -1.0
    return report


def main() -> int:
    args = parse_args()
    print("=" * 80)
    print("ABLATION STUDY — measuring each filter's individual contribution")
    print(f"  scope: {'5-min + WR + v3' if args.full else '5-min only (faster)'}")
    print("=" * 80)

    runs = []
    t0 = time.time()

    print(f"\n[1/{len(FILTERS_TO_ABLATE)+1}] BASELINE — all filters ON", flush=True)
    baseline = run_combined([], args.full)
    if baseline.get("failed"):
        return 1
    runs.append(("baseline", "all filters ON", baseline))
    print(f"   trades={baseline['trades']:>4}  wr={baseline['win_rate']*100:.1f}%  "
          f"net=${baseline['net_pnl']:+,.0f}  dd=${baseline['max_drawdown']:+,.0f}  "
          f"calmar={baseline['calmar']:.2f}  ({baseline['elapsed_s']:.0f}s)")

    for i, f in enumerate(FILTERS_TO_ABLATE, 2):
        print(f"\n[{i}/{len(FILTERS_TO_ABLATE)+1}] DISABLE — {f}", flush=True)
        r = run_combined([f], args.full)
        if r.get("failed"):
            runs.append((f"disable_{f}", f"only {f} disabled", {"failed": True}))
            continue
        runs.append((f"disable_{f}", f"only {f} disabled", r))
        delta_trades = r["trades"] - baseline["trades"]
        delta_pnl = r["net_pnl"] - baseline["net_pnl"]
        delta_dd = r["max_drawdown"] - baseline["max_drawdown"]
        sign_t = "+" if delta_trades >= 0 else ""
        sign_p = "+" if delta_pnl >= 0 else ""
        sign_d = "+" if delta_dd >= 0 else ""
        print(f"   trades={r['trades']:>4} ({sign_t}{delta_trades})  "
              f"wr={r['win_rate']*100:.1f}%  net=${r['net_pnl']:+,.0f} "
              f"({sign_p}${delta_pnl:+,.0f})  dd=${r['max_drawdown']:+,.0f} "
              f"({sign_d}${delta_dd:+,.0f})  calmar={r['calmar']:.2f}  "
              f"({r['elapsed_s']:.0f}s)")

    # Build comparison table
    print("\n" + "=" * 95)
    print("ABLATION RESULTS — impact of removing each filter")
    print("=" * 95)
    print(f"  {'config':<22} {'trades':>7} {'wr':>6} {'PF':>5} "
          f"{'net P&L':>12} {'max DD':>11} {'calmar':>7} {'verdict'}")
    print("  " + "-" * 93)
    base = baseline
    for tag, label, r in runs:
        if r.get("failed"):
            print(f"  {label:<22} (FAILED)")
            continue
        if tag == "baseline":
            verdict = "← reference"
        else:
            d_pnl = r["net_pnl"] - base["net_pnl"]
            d_trades = r["trades"] - base["trades"]
            if d_pnl > 5000:
                verdict = "✅ filter HURTS — disabling adds $%.0f" % d_pnl
            elif d_pnl < -5000:
                verdict = "❌ filter HELPS — disabling costs $%.0f" % d_pnl
            elif d_trades > 100:
                verdict = "⚪ neutral P&L, +%d trades freed" % d_trades
            else:
                verdict = "⚪ neutral / negligible"
        pf_disp = f"{r['profit_factor']:5.2f}" if r['profit_factor'] else "  inf"
        print(f"  {label:<22} {r['trades']:>7,} {r['win_rate']*100:>5.1f}% "
              f"{pf_disp} ${r['net_pnl']:>10,.0f} ${r['max_drawdown']:>9,.0f} "
              f"{r['calmar']:>7.2f}  {verdict}")
    print("=" * 95)

    # Persist
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "full" if args.full else "5-min only",
        "filters_tested": FILTERS_TO_ABLATE,
        "runs": [
            {"tag": tag, "label": label,
             "stats": {k: v for k, v in r.items()
                       if k in ("trades", "trades_per_day", "win_rate",
                                "profit_factor", "net_pnl", "final_equity",
                                "max_drawdown", "annualized_return", "calmar",
                                "rejection_breakdown", "elapsed_s")}
             if not r.get("failed") else {"failed": True}}
            for tag, label, r in runs
        ],
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Wrote -> {RESULTS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  Total runtime: {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())

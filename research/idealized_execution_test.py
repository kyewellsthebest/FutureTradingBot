"""Idealized-execution test — does the inverse-fade strategy have edge
when execution is perfect, or is the strategy itself broken?

Five variants, all on the same 60-day tick window, all using the same
strategy code (bot.pullback_strategy), differing only in execution model:

  V1 BASELINE_LIVE      : arming ON, marketable LIMIT, 0.5pt stop slip
                          (matches the current live bot model exactly)
  V2 STRICT_LIMIT_REAL  : arming ON, exact-pullback LIMIT fill,
                          0.5pt stop slip (best-case LIMIT execution)
  V3 STRICT_LIMIT_IDEAL : arming ON, exact-pullback LIMIT fill,
                          NO stop slip (no friction at all on a real-trigger
                          strategy)
  V4 NO_ARM_STRICT_REAL : NO arming (phantoms allowed), exact-pullback fill,
                          0.5pt stop slip — should reproduce the original
                          sim_honest_battery result (~$1,952/day if my
                          backtest model matches the original)
  V5 NO_ARM_IDEAL       : NO arming, exact-pullback, no stop slip — ceiling
                          for any version of this strategy on this data

Interpretation:
  V4 ~ $1,952/day  → my backtest reproduces the original. Discrepancy
                      with live is fully explained by arming + LIMIT exec.
  V2 positive      → strategy DOES have edge with ideal LIMITs.
                      The bot's execution is leaking the edge. Engineering fix.
  V2 negative      → strategy has no edge even with perfect LIMITs.
                      The bot was implementing a non-edge correctly.
  V5 negative      → strategy has no edge under any conditions.
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override stop-slip via env so each variant can opt out
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")

import research.comprehensive_backtest as cb
from research.comprehensive_backtest import VariantConfig

# Patch STOP_SLIP_PTS dynamically per-variant by monkey-patching the module
# constant. We run sequentially to allow this.
ORIG_STOP_SLIP = cb.STOP_SLIP_PTS  # 0.5


def make_variants():
    V = []
    V.append(VariantConfig("V1_BASELINE_LIVE",
                            arming=True, marketable_limit=True))
    V.append(VariantConfig("V2_STRICT_REAL",
                            arming=True, marketable_limit=False))
    V.append(VariantConfig("V3_STRICT_IDEAL",
                            arming=True, marketable_limit=False))   # stop slip 0
    V.append(VariantConfig("V4_NOARM_STRICT_REAL",
                            arming=False, marketable_limit=False))
    V.append(VariantConfig("V5_NOARM_IDEAL",
                            arming=False, marketable_limit=False))  # stop slip 0
    return V


def main():
    print("=" * 72)
    print("Idealized-execution test")
    print("=" * 72)

    # Run all variants on the same 60-day window. The harness already
    # streams the tick CSV once and updates all variant states per tick.
    # We need separate runs for variants that need different STOP_SLIP_PTS,
    # so we split into two passes: slip=0.5 group {V1,V2,V4} and
    # slip=0.0 group {V3,V5}.
    variants_slip_real = [v for v in make_variants()
                          if v.name in ("V1_BASELINE_LIVE",
                                         "V2_STRICT_REAL",
                                         "V4_NOARM_STRICT_REAL")]
    variants_slip_ideal = [v for v in make_variants()
                           if v.name in ("V3_STRICT_IDEAL",
                                          "V5_NOARM_IDEAL")]

    all_results = {}

    print("\n--- Pass 1: real stop slip (0.5pt) ---")
    cb.STOP_SLIP_PTS = 0.5
    offset_60 = cb.get_60d_offset()
    print(f"60-day offset: {offset_60:,}")
    res = cb.run_battery(variants_slip_real,
                          start_offset=offset_60,
                          label="REAL_SLIP")
    all_results.update(res)

    print("\n--- Pass 2: idealised (no stop slip) ---")
    cb.STOP_SLIP_PTS = 0.0
    res = cb.run_battery(variants_slip_ideal,
                          start_offset=offset_60,
                          label="IDEAL_NOSLIP")
    all_results.update(res)

    cb.STOP_SLIP_PTS = ORIG_STOP_SLIP  # restore

    # Pretty print summary
    print("\n" + "=" * 72)
    print("RESULTS")
    print("=" * 72)
    rows = []
    for name in ("V1_BASELINE_LIVE", "V2_STRICT_REAL", "V3_STRICT_IDEAL",
                  "V4_NOARM_STRICT_REAL", "V5_NOARM_IDEAL"):
        if name not in all_results:
            print(f"  {name}: MISSING")
            continue
        summary = cb.summarize(all_results[name])
        rows.append(summary)
    if rows:
        print(f"{'Variant':<22} {'Trades':>8} {'WR':>6} {'P&L':>10} {'$/day':>9} {'$/trade':>9} {'DD':>9}")
        for s in rows:
            print(f"{s['name']:<22} {s['trades']:>8} {s['wr']:>5.1f}% "
                  f"${s['pnl']:>8.0f} ${s['per_day']:>7.2f} ${s['per_trade']:>7.2f} "
                  f"${s['max_dd']:>7.0f}")

    print("\nINTERPRETATION GUIDE:")
    print("  V4 (no arming, strict LIMIT, real slip) should match the")
    print("    original sim_honest_battery's $1,952/day claim if my model")
    print("    is faithful to it.")
    print("  V2 (arming on, strict LIMIT, real slip) is the strategy with")
    print("    ideal LIMIT execution. If POSITIVE, strategy has edge — bot")
    print("    needs better LIMITs. If NEGATIVE, strategy has no edge.")
    print("  V3 vs V2 shows how much the stop-MARKET slip costs.")
    print("  V5 is the ceiling: if even V5 is negative, the strategy is")
    print("    structurally negative.")
    print("  V1 vs V2 shows how much the marketable LIMIT exec costs.")

    return all_results


if __name__ == "__main__":
    main()

"""Test V4 with the Lucid microscalp guard DISABLED.

The original sim_honest_battery does NOT enforce MIN_TARGET_HOLD_SECONDS.
The comprehensive_backtest harness does — it requires 10 seconds of hold
before a target can fire. On tick data this materially changes results:
sub-10s target hits become "wait then maybe re-trigger" cases that often
end up at stop or timeout instead.

Compare:
  V4_W_MICROSCALP_GUARD  : as before (+$144/day on 60d)
  V4_NO_MICROSCALP_GUARD : without guard (should be closer to sim's
                            +$3,008/day)
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

# Disable the microscalp guard globally for this run
cb.MIN_TARGET_HOLD_SECONDS = 0
# Real stop slip
cb.STOP_SLIP_PTS = 0.5

# Run only the variant of interest: no arming + strict LIMIT (matches V4)
V = [
    VariantConfig("V4_NO_MICROSCALP",
                   arming=False, marketable_limit=False),
]

offset_60 = cb.get_60d_offset()
print(f"60-day offset: {offset_60:,}")
results = cb.run_battery(V, start_offset=offset_60,
                         label="V4_NO_MICROSCALP")

print("\n" + "=" * 72)
print("RESULTS — V4 with no microscalp guard")
print("=" * 72)
for name, state in results.items():
    s = cb.summarize(state)
    print(f"{s['name']:<24} trades={s['trades']:>6} WR={s['wr']:.1f}% "
          f"P&L=${s['pnl']:+,.0f} $/day=${s['per_day']:+,.2f} "
          f"$/trade=${s['per_trade']:+,.2f} DD=${s['max_dd']:,.0f}")
print()
print("Compare:")
print("  Original sim on same 60d: +$3,009/day, WR 54%, 16,197 trades")
print("  V4 WITH microscalp guard: +$144/day, WR ~36%, 12,078 trades")
print("  V4 NO microscalp guard  : ABOVE")
print()
print("If V4_NO_MICROSCALP ~ +$3,000/day → microscalp guard was the bug.")
print("If V4_NO_MICROSCALP ~ +$500/day  → only part of the gap.")

"""V4 with ASK/BID trigger (matching sim_honest_battery) instead of MID.

The sim uses ASK <= entry for orig=LONG (inverse SHORT) trades and
BID >= entry for orig=SHORT (inverse LONG) trades. My harness uses MID
for both.

If swapping to ASK/BID closes the gap with sim (which showed +$3,008/day
on this 60d window), the trigger price was the bug.
"""
from __future__ import annotations
import os, sys, numpy as np
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

# Disable microscalp guard
cb.MIN_TARGET_HOLD_SECONDS = 0
cb.STOP_SLIP_PTS = 0.5

# Monkey-patch _check_setup_arm_trigger to use ASK or BID based on
# approach side, instead of MID.
_orig_check = cb._check_setup_arm_trigger


def _check_setup_arm_trigger_askbid(setup, mid_arr, start_idx, arming,
                                       bid_arr=None, ask_arr=None):
    """Same as original but uses ask/bid for trigger when provided."""
    approach = setup.orig_side or setup.side
    pe = setup.pullback_entry
    n_remain = len(mid_arr) - start_idx
    if n_remain <= 0:
        return None
    # arming side uses MID still (irrelevant when arming is off)
    if arming and not setup.entry_armed:
        if approach == "LONG":
            arm = mid_arr[start_idx:] > pe
        else:
            arm = mid_arr[start_idx:] < pe
        if not arm.any():
            return None
        arm_idx = int(np.argmax(arm))
        setup.entry_armed = True
        trig_start = arm_idx + 1
    else:
        trig_start = 0
    if trig_start >= n_remain:
        return None
    # TRIGGER USES ASK/BID
    if approach == "LONG":
        # orig=LONG (inverse SHORT trade): need ASK to drop to entry
        if ask_arr is None:
            return None
        seg = ask_arr[start_idx + trig_start:]
        trig = seg <= pe
    else:
        # orig=SHORT (inverse LONG trade): need BID to rise to entry
        if bid_arr is None:
            return None
        seg = bid_arr[start_idx + trig_start:]
        trig = seg >= pe
    if not trig.any():
        return None
    return start_idx + trig_start + int(np.argmax(trig))


# Re-patch the segment processor to pass bid_arr / ask_arr to our trigger.
_orig_process_segment = cb._process_segment


def _process_segment_patched(vs, bid_arr, ask_arr, mid_arr, ts_ns_arr,
                               seg_start, seg_end):
    """Same as original but passes bid/ask to the trigger check."""
    cfg = vs.cfg
    sticky_blocked = False
    if getattr(vs, 'daily_dd_tripped', False):
        sticky_blocked = True
    pause_attr = getattr(vs, 'pause_until_ts', None) or getattr(vs, 'cb_pause_until_ts_ns', None)
    if pause_attr is not None:
        pause_us = pause_attr
        if int(ts_ns_arr[seg_end - 1]) <= pause_us:
            sticky_blocked = True
    cur = seg_start
    while cur < seg_end:
        if vs.active_trade is not None:
            exit_idx, exit_px, exit_reason = cb._check_trade_exit_vectorized(
                vs.active_trade, bid_arr[:seg_end], ask_arr[:seg_end],
                ts_ns_arr[:seg_end], cur)
            if exit_idx is None:
                return
            cb._record_trade_exit(vs, int(ts_ns_arr[exit_idx]),
                                    exit_px, exit_reason)
            cur = exit_idx + 1
            continue
        if sticky_blocked:
            return
        if not vs.pending_setups:
            return
        now_ns = ts_ns_arr[cur]
        cutoff_ns = now_ns - cb.MAX_WAIT_SECS * cb.US_PER_SEC
        vs.pending_setups = [
            s for s in vs.pending_setups
            if (not s.used)
            and (s.detected_at.timestamp() * cb.US_PER_SEC > cutoff_ns)
        ]
        if not vs.pending_setups:
            return
        earliest_idx = None
        earliest_setup = None
        for setup in vs.pending_setups:
            if setup.used:
                continue
            fi = _check_setup_arm_trigger_askbid(
                setup, mid_arr[:seg_end], cur, cfg.arming,
                bid_arr=bid_arr[:seg_end], ask_arr=ask_arr[:seg_end])
            if fi is not None and (earliest_idx is None or fi < earliest_idx):
                earliest_idx = fi
                earliest_setup = setup
        if earliest_idx is None:
            return
        opened = cb._try_open_trade(vs, earliest_setup, earliest_idx,
                                      bid_arr, ask_arr, ts_ns_arr)
        if not opened:
            earliest_setup.used = True
            cur = earliest_idx + 1
            continue
        cur = earliest_idx + 1


cb._process_segment = _process_segment_patched

# Run only the V4 variant
V = [VariantConfig("V4_ASKBID_TRIGGER",
                    arming=False, marketable_limit=False)]

offset_60 = cb.get_60d_offset()
print(f"60-day offset: {offset_60:,}")
results = cb.run_battery(V, start_offset=offset_60,
                         label="V4_ASKBID_TRIGGER")

print()
print("=" * 72)
print("RESULTS — V4 with ASK/BID trigger (matches sim_honest_battery)")
print("=" * 72)
for name, state in results.items():
    s = cb.summarize(state)
    print(f"{s['name']:<24} trades={s['trades']:>6} WR={s['wr']:.1f}% "
          f"P&L=${s['pnl']:+,.0f} $/day=${s['per_day']:+,.2f} "
          f"$/trade=${s['per_trade']:+,.2f} DD=${s['max_dd']:,.0f}")
print()
print("Compare:")
print("  Original sim_honest_battery same 60d: +$3,009/day, WR 54.4%, 16,197 trades")
print("  V4 ORIGINAL (MID + microscalp) :     +$144/day,   WR ~36%, 12,078 trades")
print("  V4 NO MICROSCALP (MID trigger) :     +$206/day,   WR ~37%, 12,110 trades")
print("  V4 ASKBID + NO MICROSCALP (this) :   ABOVE")

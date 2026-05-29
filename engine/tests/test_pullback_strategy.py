"""Golden-file tests for the PullbackImpulse strategy.

These tests pin the strategy's behaviour to specific bar inputs and
expected outputs. If anyone changes the formula, these break. That's the
point -- "rule mismatch audit" the user asked for.

Each test specifies:
  - the 4-bar OHLC input
  - the expected Setup (or None)
  - which rule it's verifying

Run with: python -m engine.tests.test_pullback_strategy
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.strategies.pullback import PullbackImpulse, DEFAULTS
from engine.types import Side


def _bars_from_ohlc(rows):
    """rows = list of (open, high, low, close) tuples for sequential 1-min bars."""
    base = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    idx = pd.date_range(base, periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame({
        "open":  [r[0] for r in rows],
        "high":  [r[1] for r in rows],
        "low":   [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "volume": [100] * len(rows),
    }, index=idx)


PASS = 0
FAIL = 0
def assert_equal(actual, expected, msg=""):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  ✓ {msg}")
    else:
        FAIL += 1
        print(f"  ✗ {msg}: expected {expected!r} got {actual!r}")

def assert_close(actual, expected, tol=0.01, msg=""):
    global PASS, FAIL
    if abs(actual - expected) <= tol:
        PASS += 1
        print(f"  ✓ {msg} ({actual:.2f} ≈ {expected:.2f})")
    else:
        FAIL += 1
        print(f"  ✗ {msg}: expected {expected:.2f}±{tol} got {actual:.2f}")


# ---------------------------------------------------------------------------
# TEST 1: Strong UP impulse → LONG setup at 0.618 retrace
# ---------------------------------------------------------------------------
def test_strong_up_impulse_fires_long():
    print("\n[TEST] strong UP impulse (10pt over 4 bars) fires LONG")
    # 4 bars: open at 20000, close at 20010 (10pt up impulse).
    # imp_high=20011, imp_low=20000 → range=11 → 0.618 retrace down from high = 20011 - 6.8 = 20004.2
    bars = _bars_from_ohlc([
        (20000, 20002, 19999, 20002),  # bar 0: open=20000
        (20002, 20005, 20001, 20004),  # bar 1
        (20004, 20008, 20003, 20007),  # bar 2
        (20007, 20011, 20006, 20010),  # bar 3 close=20010
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert setup is not None, "expected a setup, got None"
    assert_equal(setup.side, Side.LONG, "side is LONG")
    assert_equal(setup.impulse_pts, 10.0, "impulse_pts = 10.0")
    assert_equal(setup.impulse_high, 20011.0, "imp_high")
    assert_equal(setup.impulse_low, 19999.0, "imp_low")
    # range = 12; 0.618 retrace = 7.416; entry = 20011 - 7.416 = 20003.58
    assert_close(setup.entry_price, 20003.58, msg="entry @ 0.618 retrace")
    assert_close(setup.stop_price, 20003.58 - 6.0, msg="stop = entry - 6")
    assert_close(setup.target_price, 20003.58 + 12.0, msg="target = entry + 12")


# ---------------------------------------------------------------------------
# TEST 2: Strong DOWN impulse → SHORT setup
# ---------------------------------------------------------------------------
def test_strong_down_impulse_fires_short():
    print("\n[TEST] strong DOWN impulse (10pt over 4 bars) fires SHORT")
    bars = _bars_from_ohlc([
        (20010, 20011, 20008, 20008),  # bar 0: open=20010
        (20008, 20009, 20005, 20006),
        (20006, 20007, 20002, 20003),
        (20003, 20003, 19999, 20000),  # bar 3 close=20000
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert setup is not None, "expected a setup, got None"
    assert_equal(setup.side, Side.SHORT, "side is SHORT")
    assert_equal(setup.impulse_pts, -10.0, "impulse_pts = -10")
    assert_equal(setup.impulse_high, 20011.0, "imp_high")
    assert_equal(setup.impulse_low, 19999.0, "imp_low")
    # range = 12; 0.618 retrace from low: 19999 + 7.416 = 20006.42
    assert_close(setup.entry_price, 20006.42, msg="entry @ 0.618 retrace")
    assert_close(setup.stop_price, 20006.42 + 6.0, msg="stop = entry + 6")
    assert_close(setup.target_price, 20006.42 - 12.0, msg="target = entry - 12")


# ---------------------------------------------------------------------------
# TEST 3: Weak impulse (< 5pt) → no setup
# ---------------------------------------------------------------------------
def test_weak_impulse_no_setup():
    print("\n[TEST] weak impulse (3pt over 4 bars) returns None")
    bars = _bars_from_ohlc([
        (20000, 20001, 19999, 20001),
        (20001, 20002, 20000, 20001),
        (20001, 20002, 20000, 20002),
        (20002, 20003, 20001, 20003),  # close-open = 3pt
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert_equal(setup, None, "setup is None")


# ---------------------------------------------------------------------------
# TEST 4: Exactly at threshold (5.0 pt) → fires
# ---------------------------------------------------------------------------
def test_exact_threshold_fires():
    print("\n[TEST] exactly 5.0pt impulse fires")
    bars = _bars_from_ohlc([
        (20000, 20001, 19999, 20001),
        (20001, 20002, 20000, 20002),
        (20002, 20003, 20001, 20003),
        (20003, 20006, 20002, 20005),  # close-open = 5.0
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert setup is not None, f"expected setup at 5pt threshold, got None"
    assert_equal(setup.side, Side.LONG, "side")
    assert_equal(setup.impulse_pts, 5.0, "impulse_pts")


# ---------------------------------------------------------------------------
# TEST 5: Below threshold (4.9 pt) → no setup
# ---------------------------------------------------------------------------
def test_just_below_threshold():
    print("\n[TEST] 4.99pt impulse does NOT fire")
    bars = _bars_from_ohlc([
        (20000, 20001, 19999, 20001),
        (20001, 20002, 20000, 20002),
        (20002, 20003, 20001, 20003),
        (20003, 20006, 20002, 20004.99),  # close-open = 4.99
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert_equal(setup, None, "below threshold = no setup")


# ---------------------------------------------------------------------------
# TEST 6: Strategy uses ONLY the last 4 bars (not the whole history)
# ---------------------------------------------------------------------------
def test_only_last_4_bars_used():
    print("\n[TEST] strategy ignores bars older than the last 4")
    bars = _bars_from_ohlc([
        (20000, 20001, 19999, 20001),  # ancient
        (20001, 20020, 19990, 20015),  # ancient bar with huge range -- should NOT be used
        (20015, 20016, 20014, 20015),  # 4 bars back: open=20015
        (20015, 20016, 20014, 20015),
        (20015, 20016, 20014, 20015),
        (20015, 20017, 20014, 20017),  # close 20017 - open 20015 (from 4 bars back) = 2pt
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert_equal(setup, None,
                  "only last 4 bars considered; ancient huge bar ignored")


# ---------------------------------------------------------------------------
# TEST 7: Params override defaults (target=18 instead of 12)
# ---------------------------------------------------------------------------
def test_params_override():
    print("\n[TEST] params override default TARGET_PTS")
    bars = _bars_from_ohlc([
        (20000, 20001, 19999, 20001),
        (20001, 20002, 20000, 20002),
        (20002, 20003, 20001, 20003),
        (20003, 20011, 20002, 20010),  # 10pt up
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(),
                            {"TARGET_PTS": 18.0, "STOP_PTS": 4.0})
    assert setup is not None
    # range = 20011 - 19999 = 12; 0.618 retrace = 7.416; entry = 20011 - 7.416 = 20003.58
    assert_close(setup.target_price, setup.entry_price + 18.0,
                  msg="target_pts=18 honored")
    assert_close(setup.stop_price, setup.entry_price - 4.0,
                  msg="stop_pts=4 honored")


# ---------------------------------------------------------------------------
# TEST 8: Zero-range bars (gapped/synthetic) handled safely
# ---------------------------------------------------------------------------
def test_zero_range_safe():
    print("\n[TEST] zero impulse range returns None safely")
    bars = _bars_from_ohlc([
        (20000, 20000, 20000, 20000),
        (20000, 20000, 20000, 20000),
        (20000, 20000, 20000, 20000),
        (20000, 20000, 20000, 20000),
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert_equal(setup, None, "zero-range bars produce no setup")


# ---------------------------------------------------------------------------
# TEST 9: Less than 4 bars → None (need full window)
# ---------------------------------------------------------------------------
def test_insufficient_bars():
    print("\n[TEST] insufficient history returns None")
    bars = _bars_from_ohlc([
        (20000, 20002, 19999, 20002),
        (20002, 20005, 20001, 20005),
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert_equal(setup, None, "< 4 bars produces no setup")


# ---------------------------------------------------------------------------
# TEST 10: Setup's impulse calculation matches bot/pullback_strategy exactly
# (close[-1] - open[0] across the last 4 bars). This is the formula the
# bot uses; we are pinning it.
# ---------------------------------------------------------------------------
def test_impulse_formula_pinned():
    print("\n[TEST] impulse = close[-1] - open[0] (NOT close[-1] - close[-4])")
    # Construct a case where the two formulas would give different answers.
    # close-vs-open: open=20000, close=20008  → 8pt UP (FIRES)
    # close-vs-close: close[0]=20015, close[3]=20008 → -7pt (DOWN)
    bars = _bars_from_ohlc([
        (20000, 20020, 19990, 20015),  # open=20000, close=20015
        (20015, 20020, 20005, 20010),
        (20010, 20015, 20005, 20009),
        (20009, 20012, 20004, 20008),  # close=20008
    ])
    s = PullbackImpulse()
    setup = s.detect_setup(bars, bars.index[-1].to_pydatetime(), {})
    assert setup is not None, "should fire LONG via close[-1]-open[0] = +8pt"
    assert_equal(setup.side, Side.LONG, "side = LONG (UP impulse)")
    assert_equal(setup.impulse_pts, 8.0, "impulse_pts = +8 (open→close formula)")


def main():
    print("=" * 60)
    print("Pullback Impulse strategy: golden-file tests")
    print("=" * 60)
    print(f"Defaults under test: {DEFAULTS}")
    test_strong_up_impulse_fires_long()
    test_strong_down_impulse_fires_short()
    test_weak_impulse_no_setup()
    test_exact_threshold_fires()
    test_just_below_threshold()
    test_only_last_4_bars_used()
    test_params_override()
    test_zero_range_safe()
    test_insufficient_bars()
    test_impulse_formula_pinned()
    print("\n" + "=" * 60)
    print(f"Result: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()

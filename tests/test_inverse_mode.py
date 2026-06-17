"""Unit tests for INVERSE pullback strategy mode (STRAT_INVERT=1).

These exercise bot.pullback_strategy.detect_pullback_setup and the
FibSetup.is_filled approach geometry, which are the two integration
points where the original "go with the impulse" logic and the inverse
"fade the impulse" logic diverge.

Run: pytest tests/test_inverse_mode.py
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

import bot.pullback_strategy as ps


def _make_bars(rows):
    """rows: list of (o, h, l, c). Returns DataFrame indexed by ts."""
    base = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows],
        index=pd.DatetimeIndex(
            [base.replace(minute=i) for i in range(len(rows))], name="ts"),
    )
    return df


# 4-bar UP impulse: open 22000, close 22010, range 21999..22011.
_UP_BARS = _make_bars([
    (22000, 22002, 21999, 22001),
    (22001, 22005, 22000, 22004),
    (22004, 22008, 22003, 22007),
    (22007, 22011, 22006, 22010),
])

# 4-bar DOWN impulse: open 22010, close 22000, range 21999..22011.
_DOWN_BARS = _make_bars([
    (22010, 22011, 22008, 22009),
    (22009, 22010, 22005, 22006),
    (22006, 22007, 22001, 22002),
    (22002, 22003, 21999, 22000),
])
_NOW = datetime(2026, 6, 1, 14, 5, tzinfo=timezone.utc)


def test_original_up_impulse_long():
    """INVERT=False on UP impulse → LONG at 0.618 retracement."""
    s = ps.detect_pullback_setup(
        _UP_BARS, _NOW,
        params={"INVERT": False, "PULLBACK_PCT": 0.618,
                "STOP_PTS": 6, "TARGET_PTS": 12, "IMPULSE_PTS": 5},
    )
    assert s is not None
    assert s.side == "LONG"
    assert s.orig_side == "LONG"
    assert s.pullback_entry == 22003.50
    assert s.stop_px_val == 21997.75
    assert s.target_px_val == 22015.75


def test_inverse_up_impulse_short():
    """INVERT=True on UP impulse → SHORT at 0.236 retracement (fade)."""
    s = ps.detect_pullback_setup(
        _UP_BARS, _NOW,
        params={"INVERT": True, "PULLBACK_PCT": 0.236,
                "STOP_PTS": 10, "TARGET_PTS": 20, "IMPULSE_PTS": 5},
    )
    assert s is not None
    assert s.side == "SHORT"            # trade side: flipped
    assert s.orig_side == "LONG"        # approach: UP impulse
    assert s.pullback_entry == 22008.00 # 22011 - 0.236*12 = 22008.168 -> floor 22008.00
    assert s.stop_px_val == 22018.00    # SHORT stop ABOVE entry: 22008+10=22018
    assert s.target_px_val == 21988.00  # SHORT target BELOW entry: 22008-20=21988


def test_inverse_down_impulse_long():
    """INVERT=True on DOWN impulse → LONG at 0.236 retracement (fade)."""
    s = ps.detect_pullback_setup(
        _DOWN_BARS, _NOW,
        params={"INVERT": True, "PULLBACK_PCT": 0.236,
                "STOP_PTS": 10, "TARGET_PTS": 20, "IMPULSE_PTS": 5},
    )
    assert s is not None
    assert s.side == "LONG"             # trade side: flipped
    assert s.orig_side == "SHORT"       # approach: DOWN impulse
    assert s.pullback_entry == 22002.00 # 21999 + 0.236*12 = 22001.832 -> ceil 22002.00
    assert s.stop_px_val == 21992.00    # LONG stop BELOW entry: 22002-10=21992
    assert s.target_px_val == 22022.00  # LONG target ABOVE entry: 22002+20=22022


def test_is_filled_uses_orig_side_for_approach():
    """For inverse LONG (after DOWN impulse), bar must reach entry from
    BELOW (high >= entry), not from above (low <= entry)."""
    s = ps.detect_pullback_setup(
        _DOWN_BARS, _NOW,
        params={"INVERT": True, "PULLBACK_PCT": 0.236,
                "STOP_PTS": 10, "TARGET_PTS": 20, "IMPULSE_PTS": 5},
    )
    assert s is not None
    # Bar high 22001 < entry 22002 -> not yet filled.
    not_yet = pd.Series({"open": 21998, "high": 22001, "low": 21997, "close": 21999})
    assert s.is_filled(not_yet) is False
    # Bar high 22003 >= entry -> filled.
    filled = pd.Series({"open": 21998, "high": 22003, "low": 21997, "close": 22002})
    assert s.is_filled(filled) is True


def test_subimpulse_below_threshold_returns_none():
    """4-bar net move below IMPULSE_PTS -> no setup."""
    # 2pt net (< 5pt threshold)
    tiny_bars = _make_bars([
        (22000, 22001, 21999, 22000),
        (22000, 22001, 21999, 22001),
        (22001, 22002, 22000, 22001),
        (22001, 22002, 22000, 22002),
    ])
    s = ps.detect_pullback_setup(
        tiny_bars, _NOW,
        params={"INVERT": True, "PULLBACK_PCT": 0.236, "IMPULSE_PTS": 5},
    )
    assert s is None

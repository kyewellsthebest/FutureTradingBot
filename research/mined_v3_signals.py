"""
V3 mined patterns — TEMPORARILY EMPTY.

The original 209 patterns in this file were mined using
research/pattern_miner_v3.py + research/signal_generator.py before the
look-ahead-leak fix (2026-05-04). Those patterns' apparent edge came
from `_attach_prev_day_levels` accidentally returning SAME-DAY H/L/C
as "previous day" data — i.e. the features peeked into the future.

Re-mining with the leak-fixed features produced ZERO surviving patterns
under the original miner's 5-test gauntlet (train_wr ≥ 56%, cpcv_mean
≥ 53%, cpcv_min ≥ 50%, n ≥ trades-per-week × 52). NQ's natural base
WR for triple-barrier 1:2 RR over 8 yrs is 20-28% — well below the
33-42% break-even.

This file is intentionally empty until honest patterns are mined and
emitted. The engine will gracefully skip V3 signals (whitelist filter
ignores names that don't exist as classes here).

When mining produces survivors:
    python -m research.pattern_miner_v3 --emit ...
will overwrite this file with the new classes.
"""
from __future__ import annotations

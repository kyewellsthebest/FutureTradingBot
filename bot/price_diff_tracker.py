"""Polygon vs Tradovate live price diff tracker.

The bot's strategy fires on Polygon market data; the broker fills on
Tradovate market data. If those two feeds disagree -- even by 0.25pt --
the strategy may detect a pullback touch that the broker never saw, or
miss one the broker did see.

This module collects matched (poly_px, trad_px, ts) samples whenever
the bot has both feeds live and exposes a summary for the diagnostic
bundle.

Usage from the WS handler / monitor:
    from bot.price_diff_tracker import record_sample
    record_sample(poly_px=29683.50, trad_px=29683.75)

Read from dashboard:
    from bot.price_diff_tracker import get_price_diff_history
    history = get_price_diff_history()
"""
from __future__ import annotations

import time
from collections import deque
from typing import Optional

# Bounded so steady-state memory stays modest. ~2 kB per sample with
# extras. At maxlen=2000 that's ~4 MB worst case.
_SAMPLES: "deque[dict]" = deque(maxlen=2000)


def record_sample(poly_px: Optional[float],
                   trad_px: Optional[float]) -> None:
    if poly_px is None or trad_px is None:
        return
    diff = float(trad_px) - float(poly_px)
    _SAMPLES.append({
        "ts": time.time(),
        "poly": round(float(poly_px), 4),
        "trad": round(float(trad_px), 4),
        "diff": round(diff, 4),
    })


def get_price_diff_history() -> dict:
    """Return summary stats plus the most recent samples."""
    samples = list(_SAMPLES)
    if not samples:
        return {"n": 0, "samples": []}
    diffs = [s["diff"] for s in samples]
    diffs_sorted = sorted(diffs)
    n = len(diffs_sorted)

    def _pct(p: float) -> float:
        idx = min(n - 1, int(n * p / 100))
        return round(diffs_sorted[idx], 4)

    mean = sum(diffs) / n
    return {
        "n": n,
        "mean_diff": round(mean, 4),
        "abs_mean": round(sum(abs(d) for d in diffs) / n, 4),
        "min_diff": round(min(diffs), 4),
        "max_diff": round(max(diffs), 4),
        "p05": _pct(5),
        "p50": _pct(50),
        "p95": _pct(95),
        "recent_50": samples[-50:],
    }

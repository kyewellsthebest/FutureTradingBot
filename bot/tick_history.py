"""Bounded ring buffer of recent ticks the bot saw.

Stored as compact dicts so the diagnostic bundle can replay exactly
what the strategy was looking at when it decided to fire (or not). The
PriceMonitor (or any tick source) calls record_tick on every update.

Tick fields:
    ts   -- epoch seconds (float)
    px   -- last trade
    bid  -- best bid (optional)
    ask  -- best ask (optional)
    src  -- "polygon" | "tradovate" | "other"

Bounded at 5000 entries -- ~20 minutes of 4 Hz ticks. Memory ~500 kB.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Optional

_TICKS: "deque[dict]" = deque(maxlen=5000)

# Latest tick per source -- read by the price-diff tracker to compare
# Polygon vs Tradovate without coupling those modules directly.
_LATEST_BY_SRC: dict = {}


def latest_by_src(src: str) -> Optional[dict]:
    return _LATEST_BY_SRC.get(src)


def record_tick(px: float, *,
                 bid: Optional[float] = None,
                 ask: Optional[float] = None,
                 src: str = "polygon") -> None:
    rec = {
        "ts": time.time(),
        "px": round(float(px), 4),
        "bid": round(float(bid), 4) if bid is not None else None,
        "ask": round(float(ask), 4) if ask is not None else None,
        "src": src,
    }
    _TICKS.append(rec)
    _LATEST_BY_SRC[src] = rec


def get_tick_history() -> dict:
    ticks = list(_TICKS)
    if not ticks:
        return {"n": 0, "ticks": []}
    # Compute basic spread stats if bid+ask are present
    spreads = [t["ask"] - t["bid"] for t in ticks
                if t.get("bid") is not None and t.get("ask") is not None]
    summary = {
        "n": len(ticks),
        "ts_start": ticks[0]["ts"],
        "ts_end": ticks[-1]["ts"],
        "px_first": ticks[0]["px"],
        "px_last": ticks[-1]["px"],
        "px_min": min(t["px"] for t in ticks),
        "px_max": max(t["px"] for t in ticks),
    }
    if spreads:
        summary["spread_n"] = len(spreads)
        summary["spread_mean"] = round(sum(spreads) / len(spreads), 4)
        summary["spread_max"] = round(max(spreads), 4)
    # Only the most recent 500 ticks go in the bundle -- enough to
    # replay an entry/exit moment without bloating the file.
    return {**summary, "ticks_tail": ticks[-500:]}

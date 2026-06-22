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
    # Carry forward the last known bid/ask for this source when the
    # incoming record only has a trade price. Polygon delivers T (trade)
    # and Q (quote) on separate events; without this, a trade tick
    # overwrites the most recent quote and the strategy loses its bid/
    # ask reference. Quote events still update bid/ask explicitly.
    prev = _LATEST_BY_SRC.get(src)
    eff_bid = bid
    eff_ask = ask
    if eff_bid is None and prev is not None:
        eff_bid = prev.get("bid")
    if eff_ask is None and prev is not None:
        eff_ask = prev.get("ask")
    rec = {
        "ts": time.time(),
        "px": round(float(px), 4),
        "bid": round(float(eff_bid), 4) if eff_bid is not None else None,
        "ask": round(float(eff_ask), 4) if eff_ask is not None else None,
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


def get_ticks_in_window(start_ts: float, end_ts: float) -> list:
    """Return all buffered ticks whose ts falls within [start_ts, end_ts].

    Used by the per-trade tick snapshot recorder so each completed
    trade carries its surrounding 3-min-before / 3-min-after price
    path into the diagnostic bundle. Operates on the full 5000-tick
    deque, not the bundle-trimmed ticks_tail.
    """
    out = []
    for t in _TICKS:
        ts = t.get("ts", 0)
        if ts < start_ts:
            continue
        if ts > end_ts:
            continue
        out.append(t)
    return out

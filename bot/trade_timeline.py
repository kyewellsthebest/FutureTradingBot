"""Per-trade event timeline.

Records every state transition for each trade with timestamps so we
can reconstruct exactly when each thing happened: setup detected,
entry armed, placeoso sent, parent acked, bracket child status,
fill confirmed, exit detected, paper closed.

Stored by setup_ref (the unique string the bot tags every order with).
A simple in-memory dict bounded by a deque of most-recent refs.

Read from dashboard:
    from bot.trade_timeline import get_timeline_all, get_timeline
"""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Optional

_MAX_TRADES = 200  # ~50 trade-days of memory
_TIMELINES: "OrderedDict[str, list[dict]]" = OrderedDict()
_LOCK = Lock()


def add_event(setup_ref: Optional[str], event: str, **fields) -> None:
    if not setup_ref:
        return
    with _LOCK:
        if setup_ref not in _TIMELINES:
            _TIMELINES[setup_ref] = []
            # Bound memory: drop oldest when over cap
            while len(_TIMELINES) > _MAX_TRADES:
                _TIMELINES.popitem(last=False)
        _TIMELINES[setup_ref].append({
            "ts": time.time(),
            "event": event,
            **fields,
        })


def get_timeline(setup_ref: str) -> list:
    with _LOCK:
        return list(_TIMELINES.get(setup_ref, []))


def get_timeline_all() -> dict:
    """Return all timelines keyed by setup_ref. Most-recent last."""
    with _LOCK:
        return {k: list(v) for k, v in _TIMELINES.items()}


def get_summary() -> dict:
    """Compact stats per trade: counts of each event type + total
    span (first event -> last event)."""
    out = []
    with _LOCK:
        for ref, events in _TIMELINES.items():
            if not events:
                continue
            by_event = {}
            for e in events:
                by_event[e["event"]] = by_event.get(e["event"], 0) + 1
            out.append({
                "setup_ref": ref,
                "n_events": len(events),
                "by_event": by_event,
                "ts_first": events[0]["ts"],
                "ts_last": events[-1]["ts"],
                "span_s": round(events[-1]["ts"] - events[0]["ts"], 2),
            })
    return {"n": len(out), "summary": out}

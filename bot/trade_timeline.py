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


def _percentile(values: list, pct: float) -> float | None:
    """Linear-interp percentile. Returns None for an empty list."""
    if not values:
        return None
    sv = sorted(values)
    k = (len(sv) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(sv) - 1)
    if f == c:
        return round(sv[f], 2)
    return round(sv[f] + (sv[c] - sv[f]) * (k - f), 2)


def _first_event(events: list, name: str) -> dict | None:
    for e in events:
        if e.get("event") == name:
            return e
    return None


def _first_fill(events: list) -> dict | None:
    """Earliest event that proves the broker parent filled. Either a
    broker_ws_event with ordStatus=Filled (instant via user WS) or the
    broker_parent_filled record from the REST poller (the safety net).
    Returns the event dict or None."""
    for e in events:
        ev = e.get("event")
        if ev == "broker_ws_event" and str(e.get("ord_status")) == "Filled":
            return e
        if ev == "broker_parent_filled":
            return e
    return None


def get_latency_report(limit: int = 200) -> dict:
    """Per-trade latency + price-divergence report. Answers the
    question 'why is broker diverging from paper' with REAL numbers,
    one row per trade plus aggregate percentiles.

    Latency stages (each measured in milliseconds, None if the
    necessary events weren't recorded for that trade):

      signal_to_placeoso_ms   -- trade_open_started -> placeoso_sending
      placeoso_rtt_ms         -- placeoso_sending -> placeoso_result
                                 (REST round-trip to Tradovate)
      placeoso_to_fill_ms     -- placeoso_result -> broker filled
                                 (matching-engine time)
      total_entry_ms          -- trade_open_started -> broker filled
                                 (end-to-end paper signal to broker
                                 having a real position)
      paper_to_broker_close_ms -- paper_closed -> broker_close_sent
                                 (decision lag on the exit side)
      close_rtt_ms            -- broker_close_sent -> broker_close_result

    Prices:
      paper_entry_px / broker_fill_px / entry_px_diff
      paper_exit_px  / broker_exit_px / exit_px_diff (when present)

    Skip / fail reasons are aggregated at the bottom with counts so a
    quick scan tells you "broker missed N of M paper trades for reason X".
    """
    rows = []
    with _LOCK:
        items = list(_TIMELINES.items())
    # Most-recent trades first; bound output size.
    items = items[-limit:]
    skip_counts: dict[str, int] = {}
    flatten_count = 0
    divergence_warn_count = 0
    for setup_ref, events in items:
        if not events:
            continue
        evs = sorted(events, key=lambda e: e.get("ts", 0))
        # Tally skip/fail reasons across every trade so the aggregate
        # at the bottom shows what's blocking the broker.
        for e in evs:
            ev = e.get("event")
            if ev == "broker_skip":
                r = str(e.get("reason") or "unknown")
                skip_counts[r] = skip_counts.get(r, 0) + 1
            elif ev == "broker_flatten_stale":
                flatten_count += 1
            elif ev == "broker_divergence_warning":
                divergence_warn_count += 1

        e_signal = _first_event(evs, "trade_open_started")
        e_send = _first_event(evs, "placeoso_sending")
        e_result = _first_event(evs, "placeoso_result")
        e_fill = _first_fill(evs)
        e_paper_closed = _first_event(evs, "paper_closed")
        e_close_sent = _first_event(evs, "broker_close_sent")
        e_close_result = _first_event(evs, "broker_close_result")
        e_skip = _first_event(evs, "broker_skip")

        def _ms(a, b):
            if a is None or b is None:
                return None
            return round((b["ts"] - a["ts"]) * 1000.0, 1)

        signal_to_placeoso_ms = _ms(e_signal, e_send)
        placeoso_rtt_ms = _ms(e_send, e_result)
        placeoso_to_fill_ms = _ms(e_result, e_fill)
        total_entry_ms = _ms(e_signal, e_fill)
        paper_to_broker_close_ms = _ms(e_paper_closed, e_close_sent)
        close_rtt_ms = _ms(e_close_sent, e_close_result)

        paper_entry_px = e_signal.get("entry_px") if e_signal else None
        broker_fill_px = None
        if e_fill:
            broker_fill_px = (e_fill.get("avg_px")
                              or e_fill.get("last_px"))
        paper_exit_px = e_paper_closed.get("exit_px") if e_paper_closed else None

        entry_px_diff = None
        if paper_entry_px is not None and broker_fill_px is not None:
            try:
                entry_px_diff = round(
                    float(broker_fill_px) - float(paper_entry_px), 4)
            except Exception:
                entry_px_diff = None

        row = {
            "setup_ref": setup_ref,
            "side": e_signal.get("side") if e_signal else None,
            "signal_ts": e_signal["ts"] if e_signal else None,
            "broker_fired": e_send is not None,
            "broker_skipped": e_skip is not None,
            "skip_reason": e_skip.get("reason") if e_skip else None,
            "broker_filled": e_fill is not None,
            "paper_closed": e_paper_closed is not None,
            "broker_close_sent": e_close_sent is not None,
            "latency_ms": {
                "signal_to_placeoso": signal_to_placeoso_ms,
                "placeoso_rtt": placeoso_rtt_ms,
                "placeoso_to_fill": placeoso_to_fill_ms,
                "total_entry": total_entry_ms,
                "paper_to_broker_close": paper_to_broker_close_ms,
                "close_rtt": close_rtt_ms,
            },
            "prices": {
                "paper_entry_px": paper_entry_px,
                "broker_fill_px": broker_fill_px,
                "entry_px_diff": entry_px_diff,
                "paper_exit_px": paper_exit_px,
            },
        }
        if e_result and not e_result.get("ok"):
            row["placeoso_error"] = e_result.get("error")
            row["placeoso_http_status"] = e_result.get("http_status")
        rows.append(row)

    def _agg(field):
        vals = [r["latency_ms"][field] for r in rows
                if r["latency_ms"][field] is not None]
        if not vals:
            return {"n": 0}
        return {
            "n": len(vals),
            "p50": _percentile(vals, 50),
            "p95": _percentile(vals, 95),
            "p99": _percentile(vals, 99),
            "max": round(max(vals), 1),
            "mean": round(sum(vals) / len(vals), 1),
        }
    px_diffs = [r["prices"]["entry_px_diff"] for r in rows
                if r["prices"]["entry_px_diff"] is not None]
    px_agg = {"n": 0}
    if px_diffs:
        abs_diffs = [abs(x) for x in px_diffs]
        px_agg = {
            "n": len(px_diffs),
            "p50_abs": _percentile(abs_diffs, 50),
            "p95_abs": _percentile(abs_diffs, 95),
            "max_abs": round(max(abs_diffs), 4),
            "mean_signed": round(sum(px_diffs) / len(px_diffs), 4),
        }

    return {
        "n_trades": len(rows),
        "aggregate_ms": {
            "signal_to_placeoso": _agg("signal_to_placeoso"),
            "placeoso_rtt": _agg("placeoso_rtt"),
            "placeoso_to_fill": _agg("placeoso_to_fill"),
            "total_entry": _agg("total_entry"),
            "paper_to_broker_close": _agg("paper_to_broker_close"),
            "close_rtt": _agg("close_rtt"),
        },
        "entry_price_divergence": px_agg,
        "skip_counts": skip_counts,
        "flatten_first_count": flatten_count,
        "divergence_warning_count": divergence_warn_count,
        "trades": rows,
    }

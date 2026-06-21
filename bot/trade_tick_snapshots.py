"""Per-trade tick + decision snapshot for paper-vs-broker forensics.

When a paper trade closes, we want to be able to answer questions like:

  * Where exactly did the bot place the broker LIMIT order?
  * Where did the broker actually fill (if at all)?
  * Where did paper book the entry vs the broker entry?
  * How did the tick path move around the entry / target / stop levels?
  * What did price do for 3 minutes after exit -- did the trade close
    too early / too late?

To answer those, this module captures the 3-min-before / 3-min-after
window of every paper trade and stitches it together with all the
broker events the trade fired (placeoso_sending, placeoso_result,
broker_ws_event fills, broker_close_sent, broker_close_result) so a
single JSON record per trade is enough to replay the whole thing.

Lifecycle:

  1. fib_main._on_trade_close calls queue_snapshot() right after the
     paper close.
  2. A daemon thread waits until exit_ts + WINDOW_AFTER_S (3 min) so
     the full after-window is available in the tick buffer.
  3. It then pulls the ticks from tick_history and the timeline
     events from trade_timeline, builds the snapshot dict and stores
     it in _SNAPSHOTS (bounded ring of MAX_SNAPSHOTS entries).
  4. The diagnostic bundle reads get_snapshots() and includes them
     under extras["per_trade_snapshots"].
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger("trade_tick_snapshots")

# Tunables (env-overridable). Window of 3 min before entry to 3 min
# after exit is plenty to see how price approached the level and how
# it behaved post-exit, without bloating the bundle.
WINDOW_BEFORE_S = float(180)
WINDOW_AFTER_S = float(180)
# Keep the most-recent N completed trade snapshots. 50 covers the
# last ~2-3 hours of activity at the current trade rate; older ones
# fall off the ring.
MAX_SNAPSHOTS = 50

_SNAPSHOTS: "OrderedDict[str, dict]" = OrderedDict()
_PENDING: list = []   # list of dicts: setup_ref, entry_ts, exit_ts, paper_record
_LOCK = threading.Lock()
_THREAD_STARTED = False


def queue_snapshot(setup_ref: Optional[str], entry_ts: float,
                    exit_ts: float, paper_record: dict) -> None:
    """Schedule a snapshot capture for a just-closed paper trade.

    The actual capture runs WINDOW_AFTER_S seconds after exit_ts so
    that the +3-min after-window is fully resident in the tick
    history buffer at capture time.
    """
    if not setup_ref:
        return
    capture_at = float(exit_ts) + WINDOW_AFTER_S
    with _LOCK:
        _PENDING.append({
            "setup_ref": setup_ref,
            "entry_ts": float(entry_ts),
            "exit_ts": float(exit_ts),
            "capture_at": capture_at,
            "paper_record": dict(paper_record or {}),
        })
    _ensure_worker()


def _ensure_worker() -> None:
    """Start the background capture thread on demand."""
    global _THREAD_STARTED
    with _LOCK:
        if _THREAD_STARTED:
            return
        _THREAD_STARTED = True
    t = threading.Thread(target=_loop, daemon=True,
                          name="trade-snap-worker")
    t.start()


def _loop() -> None:
    while True:
        try:
            time.sleep(15)
            now = time.time()
            ready: list = []
            with _LOCK:
                still_pending = []
                for p in _PENDING:
                    if p["capture_at"] <= now:
                        ready.append(p)
                    else:
                        still_pending.append(p)
                _PENDING[:] = still_pending
            for p in ready:
                try:
                    _capture_one(p)
                except Exception as e:
                    logger.debug(f"snapshot capture failed: {e!r}")
        except Exception as e:
            logger.debug(f"snapshot loop iter: {e!r}")


def _find_event(events: list, name: str) -> Optional[dict]:
    for e in events:
        if e.get("event") == name:
            return e
    return None


def _find_broker_fill(events: list) -> Optional[dict]:
    """Pick the earliest event that proves the broker parent filled.
    Either a broker_ws_event with ordStatus=Filled or the
    broker_parent_filled record from the REST poller."""
    for e in events:
        ev = e.get("event")
        if ev == "broker_ws_event" and str(e.get("ord_status")) == "Filled":
            return e
        if ev == "broker_parent_filled":
            return e
    return None


def _capture_one(pending: dict) -> None:
    from bot.tick_history import get_ticks_in_window
    from bot.trade_timeline import get_timeline

    setup_ref = pending["setup_ref"]
    entry_ts = pending["entry_ts"]
    exit_ts = pending["exit_ts"]
    paper_record = pending["paper_record"]

    window_start = entry_ts - WINDOW_BEFORE_S
    window_end = exit_ts + WINDOW_AFTER_S

    ticks = get_ticks_in_window(window_start, window_end)
    events = get_timeline(setup_ref)
    # Sort timeline events chronologically (defensive: should already be).
    events = sorted(events, key=lambda e: e.get("ts", 0))

    broker_intent = _find_event(events, "placeoso_sending")
    broker_result = _find_event(events, "placeoso_result")
    broker_fill = _find_broker_fill(events)
    broker_close_sent = _find_event(events, "broker_close_sent")
    broker_close_result = _find_event(events, "broker_close_result")
    broker_skip = _find_event(events, "broker_skip")
    broker_flatten_stale = _find_event(events, "broker_flatten_stale")

    snapshot = {
        "setup_ref": setup_ref,
        "captured_at": time.time(),
        "window": {
            "start_ts": window_start,
            "end_ts": window_end,
            "before_s": WINDOW_BEFORE_S,
            "after_s": WINDOW_AFTER_S,
            "tick_count": len(ticks),
            # Each tick is {ts, px, bid?, ask?, src}. We keep them as
            # already-trimmed dicts from tick_history.
            "ticks": ticks,
        },
        "paper": {
            "side": paper_record.get("side"),
            "qty": paper_record.get("n_mnq") or paper_record.get("qty") or 1,
            "entry_ts": entry_ts,
            "entry_px": paper_record.get("entry_px"),
            "exit_ts": exit_ts,
            "exit_px": paper_record.get("exit_px"),
            "stop_px": paper_record.get("stop_px"),
            "target_px": paper_record.get("target_px"),
            "exit_reason": paper_record.get("exit_reason"),
            "hold_s": paper_record.get("hold_s"),
            "pnl_pts": paper_record.get("pnl_pts"),
            "pnl_usd": paper_record.get("pnl_usd"),
        },
        "broker": {
            "intent": ({
                "ts": broker_intent.get("ts"),
                "symbol": broker_intent.get("symbol"),
                "entry_px": broker_intent.get("entry_px"),
                "stop_pts": broker_intent.get("stop_pts"),
                "target_pts": broker_intent.get("target_pts"),
                "live_px_at_send": broker_intent.get("live_px"),
            } if broker_intent else None),
            "submission_result": ({
                "ts": broker_result.get("ts"),
                "ok": broker_result.get("ok"),
                "order_id": broker_result.get("order_id"),
                "http_status": broker_result.get("http_status"),
                "error": broker_result.get("error"),
            } if broker_result else None),
            "fill": ({
                "ts": broker_fill.get("ts"),
                "fill_px": (broker_fill.get("avg_px")
                            or broker_fill.get("last_px")),
                "qty": broker_fill.get("last_qty"),
                "source": broker_fill.get("event"),
            } if broker_fill else None),
            "close_sent": ({
                "ts": broker_close_sent.get("ts"),
                "reason": broker_close_sent.get("reason"),
                "paper_exit_px_at_send": broker_close_sent.get("paper_exit_px"),
            } if broker_close_sent else None),
            "close_result": ({
                "ts": broker_close_result.get("ts"),
                "ok": broker_close_result.get("ok"),
                "order_id": broker_close_result.get("order_id"),
                "http_status": broker_close_result.get("http_status"),
                "error": broker_close_result.get("error"),
            } if broker_close_result else None),
            "skip": ({
                "ts": broker_skip.get("ts"),
                "reason": broker_skip.get("reason"),
            } if broker_skip else None),
            "flatten_first": ({
                "ts": broker_flatten_stale.get("ts"),
                "contractId": broker_flatten_stale.get("contractId"),
                "netPos": broker_flatten_stale.get("netPos"),
            } if broker_flatten_stale else None),
        },
    }

    # Quick divergence summary: signed differences between paper and
    # broker for the prices that matter most.
    paper_entry = paper_record.get("entry_px")
    broker_fill_px = (broker_fill.get("avg_px") or broker_fill.get("last_px")
                       if broker_fill else None)
    entry_px_diff = None
    if paper_entry is not None and broker_fill_px is not None:
        try:
            entry_px_diff = round(
                float(broker_fill_px) - float(paper_entry), 4)
        except Exception:
            entry_px_diff = None
    snapshot["divergence"] = {
        "entry_px_diff": entry_px_diff,
        "broker_filled": broker_fill is not None,
        "broker_submitted": broker_intent is not None,
        "broker_skipped": broker_skip is not None,
        "broker_close_succeeded": (broker_close_result.get("ok")
                                    if broker_close_result else None),
    }

    with _LOCK:
        _SNAPSHOTS[setup_ref] = snapshot
        while len(_SNAPSHOTS) > MAX_SNAPSHOTS:
            _SNAPSHOTS.popitem(last=False)


def get_snapshots() -> dict:
    """Return all stored snapshots keyed by setup_ref. Most recent
    appended last. Read by the diagnostic bundle."""
    with _LOCK:
        return {k: v for k, v in _SNAPSHOTS.items()}


def get_pending_count() -> int:
    with _LOCK:
        return len(_PENDING)

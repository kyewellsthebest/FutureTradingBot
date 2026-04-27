"""
JSON-backed persistence for paper account, trade log, recent signal events,
and dashboard snapshots. Replaces the .pyc shipped from the live machine —
schema mirrors data/paper_account.json and data/dashboard_data.json.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research.data_loader import DATA_DIR

logger = logging.getLogger("persistence")

ACCOUNT_PATH = DATA_DIR / "paper_account.json"
TRADES_PATH = DATA_DIR / "trade_log.json"
DASHBOARD_PATH = DATA_DIR / "dashboard_data.json"
SIGNAL_EVENTS_PATH = DATA_DIR / "signal_events.json"

DEFAULT_ACCOUNT = {
    "balance": 50_000.0,
    "starting_balance": 50_000.0,
    "open_position": None,
    "trades_today": 0,
    "last_trade_date": None,
    "last_trade_close_time": None,
    "last_trade_was_winner": False,
    "total_trades": 0,
    "wins": 0,
    "losses": 0,
    "realized_pnl": 0.0,
    "peak_balance": 50_000.0,
    "max_drawdown": 0.0,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_account() -> dict:
    if not ACCOUNT_PATH.exists():
        save_account(DEFAULT_ACCOUNT)
        return dict(DEFAULT_ACCOUNT)
    try:
        return json.loads(ACCOUNT_PATH.read_text())
    except Exception as e:
        logger.error("[persistence] account read failed: %s", e)
        return dict(DEFAULT_ACCOUNT)


def save_account(acct: dict) -> None:
    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PATH.write_text(json.dumps(acct, indent=2, default=str))


def append_trade(trade: dict) -> None:
    arr = []
    if TRADES_PATH.exists():
        try:
            arr = json.loads(TRADES_PATH.read_text())
        except Exception:
            arr = []
    arr.append(trade)
    TRADES_PATH.write_text(json.dumps(arr, indent=2, default=str))


def load_trades(limit: int | None = None) -> list[dict]:
    if not TRADES_PATH.exists():
        return []
    try:
        arr = json.loads(TRADES_PATH.read_text())
    except Exception:
        return []
    if limit:
        return arr[-limit:]
    return arr


def save_dashboard(state: dict) -> None:
    DASHBOARD_PATH.write_text(json.dumps(state, indent=2, default=str))


def load_dashboard() -> dict:
    if not DASHBOARD_PATH.exists():
        return {}
    try:
        return json.loads(DASHBOARD_PATH.read_text())
    except Exception:
        return {}


def push_signal_event(event: dict, max_keep: int = 100) -> None:
    arr = []
    if SIGNAL_EVENTS_PATH.exists():
        try:
            arr = json.loads(SIGNAL_EVENTS_PATH.read_text())
        except Exception:
            arr = []
    arr.append(event)
    arr = arr[-max_keep:]
    SIGNAL_EVENTS_PATH.write_text(json.dumps(arr, indent=2, default=str))


def load_signal_events(limit: int = 25) -> list[dict]:
    if not SIGNAL_EVENTS_PATH.exists():
        return []
    try:
        arr = json.loads(SIGNAL_EVENTS_PATH.read_text())
    except Exception:
        return []
    return arr[-limit:]

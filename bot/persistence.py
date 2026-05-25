"""
Persistence layer.

  data/paper_account.json   — account state JSON (balance, position, counters)
  data/paper_trades.db      — SQLite trade ledger, indexed on (entry_time, signal_name)
  data/dashboard_data.json  — full dashboard payload (60s flush)
  data/signal_events.json   — recent fired signals (rolling, 100 max)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from research.data_loader import DATA_DIR

logger = logging.getLogger("persistence")

ACCOUNT_PATH = DATA_DIR / "paper_account.json"
TRADES_DB_PATH = DATA_DIR / "paper_trades.db"
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


# ---------------------------------------------------------------------------
# Account JSON
# ---------------------------------------------------------------------------

def load_account() -> dict:
    if not ACCOUNT_PATH.exists():
        save_account(DEFAULT_ACCOUNT)
        return dict(DEFAULT_ACCOUNT)
    try:
        return json.loads(ACCOUNT_PATH.read_text())
    except Exception as e:
        logger.error(f"account read failed: {e}")
        return dict(DEFAULT_ACCOUNT)


def save_account(acct: dict) -> None:
    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PATH.write_text(json.dumps(acct, indent=2, default=str))


# ---------------------------------------------------------------------------
# Trade DB (SQLite)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name   TEXT    NOT NULL,
    side          TEXT    NOT NULL,
    entry_time    TEXT    NOT NULL,
    entry_px      REAL    NOT NULL,
    stop_px       REAL    NOT NULL,
    target_px     REAL    NOT NULL,
    qty           INTEGER NOT NULL,
    ml_decision   TEXT,
    ml_confidence REAL,
    vol_regime    TEXT,
    daily_bias    TEXT,
    rr            REAL,
    exit_time     TEXT,
    exit_px       REAL,
    exit_reason   TEXT,
    pnl           REAL,
    commission    REAL    DEFAULT 60.0
);
CREATE INDEX IF NOT EXISTS idx_trades_entry  ON trades (entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_signal ON trades (signal_name);
"""


def _conn() -> sqlite3.Connection:
    TRADES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TRADES_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def insert_trade(t: dict) -> int:
    """Insert an open trade row; returns the row id."""
    keys = ("signal_name", "side", "entry_time", "entry_px", "stop_px", "target_px",
            "qty", "ml_decision", "ml_confidence", "vol_regime", "daily_bias", "rr")
    values = tuple(t.get(k) for k in keys)
    placeholders = ", ".join("?" * len(keys))
    cols = ", ".join(keys)
    with _conn() as conn:
        cur = conn.execute(f"INSERT INTO trades ({cols}) VALUES ({placeholders})", values)
        return int(cur.lastrowid)


def close_trade(trade_id: int, exit_time: str, exit_px: float,
                exit_reason: str, pnl: float) -> None:
    with _conn() as conn:
        # Need signal_name to update the Kelly sizer
        row = conn.execute("SELECT signal_name FROM trades WHERE id=?",
                            (trade_id,)).fetchone()
        conn.execute(
            "UPDATE trades SET exit_time=?, exit_px=?, exit_reason=?, pnl=? WHERE id=?",
            (exit_time, exit_px, exit_reason, pnl, trade_id),
        )
    # Push the realized P&L into the Kelly sizer's rolling window so the
    # next entry on this strategy sizes adaptively.
    if row:
        try:
            from research.kelly_sizer import record_trade
            record_trade(row["signal_name"], float(pnl))
        except Exception:
            pass   # never let Kelly bookkeeping break a trade close


def load_trades(limit: int = 100, only_closed: bool = False) -> list[dict]:
    sql = "SELECT * FROM trades"
    if only_closed:
        sql += " WHERE exit_time IS NOT NULL"
    sql += " ORDER BY entry_time DESC LIMIT ?"
    with _conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]


def load_closed_trades_today(now_utc_iso: str) -> list[dict]:
    """Closed trades on the same NY date as `now_utc_iso`."""
    sql = ("SELECT * FROM trades WHERE exit_time IS NOT NULL "
           "ORDER BY entry_time DESC LIMIT 50")
    with _conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def migrate_commission_into_pnl(commission_per_mnq_rt: float = 0.74) -> int:
    """One-shot migration: trades closed BEFORE the May 25 commission-accounting
    fix recorded their pnl as gross (no commission deducted), while balance was
    correctly net of commissions. This left a small phantom "closed days = -$X"
    drift on the dashboard equal to today's accumulated commissions.

    Fix: for any trade with the legacy default commission value (>= $50, which
    can only be the unmigrated DEFAULT 60.0 marker -- real Lucid commissions
    are <$2 per round trip), subtract qty * commission_per_mnq_rt from pnl and
    write the real commission value into the column. Idempotent: only touches
    rows whose commission column is still at the legacy default.

    Returns the number of rows migrated."""
    with _conn() as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, qty, pnl FROM trades "
            "WHERE exit_time IS NOT NULL AND pnl IS NOT NULL "
            "AND commission >= 50.0"
        ).fetchall()
        if not rows:
            return 0
        for r in rows:
            real_comm = commission_per_mnq_rt * (r["qty"] or 0)
            new_pnl = (r["pnl"] or 0.0) - real_comm
            cur.execute("UPDATE trades SET pnl=?, commission=? WHERE id=?",
                        (new_pnl, real_comm, r["id"]))
        conn.commit()
        return len(rows)


def lifetime_stats() -> dict:
    """Aggregate every closed trade in the DB. Used by the Live tab's
    "Today's Activity" card after we replaced today-only with lifetime --
    the deque(maxlen=30) cap was hiding earlier wins once >=30 trades closed.
    Pure SQL aggregation -- O(1) memory regardless of trade count."""
    sql = """
        SELECT
            COUNT(*) AS n_trades,
            COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(SUM(pnl), 0.0) AS total_pnl,
            COALESCE(AVG((julianday(exit_time) - julianday(entry_time)) * 86400.0),
                     0.0) AS avg_hold_s
        FROM trades
        WHERE exit_time IS NOT NULL
    """
    with _conn() as conn:
        row = conn.execute(sql).fetchone()
    if row is None or row["n_trades"] == 0:
        return {"n_trades": 0, "wins": 0, "win_rate": 0.0,
                "total_pnl": 0.0, "avg_hold_s": 0.0, "today_pnl": 0.0,
                "today_trades": 0}
    n = int(row["n_trades"])
    wins = int(row["wins"])
    # Today's P&L computed server-side from the trades DB using NY date
    # (Lucid defines days in NY tz). The dashboard's previous client-side
    # filter used browser tz on a 30-deep deque -> sums drifted as the
    # deque rotated. Now authoritative.
    today_sql = """
        SELECT COUNT(*) AS n, COALESCE(SUM(pnl), 0.0) AS today_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND date(exit_time, '-4 hours') = date('now', '-4 hours')
    """
    with _conn() as conn:
        today_row = conn.execute(today_sql).fetchone()
    return {
        "n_trades": n,
        "wins": wins,
        "win_rate": round(wins / n * 100, 1) if n else 0.0,
        "total_pnl": round(float(row["total_pnl"]), 2),
        "avg_hold_s": round(float(row["avg_hold_s"]), 1),
        "today_pnl": round(float(today_row["today_pnl"]) if today_row else 0.0, 2),
        "today_trades": int(today_row["n"]) if today_row else 0,
    }


# ---------------------------------------------------------------------------
# Dashboard / signal-event JSON snapshots
# ---------------------------------------------------------------------------

def save_dashboard(state: dict) -> None:
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(json.dumps(state, indent=2, default=str))


def load_dashboard() -> dict:
    if not DASHBOARD_PATH.exists():
        return {}
    try:
        return json.loads(DASHBOARD_PATH.read_text())
    except Exception:
        return {}


def push_signal_event(event: dict, max_keep: int = 100) -> None:
    arr: list = []
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


# Backwards-compat shim for older callers
def append_trade(trade: dict) -> None:
    insert_trade(trade)

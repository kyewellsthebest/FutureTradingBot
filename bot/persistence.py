"""
Persistence layer.

  data/paper_account.json   — account state JSON (balance, position, counters)
  data/paper_trades.db      — SQLite trade ledger, indexed on (entry_time, signal_name)
  data/dashboard_data.json  — full dashboard payload (60s flush)
  data/signal_events.json   — recent fired signals (rolling, 100 max)

Multi-account: paths resolve per-thread via bot.account_ctx.data_dir(). The
legacy account_id "1" still uses the top-level data/ directory; new accounts
("2", "3", ...) live under data/account_<N>/. Module-level constants like
_account_path() are exposed via PEP 562 __getattr__ so external code that
references them continues to work without changes.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bot.account_ctx import data_dir

logger = logging.getLogger("persistence")

# Internal helpers — always resolve to the current thread's account.
def _account_path():      return data_dir() / "paper_account.json"
def _trades_db_path():    return data_dir() / "paper_trades.db"
def _dashboard_path():    return data_dir() / "dashboard_data.json"
def _signal_events_path(): return data_dir() / "signal_events.json"


def __getattr__(name):
    """Backward-compat: persistence.ACCOUNT_PATH etc. still work."""
    if name == "ACCOUNT_PATH":      return _account_path()
    if name == "TRADES_DB_PATH":    return _trades_db_path()
    if name == "DASHBOARD_PATH":    return _dashboard_path()
    if name == "SIGNAL_EVENTS_PATH": return _signal_events_path()
    raise AttributeError(f"module 'persistence' has no attribute {name!r}")

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
    if not _account_path().exists():
        save_account(DEFAULT_ACCOUNT)
        return dict(DEFAULT_ACCOUNT)
    try:
        return json.loads(_account_path().read_text())
    except Exception as e:
        logger.error(f"account read failed: {e}")
        return dict(DEFAULT_ACCOUNT)


def save_account(acct: dict) -> None:
    _account_path().parent.mkdir(parents=True, exist_ok=True)
    _account_path().write_text(json.dumps(acct, indent=2, default=str))


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
    _trades_db_path().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_trades_db_path()))
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

    # Compute worst single-day intra-day drawdown across all NY days
    # (peak-to-trough within one Lucid trading day). This is the
    # "daily max DD" stat -- distinct from lifetime DD which spans
    # the whole history.
    daily_dd_sql = """
        SELECT date(exit_time, '-4 hours') AS ny_date,
               pnl, exit_time
        FROM trades
        WHERE exit_time IS NOT NULL AND pnl IS NOT NULL
        ORDER BY exit_time ASC
    """
    worst_daily_dd = 0.0
    today_running_dd = 0.0
    with _conn() as conn:
        all_rows = conn.execute(daily_dd_sql).fetchall()
    current_ny = None
    cum = 0.0; peak = 0.0; max_intraday_dd = 0.0
    today_str = None
    if all_rows:
        # Need today's NY date for the today_dd computation
        today_str_sql = "SELECT date('now', '-4 hours') AS d"
        with _conn() as conn:
            today_str = conn.execute(today_str_sql).fetchone()["d"]
    for r in all_rows:
        nd = r["ny_date"]
        if nd != current_ny:
            # Day boundary -- record the worst intra-day DD and reset
            if max_intraday_dd > worst_daily_dd:
                worst_daily_dd = max_intraday_dd
            current_ny = nd
            cum = 0.0; peak = 0.0; max_intraday_dd = 0.0
        cum += float(r["pnl"])
        if cum > peak: peak = cum
        dd = peak - cum
        if dd > max_intraday_dd: max_intraday_dd = dd
        if today_str and nd == today_str:
            today_running_dd = max(today_running_dd, dd)
    # Final day's max
    if max_intraday_dd > worst_daily_dd:
        worst_daily_dd = max_intraday_dd

    return {
        "n_trades": n,
        "wins": wins,
        "win_rate": round(wins / n * 100, 1) if n else 0.0,
        "total_pnl": round(float(row["total_pnl"]), 2),
        "avg_hold_s": round(float(row["avg_hold_s"]), 1),
        "today_pnl": round(float(today_row["today_pnl"]) if today_row else 0.0, 2),
        "today_trades": int(today_row["n"]) if today_row else 0,
        "max_daily_dd": round(worst_daily_dd, 0),    # worst peak-to-trough within a single NY day
        "today_dd": round(today_running_dd, 0),      # current NY-day DD so far
    }


# ---------------------------------------------------------------------------
# Dashboard / signal-event JSON snapshots
# ---------------------------------------------------------------------------

def save_dashboard(state: dict) -> None:
    _dashboard_path().parent.mkdir(parents=True, exist_ok=True)
    _dashboard_path().write_text(json.dumps(state, indent=2, default=str))


def load_dashboard() -> dict:
    if not _dashboard_path().exists():
        return {}
    try:
        return json.loads(_dashboard_path().read_text())
    except Exception:
        return {}


def push_signal_event(event: dict, max_keep: int = 100) -> None:
    arr: list = []
    if _signal_events_path().exists():
        try:
            arr = json.loads(_signal_events_path().read_text())
        except Exception:
            arr = []
    arr.append(event)
    arr = arr[-max_keep:]
    _signal_events_path().write_text(json.dumps(arr, indent=2, default=str))


def load_signal_events(limit: int = 25) -> list[dict]:
    if not _signal_events_path().exists():
        return []
    try:
        arr = json.loads(_signal_events_path().read_text())
    except Exception:
        return []
    return arr[-limit:]


# Backwards-compat shim for older callers
def append_trade(trade: dict) -> None:
    insert_trade(trade)

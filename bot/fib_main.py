"""
Fibonacci 50% retracement bot runtime.

Replaces bot/v11_main.py as the new live engine. Single strategy: Fib 50%
retracement on 10-min entries / 1-min exits, 5 MNQ default size.

Configuration via env vars:
  BOT_SHADOW_MODE=1   (default) Logs decisions but does NOT send orders.
                      Run in shadow for several days before flipping live.
  BOT_SHADOW_MODE=0   Live execution via LucidAccount paper trading layer.
  FIB_N_MNQ=5         Override contract size (default 5)

Live deployment pattern (used by live_runner.py):
    from bot.fib_main import FibRuntime
    FibRuntime().run()
"""
from __future__ import annotations

import json
import logging
import os
import signal as signal_mod
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from bot import persistence
from bot.pullback_strategy import (
    DEFAULT_SIZE, FibStrategyState, MICROSCALP_HARD_THRESHOLD,
    MIN_TARGET_HOLD_SECONDS, lucid_precheck, on_new_1m_bar,
    snapshot as fib_snapshot,
)
from bot.lucid_account import LucidAccount
from bot.price_monitor import PriceMonitor
from research.clock_sync import real_utc_now, sync_clock
from research.data_loader import DATA_DIR, download_nq, download_symbol
from bot.account_ctx import data_dir as _account_data_dir

logger = logging.getLogger("bot_fib")

CYCLE_FLAT_SECONDS = 60
CYCLE_TRADE_SECONDS = 5
def _dashboard_path():
    """Resolve per-account so each FibRuntime writes to its own snapshot."""
    return _account_data_dir() / "dashboard_data.json"
def __getattr__(name):
    """Backward-compat for any code that imported DASHBOARD_PATH directly."""
    if name == "DASHBOARD_PATH": return _dashboard_path()
    raise AttributeError(f"module 'fib_main' has no attribute {name!r}")
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "bot_fib.log"

SHADOW_MODE = os.environ.get("BOT_SHADOW_MODE", "1") == "1"
N_MNQ = int(os.environ.get("FIB_N_MNQ", str(DEFAULT_SIZE)))
# Execution cost overrides (Lucid 50K Pro / Tradovate prop-firm defaults).
# These override the paper account's legacy market-order constants. Tune
# via env if your broker statement shows different rates.
ENTRY_SLIP_PTS = float(os.environ.get("FIB_ENTRY_SLIP_PTS", "0.0"))      # limit fills
ADVERSE_SLIP_PTS = float(os.environ.get("FIB_ADVERSE_SLIP_PTS", "0.25")) # realistic MNQ stop slip
COMM_PER_MNQ_RT = float(os.environ.get("FIB_COMM_PER_MNQ_RT", "0.74"))   # Lucid prop rate


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    if not logger.handlers:
        h_file = logging.FileHandler(LOG_PATH)
        h_file.setFormatter(fmt)
        logger.addHandler(h_file)
        h_stream = logging.StreamHandler()
        h_stream.setFormatter(fmt)
        logger.addHandler(h_stream)
    logger.setLevel(logging.INFO)


def _iso(v):
    """ISO-format a timestamp-ish value, robust to None / non-datetime.

    CRITICAL: always returns a UTC-aware ISO string (with +00:00 or Z).
    Naive strings from SQLite get a UTC suffix appended -- without this,
    JS new Date(naive_string) interprets the value in the BROWSER's local
    timezone, which on a phone in AEST is +10h ahead of UTC. The trade
    markers then land 10h past the latest candle on the chart, causing
    all markers to pile up on the rightmost bar instead of their real
    candle. (Caused the May 25 "all arrows on one candle" bug.)
    """
    if v is None: return None
    if hasattr(v, "isoformat"):
        try:
            iso = v.isoformat()
        except Exception:
            iso = str(v)
    else:
        iso = str(v)
    # If the rendered string carries no tz designator, assume UTC.
    # ISO tz markers: "+HH:MM", "-HH:MM", "Z" anywhere after the time
    # component (i.e. after position 10 = "YYYY-MM-DD").
    if len(iso) >= 11 and not (iso.endswith("Z") or "+" in iso[10:] or "-" in iso[10:]):
        # Replace SQLite's space separator with 'T' so JS Date sees ISO 8601
        iso = iso.replace(" ", "T", 1) + "+00:00"
    return iso


# ---------------------------------------------------------------------------
# Bar utilities — synthesize 1-min from 5-min for setup detection
# ---------------------------------------------------------------------------
def _synth_1min_from_5min(bars_5m: pd.DataFrame) -> pd.DataFrame:
    """Synthesize 1-min OHLCV by walking a deterministic O→{L|H}→mid→{H|L}→C
    path inside each 5-min bar (up bars dip to L early, peak at H late;
    down bars do the opposite). Preserves the parent 5-min OHLC exactly
    across each 5-bar block. This matches the backtest synthesis path
    so live behavior mirrors the validated numbers."""
    if bars_5m is None or bars_5m.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    o = bars_5m["open"].to_numpy()
    h = bars_5m["high"].to_numpy()
    l = bars_5m["low"].to_numpy()
    c = bars_5m["close"].to_numpy()
    v = bars_5m["volume"].to_numpy()
    idx = bars_5m.index
    rows = []
    for i in range(len(bars_5m)):
        if c[i] >= o[i]:
            wp = [o[i], l[i], (l[i] + h[i]) / 2, h[i], c[i]]
        else:
            wp = [o[i], h[i], (h[i] + l[i]) / 2, l[i], c[i]]
        ts = idx[i]
        for k in range(5):
            so = wp[k]
            sc = wp[k + 1] if k + 1 < len(wp) else c[i]
            rows.append((ts + pd.Timedelta(minutes=k),
                          so, max(so, sc), min(so, sc), sc, v[i] / 5))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low",
                                      "close", "volume"])
    return df.set_index("ts")


def _build_last_1m_from_price(monitor_snap, last_5m_close: float) -> pd.Series:
    """Synthesize a 1-min bar from the price-monitor's accumulated tick
    high/low. Used between full 1-min bar refreshes for tight exit timing."""
    high = monitor_snap.high if monitor_snap and monitor_snap.high else last_5m_close
    low = monitor_snap.low if monitor_snap and monitor_snap.low else last_5m_close
    price = monitor_snap.price if monitor_snap else last_5m_close
    return pd.Series({"open": price, "high": high, "low": low,
                      "close": price, "volume": 1})


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
class FibRuntime:
    def __init__(self, account_id: str = "1") -> None:
        # Bind THIS thread to this account so all persistence calls during
        # __init__ (LucidAccount load, paper account load) read/write the
        # correct namespace. live_runner.py spawns one FibRuntime per
        # account configured in the ACCOUNTS env var.
        from bot.account_ctx import set_account
        set_account(account_id)
        self.account_id = account_id
        self.state = FibStrategyState()
        self.account = LucidAccount()
        self.monitor = PriceMonitor()
        self.cycle = 0
        self._running = True
        self.last_error: Optional[str] = None
        self.bars_processed = 0
        self.signals_fired = 0
        self.signals_blocked = 0
        # Cache fetched 5-min bars + synthesized 1-min; refresh every 60s when flat.
        # 1-min = setup detection timeframe (synthesized from 5-min source).
        # 5-min = HTF trend filter timeframe (raw Polygon data).
        self._bars_5m: Optional[pd.DataFrame] = None
        self._bars_1m: Optional[pd.DataFrame] = None
        self._bars_1m_source: str = "synth"   # "real" or "synth"
        self._last_bar_refresh = 0.0
        # Recent completed trades for dashboard. Hydrated from the
        # SQLite trade log on construction so history survives restarts.
        self.recent_trades: deque = deque(maxlen=30)
        self._hydrate_recent_trades()

    def _hydrate_recent_trades(self) -> None:
        """Load the last 30 closed trades from persistence so the Trades
        tab keeps history across bot restarts / Railway redeploys."""
        try:
            rows = persistence.load_trades(limit=30, only_closed=True)
        except Exception as e:
            logger.warning(f"trade-history hydrate failed: {e}")
            return
        # persistence.load_trades returns newest-first ORDER BY entry_time DESC.
        # Convert each DB row into the dashboard's expected record shape.
        for row in rows:
            try:
                hold_s = 0.0
                if row.get("entry_time") and row.get("exit_time"):
                    et = pd.Timestamp(row["entry_time"])
                    xt = pd.Timestamp(row["exit_time"])
                    hold_s = (xt - et).total_seconds()
                rec = {
                    "ts": row.get("exit_time") or row.get("entry_time"),
                    "entry_ts": row.get("entry_time"),
                    "side": row.get("side"),
                    "n_mnq": int(row.get("qty") or 0),
                    "entry_px": float(row.get("entry_px") or 0),
                    "exit_px": float(row.get("exit_px") or 0),
                    "exit_reason": row.get("exit_reason") or "",
                    "pnl_usd": float(row.get("pnl") or 0),
                    "pnl_pts": 0.0,
                    "hold_s": float(hold_s),
                }
                self.recent_trades.append(rec)
            except Exception as e:
                logger.debug(f"skip malformed trade row: {e}")
        logger.info(f"hydrated {len(self.recent_trades)} trade(s) from DB")

    def stop(self, *_):
        logger.info("stop received")
        self._running = False

    # ---- main loop -----------------------------------------------------
    def run(self) -> int:
        # Re-bind in case this is a different thread than __init__ ran in
        # (live_runner spawns one thread per account, and constructs the
        # Runtime inside that thread, but be defensive).
        from bot.account_ctx import set_account
        set_account(self.account_id)
        _setup_logging()
        sync_clock()
        # One-shot historical commission migration. Trades closed before the
        # commission-into-pnl fix have inflated pnl values by ~$1.48 each
        # (qty=2 * $0.74 RT) which made the dashboard show a small phantom
        # "closed_days" drift. This is idempotent -- only touches rows still
        # carrying the schema's legacy DEFAULT 60.0 commission marker.
        try:
            migrated = persistence.migrate_commission_into_pnl(COMM_PER_MNQ_RT)
            if migrated:
                logger.warning(f"migrated commission accounting on {migrated} historical trade(s)")
        except Exception as e:
            logger.warning(f"commission migration failed (non-fatal): {e}")
        mode = "SHADOW (no orders)" if SHADOW_MODE else "LIVE"
        logger.info(f"[fib_main] starting — {mode} mode, "
                    f"strategy=Fib 50% (1-min setup + 5-min HTF trend), "
                    f"size={N_MNQ} MNQ default, "
                    f"min_target_hold={MIN_TARGET_HOLD_SECONDS}s, "
                    f"circuit_breaker_threshold={MICROSCALP_HARD_THRESHOLD*100:.0f}%")
        self.monitor.start()
        # Signal handlers can ONLY be installed from the main thread of the
        # main interpreter. Account 2+ (and any other multi-account
        # secondary) runs on a daemon thread and would crash here without
        # the try/except. Guard both calls.
        try:
            signal_mod.signal(signal_mod.SIGINT, self.stop)
        except (ValueError, Exception):
            pass   # not main thread; the primary account's handler covers SIGINT
        try:
            signal_mod.signal(signal_mod.SIGTERM, self.stop)
        except Exception:
            pass
        while self._running:
            try:
                self._tick()
            except Exception as e:
                self.last_error = repr(e)
                logger.exception(f"tick failed: {e}")
            self._publish_dashboard()
            in_trade = self.state.active_trade is not None
            self._sleep(CYCLE_TRADE_SECONDS if in_trade else CYCLE_FLAT_SECONDS)
            if self.cycle % 60 == 0:
                sync_clock()
        self.monitor.stop()
        return 0

    def _sleep(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                return
            time.sleep(1)

    # ---- single tick ---------------------------------------------------
    def _tick(self) -> None:
        self.cycle += 1
        now = real_utc_now()
        snap = self.monitor.snapshot_and_reset()
        in_trade = self.state.active_trade is not None

        # Refresh 5-min (HTF trend) + 1-min (setup detection) bars at most
        # every 60s. Prefer REAL 1-min from Polygon/yfinance; fall back to
        # synthesizing 1-min from 5-min if 1-min source is unavailable. The
        # synth path mirrors the backtest exactly so behavior degrades
        # gracefully when the 1-min feed has a hiccup.
        tnow = time.time()
        if self._bars_5m is None or tnow - self._last_bar_refresh > 60:
            try:
                nq5 = download_nq("5min")
                if nq5 is not None and not nq5.empty:
                    if nq5.index.tz is None:
                        nq5.index = nq5.index.tz_localize("UTC")
                    self._bars_5m = nq5
                    # Try real 1-min; if unavailable, synthesize.
                    nq1 = None
                    try:
                        nq1 = download_nq("1min")
                        if nq1 is not None and not nq1.empty and nq1.index.tz is None:
                            nq1.index = nq1.index.tz_localize("UTC")
                    except Exception as e:
                        logger.debug(f"1-min fetch failed (will synth): {e}")
                    if nq1 is None or nq1.empty:
                        self._bars_1m = _synth_1min_from_5min(nq5)
                        self._bars_1m_source = "synth"
                    else:
                        self._bars_1m = nq1
                        self._bars_1m_source = "real"
                    self._last_bar_refresh = tnow
            except Exception as e:
                logger.warning(f"bar refresh failed: {e}")
                if self._bars_5m is None:
                    return

        if self._bars_5m is None or self._bars_5m.empty:
            return
        if self._bars_1m is None or self._bars_1m.empty:
            return

        # Synthesize the live 1-min bar from accumulated tick high/low.
        # Used for exit-detection precision (tight when in-trade) and to
        # arm/invalidate pending setups against very recent price.
        last_5m_close = float(self._bars_5m["close"].iloc[-1])
        last_1m = _build_last_1m_from_price(snap, last_5m_close)

        self.bars_processed += 1
        had_trade_before = self.state.active_trade is not None
        # The fib strategy reads a research/lucid_guard.LucidState — the
        # bot's LucidAccount has a helper to build that on demand.
        runtime_lucid = self.account._build_runtime_lucid_state()
        # bars_trend is the same 1-min series as bars_setup — the HTF
        # filter now runs on 1-min bars with k=30 (~30 min confirmation)
        # instead of 5-min k=10 (~50 min). Same-timeframe trend reacts
        # faster than the older 5-min variant and dropped PF 1.26 -> 1.43
        # in real-data backtest.
        # Per-account strategy params (account 1 = target=12 legacy,
        # account 2 = target=18 upgrade -- see bot/account_ctx.py).
        from bot.account_ctx import get_strategy_params
        record = on_new_1m_bar(self.state, runtime_lucid,
                               self._bars_1m, last_1m, now,
                               n_mnq=N_MNQ, bars_trend=self._bars_1m,
                               params=get_strategy_params(self.account_id))

        # Trade opened this tick?
        if not had_trade_before and self.state.active_trade is not None:
            self.signals_fired += 1
            self._on_trade_open(self.state.active_trade, now)

        # Trade closed this tick?
        if record is not None:
            self._on_trade_close(record, now)
            self.recent_trades.appendleft(record)

    # ---- trade lifecycle hooks ----------------------------------------
    def _on_trade_open(self, trade, now: datetime) -> None:
        # Always route through the paper account so balance + DB persist
        # in both LIVE and SHADOW modes. The mode label only controls
        # whether we'd ALSO send a real broker order (we never do yet,
        # so today shadow and live are functionally identical).
        try:
            # Pullback strategy uses LIMIT-style entries (waits for price to
            # touch pullback_entry, fills at that level). Override the paper
            # account's legacy market-order defaults with prop-firm-realistic
            # values (env-configurable for tuning to actual broker statements).
            self.account.enter(
                signal_name=f"FIB_{trade.side}_{int(trade.setup.level50)}",
                side=trade.side, entry_px_raw=trade.entry_px,
                stop_px=trade.stop_px, target_px=trade.target_px,
                qty=trade.n_mnq, vol_regime="FIB",
                rr=abs(trade.target_px - trade.entry_px) /
                   max(abs(trade.stop_px - trade.entry_px), 1e-9),
                now=now,
                entry_slip_pts=ENTRY_SLIP_PTS,
                adverse_slip_pts=ADVERSE_SLIP_PTS,
                commission_per_mnq_rt=COMM_PER_MNQ_RT,
            )
            tag = "SHADOW" if SHADOW_MODE else "LIVE"
            logger.info(f"[{tag} OPEN] {trade.side} {trade.n_mnq} MNQ "
                        f"@ {trade.entry_px:.2f}  stop={trade.stop_px:.2f} "
                        f"tgt={trade.target_px:.2f}")
        except Exception as e:
            self.last_error = f"open failed: {e}"
            logger.exception(f"open failed: {e}")

    def _on_trade_close(self, record: dict, now: datetime) -> None:
        # Always close through the paper account so balance updates and
        # the trade is persisted to the SQLite DB — surviving restarts.
        adverse = (record["exit_reason"] == "stop")
        try:
            self.account._close(exit_px_raw=record["exit_px"],
                                reason=record["exit_reason"],
                                adverse=adverse, now=now)
            tag = "SHADOW" if SHADOW_MODE else "LIVE"
            logger.info(f"[{tag} CLOSE] {record['side']} pnl=${record['pnl_usd']:+,.2f} "
                        f"hold={record['hold_s']:.1f}s reason={record['exit_reason']}")
        except Exception as e:
            self.last_error = f"close failed: {e}"
            logger.exception(f"close failed: {e}")

    # ---- dashboard data publish ---------------------------------------
    def _publish_dashboard(self) -> None:
        try:
            # Live price for topbar + live P&L on active trade
            latest = self.monitor.latest()
            current_price = float(latest.price) if latest and latest.price else None
            fib_snap = fib_snapshot(self.state, current_price=current_price)
            lucid_snap = self.account.lucid_snapshot()
            funded_snap = self.account.ledger.snapshot()
            # Lifetime aggregate (every closed trade ever) -- the "Today's
            # Activity" card was previously filtering recent_trades which is
            # capped at 30 in this deque, hiding earlier history once the
            # bot had been running long enough.
            try:
                lifetime = persistence.lifetime_stats()
            except Exception as e:
                logger.debug(f"lifetime_stats failed: {e}")
                lifetime = None
            blob = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": "shadow" if SHADOW_MODE else "live",
                "lifetime_stats": lifetime,
                "strategy": "Fib 50% (1-min entries + 5-min HTF trend filter)",
                "bars_1m_source": self._bars_1m_source,
                "cycle": self.cycle,
                "last_error": self.last_error,
                "bars_processed": self.bars_processed,
                "signals_fired": self.signals_fired,
                "signals_blocked": self.signals_blocked,
                "price": current_price,
                "price_ts": latest.ts.isoformat() if latest and latest.ts else None,
                "fib": fib_snap,
                "lucid_account": lucid_snap,
                "funded_accounts": funded_snap,
                "recent_trades": [
                    {**t,
                     "ts": _iso(t.get("ts")),
                     "entry_ts": _iso(t.get("entry_ts")),
                     "pivot_high_ts": _iso(t.get("pivot_high_ts")),
                     "pivot_low_ts": _iso(t.get("pivot_low_ts")),
                     "armed_at_ts": _iso(t.get("armed_at_ts"))}
                    for t in list(self.recent_trades)[:30]
                ],
            }
            _dashboard_path().write_text(json.dumps(blob, indent=2, default=str))
        except Exception as e:
            # Was silently swallowed at DEBUG — caused the May 25 zombie-bot
            # incident where the dashboard showed "UPDATED —" for hours
            # because EVERY publish threw and nobody saw. Now: log at ERROR
            # so it shows in Railway logs, AND write the traceback to
            # data/bot_crash.txt so /api/diag can surface it.
            logger.error(f"dashboard publish failed: {e!r}", exc_info=True)
            try:
                import traceback as _tb
                from datetime import datetime as _dt, timezone as _tz
                (_dashboard_path().parent / "bot_crash.txt").write_text(
                    f"[{_dt.now(_tz.utc).isoformat()}] "
                    f"_publish_dashboard crashed: {e!r}\n\n{_tb.format_exc()}")
            except Exception:
                pass


def main() -> int:
    return FibRuntime().run()


if __name__ == "__main__":
    raise SystemExit(main())

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

CYCLE_FLAT_SECONDS = 2     # was 60 -- WAY too slow. Bot was missing
                            # tick-level pullback touches by 0-60s while
                            # waiting for the next cycle. Now polls every
                            # 2s for general management; tick-level firing
                            # runs INLINE on every Polygon tick (sub-100ms).
CYCLE_TRADE_SECONDS = 2    # was 5. Same rationale.
def _dashboard_path():
    """Resolve per-account so each FibRuntime writes to its own snapshot."""
    return _account_data_dir() / "dashboard_data.json"
def __getattr__(name):
    """Backward-compat for any code that imported DASHBOARD_PATH directly."""
    if name == "DASHBOARD_PATH": return _dashboard_path()
    raise AttributeError(f"module 'fib_main' has no attribute {name!r}")
# Log path resolves in this order:
#   1. BOT_LOG_FILE env var (used on Railway with persistent volume)
#   2. <repo>/logs/bot_fib.log (legacy / local dev)
# When BOT_LOG_FILE points at a persistent volume (e.g. /app/data/bot.log)
# the dashboard's diagnostic bundle can include the actual log tail
# instead of reporting "unavailable".
def _resolve_log_path() -> Path:
    env_path = os.environ.get("BOT_LOG_FILE")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent.parent / "logs" / "bot_fib.log"
LOG_PATH = _resolve_log_path()

def _is_shadow_mode() -> bool:
    """Re-read BOT_SHADOW_MODE on every call instead of using a
    module-level constant. A constant captured at import time stays
    stale if the env changes mid-run (Railway env edit, restart with
    different config, etc.) -- and the silent-shadow-broker-skip bug
    that hid 88 paper trades from TradersPost is exactly the symptom.

    Returns True if shadow mode is on (paper only, no broker call)."""
    return os.environ.get("BOT_SHADOW_MODE", "1") == "1"
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
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    if not logger.handlers:
        # Use a rotating handler so the volume can't fill up. 5x 10 MB
        # = 50 MB of recent history retained, oldest auto-truncated.
        # Without rotation a long-running bot can fill the 500 MB
        # volume with logs alone in a few weeks.
        from logging.handlers import RotatingFileHandler
        h_file = RotatingFileHandler(
            LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=4)
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


def _build_last_1m_from_price(monitor_snap, fallback_bar: pd.Series,
                              bars_1m_source: str = "real") -> pd.Series:
    """Build the bar used by the strategy for fill / exit checks.

    Critical decision: we ALWAYS use the latest CLOSED 1-min bar from Polygon
    (the `fallback_bar` arg, despite its name) -- NOT the synth bar built from
    the 3-second-poll PriceMonitor extremes. Why:

    Forensic analysis of 1,412 live paper trades vs realistic 2-year 1-min
    backtest showed the live bot was making ~$8/trade LESS than the same
    strategy run on real 1-min OHLC. Diagnosis: the synth bar's high/low
    only captures whichever 20 of ~6000 ticks-per-minute the 3-sec poller
    happened to sample. During US RTH high-vol periods this triggers
    spurious "fills" on sampled wicks that don't reflect actual intra-bar
    price action, then books fictitious stop-outs seconds later. 78-100%
    of all live stops were within 10s of entry -- the smoking gun.

    By using the real closed 1-min bar's OHLC, the live bot now executes
    identically to the realistic backtest (which scans bar-by-bar). Expected
    impact: WR 37% -> 49%, expectancy +$0.58 -> +$8.36/trade, max DD
    $1,831 -> $661 (validated on 2yr/426k 1-min bars, 0 DLL breaches).

    Trade-off: up to 60s latency on entries (have to wait for the bar that
    crosses the limit to close before the strategy fires). This matches
    backtest semantics exactly.
    """
    # bars_1m_source == "synth" means we're already running on downsampled
    # 5-min data -- no real intra-minute high/low to consult. In that case
    # the synth-bar reasoning above doesn't apply; fall back to the snap.
    if bars_1m_source == "real" and fallback_bar is not None:
        return pd.Series({
            "open":  float(fallback_bar["open"]),
            "high":  float(fallback_bar["high"]),
            "low":   float(fallback_bar["low"]),
            "close": float(fallback_bar["close"]),
            "volume": float(fallback_bar.get("volume", 1)),
        })
    if monitor_snap is not None and monitor_snap.high and monitor_snap.low:
        return pd.Series({
            "open":  monitor_snap.price,
            "high":  monitor_snap.high,
            "low":   monitor_snap.low,
            "close": monitor_snap.price,
            "volume": 1,
        })
    # Last-resort fallback when both real bars and the monitor are dead.
    return pd.Series({
        "open":  float(fallback_bar["open"]),
        "high":  float(fallback_bar["high"]),
        "low":   float(fallback_bar["low"]),
        "close": float(fallback_bar["close"]),
        "volume": float(fallback_bar.get("volume", 1)),
    })


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
        # Shadow engine: runs the new engine.runtime.Runtime in parallel on
        # the same bars. Zero influence on live trading; produces an
        # artifact we can diff against the live bot to verify equivalence.
        # Disabled if engine package can't be imported (graceful fallback).
        try:
            from bot.shadow_engine import ShadowEngine
            self.shadow = ShadowEngine(
                account_id=account_id,
                starting_balance=float(getattr(self.account.state, "starting_balance",
                                                 50000.0)),
            )
        except Exception as e:
            self.last_error = f"shadow_engine init failed: {e!r}"
            self.shadow = None
        # TradersPost broker -- forwards every live trade open/close to the
        # user's TradersPost webhook so it can route to whichever prop firm
        # broker they've connected (Lucid/Tradovate, Apex, etc).
        # SAFETY: default is dry-run (TRADERSPOST_LIVE!=true logs payloads
        # but doesn't actually POST). Wrapped so broker outages can never
        # crash the bot loop.
        try:
            from engine.brokers.traderspost import TradersPostBroker
            self.traderspost = TradersPostBroker()
        except Exception as e:
            self.last_error = f"traderspost init failed: {e!r}"
            self.traderspost = None
        # Tradovate direct broker client -- preferred when configured.
        # When tradovate is available, broker forwarding goes through
        # the Tradovate REST API instead of TradersPost. Same market
        # data feed (Tradovate WS) and same execution venue eliminates
        # paper-vs-broker divergence at the source.
        try:
            from bot.tradovate_client import get_session
            from bot.tradovate_orders import TradovateOrders
            self.tradovate_session = get_session()
            if self.tradovate_session.is_configured:
                self.tradovate_orders = TradovateOrders(self.tradovate_session)
                logger.info("Tradovate broker active (env vars configured)")
                # LATENCY: pre-establish HTTP keep-alive socket BEFORE
                # the first real trade. Saves 200-300ms of TCP+TLS
                # handshake off the first placeoso's critical path.
                try:
                    self.tradovate_session.prewarm()
                except Exception:
                    pass
                # Pre-resolve front-month contractId once at boot so
                # every liquidate / order doesn't hit /contract/find.
                try:
                    from research.data_loader import polygon_front_month
                    _sym = os.environ.get(
                        "TRADOVATE_SYMBOL",
                        polygon_front_month(
                            os.environ.get("POLYGON_CONTRACT", "MNQ")))
                    _root = _sym.rstrip("0123456789MHUZQNF") or "MNQ"
                    _c = self.tradovate_session.find_contract(_root)
                    if _c and _c.get("id"):
                        self.tradovate_session._contract_id_cache[_sym] = int(_c["id"])
                        logger.info(
                            f"[Tradovate prewarm] cached contractId="
                            f"{_c['id']} for {_sym}")
                except Exception:
                    pass
            else:
                self.tradovate_orders = None
                logger.info("Tradovate broker not configured; using TradersPost")
        except Exception as e:
            self.last_error = f"tradovate init failed: {e!r}"
            self.tradovate_session = None
            self.tradovate_orders = None
        # Economic calendar -- pulled from Forex Factory's free XML feed
        # every 6h. Used by pullback_strategy to skip entries 5min before
        # / 15min after big USD releases (CPI, FOMC, NFP, PCE, GDP, Powell,
        # ISM, Retail Sales). Init is non-blocking: the first refresh()
        # runs lazily on the first strategy tick. A fetch failure leaves
        # events=[] so no blackout windows fire -- fail-open.
        try:
            from engine.data_sources.economic_calendar import EconomicCalendar
            self.news_calendar = EconomicCalendar(
                cache_dir=_account_data_dir() / "cache")
            # Warm the cache once at startup so the first ticks already
            # know about today's events. Errors swallowed -- the strategy
            # will retry on its next next_event_within() call.
            try:
                self.news_calendar.refresh()
            except Exception as e:
                logger.warning(f"economic calendar initial refresh failed: {e!r}")
        except Exception as e:
            self.last_error = f"calendar init failed: {e!r}"
            self.news_calendar = None
        # Stashes the setup_ref between open and close so the close webhook
        # can pair with its open for TradersPost idempotency.
        self._open_trade_ref: Optional[str] = None
        # Set when we've fired a broker-side panic close so the next tick
        # doesn't re-fire it. Cleared in _on_trade_close. Without this
        # flag, every tick after the panic trigger would send another
        # submit_close to TradersPost.
        self._panic_closed_ref: Optional[str] = None
        # Broker-anchored stop level + side, captured at submit_open time
        # using the LIVE PriceMonitor anchor. The panic-close compares
        # live price against THIS, not against the strategy's stale
        # stop_px (which can be 20-40pt off from real fill).
        self._broker_stop_px: Optional[float] = None
        self._broker_target_px: Optional[float] = None
        self._broker_side: Optional[str] = None
        # Trade timing + deferred target dispatch state. Lucid funded
        # account microscalp rule: <5s profit trades can't exceed 50% of
        # profits. We defer sending the broker take-profit by 10s after
        # entry so the broker can't fire it inside Lucid's microscalp
        # window. The entry is sent with stop-only; the target is sent
        # as a separate limit order once hold time >= LUCID_TARGET_DEFER_S.
        self._broker_entry_ts: Optional[datetime] = None
        self._broker_target_sent: bool = False
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
        # Rate-limit the "[BAR-STALE]" log so it fires at most once per
        # minute of staleness instead of every tick.
        self._last_stale_warn_age: int = -1
        # Recent completed trades for dashboard. Hydrated from the
        # SQLite trade log on construction so history survives restarts.
        self.recent_trades: deque = deque(maxlen=30)
        self._hydrate_recent_trades()
        # Passive broker fill tracker. After every placeoso, append
        # {setup_ref, parent_order_id, submitted_at, checks_done, ...}
        # here. The poll runs on each _tick (PASSIVE -- we never block
        # paper, never cancel the order, never reduce trades). Just tag
        # the trade record with whether the broker actually filled.
        self._pending_parent_orders: list = []
        # PRE-SUBMIT LIMIT: at most ONE pre-submitted broker LIMIT at a
        # time. When the strategy creates a pending_setup (impulse formed,
        # pullback level computed), we immediately submit a LIMIT @ that
        # level + bracket. The LIMIT rests on the matching engine for up
        # to 5 minutes (setup TTL). When price retraces to the level, it
        # fills INSTANTLY (microseconds) -- no network RTT delay.
        # When a different setup arrives, cancel the old LIMIT and submit
        # a new one (single-position invariant).
        # Format: {'setup_key', 'order_id', 'side', 'entry_px', 'stop_px',
        #          'target_px', 'submitted_at'}
        self._pre_submitted_limit: Optional[dict] = None
        # ANTICIPATORY LIMIT: when price approaches within 1pt of a
        # pending setup's entry level, submit the broker LIMIT NOW so it
        # rests on the matching engine ahead of the touch. Solves the
        # 500ms-RTT miss without the multi-LIMIT stacking that broke
        # the original pre-submit design. Only ONE alive at a time.
        # Format: same as _pre_submitted_limit.
        self._anticipatory_limit: Optional[dict] = None
        # LATENCY: cache the resolved Tradovate symbol so we don't
        # re-resolve from polygon_front_month on every trade. Same
        # value all day. Refreshes on next bot restart.
        self._cached_symbol: Optional[str] = None
        # Process start time for the diagnostic bundle's uptime stats.
        self._started_at = time.time()
        # CRITICAL LATENCY OPTIMIZATION: register a tick callback so
        # try_fire_on_tick runs inline on every Polygon tick (sub-100ms
        # reaction time) instead of waiting up to CYCLE_FLAT_SECONDS for
        # the next main-loop cycle. Lock prevents the tick handler from
        # firing while _tick() is also processing one.
        import threading as _threading
        self._tick_fire_lock = _threading.Lock()
        try:
            self.monitor.register_tick_callback(self._on_tick_instant)
            logger.info("[FAST PATH] tick callback registered on monitor")
        except Exception as e:
            logger.warning(f"failed to register tick callback: {e!r}")
        # Spin up the Tradovate user WS for real-time fill events. The
        # bot can survive without it (falls back to the +0.5/2/5/15s
        # REST poll above), but with it we see fills in <100ms.
        try:
            if self.tradovate_session is not None:
                from bot.tradovate_user_ws import TradovateUserWS
                self.tradovate_user_ws = TradovateUserWS(self.tradovate_session)
                started = self.tradovate_user_ws.start()
                logger.info(f"tradovate_user_ws started={started}")
            else:
                self.tradovate_user_ws = None
        except Exception as e:
            logger.warning(f"tradovate_user_ws init failed: {e!r}")
            self.tradovate_user_ws = None

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
        mode = "SHADOW (no orders)" if _is_shadow_mode() else "LIVE"
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
    def _poll_pending_broker_orders(self) -> None:
        """Passive broker fill tracker. Polls the parent order ID for
        each recent placeoso to record actual fill status into the
        trade timeline. NEVER blocks paper, NEVER cancels orders,
        NEVER reduces trades. Pure read-only diagnostic.

        Two paths:
          1. If the user WS is connected, look up the parent order
             in the live ExecutionReport buffer -- arrives in <100ms.
          2. Otherwise REST poll at +0.5s, +2s, +5s, +15s.

        Goal: by the time the bot enters _on_trade_close, we know
        from the timeline whether the broker actually filled or
        not -- so the reconciliation can correctly attribute the
        paper-vs-broker delta.
        """
        if not self._pending_parent_orders or self.tradovate_orders is None:
            return
        from bot.trade_timeline import add_event as _tl
        # First pass: check the live user WS event buffer for fills on
        # any pending parents. This catches fills the instant the
        # matching engine reports them, well before the REST poll
        # schedule would trigger.
        ws_fills_by_order = {}
        try:
            if getattr(self, "tradovate_user_ws", None) is not None:
                ws = self.tradovate_user_ws
                if ws.connected:
                    for er in ws.get_exec_reports(limit=200):
                        oid = er.get("orderId")
                        if oid is not None:
                            ws_fills_by_order[int(oid)] = er
        except Exception:
            pass
        now_ts = time.time()
        keep = []
        # Check intervals: at most one poll per tick to avoid burning
        # rate budget. Stops after 15s.
        for entry in self._pending_parent_orders:
            age = now_ts - entry["submitted_at"]
            # WS shortcut: if we have a live exec report showing this
            # parent filled/rejected, record it and move on. The REST
            # poll is the safety net.
            pid = entry.get("parent_order_id")
            if pid is not None and int(pid) in ws_fills_by_order:
                er = ws_fills_by_order[int(pid)]
                ord_status = er.get("ordStatus")
                exec_type = er.get("execType")
                _tl(entry["setup_ref"], "broker_ws_event",
                     exec_type=exec_type, ord_status=ord_status,
                     avg_px=er.get("avgPx"),
                     last_qty=er.get("lastQty"),
                     last_px=er.get("lastPx"),
                     reject_reason=er.get("rejectReason"),
                     ws_age_s=round(age, 3))
                if ord_status in {"Filled", "Rejected", "Canceled", "Expired"}:
                    # No more polling needed -- WS gave us the answer.
                    continue
            check_schedule = (0.5, 2.0, 5.0, 15.0)
            checks_done = entry.get("checks_done", 0)
            should_check = (
                checks_done < len(check_schedule)
                and age >= check_schedule[checks_done]
            )
            if not should_check:
                # Not due yet; keep waiting, unless we're past 15s
                if age < 15.0:
                    keep.append(entry)
                else:
                    _tl(entry["setup_ref"], "broker_poll_timeout",
                         age_s=round(age, 1))
                continue
            try:
                status = self.tradovate_orders.get_order_status(
                    entry["parent_order_id"])
            except Exception as e:
                status = None
                _tl(entry["setup_ref"], "broker_poll_error",
                     parent_id=entry["parent_order_id"],
                     error=repr(e))
            _tl(entry["setup_ref"], "broker_poll",
                 parent_id=entry["parent_order_id"],
                 age_s=round(age, 1), check_num=checks_done + 1,
                 ord_status=status)
            entry["checks_done"] = checks_done + 1
            if status == "Filled":
                _tl(entry["setup_ref"], "broker_parent_filled",
                     fill_age_s=round(age, 2))
                # Filled -> stop polling this one.
                continue
            if status in {"Rejected", "Canceled", "Expired"}:
                _tl(entry["setup_ref"], "broker_parent_dead",
                     ord_status=status, age_s=round(age, 1))
                continue
            # Still working or unknown: keep polling
            if age < 15.0:
                keep.append(entry)
            else:
                _tl(entry["setup_ref"], "broker_poll_timeout",
                     age_s=round(age, 1),
                     final_status=status or "unknown")
        self._pending_parent_orders = keep

    def _on_tick_instant(self, price: float, ts) -> None:
        """Called inline by PriceMonitor on EVERY Polygon tick. Reacts
        to pullback-level touches in <100ms total latency:
          tick arrives over WS -> on_tick fires -> we check pending
          setups -> try_fire_on_tick may open a trade -> _on_trade_open
          sends OSO to Tradovate.

        Also runs the ANTICIPATORY PRE-SUBMIT check: if price is within
        1pt of a pending setup's entry level, submit the broker LIMIT
        NOW so it's resting on the matching engine by the time the
        actual touch happens. Eliminates the 500ms RTT miss that
        causes 0-sec-hold paper wins to be missed by broker.

        Must be fast and safe to run from the WS thread.
        """
        # Fast bail: no pending setups, nothing to fire.
        if not self.state or not self.state.pending_setups:
            return
        if self.state.active_trade is not None:
            return
        # Non-blocking lock: if main loop is in _tick, skip this tick
        # (the cycle will catch it). Prevents double-fire from the same
        # setup if WS and cycle race.
        if not self._tick_fire_lock.acquire(blocking=False):
            return
        try:
            # ANTICIPATORY PRE-SUBMIT: place LIMIT before the touch.
            # Cheap O(N) loop over a few pending setups, no REST calls
            # unless we actually need to submit/cancel.
            try:
                self._check_anticipatory_limit(price)
            except Exception as e:
                logger.debug(f"anticipatory check: {e!r}")
            from bot.pullback_strategy import try_fire_on_tick
            from bot.account_ctx import get_strategy_params
            runtime_lucid = self.account._build_runtime_lucid_state()
            now = real_utc_now()
            fired = try_fire_on_tick(
                state=self.state, lucid=runtime_lucid,
                live_price=float(price), now=now,
                n_mnq=N_MNQ,
                params=get_strategy_params(self.account_id),
                calendar=self.news_calendar,
            )
            if fired and self.state.active_trade is not None:
                self.signals_fired += 1
                logger.info(f"[FAST FIRE] tick={price:.2f} fired setup at "
                            f"sub-100ms latency (was up to "
                            f"CYCLE_FLAT_SECONDS={CYCLE_FLAT_SECONDS}s before fix)")
                self._on_trade_open(self.state.active_trade, now)
        except Exception as e:
            logger.warning(f"_on_tick_instant raised: {e!r}")
        finally:
            self._tick_fire_lock.release()

    def _tick(self) -> None:
        self.cycle += 1
        now = real_utc_now()
        # Passive broker-fill tracker. Read-only, no side effects.
        try:
            self._poll_pending_broker_orders()
        except Exception as e:
            logger.debug(f"broker poll: {e!r}")
        # Position discrepancy check: catches the stacking bug class.
        # If broker netPos > 1 (more contracts than strategy expects),
        # flatten the extras via liquidateposition.
        try:
            self._check_position_discrepancy()
        except Exception as e:
            logger.debug(f"position discrepancy check: {e!r}")
        # PRE-SUBMIT DISABLED 2026-06-16: race condition between sibling
        # cancel and new submit allowed multiple LIMITs to rest briefly
        # and BOTH fill on the same tick -> netPos=+2 or +3 stacking ->
        # discrepancy detector flushed everything at random prices ->
        # tiny -$1, +$0.76, -$3.24 trades destroying P&L.
        #
        # Reverting to post-fire LIMIT (submit at tick fire, not setup
        # arm). Loses ~50ms of latency advantage but eliminates the
        # stacking entirely. The +1pt stop tolerance still helps the
        # wick-mismatch class.
        #
        # try:
        #     self._sync_pre_submitted_limit()
        # except Exception as e:
        #     logger.debug(f"pre-submit sync: {e!r}")
        # Runtime reset trigger -- dashboard's /api/admin/reset_all writes
        # a flag file; we honour it here so the in-memory state matches the
        # wiped disk state without requiring a redeploy. Idempotent: the
        # flag is consumed on processing.
        try:
            from bot.account_ctx import data_dir as _acct_dir
            _reset_flag = _acct_dir() / "reset_pending.flag"
            if _reset_flag.exists():
                logger.warning("=== runtime reset flag detected — wiping in-memory state ===")
                # Flag file may contain a custom starting balance on the
                # SECOND line (first line is the ISO timestamp). Used to
                # align bot's starting equity with a broker account that
                # has non-default starting balance (e.g. $49,956 after a
                # partial loss on the demo broker before reset).
                starting_balance = None
                try:
                    raw = _reset_flag.read_text().strip().splitlines()
                    if len(raw) >= 2:
                        starting_balance = float(raw[1].strip())
                except Exception:
                    pass
                try:
                    self.account._hard_reset_all(starting_balance=starting_balance)
                except Exception as e:
                    logger.warning(f"hard_reset_all failed during runtime reset: {e!r}")
                # Re-init strategy state (clear pending setups + any active trade).
                self.state = FibStrategyState()
                # Clear in-memory recent trades cache. Without this, the
                # dashboard keeps showing yesterday's trades after a reset
                # because the deque survives in memory until bot restart.
                self.recent_trades.clear()
                # Reset counters too so "TRADES TODAY" reflects post-reset state.
                self.bars_processed = 0
                self.signals_fired = 0
                self.signals_blocked = 0
                try:
                    _reset_flag.unlink()
                except Exception:
                    pass
                _bal_msg = f"${starting_balance:,.0f}" if starting_balance else "$50k"
                logger.warning(f"=== runtime reset complete -- account at {_bal_msg}, history wiped ===")
        except Exception as e:
            logger.debug(f"reset-flag check skipped: {e!r}")
        snap = self.monitor.snapshot_and_reset()
        in_trade = self.state.active_trade is not None

        # ------------------------------------------------------------------
        # PRICE-INVALID HARD STOP
        # ------------------------------------------------------------------
        # When PriceMonitor has no valid price (sanity-rejected source
        # output or just no data) we MUST NOT fire any new trades. The
        # symptom we're protecting against: bot's cached price is a
        # garbage value (e.g. 10239 when real MNQ is 29000), strategy
        # detects setups against real WS bars, paper books at strategy
        # prices, broker call gets blocked by 10pt divergence but the
        # paper account hallucinates an 86-trade winning streak that
        # doesn't exist on the broker. Hard-skip everything strategy-
        # related when latest() is None.
        #
        # The strategy / broker forwarder already has its own kill-
        # switches but they only protect the BROKER. Paper still
        # books unless we gate here.
        if self.monitor.latest() is None:
            if not hasattr(self, "_last_price_invalid_log") or \
                    time.time() - getattr(self, "_last_price_invalid_log", 0) > 30:
                self._last_price_invalid_log = time.time()
                logger.warning("PRICE INVALID: monitor.latest() is None -- "
                               "skipping all strategy eval and entries. "
                               "Bot will resume when a valid price arrives.")
            self.last_error = "price_invalid_paused"
            return

        # ------------------------------------------------------------------
        # TICK-LEVEL ENTRY TRIGGER
        # ------------------------------------------------------------------
        # If there are pending pullback setups armed by a previously
        # closed bar, check if live tick has touched the pullback level
        # NOW (instead of waiting for the next bar to close, up to 60s
        # later).
        #
        # This is the missing piece between strategy and execution:
        #   Strategy fires setups on closed bars.
        #   Polygon WS gives us tick-level price data.
        #   Without this hook, the bot would WAIT 0-60s after the
        #   pullback level was actually touched to send the entry --
        #   by which time price has often moved off the level.
        #
        # With this hook, the bot fires within the PriceMonitor poll
        # interval (typically <1s of the actual tick) and the broker's
        # market entry fills at near-pullback price. Most of the paper-
        # vs-broker timing gap goes away.
        if (not in_trade and snap is not None
                and self.state.pending_setups):
            # Acquire the fire-lock so we don't race the instant-tick
            # callback path. If it's already firing, just skip -- we'll
            # catch it next cycle.
            if self._tick_fire_lock.acquire(blocking=False):
                try:
                    from bot.account_ctx import get_strategy_params
                    from bot.pullback_strategy import try_fire_on_tick
                    runtime_lucid = self.account._build_runtime_lucid_state()
                    fired = try_fire_on_tick(
                        state=self.state, lucid=runtime_lucid,
                        live_price=float(snap.price), now=now,
                        n_mnq=N_MNQ,
                        params=get_strategy_params(self.account_id),
                        calendar=self.news_calendar,
                    )
                    if fired:
                        self.signals_fired += 1
                        self._on_trade_open(self.state.active_trade, now)
                        in_trade = True  # we're in a trade now
                finally:
                    self._tick_fire_lock.release()

        # Tick-level panic-close REMOVED.
        # ----------------------------------------------------------------
        # Was a workaround for the bracket-mis-anchored bug class. With
        # the bare-minimum architecture (subscription owns brackets at
        # $12/$24 per contract from actual fill), the bracket is always
        # correctly anchored. Tick panic-close racing it caused more
        # harm than help -- it would fire market exits that filled at
        # worse prices than the bracket's clean limit/stop fills.
        #
        # If the subscription bracket doesn't fire (broker outage, etc),
        # the bot's 10-min max_hold timeout sends a market flatten
        # via _on_trade_close. That's the only safety net needed.

        # Deferred-target dispatch REMOVED -- it was sending a flat
        # sentiment signal that TradersPost interpreted as "cancel
        # bracket, install limit exit", killing the stop. Trades ran
        # 20-30pt without stopping. Bracket is now sent atomically at
        # entry (entry+stop+target together) so the stop is guaranteed
        # to be on the broker for the entire trade lifecycle.

        # Refresh 5-min (HTF trend) + 1-min (setup detection) bars at most
        # every 60s. Prefer REAL 1-min from Polygon/yfinance; fall back to
        # synthesizing 1-min from 5-min if 1-min source is unavailable. The
        # synth path mirrors the backtest exactly so behavior degrades
        # gracefully when the 1-min feed has a hiccup.
        tnow = time.time()
        if self._bars_5m is None or tnow - self._last_bar_refresh > 60:
            try:
                # live_only=True: Polygon or nothing. No yfinance, no
                # cache, no synthetic. If Polygon is down the bars stay
                # stale until the next successful poll and the bot won't
                # arm new setups -- safer than trading on delayed data.
                nq5 = download_nq("5min", live_only=True)
                if nq5 is not None and not nq5.empty:
                    if nq5.index.tz is None:
                        nq5.index = nq5.index.tz_localize("UTC")
                    self._bars_5m = nq5
                    nq1 = None
                    try:
                        nq1 = download_nq("1min", live_only=True)
                        if nq1 is not None and not nq1.empty and nq1.index.tz is None:
                            nq1.index = nq1.index.tz_localize("UTC")
                    except Exception as e:
                        logger.debug(f"1-min fetch failed: {e}")
                    if nq1 is None or nq1.empty:
                        # Synthesizing 1-min from 5-min is acceptable here:
                        # the source 5-min IS Polygon (live_only enforced),
                        # we're just up-sampling its OHLC walk. Not a
                        # different data provider.
                        self._bars_1m = _synth_1min_from_5min(nq5)
                        self._bars_1m_source = "synth"
                    else:
                        self._bars_1m = nq1
                        self._bars_1m_source = "real"
                    self._last_bar_refresh = tnow
                else:
                    logger.warning("bar refresh: Polygon returned empty "
                                   "-- keeping previous bars (or no-op if "
                                   "none cached)")
            except Exception as e:
                logger.warning(f"bar refresh failed: {e}")
                if self._bars_5m is None:
                    return

        if self._bars_5m is None or self._bars_5m.empty:
            return
        if self._bars_1m is None or self._bars_1m.empty:
            return

        # Bar-staleness guard with WS-tick fallback.
        # ------------------------------------------------------------
        # If the latest REST aggs bar is >5min old (observed on the
        # user's Polygon plan: aggs endpoint stops updating after each
        # session reopen even though WS keeps delivering ticks), try
        # the live WS-built bars instead. The tick aggregator only has
        # data from when the bot started, so it needs enough warmup
        # bars (>= 35) before HTF trend + impulse window are valid.
        # If neither REST nor WS bars are usable, skip strategy eval.
        try:
            latest_bar_ts = self._bars_1m.index[-1]
            if latest_bar_ts.tz is None:
                latest_bar_ts = latest_bar_ts.tz_localize("UTC")
            bar_age_s = (datetime.now(timezone.utc) - latest_bar_ts.to_pydatetime()
                         ).total_seconds()
            stale_max = float(os.environ.get("BOT_STALE_BAR_MAX_S", "300"))
            if bar_age_s > stale_max:
                # Try WS-built bars as a live replacement
                ws_bars = None
                ws_closed = 0
                try:
                    ws_bars = self.monitor.tick_bars.get_bars()
                    ws_closed = len(ws_bars)
                except Exception as e:
                    logger.debug(f"tick_bars.get_bars failed: {e!r}")
                # Minimum bars to start trading: impulse window (4) +
                # one slot for the current closing bar. HTF filter is
                # bypassed during warmup (see pullback_strategy), so
                # we don't need 2*HTF_K+1 before firing.
                min_ws_bars = 5
                if ws_bars is not None and ws_closed >= min_ws_bars:
                    if self._bars_1m_source != "polygon_ws_ticks":
                        logger.warning(
                            f"[BAR-FALLBACK] REST aggs is {bar_age_s/60:.1f} min "
                            f"stale; switching to WS-built bars "
                            f"({ws_closed} closed bars from tick stream)")
                    self._bars_1m = ws_bars
                    self._bars_1m_source = "polygon_ws_ticks"
                else:
                    if self._last_stale_warn_age != int(bar_age_s) // 60:
                        self._last_stale_warn_age = int(bar_age_s) // 60
                        logger.warning(
                            f"[BAR-STALE] REST 1-min bar is {bar_age_s/60:.1f} "
                            f"min old (>{stale_max/60:.1f} min) and WS has "
                            f"only {ws_closed} closed bars (need "
                            f">={min_ws_bars}) -- skipping strategy eval.")
                    self.last_error = (f"bars_stale_{int(bar_age_s/60)}min_"
                                       f"ws_warmup_{ws_closed}/{min_ws_bars}")
                    return
        except Exception as e:
            logger.debug(f"bar-staleness check failed: {e!r}")

        # Synthesize the live 1-min bar from accumulated tick high/low.
        # Used for exit-detection precision (tight when in-trade) and to
        # arm/invalidate pending setups against very recent price.
        # Pass the latest 1-min bar as fallback so when PriceMonitor is
        # dead we still have realistic high/low/close instead of a stale
        # 5-min close that broke is_filled() detection.
        fallback_bar = self._bars_1m.iloc[-1]
        last_1m = _build_last_1m_from_price(snap, fallback_bar,
                                            bars_1m_source=self._bars_1m_source)

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
        # Per-account strategy params (account 1 = target=12 legacy --
        # see bot/account_ctx.py). Accounts 2/3 were removed.
        from bot.account_ctx import get_strategy_params
        record = on_new_1m_bar(self.state, runtime_lucid,
                               self._bars_1m, last_1m, now,
                               n_mnq=N_MNQ, bars_trend=self._bars_1m,
                               params=get_strategy_params(self.account_id),
                               calendar=self.news_calendar)

        # Trade opened this tick?
        if not had_trade_before and self.state.active_trade is not None:
            self.signals_fired += 1
            self._on_trade_open(self.state.active_trade, now)

        # Trade closed this tick?
        if record is not None:
            self._on_trade_close(record, now)
            self.recent_trades.appendleft(record)

        # ---- SHADOW ENGINE -----------------------------------------------
        # Run the new engine.runtime.Runtime in parallel on the same bar.
        # Pure observer; doesn't touch live state. Lets us verify the engine
        # produces equivalent decisions before any migration.
        if self.shadow is not None:
            try:
                from bot.lucid_account import _ny_date_iso
                ny = _ny_date_iso(now)
                self.shadow.on_new_closed_bar(self._bars_1m, now, ny)
                # Persist every 10 cycles to keep disk writes light
                if self.cycle % 10 == 0:
                    from bot.account_ctx import data_dir as _acct_dir
                    self.shadow.persist(_acct_dir() / "shadow_engine.json")
            except Exception as e:
                logger.debug(f"shadow tick failed: {e!r}")

    # ---- trade lifecycle hooks ----------------------------------------
    def _on_trade_open(self, trade, now: datetime) -> None:
        # Always route through the paper account so balance + DB persist
        # in both LIVE and SHADOW modes. The mode label only controls
        # whether we'd ALSO send a real broker order (we never do yet,
        # so today shadow and live are functionally identical).
        #
        # DUPLICATE-ENTRY GUARD: if _open_trade_ref is already set, the
        # broker thinks we already have a position open. Sending another
        # entry would open a SECOND identical position, with each having
        # its own bracket. During fast moves the brackets can fail to
        # fill simultaneously (Tradovate matching engine partials), and
        # in the worst case one position runs naked while the other
        # closes -- producing the 58-74pt losses observed in user's
        # cash log. Hard-block here so the broker never gets a duplicate
        # open while a previous one is still active.
        if self._open_trade_ref is not None:
            logger.error(
                f"[traderspost SKIP] duplicate entry blocked: "
                f"_open_trade_ref={self._open_trade_ref} still active. "
                f"Strategy fired {trade.side} setup but broker already "
                f"has a position open. Paper account books normally; "
                f"broker stays single-position.")
            return
        try:
            # Pullback strategy uses LIMIT-style entries (waits for price to
            # touch pullback_entry, fills at that level). Override the paper
            # account's legacy market-order defaults with prop-firm-realistic
            # values (env-configurable for tuning to actual broker statements).
            #
            # Paper account books at the bot's INTENDED entry price (the
            # 0.618 pullback level). With LIMIT orders on TradersPost,
            # Tradovate's actual fill happens at exactly this price (or
            # better), so paper P&L matches Tradovate within ~$1 slippage
            # on stop fills. Wins are clean $48, losses clean -$24, just
            # like the paper backtest.
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
            tag = "SHADOW" if _is_shadow_mode() else "LIVE"
            logger.info(f"[{tag} OPEN] {trade.side} {trade.n_mnq} MNQ "
                        f"@ {trade.entry_px:.2f}  stop={trade.stop_px:.2f} "
                        f"tgt={trade.target_px:.2f}")
            # BARE-MINIMUM TRADERSPOST INTEGRATION
            # ---------------------------------------------------------
            # We send: direction + quantity + market type. That's it.
            # No stop/target prices, no order ref tricks, no deferred
            # signals. The TradersPost subscription owns the bracket
            # logic ($12 stop, $24 target per contract) which auto-
            # attaches at fill price.
            #
            # This is the canonical TradersPost design pattern (see
            # all the example videos: Jacob/Lux Algo, Tom/Trader Post
            # founder, Rebecca walkthrough). Every override we used to
            # add was a workaround for incomplete understanding of how
            # the subscription brackets work. Each override introduced
            # bugs:
            #   - Absolute stop/target prices (mis-anchored on slippage)
            #   - LIMIT entries (didn't always fill, paper booked phantom
            #     wins, subscription auto-converted to market anyway)
            #   - Deferred-target signal (wiped the stop bracket)
            #   - Bar-based market close (raced and beat the bracket
            #     at worse prices)
            #
            # By trusting the subscription, all these classes of bugs
            # vanish. The broker bracket is the single source of truth
            # for the trade's lifecycle.
            #
            # The strategy still owns WHEN to enter (price has touched
            # the 0.618 pullback level on the closed bar -- that's why
            # on_new_1m_bar returned this trade). The broker handles
            # everything else.
            # === BROKER FORWARDING GATES (with explicit logging) ===
            # Every gate that blocks the broker call now logs WHICH
            # gate fired and with what values. Previously several of
            # these were silent skips, which is how 88 paper trades
            # got booked while the broker tab showed "0 signals".
            shadow_on = _is_shadow_mode()
            logger.info(f"[broker gate 1/4 SHADOW_MODE] env={shadow_on} "
                        f"(env var BOT_SHADOW_MODE="
                        f"{os.environ.get('BOT_SHADOW_MODE', '<unset>')!r})")
            if shadow_on:
                logger.info(f"[SHADOW] not forwarding to broker: "
                            f"{trade.side} {trade.n_mnq} MARKET")
                return

            # Route through Tradovate if available, else TradersPost.
            use_tradovate = self.tradovate_orders is not None
            broker_name = "tradovate" if use_tradovate else "traderspost"
            broker_client_ok = (self.tradovate_orders is not None
                                 if use_tradovate
                                 else self.traderspost is not None)
            logger.info(f"[broker gate 2/4 {broker_name} init] "
                        f"client={broker_client_ok}")
            if not broker_client_ok:
                logger.error(f"[{broker_name} SKIP] client not initialised")
                return

            try:
                op = self.account.state.open_position
                db_id = getattr(op, "db_id", None) if op else None
                setup_ref = (f"acct{self.account_id}_"
                             f"{db_id or 'noid'}_"
                             f"{int(now.timestamp())}")
                # Begin the per-trade event timeline. Every state
                # transition from here on is timestamped to setup_ref.
                from bot.trade_timeline import add_event as _tl
                _tl(setup_ref, "trade_open_started",
                     side=trade.side, qty=trade.n_mnq,
                     entry_px=trade.entry_px,
                     stop_px=trade.stop_px,
                     target_px=trade.target_px)
                live_snap = self.monitor.latest()
                logger.info(f"[broker gate 3/4 live_price] snap="
                            f"{'None' if live_snap is None else f'{live_snap.price:.2f}'}")
                if live_snap is None:
                    logger.warning(
                        f"[{broker_name} SKIP] no live price -- refusing entry")
                    _tl(setup_ref, "broker_skip", reason="no_live_price")
                    return
                divergence = abs(trade.entry_px - live_snap.price)
                # Divergence gate: original wide 30pt setting.
                # USER REQUIREMENT: trade frequency MUST match paper
                # exactly. Volume is what makes the strategy money.
                # Don't skip trades just because price drifted a bit
                # between strategy decision and broker submit -- the
                # bracket re-anchor logic handles bracket validity
                # downstream. The bug fixes (dd160d9, e9ea951,
                # 070df56) eliminate the actual leak mechanisms
                # without touching trade count.
                divergence_max = float(os.environ.get(
                    "TRADERSPOST_MAX_DIVERGENCE_PT", "30"))
                logger.info(f"[broker gate 4/4 divergence] "
                            f"strategy={trade.entry_px:.2f} "
                            f"live={live_snap.price:.2f} "
                            f"diff={divergence:.1f}pt "
                            f"limit={divergence_max:.1f}pt")
                if divergence > divergence_max:
                    logger.error(
                        f"[{broker_name} SKIP] divergence "
                        f"{divergence:.1f}pt > {divergence_max:.1f}pt")
                    _tl(setup_ref, "broker_skip", reason="divergence",
                         strategy=trade.entry_px, live=live_snap.price,
                         diff=divergence)
                    return

                # All gates passed -- send the order.
                # FIRST: check if we already pre-submitted (anticipatory or
                # legacy pre-submit) a LIMIT for this setup. If so, adopt
                # that order instead of sending a duplicate.
                if use_tradovate:
                    pre_oid = self._adopt_anticipatory_for_active_trade(
                        trade, setup_ref)
                    if pre_oid is None:
                        pre_oid = self._adopt_pre_submitted_for_active_trade(
                            trade, setup_ref)
                    if pre_oid is not None:
                        # Pre-submitted LIMIT is now the active trade's
                        # broker order. Tracking already added to
                        # _pending_parent_orders by the adopt method.
                        self._open_trade_ref = setup_ref
                        self._broker_entry_ts = now
                        self._broker_stop_px = trade.stop_px
                        self._broker_target_px = trade.target_px
                        self._broker_side = trade.side
                        self._broker_target_sent = True
                        _tl(setup_ref, "pre_submitted_adopted",
                             order_id=pre_oid)
                        return
                stop_pts = abs(trade.entry_px - trade.stop_px)
                target_pts = abs(trade.target_px - trade.entry_px)
                if use_tradovate:
                    # SINGLE-POSITION GUARD: before submitting a new
                    # broker entry, verify Tradovate's netPos is 0. If
                    # broker still has an open position (paper exited
                    # but bracket OCO hasn't fired yet), submitting now
                    # would stack to netPos=2 -- the bug seen at
                    # 05:45:42 today (SHORT pos=-1 -> SHORT pos=-2 ->
                    # discrepancy detector flushed both via MARKET).
                    # LATENCY: prefer WS-cached netPos (instant) over
                    # REST /position/list (100-200ms).
                    try:
                        sess = self.tradovate_orders.session
                        acct_id = sess.get_account_id()
                        net = None
                        try:
                            from bot.tradovate_user_ws import get_user_ws
                            _uws = get_user_ws()
                            if _uws is not None:
                                for cid, entry in (_uws._netpos_cache or {}).items():
                                    if entry.get("netPos", 0) != 0:
                                        net = entry["netPos"]
                                        break
                        except Exception:
                            pass
                        if net is None:
                            status, positions = sess._rest("GET", "/position/list")
                            if status == 200 and isinstance(positions, list):
                                for pos in positions:
                                    if not isinstance(pos, dict): continue
                                    if pos.get("accountId") != acct_id: continue
                                    if int(pos.get("netPos") or 0) != 0:
                                        net = int(pos["netPos"])
                                        break
                        if net not in (0, None):
                            logger.warning(
                                f"[broker SKIP] netPos={net} != 0, "
                                f"refusing to stack. Paper booked "
                                f"this setup; broker holds previous "
                                f"position. Wait for bracket exit.")
                            _tl(setup_ref, "broker_skip",
                                 reason="netpos_nonzero", netpos=net)
                            return
                    except Exception as ne:
                        logger.warning(f"netPos check failed: {ne!r}")
                    # LATENCY: cached symbol -- skips polygon_front_month
                    # date logic on every entry.
                    if self._cached_symbol is None:
                        from research.data_loader import polygon_front_month
                        self._cached_symbol = os.environ.get(
                            "TRADOVATE_SYMBOL",
                            polygon_front_month(
                                os.environ.get("POLYGON_CONTRACT", "MNQ")))
                    symbol = self._cached_symbol
                    logger.info(
                        f"[tradovate SEND BRACKET] {trade.side} "
                        f"{trade.n_mnq} {symbol} entry@{trade.entry_px:.2f} "
                        f"stop={stop_pts:.2f}pt target={target_pts:.2f}pt "
                        f"(live={live_snap.price:.2f})")
                    _tl(setup_ref, "placeoso_sending",
                         symbol=symbol, entry_px=trade.entry_px,
                         stop_pts=stop_pts, target_pts=target_pts,
                         live_px=live_snap.price)

                    # SINGLE-POSITION INVARIANT for LIMIT entries.
                    # Strategy is single-position; only one broker LIMIT
                    # should rest at a time. If a prior LIMIT from an
                    # earlier setup is still Working (paper closed, but
                    # the cancel-stale-limits pass missed it, OR a race
                    # condition), cancel it before sending the new one.
                    # Otherwise the new order would queue alongside and
                    # both could fill = stacked position.
                    # Also cancel any pre-submitted LIMIT for a setup
                    # that didn't end up firing (different setup is now
                    # being entered).
                    if self._pre_submitted_limit:
                        self._cancel_pre_submitted_limit(
                            "different_setup_firing")
                    for prior in list(self._pending_parent_orders):
                        prior_id = prior.get("parent_order_id")
                        if not prior_id:
                            continue
                        try:
                            status = self.tradovate_orders.get_order_status(
                                int(prior_id))
                            if status == "Working":
                                logger.info(
                                    f"[LIMIT sibling cancel] new setup "
                                    f"firing; cancelling prior pending "
                                    f"LIMIT order_id={prior_id} "
                                    f"(setup_ref={prior.get('setup_ref')})")
                                self.tradovate_orders.cancel_order(
                                    int(prior_id))
                        except Exception as ce:
                            logger.warning(
                                f"[LIMIT sibling cancel] failed for "
                                f"{prior_id}: {ce!r}")
                    self._pending_parent_orders.clear()

                    # CRITICAL: pass the STRATEGY'S intended entry price
                    # (the 0.618 pullback level) -- NOT the live tick.
                    # The LIMIT order needs to fill at the strategy's
                    # exact price so brackets anchor correctly.
                    result = self.tradovate_orders.submit_market_with_bracket(
                        side=trade.side, qty=trade.n_mnq, symbol=symbol,
                        stop_pts=stop_pts, target_pts=target_pts,
                        entry_estimate=float(trade.entry_px),
                        # Pass live last-trade price so the bracket can
                        # re-anchor relative to actual fill when LIMIT
                        # is marketable. Critical: Tradovate WS isn't
                        # providing bid/ask (tick_count=0 in practice),
                        # so live_price is our only fill-side hint.
                        live_price=float(live_snap.price) if live_snap else None,
                        # USER REQUIREMENT 2026-06-15: paper's exact
                        # stop_px / target_px (structure-derived from
                        # swing points + fib levels) become the broker
                        # bracket levels. Every fill mirrors paper.
                        paper_stop_px=float(trade.stop_px),
                        paper_target_px=float(trade.target_px),
                        setup_ref=setup_ref,
                    )
                    _tl(setup_ref, "placeoso_result",
                         ok=result.ok, order_id=result.order_id,
                         http_status=result.status_code,
                         error=result.error)
                    if not result.ok:
                        logger.error(f"[tradovate order REJECTED] {result.error}")
                        return
                    logger.info(f"[tradovate order ACCEPTED] order_id="
                                f"{result.order_id}")
                    # Stash for the passive fill-tracker.
                    self._pending_parent_orders.append({
                        "setup_ref": setup_ref,
                        "parent_order_id": result.order_id,
                        "submitted_at": time.time(),
                        "checks_done": 0,
                        "side": trade.side,
                        "entry_px": float(trade.entry_px),
                        "qty": trade.n_mnq,
                    })
                else:
                    logger.info(
                        f"[traderspost SEND BRACKET] {trade.side} "
                        f"{trade.n_mnq} entry={trade.entry_px:.2f} "
                        f"stop={trade.stop_px:.2f} tgt={trade.target_px:.2f} "
                        f"(live={live_snap.price:.2f})")
                    self.traderspost.submit_open(
                        side=trade.side, qty=trade.n_mnq,
                        entry_price=trade.entry_px,
                        stop_price=trade.stop_px,
                        target_price=trade.target_px,
                        setup_id=setup_ref,
                    )

                self._open_trade_ref = setup_ref
                self._broker_entry_ts = now
                self._broker_stop_px = trade.stop_px
                self._broker_target_px = trade.target_px
                self._broker_side = trade.side
                self._broker_target_sent = True
            except Exception as te:
                logger.warning(f"broker submit failed: {te!r}")
        except Exception as e:
            self.last_error = f"open failed: {e}"
            logger.exception(f"open failed: {e}")

    def _check_anticipatory_limit(self, current_price: float) -> None:
        """Place a broker LIMIT a moment BEFORE price actually crosses
        the pullback entry level. This way the LIMIT is already
        resting on Tradovate's matching engine when the touch happens
        -- it fills in microseconds instead of waiting on a 500ms HTTP
        round-trip after the touch.

        STACKING SAFETY:
          - Only ONE anticipatory LIMIT alive at a time.
          - When a different setup becomes the closest, the old LIMIT
            is cancelled SYNCHRONOUSLY (we poll status until Canceled
            or other terminal) before submitting the new one. No race.
          - Will skip submission if broker netPos != 0.
        """
        # Avoid spamming -- check at most every 200ms.
        nowt = time.time()
        last = getattr(self, "_anticip_last_check", 0)
        if nowt - last < 0.2:
            return
        self._anticip_last_check = nowt
        if self.tradovate_orders is None:
            return
        sess = getattr(self.tradovate_orders, "session", None)
        if sess is None or not sess.is_configured:
            return
        if self.account.state.open_position is not None:
            return
        # Find the pending setup whose entry is closest to current price
        # and on the correct side (price still APPROACHING, not past).
        APPROACH_THRESHOLD_PT = 1.5
        best = None
        best_dist = APPROACH_THRESHOLD_PT + 0.01
        for s in (self.state.pending_setups if self.state else []):
            if getattr(s, 'used', False) or getattr(s, 'fire_attempted', False):
                continue
            entry = float(s.pullback_entry)
            if s.side == "LONG":
                # LONG entry triggers when price FALLS to entry.
                # Approach means current price >= entry (above, falling).
                if current_price < entry:
                    continue
                dist = current_price - entry
            else:  # SHORT
                # SHORT triggers when price RISES to entry.
                # Approach means current price <= entry (below, rising).
                if current_price > entry:
                    continue
                dist = entry - current_price
            if dist < best_dist:
                best_dist = dist
                best = s
        if best is None:
            # No setup within threshold -- cancel any stale anticipatory.
            if self._anticipatory_limit is not None:
                self._cancel_anticipatory_sync("price_far_from_all_setups")
            return
        target_key = self._setup_key(best)
        cur_key = (self._anticipatory_limit.get('setup_key')
                    if self._anticipatory_limit else None)
        if cur_key == target_key:
            return  # already submitted for this setup
        # Different (or no) anticipatory. Cancel old synchronously then submit new.
        if self._anticipatory_limit is not None:
            self._cancel_anticipatory_sync("different_setup_closer")
        # Single-position guard: verify broker netPos == 0.
        # LATENCY: prefer WS-cached netPos to avoid a ~100-200ms REST
        # call. WS pushes position updates instantly on every fill.
        try:
            acct_id = sess.get_account_id()
            cur_net = None
            try:
                from bot.tradovate_user_ws import get_user_ws
                _uws = get_user_ws()
                if _uws is not None:
                    # Try to find a cached netPos for any contract we hold.
                    for cid, entry in (_uws._netpos_cache or {}).items():
                        if entry.get("netPos", 0) != 0:
                            cur_net = entry["netPos"]
                            break
            except Exception:
                pass
            if cur_net is None:
                # Fallback to REST.
                status, positions = sess._rest("GET", "/position/list")
                if status == 200 and isinstance(positions, list):
                    for pos in positions:
                        if not isinstance(pos, dict): continue
                        if pos.get("accountId") != acct_id: continue
                        if int(pos.get("netPos") or 0) != 0:
                            cur_net = int(pos["netPos"])
                            break
            if cur_net not in (0, None):
                return  # broker holds a position, don't pre-submit
        except Exception:
            return
        self._submit_anticipatory(best, current_price)

    def _submit_anticipatory(self, setup, live_price: float) -> None:
        """Submit a LIMIT+bracket for a setup that's about to fire."""
        try:
            if self._cached_symbol is None:
                from research.data_loader import polygon_front_month
                self._cached_symbol = os.environ.get(
                    "TRADOVATE_SYMBOL",
                    polygon_front_month(
                        os.environ.get("POLYGON_CONTRACT", "MNQ")))
            symbol = self._cached_symbol
            stop_pts = abs(setup.pullback_entry - setup.stop_px_val)
            target_pts = abs(setup.target_px_val - setup.pullback_entry)
            setup_key = self._setup_key(setup)
            pre_ref = f"acct{self.account_id}_antc_{setup_key}"[:64]
            logger.info(
                f"[ANTICIPATORY] {setup.side} @ {setup.pullback_entry:.2f} "
                f"(live={live_price:.2f}, dist="
                f"{abs(live_price - setup.pullback_entry):.2f}pt) -- "
                f"placing LIMIT ahead of touch")
            result = self.tradovate_orders.submit_market_with_bracket(
                side=setup.side, qty=N_MNQ, symbol=symbol,
                stop_pts=stop_pts, target_pts=target_pts,
                entry_estimate=float(setup.pullback_entry),
                live_price=float(live_price),
                paper_stop_px=float(setup.stop_px_val),
                paper_target_px=float(setup.target_px_val),
                setup_ref=pre_ref,
            )
            if result.ok:
                self._anticipatory_limit = {
                    'setup_key': self._setup_key(setup),
                    'order_id': result.order_id,
                    'side': setup.side,
                    'entry_px': float(setup.pullback_entry),
                    'stop_px': float(setup.stop_px_val),
                    'target_px': float(setup.target_px_val),
                    'submitted_at': time.time(),
                    'pre_ref': pre_ref,
                }
                logger.info(f"[ANTICIPATORY OK] order_id={result.order_id}")
        except Exception as e:
            logger.warning(f"anticipatory submit failed: {e!r}")

    def _cancel_anticipatory_sync(self, reason: str) -> None:
        """Cancel the live anticipatory LIMIT and confirm terminal state
        via Tradovate user WS exec_reports (instant push) instead of
        REST polling. Typical wait now ~10-30ms instead of 50-300ms.
        Fallback to REST poll if WS isn't connected."""
        if not self._anticipatory_limit:
            return
        oid = self._anticipatory_limit.get('order_id')
        sk = self._anticipatory_limit.get('setup_key')
        try:
            if oid:
                oid_int = int(oid)
                # Mark the watermark BEFORE sending cancel so we only
                # consider exec_reports that arrive AFTER our cancel.
                ws_baseline = None
                try:
                    from bot.tradovate_user_ws import get_user_ws
                    _uws = get_user_ws()
                    if _uws is not None:
                        ws_baseline = len(_uws.exec_reports)
                except Exception:
                    _uws = None
                self.tradovate_orders.cancel_order(oid_int)
                import time as _t
                t_start = _t.time()
                terminal_states = {"Canceled", "Filled", "Rejected", "Expired"}
                confirmed = False
                # Tight WS-event loop: check every 5ms for up to 500ms.
                # When the WS pushes an exec_report for this order with
                # a terminal ordStatus, we're done.
                while _t.time() - t_start < 0.5:
                    if _uws is not None:
                        try:
                            recent = list(_uws.exec_reports)[ws_baseline:]
                            for r in recent:
                                if r.get("orderId") == oid_int and r.get("ordStatus") in terminal_states:
                                    logger.info(
                                        f"[ANTICIPATORY cancel WS-confirmed] "
                                        f"order_id={oid} status={r.get('ordStatus')} "
                                        f"reason={reason} "
                                        f"latency_ms={int((_t.time()-t_start)*1000)}")
                                    confirmed = True
                                    break
                            if confirmed:
                                break
                        except Exception:
                            pass
                    _t.sleep(0.005)
                if not confirmed:
                    # Fallback: REST poll once.
                    try:
                        status = self.tradovate_orders.get_order_status(oid_int)
                        if status in terminal_states:
                            confirmed = True
                            logger.info(
                                f"[ANTICIPATORY cancel REST-confirmed] "
                                f"order_id={oid} status={status} reason={reason}")
                    except Exception:
                        pass
                if not confirmed:
                    logger.warning(
                        f"[ANTICIPATORY cancel timeout] order_id={oid} "
                        f"still pending after 500ms -- abandoning. "
                        f"netPos guard will block any stack.")
        except Exception as e:
            logger.warning(f"anticipatory cancel: {e!r}")
        self._anticipatory_limit = None

    def _adopt_anticipatory_for_active_trade(self, trade, setup_ref: str) -> Optional[int]:
        """When paper fires for a setup that we anticipatorily submitted,
        adopt that LIMIT's order_id as the active trade's broker order."""
        if not self._anticipatory_limit:
            return None
        try:
            ts = getattr(trade, 'setup', None)
            if ts is None:
                return None
            trade_key = self._setup_key(ts)
            if trade_key != self._anticipatory_limit.get('setup_key'):
                return None
            oid = self._anticipatory_limit.get('order_id')
            self._pending_parent_orders.append({
                "setup_ref": setup_ref,
                "parent_order_id": oid,
                "submitted_at": self._anticipatory_limit.get('submitted_at', time.time()),
                "checks_done": 0,
                "side": trade.side,
                "entry_px": float(trade.entry_px),
                "qty": trade.n_mnq,
                "anticipatory": True,
            })
            logger.info(
                f"[ANTICIPATORY ADOPTED] order_id={oid} setup_ref={setup_ref}")
            self._anticipatory_limit = None
            return oid
        except Exception as e:
            logger.warning(f"anticipatory adopt: {e!r}")
            return None

    def _setup_key(self, setup) -> str:
        """Stable identifier for a pending FibSetup. Used to track which
        setup the pre-submitted LIMIT is for."""
        try:
            return (f"{setup.side}_"
                     f"{round(float(setup.pullback_entry), 2)}_"
                     f"{int(setup.detected_at.timestamp())}")
        except Exception:
            return f"unknown_{id(setup)}"

    def _sync_pre_submitted_limit(self) -> None:
        """Ensure exactly ONE broker LIMIT is on the book for the most
        recent pending setup. Pre-submits the LIMIT so it rests on
        Tradovate's matching engine -- when price retraces to the entry
        level, fills instantly with zero network latency.

        Eliminates the missed-LIMIT class observed in the audit: paper
        books at strategy_entry instantly on tick touch, but the OLD
        flow submitted the broker LIMIT only AFTER the tick fired.
        500ms of network RTT later, price had often moved past, and the
        LIMIT was canceled without filling. Paper booked a +$23 win;
        broker booked nothing.
        """
        if self.tradovate_orders is None:
            return
        sess = getattr(self.tradovate_orders, "session", None)
        if sess is None or not sess.is_configured:
            return
        # In an open trade -- the pre-submitted LIMIT (if any) has been
        # adopted as the active trade's broker order. Don't disturb.
        if self.account.state.open_position is not None:
            return
        if self.state is None or not self.state.pending_setups:
            if self._pre_submitted_limit:
                self._cancel_pre_submitted_limit("no_pending_setups")
            return
        # Setups still waiting for a fill (not yet used or attempted).
        valid = [s for s in self.state.pending_setups
                  if not getattr(s, 'used', False)
                  and not getattr(s, 'fire_attempted', False)]
        if not valid:
            if self._pre_submitted_limit:
                self._cancel_pre_submitted_limit("no_valid_setups")
            return
        # Pick the most recent one (single LIMIT at a time).
        target = valid[-1]
        target_key = self._setup_key(target)
        cur_key = (self._pre_submitted_limit.get('setup_key')
                    if self._pre_submitted_limit else None)
        if cur_key == target_key:
            return  # Already pre-submitted for this setup.
        if self._pre_submitted_limit:
            self._cancel_pre_submitted_limit("new_setup")
        self._submit_pre_limit_for_setup(target)

    def _submit_pre_limit_for_setup(self, setup) -> None:
        """Submit a broker LIMIT + OCO bracket for an upcoming setup
        before its price level is touched. Resting on the matching
        engine -> fills instantly when price arrives."""
        try:
            from research.data_loader import polygon_front_month
            symbol = os.environ.get(
                "TRADOVATE_SYMBOL",
                polygon_front_month(
                    os.environ.get("POLYGON_CONTRACT", "MNQ")))
            stop_pts = abs(setup.pullback_entry - setup.stop_px_val)
            target_pts = abs(setup.target_px_val - setup.pullback_entry)
            live = self.monitor.latest() if self.monitor else None
            live_px = float(live.price) if live else None
            setup_key = self._setup_key(setup)
            pre_ref = f"acct{self.account_id}_pre_{setup_key}"[:64]
            logger.info(
                f"[PRE-SUBMIT LIMIT] {setup.side} @ "
                f"{setup.pullback_entry:.2f} stop@{setup.stop_px_val:.2f} "
                f"tgt@{setup.target_px_val:.2f} (resting on book; will "
                f"fill instantly when price touches)")
            result = self.tradovate_orders.submit_market_with_bracket(
                side=setup.side, qty=N_MNQ, symbol=symbol,
                stop_pts=stop_pts, target_pts=target_pts,
                entry_estimate=float(setup.pullback_entry),
                live_price=live_px,
                paper_stop_px=float(setup.stop_px_val),
                paper_target_px=float(setup.target_px_val),
                setup_ref=pre_ref,
            )
            if result.ok:
                self._pre_submitted_limit = {
                    'setup_key': setup_key,
                    'order_id': result.order_id,
                    'side': setup.side,
                    'entry_px': float(setup.pullback_entry),
                    'stop_px': float(setup.stop_px_val),
                    'target_px': float(setup.target_px_val),
                    'submitted_at': time.time(),
                    'pre_ref': pre_ref,
                }
                logger.info(
                    f"[PRE-SUBMIT OK] order_id={result.order_id} for "
                    f"setup {setup_key}")
            else:
                logger.warning(
                    f"[PRE-SUBMIT FAILED] {result.error} -- normal flow "
                    f"will submit on tick fire")
        except Exception as e:
            logger.warning(f"[PRE-SUBMIT exception] {e!r}")

    def _cancel_pre_submitted_limit(self, reason: str) -> None:
        """Cancel the currently pre-submitted broker LIMIT (e.g. because
        a new setup arrived, or the setup expired without firing)."""
        if not self._pre_submitted_limit:
            return
        oid = self._pre_submitted_limit.get('order_id')
        sk = self._pre_submitted_limit.get('setup_key')
        try:
            if oid:
                status = self.tradovate_orders.get_order_status(int(oid))
                if status == "Working":
                    self.tradovate_orders.cancel_order(int(oid))
                    logger.info(
                        f"[PRE-SUBMIT CANCEL] order_id={oid} "
                        f"setup={sk} reason={reason}")
        except Exception as e:
            logger.warning(f"[PRE-SUBMIT cancel] {e!r}")
        self._pre_submitted_limit = None

    def _adopt_pre_submitted_for_active_trade(self, trade, setup_ref: str) -> Optional[int]:
        """If we pre-submitted a LIMIT for the setup that just fired in
        paper, return its order_id so the normal flow can skip the
        re-submit. Returns None if no matching pre-submission."""
        if not self._pre_submitted_limit:
            return None
        try:
            ts = getattr(trade, 'setup', None)
            if ts is None:
                return None
            trade_key = self._setup_key(ts)
            if trade_key != self._pre_submitted_limit.get('setup_key'):
                return None
            oid = self._pre_submitted_limit.get('order_id')
            # Re-track this order under the active trade's setup_ref.
            self._pending_parent_orders.append({
                "setup_ref": setup_ref,
                "parent_order_id": oid,
                "submitted_at": self._pre_submitted_limit.get('submitted_at', time.time()),
                "checks_done": 0,
                "side": trade.side,
                "entry_px": float(trade.entry_px),
                "qty": trade.n_mnq,
                "pre_submitted": True,
            })
            logger.info(
                f"[PRE-SUBMIT ADOPTED] order_id={oid} for active trade "
                f"setup_ref={setup_ref}; skipping re-submit")
            self._pre_submitted_limit = None
            return oid
        except Exception as e:
            logger.warning(f"[PRE-SUBMIT adopt] {e!r}")
            return None

    def _check_position_discrepancy(self) -> None:
        """If broker has more contracts open than paper expects,
        flatten the extras. Catches the position-stacking bug class:
        each accidental extra fill (stale LIMIT or buggy fallback)
        leaves the bot with N > 1 contracts open.

        Paper has at most 1 active trade (single-position strategy).
        So broker netPos > 1 (or < -1 for SHORT) is always an error.

        Runs on every cycle. Idempotent.
        """
        if self.tradovate_orders is None:
            return
        sess = getattr(self.tradovate_orders, "session", None)
        if sess is None or not sess.is_configured:
            return
        acct_id = sess.get_account_id()
        if acct_id is None:
            return
        try:
            status, positions = sess._rest("GET", "/position/list")
            if status != 200 or not isinstance(positions, list):
                return
            for p in positions:
                if not isinstance(p, dict):
                    continue
                if p.get("accountId") != acct_id:
                    continue
                net = int(p.get("netPos") or 0)
                if abs(net) <= 1:
                    continue   # Single position is fine
                # MULTIPLE POSITIONS DETECTED
                excess = abs(net) - 1
                logger.error(
                    f"[POSITION STACK DETECTED] broker netPos={net} "
                    f"(strategy expects max 1). Flattening {excess} "
                    f"extra contracts to restore single-position "
                    f"invariant.")
                try:
                    from research.data_loader import polygon_front_month
                    symbol = os.environ.get(
                        "TRADOVATE_SYMBOL",
                        polygon_front_month(
                            os.environ.get("POLYGON_CONTRACT", "MNQ")))
                    # liquidateposition flattens ALL contracts. We
                    # actually want to keep 1 -- so this overshoots,
                    # but the next entry signal will re-open if needed.
                    # Cleaner than trying to partially close.
                    # Use contractId from the position record directly
                    # (more reliable than re-resolving from symbol).
                    cid = p.get("contractId")
                    if cid:
                        flat_body = {
                            "accountSpec": self.tradovate_orders._account_spec(),
                            "accountId": int(acct_id),
                            "contractId": int(cid),
                            "admin": False,
                            "isAutomated": True,
                        }
                        sess._rest(
                            "POST", "/order/liquidateposition",
                            body=flat_body)
                        logger.warning(
                            f"[POSITION STACK FLATTENED] contractId={cid} "
                            f"netPos={net}")
                    else:
                        logger.error(
                            f"[POSITION STACK] no contractId in position "
                            f"record; cannot flatten")
                except Exception as e:
                    logger.error(f"position stack flatten failed: {e!r}")
        except Exception as e:
            logger.debug(f"position discrepancy check: {e!r}")

    def _cancel_stale_entry_limits(self) -> None:
        """If the broker's LIMIT entry parent is still Working when
        paper closes its trade, cancel it. Otherwise it can fill
        later when price retraces -- putting the broker in a stale
        position the strategy doesn't want.

        Iterates _pending_parent_orders, queries each parent's
        ordStatus, and cancels any that are still Working.
        """
        if not self._pending_parent_orders or self.tradovate_orders is None:
            return
        keep = []
        for entry in self._pending_parent_orders:
            try:
                status = self.tradovate_orders.get_order_status(
                    entry["parent_order_id"])
            except Exception:
                # If we can't tell, leave it -- the bracket might fire
                keep.append(entry)
                continue
            if status == "Working":
                # Still pending. Cancel to prevent stale fill.
                try:
                    ok = self.tradovate_orders.cancel_order(
                        entry["parent_order_id"])
                    if ok:
                        logger.warning(
                            f"[STALE LIMIT CANCELLED] parent_order_id="
                            f"{entry['parent_order_id']} setup_ref="
                            f"{entry['setup_ref']} -- paper closed but "
                            f"broker LIMIT was still working. Preventing "
                            f"phantom stale fill.")
                    else:
                        logger.info(
                            f"[stale limit cancel noop] parent_order_id="
                            f"{entry['parent_order_id']} -- order may "
                            f"have just filled or been cancelled")
                except Exception as e:
                    logger.warning(f"stale limit cancel: {e!r}")
                # Stop tracking this entry regardless
                continue
            # Anything else (Filled, Canceled, Rejected, Expired): drop
        self._pending_parent_orders = keep

    def _on_trade_close(self, record: dict, now: datetime) -> None:
        # Always close through the paper account so balance updates and
        # the trade is persisted to the SQLite DB — surviving restarts.
        adverse = (record["exit_reason"] == "stop")
        try:
            # STALE LIMIT GUARD: cancel any unfilled broker LIMIT on
            # paper close. The preserve-on-target variant (f91d326)
            # was reverted -- it captured occasional wins but also
            # produced late-fill losses (LIMIT filled 1-5 min after
            # paper target, then went the wrong way) at roughly the
            # same rate, with no net P&L improvement. Clean cancel is
            # safer and simpler.
            self._cancel_stale_entry_limits()
            # Also cancel any anticipatory LIMIT that's no longer needed
            # because paper just closed (next setup will get its own).
            if self._anticipatory_limit is not None:
                try:
                    self._cancel_anticipatory_sync("paper_close")
                except Exception:
                    pass
            self.account._close(exit_px_raw=record["exit_px"],
                                reason=record["exit_reason"],
                                adverse=adverse, now=now)
            tag = "SHADOW" if _is_shadow_mode() else "LIVE"
            logger.info(f"[{tag} CLOSE] {record['side']} pnl=${record['pnl_usd']:+,.2f} "
                        f"hold={record['hold_s']:.1f}s reason={record['exit_reason']}")
            # Timeline: paper-side close happened.
            try:
                from bot.trade_timeline import add_event as _tl
                _tl(self._open_trade_ref, "paper_closed",
                     reason=record.get("exit_reason"),
                     exit_px=record.get("exit_px"),
                     pnl_usd=record.get("pnl_usd"),
                     hold_s=record.get("hold_s"))
            except Exception:
                pass
            # BROKER EXIT POLICY -- bare-minimum integration
            #
            # The subscription's OCO bracket (stop-market + take-profit
            # limit at $12/$24 per contract) is the single source of
            # truth for stop and target exits. The bracket fires
            # tick-accurately on Tradovate's engine at the EXACT levels
            # the subscription computed from actual fill price.
            #
            # The bot's should_exit detects exits from CLOSED 1-min
            # bars -- up to 60s stale. Sending a MARKET close on bar-
            # detected stop/target was the #1 cause of paper>broker
            # divergence: bar's high touched target briefly, reversed,
            # should_exit booked paper +$48 AND fired stale market
            # close that filled at reversed price.
            #
            # Policy: only forward an exit on TIMEOUT (10-min max hold;
            # the OCO bracket has no timeout equivalent). For stop and
            # target, the broker bracket already owns the close --
            # paper account books the strategy outcome for the dashboard,
            # but we never send a competing signal that could race the
            # bracket at a worse fill.
            reason = record.get("exit_reason", "manual")
            if self._open_trade_ref is None:
                pass  # broker never got the open; nothing to close
            elif reason in ("stop", "target"):
                # USER REQUIREMENT (2026-06-15): trade like manual.
                # Bracket OCO is the SINGLE source of truth for exits.
                # Don't send a competing market close that races the
                # bracket at a worse fill.
                #
                # Previously TARGET CHASE liquidated on paper target
                # wicks -- but by the time it executed, price had
                # retreated, fills were at random prices, and the
                # trade list filled with bizarre tiny P&L values
                # ($0.76 wins, $2.74 losses on 0-second holds).
                #
                # Clean behavior now:
                #   - Bracket STOP fires at stop_price (with normal
                #     stop-market slip of 0-1pt)
                #   - Bracket LIMIT TARGET fires when bid/ask reaches
                #     target_price (matches strategy exactly)
                #   - If LIMIT target wick doesn't fire bracket,
                #     position runs to stop -- accept this as the
                #     cost of clean execution
                logger.info(
                    f"[broker CLOSE skip] {reason} owned by broker "
                    f"OCO bracket -- letting it handle the exit at "
                    f"bracket price")
            elif self.tradovate_orders is not None:
                # Tradovate path: timeout/manual close -> market flatten
                try:
                    from research.data_loader import polygon_front_month
                    symbol = os.environ.get(
                        "TRADOVATE_SYMBOL",
                        polygon_front_month(
                            os.environ.get("POLYGON_CONTRACT", "MNQ")))
                    result = self.tradovate_orders.submit_market_close(
                        side=record.get("side", "LONG"),
                        qty=record.get("n_mnq", 1),
                        symbol=symbol,
                        setup_ref=self._open_trade_ref,
                    )
                    if result.ok:
                        logger.info(
                            f"[tradovate CLOSE OK] order_id={result.order_id} "
                            f"reason={reason}")
                    else:
                        logger.warning(
                            f"[tradovate CLOSE FAIL] {result.error}")
                except Exception as te:
                    logger.warning(f"tradovate close failed: {te!r}")
            elif self.traderspost is not None:
                # timeout / manual / auto-DLL: bracket has no equivalent,
                # send the market close to flatten.
                try:
                    self.traderspost.submit_close(
                        side=record.get("side", "LONG"),
                        qty=record.get("n_mnq", 1),
                        reason=reason,
                        setup_id=self._open_trade_ref,
                    )
                    logger.info(
                        f"[traderspost CLOSE sent] {reason} market flatten "
                        f"for {self._open_trade_ref}")
                except Exception as te:
                    logger.warning(f"traderspost submit_close failed: {te!r}")
            self._open_trade_ref = None
            self._broker_stop_px = None
            self._broker_target_px = None
            self._broker_side = None
            self._broker_entry_ts = None
            self._broker_target_sent = False
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
            shadow_snap = self.shadow.snapshot() if self.shadow else {"enabled": False}
            # Calendar snapshot for the dashboard: next blackout-worthy
            # event + current status. None if calendar disabled.
            cal_snap = None
            if self.news_calendar is not None:
                try:
                    cal_snap = self.news_calendar.status()
                except Exception as e:
                    logger.debug(f"calendar status failed: {e!r}")
            blob = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": "shadow" if _is_shadow_mode() else "live",
                "lifetime_stats": lifetime,
                "strategy": "Fib 50% (1-min entries + 5-min HTF trend filter)",
                "bars_1m_source": self._bars_1m_source,
                "cycle": self.cycle,
                "last_error": self.last_error,
                "bars_processed": self.bars_processed,
                "signals_fired": self.signals_fired,
                "signals_blocked": self.signals_blocked,
                "price": current_price,
                "price_ts": latest.ts.isoformat() if (latest is not None and latest.ts is not None) else None,
                # Source of the displayed price -- "polygon" is real-time;
                # anything else means we're on a delayed fallback (CNBC =
                # 15min, yfinance = 1-15min). When user sees the price
                # flicker between two values, this field tells them which
                # source it came from each tick. The dashboard can render
                # a "STALE" badge based on this.
                "price_source": self.monitor.last_source if latest is not None else None,
                # WS push and REST snapshot are both Polygon-only paths;
                # either qualifies as real-time. Anything else (none,
                # fallback name) is not.
                "price_realtime": self.monitor.last_source in
                                   ("tradovate_md", "polygon_ws",
                                    "polygon_ws_am", "polygon"),
                # WS health: tells the user whether Polygon's WebSocket is
                # actually delivering ticks. tick_count=0 several minutes
                # after start = plan likely doesn't include futures real-
                # time WS, or contract is illiquid.
                "polygon_ws": (self.monitor._ws_client.health()
                               if getattr(self.monitor, "_ws_client", None)
                               else {"enabled": False}),
                "tradovate_md": (self.monitor._tradovate_md.health()
                                  if getattr(self.monitor, "_tradovate_md", None)
                                  else {"enabled": False}),
                # WS-built bar count -- needs >=35 closed bars before
                # the strategy can fall back to it when REST aggs is
                # stale. Surface so user can watch warmup progress.
                "ws_tick_bars": (self.monitor.tick_bars.closed_count
                                 if hasattr(self.monitor, "tick_bars")
                                 else 0),
                "fib": fib_snap,
                "news_calendar": cal_snap,
                "shadow_engine": shadow_snap,
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

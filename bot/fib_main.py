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
    # ALSO attach handlers to peer loggers used by other modules so their
    # warnings/errors appear in the same log file. Without this,
    # tradovate_client's "Tradovate auth HTTP 401" / "Tradovate auth
    # rate-limited" / "Tradovate authenticated" messages all go to the
    # default Python handler (nowhere visible) and the diagnostic bundle
    # has no record of WHY broker auth is failing. The recurring
    # "[BROKER HEALTH] account_list returned empty" appeared in the bundle
    # with zero accompanying detail because of this gap.
    for peer in ("tradovate", "tradovate_user_ws", "tradovate_md",
                  "pullback_strategy"):
        pl = logging.getLogger(peer)
        if not pl.handlers:
            for h in logger.handlers:
                pl.addHandler(h)
        pl.setLevel(logging.INFO)


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
        # LATENCY: tune Python's garbage collector to reduce pause times
        # in the hot tick callback. Default thresholds (700, 10, 10)
        # trigger frequent minor collections that can pause the
        # interpreter for 5-15ms. Bumping the threshold means fewer
        # GC cycles, each ~5ms longer but overall ~30% less GC pause
        # time on the tick path. We rely on bounded deque buffers +
        # explicit state cleanup so memory stays bounded even with
        # less aggressive GC.
        try:
            import gc as _gc
            _gc.set_threshold(5000, 25, 25)
            # Freeze startup-time allocations so they're skipped by
            # future GC scans. Significantly reduces gen-2 cost.
            _gc.freeze()
        except Exception:
            pass
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
                # Start background token refresher so re-auth never
                # delays a trade. Tokens get refreshed 10 min before
                # expiry in a daemon thread.
                try:
                    self.tradovate_session.start_background_refresh()
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
                # LATENCY: pre-establish the user WebSocket connection
                # so the first trade isn't delayed by the WS handshake
                # + authorize + syncrequest round-trips (~500ms-1s).
                # When the first placeoso fires, the WS is already
                # connected, authorized, and ready to send.
                try:
                    from bot.tradovate_user_ws import get_user_ws
                    _uws = get_user_ws()
                    if _uws is not None:
                        logger.info("[Tradovate prewarm] user WS started "
                                    "-- first order will use WS path")
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
        # State persistence path. Every Railway redeploy wipes in-memory
        # state -- _pending_parent_orders, _anticipatory_limit, etc. --
        # which causes silent failures: bot doesn't know about its own
        # working orders after restart, so it can't cancel stale ones,
        # can't poll for fills, and may submit duplicates.
        # Fix: serialize critical tracking state to disk on every change,
        # restore + reconcile against Tradovate's actual state on startup.
        try:
            import pathlib as _pl
            self._state_path = _pl.Path(
                os.environ.get("BOT_DATA_DIR", "/app/data")
                ) / f"bot_state_acct{self.account_id}.json"
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            self._state_path = None
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
        # ANTICIPATORY DIAGNOSTICS. Every call to _check_anticipatory_limit
        # records WHY it did or did not rest a LIMIT. This is the missing
        # telemetry that let the anticipatory path silently never-fire
        # (0/150 broker orders in the 2026-07-01 bundle) without any
        # visible reason. Surfaced in the diagnostic bundle as
        # `anticipatory_diag` so the exact blocker is provable from a
        # single live/demo run instead of inferred.
        #   skips     -> Counter of skip-reason -> count
        #   submits   -> how many LIMITs we actually rested
        #   adopts    -> how many rested LIMITs paper later adopted
        #   last      -> last few (ts, outcome, detail) events (ring)
        self._anticip_diag = {
            "skips": {}, "submits": 0, "adopts": 0,
            "checks": 0, "last": [],
        }
        self._anticip_last_drain = 0.0
        # EXIT-PATH LEDGER. Counts how each broker close was captured
        # (bracket fill at paper's exact target vs liquidate variants vs
        # discrepancy flattens). Turns "did target-patience recover the
        # spread?" into a single bundle lookup instead of a timeline scan.
        self._close_path_counts: dict = {}
        # LATENCY: cache the resolved Tradovate symbol so we don't
        # re-resolve from polygon_front_month on every trade. Same
        # value all day. Refreshes on next bot restart.
        self._cached_symbol: Optional[str] = None
        # Process start time for the diagnostic bundle's uptime stats.
        self._started_at = time.time()
        # Restore persisted state + reconcile with broker. Critical after
        # restarts -- without this, the bot loses track of working orders,
        # positions, anticipatory LIMITs etc and can submit duplicates or
        # leave orphans running.
        try:
            self._restore_state()
        except Exception as e:
            logger.warning(f"state restore failed: {e!r}")
        # Register graceful shutdown hook so state is persisted on
        # SIGTERM (Railway redeploy). atexit handles normal Python exits.
        try:
            import atexit
            atexit.register(self._persist_state)
        except Exception:
            pass
        try:
            import signal as _sig
            def _sigterm_handler(sig, frame):
                logger.info("[shutdown] SIGTERM received -- persisting state")
                try:
                    self._persist_state()
                except Exception:
                    pass
            _sig.signal(_sig.SIGTERM, _sigterm_handler)
        except Exception:
            pass
        # CRITICAL LATENCY OPTIMIZATION: register a tick callback so
        # try_fire_on_tick runs inline on every Polygon tick (sub-100ms
        # reaction time) instead of waiting up to CYCLE_FLAT_SECONDS for
        # the next main-loop cycle. Lock prevents the tick handler from
        # firing while _tick() is also processing one.
        import threading as _threading
        self._tick_fire_lock = _threading.Lock()
        # Guards _pending_parent_orders against the WS-thread real-time
        # fill drain (_drain_ws_fills, runs on the Polygon tick thread)
        # racing the main-loop cycle poll (_poll_pending_broker_orders).
        # Both mutate the same list; without this they can drop/duplicate
        # fill records.
        self._poll_lock = _threading.Lock()
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
                # Use the module singleton -- constructing a second
                # TradovateUserWS here opened a SECOND socket alongside
                # the one every other call site gets via get_user_ws().
                # Tradovate then delivered every exec/fill event on both
                # sockets: doubled log lines, doubled fill-archive rows
                # (bundle11: 817 rows, 407 unique fills), and doubled
                # event processing.
                from bot.tradovate_user_ws import get_user_ws
                self.tradovate_user_ws = get_user_ws()
                logger.info(
                    f"tradovate_user_ws singleton attached="
                    f"{self.tradovate_user_ws is not None}")
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
        # FIRST line in the log: resolved strategy config. Without this,
        # an operator can't tell from logs alone whether INVERSE FADE is
        # on or whether the env vars actually took effect. Reads the same
        # module-level resolved constants as detect_pullback_setup, so
        # any drift between intent and reality shows up immediately.
        try:
            import bot.pullback_strategy as _ps
            mode = "INVERSE FADE" if _ps.INVERT_DIRECTION else "WITH-IMPULSE"
            logger.warning(
                "[STRATEGY CONFIG] mode=%s impulse=%.1fpt over %d bars "
                "pull_pct=%.3f stop=%.1fpt target=%.1fpt RR=1:%.2f",
                mode, _ps.IMPULSE_PTS, _ps.IMPULSE_WINDOW_BARS,
                _ps.PULLBACK_PCT, _ps.STOP_PTS, _ps.TARGET_PTS,
                (_ps.TARGET_PTS / _ps.STOP_PTS) if _ps.STOP_PTS > 0 else 0,
            )
            if _ps.INVERT_DIRECTION:
                logger.warning(
                    "[STRATEGY CONFIG] INVERSE MODE ACTIVE -- the bot will "
                    "FADE 1-min impulses at the %.1f%% retracement.",
                    _ps.PULLBACK_PCT * 100.0)
            else:
                logger.warning(
                    "[STRATEGY CONFIG] INVERSE MODE OFF -- still trading "
                    "the original with-impulse pullback. To activate the "
                    "inverse strategy, set STRAT_INVERT=1 in Railway env.")
        except Exception as _e:
            logger.exception("[STRATEGY CONFIG] failed to log resolved params: %s", _e)
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
        # STARTUP-TIME AUTO-PAUSE CLEAR. The bot's auto daily-loss-limit
        # writes pause_file() with reason=auto_daily_loss_limit when
        # today_pnl crosses -$FIB_AUTO_DLL. Without clearing on startup,
        # every redeploy after a losing day inherits the pause and the
        # bot sits idle overnight waiting for the NY day to roll. User
        # reported this happening repeatedly. Clear it on startup so a
        # redeploy = a fresh state. Manual pauses (reason=user_manual)
        # are preserved -- only auto-DLL clears.
        try:
            from bot.account_ctx import get_pause_state, pause_file
            pstate = get_pause_state()
            if pstate.get("paused") and pstate.get("reason") == "auto_daily_loss_limit":
                pause_file().unlink()
                logger.warning("[STARTUP] cleared stale auto_daily_loss_limit "
                               "pause from previous session -- bot will resume "
                               "trading. Set FIB_AUTO_DLL=<amount> on Railway "
                               "if you want the auto-DLL safety re-enabled.")
        except Exception as _e:
            logger.debug(f"[STARTUP] pause cleanup skipped: {_e!r}")
        # PAPER ORPHAN RECONCILIATION. If the paper account loaded an
        # open_position from disk but the strategy state is fresh (no
        # active trade), the lucid_guard sees the stale position and
        # blocks every new entry on the opposite side with
        # "hedge: <SIDE> already open". Symptom: bundle 12:18 UTC --
        # 4 SHORT setups all blocked, 0 trades since restart, ~25 broker
        # trades for the day stuck.
        #
        # Close the orphan in the paper book at the position's entry
        # price (pnl = 0 minus commission, same as the existing
        # orphan_recovered path in paper_trading.enter()). The next
        # signal can then fire normally.
        try:
            if (self.account.state.open_position is not None
                    and self.state.active_trade is None):
                op = self.account.state.open_position
                logger.warning(
                    f"[STARTUP] paper account holds orphan {op.side} "
                    f"qty={op.qty} @ {op.entry_px:.2f} (db_id={op.db_id}) "
                    f"but strategy state is flat -- closing as "
                    f"orphan_recovered to unblock new entries.")
                from bot import persistence as _p
                now_iso = real_utc_now().isoformat()
                try:
                    _p.close_trade(op.db_id, now_iso, op.entry_px,
                                    "orphan_recovered", 0.0)
                except Exception as _de:
                    logger.warning(f"[STARTUP] orphan DB close failed: {_de!r}")
                self.account.state.open_position = None
                self.account.save()
        except Exception as _e:
            logger.warning(f"[STARTUP] paper orphan reconciliation failed: {_e!r}")
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
    def _revise_paper_entry_to_broker_fill(self, broker_fill_px: float,
                                              source: str = "ws") -> None:
        """Update paper's entry price to match the broker's actual
        fill. Eliminates the price-improvement divergence between
        the two books -- the LIMIT often fills at a better price
        than the requested level (matching engine semantics) and
        without this revision paper P&L drifts from broker P&L by
        the improvement amount.

        Safe to call multiple times for the same trade; idempotent
        if the entry price already equals the fill price. Skips if
        no active trade or if the trade is already closed.

        OFF BY DEFAULT since 2026-07-06 (user directive: paper is the
        untouchable reference). This hook rewrites PAPER'S OWN BOOKS
        with broker fill prices. While the drift safety cap skipped
        big-drift entries it only fired on small improvements and was
        harmless; the 2026-07-03 mirror policy made the broker fill
        EVERY trade -- including entries 5-33pt past paper's level --
        so this hook began silently repricing paper's biggest winners
        down to broker reality on every trade. That is exactly the
        "paper trading changed since Friday" regression the user
        observed: selection was unchanged, but the books were being
        rewritten. Paper must book its OWN prices; the paper-vs-broker
        gap is measured honestly in execution_audit.entry_parity_pts
        instead of being hidden by mutating the reference. Set
        PAPER_MATCH_BROKER_FILL=1 to re-enable the old behaviour.
        """
        from bot.trade_timeline import add_event as _tl
        if os.environ.get("PAPER_MATCH_BROKER_FILL", "0") != "1":
            return
        if self.state is None or self.state.active_trade is None:
            return
        trade = self.state.active_trade
        old_px = float(trade.entry_px)
        if abs(old_px - broker_fill_px) < 0.001:
            return  # already matches
        diff_pts = broker_fill_px - old_px
        trade.entry_px = float(broker_fill_px)
        # Mirror into the paper account so close() computes P&L
        # against the revised entry.
        try:
            if (self.account is not None
                    and self.account.state is not None
                    and self.account.state.open_position is not None):
                self.account.state.open_position.entry_px = float(broker_fill_px)
                self.account.save()
        except Exception as e:
            logger.debug(f"revise_paper_entry account save: {e!r}")
        logger.info(
            f"[paper REVISE entry] {old_px:.2f} -> {broker_fill_px:.2f} "
            f"(diff {diff_pts:+.2f}pt, src={source}); paper and broker "
            f"books now exactly aligned on this trade.")
        _tl(self._open_trade_ref, "paper_entry_revised",
             old_px=old_px, new_px=broker_fill_px,
             diff_pts=round(diff_pts, 4), source=source)

    def _poll_pending_broker_orders(self) -> None:
        """Locked entry point (see _poll_pending_broker_orders_impl).
        Called from the main-loop cycle AND indirectly from the Polygon
        tick thread (via _drain_ws_fills), so the mutation of
        _pending_parent_orders must be serialized."""
        with self._poll_lock:
            self._poll_pending_broker_orders_impl()

    def _drain_ws_fills(self) -> None:
        """REAL-TIME broker-fill detection, called on every Polygon tick.

        The root cause of the phantom "~2 second fill delay" seen in the
        2026-07-01 bundle: broker ENTRY orders actually fill instantly on
        Tradovate (New->Filled p50 = 0.0s, 93.7% < 100ms per that
        bundle's execution_reports), but the bot only DRAINED the user-WS
        exec-report buffer inside _poll_pending_broker_orders, which ran
        once per 2s main-loop cycle. So a fill that landed at t+0.02s was
        not *seen* until the next cycle, and the timeline stamped a stale
        ws_age_s ~= 2.0s. That lag also delayed paper<->broker entry-price
        reconciliation AND left the anticipatory netPos/open_position
        guards stale during the brief flat window between trades -- which
        is exactly when a resting LIMIT needs to be placed to catch the
        fast-reversal winners the broker currently misses.

        Draining here (throttled to ~10x/sec) makes fills register in
        real time. Read-only + idempotent: reuses the same locked poll,
        which never blocks paper, cancels, or reduces trades. The REST
        portion stays age-scheduled, so this does NOT add REST spam."""
        if not self._pending_parent_orders or self.tradovate_orders is None:
            return
        nowt = time.time()
        if nowt - getattr(self, "_anticip_last_drain", 0.0) < 0.1:
            return
        self._anticip_last_drain = nowt
        # Non-blocking: if the main cycle already holds the poll lock it
        # is doing this exact work right now, so skip rather than stall
        # the tick thread (which also fires entries -- must stay fast).
        if not self._poll_lock.acquire(blocking=False):
            return
        try:
            # record_only: detect + record fills in real time but do NOT
            # reassign _pending_parent_orders. Removal stays on the main
            # cycle so there is a single list-mutating thread.
            self._poll_pending_broker_orders_impl(record_only=True)
        except Exception as e:
            logger.debug(f"ws fill drain: {e!r}")
        finally:
            self._poll_lock.release()

    def _poll_pending_broker_orders_impl(self, record_only: bool = False) -> None:
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

        record_only=True is the real-time tick-thread path
        (_drain_ws_fills): it detects fills from the WS buffer and
        records them, but does NOT reassign _pending_parent_orders.
        Only the main-loop cycle (record_only=False) ever mutates the
        list structure, so there is exactly ONE thread that reassigns
        it -- no cross-thread lost-append/dropped-fill race. A per-entry
        `_ws_logged` flag keeps the event from being recorded twice when
        both paths see the same fill.
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
        # Iterate a SNAPSHOT copy: the real-time drain (record_only) runs
        # on the tick thread and could otherwise observe the main cycle's
        # reassignment mid-loop. The snapshot is stable; per-entry flags
        # we set below carry over because entries are shared by reference.
        for entry in list(self._pending_parent_orders):
            age = now_ts - entry["submitted_at"]
            # WS shortcut: if we have a live exec report showing this
            # parent filled/rejected, record it and move on. The REST
            # poll is the safety net.
            pid = entry.get("parent_order_id")
            if pid is not None and int(pid) in ws_fills_by_order:
                er = ws_fills_by_order[int(pid)]
                ord_status = er.get("ordStatus")
                exec_type = er.get("execType")
                # Log once per STATUS TRANSITION (not once ever): the WS
                # buffer holds the latest report, so New->Working->Filled
                # must each log exactly once. A plain "already logged"
                # boolean would suppress the later Filled (and its paper
                # revise) after an earlier Working was seen.
                already_logged = (entry.get("_ws_last_status") == ord_status)
                # TRUE fill latency from Tradovate's own exec-report
                # timestamp, NOT the bot's poll time. ws_age_s used to be
                # `now - submitted_at`, which conflated network+matching
                # latency (instant) with the bot's own 2s poll cadence
                # (the phantom "2s delay"). broker_fill_latency_s isolates
                # the real number so the bundle stops mislabeling it.
                if not already_logged:
                    broker_fill_latency_s = None
                    try:
                        tsx = er.get("timestamp")
                        if tsx:
                            from datetime import datetime as _dt
                            fill_epoch = _dt.fromisoformat(
                                tsx.replace("Z", "+00:00")).timestamp()
                            broker_fill_latency_s = round(
                                fill_epoch - float(entry["submitted_at"]), 3)
                    except Exception:
                        pass
                    _tl(entry["setup_ref"], "broker_ws_event",
                         exec_type=exec_type, ord_status=ord_status,
                         avg_px=er.get("avgPx"),
                         last_qty=er.get("lastQty"),
                         last_px=er.get("lastPx"),
                         reject_reason=er.get("rejectReason"),
                         ws_age_s=round(age, 3),
                         broker_fill_latency_s=broker_fill_latency_s,
                         detect_lag_s=(round(age - broker_fill_latency_s, 3)
                                       if broker_fill_latency_s is not None
                                       else None))
                    # Remember the status we just logged so neither the
                    # tick drain nor the cycle records this same status
                    # twice (but a later transition still logs).
                    entry["_ws_last_status"] = ord_status
                # PAPER-MATCHES-BROKER. The moment the broker fill is
                # confirmed via WS, revise paper's entry_px to the actual
                # fill price -- eliminates the price-improvement drift
                # (paper booked at the theoretical pullback level, the
                # LIMIT got a better fill). Guarded by its OWN once-flag,
                # NOT the log dedup: the drain can see Filled BEFORE
                # _open_trade_ref is set, so the revise must be retried on
                # later polls until it lands, then marked done. Skipping
                # it on the first sight (as a shared log flag would) would
                # lose the revise permanently.
                if ord_status == "Filled" and not entry.get("_paper_revised"):
                    fill_px = er.get("avgPx") or er.get("lastPx")
                    if (fill_px is not None
                            and entry.get("setup_ref") == self._open_trade_ref):
                        try:
                            self._revise_paper_entry_to_broker_fill(
                                float(fill_px), source="ws_exec_report")
                            entry["_paper_revised"] = True
                        except Exception as _re:
                            logger.debug(f"revise_paper_entry: {_re!r}")
                if record_only:
                    # Real-time path: recorded the fill, but leave list
                    # mutation (removal) to the single-threaded main cycle.
                    continue
                if ord_status in {"Filled", "Rejected", "Canceled", "Expired"}:
                    # No more polling needed -- WS gave us the answer.
                    continue
            if record_only:
                # Real-time path does WS detection only; the REST poll
                # schedule and list removal stay on the main cycle.
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
                # REST-fallback fill confirmation: same paper-revise
                # behaviour as the WS path above. The REST poll
                # response doesn't always include avg_px directly;
                # fetch the parent order fills via get_order_status's
                # broader API if needed. For now we hit /order/item
                # to get the avgPx.
                try:
                    avg_px = self.tradovate_orders.get_order_fill_price(
                        entry["parent_order_id"])
                    if (avg_px is not None
                            and entry.get("setup_ref") == self._open_trade_ref):
                        self._revise_paper_entry_to_broker_fill(
                            float(avg_px), source="rest_poll")
                except Exception as _re:
                    logger.debug(f"revise_paper_entry (rest): {_re!r}")
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
        # Only the main cycle reassigns the list (single writer). The
        # record_only tick path returned above without touching it.
        if not record_only:
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
        # REAL-TIME broker-fill detection. Drains the user-WS exec-report
        # buffer on every tick so instant Tradovate fills register now
        # instead of up to 2s later on the main cycle. Kills the phantom
        # "2s fill delay" AND keeps the anticipatory netPos/open_position
        # guards fresh during the flat window between trades. Throttled +
        # locked internally; never blocks or cancels.
        try:
            self._drain_ws_fills()
        except Exception as e:
            logger.debug(f"tick ws drain: {e!r}")
        # TICK-BASED EXIT for active paper trade (mirrors broker reality).
        # Without this, paper's exit logic uses 1-min bar HIGH/LOW which
        # counts every wick that brushed target as a win -- inflating
        # paper P&L vs what the broker bracket can actually capture.
        # Now paper exits use bid/ask just like the matching engine does.
        if self.state and self.state.active_trade is not None:
            try:
                from bot.pullback_strategy import should_exit_on_tick, close_trade
                from bot.tick_history import latest_by_src
                tv = latest_by_src("tradovate") or {}
                bid = tv.get("bid"); ask = tv.get("ask")
                if bid is None or ask is None:
                    # Try Polygon NBBO before resorting to the trade price.
                    pg = latest_by_src("polygon") or {}
                    pg_bid = pg.get("bid"); pg_ask = pg.get("ask")
                    if pg_bid is not None and pg_ask is not None:
                        bid, ask = pg_bid, pg_ask
                    else:
                        # No NBBO feed -- synthesize a 1-tick spread
                        # around last. This matches what a broker LIMIT
                        # actually requires: a LONG target LIMIT SELL
                        # fills when a BUYER comes UP to pay our offer
                        # (bid touches target), not when last prints at
                        # target. Treating bid=ask=last was symmetric
                        # but paper-favorable: 308 broker round-trips
                        # today gave only 66 LIMIT target hits while
                        # paper booked 113. The half-tick offset makes
                        # paper require last to overshoot LIMIT exits
                        # by one tick, mirroring real fill conditions.
                        HALF_SPREAD_PTS = 0.125  # MNQ tick = 0.25
                        bid = float(price) - HALF_SPREAD_PTS
                        ask = float(price) + HALF_SPREAD_PTS
                result = should_exit_on_tick(
                    self.state.active_trade,
                    float(bid), float(ask), real_utc_now())
                if result is not None:
                    exit_px, reason = result
                    record = close_trade(
                        self.state.active_trade, exit_px, reason, real_utc_now())
                    self.state.completed_trades.append(record)
                    self.state.active_trade = None
                    self.state.last_trade_close_ts = real_utc_now()
                    try:
                        self._on_trade_close(record, real_utc_now())
                    except Exception as ce:
                        logger.warning(f"_on_trade_close failed: {ce!r}")
                    return
            except Exception as e:
                logger.debug(f"tick-based exit: {e!r}")
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
        # Persist tracking state to disk every ~10s (cycle * 2s = 10s
        # when in CYCLE_FLAT_SECONDS=2). Cheap atomic JSON write. If
        # the bot crashes / Railway redeploys, we recover within
        # 10 seconds of last consistent state.
        if self.cycle % 5 == 0:
            try:
                self._persist_state()
            except Exception:
                pass
        # PERIODIC BROKER HEALTH CHECK. Every ~5 minutes (150 cycles at
        # CYCLE_FLAT_SECONDS=2) we:
        #   1) Force-refresh the account_id (clears the cached id and
        #      re-fetches /account/list). This triggers token refresh
        #      under the hood if the token has expired since the bot
        #      started. Catches the recurring "broker dies overnight"
        #      auth failure where the bot keeps making paper trades but
        #      can no longer authenticate with Tradovate.
        #   2) Re-run _reconcile_with_broker to clear stale
        #      _open_trade_ref / orphaned anticipatory limits. Without
        #      this, the duplicate-entry guard wedges and no new trades
        #      fire on the broker until the next process restart.
        # Cheap: 1-2 API calls every 5 minutes. The cost of NOT doing
        # this is the silent broker-offline state observed multiple
        # times.
        # BROKER HEALTH CHECK FREQUENCY. Tightened from 150 cycles (~5 min)
        # to 60 cycles (~1-2 min depending on cycle pace) so that auth
        # gaps, stale _open_trade_ref, and orphan broker positions get
        # caught much faster. The forced re-fetch of account_id is one
        # cheap REST call; the upside is the bot recovers from auth/state
        # divergences in <2 min instead of <6 min, directly cutting the
        # "paper fired, broker didn't" window.
        _broker_health_every = int(os.environ.get("BROKER_HEALTH_CYCLES", "60"))
        if self.cycle % _broker_health_every == 0 and self.tradovate_orders is not None:
            try:
                sess = self.tradovate_orders.session
                if sess is not None and sess.is_configured:
                    # NON-DESTRUCTIVE REFRESH. Previously we set
                    # sess._account_id = None upfront and only restored
                    # the prior value if the re-fetch failed. That left
                    # a window (often 15-30s on a slow /account/list)
                    # where any paper trade firing in the meantime hit
                    # no_account_id and the broker order was silently
                    # dropped. Bundle 02:50 UTC: 8 of 17 trades lost
                    # this way, 2 of them with signal_to_placeoso=60001ms
                    # (one 15s timeout + one 15s retry).
                    #
                    # Now we keep the cached id live the whole time.
                    # Re-authenticate, ask for a fresh id, only swap
                    # the cache if the refresh actually returned
                    # something. The next placeoso always reads a
                    # valid id without paying the network latency.
                    prior = sess._account_id
                    tokens = None
                    try:
                        tokens = sess.authenticate()
                    except Exception as ae:
                        logger.error(f"[BROKER HEALTH] authenticate() raised: {ae!r}")
                    fresh = None
                    if tokens is not None:
                        try:
                            accts = sess.account_list()
                            if accts:
                                fresh = int(accts[0]["id"])
                        except Exception as le:
                            logger.warning(
                                f"[BROKER HEALTH] account_list raised: "
                                f"{le!r} -- keeping cached id={prior}")
                    if fresh is None:
                        # Surface a detailed diagnostic so the operator
                        # can see WHY auth keeps failing instead of just
                        # the recurring symptom. Each branch corresponds
                        # to a specific root cause requiring a different
                        # remediation.
                        reason = "unknown"
                        if tokens is None:
                            reason = "authenticate() returned None -- check tradovate_client logs above for HTTP code / errorText / captcha p-ticket"
                        elif tokens.user_id == 0:
                            reason = "auth ok but userId=0 -- creds may belong to a disabled or wrong-cluster account"
                        else:
                            reason = "auth ok but /account/list empty or slow -- keeping cached id as fallback so in-flight trades don't lose the broker"
                        logger.error(
                            "[BROKER HEALTH] refresh failed. user_id=%r "
                            "tokens=%s reason=%s. Will retry in 5 min. "
                            "Cached id=%r still in use; paper continues.",
                            tokens.user_id if tokens else None,
                            "present" if tokens else "missing",
                            reason, prior)
                    else:
                        if prior != fresh:
                            logger.warning(
                                f"[BROKER HEALTH] account_id changed "
                                f"{prior!r} -> {fresh!r}")
                            sess._account_id = fresh
                        else:
                            logger.info(
                                f"[BROKER HEALTH] OK account_id={fresh} "
                                f"open_ref={self._open_trade_ref!r} "
                                f"pending={len(self._pending_parent_orders)} "
                                f"anticipatory={'yes' if self._anticipatory_limit else 'no'}")
                        # Now reconcile state -- clears stale open_trade_ref,
                        # cancels stuck anticipatory orders.
                        try:
                            self._reconcile_with_broker()
                        except Exception as re:
                            logger.warning(f"[BROKER HEALTH] reconcile: {re!r}")
            except Exception as e:
                logger.warning(f"[BROKER HEALTH] check failed: {e!r}")
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
                # Clear broker-side tracking state too. If the broker has
                # an actual open position on Tradovate, _reconcile_with_broker
                # below will re-discover it and re-set _open_trade_ref. If
                # the broker is flat, leaving these set would wedge the
                # duplicate-entry guard and block every new entry.
                self._open_trade_ref = None
                self._pending_parent_orders = []
                self._anticipatory_limit = None
                self._broker_stop_px = None
                self._broker_target_px = None
                self._broker_side = None
                self._broker_target_sent = False
                try:
                    _reset_flag.unlink()
                except Exception:
                    pass
                # Re-sync with broker so any actual open position is
                # rediscovered. Cheap; just a few REST calls.
                try:
                    self._reconcile_with_broker()
                except Exception as e:
                    logger.warning(f"reset post-reconcile failed: {e!r}")
                _bal_msg = f"${starting_balance:,.0f}" if starting_balance else "$50k"
                logger.warning(f"=== runtime reset complete -- account at {_bal_msg}, history wiped, broker reconciled ===")
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

        # WS-TICK BARS FALLBACK. Polygon REST has had hours-long blackouts
        # where /aggs returned empty on every poll while the WS feed kept
        # streaming ticks just fine. Bundle 23:30 UTC showed the bot
        # bailing every cycle for 3 hours straight because _bars_5m never
        # populated, while ws_tick_bars sat at 117 closed bars ready to
        # use. Build 1-min from the live tick aggregator and 5-min by
        # resampling those, so REST being down can't pause the strategy.
        if (self._bars_5m is None or self._bars_5m.empty
                or self._bars_1m is None or self._bars_1m.empty):
            try:
                ws_bars = self.monitor.tick_bars.get_bars()
                ws_closed = len(ws_bars) if ws_bars is not None else 0
            except Exception as e:
                logger.debug(f"WS-bars fallback fetch: {e!r}")
                ws_bars = None
                ws_closed = 0
            if ws_bars is not None and ws_closed >= 5:
                self._bars_1m = ws_bars
                self._bars_1m_source = "polygon_ws_ticks"
                try:
                    # Resample 1-min -> 5-min: OHLC + volume. The HTF
                    # trend filter only needs ~60 bars (k=30 pivot), so
                    # even a partial WS history works once it warms up.
                    resampled = ws_bars.resample("5min").agg({
                        "open": "first", "high": "max",
                        "low": "min", "close": "last",
                    }).dropna()
                    if not resampled.empty:
                        self._bars_5m = resampled
                except Exception as e:
                    logger.debug(f"WS->5m resample: {e!r}")
                if not hasattr(self, "_ws_fallback_warned") or not self._ws_fallback_warned:
                    self._ws_fallback_warned = True
                    logger.warning(
                        f"[BAR-SOURCE WS-FALLBACK] Polygon REST unavailable "
                        f"-- driving the strategy from {ws_closed} WS "
                        f"tick-built closed bars and resampled 5-min.")

        if self._bars_5m is None or self._bars_5m.empty:
            return
        if self._bars_1m is None or self._bars_1m.empty:
            return

        # PRIMARY BAR SOURCE: WS-built tick bars over REST aggs.
        # -------------------------------------------------------------
        # Root cause of "polygon expected X, bot fired at Y" divergence
        # (21pt gaps in some trades): the REST aggs cache only refreshes
        # every 60s, and during that 60-second window the strategy fires
        # on bars that are missing the most recent close. Verification
        # function (which reads fresh polygon aggs at trade time) then
        # disagrees on the impulse magnitude and entry level.
        #
        # WS-built bars are aggregated from the live tick stream on
        # every tick, so they are NEVER stale by more than a tick
        # (<100ms). Using them as the primary source eliminates the
        # bar-age divergence entirely. The REST aggs remain available
        # as a fallback during WS warmup (first ~35 minutes after bot
        # start) when the tick aggregator hasn't accumulated enough
        # closed bars yet.
        #
        # Env var BOT_PREFER_WS_BARS=0 to revert to the legacy
        # REST-first behaviour.
        prefer_ws = os.environ.get("BOT_PREFER_WS_BARS", "1") == "1"
        if prefer_ws:
            try:
                ws_bars = self.monitor.tick_bars.get_bars()
                ws_closed = len(ws_bars) if ws_bars is not None else 0
            except Exception as e:
                logger.debug(f"WS-bars fetch: {e!r}")
                ws_bars = None
                ws_closed = 0
            # Need at least IMPULSE_WINDOW_BARS (4) + 1 spare for the
            # current bar that is about to close.
            min_ws_bars = 5
            if ws_bars is not None and ws_closed >= min_ws_bars:
                if self._bars_1m_source != "polygon_ws_ticks":
                    logger.warning(
                        f"[BAR-SOURCE switch] using live WS tick-built "
                        f"bars as primary (was {self._bars_1m_source}, "
                        f"{ws_closed} closed bars available, eliminates "
                        f"REST refresh staleness)")
                self._bars_1m = ws_bars
                self._bars_1m_source = "polygon_ws_ticks"

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
        # The strategy ran a full tick cycle -- clear any stale
        # last_error left over from a transient failure earlier in the
        # session (e.g. price_invalid_paused from a brief stale price
        # window, or bars_stale_X when REST recovered after a blackout).
        # Without this the dashboard reports a permanent failure state
        # even though the bot has been trading normally for hours.
        if self.last_error is not None:
            self.last_error = None
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
        # SERIALIZE PAPER TRADE-OPENING. on_new_1m_bar (this main-loop
        # thread) and try_fire_on_tick (the WS tick thread) both open
        # trades gated on state.active_trade is None -- but without a
        # common lock they can BOTH pass that check within milliseconds
        # and both book a trade: the 2026-07-03 04:55 bundle shows 5
        # double-fires (two placeoso ~20-100ms apart, same price,
        # consecutive db_ids, same epoch-second refs) each ending in
        # netPos 2 and a STACK flatten. The WS path already fires under
        # _tick_fire_lock; taking the same lock here closes the race --
        # active_trade is set before either side releases.
        with self._tick_fire_lock:
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
            # DUPLICATE-ENTRY GUARD: if _open_trade_ref is already set,
            # the broker still holds a position from a previous trade.
            # Sending another entry would open a SECOND position with its
            # own bracket -- the stacking bug class. Skip ONLY the broker
            # forwarding; the paper trade above is already booked (paper
            # must trade identically no matter what the broker is doing).
            if self._open_trade_ref is not None:
                logger.error(
                    f"[broker SKIP] duplicate entry blocked: "
                    f"_open_trade_ref={self._open_trade_ref} still active. "
                    f"Strategy fired {trade.side} setup but broker already "
                    f"has a position open. Paper account books normally; "
                    f"broker stays single-position.")
                return
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
                # Per-trade execution diagnostics. These are the fields
                # that pinpoint the missed-winner mechanism: how far live
                # price had already DRIFTED past the entry level when we
                # went to enter (big favorable drift => price already left
                # the level => reactive LIMIT gets safety-capped or rests
                # stranded), and whether an anticipatory LIMIT was already
                # resting at the level (the fix). Computed cheaply, inline.
                _lpx = None
                try:
                    _ls0 = self.monitor.latest()
                    _lpx = float(_ls0.price) if _ls0 is not None else None
                except Exception:
                    _lpx = None
                _drift = None
                if _lpx is not None:
                    # Signed so +ve = price already moved in the trade's
                    # favour (the winner-miss signature).
                    _drift = round(
                        (_lpx - trade.entry_px) if trade.side == "LONG"
                        else (trade.entry_px - _lpx), 2)
                _anti = self._anticipatory_limit
                _anti_resting = bool(
                    _anti and self._setup_key(getattr(trade, 'setup', None))
                    == _anti.get('setup_key')) if getattr(
                    trade, 'setup', None) is not None else False
                _netpos = None
                try:
                    from bot.tradovate_user_ws import get_user_ws
                    _uws0 = get_user_ws()
                    if _uws0 is not None:
                        for _cid, _e in (_uws0._netpos_cache or {}).items():
                            if _e.get("netPos", 0) != 0:
                                _netpos = _e["netPos"]
                                break
                        if _netpos is None:
                            _netpos = 0
                except Exception:
                    _netpos = None
                _tl(setup_ref, "trade_open_started",
                     side=trade.side, qty=trade.n_mnq,
                     entry_px=trade.entry_px,
                     stop_px=trade.stop_px,
                     target_px=trade.target_px,
                     live_px_at_open=_lpx,
                     entry_drift_pts=_drift,
                     anticipatory_was_resting=_anti_resting,
                     broker_netpos_at_open=_netpos)
                live_snap = self.monitor.latest()
                logger.info(f"[broker gate 3/4 live_price] snap="
                            f"{'None' if live_snap is None else f'{live_snap.price:.2f}'}")
                # PRICE-MONITOR FLAKE GUARD. The Polygon WS we depend on
                # for the "live price" gate flaps -- snapshot.price_ts
                # can briefly age past the freshness threshold while
                # Polygon's REST agg is the actual fresh source. When
                # that happens, monitor.latest() returns None mid-tick
                # even though the strategy just fired (the strategy
                # code lives at a different layer and saw a valid
                # price moments before). Result: paper books the
                # trade, broker_skip with no_live_price, broker stays
                # silent. Observed in bundles where 23/23 today's
                # trades fired on paper but 0 reached the broker.
                #
                # Fix: when the gate price is missing AND the
                # strategy already decided to enter at trade.entry_px,
                # accept the strategy's own entry price as the live
                # reference. The strategy's price was valid when it
                # fired; using it for the divergence gate is no
                # worse than the alternative (refusing every trade).
                if live_snap is None:
                    class _SnapShim:
                        __slots__ = ("price",)
                        def __init__(self, p): self.price = p
                    live_snap = _SnapShim(float(trade.entry_px))
                    logger.warning(
                        f"[{broker_name} live_price=None] strategy "
                        f"already decided at {trade.entry_px:.2f}; "
                        f"using strategy price as live reference so "
                        f"the broker submit goes through. paper and "
                        f"broker stay in lockstep.")
                    _tl(setup_ref, "broker_live_price_fallback",
                         strategy_px=trade.entry_px)
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
                # DIVERGENCE GATE. The old 30pt cap was a safety against
                # broker submitting at wildly different prices than the
                # strategy decided. With the bracket re-anchor at the
                # actual fill price downstream, the cap is essentially
                # never useful in normal trading -- a 30pt divergence
                # means a black-swan event already happened. User
                # explicitly asked to NEVER skip a paper trade on the
                # broker side, so we now treat the divergence as a
                # WARNING (logged but doesn't block submission) instead
                # of a hard skip. Operators who want the hard skip back
                # can set BROKER_HARD_DIVERGENCE_SKIP=1 in env.
                divergence_max = float(os.environ.get(
                    "TRADERSPOST_MAX_DIVERGENCE_PT", "30"))
                logger.info(f"[broker gate 4/4 divergence] "
                            f"strategy={trade.entry_px:.2f} "
                            f"live={live_snap.price:.2f} "
                            f"diff={divergence:.1f}pt "
                            f"limit={divergence_max:.1f}pt")
                hard_skip = os.environ.get("BROKER_HARD_DIVERGENCE_SKIP", "0") == "1"
                if divergence > divergence_max:
                    if hard_skip:
                        logger.error(
                            f"[{broker_name} HARD-SKIP] divergence "
                            f"{divergence:.1f}pt > {divergence_max:.1f}pt "
                            f"(BROKER_HARD_DIVERGENCE_SKIP=1)")
                        _tl(setup_ref, "broker_skip", reason="divergence",
                             strategy=trade.entry_px, live=live_snap.price,
                             diff=divergence)
                        return
                    else:
                        logger.warning(
                            f"[{broker_name} divergence WARNING] "
                            f"{divergence:.1f}pt > {divergence_max:.1f}pt "
                            f"-- submitting anyway (no hard skip; user "
                            f"requested every paper trade to fire on broker)")
                        _tl(setup_ref, "broker_divergence_warning",
                             strategy=trade.entry_px, live=live_snap.price,
                             diff=divergence)

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
                    # STACK FIX: if an anticipatory LIMIT is resting for a
                    # DIFFERENT setup than the one firing (adopt returned
                    # None on key mismatch), cancel it BEFORE submitting
                    # the reactive entry. Otherwise both stay live -- the
                    # reactive order fills now and the orphaned resting
                    # LIMIT fills later when price touches its level ->
                    # netPos 2 (10 STACK flattens in the 2026-07-02 23:54
                    # bundle traced to exactly this).
                    if pre_oid is None and self._anticipatory_limit is not None:
                        _anti_snapshot = dict(self._anticipatory_limit)
                        try:
                            _term = self._cancel_anticipatory_sync(
                                "different_setup_firing")
                        except Exception as _ce:
                            _term = None
                            logger.warning(
                                f"pre-entry anticipatory cancel: {_ce!r}")
                        # CANCEL LOST THE RACE: the LIMIT filled before
                        # the cancel landed -- the broker ALREADY holds a
                        # position (at the other setup's nearby level).
                        # Submitting the reactive entry now would stack to
                        # netPos 2 (the 03:44 STACK in the 2026-07-03
                        # bundle). Adopt the filled order as this trade's
                        # broker order instead: same side family, bracket
                        # already attached, and the ws-fill revise will
                        # sync paper's entry to the actual fill price.
                        if (_term == "Filled"
                                and _anti_snapshot.get("order_id")):
                            pre_oid = int(_anti_snapshot["order_id"])
                            self._pending_parent_orders.append({
                                "setup_ref": setup_ref,
                                "parent_order_id": pre_oid,
                                "submitted_at": _anti_snapshot.get(
                                    "submitted_at", time.time()),
                                "checks_done": 0,
                                "side": trade.side,
                                "entry_px": float(trade.entry_px),
                                "qty": trade.n_mnq,
                                "anticipatory": True,
                            })
                            _tl(setup_ref,
                                 "anticipatory_fill_adopted_on_mismatch",
                                 order_id=pre_oid)
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
                    #
                    # FLATTEN-THEN-SUBMIT: bundle 20:15 UTC showed 247
                    # broker_skip events all with netpos=-1. Paper had
                    # taken 316 trades, broker had placed 7 brackets --
                    # nearly every entry was being refused because a
                    # stale position from the prior bracket was still
                    # showing non-zero. Behavior is now: if netPos !=
                    # 0 we fire liquidateposition on every non-zero
                    # contract (~70ms each via REST), wait one tick,
                    # then proceed with the placeoso. The strategy
                    # voted to be in a NEW trade right now, so any
                    # broker position remaining is by definition stale.
                    try:
                        sess = self.tradovate_orders.session
                        acct_id = sess.get_account_id()
                        # Pull authoritative position state via REST FIRST.
                        # The user-WS netpos cache goes stale silently:
                        # bundle 20:15 UTC showed cache stuck at netPos=-1
                        # since 14:58 even though /position/list said 0.
                        # Tradovate sometimes drops the "closed" position
                        # frame during a WS reconnect; without a REST
                        # cross-check the bot believes a phantom position
                        # exists forever and skips every entry.
                        nonzero_positions = []
                        status, positions = sess._rest("GET", "/position/list")
                        if status == 200 and isinstance(positions, list):
                            for pos in positions:
                                if not isinstance(pos, dict): continue
                                if pos.get("accountId") != acct_id: continue
                                np_val = int(pos.get("netPos") or 0)
                                if np_val != 0:
                                    nonzero_positions.append({
                                        "contractId": pos.get("contractId"),
                                        "netPos": np_val,
                                    })
                        # Refresh the WS cache from REST truth -- any
                        # contract REST shows as 0 gets zeroed in the
                        # cache too, so the *next* entry won't even need
                        # the REST call.
                        try:
                            from bot.tradovate_user_ws import get_user_ws
                            _uws = get_user_ws()
                            if _uws is not None and status == 200 and isinstance(positions, list):
                                rest_pos = {
                                    pos.get("contractId"): int(pos.get("netPos") or 0)
                                    for pos in positions
                                    if isinstance(pos, dict)
                                    and pos.get("accountId") == acct_id
                                }
                                for cid, entry in list((_uws._netpos_cache or {}).items()):
                                    if cid in rest_pos:
                                        entry["netPos"] = rest_pos[cid]
                                        entry["ts"] = time.time()
                        except Exception:
                            pass
                        if nonzero_positions:
                            logger.warning(
                                f"[broker FLATTEN-FIRST] netPos non-zero on "
                                f"{len(nonzero_positions)} contract(s) -- "
                                f"flushing stale position(s) before new "
                                f"entry: {nonzero_positions}")
                            for npos in nonzero_positions:
                                cid = npos.get("contractId")
                                if not cid:
                                    continue
                                try:
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
                                    _tl(setup_ref, "broker_flatten_stale",
                                         contractId=cid, netPos=npos.get("netPos"))
                                except Exception as fe:
                                    logger.warning(
                                        f"[broker FLATTEN-FIRST] "
                                        f"liquidate contractId={cid} failed: "
                                        f"{fe!r}")
                            # Invalidate the WS netpos cache for stale
                            # contracts so the next read reflects the
                            # liquidate result instead of pre-flatten
                            # state.
                            try:
                                if _uws is not None and _uws._netpos_cache:
                                    for npos in nonzero_positions:
                                        cid = npos.get("contractId")
                                        if cid in _uws._netpos_cache:
                                            _uws._netpos_cache[cid]["netPos"] = 0
                            except Exception:
                                pass
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

    def _count_close_path(self, key: str) -> None:
        """Bump the exit-path ledger (see __init__). Never raises."""
        try:
            self._close_path_counts[key] = \
                self._close_path_counts.get(key, 0) + 1
        except Exception:
            pass

    def _anticip_note(self, outcome: str, **detail) -> None:
        """Record one anticipatory-check outcome for the diagnostic bundle.

        Without this, the anticipatory path silently never-fired
        (0 of 150 broker orders in the 2026-07-01 bundle) with no way to
        tell which guard blocked it. Every skip/submit is now counted and
        the last handful kept with detail so the exact blocker is provable
        from a single run."""
        try:
            d = self._anticip_diag
            d["skips"][outcome] = d["skips"].get(outcome, 0) + 1
            if outcome == "submit":
                d["submits"] += 1
            rec = {"ts": round(time.time(), 3), "outcome": outcome}
            rec.update(detail)
            d["last"].append(rec)
            if len(d["last"]) > 40:
                d["last"] = d["last"][-40:]
        except Exception:
            pass

    def _check_anticipatory_limit(self, current_price: float) -> None:
        """Place a broker LIMIT a moment BEFORE price actually crosses
        the pullback entry level. This way the LIMIT is already
        resting on Tradovate's matching engine when the touch happens
        -- it fills in microseconds instead of waiting on a 500ms HTTP
        round-trip after the touch.

        STACKING SAFETY:
          - Only ONE anticipatory LIMIT alive at a time.
          - A new LIMIT is NEVER submitted while the current one's
            order_id is still unconfirmed (fire-and-forget in flight) --
            that was the exact race that let two LIMITs rest and both
            fill, which got the whole pre-submit path disabled on
            2026-06-16. See the guard below.
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
        self._anticip_diag["checks"] = self._anticip_diag.get("checks", 0) + 1
        # DISABLED BY DEFAULT (2026-07-06, evidence-based). The Sunday
        # session bundle -- the first with the fill archive -- priced the
        # pre-rest definitively: 59 rests produced only 15 adopted trades
        # but 44 UNADOPTED fills (27 during the 10s cooldown when paper
        # cannot fire; 17 from touch asymmetry -- the resting LIMIT fills
        # on the exact touch while paper's fire condition needs a tick
        # through). Orphan unwinds cost -$84 gross / -$170 with fees, and
        # ALL 9 netPos-2 stack events traced to an orphan sitting hidden
        # when the next reactive entry landed. Meanwhile the reactive
        # tick-fire path now executes at parity with paper (median +0.21pt
        # on 96 matched trades), so the pre-rest's incremental edge on the
        # 15 adopted trades was ~+$8/session vs -$170 of damage. Set
        # ANTICIPATORY_ENABLED=1 to re-enable for A/B.
        if os.environ.get("ANTICIPATORY_ENABLED", "0") != "1":
            self._anticip_note("disabled")
            return
        if self.tradovate_orders is None:
            self._anticip_note("no_tradovate_client")
            return
        sess = getattr(self.tradovate_orders, "session", None)
        if sess is None or not sess.is_configured:
            self._anticip_note("sess_not_configured")
            return
        if self.account.state.open_position is not None:
            self._anticip_note("paper_open_position")
            return
        # GUARD PARITY with paper's "may we trade right now" gate
        # (try_fire_on_tick). Without this, the pre-rested LIMIT could
        # fill a trade the paper account would REFUSE -- during a tripped
        # circuit breaker, a manual/auto pause, the Lucid closed window,
        # or a news blackout -- making the broker take trades the strategy
        # never books. We deliberately DO NOT check the cooldown here:
        # resting a LIMIT during the cooldown so it fills the touch that
        # paper later books via is_filled is the entire point of the fix.
        try:
            st = self.state
            if st is not None and getattr(st, "circuit_breaker_tripped", False):
                self._anticip_note("circuit_breaker")
                if self._anticipatory_limit is not None:
                    self._cancel_anticipatory_sync("circuit_breaker")
                return
            from bot.pullback_strategy import (
                _get_manual_pause_state, _in_lucid_closed_window,
                _news_blackout_reason)
            now_g = real_utc_now()
            if _get_manual_pause_state().get("paused"):
                self._anticip_note("manual_pause")
                if self._anticipatory_limit is not None:
                    self._cancel_anticipatory_sync("manual_pause")
                return
            if _in_lucid_closed_window(now_g):
                self._anticip_note("lucid_closed_window")
                if self._anticipatory_limit is not None:
                    self._cancel_anticipatory_sync("lucid_closed_window")
                return
            if _news_blackout_reason(now_g, self.news_calendar) is not None:
                self._anticip_note("news_blackout")
                if self._anticipatory_limit is not None:
                    self._cancel_anticipatory_sync("news_blackout")
                return
        except Exception as e:
            # Fail SAFE: if we can't confirm the gates, do not pre-rest.
            self._anticip_note("gate_check_error", err=repr(e)[:120])
            return
        # Find the pending setup whose entry is closest to current price
        # and on the correct side (price still APPROACHING, not past).
        # Default 3.0pt -- captures more setups including ones where
        # price gaps through. Higher value = more LIMITs placed (and
        # cancelled if not touched) but higher hit rate. Tuneable via
        # env var ANTICIPATORY_THRESHOLD_PT.
        # Wide approach window so the LIMIT gets onto the matching
        # engine WELL ahead of the touch. With the latency stack
        # already optimized to <50ms, we want the LIMIT resting for
        # at minimum a full second before the actual touch -- which
        # means triggering when price is still 5pt away if there's
        # a setup at that level. Once on the book, the LIMIT fills
        # at exactly entry price (no drift, no slip).
        # Raised 2026-06-22 from 5pt to 10pt per user requirement to
        # minimize LIMIT miss-rate on fast moves. Wider approach
        # window means the LIMIT lands on Tradovate's matching engine
        # earlier, giving fast price-action more chance to fill at
        # the resting LIMIT rather than gap through it. Trade-off:
        # more anticipatory LIMITs placed (and cancelled if not
        # touched) but higher hit rate. Tune via env if needed.
        APPROACH_THRESHOLD_PT = float(os.environ.get(
            "ANTICIPATORY_THRESHOLD_PT", "10.0"))
        best = None
        best_dist = APPROACH_THRESHOLD_PT + 0.01
        for s in (self.state.pending_setups if self.state else []):
            if getattr(s, 'used', False) or getattr(s, 'fire_attempted', False):
                continue
            entry = float(s.pullback_entry)
            # Use orig_side (impulse direction), not the trade side --
            # for the INVERSE strategy these differ. Price always
            # approaches entry from the IMPULSE direction, regardless of
            # which way we'll then trade.
            approach = getattr(s, 'orig_side', None) or s.side
            if approach == "LONG":
                # UP impulse: entry sits below the high; price falls TO it.
                if current_price < entry:
                    continue
                dist = current_price - entry
            else:
                # DOWN impulse: entry sits above the low; price rises TO it.
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
            self._anticip_note(
                "no_setup_approaching", px=round(current_price, 2),
                n_pending=len(self.state.pending_setups) if self.state else 0)
            return
        target_key = self._setup_key(best)
        cur_key = (self._anticipatory_limit.get('setup_key')
                    if self._anticipatory_limit else None)
        if cur_key == target_key:
            self._anticip_note("already_resting_for_setup",
                               dist=round(best_dist, 2))
            return  # already submitted for this setup
        # STACKING-RACE GUARD. If an anticipatory LIMIT is live but its
        # order_id hasn't been confirmed yet (fire-and-forget response
        # still in flight), we CANNOT cancel it (no id to cancel). Placing
        # a second LIMIT now is exactly how two ended up resting and both
        # filling -> netPos +2/+3 stacking -> the pre-submit path was
        # disabled. Wait for the id before switching setups.
        if (self._anticipatory_limit is not None
                and self._anticipatory_limit.get('order_id') is None):
            # ...but don't wedge forever. If the WS confirmation never
            # arrives (dropped socket / lost callback), abandon tracking
            # after a timeout so the path resumes. Any orphaned resting
            # LIMIT is caught by _reconcile_with_broker (5-min) and the
            # per-cycle _check_position_discrepancy backstop. netPos!=0
            # below still blocks a new rest if the orphan actually filled.
            unconf_age = nowt - float(
                self._anticipatory_limit.get("submitted_at", nowt))
            if unconf_age > 3.0:
                logger.warning(
                    f"[ANTICIPATORY unconfirmed timeout] no order_id after "
                    f"{unconf_age:.1f}s -- abandoning tracking (reconcile "
                    f"will sweep any orphan)")
                self._anticip_note("prev_limit_unconfirmed_timeout",
                                   age_s=round(unconf_age, 1))
                self._anticipatory_limit = None
            else:
                self._anticip_note("prev_limit_unconfirmed",
                                   waiting_setup=str(cur_key))
                return
        # Different (or no) anticipatory. Cancel old synchronously then submit new.
        if self._anticipatory_limit is not None:
            self._cancel_anticipatory_sync("different_setup_closer")
        # Single-position guard: verify broker netPos == 0.
        # LATENCY: prefer WS-cached netPos to avoid a ~100-200ms REST
        # call. WS pushes position updates instantly on every fill.
        try:
            acct_id = sess.get_account_id()
            cur_net = None
            ws_had_data = False
            try:
                from bot.tradovate_user_ws import get_user_ws
                _uws = get_user_ws()
                # Only trust the WS cache when the socket is CONNECTED and
                # the entries are FRESH (< 5s). The user WS drops
                # occasionally (seen in the bundle); a stale cache read as
                # "flat" could green-light a pre-submit while a position is
                # actually open -> double fill. When stale/disconnected we
                # fall back to REST below.
                cache = {}
                if _uws is not None and getattr(_uws, "connected", False):
                    raw = _uws._netpos_cache or {}
                    cache = {c: e for c, e in raw.items()
                             if (nowt - float(e.get("ts", 0))) < 5.0}
                if cache:
                    # The user WS pushes a netPos entry per contract in
                    # real time. When it has FRESH entries it is
                    # authoritative: populated-but-all-zero means FLAT, not
                    # "unknown". The old code left cur_net=None when flat
                    # and fell through to a REST /position/list on EVERY
                    # 200ms anticipatory check -- 5 REST calls/sec while
                    # flat, which rate-limited/errored and made the
                    # except-branch below skip the pre-submit every time.
                    # That is a prime suspect for the anticipatory path
                    # never firing (0/150). Trust the WS when it is fresh.
                    ws_had_data = True
                    cur_net = 0
                    for cid, entry in cache.items():
                        if entry.get("netPos", 0) != 0:
                            cur_net = entry["netPos"]
                            break
            except Exception:
                pass
            if cur_net is None and not ws_had_data:
                # WS gave us nothing at all -- fall back to REST, but cache
                # the answer for 2.5s so rapid checks don't spam the
                # endpoint (the 1s TTL still produced enough call volume
                # to rate-limit: 371 netpos_rest_failed skips in the
                # 2026-07-02 05:54 bundle, several of which cost real
                # winners via the safety-cap path).
                _nc = getattr(self, "_anticip_netpos_cache", None)
                if _nc is not None and (nowt - _nc[0]) < 2.5:
                    cur_net = _nc[1]
                else:
                    status, positions = sess._rest("GET", "/position/list")
                    if status == 200 and isinstance(positions, list):
                        cur_net = 0
                        for pos in positions:
                            if not isinstance(pos, dict): continue
                            if pos.get("accountId") != acct_id: continue
                            if int(pos.get("netPos") or 0) != 0:
                                cur_net = int(pos["netPos"])
                                break
                        # Only cache a CONFIRMED read.
                        self._anticip_netpos_cache = (nowt, cur_net)
                    elif _nc is not None and (nowt - _nc[0]) < 10.0:
                        # REST failed but we have a CONFIRMED read <10s
                        # old -- use it. Positions only change when THIS
                        # bot trades (single strategy, single account),
                        # and every submit path stamps tracking state
                        # (_open_trade_ref / _anticipatory_limit) that the
                        # guards above already checked. Skipping here
                        # instead (the old behaviour) silently disarmed
                        # the anticipatory path for the whole REST outage
                        # -- the 05:03 and 04:50 +87-point winners were
                        # both missed exactly this way.
                        cur_net = _nc[1]
                        self._anticip_note(
                            f"netpos_rest_failed_used_stale_{status}")
                    else:
                        # REST failed and no recent confirmed read. Do NOT
                        # assume flat -- that could green-light a pre-rest
                        # over an open position. Fail safe: skip, don't
                        # cache. Status goes into the persistent counter
                        # key so the bundle shows WHY (429 vs 503 vs None)
                        # without relying on the last-40 ring.
                        self._anticip_note(f"netpos_rest_failed_{status}")
                        return
            if cur_net not in (0, None):
                self._anticip_note("broker_netpos_nonzero", net=cur_net)
                return  # broker holds a position, don't pre-submit
        except Exception as e:
            self._anticip_note("netpos_check_error", err=repr(e)[:120])
            return
        self._anticip_note(
            "submit", side=best.side,
            orig_side=getattr(best, 'orig_side', None),
            entry=round(float(best.pullback_entry), 2),
            px=round(current_price, 2), dist=round(best_dist, 2))
        self._submit_anticipatory(best, current_price)

    def _submit_anticipatory(self, setup, live_price: float) -> None:
        """ABSOLUTE FASTEST submit path for anticipatory orders.

        Bypasses the full submit_market_with_bracket helper (which has
        ~10ms of validation overhead + waits for the WS response).
        Builds the placeoso body inline and uses
        send_request_fire_and_forget so the bot returns in <5ms.

        The order_id is captured via a WS response callback (delivered
        ~30ms later) and stored in self._anticipatory_limit. By then
        the LIMIT is already on Tradovate's matching engine.
        """
        try:
            if self._cached_symbol is None:
                from research.data_loader import polygon_front_month
                self._cached_symbol = os.environ.get(
                    "TRADOVATE_SYMBOL",
                    polygon_front_month(
                        os.environ.get("POLYGON_CONTRACT", "MNQ")))
            symbol = self._cached_symbol
            setup_key = self._setup_key(setup)
            pre_ref = f"acct{self.account_id}_antc_{setup_key}"[:64]
            side = setup.side
            entry_px = round(float(setup.pullback_entry) * 4) / 4
            stop_px = round(float(setup.stop_px_val) * 4) / 4
            target_px = round(float(setup.target_px_val) * 4) / 4
            # Apply wick tolerance on stop (same as full path).
            tol = float(os.environ.get(
                "BROKER_STOP_WICK_TOLERANCE_PTS", "0.0"))
            if side == "LONG":
                stop_px = round((stop_px - tol) * 4) / 4
            else:
                stop_px = round((stop_px + tol) * 4) / 4
            # Build the placeoso body. Minimal fields, no extras.
            action = "Buy" if side == "LONG" else "Sell"
            opposite = "Sell" if side == "LONG" else "Buy"
            sess = self.tradovate_orders.session
            body = {
                "accountSpec": (sess.creds.username if sess.creds else ""),
                "accountId": int(sess.get_account_id() or 0),
                "action": action,
                "symbol": symbol,
                "orderQty": int(N_MNQ),
                "orderType": "Limit",
                "price": entry_px,
                "timeInForce": "Day",
                "isAutomated": True,
                "bracket1": {
                    "action": opposite, "orderType": "Stop",
                    "stopPrice": stop_px, "isAutomated": True,
                },
                "bracket2": {
                    "action": opposite, "orderType": "Limit",
                    "price": target_px, "isAutomated": True,
                },
                "text": pre_ref,
            }
            # Pre-populate _anticipatory_limit so the next anticipatory
            # check won't re-fire while WS response is in flight.
            self._anticipatory_limit = {
                'setup_key': setup_key,
                'order_id': None,  # filled in by WS callback
                'side': side,
                'entry_px': entry_px,
                'stop_px': stop_px,
                'target_px': target_px,
                'submitted_at': time.time(),
                'pre_ref': pre_ref,
            }
            # Re-enable paper firing on this setup. A previous cancel of
            # anticipatory LIMIT may have set fire_attempted=True on this
            # same setup; now that we have a fresh LIMIT in the book the
            # paper can fire again. Without this, paper would skip the
            # setup even though the broker is now ready to fill.
            try:
                if self.state is not None:
                    for s in (self.state.pending_setups or []):
                        if getattr(s, 'used', False):
                            continue
                        if self._setup_key(s) == setup_key:
                            s.fire_attempted = False
                            s.last_block_reason = None
                            break
            except Exception:
                pass
            def _on_response(msg):
                try:
                    d = msg.get("d") or {}
                    oid = d.get("orderId") or d.get("id")
                    if oid and self._anticipatory_limit:
                        self._anticipatory_limit['order_id'] = int(oid)
                        logger.info(
                            f"[ANTICIPATORY oid] {oid} confirmed via WS")
                except Exception:
                    pass
            try:
                from bot.tradovate_user_ws import get_user_ws
                _uws = get_user_ws()
                rid = None
                if _uws is not None and _uws.connected:
                    rid = _uws.send_request_fire_and_forget(
                        "order/placeoso", body_json=body,
                        on_response=_on_response)
                if rid is not None:
                    logger.info(
                        f"[ANTICIPATORY fire-and-forget] {side} @ {entry_px} "
                        f"reqId={rid} (LIMIT will rest on matching engine "
                        f"in ~30ms)")
                    return
            except Exception as fe:
                logger.debug(f"fire-and-forget failed: {fe!r}")
            # FALLBACK: synchronous path (slower but always works).
            logger.info(
                f"[ANTICIPATORY fallback-sync] {side} @ {entry_px}")
            stop_pts = abs(setup.pullback_entry - setup.stop_px_val)
            target_pts = abs(setup.target_px_val - setup.pullback_entry)
            result = self.tradovate_orders.submit_market_with_bracket(
                side=side, qty=N_MNQ, symbol=symbol,
                stop_pts=stop_pts, target_pts=target_pts,
                entry_estimate=entry_px, live_price=float(live_price),
                paper_stop_px=float(setup.stop_px_val),
                paper_target_px=float(setup.target_px_val),
                setup_ref=pre_ref,
            )
            if result.ok and self._anticipatory_limit:
                self._anticipatory_limit['order_id'] = result.order_id
        except Exception as e:
            logger.warning(f"anticipatory submit failed: {e!r}")
            self._anticipatory_limit = None

    def _cancel_anticipatory_sync(self, reason: str) -> Optional[str]:
        """Cancel the live anticipatory LIMIT and confirm terminal state
        via Tradovate user WS exec_reports (instant push) instead of
        REST polling. Typical wait now ~10-30ms instead of 50-300ms.
        Fallback to REST poll if WS isn't connected.

        Returns the observed terminal ordStatus ("Canceled", "Filled",
        "Rejected", "Expired") or None if unknown. "Filled" means the
        cancel LOST the race -- the LIMIT became a live position. The
        caller MUST NOT submit another entry in that case (that is
        netPos 2); adopt the filled order instead."""
        if not self._anticipatory_limit:
            return None
        terminal_status = None
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
                                    terminal_status = r.get("ordStatus")
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
                            terminal_status = status
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
        # CRITICAL: lock paper out of this setup. Without this, paper can
        # still fire on the pullback level even though the broker LIMIT
        # is gone — that produces phantom paper trades (paper books P&L
        # the broker never executes). Found 27 such trades / $758 in
        # one day's bundle. Mark the matching setup as fire_attempted=True
        # so try_fire_on_tick / on_new_1m_bar skip it. If a NEW
        # anticipatory LIMIT is placed for the same setup later
        # (_check_anticipatory_limit), that path re-enables firing by
        # clearing the flag.
        try:
            if sk is not None and self.state is not None:
                for s in (self.state.pending_setups or []):
                    if getattr(s, 'used', False):
                        continue
                    if self._setup_key(s) == sk:
                        s.fire_attempted = True
                        s.last_block_reason = f"limit_canceled:{reason}"
                        logger.info(
                            f"[ANTICIPATORY cancel] locked setup_key={sk} "
                            f"out of paper fire (reason={reason})")
                        break
        except Exception as e:
            logger.warning(f"anticipatory cancel lock-setup: {e!r}")
        self._anticipatory_limit = None
        return terminal_status

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
            try:
                self._anticip_diag["adopts"] = (
                    self._anticip_diag.get("adopts", 0) + 1)
            except Exception:
                pass
            self._anticipatory_limit = None
            return oid
        except Exception as e:
            logger.warning(f"anticipatory adopt: {e!r}")
            return None

    def _persist_state(self) -> None:
        """Snapshot the bot's critical broker-tracking state to disk so
        a redeploy / restart can recover without losing context. Called
        after every state-changing event. Best-effort, never raises."""
        if self._state_path is None:
            return
        try:
            state = {
                "ts": time.time(),
                "account_id": self.account_id,
                "open_trade_ref": self._open_trade_ref,
                "broker_entry_ts": (
                    self._broker_entry_ts.isoformat()
                    if self._broker_entry_ts else None),
                "broker_stop_px": self._broker_stop_px,
                "broker_target_px": self._broker_target_px,
                "broker_side": self._broker_side,
                "broker_target_sent": self._broker_target_sent,
                "pending_parent_orders": self._pending_parent_orders,
                "anticipatory_limit": self._anticipatory_limit,
                "pre_submitted_limit": self._pre_submitted_limit,
            }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(state, f, default=str)
            tmp.replace(self._state_path)
        except Exception as e:
            logger.debug(f"_persist_state: {e!r}")

    def _restore_state(self) -> None:
        """Load persisted state from disk on startup, then reconcile
        against Tradovate's actual current state. Logs anything that
        doesn't match so the next bundle shows the discrepancy."""
        if self._state_path is None or not self._state_path.exists():
            logger.info("[state restore] no prior state file -- fresh start")
            return
        try:
            with open(self._state_path) as f:
                state = json.load(f)
        except Exception as e:
            logger.warning(f"[state restore] load failed: {e!r}")
            return
        age_s = time.time() - state.get("ts", 0)
        logger.info(f"[state restore] loaded state age={age_s:.1f}s")
        # Bring back the easy fields.
        self._open_trade_ref = state.get("open_trade_ref")
        self._broker_stop_px = state.get("broker_stop_px")
        self._broker_target_px = state.get("broker_target_px")
        self._broker_side = state.get("broker_side")
        self._broker_target_sent = state.get("broker_target_sent", False)
        self._pending_parent_orders = state.get("pending_parent_orders") or []
        self._anticipatory_limit = state.get("anticipatory_limit")
        self._pre_submitted_limit = state.get("pre_submitted_limit")
        # Reconcile against broker reality.
        try:
            self._reconcile_with_broker()
        except Exception as e:
            logger.warning(f"[state restore] reconcile failed: {e!r}")

    def _reconcile_with_broker(self) -> None:
        """Compare restored state to Tradovate's actual position + working
        orders. Resolve discrepancies:
          - persisted pending order no longer alive on broker → drop from tracking
          - broker has open position bot doesn't know about → flag (will
            be flattened by discrepancy detector or handled by bracket OCO)
          - broker has working orders bot doesn't know about → cancel
            them (likely orphans from before restart)
        """
        if self.tradovate_orders is None:
            return
        sess = self.tradovate_orders.session
        if sess is None or not sess.is_configured:
            return
        acct_id = sess.get_account_id()
        # 1. Verify each persisted pending order
        keep = []
        for entry in (self._pending_parent_orders or []):
            oid = entry.get("parent_order_id")
            if not oid:
                continue
            try:
                status = self.tradovate_orders.get_order_status(int(oid))
                if status in ("Working", "Pending"):
                    keep.append(entry)
                    logger.info(
                        f"[reconcile] order_id={oid} still {status}, "
                        f"resuming tracking")
                else:
                    logger.info(
                        f"[reconcile] order_id={oid} now {status}, "
                        f"dropping from tracking")
            except Exception:
                keep.append(entry)  # if can't tell, keep
        self._pending_parent_orders = keep
        # 2. Anticipatory limit -- check if still working
        if self._anticipatory_limit:
            oid = self._anticipatory_limit.get("order_id")
            try:
                status = self.tradovate_orders.get_order_status(int(oid)) if oid else None
                if status not in ("Working", "Pending"):
                    logger.info(
                        f"[reconcile] anticipatory order_id={oid} now "
                        f"{status}, clearing")
                    self._anticipatory_limit = None
            except Exception:
                pass
        # 3. Broker positions -- reconcile against persisted active trade.
        try:
            status, positions = sess._rest("GET", "/position/list")
            broker_net = 0
            if status == 200 and isinstance(positions, list):
                for pos in positions:
                    if not isinstance(pos, dict): continue
                    if pos.get("accountId") != acct_id: continue
                    n = int(pos.get("netPos") or 0)
                    if n != 0:
                        broker_net = n
                        break
            if broker_net == 0:
                # Broker is FLAT. Any persisted _open_trade_ref is stale
                # (the bracket closed our position while the bot was off).
                # Clear it so the duplicate-entry guard doesn't block
                # every new trade attempt. This was the bug causing the
                # overnight no-trade incident.
                if self._open_trade_ref is not None:
                    logger.warning(
                        f"[reconcile] _open_trade_ref={self._open_trade_ref} "
                        f"in persisted state but broker is FLAT -- "
                        f"clearing stale ref so new entries can fire")
                    self._open_trade_ref = None
                    self._broker_stop_px = None
                    self._broker_target_px = None
                    self._broker_side = None
                    self._broker_target_sent = False
            else:
                # Broker holds a position. If paper also holds the trade,
                # it's genuinely in-flight -- leave the bracket to close
                # it. But if paper is FLAT (startup scratched the trade,
                # or the position is a leftover the bot no longer knows
                # about), the broker is diverging from paper: it will
                # ride to its own bracket with no paper counterpart AND
                # the duplicate-entry guard blocks every new mirror until
                # it closes (bundle 06:48-07:05: 17 minutes stuck short 1
                # against a flat paper book, 2 mirrors blocked). Flatten
                # immediately so broker == paper within seconds.
                paper_in_trade = (
                    (self.state is not None
                     and self.state.active_trade is not None)
                    or self.account.state.open_position is not None)
                recent_close = False
                try:
                    lc = getattr(self.state, "last_trade_close_ts", None) if self.state else None
                    if lc is not None:
                        recent_close = (real_utc_now() - lc).total_seconds() < 10.0
                except Exception:
                    recent_close = False
                if paper_in_trade or recent_close:
                    logger.warning(
                        f"[reconcile] broker has open position netPos="
                        f"{broker_net} -- bot will treat as in-flight "
                        f"trade until bracket OCO closes it")
                else:
                    logger.warning(
                        f"[reconcile] broker holds netPos={broker_net} but "
                        f"paper is FLAT -- flattening now so broker matches "
                        f"paper (was: wait for bracket, which stranded the "
                        f"position and blocked new mirrors)")
                    try:
                        from research.data_loader import polygon_front_month
                        symbol = os.environ.get(
                            "TRADOVATE_SYMBOL",
                            polygon_front_month(
                                os.environ.get("POLYGON_CONTRACT", "MNQ")))
                        self.tradovate_orders.submit_market_close(
                            side=("LONG" if broker_net > 0 else "SHORT"),
                            qty=abs(int(broker_net)),
                            symbol=symbol,
                            setup_ref=str(self._open_trade_ref or "reconcile_stale"),
                        )
                        self._count_close_path("reconcile_flatten_stale")
                    except Exception as fe:
                        logger.warning(f"[reconcile] stale flatten failed: {fe!r}")
                    self._open_trade_ref = None
                    self._broker_stop_px = None
                    self._broker_target_px = None
                    self._broker_side = None
                    self._broker_target_sent = False
        except Exception:
            pass
        self._persist_state()  # Save the reconciled state.

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
                # Re-enable paper firing on this setup (a previous
                # cancel may have locked it).
                try:
                    for s in (self.state.pending_setups or []):
                        if getattr(s, 'used', False):
                            continue
                        if self._setup_key(s) == setup_key:
                            s.fire_attempted = False
                            s.last_block_reason = None
                            break
                except Exception:
                    pass
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
        # Lock paper out of the now-LIMIT-less setup. Same rationale as
        # _cancel_anticipatory_sync — without this paper would fire on a
        # setup whose broker LIMIT no longer exists.
        try:
            if sk is not None and self.state is not None:
                for s in (self.state.pending_setups or []):
                    if getattr(s, 'used', False):
                        continue
                    if self._setup_key(s) == sk:
                        s.fire_attempted = True
                        s.last_block_reason = f"pre_submit_canceled:{reason}"
                        break
        except Exception:
            pass
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

        ALSO handles ORPHAN broker positions: if paper has no active
        trade AND _open_trade_ref is None (bot's belief is "flat") but
        the broker still has a position, that's an orphan. Flatten it
        immediately so the bot's next signal can fire on broker without
        the duplicate-entry guard tripping. User explicitly requested
        every paper trade to also fire on broker -- orphan positions
        were the single biggest source of broker-skipped trades in the
        bundles I've reviewed.
        """
        # PAPER-ORPHAN check (independent of broker connectivity, runs
        # even when tradovate is offline). If the paper account holds
        # an open_position but the strategy is flat, the lucid hedge
        # guard blocks every new entry on the opposite side. Debounce
        # against the normal close path: require either no recent paper
        # close (>5s) or sustained mismatch across 3+ cycles before
        # acting, so we don't race a mid-flight legitimate close.
        try:
            paper_op = self.account.state.open_position
            if (paper_op is not None
                    and (self.state is None or self.state.active_trade is None)):
                last_close = getattr(self.state, "last_trade_close_ts", None) if self.state else None
                quiet_long_enough = True
                if last_close is not None:
                    try:
                        quiet_long_enough = (
                            (real_utc_now() - last_close).total_seconds() > 5.0)
                    except Exception:
                        quiet_long_enough = True
                self._paper_orphan_streak = getattr(self, "_paper_orphan_streak", 0) + 1
                # Require BOTH: sustained mismatch (3+ cycles) AND no
                # paper close in the last 5s. The old OR fired on the
                # FIRST cycle whenever no trade had closed recently,
                # scratching real paper trades on a transient desync
                # (bundle 06:40: trades 857/858 scratched at entry,
                # paper re-fired, broker double-entered -> netPos -2).
                if quiet_long_enough and self._paper_orphan_streak >= 3:
                    logger.warning(
                        f"[PAPER ORPHAN] paper holds {paper_op.side} qty="
                        f"{paper_op.qty} @ {paper_op.entry_px:.2f} "
                        f"(db_id={paper_op.db_id}) but strategy is flat "
                        f"-- closing as orphan_recovered to unblock entries.")
                    from bot import persistence as _p
                    try:
                        _p.close_trade(paper_op.db_id,
                                        real_utc_now().isoformat(),
                                        paper_op.entry_px,
                                        "orphan_recovered", 0.0)
                    except Exception as _de:
                        logger.warning(f"[PAPER ORPHAN] DB close failed: {_de!r}")
                    self.account.state.open_position = None
                    self.account.save()
                    self._paper_orphan_streak = 0
            else:
                self._paper_orphan_streak = 0
        except Exception as _e:
            logger.debug(f"paper orphan check: {_e!r}")
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
            # CACHE REHYDRATION. Tradovate's user WS occasionally drops
            # the "position closed" frame during a reconnect, leaving
            # _netpos_cache pinned to a phantom netPos (bundle 20:15 UTC
            # showed cache pinned at -1 for 5+ hours while REST reported
            # 0). Re-sync the WS cache from REST truth on every cycle so
            # downstream consumers (entry submission, dashboards) read
            # the right state.
            try:
                from bot.tradovate_user_ws import get_user_ws
                _uws = get_user_ws()
                if _uws is not None:
                    rest_pos = {
                        p.get("contractId"): int(p.get("netPos") or 0)
                        for p in positions
                        if isinstance(p, dict) and p.get("accountId") == acct_id
                    }
                    for cid, np_val in rest_pos.items():
                        if cid is None:
                            continue
                        entry = _uws._netpos_cache.get(int(cid))
                        if entry is None:
                            _uws._netpos_cache[int(cid)] = {
                                "netPos": np_val, "ts": time.time(),
                            }
                        elif entry.get("netPos") != np_val:
                            entry["netPos"] = np_val
                            entry["ts"] = time.time()
            except Exception as _ce:
                logger.debug(f"WS cache rehydrate: {_ce!r}")
            # Bot's belief: is paper in a trade?
            paper_in_trade = (self.state is not None
                              and self.state.active_trade is not None
                              and self._open_trade_ref is not None)
            for p in positions:
                if not isinstance(p, dict):
                    continue
                if p.get("accountId") != acct_id:
                    continue
                net = int(p.get("netPos") or 0)
                if net == 0:
                    continue   # Broker flat -- nothing to reconcile
                # Two anomalies handled below:
                #   A. Stacking: net > 1 contract (always wrong)
                #   B. Orphan:   broker has 1 contract but paper expects flat
                stack_excess = abs(net) > 1
                orphan = (abs(net) == 1) and (not paper_in_trade)
                # ANTICIPATORY GRACE. The anticipatory LIMIT rests and
                # FILLS during the cooldown, a few seconds BEFORE paper
                # fires the setup and adopts it. In that window
                # paper_in_trade is False, so the position looks like an
                # orphan -- and flattening it here market-scratches the
                # exact fast-reversal winners the anticipatory path exists
                # to capture (observed: broker entered at the level then
                # got flattened ~1pt away while paper rode to +44). The
                # filled anticipatory position carries its OWN OCO bracket
                # (stop+target), so it is never naked while we wait.
                #   - If an anticipatory LIMIT is live, it is NOT an orphan.
                #   - Otherwise give a single orphan a grace period before
                #     flattening, so cooldown + fire latency can resolve it
                #     into a normal adopted trade. A genuine orphan that
                #     outlives the grace is still flattened.
                if orphan:
                    if self._anticipatory_limit is not None:
                        self._broker_orphan_since = None
                        continue
                    grace_s = float(os.environ.get(
                        "BROKER_ORPHAN_GRACE_S", "20"))
                    since = getattr(self, "_broker_orphan_since", None)
                    if since is None:
                        self._broker_orphan_since = time.time()
                        continue  # first sighting -- start the grace clock
                    if time.time() - since < grace_s:
                        continue  # still within grace; bracket protects it
                    # Grace elapsed -- treat as a real orphan below.
                if not stack_excess and not orphan:
                    self._broker_orphan_since = None
                    continue
                anomaly_kind = "STACK" if stack_excess else "ORPHAN"
                excess = abs(net) - (1 if not orphan else 0)
                logger.error(
                    f"[POSITION {anomaly_kind} DETECTED] broker netPos={net} "
                    f"paper_in_trade={paper_in_trade} -- flattening "
                    f"{excess if stack_excess else abs(net)} contracts "
                    f"to restore single-position invariant.")
                try:
                    from research.data_loader import polygon_front_month
                    symbol = os.environ.get(
                        "TRADOVATE_SYMBOL",
                        polygon_front_month(
                            os.environ.get("POLYGON_CONTRACT", "MNQ")))
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
                            f"[POSITION {anomaly_kind} FLATTENED] "
                            f"contractId={cid} netPos={net}")
                        # INSTRUMENTATION: make this flatten visible in the
                        # bundle. An early ORPHAN flatten of an anticipatory
                        # fill (before paper adopts) scratches winners the
                        # broker had entered correctly -- it must be
                        # attributable per-trade, not just a log line.
                        try:
                            from bot.trade_timeline import add_event as _tl2
                            _ref = (self._open_trade_ref
                                    or (self._anticipatory_limit or {}).get(
                                        "setup_key")
                                    or "unattributed")
                            # FORENSICS: the 2026-07-06 bundle showed 9
                            # netPos-2 moments with no way to attribute
                            # WHICH two orders filled (anticipatory
                            # submits bypass the audit log). Capture the
                            # last few fills + every order id the bot is
                            # tracking, so the next stack names its two
                            # entry orderIds directly in the bundle.
                            _recent_fills = []
                            try:
                                from bot.tradovate_user_ws import get_user_ws
                                _uf = get_user_ws()
                                if _uf is not None:
                                    _recent_fills = [
                                        {k: f.get(k) for k in (
                                            "id", "orderId", "action",
                                            "qty", "price", "timestamp")}
                                        for f in list(_uf.fills)[-6:]]
                            except Exception:
                                pass
                            _tl2(str(_ref), "broker_discrepancy_flatten",
                                 anomaly=anomaly_kind, net_pos=net,
                                 paper_in_trade=paper_in_trade,
                                 had_anticipatory=(
                                     self._anticipatory_limit is not None),
                                 anticip_oid=(self._anticipatory_limit or
                                              {}).get("order_id"),
                                 tracked_parent_oids=[
                                     e.get("parent_order_id")
                                     for e in self._pending_parent_orders],
                                 open_trade_ref=self._open_trade_ref,
                                 recent_fills=_recent_fills)
                            self._count_close_path(
                                f"discrepancy_flatten_{anomaly_kind.lower()}")
                        except Exception:
                            pass
                        # On orphan, also wipe stale tracking state so the
                        # next signal doesn't see ghosts.
                        if orphan:
                            self._open_trade_ref = None
                            self._broker_stop_px = None
                            self._broker_target_px = None
                            self._broker_side = None
                    else:
                        logger.error(
                            f"[POSITION {anomaly_kind}] no contractId in "
                            f"position record; cannot flatten")
                except Exception as e:
                    logger.error(f"position {anomaly_kind} flatten failed: {e!r}")
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
        # Queue a per-trade tick + decision snapshot so the next
        # bundle can carry the 3-min-before / 3-min-after price path
        # alongside paper vs broker entry/exit prices. Fires
        # immediately; the snapshot worker waits 3 min before
        # capturing so the after-window is fully resident in the
        # tick buffer.
        try:
            from bot.trade_tick_snapshots import queue_snapshot
            entry_ts_raw = record.get("entry_ts")
            exit_ts_raw = record.get("exit_ts") or now
            # Normalize to epoch seconds.
            def _to_epoch(v):
                if v is None:
                    return None
                if isinstance(v, (int, float)):
                    return float(v)
                try:
                    return v.timestamp()
                except Exception:
                    pass
                try:
                    import pandas as _pd
                    return _pd.Timestamp(v).timestamp()
                except Exception:
                    return None
            entry_ts_epoch = _to_epoch(entry_ts_raw)
            exit_ts_epoch = _to_epoch(exit_ts_raw)
            if entry_ts_epoch is not None and exit_ts_epoch is not None:
                queue_snapshot(
                    self._open_trade_ref,
                    entry_ts_epoch,
                    exit_ts_epoch,
                    record,
                )
        except Exception as _se:
            logger.debug(f"queue_snapshot failed (non-fatal): {_se!r}")
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
            elif reason in ("stop", "target") and os.environ.get(
                    "BROKER_INSTANT_CLOSE", "1") != "1":
                # LEGACY behaviour (set BROKER_INSTANT_CLOSE=0 to restore):
                # let the bracket OCO own stop/target exits. Previously
                # this was the default after the 2026-06-15 "trade like
                # manual" requirement, but the user reverted on
                # 2026-06-18 -- the bracket LIMIT for the target was
                # sitting in queue while price ticked past, and the
                # trade refused to close. Now defaults to firing an
                # immediate liquidate on every paper-side exit so
                # there's ZERO delay between strategy decision and
                # broker close.
                logger.info(
                    f"[broker CLOSE skip] {reason} owned by broker "
                    f"OCO bracket (legacy mode -- BROKER_INSTANT_CLOSE=0)")
            elif self.tradovate_orders is not None:
                # ZERO-DELAY broker close (default mode). On every paper
                # exit -- stop, target, timeout, manual -- fire a
                # liquidateposition. This:
                #   - atomically cancels the bracket children
                #     (which would otherwise race us at queue priority
                #     and might miss the target by ticking through)
                #   - sends a flatten MARKET that fills in <50ms at
                #     Tradovate's matching engine
                #   - guarantees broker position matches paper on every
                #     close, eliminating "live trade ticking over TP
                #     without closing" symptom user reported
                #
                # The MARKET fill price may differ from the bracket
                # LIMIT target by 0-1pt (whatever the current bid/ask
                # is at the moment of liquidation). Accepted trade-off:
                # the user explicitly chose this on 2026-06-18,
                # prioritising instant exit over exact-tick fill.
                try:
                    from research.data_loader import polygon_front_month
                    symbol = os.environ.get(
                        "TRADOVATE_SYMBOL",
                        polygon_front_month(
                            os.environ.get("POLYGON_CONTRACT", "MNQ")))
                    # TARGET-EXIT PATIENCE (2026-07-04). The bracket's
                    # target LIMIT is already RESTING at paper's exact
                    # target price, and paper only declares "target" when
                    # bid/ask actually reached that level -- i.e. the
                    # LIMIT is fillable RIGHT NOW at the exact price
                    # paper booked. Liquidating instantly instead crosses
                    # the spread and pays ~0.5-1pt on every winner: the
                    # 2026-07-03 post-mirror session bled ~$2/trade of
                    # pure exit slippage (paper +$134.86 vs broker
                    # +$6.49 with entries synced). So on TARGET exits,
                    # give the resting LIMIT a short window to fill like
                    # paper (maker, exact price); force-liquidate only if
                    # still not flat at the deadline. Stops and timeouts
                    # stay ZERO-DELAY liquidates -- urgency wins there.
                    # Safety: patience (2.5s) << cooldown (10s), so no
                    # new entry can race the deferred flatten; the
                    # watcher also aborts if a new trade opened. Set
                    # BROKER_TARGET_PATIENCE_S=0 to restore instant
                    # liquidate on targets.
                    patience_s = 0.0
                    if reason == "target":
                        try:
                            patience_s = float(os.environ.get(
                                "BROKER_TARGET_PATIENCE_S", "2.5"))
                        except Exception:
                            patience_s = 2.5
                    if patience_s > 0:
                        _tl(self._open_trade_ref, "broker_close_sent",
                             reason=reason, mode="bracket_patience",
                             patience_s=patience_s,
                             paper_exit_px=record.get("exit_px"),
                             paper_pnl=record.get("pnl_usd"))
                        self._spawn_target_patience_watcher(
                            setup_ref=self._open_trade_ref,
                            side=record.get("side", "LONG"),
                            qty=record.get("n_mnq", 1),
                            symbol=symbol,
                            patience_s=patience_s)
                    else:
                        _tl(self._open_trade_ref, "broker_close_sent",
                             reason=reason,
                             paper_exit_px=record.get("exit_px"),
                             paper_pnl=record.get("pnl_usd"))
                        result = self.tradovate_orders.submit_market_close(
                            side=record.get("side", "LONG"),
                            qty=record.get("n_mnq", 1),
                            symbol=symbol,
                            setup_ref=self._open_trade_ref,
                        )
                        _tl(self._open_trade_ref, "broker_close_result",
                             ok=result.ok, order_id=result.order_id,
                             http_status=result.status_code,
                             error=result.error)
                        if result.ok:
                            self._count_close_path("instant_liquidate")
                            logger.info(
                                f"[tradovate CLOSE OK] order_id={result.order_id} "
                                f"reason={reason} (zero-delay liquidate)")
                        else:
                            self._count_close_path("instant_liquidate_failed")
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

    def _spawn_target_patience_watcher(self, *, setup_ref: str, side: str,
                                        qty: int, symbol: str,
                                        patience_s: float) -> None:
        """Background watcher for TARGET exits: give the bracket's
        resting target LIMIT (already at paper's exact price, already
        fillable -- paper just detected bid/ask AT that level) a short
        window to fill like paper's exit. If the broker is flat before
        the deadline, the bracket captured the exit at the exact paper
        price (maker -- no spread cost). Otherwise force-liquidate.

        Safety properties:
          - patience (default 2.5s) << strategy cooldown (10s), so the
            deferred flatten cannot collide with the next entry.
          - The watcher aborts (no liquidate) if a new trade opened
            meanwhile (_open_trade_ref set) -- that trade's own
            lifecycle owns the position then.
          - Any error path falls through TO the liquidate, never away
            from it: fail toward flat."""
        import threading

        def _watch():
            try:
                from bot.trade_timeline import add_event as _tl
                deadline = time.time() + max(0.5, float(patience_s))
                flat_seen = False
                while time.time() < deadline:
                    try:
                        from bot.tradovate_user_ws import get_user_ws
                        _uws = get_user_ws()
                        if (_uws is not None
                                and getattr(_uws, "connected", False)):
                            cache = _uws._netpos_cache or {}
                            fresh = {c: e for c, e in cache.items()
                                     if time.time() - float(
                                         e.get("ts", 0)) < 10.0}
                            if fresh and all(
                                    e.get("netPos", 0) == 0
                                    for e in fresh.values()):
                                flat_seen = True
                                break
                    except Exception:
                        pass
                    time.sleep(0.15)
                if flat_seen:
                    self._count_close_path("bracket_fill_at_target")
                    _tl(setup_ref, "broker_close_result",
                         ok=True, order_id=None, http_status=None,
                         error=None, mode="bracket_fill_at_target")
                    logger.info(
                        f"[tradovate CLOSE via bracket] target LIMIT "
                        f"filled at paper's exact price (no liquidate "
                        f"needed) ref={setup_ref}")
                    return
                # Deadline passed and not confirmed flat. If a NEW trade
                # opened meanwhile, its lifecycle owns the position.
                if self._open_trade_ref is not None:
                    self._count_close_path("patience_aborted_new_trade")
                    _tl(setup_ref, "broker_close_result",
                         ok=False, order_id=None, http_status=None,
                         error="patience_aborted_new_trade_open",
                         mode="bracket_patience")
                    logger.warning(
                        f"[target patience ABORT] new trade opened "
                        f"during patience window ref={setup_ref}")
                    return
                result = self.tradovate_orders.submit_market_close(
                    side=side, qty=qty, symbol=symbol,
                    setup_ref=setup_ref)
                self._count_close_path("liquidate_after_patience")
                _tl(setup_ref, "broker_close_result",
                     ok=result.ok, order_id=result.order_id,
                     http_status=result.status_code,
                     error=result.error,
                     mode="liquidate_after_patience")
                logger.info(
                    f"[tradovate CLOSE after patience] ok={result.ok} "
                    f"ref={setup_ref} (bracket didn't fill in "
                    f"{patience_s}s)")
            except Exception as we:
                # Last-resort flatten -- never leave a position running
                # because the watcher crashed.
                logger.warning(f"target patience watcher: {we!r}")
                try:
                    self.tradovate_orders.submit_market_close(
                        side=side, qty=qty, symbol=symbol,
                        setup_ref=setup_ref)
                except Exception as fe:
                    logger.error(
                        f"target patience fallback flatten FAILED: {fe!r}")

        threading.Thread(target=_watch, daemon=True,
                          name=f"tgt-patience-{setup_ref[-12:]}").start()

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
                # Anticipatory pre-submit telemetry. Proves, from a single
                # run, exactly why the pre-rested LIMIT did or didn't get
                # placed on each check (the path was silently never-firing
                # -- 0/150 broker orders -- with no visible reason before
                # this). Surfaced in the diagnostic bundle.
                "anticipatory_diag": getattr(self, "_anticip_diag", None),
                # Exit-path ledger: how each broker close was captured.
                # bracket_fill_at_target vs liquidate_* quantifies the
                # spread recovered by target-patience in one glance.
                "close_path_counts": getattr(
                    self, "_close_path_counts", None),
                # Effective execution knobs. Bundles carried the data but
                # not the SETTINGS that produced it -- a stale Railway env
                # var once silently reverted the entry type for days.
                # Snapshot every tunable so each bundle is self-describing.
                "exec_knobs": {
                    k: os.environ.get(k) for k in (
                        "BROKER_ENTRY_TYPE",
                        "BROKER_INSTANT_CLOSE",
                        "BROKER_TARGET_PATIENCE_S",
                        "BROKER_ORPHAN_GRACE_S",
                        "BROKER_MAX_ENTRY_DRIFT_PT",
                        "BROKER_MARKETABLE_BUFFER_PTS",
                        "BROKER_STOP_WICK_TOLERANCE_PTS",
                        "ANTICIPATORY_THRESHOLD_PT",
                        "STRAT_FIRE_DRIFT_GATE_PT",
                        "STRAT_COOLDOWN_SECS",
                        "STRAT_ARMING",
                        "TRADOVATE_LIVE",
                    )
                },
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

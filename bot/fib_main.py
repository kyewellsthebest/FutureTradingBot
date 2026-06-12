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
    def _tick(self) -> None:
        self.cycle += 1
        now = real_utc_now()
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
                live_snap = self.monitor.latest()
                logger.info(f"[broker gate 3/4 live_price] snap="
                            f"{'None' if live_snap is None else f'{live_snap.price:.2f}'}")
                if live_snap is None:
                    logger.warning(
                        f"[{broker_name} SKIP] no live price -- refusing entry")
                    return
                divergence = abs(trade.entry_px - live_snap.price)
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
                    return

                # All gates passed -- send the order
                stop_pts = abs(trade.entry_px - trade.stop_px)
                target_pts = abs(trade.target_px - trade.entry_px)
                if use_tradovate:
                    # Resolve symbol the same way the WS subscriber did.
                    from research.data_loader import polygon_front_month
                    symbol = os.environ.get(
                        "TRADOVATE_SYMBOL",
                        polygon_front_month(
                            os.environ.get("POLYGON_CONTRACT", "MNQ")))
                    logger.info(
                        f"[tradovate SEND BRACKET] {trade.side} "
                        f"{trade.n_mnq} {symbol} stop={stop_pts:.2f}pt "
                        f"target={target_pts:.2f}pt (live={live_snap.price:.2f})")
                    result = self.tradovate_orders.submit_market_with_bracket(
                        side=trade.side, qty=trade.n_mnq, symbol=symbol,
                        stop_pts=stop_pts, target_pts=target_pts,
                        setup_ref=setup_ref,
                    )
                    if not result.ok:
                        logger.error(f"[tradovate order REJECTED] {result.error}")
                        return
                    logger.info(f"[tradovate order ACCEPTED] order_id="
                                f"{result.order_id}")
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

    def _on_trade_close(self, record: dict, now: datetime) -> None:
        # Always close through the paper account so balance updates and
        # the trade is persisted to the SQLite DB — surviving restarts.
        adverse = (record["exit_reason"] == "stop")
        try:
            self.account._close(exit_px_raw=record["exit_px"],
                                reason=record["exit_reason"],
                                adverse=adverse, now=now)
            tag = "SHADOW" if _is_shadow_mode() else "LIVE"
            logger.info(f"[{tag} CLOSE] {record['side']} pnl=${record['pnl_usd']:+,.2f} "
                        f"hold={record['hold_s']:.1f}s reason={record['exit_reason']}")
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
                logger.info(
                    f"[broker CLOSE skip] {reason} owned by broker "
                    f"OCO bracket -- exchange handles it at fill price")
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

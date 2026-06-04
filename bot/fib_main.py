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
        # Panic-close: catch broker brackets that didn't fire.
        # ------------------------------------------------------------------
        # If we're in a trade AND we successfully forwarded the open to the
        # broker (i.e. self._open_trade_ref is set, meaning the kill-switch
        # didn't block it) AND live market has crossed the intended stop
        # level, force-flatten on the broker. This catches the case where
        # TradersPost auto-converted our limit entry to MARKET because the
        # limit price was unreachable from current market -- the bracket
        # then anchors to the stale strategy price, leaving the position
        # effectively naked. Without panic close, the position runs until
        # the bot's 1-min bar exit fires, by which time it's slipped 7-15pt
        # past the intended stop (observed in real trades: -$60 to -$114
        # losses on positions with a $24 intended stop).
        if (in_trade and self._open_trade_ref is not None
                and self._broker_stop_px is not None
                and self._broker_target_px is not None
                and self._broker_side is not None
                and self._panic_closed_ref != self._open_trade_ref
                and snap is not None):
            # Compare live price against the BROKER-ANCHORED stop and
            # target (set at submit_open from live monitor price), not
            # the strategy's stop_px / target_px (which are anchored to
            # a closed-bar entry that can be 20-40pt off from real fill).
            #
            # SYMMETRIC -- panic on BOTH stop breach AND target breach.
            # Without the target-side check, observed bug: bracket TP
            # didn't fire on the broker, position ran from intended
            # +$48 to +$100+ open P&L. By the time price came back to
            # the missed target level, the open P&L had already given
            # most of it back. Force-closing when target should have
            # fired locks in the strategy's intended +$48 outcome.
            if self._broker_side == "LONG":
                stop_crossed   = snap.price <= self._broker_stop_px
                target_crossed = snap.price >= self._broker_target_px
            else:
                stop_crossed   = snap.price >= self._broker_stop_px
                target_crossed = snap.price <= self._broker_target_px
            crossed = stop_crossed or target_crossed
            if crossed:
                which = "STOP" if stop_crossed else "TARGET"
                level = (self._broker_stop_px if stop_crossed
                         else self._broker_target_px)
                logger.error(
                    f"[traderspost PANIC CLOSE/{which}] live price "
                    f"{snap.price:.2f} crossed broker-anchored {which} "
                    f"{level:.2f} -- broker bracket didn't fire. "
                    f"Force-flattening.")
                # Panic-close gated by _open_trade_ref (not SHADOW_MODE):
                # if we forwarded the open, we MUST clean up the broker
                # position, even if SHADOW was toggled mid-trade.
                # _open_trade_ref None means the broker never got the
                # open, so no position to flatten.
                if (self._open_trade_ref is not None
                        and self.traderspost is not None
                        and self.state.active_trade):
                    at = self.state.active_trade
                    try:
                        self.traderspost.submit_close(
                            side=at.side, qty=at.n_mnq,
                            reason=f"panic_{which.lower()}_missed",
                            setup_id=self._open_trade_ref,
                        )
                        self._panic_closed_ref = self._open_trade_ref
                    except Exception as te:
                        logger.warning(
                            f"traderspost panic-close failed: {te!r}")

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
            tag = "SHADOW" if SHADOW_MODE else "LIVE"
            logger.info(f"[{tag} OPEN] {trade.side} {trade.n_mnq} MNQ "
                        f"@ {trade.entry_px:.2f}  stop={trade.stop_px:.2f} "
                        f"tgt={trade.target_px:.2f}")
            # Forward to TradersPost as a bracketed limit order
            # (entry LIMIT + stop + take-profit). The broker manages the
            # bracket; we also send an explicit "exit" on _on_trade_close
            # as a reconciliation safety net. TradersPost dry-run mode
            # (default) just logs the JSON without POSTing.
            #
            # SHADOW_MODE gate: when SHADOW_MODE is on (BOT_SHADOW_MODE=1,
            # default), DO NOT send to the broker. The module docstring
            # says "Logs decisions but does NOT send orders" -- without
            # this check the bot was forwarding live orders despite the
            # dashboard's SHADOW badge, producing real broker losses
            # while the paper account showed clean strategy outcomes.
            # Caller must explicitly set BOT_SHADOW_MODE=0 to enable
            # real broker forwarding.
            if SHADOW_MODE:
                logger.info(f"[SHADOW] not forwarding to broker: "
                            f"{trade.side} {trade.n_mnq} @ "
                            f"{trade.entry_px:.2f}")
            elif self.traderspost is not None:
                try:
                    op = self.account.state.open_position
                    db_id = getattr(op, "db_id", None) if op else None
                    setup_ref = (f"acct{self.account_id}_"
                                 f"{db_id or 'noid'}_"
                                 f"{int(now.timestamp())}")
                    # Kill-switch: never forward bracket prices that
                    # diverge from live market by >50pts. This catches
                    # the case where the bot's bar pipeline silently
                    # falls back to research/data_loader._synthetic() --
                    # a random walk starting at $21,000 -- and computes
                    # setups at prices that have no relation to reality.
                    # When that happens, TradersPost auto-converts our
                    # unreachable limit into a market entry that fills
                    # at real price, but the bracket attaches at the
                    # hallucinated stop level (e.g. 1300pts away), so
                    # the position is effectively naked.
                    # PriceMonitor's _CHAIN is Polygon-only now, so any
                    # non-None snapshot is real-time. Skip trade if no
                    # snap (Polygon outage -> bot shouldn't trade).
                    live_snap = self.monitor.latest()
                    if live_snap is None:
                        logger.warning(
                            "[traderspost SKIP] no live price (Polygon "
                            f"outage?) -- refusing to send bracket "
                            f"entry={trade.entry_px:.2f}")
                        return
                    divergence = abs(trade.entry_px - live_snap.price)
                    if divergence > 10.0:
                        logger.error(
                            f"[traderspost SKIP] bracket prices diverge "
                            f"from live market by {divergence:.1f}pts "
                            f"(entry={trade.entry_px:.2f} vs "
                            f"live={live_snap.price:.2f}). TradersPost "
                            f"would auto-convert the unreachable limit "
                            f"to MARKET and anchor the bracket to the "
                            f"stale strategy price -- effectively naked. "
                            f"Not forwarding to broker.")
                        return
                    # Re-anchor brackets to LIVE tick price.
                    # ----------------------------------------
                    # The strategy detects the setup on the latest CLOSED
                    # 1-min bar (up to 60s stale by design, for backtest
                    # parity). But sending those stale absolute prices to
                    # the broker is what's been producing the +/-$100s of
                    # P&L the user sees: TradersPost auto-converts the
                    # unreachable limit to a market fill at the REAL
                    # current price, while the bracket anchors to the
                    # stale strategy price, leaving stop/target 20-40pt
                    # off from real fill.
                    #
                    # Mix the two: keep the strategy's stop/target
                    # DISTANCES (its edge), but anchor them to the live
                    # PriceMonitor price (1-4s fresh from Polygon). Now
                    # the bracket lands within ~1pt of real fill instead
                    # of 20-40pt off. Worst case slippage is the gap
                    # between when we read monitor.latest() here and when
                    # Tradovate fills the entry -- typically <2pt.
                    live_anchor = live_snap.price
                    stop_dist = abs(trade.entry_px - trade.stop_px)
                    target_dist = abs(trade.target_px - trade.entry_px)
                    if trade.side == "LONG":
                        anchored_stop = live_anchor - stop_dist
                        anchored_target = live_anchor + target_dist
                    else:
                        anchored_stop = live_anchor + stop_dist
                        anchored_target = live_anchor - target_dist
                    logger.info(
                        f"[traderspost ANCHOR] strategy {trade.entry_px:.2f}"
                        f"/{trade.stop_px:.2f}/{trade.target_px:.2f} -> "
                        f"live {live_anchor:.2f}"
                        f"/{anchored_stop:.2f}/{anchored_target:.2f} "
                        f"(delta {live_anchor - trade.entry_px:+.2f}pt)")
                    self.traderspost.submit_open(
                        side=trade.side, qty=trade.n_mnq,
                        entry_price=live_anchor,
                        stop_price=anchored_stop,
                        target_price=anchored_target,
                        setup_id=setup_ref,
                    )
                    # Stash the broker-anchored stop so the panic-close
                    # check uses the SAME level the broker bracket is at,
                    # not the stale strategy stop_px.
                    self._broker_stop_px = anchored_stop
                    self._broker_target_px = anchored_target
                    self._broker_side = trade.side
                    self._open_trade_ref = setup_ref
                except Exception as te:
                    logger.warning(f"traderspost submit_open failed: {te!r}")
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
            # Forward exit to TradersPost. The bracket order (stop+target)
            # placed on the open should have already closed the position
            # when it triggered, so this "exit/flat" call is normally a
            # no-op on TradersPost's side. It exists as a reconciliation
            # safety net for non-bracket exits (timeout, manual flatten,
            # auto-DLL). action="exit"+sentiment="flat" is idempotent on
            # TradersPost's side so duplicate sends are harmless.
            #
            # Gate by _open_trade_ref (NOT by SHADOW_MODE): if we
            # successfully forwarded the open, we MUST forward the
            # close to avoid orphan positions. Toggling SHADOW_MODE
            # mid-trade or having the open fire before SHADOW was set
            # would strand the broker position otherwise. If we never
            # forwarded the open (_open_trade_ref is None because
            # SHADOW gated it or the kill-switch skipped), there's no
            # broker position to close so we skip.
            if self._open_trade_ref is None:
                pass  # broker never got the open; nothing to close
            elif self.traderspost is not None:
                try:
                    self.traderspost.submit_close(
                        side=record.get("side", "LONG"),
                        qty=record.get("n_mnq", 1),
                        reason=record.get("exit_reason", "manual"),
                        setup_id=self._open_trade_ref,
                    )
                except Exception as te:
                    logger.warning(f"traderspost submit_close failed: {te!r}")
            self._open_trade_ref = None
            self._panic_closed_ref = None
            self._broker_stop_px = None
            self._broker_target_px = None
            self._broker_side = None
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
                # Source of the displayed price -- "polygon" is real-time;
                # anything else means we're on a delayed fallback (CNBC =
                # 15min, yfinance = 1-15min). When user sees the price
                # flicker between two values, this field tells them which
                # source it came from each tick. The dashboard can render
                # a "STALE" badge based on this.
                "price_source": latest.ts and self.monitor.last_source or None,
                # WS push and REST snapshot are both Polygon-only paths;
                # either qualifies as real-time. Anything else (none,
                # fallback name) is not.
                "price_realtime": self.monitor.last_source in
                                   ("polygon_ws", "polygon"),
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

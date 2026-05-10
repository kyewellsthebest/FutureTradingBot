"""
v11 Bot Runtime — lean replacement for bot.main.

Runs ONLY v11 NQ-ES stat-arb strategies. No VPIN, regime, ML, alt-data, kill
zones, cooldown filters. Only the rules I actually backtested:

  * 5-min bar driven (60s heartbeat, but acts on bar close)
  * NQ-ES return divergence Z-score (windows 10–120)
  * NY-time context filter (e.g. 14:30–15:00 ET)
  * Stop = N*ATR, Target = M*ATR
  * Entry slippage: 2pt (fill at next-bar open + slip)
  * Lucid risk: trail floor, daily loss limit, post-loss cooldown
  * Adaptive sizing: scales down as buffer-to-trail shrinks (matches
    monte_carlo_v11 sim)

Spawn:
    python -m bot.v11_main
"""
from __future__ import annotations

import json
import logging
import signal as signal_mod
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from bot import persistence
from bot.lucid_account import LucidAccount
from bot.price_monitor import PriceMonitor
from research.clock_sync import sync_clock, real_utc_now
from research.data_loader import DATA_DIR, download_nq, download_es, download_symbol
from research.lucid_guard import MAX_MNQ as LUCID_MAX_MNQ
from research.signal_filters import DOLLARS_PER_POINT, NY_TZ
from research.v11_engine import V11Engine

logger = logging.getLogger("bot_v11")

CYCLE_FLAT_SECONDS = 60    # tick rate when no position open
CYCLE_TRADE_SECONDS = 5    # tick rate when managing an open position (12x faster)
CYCLE_SECONDS = CYCLE_FLAT_SECONDS   # backward-compat alias
DASHBOARD_PATH = DATA_DIR / "dashboard_data.json"
LIVE_BARS_PATH = DATA_DIR / "live_bars.json"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "bot_v11.log"

# v11 default position size (matches Monte Carlo "best EV" config)
BASE_SIZE = int(__import__("os").environ.get("V11_BASE_SIZE", "25"))
COOLDOWN_BARS = 5         # 5-min bars to wait after a loss

# Per-trade max loss cap. Lucid 50K has $2K trailing drawdown; capping
# every trade at $2,000 worst-case stop guarantees no SINGLE trade can
# blow the entire account, while leaving enough size to be profitable.
# (The $1,000 cap previously tested was too restrictive — gutted EV.)
# Configurable via V11_MAX_LOSS env var.
MAX_LOSS_PER_TRADE = float(__import__("os").environ.get("V11_MAX_LOSS", "2000"))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); root.addHandler(sh)
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8"); fh.setFormatter(fmt); root.addHandler(fh)


# ---------------------------------------------------------------------------
# Live-bar merge (CNBC poller)
# ---------------------------------------------------------------------------
def _merge_live_bars(intraday: pd.DataFrame) -> pd.DataFrame:
    if not LIVE_BARS_PATH.exists():
        return intraday
    try:
        bars = json.loads(LIVE_BARS_PATH.read_text())
    except Exception:
        return intraday
    rows = []
    for b in bars:
        try:
            ts = pd.Timestamp(b["ts"]).tz_convert("UTC") if pd.Timestamp(b["ts"]).tzinfo else pd.Timestamp(b["ts"], tz="UTC")
            rows.append((ts, float(b["open"]), float(b["high"]), float(b["low"]),
                         float(b["close"]), float(b.get("volume", 0))))
        except Exception:
            continue
    if not rows:
        return intraday
    live = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts").sort_index()
    out = pd.concat([intraday, live])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


# ---------------------------------------------------------------------------
# Adaptive sizing (must mirror monte_carlo_v11.adaptive_qty_factor)
# ---------------------------------------------------------------------------
def adaptive_qty(base_size: int, balance: float, trail: float,
                   account_initial: float = 50000.0) -> int:
    """Scale qty by buffer-to-trail. Mirrors the Monte-Carlo sizing exactly."""
    buffer = balance - trail
    scale = account_initial / 50000.0
    buf_norm = buffer / scale
    if buf_norm < 200:    return 0
    if buf_norm < 500:    factor = 0.20
    elif buf_norm < 1000: factor = 0.40
    elif buf_norm < 2000: factor = 0.60
    elif buf_norm < 4000: factor = 0.85
    else:                  factor = 1.0
    return max(1, int(base_size * factor)) if factor > 0 else 0


def cap_qty_by_max_loss(qty: int, stop_pts: float,
                          max_loss_dollars: float = MAX_LOSS_PER_TRADE) -> int:
    """Reduce qty so worst-case stop loss is <= max_loss_dollars.

    Per-MNQ loss = (stop_pts + 1pt commission/slippage cushion) * $2/pt.
    Wider stop = smaller position, narrower stop = larger position.
    Risk-per-trade is normalized to a fixed $ amount regardless of ATR.
    """
    if stop_pts <= 0 or max_loss_dollars <= 0:
        return qty
    per_contract_loss = (stop_pts + 1.0) * 2.0   # 1pt cushion for slip+commission
    max_qty = int(max_loss_dollars / per_contract_loss)
    return min(qty, max(1, max_qty))


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
class V11Runtime:
    def __init__(self) -> None:
        self.account = LucidAccount()
        self.engine = V11Engine()
        self.monitor = PriceMonitor()
        self.cycle = 0
        self.last_bar_ts: Optional[pd.Timestamp] = None
        self.last_error: Optional[str] = None
        self._running = True
        self._last_loss_bar_ts: Optional[pd.Timestamp] = None
        # Diagnostic counters surfaced in the dashboard
        self.bars_processed = 0
        self.signals_fired = 0
        self.signals_blocked = 0
        # Recent fires for the Brain tab (rolling)
        self.recent_fires: deque = deque(maxlen=50)
        # 1-min bar cache for tight stop/target precision when in-position.
        # Refreshed at most every 30s — keeps the fast 5s tick light.
        self._last_1m_fetch: float = 0.0
        self._cached_1m_high: Optional[float] = None
        self._cached_1m_low:  Optional[float] = None

    def stop(self, *_):
        logger.info("stop received")
        self._running = False

    # ---- main loop ---------------------------------------------------------
    def run(self) -> int:
        _setup_logging()
        sync_clock()
        logger.info(f"[v11] {len(self.engine.strategies)} strategies loaded; "
                      f"base size={BASE_SIZE} MNQ")
        self.monitor.start()
        signal_mod.signal(signal_mod.SIGINT, self.stop)
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
            # Variable tick rate: 5s when in position, 60s when flat.
            # Tighter stop/target tracking — a spike that pierces the stop
            # within 5s is caught instead of slipping through a 60s window.
            in_trade = self.account.state.open_position is not None
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

    # ---- single tick -------------------------------------------------------
    def _tick(self) -> None:
        self.cycle += 1
        now = real_utc_now()
        snap = self.monitor.snapshot_and_reset()
        in_trade = self.account.state.open_position is not None

        # When flat: refresh 5-min bars + engine state (drives Brain tab).
        # When in trade: skip the heavy data refresh — we tick every 5s
        # for stop/target precision, and the 5-min Z-scores don't change
        # within a 5s window.
        if not in_trade:
            nq = download_nq("5min")
            es = download_es("5min")
            if nq is None or nq.empty or es is None or es.empty:
                self.last_error = "no bars"
                return
            nq = _merge_live_bars(nq)
            if nq.index.tz is None:
                nq.index = nq.index.tz_localize("UTC")
            if es.index.tz is None:
                es.index = es.index.tz_localize("UTC")
            # v13 needs VIX and RTY too; failures don't block (the engine
            # gracefully skips families with no data).
            rty = vix = None
            try:
                rty = download_symbol("RTY=F", "5min")
                if rty is not None and rty.index.tz is None:
                    rty.index = rty.index.tz_localize("UTC")
            except Exception as e:
                logger.debug(f"RTY fetch failed: {e}")
            try:
                vix = download_symbol("^VIX", "5min")
                if vix is not None and vix.index.tz is None:
                    vix.index = vix.index.tz_localize("UTC")
            except Exception as e:
                logger.debug(f"VIX fetch failed: {e}")
            self.engine.update_state(nq, es, rty_5m=rty, vix_5m=vix)

        # Step 1: handle exits first (need a live price).
        # Use the WIDEST recent high/low to be conservative — combine
        # the price-monitor's accumulated high/low (last few seconds of
        # CNBC polls) with the latest 1-min bar's high/low (yfinance,
        # completed bar). Whichever is more pessimistic for the open
        # side gets used. yfinance is fetched at most once per 30s
        # (cached) so the 5s tick stays light.
        if in_trade and snap is not None:
            tick_high = snap.high
            tick_low  = snap.low
            try:
                tnow = time.time()
                if tnow - self._last_1m_fetch > 30:
                    import yfinance as yf
                    latest_1m = yf.download("NQ=F", period="1d", interval="1m",
                                              auto_adjust=False, progress=False, threads=False)
                    if latest_1m is not None and not latest_1m.empty:
                        if hasattr(latest_1m.columns, 'levels'):
                            latest_1m.columns = [c[0] if isinstance(c, tuple) else c for c in latest_1m.columns]
                        latest_1m = latest_1m.rename(columns={c: str(c).lower() for c in latest_1m.columns})
                        recent = latest_1m.tail(3)
                        if len(recent):
                            self._cached_1m_high = float(recent["high"].max())
                            self._cached_1m_low  = float(recent["low"].min())
                            self._last_1m_fetch = tnow
                if self._cached_1m_high is not None:
                    tick_high = max(tick_high, self._cached_1m_high)
                    tick_low  = min(tick_low,  self._cached_1m_low)
            except Exception as e:
                logger.debug(f"1m bar consultation failed: {e}")

            evt = self.account.check_exit(tick_high, tick_low, snap.price, now=now)
            if evt:
                pnl = evt.get("pnl", 0.0)
                if pnl < 0:
                    self._last_loss_bar_ts = pd.Timestamp(now)
                # Reset 1m cache so the next entry starts fresh
                self._cached_1m_high = None
                self._cached_1m_low  = None
                persistence.push_signal_event({"type": "EXIT", "ts": now.isoformat(), **evt})
            return

        # If we don't have a current price snap, dashboard still updates but
        # we can't enter (need live price for entry).
        if snap is None:
            self.last_error = "no price (state refreshed)"
            return

        # Position open but no exit fired: nothing else to do this tick.
        if self.account.state.open_position is not None:
            return

        latest_ts = nq.index[-1]
        bar_changed = self.last_bar_ts != latest_ts
        if not bar_changed:
            return  # don't double-fire on the same bar
        self.last_bar_ts = latest_ts
        self.bars_processed += 1

        # Post-loss cooldown
        if self._last_loss_bar_ts is not None:
            cooldown_until = self._last_loss_bar_ts + pd.Timedelta(minutes=COOLDOWN_BARS * 5)
            if pd.Timestamp(now) < cooldown_until:
                return

        cand = self.engine.evaluate(nq, es, rty_5m=rty, vix_5m=vix)
        if cand is None:
            self.last_error = None
            return

        # Adaptive sizing
        lucid = self.account.lucid_snapshot()
        balance = float(lucid.get("balance", 50000.0))
        trail = float(lucid.get("trail_floor", 48000.0))
        starting = float(lucid.get("starting_balance", 50000.0))
        qty = adaptive_qty(BASE_SIZE, balance, trail, account_initial=starting)
        if qty == 0:
            self.signals_blocked += 1
            persistence.push_signal_event({
                "type": "BLOCKED", "ts": now.isoformat(),
                "signal": cand.signal_name, "side": cand.side,
                "rule": "buffer_too_thin",
                "reason": f"buffer ${balance - trail:.0f} < $200",
            })
            return
        qty = min(qty, LUCID_MAX_MNQ)

        # Cap qty so worst-case stop loss <= MAX_LOSS_PER_TRADE.
        # This survives the EOD-trail rule: $1K stop x 2 trades = $2K
        # drawdown, exactly the trail allowance from a fresh start.
        stop_pts = abs(cand.entry_px - cand.stop_px)
        qty_before_cap = qty
        qty = cap_qty_by_max_loss(qty, stop_pts)
        if qty < qty_before_cap:
            logger.info(f"[risk-cap] {cand.signal_name}: stop {stop_pts:.1f}pt → "
                          f"qty reduced {qty_before_cap}→{qty} MNQ to keep loss "
                          f"≤ ${MAX_LOSS_PER_TRADE:.0f} (worst-case "
                          f"${(stop_pts + 1) * 2.0 * qty:.0f})")

        # Lucid pre-trade compliance check
        tgt_pts = abs(cand.target_px - cand.entry_px)
        stop_pnl = -stop_pts * DOLLARS_PER_POINT * (qty / 30.0)
        tgt_pnl = tgt_pts * DOLLARS_PER_POINT * (qty / 30.0)
        decision = self.account.can_enter(side=cand.side, qty=qty,
                                              target_pnl=tgt_pnl, stop_pnl=stop_pnl,
                                              now=now)
        if not decision.allowed:
            self.signals_blocked += 1
            logger.warning(f"[lucid_guard] BLOCK {cand.signal_name} {cand.side} "
                              f"x{qty}: {decision.reason} ({decision.rule})")
            persistence.push_signal_event({
                "type": "BLOCKED", "ts": now.isoformat(),
                "signal": cand.signal_name, "side": cand.side,
                "rule": decision.rule, "reason": decision.reason,
            })
            return

        # Execute the trade
        self.account.enter(
            signal_name=cand.signal_name, side=cand.side,
            entry_px_raw=float(cand.entry_px),
            stop_px=float(cand.stop_px), target_px=float(cand.target_px),
            qty=qty,
            ml_decision=cand.ml_decision, ml_confidence=float(cand.ml_confidence),
            vol_regime=cand.vol_regime, daily_bias=cand.daily_bias,
            rr=float(cand.rr), now=now,
        )
        self.signals_fired += 1
        fire_record = {
            "ts": now.isoformat(),
            "strategy": cand.signal_name,
            "side": cand.side,
            "qty": qty,
            "entry": cand.entry_px,
            "stop": cand.stop_px,
            "target": cand.target_px,
            "z_value": cand.stat_arb_zscore,
            "trace": cand.filter_trace,
        }
        self.recent_fires.append(fire_record)
        persistence.push_signal_event({"type": "ENTRY", **fire_record})
        self.last_error = None

    # ---- dashboard publishing ---------------------------------------------
    def _publish_dashboard(self) -> None:
        s = self.account.state
        snap = self.monitor.latest()
        now = pd.Timestamp.utcnow().tz_localize("UTC") if pd.Timestamp.utcnow().tzinfo is None else pd.Timestamp.utcnow()
        in_trade = s.open_position is not None
        recent = persistence.load_trades(limit=20)
        wins_today = sum(1 for t in recent if (t.get("pnl") or 0) > 0)
        losses_today = sum(1 for t in recent if (t.get("pnl") or 0) < 0)

        op_dump = s.open_position.__dict__ if s.open_position is not None else None

        # v11-specific brain payload
        engine_summary = self.engine.summary()
        z_scores = {str(k): (None if pd.isna(v) else round(float(v), 3))
                      for k, v in self.engine.current_z_scores().items()}
        closest = self.engine.closest_to_trigger(top_n=15)
        closest = [{
            "name": r["name"], "side": r["side"],
            "z_window": r["z_window"], "z_threshold": r["z_threshold"],
            "z_current": None if pd.isna(r["z_current"]) else round(float(r["z_current"]), 3),
            "distance": None if pd.isna(r["distance"]) else round(float(r["distance"]), 3),
            "fired": bool(r.get("fired", False)),
            "z_crossed": bool(r.get("z_crossed", False)),
            "in_time": bool(r.get("in_time", True)),
            "time_ctx": r["time_ctx"],
        } for r in closest]

        # NY time bucket of last bar
        bar_ts = self.engine.state.last_bar_ts
        ny_bucket = None
        if bar_ts is not None:
            ny = bar_ts.tz_convert(NY_TZ)
            ny_bucket = ny.strftime("%H:%M ET")

        state = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "cycle": self.cycle,
            "bot_version": "v11",
            "price": snap.price if snap else None,
            "price_ts": snap.ts.isoformat() if snap else None,
            "monitor_error": self.last_error,
            "account": {
                "balance": s.balance,
                "starting_balance": s.starting_balance,
                "realized_pnl": s.realized_pnl,
                "total_trades": s.total_trades,
                "wins": s.wins, "losses": s.losses,
                "win_rate": (s.wins / s.total_trades) if s.total_trades else 0.0,
                "trades_today": s.trades_today,
                "peak_balance": s.peak_balance,
                "max_drawdown": s.max_drawdown,
                "last_trade_close_time": s.last_trade_close_time,
                "last_trade_was_winner": s.last_trade_was_winner,
                "open_position": op_dump,
            },
            "today": {
                "trades": wins_today + losses_today,
                "wins": wins_today, "losses": losses_today,
                "win_rate": (wins_today / (wins_today + losses_today))
                              if (wins_today + losses_today) else 0.0,
                "net_pnl": sum((t.get("pnl") or 0.0) for t in recent),
            },
            "recent_trades": recent[-10:],
            "starting_balance": s.starting_balance,
            # MNQ = $2/pt per contract. (Legacy DOLLARS_PER_POINT=60 was
            # a 30x-scaled value from the old V3 sizing — never display it.)
            "dollars_per_point": 2.0,
            "recent_signal_events": persistence.load_signal_events(limit=20),
            "v11": {
                "summary": engine_summary,
                "z_scores": z_scores,
                "ny_bucket": ny_bucket,
                "last_bar_ts": bar_ts.isoformat() if bar_ts is not None else None,
                "atr": None if pd.isna(self.engine.state.atr_current) else round(float(self.engine.state.atr_current), 2),
                "closest_to_trigger": closest,
                "bars_processed": self.bars_processed,
                "signals_fired": self.signals_fired,
                "signals_blocked": self.signals_blocked,
                "recent_fires": list(self.recent_fires),
                "base_size": BASE_SIZE,
            },
            "lucid_account": self.account.lucid_snapshot(),
            "funded_accounts": self.account.ledger.snapshot(),
        }
        persistence.save_dashboard(state)


def main() -> int:
    return V11Runtime().run()


if __name__ == "__main__":
    raise SystemExit(main())

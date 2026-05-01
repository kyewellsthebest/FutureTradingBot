"""
Trading bot — 60-second heartbeat (per spec).

Boot sequence: clock sync → start price monitor → start dashboard thread →
install SIGINT/SIGTERM → enter loop. Re-syncs the clock every 60 cycles
(~1 hour) so a wrong system clock doesn't drift the bot.

Each tick:
  1. Read PriceMonitor.snapshot_and_reset() → {price, high, low, ts, poll_count}
  2. If a position is open → account.check_exit(high, low, price) (price-touch logic)
  3. If flat → download 5min/daily, merge live_bars.json into 5-min frame,
     refresh microstructure (VPIN/adverse/regime/GEX/macro), bar-change guard,
     engine.evaluate(intraday, daily, prior_trades) → TradeCandidate or None
     If candidate, account.enter(...)
  4. Write data/dashboard_data.json
  5. Sleep until next 60s tick.

Run with:  python -m bot.main
"""
from __future__ import annotations

import json
import logging
import signal as signal_mod
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from bot import persistence
from bot.lucid_account import LucidAccount
from bot.price_monitor import PriceMonitor
from research.clock_sync import sync_clock, real_utc_now
from research.data_loader import DATA_DIR, download_nq
from research.lucid_guard import DLL as LUCID_DLL, MAX_MNQ as LUCID_MAX_MNQ
from research.signal_engine import SignalEngine
from research.signal_filters import (
    DOLLARS_PER_POINT,
    KILL_ZONES,
    NY_TZ,
    TradeRef,
    kill_zone_filter,
)
from research.stat_arb import compute_or_cache as compute_stat_arb

logger = logging.getLogger("bot")

CYCLE_SECONDS = 60
DASHBOARD_PATH = DATA_DIR / "dashboard_data.json"
LIVE_BARS_PATH = DATA_DIR / "live_bars.json"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "bot.log"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); root.addHandler(sh)
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8"); fh.setFormatter(fmt); root.addHandler(fh)


def _merge_live_bars(intraday: pd.DataFrame) -> pd.DataFrame:
    """Glue the dashboard's live CNBC ledger onto the head of yfinance's 5-min frame.

    yfinance's NQ=F feed reliably stalls outside RTH; without this merge the
    engine would evaluate stale bars from yesterday.
    """
    if not LIVE_BARS_PATH.exists():
        return intraday
    try:
        bars = json.loads(LIVE_BARS_PATH.read_text())
    except Exception:
        return intraday
    if not bars:
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


def _readiness_from_microstructure(ms: dict, in_trade: bool, kz_name: str,
                                    cand: Optional[object]) -> dict:
    """Build the dashboard's trade-readiness card."""
    checks: list[tuple[str, bool]] = []
    vpin = ms.get("vpin")
    if vpin:
        checks.append(("VPIN", vpin.get("regime") not in ("HIGH", "EXTREME")
                       and not vpin.get("crash_warning")))
    adverse = ms.get("adverse_selection")
    if adverse:
        checks.append(("Adverse Selection", adverse.get("regime") not in ("HIGH", "EXTREME")))
    if ms.get("regime"):
        checks.append(("Regime", True))
    if ms.get("gex"):
        checks.append(("GEX", True))
    if ms.get("macro"):
        checks.append(("Macro", True))
    checks.append(("Kill Zone", bool(kz_name)))
    checks.append(("Signal Firing", in_trade or cand is not None))
    passing = [n for n, ok in checks if ok]
    blocking = [n for n, ok in checks if not ok]
    return {
        "pct": round(len(passing) / max(len(checks), 1), 3),
        "passing": passing, "blocking": blocking,
        "in_trade": in_trade, "total_checks": len(checks),
    }


def _next_kill_zone(now: pd.Timestamp) -> str:
    ny = now.tz_convert(NY_TZ)
    today_dt = ny.normalize()
    for name, start, end in KILL_ZONES:
        cand = today_dt + pd.Timedelta(hours=start.hour, minutes=start.minute)
        if cand > ny:
            return f"{name} @ {start.strftime('%H:%M')} EST"
    name, start, _ = KILL_ZONES[0]
    return f"{name} @ {start.strftime('%H:%M')} EST (tomorrow)"


def _active_kill_zone(now: pd.Timestamp) -> str:
    ok, name = kill_zone_filter("__check__", now)
    return name if ok else ""


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

class Runtime:
    def __init__(self) -> None:
        self.account = LucidAccount()
        self.engine = SignalEngine()
        self.monitor = PriceMonitor()
        self.cycle = 0
        self.last_bar_ts: pd.Timestamp | None = None
        self.last_error: str | None = None
        self._running = True
        self._stat_arb = None

    def stop(self, *_):
        logger.info("stop signal received")
        self._running = False

    # ---- main loop ------------------------------------------------------

    def run(self) -> int:
        _setup_logging()
        sync_clock()
        from research.filter_config import describe as describe_filters
        logger.info(f"filter config: {describe_filters()}")
        logger.info(f"clock synced; whitelist={sorted(self.engine.whitelist)}")
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
            self._sleep(CYCLE_SECONDS)
            if self.cycle % 60 == 0:
                sync_clock()
        self.monitor.stop()
        return 0

    def _sleep(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                return
            time.sleep(1)

    # ---- single tick ----------------------------------------------------

    def _tick(self) -> None:
        self.cycle += 1
        snap = self.monitor.snapshot_and_reset()
        if snap is None:
            self.last_error = "no price"
            return
        now = real_utc_now()

        # Step 2: exits first
        if self.account.state.open_position is not None:
            evt = self.account.check_exit(snap.high, snap.low, snap.price, now=now)
            if evt:
                persistence.push_signal_event({"type": "EXIT", "ts": now.isoformat(), **evt})
            return  # stop here for this cycle

        # Step 3: flat → evaluate
        intraday = download_nq("5min")
        daily = download_nq("daily")
        if intraday is None or intraday.empty or daily is None or daily.empty:
            self.last_error = "no bars"
            return
        intraday = _merge_live_bars(intraday)

        # Bar-change guard: skip if latest bar timestamp matches previous tick
        latest_ts = intraday.index[-1]
        if self.last_bar_ts == latest_ts:
            # Still refresh microstructure so dashboard meters tick
            self.engine.refresh_microstructure(intraday, daily)
            self._stat_arb = compute_stat_arb(daily, daily)  # ES not wired; advisory placeholder
            return
        self.last_bar_ts = latest_ts

        self.engine.refresh_microstructure(intraday, daily)
        self._stat_arb = compute_stat_arb(daily, daily)

        # Build prior-trades from SQLite for the cooldown filter
        closed = persistence.load_trades(limit=50, only_closed=True)
        prior_trades = []
        for t in closed:
            try:
                et = pd.Timestamp(t["entry_time"], tz="UTC") if t.get("entry_time") else None
                xt = pd.Timestamp(t["exit_time"], tz="UTC") if t.get("exit_time") else None
                prior_trades.append(TradeRef(
                    entry_time=et, exit_time=xt,
                    side=t.get("side", ""), pnl=float(t.get("pnl") or 0.0),
                    signal_name=t.get("signal_name", ""),
                ))
            except Exception:
                continue

        cand = self.engine.evaluate(intraday, daily, prior_trades=prior_trades)
        if cand is not None:
            # Lucid pre-trade compliance guard — clamp size to 40 MNQ first,
            # then ask the runtime guard if the trade is allowed.
            qty = min(int(cand.contracts), LUCID_MAX_MNQ)
            stop_pts = abs(float(cand.entry_px) - float(cand.stop_px))
            tgt_pts  = abs(float(cand.target_px) - float(cand.entry_px))
            stop_pnl = -stop_pts * DOLLARS_PER_POINT * (qty / 30.0)
            tgt_pnl  =  tgt_pts  * DOLLARS_PER_POINT * (qty / 30.0)
            decision = self.account.can_enter(side=cand.side, qty=qty,
                                                target_pnl=tgt_pnl,
                                                stop_pnl=stop_pnl, now=now)
            if not decision.allowed:
                logger.warning(f"[lucid_guard] BLOCK {cand.signal_name} {cand.side} "
                               f"x{qty}: {decision.reason} ({decision.rule})")
                persistence.push_signal_event({
                    "type": "BLOCKED", "ts": now.isoformat(),
                    "signal": cand.signal_name, "side": cand.side,
                    "rule": decision.rule, "reason": decision.reason,
                })
            else:
                self.account.enter(
                    signal_name=cand.signal_name, side=cand.side,
                    entry_px_raw=float(cand.entry_px),
                    stop_px=float(cand.stop_px), target_px=float(cand.target_px),
                    qty=qty,
                    ml_decision=cand.ml_decision, ml_confidence=float(cand.ml_confidence),
                    vol_regime=cand.vol_regime, daily_bias=cand.daily_bias,
                    rr=float(cand.rr), now=now,
                )
                persistence.push_signal_event({
                    "type": "ENTRY", "ts": now.isoformat(),
                    "signal": cand.signal_name, "side": cand.side,
                    "entry_px": cand.entry_px, "contracts": qty,
                    "ml": cand.ml_decision, "trace": cand.filter_trace,
                })
        self.last_error = None

    # ---- dashboard ------------------------------------------------------

    def _publish_dashboard(self) -> None:
        s = self.account.state
        snap = self.monitor.latest()
        ms = self.engine.snapshot_microstructure()
        now = pd.Timestamp.utcnow().tz_localize("UTC") if pd.Timestamp.utcnow().tzinfo is None \
              else pd.Timestamp.utcnow()
        kz = _active_kill_zone(now)
        in_trade = s.open_position is not None
        readiness = _readiness_from_microstructure(ms, in_trade, kz, None)
        recent = persistence.load_trades(limit=20)
        wins_today = sum(1 for t in recent if (t.get("pnl") or 0) > 0)
        losses_today = sum(1 for t in recent if (t.get("pnl") or 0) < 0)
        sa = self._stat_arb
        sa_block = {
            "enabled": True, "available": False, "signal": "NEUTRAL",
            "zscore": 0.0, "beta": 41.0, "coint_pvalue": 1.0,
            "is_cointegrated": False, "last_calibrated": "",
        }
        if sa is not None:
            sa_block.update({
                "available": sa.available, "signal": sa.signal,
                "zscore": sa.zscore, "beta": sa.beta,
                "coint_pvalue": sa.coint_pvalue,
                "is_cointegrated": sa.is_cointegrated,
                "last_calibrated": sa.last_calibrated,
            })

        op_dump = None
        if s.open_position is not None:
            op_dump = s.open_position.__dict__
        state = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "cycle": self.cycle,
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
            "whitelist": sorted(self.engine.whitelist),
            "filter_mode": __import__("research.filter_config", fromlist=["CONFIG"]).CONFIG.mode,
            "starting_balance": s.starting_balance,
            "dollars_per_point": DOLLARS_PER_POINT,
            "recent_signal_events": persistence.load_signal_events(limit=20),
            "microstructure": ms,
            "stat_arb": sa_block,
            "kill_zone": {
                "active": bool(kz), "name": kz or "",
                "next": _next_kill_zone(now),
            },
            "trade_readiness": readiness,
            # Lucid Trading $50K Pro Funded — live runtime account state
            "lucid_account": self.account.lucid_snapshot(),
            "funded_accounts": self.account.ledger.snapshot(),
        }
        persistence.save_dashboard(state)


def main() -> int:
    return Runtime().run()


if __name__ == "__main__":
    raise SystemExit(main())

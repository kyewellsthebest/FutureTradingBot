"""
Live (paper) trading loop.

Each cycle:
  1. Refresh intraday + daily bars via research.data_loader
  2. Update microstructure snapshots via SignalEngine.refresh_microstructure
  3. If a fresh bar is available, evaluate signals and try to open a trade
  4. Mark open position to market and check stop/target exits
  5. Write a fresh dashboard snapshot to data/dashboard_data.json

Run with:  python -m bot.main
"""
from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bot import persistence
from bot.portfolio_manager import PortfolioManager
from research.data_loader import download_nq, latest_price
from research.signal_engine import SignalEngine
from research.signal_filters import (
    DOLLARS_PER_POINT,
    active_kill_zone,
    next_kill_zone,
)

logger = logging.getLogger("bot")

POLL_SECONDS = 60
DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "data" / "dashboard_data.json"


class Runtime:
    def __init__(self):
        self.portfolio = PortfolioManager()
        self.engine = SignalEngine()
        self.cycle = 0
        self.last_bar_ts: pd.Timestamp | None = None
        self.last_error: str | None = None
        self._running = True

    def stop(self, *_):
        logger.info("[bot] stop signal received")
        self._running = False

    # ---- main loop ------------------------------------------------------

    def run(self) -> int:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
        )
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        logger.info("[bot] startup — whitelist=%s", sorted(self.engine.whitelist))
        while self._running:
            try:
                self._tick()
            except Exception as e:
                self.last_error = repr(e)
                logger.exception("[bot] tick failed: %s", e)
            self._publish_dashboard()
            for _ in range(POLL_SECONDS):
                if not self._running:
                    break
                time.sleep(1)
        return 0

    def _tick(self) -> None:
        self.cycle += 1
        intraday = download_nq("5min")
        daily = download_nq("daily")
        if intraday is None or intraday.empty:
            self.last_error = "no intraday data"
            return

        last_bar_ts = intraday.index[-1]
        last_bar = intraday.iloc[-1]
        last_px = float(last_bar["close"])
        now = datetime.now(timezone.utc)

        # 1. Always refresh microstructure so dashboard meters update
        self.engine.refresh_microstructure(intraday, daily)

        # 2. Check exits on any open position first
        exit_evt = self.portfolio.check_exits(
            last_px=last_px,
            last_high=float(last_bar["high"]),
            last_low=float(last_bar["low"]),
            last_time=now,
        )
        if exit_evt:
            persistence.push_signal_event({
                "type": "EXIT", "ts": now.isoformat(), "trade": exit_evt,
            })

        # 3. Evaluate signals only on a fresh bar and only when flat
        if self.last_bar_ts != last_bar_ts and self.portfolio.open_position is None:
            self.last_bar_ts = last_bar_ts
            cand = self.engine.evaluate(
                intraday, daily,
                prior_trades=self.portfolio.recent_trades,
            )
            if cand is not None:
                opened = self.portfolio.open_trade(
                    candidate=cand,
                    fill_time=now,
                    fill_px=cand.entry_px,
                    contracts=cand.contracts,
                )
                if opened:
                    persistence.push_signal_event({
                        "type": "ENTRY", "ts": now.isoformat(),
                        "signal": cand.signal_name, "side": cand.side,
                        "entry_px": cand.entry_px, "contracts": cand.contracts,
                        "ml": cand.ml_decision, "trace": cand.filter_trace,
                    })

        self.last_error = None

    # ---- dashboard publish ---------------------------------------------

    def _publish_dashboard(self) -> None:
        acct = self.portfolio.account
        last = latest_price("5min")
        last_px, last_ts = (None, None) if last is None else last
        ms = self.engine.snapshot_microstructure()
        kz = active_kill_zone(pd.Timestamp.now(tz="UTC"))
        recent = persistence.load_trades(limit=20)
        wins_today = sum(1 for t in recent if t.get("win"))
        losses_today = sum(1 for t in recent if not t.get("win"))
        total_checks = 7
        passing: list[str] = []
        blocking: list[str] = []
        if ms.get("vpin"):
            (passing if ms["vpin"]["regime"] != "EXTREME" else blocking).append("VPIN")
        if ms.get("adverse_selection"):
            (passing if not ms["adverse_selection"]["market_shutdown"] else blocking).append("Adverse Selection")
        if ms.get("regime"):
            passing.append("Regime")
        if ms.get("gex"):
            passing.append("GEX")
        if ms.get("macro"):
            passing.append("Macro")
        if kz:
            passing.append("Kill Zone")
        else:
            blocking.append("Kill Zone")
        in_trade = self.portfolio.open_position is not None
        if in_trade:
            passing.append("In Trade")
        else:
            blocking.append("Signal Firing")
        readiness = {
            "pct": round(len(passing) / total_checks, 3),
            "passing": passing, "blocking": blocking,
            "in_trade": in_trade, "total_checks": total_checks,
        }
        state = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "cycle": self.cycle,
            "price": last_px,
            "price_ts": last_ts.isoformat() if last_ts is not None else None,
            "monitor_error": self.last_error,
            "account": {
                "balance": acct.get("balance"),
                "starting_balance": acct.get("starting_balance"),
                "realized_pnl": acct.get("realized_pnl"),
                "total_trades": acct.get("total_trades"),
                "wins": acct.get("wins"),
                "losses": acct.get("losses"),
                "win_rate": (acct["wins"] / acct["total_trades"]) if acct.get("total_trades") else 0.0,
                "trades_today": acct.get("trades_today"),
                "peak_balance": acct.get("peak_balance"),
                "max_drawdown": acct.get("max_drawdown"),
                "last_trade_close_time": acct.get("last_trade_close_time"),
                "last_trade_was_winner": acct.get("last_trade_was_winner"),
                "open_position": acct.get("open_position"),
            },
            "today": {
                "trades": wins_today + losses_today,
                "wins": wins_today, "losses": losses_today,
                "win_rate": (wins_today / (wins_today + losses_today)) if (wins_today + losses_today) else 0.0,
                "net_pnl": sum(t.get("pnl_dollars", 0.0) for t in recent),
            },
            "recent_trades": recent[-10:],
            "whitelist": sorted(self.engine.whitelist),
            "starting_balance": acct.get("starting_balance"),
            "dollars_per_point": DOLLARS_PER_POINT,
            "recent_signal_events": persistence.load_signal_events(limit=20),
            "microstructure": ms,
            "kill_zone": {
                "active": bool(kz), "name": kz or "",
                "next": next_kill_zone(pd.Timestamp.now(tz="UTC")),
            },
            "trade_readiness": readiness,
        }
        persistence.save_dashboard(state)


def main() -> int:
    return Runtime().run()


if __name__ == "__main__":
    raise SystemExit(main())

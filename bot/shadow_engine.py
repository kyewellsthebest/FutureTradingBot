"""ShadowEngine: runs the engine.runtime.Runtime in parallel with the live
bot, on the same bars but with its own independent paper book. Logs every
decision and emits ClosedTrades to a JSON file for offline comparison.

ZERO INFLUENCE on live trading. The shadow's actions never touch the real
bot's state, the lucid account, the trade DB, or anything else. It's a
read-only observer that produces an artifact we can compare against the
live bot to confirm engine = bot before we migrate.

Lifecycle:
  ShadowEngine() created once per FibRuntime
  - .on_new_closed_bar(bar, history, now): called when a new 1-min bar closes
  - .snapshot(): returns dict of current shadow state for the dashboard
  - .persist(): writes the shadow's decisions + trades to JSON

Output path: data/account_<N>/shadow_engine.json (NY-day rotated).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("shadow_engine")


def _jsonable(obj):
    """Convert dataclasses / datetimes / enums / numpy to JSON-safe types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(x) for x in obj]
    return str(obj)


class ShadowEngine:
    """Wraps a Runtime; runs it on the same 1-min bars the live bot sees,
    persists everything for offline comparison.

    NEW (Phase 1-2 upgrade): the shadow engine ALSO consumes economic
    calendar + cross-market + session-structure context. Its risk engine
    has the real NewsBlackoutGate, MacroAlignmentSizerGate, and
    VolatilityAdaptiveSizerGate wired in, so its decisions reflect what
    a fully-context-aware bot would do. Compare to live's basic decisions
    to see which trades the engine would have skipped or downsized.
    """

    def __init__(self, account_id: str = "1", starting_balance: float = 50_000.0,
                 economic_calendar=None, cross_market_feed=None):
        # Lazy-import the engine so an import error in the engine package
        # never crashes the live bot.
        try:
            from engine.fills.sim import SimFillModel, SimFillParams
            from engine.market_context import build_market_context
            from engine.risk.engine import RiskEngine
            from engine.risk.gates import (
                AccountState, ActiveLockoutGate, CooldownGate,
                DailyLossLimitGate, MacroAlignmentSizerGate,
                MaxTradesPerDayGate, NewsBlackoutGate,
                TradingWindowGate, TrailDistanceSizerGate, TrailFloorBufferGate,
                ConsecutiveLossesGate, VolatilityAdaptiveSizerGate,
            )
            from engine.runtime import Runtime
            from engine.strategies.pullback import PullbackImpulse
            from bot.account_ctx import get_strategy_params
            from engine.structure.session import compute_session_structure
        except Exception as e:
            logger.warning(f"shadow engine disabled (import failed): {e!r}")
            self.enabled = False
            return

        self.enabled = True
        self.account_id = account_id
        self._build_market_context = build_market_context
        self._compute_session_structure = compute_session_structure
        self._economic_calendar = economic_calendar
        self._cross_market = cross_market_feed
        self.account_state = AccountState(
            balance=starting_balance,
            starting_balance=starting_balance,
            trail_floor=starting_balance - 2000.0,
            today_pnl=0.0,
            today_trades=0,
            consecutive_losses=0,
        )
        # Risk engine now uses REAL NewsBlackout (wired to calendar) +
        # macro alignment sizer + vol-adaptive sizer.
        gates = [
            ActiveLockoutGate(),
            DailyLossLimitGate(limit_usd=700.0),
            TrailFloorBufferGate(min_buffer_usd=800.0),
            ConsecutiveLossesGate(max_losses=4, pause_minutes=60),
            NewsBlackoutGate(enabled=True, calendar=economic_calendar,
                              pre_event_minutes=15, post_event_minutes=30),
            MaxTradesPerDayGate(max_trades=80),
            CooldownGate(seconds=60),
            TradingWindowGate(disabled_windows=[(7, 13)]),
            VolatilityAdaptiveSizerGate(default_qty=2),
            MacroAlignmentSizerGate(default_qty=2),
            TrailDistanceSizerGate(),
        ]
        self.runtime = Runtime(
            strategy=PullbackImpulse(),
            fill_model=SimFillModel(SimFillParams(seed=42)),
            risk_engine=RiskEngine(gates),
            account=self.account_state,
            strategy_params=get_strategy_params(account_id),
            default_qty=2,
        )
        # Cache session structure intra-tick
        self._cached_structure = None
        self._structure_computed_at = None
        # Track which bar timestamp we last processed (so we don't double-run
        # on the same closed bar across multiple ticks).
        self._last_processed_bar_ts: Optional[datetime] = None
        self._started_at = datetime.now(timezone.utc).isoformat()
        # Counters surfaced on the dashboard
        self.cycles_processed: int = 0
        self.errors: int = 0
        # File rotation by NY day
        self._last_file_date: Optional[str] = None

    # -----------------------------------------------------------------
    def on_new_closed_bar(self, bars_1m: pd.DataFrame,
                           now: datetime, ny_date_iso: str) -> None:
        """Drive the engine forward by ONE closed bar. Called from
        fib_main._tick(). Idempotent: if the latest bar has already been
        processed, this is a no-op."""
        if not self.enabled:
            return
        if bars_1m is None or bars_1m.empty:
            return
        last_bar_ts = bars_1m.index[-1]
        if hasattr(last_bar_ts, "to_pydatetime"):
            last_bar_ts = last_bar_ts.to_pydatetime()
        if self._last_processed_bar_ts == last_bar_ts:
            return  # already processed this bar
        try:
            # NY-day roll for shadow's daily counters
            if self._last_file_date is not None and ny_date_iso != self._last_file_date:
                self.runtime.roll_ny_day(now)
            self._last_file_date = ny_date_iso

            # Build market context and drive the engine on the latest bar
            bar = bars_1m.iloc[-1]
            ctx = self._build_market_context(bars_1m, now)
            # Attach extended context (macro, structure, news). All optional.
            if self._cross_market is not None:
                try:
                    ctx.macro = self._cross_market.snapshot()
                except Exception:
                    pass
            try:
                # Session structure -- refresh at most every 60s
                if (self._cached_structure is None or
                        self._structure_computed_at is None or
                        (now - self._structure_computed_at).total_seconds() > 60):
                    self._cached_structure = self._compute_session_structure(bars_1m, now)
                    self._structure_computed_at = now
                ctx.structure = self._cached_structure
            except Exception:
                pass
            if self._economic_calendar is not None:
                try:
                    ctx.next_news_event = \
                        self._economic_calendar.next_event_within(now, minutes=120)
                except Exception:
                    pass
            self.runtime.on_bar(bar, bars_1m, now, ctx)
            # Track trail floor like live does
            if self.account_state.balance - 2000 > self.account_state.trail_floor:
                self.account_state.trail_floor = self.account_state.balance - 2000
            self._last_processed_bar_ts = last_bar_ts
            self.cycles_processed += 1
        except Exception as e:
            self.errors += 1
            logger.warning(f"shadow engine tick failed: {e!r}")

    # -----------------------------------------------------------------
    def snapshot(self) -> dict:
        """Compact summary for the dashboard. Cheap to call."""
        if not self.enabled:
            return {"enabled": False}
        rt = self.runtime
        closed = rt.closed_trades
        wins = sum(1 for t in closed if t.pnl_usd(2.0, 0.74) > 0)
        total_pnl = sum(t.pnl_usd(2.0, 0.74) for t in closed)
        return {
            "enabled": True,
            "started_at": self._started_at,
            "cycles_processed": self.cycles_processed,
            "errors": self.errors,
            "last_processed_bar_ts": (
                self._last_processed_bar_ts.isoformat()
                if self._last_processed_bar_ts else None
            ),
            "trades_closed": len(closed),
            "wins": wins,
            "win_rate": (100 * wins / len(closed)) if closed else 0,
            "total_pnl_usd": round(total_pnl, 2),
            "balance": round(rt.account.balance, 2),
            "today_pnl": round(rt.account.today_pnl, 2),
            "today_trades": rt.account.today_trades,
            "pending_setups": len(rt.state.pending),
            "active_trade": (
                {
                    "side": rt.state.active.setup.side.value,
                    "entry": rt.state.active.entry_fill.fill_price,
                    "stop":  rt.state.active.stop_price,
                    "target": rt.state.active.target_price,
                    "mae": rt.state.active.mae_pts,
                    "mfe": rt.state.active.mfe_pts,
                }
                if rt.state.active else None
            ),
            "risk_denials_by_reason": dict(rt.risk.denial_counts),
        }

    # -----------------------------------------------------------------
    def export(self) -> dict:
        """Full export of decisions + trades for download. Larger than
        snapshot(); used by the download endpoint."""
        if not self.enabled:
            return {"enabled": False}
        rt = self.runtime
        return {
            "kind": "shadow_engine_export",
            "ts": datetime.now(timezone.utc).isoformat(),
            "started_at": self._started_at,
            "account_id": self.account_id,
            "config": {
                "strategy": rt.strategy.name,
                "params": rt.params,
                "default_qty": rt.default_qty,
                "fill_model": "SimFillModel(seed=42)",
                "risk_gates": [g.name for g in rt.risk.gates],
            },
            "stats": self.snapshot(),
            "closed_trades": [_jsonable(t) for t in rt.closed_trades],
            # Truncate decisions to last 500 to keep file size reasonable
            "decisions_tail": rt.decisions[-500:],
        }

    def persist(self, out_path: Path) -> None:
        """Write export() to disk. Called periodically by the live runtime."""
        if not self.enabled:
            return
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(self.export(), indent=2, default=str))
        except Exception as e:
            logger.warning(f"shadow persist failed: {e!r}")

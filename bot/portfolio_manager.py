"""
Paper-trading portfolio manager.

Holds cash + at most one open position, applies fills, marks open positions to
market, and writes through to persistence on every state change.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from bot import persistence
from research.signal_filters import (
    COMMISSION_PER_RT,
    DOLLARS_PER_POINT,
    SLIPPAGE_POINTS,
    TradeRef,
)

logger = logging.getLogger("portfolio")


@dataclass
class OpenPosition:
    signal_name: str
    side: str
    entry_time: str
    entry_px: float
    stop_px: float
    target_px: float
    contracts: int
    size_mult: float
    ml_decision: str
    rr: float


class PortfolioManager:
    def __init__(self):
        self.account = persistence.load_account()
        self.recent_trades: list[TradeRef] = []

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _today_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @property
    def open_position(self) -> Optional[OpenPosition]:
        op = self.account.get("open_position")
        return OpenPosition(**op) if op else None

    @property
    def balance(self) -> float:
        return float(self.account.get("balance", 0.0))

    def reload(self) -> None:
        self.account = persistence.load_account()

    def save(self) -> None:
        persistence.save_account(self.account)

    # --- trade lifecycle -------------------------------------------------

    def open_trade(self, candidate, fill_time: datetime, fill_px: float,
                   contracts: int) -> bool:
        if self.open_position is not None:
            return False
        # Apply slippage on fill
        if candidate.side == "LONG":
            fill_px = float(fill_px) + SLIPPAGE_POINTS
        else:
            fill_px = float(fill_px) - SLIPPAGE_POINTS
        op = OpenPosition(
            signal_name=candidate.signal_name,
            side=candidate.side,
            entry_time=fill_time.isoformat(),
            entry_px=float(fill_px),
            stop_px=float(candidate.stop_px),
            target_px=float(candidate.target_px),
            contracts=int(contracts),
            size_mult=float(candidate.size_mult),
            ml_decision=candidate.ml_decision,
            rr=float(candidate.rr),
        )
        self.account["open_position"] = asdict(op)
        self.save()
        logger.info("[portfolio] OPEN %s %s @ %.2f stop=%.2f tgt=%.2f size=%d",
                    op.signal_name, op.side, op.entry_px, op.stop_px,
                    op.target_px, op.contracts)
        return True

    def mark_to_market(self, last_px: float) -> dict | None:
        op = self.open_position
        if op is None:
            return None
        if op.side == "LONG":
            unrealised_pts = last_px - op.entry_px
        else:
            unrealised_pts = op.entry_px - last_px
        return {
            "signal_name": op.signal_name,
            "side": op.side,
            "entry_px": op.entry_px,
            "stop_px": op.stop_px,
            "target_px": op.target_px,
            "contracts": op.contracts,
            "unrealised_pts": float(unrealised_pts),
            "unrealised_dollars": float(unrealised_pts * op.contracts * 2.0),
            "entry_time": op.entry_time,
        }

    def check_exits(self, last_px: float, last_high: float, last_low: float,
                    last_time: datetime) -> dict | None:
        op = self.open_position
        if op is None:
            return None
        if op.side == "LONG":
            if last_low <= op.stop_px:
                return self._close(op, op.stop_px, last_time, "STOP")
            if last_high >= op.target_px:
                return self._close(op, op.target_px, last_time, "TARGET")
        else:
            if last_high >= op.stop_px:
                return self._close(op, op.stop_px, last_time, "STOP")
            if last_low <= op.target_px:
                return self._close(op, op.target_px, last_time, "TARGET")
        return None

    def _close(self, op: OpenPosition, fill_px: float,
               close_time: datetime, reason: str) -> dict:
        # Slippage on close
        if op.side == "LONG":
            fill_px = float(fill_px) - SLIPPAGE_POINTS
            pnl_pts = fill_px - op.entry_px
        else:
            fill_px = float(fill_px) + SLIPPAGE_POINTS
            pnl_pts = op.entry_px - fill_px
        contracts = op.contracts or 1
        # 1 MNQ = $2/pt; the account uses $60/pt scaling for parity with
        # "30 MNQ contracts" baseline. Keep a single source of truth: the
        # validation sheet uses $60/pt at base size. We scale linearly.
        dollars = pnl_pts * contracts * 2.0
        commission = COMMISSION_PER_RT * (contracts / 30.0)
        net = dollars - commission

        self.account["balance"] = float(self.balance + net)
        self.account["realized_pnl"] = float(self.account.get("realized_pnl", 0.0) + net)
        self.account["total_trades"] = int(self.account.get("total_trades", 0)) + 1
        won = net > 0
        if won:
            self.account["wins"] = int(self.account.get("wins", 0)) + 1
        else:
            self.account["losses"] = int(self.account.get("losses", 0)) + 1
        peak = max(self.account.get("peak_balance", self.balance), self.balance)
        self.account["peak_balance"] = float(peak)
        dd = peak - self.balance
        self.account["max_drawdown"] = float(max(self.account.get("max_drawdown", 0.0), dd))
        self.account["last_trade_close_time"] = close_time.isoformat()
        self.account["last_trade_was_winner"] = bool(won)
        self.account["last_trade_date"] = close_time.strftime("%Y-%m-%d")
        if close_time.strftime("%Y-%m-%d") == self.account.get("last_trade_date"):
            self.account["trades_today"] = int(self.account.get("trades_today", 0)) + 1
        else:
            self.account["trades_today"] = 1
        self.account["open_position"] = None
        self.save()

        trade = {
            "signal_name": op.signal_name,
            "side": op.side,
            "entry_time": op.entry_time,
            "exit_time": close_time.isoformat(),
            "entry_px": op.entry_px,
            "exit_px": float(fill_px),
            "contracts": int(contracts),
            "pnl_points": float(pnl_pts),
            "pnl_dollars": float(net),
            "exit_reason": reason,
            "win": bool(won),
        }
        persistence.append_trade(trade)
        self.recent_trades.append(TradeRef(
            signal_time=datetime.fromisoformat(op.entry_time),
            close_time=close_time, side=op.side,
            pnl_pts=float(pnl_pts), was_winner=bool(won),
        ))
        logger.info("[portfolio] CLOSE %s %s %s pnl=%+.1fpts ($%+.0f)",
                    op.signal_name, op.side, reason, pnl_pts, net)
        return trade

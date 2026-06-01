"""
Paper trading account.

Cost model (per spec):
  * 30 MNQ contracts × $2/point = $60/point
  * 2-pt entry slippage (always)
  * 2-pt adverse slippage on STOP fills, 0 on TARGET fills (we beat the level)
  * $60 round-trip commission, deducted at entry
  * Starting balance: $50,000

Lifecycle:
  enter()       — apply entry slip, deduct commission, INSERT row, store position
  check_exit()  — price-touch with high/low; stop wins if both touched same window
  _close()      — UPDATE row with exit_time/px/pnl/exit_reason, persist JSON
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from bot import persistence
from research.signal_filters import (
    ADVERSE_SLIPPAGE_POINTS,
    COMMISSION_ROUND_TRIP,
    CONTRACTS,
    DOLLARS_PER_POINT,
    NY_TZ,
    SLIPPAGE_POINTS,
)

logger = logging.getLogger("paper")


@dataclass
class OpenPosition:
    db_id: int
    signal_name: str
    side: str               # LONG | SHORT
    entry_time: str         # ISO UTC
    entry_px: float
    stop_px: float
    target_px: float
    qty: int
    ml_decision: str = ""
    ml_confidence: float = 0.0
    vol_regime: str = ""
    daily_bias: str = ""
    rr: float = 0.0
    adverse_slip_pts: float | None = None   # per-position override for stop slip
    commission_paid: float = 0.0            # round-trip cost deducted at entry,
                                            # needed at close to record true net P&L


@dataclass
class AccountState:
    balance: float = 50_000.0
    starting_balance: float = 50_000.0
    open_position: OpenPosition | None = None
    trades_today: int = 0
    last_trade_date: str | None = None
    last_trade_close_time: str | None = None
    last_trade_was_winner: bool = False
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    realized_pnl: float = 0.0
    peak_balance: float = 50_000.0
    max_drawdown: float = 0.0


class PaperAccount:
    def __init__(self) -> None:
        self.state = self._load_state()
        # Recover orphaned open trades: if SQLite has a trade with no
        # exit_time but our in-memory state thinks we're flat, the bot
        # crashed mid-trade. Re-hydrate so the next exit-check tick can
        # close the position cleanly. Without this, the SQLite row would
        # stay orphaned forever and the bot could open a duplicate.
        self._recover_orphaned_open_position()

    def _recover_orphaned_open_position(self) -> None:
        if self.state.open_position is not None:
            return
        try:
            rows = persistence.load_trades(limit=20, only_closed=False)
        except Exception:
            return
        # Find the most recent trade with no exit_time
        for t in rows:
            if t.get("exit_time"):
                continue
            try:
                op = OpenPosition(
                    db_id=t.get("id"),
                    signal_name=t.get("signal_name", ""),
                    side=t.get("side", ""),
                    entry_time=t.get("entry_time", ""),
                    entry_px=float(t.get("entry_px") or 0),
                    stop_px=float(t.get("stop_px") or 0),
                    target_px=float(t.get("target_px") or 0),
                    qty=int(t.get("qty") or 0),
                    ml_decision=t.get("ml_decision", ""),
                    ml_confidence=float(t.get("ml_confidence") or 0),
                    vol_regime=t.get("vol_regime", ""),
                    daily_bias=t.get("daily_bias", ""),
                    rr=float(t.get("rr") or 0),
                )
                self.state.open_position = op
                # Persist the recovery so we don't keep re-rehydrating
                self.save()
                logger.warning(
                    f"RECOVERED orphaned open position: {op.side} "
                    f"{op.signal_name} qty={op.qty} entry={op.entry_px:.2f} "
                    f"stop={op.stop_px:.2f} target={op.target_px:.2f} "
                    f"(db_id={op.db_id}). Next exit-check tick will manage it."
                )
                return
            except Exception as e:
                logger.error(f"failed to recover orphan trade {t.get('id')}: {e}")
                continue

    # ---- state I/O ----------------------------------------------------

    def _load_state(self) -> AccountState:
        d = persistence.load_account()
        op = d.get("open_position")
        op_obj = OpenPosition(**op) if op else None
        return AccountState(
            balance=float(d.get("balance", 50_000.0)),
            starting_balance=float(d.get("starting_balance", 50_000.0)),
            open_position=op_obj,
            trades_today=int(d.get("trades_today", 0)),
            last_trade_date=d.get("last_trade_date"),
            last_trade_close_time=d.get("last_trade_close_time"),
            last_trade_was_winner=bool(d.get("last_trade_was_winner", False)),
            total_trades=int(d.get("total_trades", 0)),
            wins=int(d.get("wins", 0)),
            losses=int(d.get("losses", 0)),
            realized_pnl=float(d.get("realized_pnl", 0.0)),
            peak_balance=float(d.get("peak_balance", d.get("balance", 50_000.0))),
            max_drawdown=float(d.get("max_drawdown", 0.0)),
        )

    def save(self) -> None:
        s = self.state
        op = s.open_position.__dict__ if s.open_position else None
        persistence.save_account({
            "balance": s.balance,
            "starting_balance": s.starting_balance,
            "open_position": op,
            "trades_today": s.trades_today,
            "last_trade_date": s.last_trade_date,
            "last_trade_close_time": s.last_trade_close_time,
            "last_trade_was_winner": s.last_trade_was_winner,
            "total_trades": s.total_trades,
            "wins": s.wins,
            "losses": s.losses,
            "realized_pnl": s.realized_pnl,
            "peak_balance": s.peak_balance,
            "max_drawdown": s.max_drawdown,
        })

    # ---- helpers ------------------------------------------------------

    def _roll_daily(self, now: datetime) -> None:
        ny_date = now.astimezone(tz=None).date().isoformat()  # local-machine fallback
        try:
            ny_date = pd.Timestamp(now).tz_convert(NY_TZ).date().isoformat()
        except Exception:
            pass
        if self.state.last_trade_date != ny_date:
            self.state.trades_today = 0
            self.state.last_trade_date = ny_date

    # ---- enter --------------------------------------------------------

    def enter(self, *, signal_name: str, side: str, entry_px_raw: float,
              stop_px: float, target_px: float, qty: int = CONTRACTS,
              ml_decision: str = "", ml_confidence: float = 0.0,
              vol_regime: str = "", daily_bias: str = "", rr: float = 0.0,
              now: datetime | None = None,
              entry_slip_pts: float | None = None,
              adverse_slip_pts: float | None = None,
              commission_per_mnq_rt: float | None = None) -> OpenPosition:
        """`entry_slip_pts` overrides the default SLIPPAGE_POINTS (2pt) per call.
        Strategies that send LIMIT orders should pass 0 — limit orders fill at
        limit or better. `adverse_slip_pts` overrides the default
        ADVERSE_SLIPPAGE_POINTS (2pt) applied on stop fills.
        `commission_per_mnq_rt` overrides the default $2/contract (legacy NQ
        figure) with the actual MNQ broker rate (~$0.74-$1)."""
        if self.state.open_position is not None:
            # Was raising RuntimeError, which desynced strategy state from
            # paper-account state after orphan recovery on restart. Now we
            # mark the stale position as closed at the new entry price
            # (best estimate of "where we were when we crashed") and
            # proceed with the new entry. Loses fidelity on the orphan's
            # P&L but keeps live and paper books in sync.
            stale = self.state.open_position
            logger.warning(
                f"paper account had orphan {stale.side} @ {stale.entry_px:.2f} "
                f"(db_id={stale.db_id}); closing it before new entry")
            try:
                persistence.close_trade(
                    stale.db_id,
                    exit_time=(now or datetime.now(timezone.utc)).isoformat(),
                    exit_px=entry_px_raw, exit_reason="orphan_recovered", pnl=0.0)
            except Exception as ce:
                logger.debug(f"orphan close persist failed (non-fatal): {ce!r}")
            self.state.open_position = None
        now = now or datetime.now(timezone.utc)
        slip = SLIPPAGE_POINTS if entry_slip_pts is None else entry_slip_pts
        slipped = entry_px_raw + slip if side == "LONG" else entry_px_raw - slip
        if commission_per_mnq_rt is None:
            commission = COMMISSION_ROUND_TRIP * (qty / CONTRACTS)
        else:
            commission = commission_per_mnq_rt * qty
        self.state.balance -= commission

        trade_id = persistence.insert_trade({
            "signal_name": signal_name, "side": side,
            "entry_time": now.isoformat(),
            "entry_px": slipped, "stop_px": stop_px, "target_px": target_px,
            "qty": qty, "ml_decision": ml_decision, "ml_confidence": ml_confidence,
            "vol_regime": vol_regime, "daily_bias": daily_bias, "rr": rr,
        })
        op = OpenPosition(
            db_id=trade_id, signal_name=signal_name, side=side,
            entry_time=now.isoformat(), entry_px=slipped,
            stop_px=stop_px, target_px=target_px, qty=qty,
            ml_decision=ml_decision, ml_confidence=ml_confidence,
            vol_regime=vol_regime, daily_bias=daily_bias, rr=rr,
            adverse_slip_pts=adverse_slip_pts,
            commission_paid=commission,
        )
        self.state.open_position = op
        self._roll_daily(now)
        # Save JSON state IMMEDIATELY after assigning open_position so a
        # crash between here and the next tick doesn't orphan the trade.
        # The startup _recover_orphaned_open_position() handles the case
        # where this save fails too.
        try:
            self.save()
        except Exception as e:
            logger.error(f"CRITICAL: paper_account.json save failed after enter — "
                            f"SQLite trade {trade_id} would orphan on restart. {e}")
            raise
        logger.info(f"ENTER {side} {signal_name} @ {slipped:.2f} stop={stop_px:.2f} target={target_px:.2f} qty={qty}")
        return op

    # ---- exit ---------------------------------------------------------

    def check_exit(self, high: float, low: float, last_price: float,
                   now: datetime | None = None) -> dict | None:
        op = self.state.open_position
        if op is None:
            return None
        now = now or datetime.now(timezone.utc)
        stop_hit = (low <= op.stop_px) if op.side == "LONG" else (high >= op.stop_px)
        target_hit = (high >= op.target_px) if op.side == "LONG" else (low <= op.target_px)
        if not (stop_hit or target_hit):
            return None
        if stop_hit and target_hit:
            return self._close(op.stop_px, "STOP", adverse=True, now=now)
        if stop_hit:
            return self._close(op.stop_px, "STOP", adverse=True, now=now)
        return self._close(op.target_px, "TARGET", adverse=False, now=now)

    def _close(self, exit_px_raw: float, reason: str,
               adverse: bool, now: datetime) -> dict:
        op = self.state.open_position
        assert op is not None
        adv = ADVERSE_SLIPPAGE_POINTS if op.adverse_slip_pts is None else op.adverse_slip_pts
        if adverse:
            exit_px = exit_px_raw - adv if op.side == "LONG" else exit_px_raw + adv
        else:
            exit_px = exit_px_raw

        if op.side == "LONG":
            points = exit_px - op.entry_px
        else:
            points = op.entry_px - exit_px
        gross = points * DOLLARS_PER_POINT * (op.qty / CONTRACTS)
        # True economic P&L = gross - commission_paid_at_entry. We add the
        # gross to balance here, but the DB pnl field needs to record the
        # NET so balance, lifetime_stats, and today_pnl all agree.
        # (Previously net=gross which made today_pnl miss the commission
        # cost -- showed up on dashboard as a phantom "closed_days = -$X"
        # equal to today's accumulated commissions.)
        net = gross - op.commission_paid

        self.state.balance += gross
        self.state.realized_pnl += net
        self.state.total_trades += 1
        is_winner = net > 0
        if is_winner:
            self.state.wins += 1
        else:
            self.state.losses += 1
        self.state.last_trade_was_winner = is_winner
        self.state.last_trade_close_time = now.isoformat()
        self.state.trades_today += 1
        self.state.peak_balance = max(self.state.peak_balance, self.state.balance)
        self.state.max_drawdown = min(self.state.max_drawdown,
                                      self.state.balance - self.state.peak_balance)

        persistence.close_trade(op.db_id, now.isoformat(), exit_px, reason, net)
        # Record the actual commission paid -- the DB schema has a column
        # but enter() never populated it. Used by migrate_commission_into_pnl
        # to distinguish migrated rows ($0-$5) from unmigrated rows ($60).
        try:
            with persistence._conn() as conn:
                conn.execute("UPDATE trades SET commission=? WHERE id=?",
                             (op.commission_paid, op.db_id))
        except Exception as e:
            logger.debug(f"commission persistence failed (non-fatal): {e}")
        self.state.open_position = None
        self.save()
        logger.info(f"EXIT {op.side} {op.signal_name} @ {exit_px:.2f} ({reason}) "
                    f"pnl={net:+.2f} bal={self.state.balance:.2f}")
        return {
            "exit_time": now.isoformat(),
            "exit_px": exit_px,
            "exit_reason": reason,
            "pnl": net,
            "signal_name": op.signal_name,
            "side": op.side,
        }

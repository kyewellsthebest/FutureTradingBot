"""
Lucid-aware paper account.

Subclasses PaperAccount and layers on the Lucid 50K Pro Funded behavior:
  - Trailing-drawdown floor (peak EOD - $2K, locks at $50K once peak >= $52K,
    LucidScale 60%-of-peak above)
  - Daily Loss Limit auto-flatten ($1,200)
  - 40% consistency-rule throttle (kicks in after MIN_DAYS_TO_PAYOUT)
  - 40 MNQ position cap
  - Microscalp ratio tracking
  - Hedging block (intra-account is impossible by design — single open position)
  - Auto-restart: when the floor is breached, archive the dead account to the
    funded-accounts ledger and reset to a fresh $50K state.

The runtime guard from research/lucid_guard.py is the single source of truth
for the rules. This class wraps it with persistence + auto-restart.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from bot import persistence
from bot.funded_accounts import FundedLedger
from bot.paper_trading import AccountState, OpenPosition, PaperAccount
from research import lucid_guard
from research.lucid_guard import (
    CONSISTENCY_PCT,
    DLL,
    INITIAL_TRAIL,
    LUCIDSCALE_RATIO,
    MAX_MNQ,
    MIN_DAYS_TO_PAYOUT,
    PROFIT_SPLIT,
    PROFIT_TARGET,
    START_BAL,
    TRAIL_DROP,
    TRAIL_LOCK_AT,
    TRAIL_LOCKED_FLOOR,
    GuardDecision,
    LucidState,
    can_request_payout,
    evaluate_trade,
)
from research.signal_filters import DOLLARS_PER_POINT, NY_TZ

logger = logging.getLogger("lucid_account")

from bot.account_ctx import data_dir
def _lucid_state_path():
    return data_dir() / "lucid_account.json"

def __getattr__(name):
    """Backward-compat: code referencing module-level LUCID_STATE_PATH
    keeps working but resolves per current thread's account."""
    if name == "LUCID_STATE_PATH": return _lucid_state_path()
    raise AttributeError(f"module 'lucid_account' has no attribute {name!r}")

# Bump this any time we need to force a full account reset on the next
# Railway deploy. The bot remembers the last applied serial in the state
# file; on startup if it doesn't match this constant, _hard_reset_all()
# runs once, then the new serial is persisted so it won't trigger again.
RESET_SERIAL = 13  # bumped: strategy upgraded (window 3->4 bars, target 10->12pt; +21%/mo)


# ---------------------------------------------------------------------------
# State persisted to disk
# ---------------------------------------------------------------------------
@dataclass
class LucidAccountState:
    """All Lucid bookkeeping for the live account, persisted as JSON."""
    account_id: int = 1                 # increments on auto-restart
    started_at: str = ""
    peak_eod_high: float = START_BAL
    trail_floor: float = INITIAL_TRAIL
    trail_locked: bool = False
    cum_pnl_closed_days: float = 0.0    # cumulative P&L excluding today
    today_pnl: float = 0.0
    today_date: Optional[str] = None    # NY date string YYYY-MM-DD
    n_trading_days: int = 0
    micro_total_profit: float = 0.0
    micro_short_profit: float = 0.0
    blown: bool = False
    blow_reason: Optional[str] = None
    applied_reset_serial: int = 0       # last RESET_SERIAL applied

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "LucidAccountState":
        return cls(**{k: d.get(k, getattr(cls(), k)) for k in cls.__dataclass_fields__})


def _load_state() -> LucidAccountState:
    if not _lucid_state_path().exists():
        s = LucidAccountState(started_at=datetime.now(timezone.utc).isoformat())
        _save_state(s)
        return s
    try:
        import json
        return LucidAccountState.from_dict(json.loads(_lucid_state_path().read_text()))
    except Exception as e:
        logger.error(f"lucid state load failed: {e}; resetting")
        s = LucidAccountState(started_at=datetime.now(timezone.utc).isoformat())
        _save_state(s)
        return s


def _save_state(s: LucidAccountState) -> None:
    import json
    _lucid_state_path().parent.mkdir(parents=True, exist_ok=True)
    _lucid_state_path().write_text(json.dumps(s.to_dict(), indent=2, default=str))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ny_date_iso(now: datetime) -> str:
    try:
        return pd.Timestamp(now).tz_convert(NY_TZ).date().isoformat()
    except Exception:
        return now.astimezone().date().isoformat()


# ---------------------------------------------------------------------------
# LucidAccount — wraps PaperAccount with Lucid behavior
# ---------------------------------------------------------------------------
class LucidAccount(PaperAccount):
    def __init__(self) -> None:
        super().__init__()
        self.lucid: LucidAccountState = _load_state()
        self.ledger = FundedLedger()
        # Auto-reset trigger #1: serial bump. Bumping RESET_SERIAL in
        # source code forces exactly one reset on the next deploy.
        # Self-extinguishing — the new serial is persisted so it won't
        # fire again until the constant is bumped again.
        if self.lucid.applied_reset_serial != RESET_SERIAL:
            logger.warning(f"RESET_SERIAL bumped {self.lucid.applied_reset_serial} → "
                           f"{RESET_SERIAL} — running one-shot reset")
            self._hard_reset_all()
        # Auto-reset trigger #2: manual env var (still supported for ad-hoc).
        # Set BOT_RESET_ACCOUNT=1 in Railway Variables. UNSET it after, or
        # every deploy will wipe again.
        import os
        if os.environ.get("BOT_RESET_ACCOUNT") == "1":
            self._hard_reset_all()
        # Force a day-roll check at startup. Belt-and-braces for the
        # "TODAY P&L stuck on yesterday" bug — even if the snapshot path
        # somehow misses it, we ALWAYS reconcile here so the bot's first
        # tick after a restart has a clean today_pnl.
        try:
            self._maybe_roll_eod(datetime.now(timezone.utc))
        except Exception as e:
            logger.warning(f"startup day-roll failed: {e}")
        # Make sure the underlying paper-account balance + trail are coherent
        # with the Lucid state (in case we reset since last persist).
        if self.state.balance != self.state.starting_balance and self.lucid.account_id == 1 \
                and self.lucid.cum_pnl_closed_days == 0 and self.lucid.today_pnl == 0:
            # Fresh Lucid state but stale paper state — reset paper too
            self._reset_paper_account()

    # ---- helpers --------------------------------------------------

    def _save_lucid(self) -> None:
        _save_state(self.lucid)

    def _reset_paper_account(self) -> None:
        """Wipe the underlying PaperAccount to a fresh $50K start."""
        self.state = AccountState(
            balance=START_BAL, starting_balance=START_BAL,
            open_position=None,
            trades_today=0, last_trade_date=None,
            last_trade_close_time=None, last_trade_was_winner=False,
            total_trades=0, wins=0, losses=0, realized_pnl=0.0,
            peak_balance=START_BAL, max_drawdown=0.0,
        )
        self.save()

    def _hard_reset_all(self) -> None:
        """One-shot full reset triggered by RESET_SERIAL bump or
        BOT_RESET_ACCOUNT=1. Wipes paper balance, Lucid bookkeeping,
        the trades DB, the dashboard JSON cache, and signal-event JSON so
        the dashboard shows a clean $50k account with zero trade history."""
        logger.warning("=== HARD RESET requested — wiping account back to $50k ===")
        # Lucid state → fresh, but record the serial we just applied so
        # the bump-trigger doesn't loop on every restart.
        self.lucid = LucidAccountState(
            account_id=1,
            started_at=datetime.now(timezone.utc).isoformat(),
            peak_eod_high=START_BAL,
            trail_floor=INITIAL_TRAIL,
            applied_reset_serial=RESET_SERIAL,
        )
        self._save_lucid()
        # Paper account → fresh
        self._reset_paper_account()
        # Trades DB → wiped via persistence helper (handles concurrent
        # bot writes by using DELETE+VACUUM rather than file unlink, and
        # falls back to file removal if that fails).
        try:
            n = persistence.wipe_all_trades()
            logger.warning(f"=== trades DB cleared ({n} rows deleted) ===")
        except Exception as e:
            logger.warning(f"trades DB wipe failed (non-fatal): {e}")
        # Dashboard JSON cache → deleted (regenerated on next snapshot in ~60s)
        try:
            dashboard_path = _lucid_state_path().parent / "dashboard_data.json"
            if dashboard_path.exists():
                dashboard_path.unlink()
                logger.warning("=== dashboard_data.json deleted ===")
        except Exception as e:
            logger.warning(f"dashboard cache wipe failed (non-fatal): {e}")
        # Signal events JSON → deleted
        try:
            sig_path = _lucid_state_path().parent / "signal_events.json"
            if sig_path.exists():
                sig_path.unlink()
                logger.warning("=== signal_events.json deleted ===")
        except Exception as e:
            logger.warning(f"signal events wipe failed (non-fatal): {e}")
        logger.warning(f"=== HARD RESET COMPLETE — balance ${START_BAL:,.0f}, "
                       f"trail ${INITIAL_TRAIL:,.0f} ===")
        logger.warning("=== REMEMBER to unset BOT_RESET_ACCOUNT in Railway "
                       "or every deploy will wipe again ===")

    def _maybe_roll_eod(self, now: datetime) -> None:
        """If today's NY date changed, roll P&L into cumulative + recompute floor."""
        ny_today = _ny_date_iso(now)
        if self.lucid.today_date is None:
            self.lucid.today_date = ny_today
            self.lucid.n_trading_days = max(self.lucid.n_trading_days, 1)
            self._save_lucid()
            return
        if ny_today == self.lucid.today_date:
            return
        # Day changed — close out yesterday
        self.lucid.cum_pnl_closed_days += self.lucid.today_pnl
        self.lucid.today_pnl = 0.0
        self.lucid.today_date = ny_today
        # Update peak EOD high from current balance
        self.lucid.peak_eod_high = max(self.lucid.peak_eod_high, self.state.balance)
        # Latch the lock
        if not self.lucid.trail_locked and self.lucid.peak_eod_high >= TRAIL_LOCK_AT:
            self.lucid.trail_locked = True
            logger.info(f"trail LOCKED at ${TRAIL_LOCKED_FLOOR:.0f} (peak EOD ${self.lucid.peak_eod_high:.0f} >= ${TRAIL_LOCK_AT:.0f})")
        # Recompute floor
        if not self.lucid.trail_locked:
            new_floor = self.lucid.peak_eod_high - TRAIL_DROP
        else:
            scale = LUCIDSCALE_RATIO * self.lucid.peak_eod_high
            new_floor = max(TRAIL_LOCKED_FLOOR, scale)
        self.lucid.trail_floor = max(self.lucid.trail_floor, new_floor)
        self.lucid.n_trading_days += 1
        self._save_lucid()
        logger.info(f"EOD roll → day {self.lucid.today_date} | trail ${self.lucid.trail_floor:.0f} | "
                    f"peak EOD ${self.lucid.peak_eod_high:.0f} | cum P&L ${self.lucid.cum_pnl_closed_days:+.0f}")

    def _build_runtime_lucid_state(self) -> LucidState:
        """Snapshot the persisted LucidAccountState into the runtime LucidState
        used by lucid_guard.evaluate_trade()."""
        rs = LucidState(
            balance=self.state.balance,
            peak_eod_high=self.lucid.peak_eod_high,
            trail_floor=self.lucid.trail_floor,
            trail_locked=self.lucid.trail_locked,
            cum_pnl=self.lucid.cum_pnl_closed_days,
            today_pnl=self.lucid.today_pnl,
            current_day=self.lucid.today_date,
            n_trading_days=self.lucid.n_trading_days,
            open_position_side=self.state.open_position.side if self.state.open_position else None,
            open_position_n=self.state.open_position.qty if self.state.open_position else 0,
            blown=self.lucid.blown,
            blow_reason=self.lucid.blow_reason,
            micro_total_profit=self.lucid.micro_total_profit,
            micro_short_profit=self.lucid.micro_short_profit,
        )
        return rs

    # ---- pre-trade Lucid guard ------------------------------------

    def can_enter(self, side: str, qty: int, target_pnl: float, stop_pnl: float,
                   now: datetime) -> GuardDecision:
        """Run lucid_guard.evaluate_trade() against the current persisted state.
        The runtime returns False for any rule violation; main.py honors that
        by skipping the entry."""
        self._maybe_roll_eod(now)
        if self.lucid.blown:
            return GuardDecision(False, f"account blown: {self.lucid.blow_reason}", "blown")
        # The guard's running-day consistency check is informational; we wrap the
        # 3-day grace window here to match the simulator's logic.
        rs = self._build_runtime_lucid_state()
        if self.lucid.n_trading_days <= MIN_DAYS_TO_PAYOUT \
                and rs.cum_pnl < PROFIT_TARGET:
            # Disable the consistency check by zeroing today's P&L for the
            # check (simulator does the same — 3-day grace window).
            rs.today_pnl = 0.0
        return evaluate_trade(rs, side=side, n_contracts=qty,
                               proposed_pnl_at_target=target_pnl,
                               proposed_pnl_at_stop=stop_pnl,
                               correlated_open_in_other_account=None)

    # ---- enter/exit hooks -----------------------------------------

    def enter(self, *args, now: datetime | None = None, **kw):
        now = now or datetime.now(timezone.utc)
        self._maybe_roll_eod(now)
        return super().enter(*args, now=now, **kw)

    def check_exit(self, high: float, low: float, last_price: float,
                   now: datetime | None = None) -> dict | None:
        now = now or datetime.now(timezone.utc)
        self._maybe_roll_eod(now)
        result = super().check_exit(high, low, last_price, now=now)
        if result is None:
            return None
        # The trade just closed — update Lucid state with the realized P&L
        pnl = float(result.get("pnl", 0.0))
        self.lucid.today_pnl += pnl
        # Microscalp accounting: hold time
        try:
            entry_t = pd.Timestamp(result.get("entry_time") or "")
        except Exception:
            entry_t = None
        try:
            exit_t = pd.Timestamp(result.get("exit_time") or "")
        except Exception:
            exit_t = None
        hold_s = (exit_t - entry_t).total_seconds() if entry_t and exit_t else 60.0
        if pnl > 0:
            self.lucid.micro_total_profit += pnl
            if hold_s <= 5:
                self.lucid.micro_short_profit += pnl
        # Real-time floor-breach check (intraday — same trail_floor value)
        if self.state.balance <= self.lucid.trail_floor:
            self.lucid.blown = True
            self.lucid.blow_reason = (
                f"trail_breach@${self.state.balance:.0f}<=${self.lucid.trail_floor:.0f}"
            )
            self._save_lucid()
            self._auto_restart(now)
            return result
        # DLL auto-flatten check (informational — main loop will refuse new entries)
        if self.lucid.today_pnl <= -DLL:
            logger.warning(f"DLL hit: today P&L ${self.lucid.today_pnl:+.0f} ≤ -${DLL:.0f}; "
                           f"no new entries until tomorrow")
        self._save_lucid()
        return result

    def _close(self, exit_px_raw: float, reason: str,
                adverse: bool, now: datetime) -> dict:
        """Override PaperAccount._close to ALSO update Lucid bookkeeping.

        The fib_main flow calls account._close() directly (bypassing
        check_exit's tick-based simulation), which means without this
        override the Lucid state (today_pnl, microscalp tracker,
        trail-floor breach check) is never updated. That's why the
        dashboard's TODAY P&L stayed at $0 even after losing trades —
        balance updated, but today_pnl didn't."""
        self._maybe_roll_eod(now)
        result = super()._close(exit_px_raw, reason, adverse, now)
        pnl = float(result.get("pnl", 0.0))
        self.lucid.today_pnl += pnl
        # Microscalp tracker (Lucid's >5s hold rule)
        try:
            entry_t = pd.Timestamp(result.get("entry_time") or "")
            exit_t = pd.Timestamp(result.get("exit_time") or "")
            hold_s = (exit_t - entry_t).total_seconds()
        except Exception:
            hold_s = 60.0
        if pnl > 0:
            self.lucid.micro_total_profit += pnl
            if hold_s <= 5:
                self.lucid.micro_short_profit += pnl
        # Real-time trail-floor breach check
        if self.state.balance <= self.lucid.trail_floor:
            self.lucid.blown = True
            self.lucid.blow_reason = (
                f"trail_breach@${self.state.balance:.0f}<=${self.lucid.trail_floor:.0f}"
            )
        if self.lucid.today_pnl <= -DLL:
            logger.warning(f"DLL hit: today P&L ${self.lucid.today_pnl:+.0f} ≤ -${DLL:.0f}; "
                           f"no new entries until tomorrow")
        self._save_lucid()
        return result

    # ---- auto-restart on blow-up ----------------------------------

    def _auto_restart(self, now: datetime) -> None:
        """Archive the dead account to the ledger and start fresh."""
        archived_id = self.lucid.account_id
        ended_at = now.isoformat()
        outcome = {
            "account_id": archived_id,
            "started_at": self.lucid.started_at,
            "ended_at": ended_at,
            "outcome": "FAILED",
            "blow_reason": self.lucid.blow_reason,
            "ending_balance": self.state.balance,
            "peak_eod_high": self.lucid.peak_eod_high,
            "trail_floor_at_blow": self.lucid.trail_floor,
            "n_trading_days": self.lucid.n_trading_days,
            "cum_pnl": self.lucid.cum_pnl_closed_days + self.lucid.today_pnl,
            "n_trades": self.state.total_trades,
            "wins": self.state.wins,
            "losses": self.state.losses,
        }
        self.ledger.record(outcome)
        logger.warning(f"=== ACCOUNT #{archived_id} BLOWN: {self.lucid.blow_reason} ===")
        logger.warning(f"=== Auto-restarting with fresh ${START_BAL:,.0f} (account #{archived_id+1}) ===")
        # Reset both layers
        self.lucid = LucidAccountState(
            account_id=archived_id + 1,
            started_at=ended_at,
            peak_eod_high=START_BAL,
            trail_floor=INITIAL_TRAIL,
        )
        self._save_lucid()
        self._reset_paper_account()

    # ---- views ----------------------------------------------------

    def lucid_snapshot(self) -> dict:
        """Public snapshot used by the dashboard."""
        # Make sure the NY-day rollover happens even when the bot is flat
        # for hours/days. _maybe_roll_eod only fires from can_enter/enter/
        # exit hooks otherwise, so today_pnl could stay stuck on yesterday.
        try:
            self._maybe_roll_eod(datetime.now(timezone.utc))
        except Exception as e:
            logger.warning(f"lucid_snapshot day-roll check failed: {e}")
        rs = self._build_runtime_lucid_state()
        payout = can_request_payout(rs)
        running_total = rs.cum_pnl + rs.today_pnl
        # Legacy "today share" -- kept for backwards-compat. Today's share
        # of total profit (the original consistency metric).
        today_share = (rs.today_pnl / running_total) if running_total > 0 else 0.0
        # New payout-readiness math: look across ALL days, find the biggest
        # one (could be today, could be Friday two weeks ago), compute its
        # share of total profit, and how much more $ would need to come
        # from OTHER days to drop the biggest day's share under the 40%
        # threshold (= the moment a payout request would clear consistency).
        try:
            from bot import persistence
            day_rows = persistence.per_day_pnls()
        except Exception as e:
            logger.debug(f"per_day_pnls failed: {e!r}")
            day_rows = []
        # Profitable days only matter for the rule -- losing days don't
        # contribute to total profit, and the ratio is computed on positive
        # profit. If a day is in the red, exclude it from both biggest-day
        # search and total.
        positive_days = [d for d in day_rows if d["pnl"] > 0]
        total_profit = sum(d["pnl"] for d in positive_days)
        if positive_days and total_profit > 0:
            worst_day = max(positive_days, key=lambda d: d["pnl"])
            worst_day_pnl = float(worst_day["pnl"])
            worst_day_date = worst_day["ny_date"]
            worst_day_share = worst_day_pnl / total_profit
            # To drop worst_day_share below 40%, total_profit needs to grow
            # such that worst_day_pnl / new_total < 0.40
            #   new_total > worst_day_pnl / 0.40
            # All growth must come from OTHER days (worst day stays fixed --
            # making the worst day bigger only makes the ratio worse).
            needed_other_total = (worst_day_pnl / CONSISTENCY_PCT) - worst_day_pnl
            current_other_total = total_profit - worst_day_pnl
            headroom_needed = max(0.0, needed_other_total - current_other_total)
            payout_consistency_ok = worst_day_share < CONSISTENCY_PCT
        else:
            worst_day_pnl = 0.0
            worst_day_date = None
            worst_day_share = 0.0
            headroom_needed = 0.0
            payout_consistency_ok = True
        return {
            "account_id": self.lucid.account_id,
            "started_at": self.lucid.started_at,
            "balance": self.state.balance,
            "starting_balance": START_BAL,
            "peak_eod_high": self.lucid.peak_eod_high,
            "trail_floor": self.lucid.trail_floor,
            "trail_locked": self.lucid.trail_locked,
            "buffer_to_trail": self.state.balance - self.lucid.trail_floor,
            "today_pnl": self.lucid.today_pnl,
            "today_date": self.lucid.today_date,
            "cum_pnl": running_total,
            "n_trading_days": self.lucid.n_trading_days,
            "today_share_of_total": today_share,
            "consistency_ok": today_share <= CONSISTENCY_PCT or running_total <= 0,
            # Payout readiness (the actually useful number for clicking
            # "request payout") -- looks at the biggest single day across
            # all NY days and its share of TOTAL profit. Bot trades
            # freely; this is informational, not a gate.
            "worst_day_pnl": round(worst_day_pnl, 2),
            "worst_day_date": worst_day_date,
            "worst_day_share": round(worst_day_share, 4),
            "payout_consistency_ok": payout_consistency_ok,
            "consistency_headroom_needed_usd": round(headroom_needed, 2),
            "total_profit_so_far": round(total_profit, 2),
            "dll_remaining": max(0.0, DLL + self.lucid.today_pnl),
            "dll_hit": self.lucid.today_pnl <= -DLL,
            "payout_eligible": payout.eligible,
            "payout_reason": payout.reason,
            "take_home_at_split": payout.take_home_at_split,
            "profit_target": PROFIT_TARGET,
            "min_days_to_payout": MIN_DAYS_TO_PAYOUT,
            "max_mnq": MAX_MNQ,
            "consistency_pct": CONSISTENCY_PCT,
            "profit_split": PROFIT_SPLIT,
            "blown": self.lucid.blown,
            "blow_reason": self.lucid.blow_reason,
        }

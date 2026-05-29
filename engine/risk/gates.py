"""Risk gates. Each gate has ONE job. The RiskEngine chains them in a
fixed order; first denial wins. Gate order matters: cheap checks first,
expensive last; lockout gates before sizing gates.

Every gate stores its config in __init__ (no globals) and returns a
RiskDecision with a stable `reason` tag for analytics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from engine.market_context import MarketContext
from engine.types import RiskDecision, Setup


@dataclass
class AccountState:
    """Everything the risk engine needs to know about the account."""
    balance: float
    starting_balance: float
    trail_floor: float           # Lucid 50K Pro starting trail = balance - 2000
    today_pnl: float             # realized P&L for the current NY day
    today_trades: int            # count of closed trades today
    consecutive_losses: int
    last_trade_close_ts: Optional[datetime] = None
    is_in_trade: bool = False
    # Locks are bound to a tag so multiple gates can have independent
    # locks without stepping on each other.
    locks: dict = field(default_factory=dict)   # {tag: lockout_until_ts}


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class RiskGate(ABC):
    name: str = "base_gate"

    @abstractmethod
    def check(self, setup: Setup, state: AccountState,
              ctx: MarketContext) -> RiskDecision:
        ...


# ---------------------------------------------------------------------------
# Concrete gates -- ordered roughly cheapest to most expensive
# ---------------------------------------------------------------------------
class ActiveLockoutGate(RiskGate):
    """Honour any lock left by another gate (e.g. daily_loss_limit ->
    locked until end of NY day)."""
    name = "active_lockout"

    def check(self, setup, state, ctx):
        for tag, until in list(state.locks.items()):
            if until is None:
                continue
            if ctx.now < until:
                return RiskDecision.deny(
                    reason=f"locked_by_{tag}",
                    detail=f"locked until {until.isoformat()}",
                    lockout_until=until,
                )
            else:
                # Lockout expired; clean up.
                state.locks.pop(tag, None)
        return RiskDecision.ok()


class DailyLossLimitGate(RiskGate):
    """Self-imposed DLL well below the prop firm's $1,200 DLL. When today's
    realized P&L breaches the limit, lock out for the rest of the NY day.
    """
    name = "daily_loss_limit"

    def __init__(self, limit_usd: float = 700.0):
        self.limit = float(limit_usd)

    def check(self, setup, state, ctx):
        if self.limit <= 0:
            return RiskDecision.ok()
        if state.today_pnl <= -self.limit:
            # Lock until next NY day rollover.
            # NY day = 16:00 ET; approx midnight UTC.
            from engine.market_context import ET_OFFSET_HOURS
            et_now = ctx.now + timedelta(hours=ET_OFFSET_HOURS)
            # Next 16:00 ET
            rollover_et = et_now.replace(hour=16, minute=0, second=0, microsecond=0)
            if et_now.hour >= 16:
                rollover_et = rollover_et + timedelta(days=1)
            rollover_utc = rollover_et - timedelta(hours=ET_OFFSET_HOURS)
            state.locks["daily_loss_limit"] = rollover_utc.replace(tzinfo=ctx.now.tzinfo)
            return RiskDecision.deny(
                reason="daily_loss_limit",
                detail=f"today_pnl={state.today_pnl:.2f} <= -{self.limit:.0f}",
                lockout_until=rollover_utc,
            )
        return RiskDecision.ok()


class TrailFloorBufferGate(RiskGate):
    """Lucid 50K Pro: trail floor = peak_eod - $2000. If we get within
    $min_buffer of the floor, stop trading -- one bad fill could breach.
    """
    name = "trail_floor_buffer"

    def __init__(self, min_buffer_usd: float = 800.0):
        self.min_buffer = float(min_buffer_usd)

    def check(self, setup, state, ctx):
        distance = state.balance - state.trail_floor
        if distance < self.min_buffer:
            return RiskDecision.deny(
                reason="trail_floor_buffer",
                detail=f"only ${distance:.0f} above trail (need ${self.min_buffer:.0f})",
            )
        return RiskDecision.ok()


class ConsecutiveLossesGate(RiskGate):
    """After N consecutive losses, set a lockout for M minutes AND reset
    the streak counter. The reset is important -- it ensures the lock is
    set EXACTLY ONCE per streak event, instead of re-set every tick. Once
    set, ActiveLockoutGate (which runs earlier in the chain) handles the
    denial. After the lock expires, ActiveLockoutGate removes it and this
    gate allows again with a fresh streak budget."""
    name = "consecutive_losses"

    def __init__(self, max_losses: int = 4, pause_minutes: int = 60):
        self.max_losses = int(max_losses)
        self.pause_minutes = int(pause_minutes)

    def check(self, setup, state, ctx):
        if state.consecutive_losses >= self.max_losses \
           and "consecutive_losses" not in state.locks:
            until = ctx.now + timedelta(minutes=self.pause_minutes)
            state.locks["consecutive_losses"] = until
            # Reset streak so we don't trip again immediately after lock
            # expires (we've waited it out -- start fresh).
            state.consecutive_losses = 0
            return RiskDecision.deny(
                reason="consecutive_losses",
                detail=f"hit {self.max_losses} in a row",
                lockout_until=until,
            )
        return RiskDecision.ok()


class MaxTradesPerDayGate(RiskGate):
    """Hard cap on trade count to prevent revenge trading and stay within
    Lucid's consistency expectations."""
    name = "max_trades_per_day"

    def __init__(self, max_trades: int = 60):
        self.max_trades = int(max_trades)

    def check(self, setup, state, ctx):
        if state.today_trades >= self.max_trades:
            return RiskDecision.deny(
                reason="max_trades_per_day",
                detail=f"already took {state.today_trades} today",
            )
        return RiskDecision.ok()


class CooldownGate(RiskGate):
    """Global cooldown between trade exits. Prevents the bot from
    re-entering on the same noise that just stopped it out."""
    name = "cooldown"

    def __init__(self, seconds: int = 60):
        self.cooldown_secs = int(seconds)

    def check(self, setup, state, ctx):
        last = state.last_trade_close_ts
        if last is None:
            return RiskDecision.ok()
        elapsed = (ctx.now - last).total_seconds()
        if elapsed < self.cooldown_secs:
            until = last + timedelta(seconds=self.cooldown_secs)
            return RiskDecision.deny(
                reason="cooldown",
                detail=f"{elapsed:.0f}s since last exit (need {self.cooldown_secs}s)",
                lockout_until=until,
            )
        return RiskDecision.ok()


class TradingWindowGate(RiskGate):
    """Allow trading only during configured ET windows. Per the regime
    analysis we ran on live trades, US RTH 07:00-13:00 ET destroys this
    strategy (-$2,156 over 4 days). Default disables that window.

    `windows` is a list of (start_hour, end_hour) tuples in ET. Empty
    list = no windows = no trading. Set to [(0, 24)] to disable filter.
    `disabled_windows` overrides allowed windows; if a time matches BOTH
    allowed and disabled, it's denied.
    """
    name = "trading_window"

    def __init__(self, allowed_windows=None, disabled_windows=None):
        self.allowed = list(allowed_windows or [(0, 24)])
        self.disabled = list(disabled_windows or [])

    def check(self, setup, state, ctx):
        h = ctx.et_hour
        for s, e in self.disabled:
            if s <= h < e:
                return RiskDecision.deny(
                    reason="trading_window_disabled",
                    detail=f"ET hour {h:02d}:00 is in disabled window {s}-{e}",
                )
        for s, e in self.allowed:
            if s <= h < e:
                return RiskDecision.ok()
        return RiskDecision.deny(
            reason="trading_window_closed",
            detail=f"ET hour {h:02d}:00 not in any allowed window",
        )


class NewsBlackoutGate(RiskGate):
    """Block ±N minutes around scheduled high-impact events. Uses the
    MarketContext.is_news_window flag, which is computed upstream by
    the runtime from an EconomicCalendar."""
    name = "news_blackout"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def check(self, setup, state, ctx):
        if self.enabled and ctx.is_news_window:
            return RiskDecision.deny(
                reason="news_blackout",
                detail="within scheduled news window",
            )
        return RiskDecision.ok()


class TrailDistanceSizerGate(RiskGate):
    """Doesn't deny -- adjusts size based on distance to trail floor.
    Returns suggested_qty so the runtime can override the default.
    `tiers` is a list of (min_distance_usd, qty) -- iterate from highest
    distance and pick the first matching tier."""
    name = "trail_distance_sizer"

    def __init__(self, tiers=None):
        # Default for Lucid 50K Pro (5 MNQ cap):
        # > $1500 buffer: 2 MNQ
        # $1000-1500:     1 MNQ
        # < $1000:        deny (handled by TrailFloorBufferGate)
        self.tiers = list(tiers or [(1500.0, 2), (1000.0, 1)])

    def check(self, setup, state, ctx):
        distance = state.balance - state.trail_floor
        for min_d, qty in sorted(self.tiers, reverse=True):
            if distance >= min_d:
                return RiskDecision.ok(suggested_qty=qty)
        return RiskDecision.deny(
            reason="trail_distance_zero_size",
            detail=f"distance ${distance:.0f} below all sizing tiers",
        )

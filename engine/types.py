"""Core data types. All immutable dataclasses; no behaviour.

The strategy returns Setups. The runtime turns Setups into LimitOrders.
The FillModel returns Fills. The runtime tracks ActiveTrades. When a
trade exits, the runtime emits a ClosedTrade.

Every dataclass here is JSON-serialisable so we can persist + replay.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG  = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


class ExitReason(str, Enum):
    STOP    = "stop"
    TARGET  = "target"
    TIMEOUT = "timeout"
    MANUAL  = "manual"      # user intervention / risk-engine flatten
    NEWS    = "news_flatten"


@dataclass(frozen=True)
class Setup:
    """A strategy's decision that a trade SHOULD be considered, pending
    fill. The strategy is responsible for producing this; the runtime
    decides if the limit order should actually be placed."""
    detected_at: datetime
    side: Side
    entry_price: float          # the LIMIT price the strategy wants to fill at
    stop_price: float
    target_price: float
    # Provenance for the audit log -- which bars triggered this signal.
    impulse_high: float
    impulse_low: float
    impulse_pts: float          # signed; same sign as side
    strategy_name: str
    # Free-form metadata for analytics. Will be serialised onto the trade.
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LimitOrder:
    """A LIMIT order ready to send to the broker (sim or real)."""
    side: Side
    price: float
    qty: int
    setup_id: str               # provenance back to the Setup
    submitted_at: datetime


@dataclass(frozen=True)
class StopOrder:
    """A protective STOP order for an open position. STOPS always fill,
    but with slippage modelled by the FillModel."""
    side: Side                  # side TO EXIT (LONG position -> SHORT stop)
    trigger_price: float
    qty: int


@dataclass(frozen=True)
class Fill:
    """A confirmed fill. Includes the broker's actual filled price (which
    may differ from the order's intended price due to slippage / queue)."""
    order_side: Side
    intended_price: float
    fill_price: float           # what we actually got
    qty: int
    ts: datetime                # timestamp of the fill
    latency_ms: float = 0.0     # how long from submit to ack
    slippage_pts: float = 0.0   # signed: positive = adverse


@dataclass
class ActiveTrade:
    """A trade currently open. Mutable because hold time + MAE/MFE evolve.
    The runtime owns this; the strategy is read-only on it."""
    setup: Setup
    entry_fill: Fill
    qty: int
    stop_price: float
    target_price: float
    opened_at: datetime
    # Live tracking; updated as new bars come in.
    mae_pts: float = 0.0        # max adverse excursion (positive number)
    mfe_pts: float = 0.0        # max favourable excursion (positive number)

    def hold_seconds(self, now: datetime) -> float:
        return (now - self.opened_at).total_seconds()

    def unrealized_pnl_pts(self, current_price: float) -> float:
        return (current_price - self.entry_fill.fill_price) * self.setup.side.sign

    def update_excursions(self, bar_high: float, bar_low: float) -> None:
        side = self.setup.side
        entry = self.entry_fill.fill_price
        # Adverse excursion = how far against us we went
        if side is Side.LONG:
            adverse = entry - bar_low
            favorable = bar_high - entry
        else:
            adverse = bar_high - entry
            favorable = entry - bar_low
        if adverse > self.mae_pts: self.mae_pts = adverse
        if favorable > self.mfe_pts: self.mfe_pts = favorable


@dataclass(frozen=True)
class ClosedTrade:
    """A completed round-trip trade. The unit of analysis for every
    statistic the dashboard / analytics layer cares about."""
    setup: Setup
    entry_fill: Fill
    exit_fill: Fill
    exit_reason: ExitReason
    qty: int
    opened_at: datetime
    closed_at: datetime
    mae_pts: float
    mfe_pts: float

    @property
    def hold_seconds(self) -> float:
        return (self.closed_at - self.opened_at).total_seconds()

    @property
    def pnl_pts(self) -> float:
        return (self.exit_fill.fill_price - self.entry_fill.fill_price) \
               * self.setup.side.sign

    def pnl_usd(self, dollars_per_pt: float, commission_rt: float) -> float:
        """qty MNQ * 2 USD/pt * pnl_pts - commissions."""
        gross = self.pnl_pts * dollars_per_pt * self.qty
        return gross - commission_rt * self.qty


# ---------------------------------------------------------------------------
# Risk engine output
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskDecision:
    """Output of a single risk gate or the risk engine as a whole."""
    allow: bool
    reason: Optional[str] = None       # short tag e.g. "daily_loss_limit"
    detail: Optional[str] = None       # human-readable
    lockout_until: Optional[datetime] = None
    suggested_qty: Optional[int] = None  # if allowed but want to override size

    @classmethod
    def ok(cls, suggested_qty: Optional[int] = None) -> "RiskDecision":
        return cls(allow=True, suggested_qty=suggested_qty)

    @classmethod
    def deny(cls, reason: str, detail: str = "",
             lockout_until: Optional[datetime] = None) -> "RiskDecision":
        return cls(allow=False, reason=reason, detail=detail,
                   lockout_until=lockout_until)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def setup_to_orders(setup: Setup, qty: int, now: datetime) -> tuple[LimitOrder, StopOrder, LimitOrder]:
    """Convert a Setup + size into the three orders the broker will hold:
    entry limit + protective stop + take-profit limit. The exit orders
    aren't activated until the entry fills."""
    setup_id = f"{setup.strategy_name}-{int(setup.detected_at.timestamp())}-{setup.side.value}"
    entry = LimitOrder(side=setup.side, price=setup.entry_price,
                       qty=qty, setup_id=setup_id, submitted_at=now)
    exit_side = Side.SHORT if setup.side is Side.LONG else Side.LONG
    stop = StopOrder(side=exit_side, trigger_price=setup.stop_price, qty=qty)
    target = LimitOrder(side=exit_side, price=setup.target_price,
                        qty=qty, setup_id=setup_id, submitted_at=now)
    return entry, stop, target

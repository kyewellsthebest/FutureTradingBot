"""RiskEngine: chains gates and produces a single allow/deny decision.

USAGE:
    risk = RiskEngine([
        ActiveLockoutGate(),
        DailyLossLimitGate(limit_usd=700),
        TrailFloorBufferGate(min_buffer_usd=800),
        ConsecutiveLossesGate(max_losses=4, pause_minutes=60),
        TradingWindowGate(disabled_windows=[(7, 13)]),
        NewsBlackoutGate(),
        CooldownGate(seconds=60),
        TrailDistanceSizerGate(),   # SIZER -- must be last
    ])
    decision = risk.evaluate(setup, account_state, market_ctx)
    if decision.allow:
        runtime.submit_entry(setup, qty=decision.suggested_qty or default_qty)
    else:
        log_denial(decision.reason, decision.detail)
"""
from __future__ import annotations

from typing import Iterable, Optional

from engine.market_context import MarketContext
from engine.risk.gates import AccountState, RiskGate
from engine.types import RiskDecision, Setup


class RiskEngine:
    """Chains gates. First denial wins. Sizer gates run last and only
    take effect if every prior gate allowed."""

    def __init__(self, gates: Iterable[RiskGate]):
        self.gates = list(gates)
        # Stats for analytics: per-gate denial counter.
        self.denial_counts: dict = {}

    def evaluate(self, setup: Setup, state: AccountState,
                  ctx: MarketContext) -> RiskDecision:
        suggested_qty: Optional[int] = None
        for gate in self.gates:
            d = gate.check(setup, state, ctx)
            if not d.allow:
                self.denial_counts[d.reason or gate.name] = \
                    self.denial_counts.get(d.reason or gate.name, 0) + 1
                return d
            if d.suggested_qty is not None:
                suggested_qty = d.suggested_qty
        return RiskDecision.ok(suggested_qty=suggested_qty)

"""FillModel interface. Concrete implementations:
  - SimFillModel: backtest -- models latency, queue, slippage from bars
  - TradovateFillModel: live -- wraps the Tradovate REST API
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

from engine.market_context import MarketContext
from engine.types import Fill, LimitOrder, StopOrder


class FillModel(ABC):
    """Abstract broker. Decides if/how/when orders fill."""

    @abstractmethod
    def check_limit_fill(self, order: LimitOrder, bar: pd.Series,
                          ctx: MarketContext) -> Optional[Fill]:
        """Called once per bar AFTER the order is submitted. Returns a
        Fill if this bar caused the order to fill, else None.

        Semantics matter: this is a "did this bar trigger a fill" check,
        not a "is the order still alive" check. The runtime tracks the
        order lifetime separately. Implementations can use the bar's
        OHLC + ctx to model:
          - touched-not-filled probability
          - queue position
          - slippage from the limit price
        """

    @abstractmethod
    def fill_stop(self, order: StopOrder, bar: pd.Series,
                   ctx: MarketContext) -> Optional[Fill]:
        """Stops always fill once triggered. Returns the Fill with
        slippage applied. Returns None if THIS bar didn't trigger the
        stop (high/low didn't reach trigger_price)."""

    @abstractmethod
    def fill_market(self, side, qty: int, bar: pd.Series,
                     ctx: MarketContext) -> Fill:
        """Market orders -- used by the risk engine for emergency
        flatten. Fill at the bar's close with a market-style slip."""

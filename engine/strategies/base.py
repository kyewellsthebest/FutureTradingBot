"""Strategy interface. Strategies are pure functions; the runtime calls
them and threads state. Strategies MUST NOT:
  - hold mutable state between calls (use the runtime's state for that)
  - read from disk / network / clock (use the bars + `now` argument)
  - mutate their input (bars is read-only)

This is the contract that makes backtest = live possible.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

from engine.types import Setup


class Strategy(ABC):
    """Pure-function strategy interface."""

    name: str = "base"

    @abstractmethod
    def detect_setup(self, bars: pd.DataFrame, now: datetime,
                      params: dict) -> Optional[Setup]:
        """Look at the bar history and return a Setup if one fires THIS bar,
        else None. Implementations may NOT look at bars beyond the last
        index -- enforced by the runtime feeding only bars[0:current+1]."""
        ...

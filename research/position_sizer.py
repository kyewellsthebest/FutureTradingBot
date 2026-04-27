"""
Kelly-fraction position sizer with regime / VPIN / adverse / macro multipliers.

Returns a `Sizing` with:
  contracts : MNQ contracts to use (0 = skip)
  reason    : human-readable trace

Per-signal historical edge is read from data/validation_results.json — we use
profit_factor and win_rate to compute a Kelly fraction, then apply caps and
multipliers.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from research.data_loader import DATA_DIR

logger = logging.getLogger("sizer")

VALIDATION_PATH = DATA_DIR / "validation_results.json"

BASE_CONTRACTS = 30
MIN_CONTRACTS = 1
MAX_CONTRACTS = 60
KELLY_CAP = 0.25       # never bet more than 25% of Kelly fraction
DOLLAR_PER_POINT_MNQ = 2.0   # 1 MNQ = $2 per point


@dataclass
class Sizing:
    contracts: int
    reason: str
    kelly_fraction: float
    multiplier: float


_validation_cache: dict | None = None


def _load_validation() -> dict:
    global _validation_cache
    if _validation_cache is not None:
        return _validation_cache
    if not VALIDATION_PATH.exists():
        _validation_cache = {}
        return _validation_cache
    try:
        _validation_cache = json.loads(VALIDATION_PATH.read_text()).get("signals", {})
    except Exception:
        _validation_cache = {}
    return _validation_cache


def _kelly(win_rate: float, profit_factor: float) -> float:
    """Approximate Kelly: f* = W - (1-W)/R where R = avg_win/avg_loss."""
    if win_rate <= 0 or win_rate >= 1 or profit_factor <= 0:
        return 0.0
    # Derive R from profit_factor: PF = (W*R)/(1-W)  =>  R = PF*(1-W)/W
    r = profit_factor * (1 - win_rate) / win_rate
    if r <= 0:
        return 0.0
    f = win_rate - (1 - win_rate) / r
    return max(0.0, min(1.0, f))


def size_position(*,
                  signal_name: str,
                  stop_pts: float,
                  ml_confidence: float,
                  regime_mult: float = 1.0,
                  vpin_mult: float = 1.0,
                  adverse_selection_mult: float = 1.0,
                  macro_mult: float = 1.0) -> Sizing:
    info = _load_validation().get(signal_name, {})
    wr = float(info.get("win_rate", 0.4))
    pf = float(info.get("profit_factor", 1.5))
    f = _kelly(wr, pf) * KELLY_CAP

    # ML confidence scales 0.6..1.2 around 0.5 (neutral)
    ml_scale = max(0.5, min(1.5, 0.4 + 1.6 * (ml_confidence - 0.5) + 1.0))
    multiplier = float(regime_mult * vpin_mult * adverse_selection_mult * macro_mult * ml_scale)

    raw = BASE_CONTRACTS * (1.0 + 4.0 * f) * multiplier
    contracts = int(round(max(0.0, raw)))
    if contracts > MAX_CONTRACTS:
        contracts = MAX_CONTRACTS
    if 0 < contracts < MIN_CONTRACTS:
        contracts = MIN_CONTRACTS
    if multiplier <= 0.0:
        contracts = 0
    reason = (f"kelly={f:.3f} mult={multiplier:.2f} ml={ml_confidence:.2f}")
    return Sizing(contracts=contracts, reason=reason, kelly_fraction=float(f),
                  multiplier=multiplier)

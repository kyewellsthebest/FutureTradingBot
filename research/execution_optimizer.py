"""
Execution helpers: signal half-life check + slippage estimator.

`signal_half_life_ok` confirms the signal hasn't decayed (price hasn't moved
more than half the stop already). Used to skip stale entries.
"""
from __future__ import annotations

import pandas as pd


def signal_half_life_ok(intraday: pd.DataFrame,
                        signal_time: pd.Timestamp,
                        side: str,
                        entry_px: float,
                        stop_pts: float,
                        max_decay_frac: float = 0.5) -> tuple[bool, str]:
    if intraday.empty:
        return True, "no-data"
    try:
        idx = intraday.index.get_indexer([signal_time], method="nearest")[0]
    except Exception:
        return True, "ts-not-found"
    last_idx = len(intraday) - 1
    if last_idx <= idx:
        return True, "fresh"
    last_close = float(intraday["close"].iloc[-1])
    if side == "LONG":
        decay = (entry_px - last_close)
    else:
        decay = (last_close - entry_px)
    frac = decay / max(stop_pts, 1e-9)
    if frac > max_decay_frac:
        return False, f"decayed {frac:.2f} stops"
    return True, f"decay {frac:+.2f}"


def estimate_slippage(volume_ratio: float, contracts: int = 30) -> float:
    """Rough slippage in points: bigger size & thinner book = more slippage."""
    base = 1.5
    size_pen = 0.5 * (contracts / 30 - 1)
    liq_pen = max(0.0, 1.0 - (volume_ratio or 1.0)) * 1.5
    return float(max(0.5, base + size_pen + liq_pen))

"""
Filter strictness configuration.

Three modes — pick one with env var HFT_FILTER_MODE:

  STRICT     (default) — original 13-filter veto chain, max 2 trades/day.
                          Survives walk-forward; very few trades.
  MODERATE              — converts kill-zone to a sizing penalty, allows up to 5
                          trades/day, 30-minute gap. ~3-5 trades/day expected.
  AGGRESSIVE            — kill-zone is sizing only, daily bias only halves size,
                          up to 12 trades/day, 15-min gap. ~8-15 trades/day.

You can also override individual fields via env vars:
  HFT_MAX_TRADES_PER_DAY=10
  HFT_MIN_GAP_MIN=20
  HFT_MIN_GAP_AFTER_WIN_MIN=45
  HFT_KILLZONE_AS_VETO=0
  HFT_DAILY_BIAS_AS_VETO=0
  HFT_PROXIMITY_AS_VETO=0

This is the single knob that turns the bot from "trades twice a day" into
"trades 10+ times a day." It does not change validation thresholds, only
runtime gating, so signals that survived backtest are still the only ones
that fire — the bot just stops vetoing them on time-of-day or arbitrary
spacing rules.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["STRICT", "MODERATE", "AGGRESSIVE"]


@dataclass
class FilterConfig:
    mode: Mode = "STRICT"
    # Cooldown
    max_trades_per_day: int = 2
    min_gap_between_min: int = 90
    min_gap_after_winner_min: int = 120
    # Veto vs sizing toggles — when False, the filter only adjusts size_mult
    killzone_as_veto: bool = True
    daily_bias_as_veto: bool = True
    proximity_as_veto: bool = True
    # Sizing penalties when a filter is "soft" (only used when *_as_veto is False)
    killzone_soft_size_mult: float = 0.5
    daily_bias_soft_size_mult: float = 0.5
    proximity_soft_size_mult: float = 0.7
    # Min R:R floor (per-signal overrides still apply)
    default_min_rr: float = 2.0


def _bool_env(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def load_config() -> FilterConfig:
    """Build config from HFT_FILTER_MODE + optional individual overrides."""
    mode = (os.environ.get("HFT_FILTER_MODE") or "STRICT").upper().strip()
    if mode not in ("STRICT", "MODERATE", "AGGRESSIVE"):
        mode = "STRICT"

    if mode == "STRICT":
        cfg = FilterConfig(mode="STRICT")
    elif mode == "MODERATE":
        cfg = FilterConfig(
            mode="MODERATE",
            max_trades_per_day=5,
            min_gap_between_min=30,
            min_gap_after_winner_min=60,
            killzone_as_veto=False,
            daily_bias_as_veto=True,
            proximity_as_veto=True,
            default_min_rr=1.8,
        )
    else:  # AGGRESSIVE
        cfg = FilterConfig(
            mode="AGGRESSIVE",
            max_trades_per_day=12,
            min_gap_between_min=15,
            min_gap_after_winner_min=30,
            killzone_as_veto=False,
            daily_bias_as_veto=False,
            proximity_as_veto=False,
            default_min_rr=1.3,
        )

    # Per-field overrides
    cfg.max_trades_per_day = _int_env("HFT_MAX_TRADES_PER_DAY", cfg.max_trades_per_day)
    cfg.min_gap_between_min = _int_env("HFT_MIN_GAP_MIN", cfg.min_gap_between_min)
    cfg.min_gap_after_winner_min = _int_env("HFT_MIN_GAP_AFTER_WIN_MIN", cfg.min_gap_after_winner_min)
    cfg.killzone_as_veto = _bool_env("HFT_KILLZONE_AS_VETO", cfg.killzone_as_veto)
    cfg.daily_bias_as_veto = _bool_env("HFT_DAILY_BIAS_AS_VETO", cfg.daily_bias_as_veto)
    cfg.proximity_as_veto = _bool_env("HFT_PROXIMITY_AS_VETO", cfg.proximity_as_veto)
    cfg.default_min_rr = _float_env("HFT_DEFAULT_MIN_RR", cfg.default_min_rr)
    return cfg


# Module-level singleton, loaded once at import time
CONFIG: FilterConfig = load_config()


def reload() -> FilterConfig:
    """Re-read env vars (useful in tests)."""
    global CONFIG
    CONFIG = load_config()
    return CONFIG


def describe(cfg: FilterConfig | None = None) -> str:
    cfg = cfg or CONFIG
    return (
        f"mode={cfg.mode}  max/day={cfg.max_trades_per_day}  "
        f"gap={cfg.min_gap_between_min}m / {cfg.min_gap_after_winner_min}m after-win  "
        f"killzone-veto={cfg.killzone_as_veto}  bias-veto={cfg.daily_bias_as_veto}  "
        f"prox-veto={cfg.proximity_as_veto}  min-rr={cfg.default_min_rr}"
    )

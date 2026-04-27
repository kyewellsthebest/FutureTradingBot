"""
Filter strictness configuration.

Modes — pick with env var HFT_FILTER_MODE:

  LEAN       (default) — ablation-tuned mode. Drops 3 filters that proved
                          NEGATIVE in 2-yr ablation study (bias, cooldown,
                          vol_regime). Keeps 3 that proved positive
                          (proximity, R:R, killzone). ~2-3 trades/day,
                          +$245k/2yr projection vs old STRICT's +$145k.
  STRICT                — original 13-filter veto chain (kept for comparison).
  MODERATE              — kill-zone soft, max 5/day. ~3-5 trades/day.
  AGGRESSIVE            — proximity off, no R:R floor. WARNING: ablation
                          showed this LOSES money (-$1.2M/2yr).

Per-field overrides via env:
  HFT_MAX_TRADES_PER_DAY=10
  HFT_MIN_GAP_MIN=20
  HFT_MIN_GAP_AFTER_WIN_MIN=45
  HFT_KILLZONE_AS_VETO=0
  HFT_DAILY_BIAS_AS_VETO=0
  HFT_PROXIMITY_AS_VETO=0
  HFT_COOLDOWN_DISABLED=1
  HFT_VOL_REGIME_DISABLED=1
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["LEAN", "STRICT", "MODERATE", "AGGRESSIVE"]


@dataclass
class FilterConfig:
    mode: Mode = "LEAN"
    # Cooldown
    max_trades_per_day: int = 12
    min_gap_between_min: int = 5
    min_gap_after_winner_min: int = 10
    cooldown_disabled: bool = True   # LEAN: cooldown off (ablation: +$47k)
    # Veto vs sizing toggles — when False, the filter only adjusts size_mult
    killzone_as_veto: bool = True
    daily_bias_as_veto: bool = False  # LEAN: bias off (ablation: +$7k)
    proximity_as_veto: bool = True
    # Vol regime
    vol_regime_enabled: bool = False  # LEAN: vol regime off (ablation: +$50k)
    fixed_stop_pts: float = 15.0      # used when vol_regime_enabled = False
    # Sizing penalties when a filter is "soft"
    killzone_soft_size_mult: float = 0.5
    daily_bias_soft_size_mult: float = 0.5
    proximity_soft_size_mult: float = 0.7
    # Min R:R floor
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
    mode = (os.environ.get("HFT_FILTER_MODE") or "LEAN").upper().strip()
    if mode not in ("LEAN", "STRICT", "MODERATE", "AGGRESSIVE"):
        mode = "LEAN"

    if mode == "LEAN":
        # Ablation-tuned: drop bias + cooldown + vol_regime
        cfg = FilterConfig(
            mode="LEAN",
            max_trades_per_day=12,
            min_gap_between_min=5,
            min_gap_after_winner_min=10,
            cooldown_disabled=True,
            killzone_as_veto=True,
            daily_bias_as_veto=False,
            proximity_as_veto=True,
            vol_regime_enabled=False,
            fixed_stop_pts=15.0,
            default_min_rr=2.0,
        )
    elif mode == "STRICT":
        cfg = FilterConfig(
            mode="STRICT",
            max_trades_per_day=2,
            min_gap_between_min=90,
            min_gap_after_winner_min=120,
            cooldown_disabled=False,
            killzone_as_veto=True,
            daily_bias_as_veto=True,
            proximity_as_veto=True,
            vol_regime_enabled=True,
            default_min_rr=2.0,
        )
    elif mode == "MODERATE":
        cfg = FilterConfig(
            mode="MODERATE",
            max_trades_per_day=5,
            min_gap_between_min=30,
            min_gap_after_winner_min=60,
            cooldown_disabled=False,
            killzone_as_veto=False,
            daily_bias_as_veto=True,
            proximity_as_veto=True,
            vol_regime_enabled=True,
            default_min_rr=1.8,
        )
    else:  # AGGRESSIVE
        cfg = FilterConfig(
            mode="AGGRESSIVE",
            max_trades_per_day=12,
            min_gap_between_min=15,
            min_gap_after_winner_min=30,
            cooldown_disabled=False,
            killzone_as_veto=False,
            daily_bias_as_veto=False,
            proximity_as_veto=False,
            vol_regime_enabled=True,
            default_min_rr=1.3,
        )

    # Per-field overrides
    cfg.max_trades_per_day = _int_env("HFT_MAX_TRADES_PER_DAY", cfg.max_trades_per_day)
    cfg.min_gap_between_min = _int_env("HFT_MIN_GAP_MIN", cfg.min_gap_between_min)
    cfg.min_gap_after_winner_min = _int_env("HFT_MIN_GAP_AFTER_WIN_MIN", cfg.min_gap_after_winner_min)
    cfg.cooldown_disabled = _bool_env("HFT_COOLDOWN_DISABLED", cfg.cooldown_disabled)
    cfg.killzone_as_veto = _bool_env("HFT_KILLZONE_AS_VETO", cfg.killzone_as_veto)
    cfg.daily_bias_as_veto = _bool_env("HFT_DAILY_BIAS_AS_VETO", cfg.daily_bias_as_veto)
    cfg.proximity_as_veto = _bool_env("HFT_PROXIMITY_AS_VETO", cfg.proximity_as_veto)
    cfg.vol_regime_enabled = _bool_env("HFT_VOL_REGIME_ENABLED", cfg.vol_regime_enabled)
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
        f"gap={cfg.min_gap_between_min}m/{cfg.min_gap_after_winner_min}m "
        f"cooldown={'OFF' if cfg.cooldown_disabled else 'ON'}  "
        f"bias-veto={cfg.daily_bias_as_veto}  killzone-veto={cfg.killzone_as_veto}  "
        f"prox-veto={cfg.proximity_as_veto}  vol-regime={'ON' if cfg.vol_regime_enabled else 'OFF'}  "
        f"min-rr={cfg.default_min_rr}"
    )


def filter_status(cfg: FilterConfig | None = None) -> dict:
    """Return a structured snapshot for the dashboard."""
    cfg = cfg or CONFIG
    return {
        "mode": cfg.mode,
        "filters": {
            "proximity":  {"enabled": True, "as_veto": cfg.proximity_as_veto,
                            "ablation": "CRITICAL — disabling costs $395k"},
            "min_rr":     {"enabled": True, "min": cfg.default_min_rr,
                            "ablation": "CRITICAL — disabling costs $415k"},
            "killzone":   {"enabled": True, "as_veto": cfg.killzone_as_veto,
                            "ablation": "marginal help — disabling costs $11k"},
            "daily_bias": {"enabled": cfg.daily_bias_as_veto,
                            "ablation": "DROP — keeping it costs $7k"},
            "cooldown":   {"enabled": not cfg.cooldown_disabled,
                            "max_per_day": cfg.max_trades_per_day,
                            "gap_min": cfg.min_gap_between_min,
                            "ablation": "DROP — keeping it costs $47k"},
            "vol_regime": {"enabled": cfg.vol_regime_enabled,
                            "ablation": "DROP — keeping it costs $50k"},
        },
    }


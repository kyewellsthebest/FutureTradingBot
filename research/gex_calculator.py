"""
Dealer-gamma exposure (GEX) for the QQQ option chain → NQ proxy.

  gamma_per_contract = BlackScholes_gamma(spot, strike, T, r, σ)
  total_gex = Σ_strike (gamma * OI * 100 * spot² * sign)
              where sign = +1 for calls, -1 for puts

Maps to NQ via the empirical ratio NQ_price / QQQ_price (typically ≈ 41×).

Regimes (per spec):
  total_gex > +$0.5B  POSITIVE  size ×0.5 SHORTS, ×1.0 LONGS
  total_gex < -$0.5B  NEGATIVE  size ×0.5 LONGS,  ×1.0 SHORTS
  in range            NEUTRAL   ×1.0

Defenses:
  - Cache rejected if |total_gex| < 1e9 (likely a partial/bad fetch)
  - Bad fetches keep the previous valid cache instead of overwriting
  - Sub-20-strikes or sub-$1B total → invalid, fall back to last good
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from research.data_loader import DATA_DIR

GEXRegime = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]

CACHE_PATH = DATA_DIR / "gex_cache.json"
HISTORY_PATH = DATA_DIR / "gex_history.json"
CACHE_TTL_SECONDS = 15 * 60

NQ_PER_QQQ = 41.0   # spot ratio (NQ / QQQ)
MIN_VALID_GEX = 1e9
MIN_VALID_STRIKES = 20


@dataclass
class GEXSnapshot:
    as_of: str
    regime: GEXRegime
    total_gex: float                      # in QQQ-equivalent dollars
    intensity_percentile: float           # 0..100
    zero_gamma_qqq: float
    zero_gamma_nq: float
    magnets_qqq: list[float] = field(default_factory=list)
    magnets_nq: list[float] = field(default_factory=list)


def _bs_gamma(spot: float, strike: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    return pdf / (spot * sigma * math.sqrt(T))


def _load_history() -> list[float]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return [float(x) for x in json.loads(HISTORY_PATH.read_text())]
    except Exception:
        return []


def _save_history(values: list[float]) -> None:
    HISTORY_PATH.write_text(json.dumps(values[-365:]))


def _percentile(values: list[float], x: float) -> float:
    if not values:
        return 50.0
    arr = np.array(values, dtype=float)
    return float((arr <= abs(x)).mean() * 100.0)


def compute_gex(spot_qqq: float | None = None) -> GEXSnapshot | None:
    """Best-effort GEX from QQQ chain via yfinance. Returns None if unavailable."""
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        tk = yf.Ticker("QQQ")
        if spot_qqq is None:
            info = getattr(tk, "fast_info", None)
            spot_qqq = float(info["last_price"]) if info and "last_price" in info else 0.0
        expirations = tk.options[:3]
    except Exception:
        return None
    if not expirations or not spot_qqq:
        return None

    total_gex = 0.0
    strikes_seen: dict[float, float] = {}
    now = datetime.now(timezone.utc)
    for exp in expirations:
        try:
            chain = tk.option_chain(exp)
        except Exception:
            continue
        try:
            T = max((datetime.fromisoformat(exp).replace(tzinfo=timezone.utc) - now).days, 1) / 365.0
        except Exception:
            T = 30.0 / 365.0
        for sign, df in (("call", chain.calls), ("put", chain.puts)):
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                strike = float(row.get("strike", 0))
                oi = float(row.get("openInterest", 0) or 0)
                iv = float(row.get("impliedVolatility", 0.20) or 0.20)
                if strike <= 0 or oi <= 0 or iv <= 0:
                    continue
                g = _bs_gamma(spot_qqq, strike, T, 0.05, iv)
                contrib = g * oi * 100 * spot_qqq * spot_qqq * (1 if sign == "call" else -1)
                total_gex += contrib
                strikes_seen[strike] = strikes_seen.get(strike, 0.0) + abs(contrib)

    if len(strikes_seen) < MIN_VALID_STRIKES or abs(total_gex) < MIN_VALID_GEX:
        return None  # bad fetch

    # Magnet strikes = top 3 by absolute contribution
    magnets_qqq = sorted(strikes_seen, key=strikes_seen.get, reverse=True)[:3]
    zero_gamma_qqq = float(np.mean(magnets_qqq)) if magnets_qqq else spot_qqq

    if total_gex > 0.5e9:
        regime: GEXRegime = "POSITIVE"
    elif total_gex < -0.5e9:
        regime = "NEGATIVE"
    else:
        regime = "NEUTRAL"

    history = _load_history()
    history.append(abs(total_gex))
    _save_history(history)
    pct = _percentile(history[:-1], total_gex)

    snap = GEXSnapshot(
        as_of=now.isoformat(),
        regime=regime,
        total_gex=float(total_gex),
        intensity_percentile=pct,
        zero_gamma_qqq=zero_gamma_qqq,
        zero_gamma_nq=zero_gamma_qqq * NQ_PER_QQQ,
        magnets_qqq=magnets_qqq,
        magnets_nq=[k * NQ_PER_QQQ for k in magnets_qqq],
    )
    CACHE_PATH.write_text(json.dumps(snap.__dict__))
    return snap


def load_cached_snapshot() -> GEXSnapshot | None:
    if not CACHE_PATH.exists():
        return None
    try:
        d = json.loads(CACHE_PATH.read_text())
        return GEXSnapshot(**d)
    except Exception:
        return None


def gex_filter(snap: GEXSnapshot | None, side: str) -> tuple[bool, str, float]:
    if snap is None:
        return True, "gex=unavailable", 1.0
    if snap.regime == "POSITIVE":
        if side == "SHORT":
            return True, f"gex POSITIVE +${snap.total_gex/1e9:.1f}B SHORT ×0.5", 0.5
        return True, f"gex POSITIVE +${snap.total_gex/1e9:.1f}B LONG ×1.0", 1.0
    if snap.regime == "NEGATIVE":
        if side == "LONG":
            return True, f"gex NEGATIVE ${snap.total_gex/1e9:.1f}B LONG ×0.5", 0.5
        return True, f"gex NEGATIVE ${snap.total_gex/1e9:.1f}B SHORT ×1.0", 1.0
    return True, f"gex NEUTRAL ${snap.total_gex/1e9:.1f}B ×1.0", 1.0

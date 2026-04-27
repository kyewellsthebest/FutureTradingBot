"""
Dealer-gamma exposure (GEX) for QQQ -> NQ proxy.

Real implementation needs an options-chain feed (CBOE bulk, Polygon, Tradier).
We pull the QQQ chain via yfinance when available, compute aggregate GEX, and
cache to data/cache/gex_snapshot.json. If options data is unavailable, return
None — the system handles that gracefully via macro_filter / gex_filter.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from research.data_loader import DATA_DIR

logger = logging.getLogger("gex")

CACHE_PATH = DATA_DIR / "cache" / "gex_snapshot.json"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour
QQQ_TO_NQ = 41.0  # rough proxy multiplier


@dataclass
class GEXSnapshot:
    as_of: str
    regime: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
    total_gex: float                # in dollars
    intensity_percentile: float     # 0..100 across recent history
    zero_gamma_qqq: float
    zero_gamma_nq: float
    magnets_qqq: list[float] = field(default_factory=list)
    magnets_nq: list[float] = field(default_factory=list)


def load_cached_snapshot() -> GEXSnapshot | None:
    if not CACHE_PATH.exists():
        return None
    try:
        d = json.loads(CACHE_PATH.read_text())
        ts = datetime.fromisoformat(d["as_of"])
        if (datetime.now(timezone.utc) - ts).total_seconds() > CACHE_TTL_SECONDS:
            return None
        return GEXSnapshot(**d)
    except Exception:
        return None


def _save(snap: GEXSnapshot) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(snap.__dict__))


def compute_gex(symbol: str = "QQQ") -> GEXSnapshot | None:
    """Best-effort QQQ chain GEX. Returns None when options data unavailable."""
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        tk = yf.Ticker(symbol)
        spot = float(tk.history(period="1d")["Close"].iloc[-1])
        expiries = tk.options or []
    except Exception as e:
        logger.info("[gex] chain fetch failed: %s", e)
        return None
    if not expiries:
        return None
    total_gex = 0.0
    by_strike: dict[float, float] = {}
    for exp in expiries[:4]:
        try:
            chain = tk.option_chain(exp)
        except Exception:
            continue
        for side, sign in (("calls", 1), ("puts", -1)):
            df = getattr(chain, side, None)
            if df is None or df.empty:
                continue
            iv = df["impliedVolatility"].fillna(0.2).clip(0.05, 2.0)
            oi = df["openInterest"].fillna(0)
            strike = df["strike"].astype(float)
            # Approx gamma per option ~ N'(d1)/(spot*iv*sqrt(T))
            gamma_proxy = 1.0 / (spot * iv.clip(0.05) * np.sqrt(0.05))
            contrib = sign * gamma_proxy * oi * 100 * spot * spot * 0.01
            for s, c in zip(strike, contrib):
                by_strike[float(s)] = by_strike.get(float(s), 0.0) + float(c)
            total_gex += float(contrib.sum())
    if not by_strike:
        return None
    cumul = 0.0
    pos_gex = sum(v for v in by_strike.values() if v > 0)
    cumul = 0.0
    zero_gamma = spot
    items = sorted(by_strike.items())
    running = 0.0
    for s, v in items:
        running += v
        if running >= 0 and zero_gamma == spot:
            zero_gamma = s
            break
    magnets = sorted(by_strike.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
    magnets_qqq = [m[0] for m in magnets]
    if total_gex > 0:
        regime = "POSITIVE"
    elif total_gex < 0:
        regime = "NEGATIVE"
    else:
        regime = "NEUTRAL"
    intensity = min(100.0, abs(total_gex) / 5e9 * 100.0)
    snap = GEXSnapshot(
        as_of=datetime.now(timezone.utc).isoformat(),
        regime=regime, total_gex=float(total_gex),
        intensity_percentile=float(intensity),
        zero_gamma_qqq=float(zero_gamma),
        zero_gamma_nq=float(zero_gamma * QQQ_TO_NQ),
        magnets_qqq=magnets_qqq,
        magnets_nq=[round(m * QQQ_TO_NQ, 1) for m in magnets_qqq],
    )
    _save(snap)
    return snap


def gex_filter(snap: GEXSnapshot | None, side: str) -> tuple[bool, str, float]:
    if snap is None:
        return True, "gex=unavailable", 1.0
    if snap.regime == "POSITIVE" and snap.intensity_percentile >= 90:
        # Extreme positive gex pins price — fade size on directional plays
        return True, f"gex=POS extreme ({snap.intensity_percentile:.0f}%)", 0.7
    if snap.regime == "NEGATIVE" and snap.intensity_percentile >= 75:
        return True, f"gex=NEG ({snap.intensity_percentile:.0f}%) size×1.1", 1.1
    return True, f"gex={snap.regime} ({snap.intensity_percentile:.0f}%)", 1.0

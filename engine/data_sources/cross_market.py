"""Cross-market state -- VIX, ES, SPY, DXY. Used by the macro-alignment
sizer to cut size when NQ wants up but the broader market is risk-off.

Data sources (in fallback order):
  1. Polygon (already paid for) -- best quality for ES, VIX, futures
  2. Existing data_loader.download_nq pattern for ES (Polygon futures)
  3. yfinance fallback for VIX / DXY / SPY when polygon doesn't have them

We cache aggressively (1 minute) because none of this needs sub-minute
resolution for the 1-min strategy.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger("cross_market")

# 5 min cache. Pre-fix this was 60s -- 5 instruments × 1 fetch/min = 5
# yfinance calls/min, which leaks memory through curl_cffi sessions and
# contributed to the OOM crash. VIX/SPY/DXY don't change so fast that
# we need sub-5min freshness for the macro alignment sizer.
CACHE_TTL_SEC = 300


@dataclass
class CrossMarketState:
    """Snapshot of macro context. None = data unavailable, don't penalise
    the signal."""
    vix: Optional[float] = None
    vix_change_5m_pct: Optional[float] = None
    es_last: Optional[float] = None
    es_change_5m_pct: Optional[float] = None
    spy_last: Optional[float] = None
    spy_change_5m_pct: Optional[float] = None
    dxy_last: Optional[float] = None
    dxy_change_60m_pct: Optional[float] = None
    nq_es_spread_5m_pct: Optional[float] = None    # NQ % - ES %, positive = NQ leading
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "vix":                  self.vix,
            "vix_change_5m_pct":    self.vix_change_5m_pct,
            "es_last":              self.es_last,
            "es_change_5m_pct":     self.es_change_5m_pct,
            "spy_last":             self.spy_last,
            "spy_change_5m_pct":    self.spy_change_5m_pct,
            "dxy_last":             self.dxy_last,
            "dxy_change_60m_pct":   self.dxy_change_60m_pct,
            "nq_es_spread_5m_pct":  self.nq_es_spread_5m_pct,
            "ts":                   self.ts.isoformat(),
        }

    def alignment_score(self, side: str) -> float:
        """Returns -1.0 .. +1.0. Positive = aligned with `side` (bullish for
        LONG, bearish for SHORT). Negative = macro disagrees with the
        signal. Magnitude = strength of (dis)agreement.

        Components (each weighted 0.0-1.0 of the total):
            VIX direction (40%):    rising VIX = bearish stocks
            ES alignment (30%):     ES move agrees with NQ side?
            NQ-ES spread (15%):     NQ leading or lagging ES?
            DXY direction (15%):    rising USD = headwind for stocks/NQ

        None values are silently treated as zero contribution.
        """
        signed = 1.0 if side == "LONG" else -1.0
        score = 0.0
        used_weight = 0.0

        # VIX: rising VIX is bearish; falling VIX is bullish. Cap at 5%.
        if self.vix_change_5m_pct is not None:
            v = max(-5.0, min(5.0, self.vix_change_5m_pct)) / 5.0  # -1..+1
            # Bearish for stocks when VIX up, so component for LONG is -v.
            score += signed * -v * 0.40
            used_weight += 0.40

        # ES move alignment. Convert to -1..+1 scaled at 0.5%.
        if self.es_change_5m_pct is not None:
            e = max(-0.5, min(0.5, self.es_change_5m_pct)) / 0.5
            score += signed * e * 0.30
            used_weight += 0.30

        # NQ-ES spread: positive spread = NQ leading. Bullish for NQ regardless.
        # Capped at 0.3% spread.
        if self.nq_es_spread_5m_pct is not None:
            s = max(-0.3, min(0.3, self.nq_es_spread_5m_pct)) / 0.3
            # If NQ is leading down (negative spread), that's bearish for NQ
            # regardless of which side we want -- it's just a "NQ is weaker"
            # signal. Multiply by the signed direction.
            score += signed * s * 0.15
            used_weight += 0.15

        # DXY: rising dollar = bearish stocks. Cap at 1% / hr.
        if self.dxy_change_60m_pct is not None:
            d = max(-1.0, min(1.0, self.dxy_change_60m_pct)) / 1.0
            score += signed * -d * 0.15
            used_weight += 0.15

        if used_weight == 0:
            return 0.0
        return score / used_weight   # Normalise to -1..+1 regardless of missing data


class CrossMarketFeed:
    """Lazy fetcher with TTL cache. Failures are non-fatal -- returns the
    last-good cache or empty state."""

    def __init__(self):
        self._cache = CrossMarketState()
        self._last_refresh = 0.0
        self._fetch_errors = 0

    def refresh(self, *, force: bool = False) -> bool:
        now = time.time()
        if not force and (now - self._last_refresh) < CACHE_TTL_SEC:
            return True
        try:
            new = self._fetch_all()
            self._cache = new
            self._last_refresh = now
            return True
        except Exception as e:
            self._fetch_errors += 1
            logger.warning(f"cross-market fetch failed (non-fatal): {e!r}")
            return False

    def snapshot(self) -> CrossMarketState:
        self.refresh()
        return self._cache

    # -----------------------------------------------------------------
    def _fetch_all(self) -> CrossMarketState:
        """Pull each instrument, return combined state. Each instrument
        is independent so one failure doesn't void everything."""
        out = CrossMarketState()

        # VIX -- Polygon-supported as index "I:VIX" but the existing
        # data_loader fetches it differently. Try yfinance first since
        # it's reliable for indices.
        try:
            v_close, v_change = _fetch_pct_change("^VIX", "5m")
            out.vix = v_close
            out.vix_change_5m_pct = v_change
        except Exception as e:
            logger.debug(f"VIX fetch failed: {e!r}")

        # ES via Polygon futures
        try:
            from research.data_loader import download_polygon_futures
            es_df = download_polygon_futures("ES", "1min")
            if es_df is not None and len(es_df) >= 6:
                last_close = float(es_df["close"].iloc[-1])
                close_5m_ago = float(es_df["close"].iloc[-6])
                out.es_last = last_close
                out.es_change_5m_pct = 100 * (last_close - close_5m_ago) / close_5m_ago
        except Exception as e:
            logger.debug(f"ES fetch failed: {e!r}")

        # SPY (equity proxy) via yfinance
        try:
            sp_close, sp_change = _fetch_pct_change("SPY", "5m")
            out.spy_last = sp_close
            out.spy_change_5m_pct = sp_change
        except Exception as e:
            logger.debug(f"SPY fetch failed: {e!r}")

        # DXY (Dollar Index) via yfinance
        try:
            dx_close, dx_change = _fetch_pct_change("DX-Y.NYB", "60m")
            out.dxy_last = dx_close
            out.dxy_change_60m_pct = dx_change
        except Exception as e:
            logger.debug(f"DXY fetch failed: {e!r}")

        # NQ-ES spread: pull current NQ and compute
        try:
            from research.data_loader import download_nq
            nq_df = download_nq("1min")
            if nq_df is not None and len(nq_df) >= 6 and out.es_change_5m_pct is not None:
                nq_change_5m = 100 * (
                    float(nq_df["close"].iloc[-1]) -
                    float(nq_df["close"].iloc[-6])
                ) / float(nq_df["close"].iloc[-6])
                out.nq_es_spread_5m_pct = nq_change_5m - out.es_change_5m_pct
        except Exception as e:
            logger.debug(f"NQ-ES spread compute failed: {e!r}")

        return out


def _fetch_pct_change(ticker: str, lookback: str) -> tuple[float, float]:
    """Returns (last_close, pct_change_over_lookback) via yfinance.
    lookback like '5m' or '60m'. Raises on failure."""
    import yfinance as yf
    # Use 1d period at finest interval that covers the lookback
    interval = "1m" if lookback.endswith("m") and int(lookback[:-1]) <= 30 else "5m"
    df = yf.download(ticker, period="1d", interval=interval,
                      progress=False, threads=False, auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned empty for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.columns = [str(c).lower() for c in df.columns]
    last_close = float(df["close"].iloc[-1])
    minutes_back = int(lookback[:-1])
    bars_back = max(1, minutes_back // (1 if interval == "1m" else 5))
    if len(df) <= bars_back:
        raise RuntimeError(f"insufficient history for {ticker}")
    old_close = float(df["close"].iloc[-bars_back - 1])
    pct = 100 * (last_close - old_close) / old_close
    return last_close, pct

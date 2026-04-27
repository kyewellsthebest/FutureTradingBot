"""
Data loader.

Tries three sources in order:
  1. Local 1-min NQ files (research.local_data_loader) — preferred
  2. yfinance with NQ=F symbol — fallback (intraday capped to ~70 days)
  3. A small synthetic random-walk sample — last-resort so the bot still boots

DATA_DIR is the on-disk cache directory used for all JSON snapshots.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("data_loader")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("HFT_DATA_DIR", PROJECT_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)

NQ_SYMBOL = "NQ=F"


def _try_local() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    try:
        from research import local_data_loader as L  # noqa: WPS433
        m1 = L.load_intraday_1min()
        if m1 is None or m1.empty:
            return None, None
        m5 = L.load_intraday_5min()
        d = L.load_daily()
        return m5, d
    except Exception as e:
        logger.info("[data] local NQ files not available: %s", e)
        return None, None


def _try_yfinance(timeframe: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        if timeframe == "5min":
            df = yf.download(NQ_SYMBOL, period="60d", interval="5m",
                             auto_adjust=False, progress=False)
        elif timeframe == "1h":
            df = yf.download(NQ_SYMBOL, period="730d", interval="60m",
                             auto_adjust=False, progress=False)
        else:
            df = yf.download(NQ_SYMBOL, period="max", interval="1d",
                             auto_adjust=False, progress=False)
    except Exception as e:
        logger.info("[data] yfinance fetch failed: %s", e)
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"adj close": "adj_close"})
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "ts"
    return df


def _synthetic(timeframe: str) -> pd.DataFrame:
    """Random-walk fallback so the bot still boots when offline."""
    rng = np.random.default_rng(7)
    if timeframe == "daily":
        n, freq = 600, "1D"
    elif timeframe == "1h":
        n, freq = 24 * 60, "1h"
    else:
        n, freq = 12 * 24 * 60, "5min"
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor(freq), periods=n, freq=freq)
    rets = rng.normal(0, 0.0015, n)
    close = 18000 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.0010, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.0010, n)))
    open_ = np.r_[close[0], close[:-1]]
    vol = rng.integers(1_000, 10_000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


_cache: dict[str, pd.DataFrame] = {}


def download_nq(timeframe: str = "5min") -> pd.DataFrame:
    """Return a UTC-indexed OHLCV DataFrame for the requested timeframe."""
    if timeframe in _cache:
        return _cache[timeframe]

    if timeframe in ("5min", "daily"):
        m5, d = _try_local()
        if m5 is not None and timeframe == "5min":
            _cache["5min"] = m5
            _cache.setdefault("daily", d)
            return m5
        if d is not None and timeframe == "daily":
            _cache["daily"] = d
            _cache.setdefault("5min", m5)
            return d

    df = _try_yfinance(timeframe)
    if df is None or df.empty:
        logger.warning("[data] using synthetic fallback for %s", timeframe)
        df = _synthetic(timeframe)
    _cache[timeframe] = df
    return df


def latest_price(timeframe: str = "5min") -> tuple[float, pd.Timestamp] | None:
    df = download_nq(timeframe)
    if df.empty:
        return None
    return float(df["close"].iloc[-1]), df.index[-1]


if __name__ == "__main__":
    for tf in ("5min", "daily"):
        df = download_nq(tf)
        print(f"{tf:>5s}: {len(df):,} bars  {df.index[0]} -> {df.index[-1]}")

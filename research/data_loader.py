"""
Data loader for NQ futures (yfinance NQ=F).

Downloads daily, 1-hour, and 5-minute bars with a 24-hour CSV cache.
If yfinance fails, falls back to the cached CSV (even if stale).
If env NQ_USE_LOCAL=1 is set, loads from local_data_loader instead.

Usage:
    python -m research.data_loader

(Reconstructed from research/data_loader.cpython311.pyc decompile.)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
(DATA_DIR / "cache").mkdir(exist_ok=True)

logger = logging.getLogger("data_loader")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(sh)
    fh = logging.FileHandler(LOG_DIR / "research.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] %(levelname)s %(message)s"))
    logger.addHandler(fh)

SYMBOL = "NQ=F"
Timeframe = Literal["daily", "1hr", "5min"]
TIMEFRAME_CONFIG: dict[str, tuple[str, str, str, int]] = {
    "daily": ("1d", "max", "nq_daily.csv", 7200),
    "1hr":   ("1h", "730d", "nq_1hr.csv", 7200),
    "5min":  ("5m", "60d", "nq_5min.csv", 600),
}
CACHE_TTL_SECONDS = 7200


def cache_path(timeframe: Timeframe) -> Path:
    return DATA_DIR / TIMEFRAME_CONFIG[timeframe][2]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure consistent schema: lowercase OHLCV columns, UTC tz, monotonic index."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _is_cache_fresh(path: Path, ttl_seconds: int) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_seconds


def _read_cache(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return _normalize(df)


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path)


def _synthetic(timeframe: Timeframe, n: int = 2000) -> pd.DataFrame:
    """Last-resort sample so the bot can boot offline."""
    freq = {"daily": "1D", "1hr": "1h", "5min": "5min"}[timeframe]
    end = pd.Timestamp.utcnow().floor(freq)
    idx = pd.date_range(end=end, periods=n, freq=freq, tz="UTC")
    rng = np.random.default_rng(42)
    rets = rng.normal(0, 0.0008, n)
    close = 21000.0 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0005, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0005, n)))
    vol = rng.integers(1000, 50000, n).astype(float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def download_nq(timeframe: Timeframe, *, force_refresh: bool = False) -> pd.DataFrame:
    """
    Return OHLCV DataFrame for NQ=F at the requested timeframe.

    If environment variable NQ_USE_LOCAL=1 is set, load from local 2-year
    1-min contract files (stitched with front-month convention) instead of yfinance.

    Cache strategy:
      - If cache file is < 24h old and not force_refresh -> return cached data.
      - Otherwise call yfinance. If that fails, fall back to cached (stale OK).
    """
    if os.environ.get("NQ_USE_LOCAL") == "1":
        try:
            from research.local_data_loader import (
                load_daily as _load_daily_local,
                load_intraday_1min as _load_1min_local,
                load_intraday_5min as _load_5min_local,
            )
            if timeframe == "5min":
                return _normalize(_load_5min_local())
            if timeframe == "daily":
                return _normalize(_load_daily_local())
            if timeframe == "1hr":
                m5 = _load_5min_local()
                return _normalize(m5.resample("1h").agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum",
                }).dropna())
        except Exception as e:
            logger.warning(f"local loader failed ({e!r}), falling through to yfinance")

    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Unknown timeframe {timeframe!r}; expected one of {list(TIMEFRAME_CONFIG)}")

    interval, period, _, ttl = TIMEFRAME_CONFIG[timeframe]
    path = cache_path(timeframe)
    if not force_refresh and _is_cache_fresh(path, ttl):
        logger.info(f"{timeframe}: using fresh cache {path.name}")
        return _read_cache(path)

    logger.info(f"{timeframe}: downloading {SYMBOL} interval={interval} period={period}")
    try:
        import yfinance as yf
        df = yf.download(SYMBOL, interval=interval, period=period,
                         auto_adjust=False, progress=False, threads=False)
        df = _normalize(df)
        if df.empty:
            raise RuntimeError("yfinance returned empty frame")
        _write_cache(df, path)
        logger.info(f"{timeframe}: downloaded {len(df)} rows, cached -> {path.name}")
        return df
    except Exception as exc:
        logger.warning(f"{timeframe}: download failed ({exc!r}), falling back to cache")
        if path.exists():
            return _read_cache(path)
        logger.warning(f"{timeframe}: no cache, generating synthetic sample")
        return _synthetic(timeframe)


def download_es(timeframe: Timeframe, *, force_refresh: bool = False) -> pd.DataFrame:
    """Same as download_nq but for ES=F (S&P 500 e-mini futures)."""
    if os.environ.get("NQ_USE_LOCAL") == "1":
        try:
            from research.local_data_loader import load_intraday_5min as _load_5min_local
            if timeframe == "5min":
                return _normalize(_load_5min_local("es"))
        except Exception as e:
            logger.warning(f"local ES loader failed ({e!r}), falling through to yfinance")

    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Unknown timeframe {timeframe!r}")

    interval, period, _, ttl = TIMEFRAME_CONFIG[timeframe]
    path = DATA_DIR / "cache" / f"es_{timeframe}.csv"
    if not force_refresh and _is_cache_fresh(path, ttl):
        return _read_cache(path)

    logger.info(f"ES {timeframe}: downloading interval={interval} period={period}")
    try:
        import yfinance as yf
        df = yf.download("ES=F", interval=interval, period=period,
                          auto_adjust=False, progress=False, threads=False)
        df = _normalize(df)
        if df.empty:
            raise RuntimeError("yfinance returned empty frame")
        _write_cache(df, path)
        return df
    except Exception as exc:
        logger.warning(f"ES {timeframe}: download failed ({exc!r}), falling back to cache")
        if path.exists():
            return _read_cache(path)
        return _synthetic(timeframe)


def load_all() -> dict[str, pd.DataFrame]:
    """Return dict of all 3 timeframes."""
    return {tf: download_nq(tf) for tf in TIMEFRAME_CONFIG}


def latest_price() -> tuple[float, pd.Timestamp] | tuple[None, None]:
    """Most recent close + timestamp from the 5-min frame (dashboard ticker)."""
    try:
        df = download_nq("5min")
        if df.empty:
            return None, None
        return float(df["close"].iloc[-1]), df.index[-1]
    except Exception as e:
        logger.warning(f"latest_price failed: {e!r}")
        return None, None


def _summary_row(name: str, df: pd.DataFrame) -> str:
    if df.empty:
        return f"  {name:6s}  EMPTY"
    return (f"{name:6s}  rows={len(df):>7,}   "
            f"first={df.index[0]:%Y-%m-%d %H:%M}   "
            f"last={df.index[-1]:%Y-%m-%d %H:%M}   "
            f"last_close={float(df['close'].iloc[-1]):.2f}")


def main() -> int:
    print("=" * 72)
    print("NQ=F Data Loader")
    print("=" * 72)
    frames = load_all()
    print()
    for name, df in frames.items():
        print(_summary_row(name, df))
    print()
    print("Cache files:")
    for tf in TIMEFRAME_CONFIG:
        p = cache_path(tf)
        if p.exists():
            age_h = (time.time() - p.stat().st_mtime) / 3600
            print(f"  {p.name:18s}  {p.stat().st_size / 1024:>8.1f} KB   age={age_h:>5.1f}h")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())

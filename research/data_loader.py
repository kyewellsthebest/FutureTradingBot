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

    # Polygon futures = preferred live source when POLYGON_API is configured.
    # Falls through to yfinance on any failure (see _try_polygon_futures).
    pf = _try_polygon_futures("NQ", timeframe, force_refresh)
    if pf is not None:
        return pf

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

    pf = _try_polygon_futures("ES", timeframe, force_refresh)
    if pf is not None:
        return pf

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


def download_symbol(symbol: str, timeframe: Timeframe, *,
                      force_refresh: bool = False, period: str | None = None) -> pd.DataFrame:
    """Generic OHLCV fetcher for any yfinance symbol. Used by v13 cross-asset
    features (DXY, TNX, GC=F, CL=F, BTC-USD, HG=F, ZN=F, etc.).

    Cache key includes the symbol so different instruments don't collide.
    """
    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Unknown timeframe {timeframe!r}")
    interval, default_period, _, ttl = TIMEFRAME_CONFIG[timeframe]
    period = period or default_period
    safe_sym = symbol.replace("=", "_").replace("^", "").replace("-", "_")
    path = DATA_DIR / "cache" / f"{safe_sym}_{timeframe}.csv"
    if not force_refresh and _is_cache_fresh(path, ttl):
        return _read_cache(path)
    logger.info(f"{symbol} {timeframe}: downloading interval={interval} period={period}")
    try:
        import yfinance as yf
        df = yf.download(symbol, interval=interval, period=period,
                          auto_adjust=False, progress=False, threads=False)
        df = _normalize(df)
        if df.empty:
            raise RuntimeError("yfinance returned empty frame")
        _write_cache(df, path)
        return df
    except Exception as exc:
        logger.warning(f"{symbol} {timeframe}: download failed ({exc!r}), falling back")
        if path.exists():
            return _read_cache(path)
        return _synthetic(timeframe)


def load_all() -> dict[str, pd.DataFrame]:
    """Return dict of all 3 timeframes."""
    return {tf: download_nq(tf) for tf in TIMEFRAME_CONFIG}


# ---------------------------------------------------------------------------
# Polygon.io integration
# ---------------------------------------------------------------------------
def _polygon_key() -> str | None:
    """API key from POLYGON_API (or POLYGON_API_KEY) env var."""
    return os.environ.get("POLYGON_API") or os.environ.get("POLYGON_API_KEY")


def _third_friday(year: int, month: int):
    """3rd Friday of a month — CME equity-index futures expiry."""
    from datetime import date as _d
    d = _d(year, month, 1)
    # weekday(): Mon=0 .. Sun=6 ; Friday=4
    first_friday = 1 + ((4 - d.weekday()) % 7)
    return _d(year, month, first_friday + 14)


def polygon_front_month(product: str, asof=None) -> str:
    """Construct the live front-month futures ticker, e.g. 'NQM6' (June 2026).

    CME equity-index futures are quarterly: H=Mar, M=Jun, U=Sep, Z=Dec.
    Picks the soonest quarterly contract whose 3rd-Friday expiry is still
    in the future. Year is encoded as the last digit (2026 -> 6)."""
    from datetime import date as _d
    asof = asof or _d.today()
    code = {3: "H", 6: "M", 9: "U", 12: "Z"}
    year = asof.year
    for _ in range(9):
        for m in (3, 6, 9, 12):
            exp = _third_friday(year, m)
            if exp >= asof:
                return f"{product}{code[m]}{year % 10}"
        year += 1
    return f"{product}M{asof.year % 10}"


def download_polygon_futures(product: str, timeframe: Timeframe = "5min", *,
                               ticker: str | None = None,
                               force_refresh: bool = False) -> pd.DataFrame | None:
    """Fetch OHLCV bars for a CME futures product from Polygon.

    product : "NQ", "ES", "RTY", etc. — the front-month contract is
              auto-constructed unless `ticker` is given explicitly.
    Uses /futures/v1/aggs/{ticker}?resolution=5_minute (confirmed working).
    window_start in the response is nanoseconds since epoch.
    """
    import json as _json
    import urllib.request

    key = _polygon_key()
    if not key:
        return None
    tk = ticker or polygon_front_month(product)
    res_map = {"5min": "5_minute", "1hr": "1_hour", "daily": "1_day"}
    resolution = res_map.get(timeframe, "5_minute")

    path = DATA_DIR / "cache" / f"polyfut_{tk}_{timeframe}.csv"
    ttl = TIMEFRAME_CONFIG.get(timeframe, ("", "", "", 600))[3]
    if not force_refresh and _is_cache_fresh(path, ttl):
        return _read_cache(path)

    url = (f"https://api.polygon.io/futures/v1/aggs/{tk}"
            f"?resolution={resolution}&limit=50000&apiKey={key}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"polygon futures {tk} {timeframe} fetch failed: {e!r}")
        if path.exists():
            return _read_cache(path)
        return None

    results = data.get("results") or []
    if not results:
        logger.warning(f"polygon futures {tk}: empty (status={data.get('status')})")
        return None
    rows = []
    for r in results:
        try:
            # window_start is nanoseconds since epoch
            ts = pd.Timestamp(int(r["window_start"]), unit="ns", tz="UTC")
            rows.append((ts, float(r["open"]), float(r["high"]),
                          float(r["low"]), float(r["close"]),
                          float(r.get("volume", 0))))
        except Exception:
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]
                        ).set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    try:
        _write_cache(df, path)
    except Exception:
        pass
    return df


def _try_polygon_futures(product: str, timeframe: Timeframe,
                          force_refresh: bool) -> pd.DataFrame | None:
    """Polygon front-month futures as the PREFERRED live source.

    Returns a sane, recent OHLCV frame, or None — None means 'fall through
    to yfinance'. Every failure mode (no key, error, too few bars, stale
    frame) returns None, so wiring Polygon in can only help the bot, never
    break it: a bad Polygon response silently defers to the old path.
    """
    if not _polygon_key() or timeframe not in ("5min", "1hr"):
        return None
    try:
        df = download_polygon_futures(product, timeframe,
                                        force_refresh=force_refresh)
    except Exception as e:
        logger.warning(f"polygon {product} {timeframe}: {e!r} — using yfinance")
        return None
    if df is None or len(df) < 150:
        return None
    now = pd.Timestamp.now(tz="UTC")
    age_days = (now - df.index[-1]).total_seconds() / 86400
    if age_days > 4:   # dead contract / plan delay — don't trade stale data
        logger.warning(f"polygon {product}: last bar {age_days:.1f}d old "
                          f"— using yfinance")
        return None
    logger.info(f"polygon {product} {timeframe}: {len(df)} bars (live source)")
    return df


def download_polygon_aggs(ticker: str, timeframe: Timeframe, *,
                            lookback_days: int | None = None,
                            force_refresh: bool = False) -> pd.DataFrame | None:
    """Fetch OHLCV aggregate bars from Polygon.io.

    Returns a normalized OHLCV DataFrame (UTC index), or None if no API
    key is set or the request fails. Ticker formats Polygon uses:
      stocks  : "QQQ", "SPY"
      indices : "I:NDX", "I:SPX", "I:VIX"
      futures : varies by Polygon's futures product entitlement

    Cached to data/cache/polygon_<ticker>_<tf>.csv with the standard TTL.
    """
    import json as _json
    import urllib.request
    import urllib.parse
    from datetime import datetime, timedelta, timezone as _tz

    key = _polygon_key()
    if not key:
        return None
    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Unknown timeframe {timeframe!r}")
    tf_map = {"5min": (5, "minute", 45), "1hr": (1, "hour", 365),
                "daily": (1, "day", 1825)}
    mult, span, default_days = tf_map.get(timeframe, (5, "minute", 45))
    days = lookback_days or default_days

    safe = ticker.replace(":", "_").replace("/", "_")
    path = DATA_DIR / "cache" / f"polygon_{safe}_{timeframe}.csv"
    ttl = TIMEFRAME_CONFIG[timeframe][3]
    if not force_refresh and _is_cache_fresh(path, ttl):
        return _read_cache(path)

    to_d = datetime.now(_tz.utc).strftime("%Y-%m-%d")
    from_d = (datetime.now(_tz.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = (f"https://api.polygon.io/v2/aggs/ticker/{urllib.parse.quote(ticker)}"
            f"/range/{mult}/{span}/{from_d}/{to_d}"
            f"?adjusted=true&sort=asc&limit=50000&apiKey={key}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"polygon {ticker} {timeframe} fetch failed: {e!r}")
        if path.exists():
            return _read_cache(path)
        return None

    results = data.get("results") or []
    if not results:
        logger.warning(f"polygon {ticker} {timeframe}: empty (status={data.get('status')}, "
                        f"msg={data.get('message') or data.get('error')})")
        return None
    rows = []
    for r in results:
        try:
            ts = pd.Timestamp(int(r["t"]), unit="ms", tz="UTC")
            rows.append((ts, float(r["o"]), float(r["h"]), float(r["l"]),
                          float(r["c"]), float(r.get("v", 0))))
        except Exception:
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]
                        ).set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    try:
        _write_cache(df, path)
    except Exception:
        pass
    return df


def polygon_diagnostic() -> dict:
    """Probe the Polygon key — discover what the plan exposes.

    Explores BOTH the stocks/index aggregates AND the futures API
    (different endpoint + ticker namespace). Reports which products work
    and lists discovered futures tickers for NQ/ES."""
    import json as _json
    import urllib.request
    import urllib.error

    key = _polygon_key()
    if not key:
        return {"ok": False, "error": "POLYGON_API env var not set"}
    out: dict = {"ok": True, "key_present": True,
                   "stocks_indices": {}, "futures": {}}

    def _get(url: str) -> dict | None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return _json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = _json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            return {"_http_error": e.code, **body}
        except Exception as e:
            return {"_error": str(e)}

    # --- 1. Stocks / index aggregates (free Basic tiers) -----------------
    for t in ["I:NDX", "QQQ", "SPY"]:
        try:
            df = download_polygon_aggs(t, "5min", lookback_days=5, force_refresh=True)
            if df is not None and not df.empty:
                out["stocks_indices"][t] = {"ok": True, "bars": len(df),
                                              "last_close": float(df["close"].iloc[-1])}
            else:
                out["stocks_indices"][t] = {"ok": False}
        except Exception as e:
            out["stocks_indices"][t] = {"ok": False, "reason": str(e)}

    # --- 2. Futures API — find the live front-month NQ/ES contract -------
    def _get_json(url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return _json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            try:
                body = _json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            return None, f"HTTP {e.code}: {body.get('message') or body.get('error') or ''}"
        except Exception as e:
            return None, str(e)

    today = datetime.now(_tz.utc).date().isoformat() if False else None
    from datetime import date as _date
    today_str = _date.today().isoformat()

    # 2a. Pull NQ + ES contracts NEWEST-FIRST, find the front-month
    #     (active, last_trade_date in the future, soonest expiry).
    for prod in ["NQ", "ES"]:
        # Try several query forms — Polygon's futures contract endpoint
        # param names aren't certain, so probe newest-first + a date filter.
        url_variants = [
            (f"https://api.polygon.io/futures/v1/contracts"
              f"?product_code={prod}&order=desc&sort=last_trade_date"
              f"&limit=100&apiKey={key}"),
            (f"https://api.polygon.io/futures/v1/contracts"
              f"?product_code={prod}&last_trade_date.gte={today_str}"
              f"&limit=100&apiKey={key}"),
            (f"https://api.polygon.io/futures/v1/contracts"
              f"?product_code={prod}&limit=1000&apiKey={key}"),
        ]
        front = None
        n_contracts = 0
        n_live = 0
        used = None
        for vi, url in enumerate(url_variants):
            d, err = _get_json(url)
            if err or not d:
                continue
            results = d.get("results") or []
            n_contracts = len(results)
            live = [r for r in results
                      if isinstance(r, dict) and r.get("last_trade_date", "") >= today_str]
            n_live = len(live)
            if live:
                live.sort(key=lambda r: r.get("last_trade_date", ""))
                front = live[0]
                used = f"variant_{vi}"
                break
        out["futures"][f"{prod}_frontmonth"] = {
            "ok": front is not None,
            "n_contracts": n_contracts,
            "n_live": n_live,
            "query_used": used,
            "front_ticker": front.get("ticker") if front else None,
            "front_last_trade": front.get("last_trade_date") if front else None,
        }

    # 2b. The futures aggs endpoint is /futures/v1/aggs/{ticker} — confirmed
    #     to exist (HTTP 400 'Invalid resolution', not 404). Probe a batch
    #     of resolution-parameter formats to find the one Polygon accepts.
    nq_front = out["futures"].get("NQ_frontmonth", {}).get("front_ticker")
    if nq_front:
        resolutions = ["1S", "1M", "5M", "1H", "1D",
                         "second", "minute", "hour", "day",
                         "1minute", "5minute", "1_minute", "5_minute",
                         "1m", "60", "300"]
        out["futures"]["aggs_resolution_probe"] = {"tested_ticker": nq_front,
                                                       "results": {}}
        for res in resolutions:
            url = (f"https://api.polygon.io/futures/v1/aggs/{nq_front}"
                    f"?resolution={res}&limit=10&apiKey={key}")
            d, err = _get_json(url)
            if err:
                # Distinguish "bad resolution" (400) from other failures
                short = err[:60]
                out["futures"]["aggs_resolution_probe"]["results"][res] = short
            else:
                results = (d or {}).get("results") or []
                if results:
                    out["futures"]["aggs_resolution_probe"]["results"][res] = {
                        "ok": True, "n_bars": len(results),
                        "sample_bar": results[0],
                    }
                else:
                    out["futures"]["aggs_resolution_probe"]["results"][res] = "empty (200 OK, no bars)"
    return out


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

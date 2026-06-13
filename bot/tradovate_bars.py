"""Tradovate historical bar fetcher.

Replaces Polygon for the bot's warmup data path. Uses Tradovate's
/md/getChart WebSocket request to pull OHLCV bars for any front-month
contract.

ARCHITECTURE:
  Tradovate's chart endpoint is WebSocket-only (not REST). We open a
  short-lived market-data WS connection, authenticate with the
  mdAccessToken, send `md/getChart`, collect the bar packets, then
  close.

  Result is cached in-memory for CHART_CACHE_TTL seconds (default 30)
  so the bot doesn't spam Tradovate for warmup data every cycle.

USAGE:
    from bot.tradovate_bars import get_bars
    df = get_bars(symbol="MNQM6", interval="1m", n=60)
    # df: index=tz-aware UTC datetime, columns: open/high/low/close/volume

ENV:
    TRADOVATE_BAR_TIMEOUT_S    -- WS receive timeout (default 12)
    TRADOVATE_BAR_CACHE_TTL_S  -- in-memory cache TTL (default 30)

Reference: Tradovate API docs -- Chart Data section.
  - md/getChart request body:
      {
        "symbol": "<contractName>",
        "chartDescription": {
          "underlyingType": "MinuteBar"|"DailyBar"|"Tick",
          "elementSize": <int>,             # 1, 5, 30, etc.
          "elementSizeUnit": "UnderlyingUnits",
          "withHistogram": false
        },
        "timeRange": {
          "asMuchAsElements": <int>         # request N bars
          # OR
          "asFarAsTimestamp": "2026-06-13T00:00:00Z"
        }
      }
  - Response packets stream as `chart` events; each has packetEntries
    with {timestamp, open, high, low, close, upVolume, downVolume}.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger("tradovate_bars")

_CACHE: dict = {}  # (symbol, interval, n) -> (ts_loaded, dataframe)
_CACHE_LOCK = threading.Lock()

# Stats for the Polygon Readiness card. Track every Tradovate WS
# success / failure so the dashboard can tell the user whether it's
# safe to cancel Polygon yet.
_STATS = {
    "tradovate_success_count": 0,
    "tradovate_failure_count": 0,
    "last_tradovate_success_ts": None,
    "last_tradovate_failure_ts": None,
    "last_polygon_fallback_ts": None,
    "first_call_ts": None,
}
_STATS_LOCK = threading.Lock()


def get_stats() -> dict:
    """Snapshot of fetch stats for the diagnostic bundle + dashboard."""
    with _STATS_LOCK:
        return dict(_STATS)


def mark_polygon_fallback() -> None:
    """Called by data_loader when it falls back to Polygon."""
    with _STATS_LOCK:
        _STATS["last_polygon_fallback_ts"] = time.time()


def _cache_ttl() -> float:
    return float(os.environ.get("TRADOVATE_BAR_CACHE_TTL_S", "30"))


def _recv_timeout() -> float:
    return float(os.environ.get("TRADOVATE_BAR_TIMEOUT_S", "12"))


def _md_ws_url() -> str:
    return os.environ.get("TRADOVATE_MD_WS",
                           "wss://md.tradovateapi.com/v1/websocket")


def _interval_to_chart_desc(interval: str) -> dict:
    """Map our interval strings to Tradovate's chartDescription.

    Supported intervals:
      '1m', '5m', '15m', '30m', '1h', '4h', '1d'
    """
    iv = interval.lower().strip()
    if iv == "1d":
        return {"underlyingType": "DailyBar", "elementSize": 1,
                "elementSizeUnit": "UnderlyingUnits"}
    suffix = iv[-1]
    n = int(iv[:-1])
    if suffix == "m":
        return {"underlyingType": "MinuteBar", "elementSize": n,
                "elementSizeUnit": "UnderlyingUnits"}
    if suffix == "h":
        return {"underlyingType": "MinuteBar", "elementSize": n * 60,
                "elementSizeUnit": "UnderlyingUnits"}
    raise ValueError(f"unsupported interval {interval!r}")


def get_bars(symbol: str, interval: str = "1m",
              n: int = 60) -> Optional["pd.DataFrame"]:
    """Fetch OHLCV bars for a contract.

    Returns pandas DataFrame indexed by tz-aware UTC datetime with
    columns [open, high, low, close, volume]. Returns None on
    failure (caller falls back to Polygon).

    Cached by (symbol, interval, n) for cache_ttl seconds.
    """
    import pandas as pd
    key = (symbol, interval, n)
    now = time.time()
    with _STATS_LOCK:
        if _STATS["first_call_ts"] is None:
            _STATS["first_call_ts"] = now
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _cache_ttl():
        return cached[1]
    try:
        bars = _fetch_via_ws(symbol, interval, n)
    except Exception as e:
        logger.warning(f"tradovate_bars {symbol} {interval} n={n}: "
                       f"WS fetch failed: {e!r}")
        with _STATS_LOCK:
            _STATS["tradovate_failure_count"] += 1
            _STATS["last_tradovate_failure_ts"] = now
        return None
    if not bars:
        with _STATS_LOCK:
            _STATS["tradovate_failure_count"] += 1
            _STATS["last_tradovate_failure_ts"] = now
        return None
    df = pd.DataFrame(bars)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    # Ensure tz-aware UTC
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    with _CACHE_LOCK:
        _CACHE[key] = (now, df)
    with _STATS_LOCK:
        _STATS["tradovate_success_count"] += 1
        _STATS["last_tradovate_success_ts"] = now
    return df


def _fetch_via_ws(symbol: str, interval: str, n: int) -> list:
    """Open a short-lived WS connection, authenticate, send getChart,
    collect bar packets, close. Returns list of dicts."""
    try:
        import websocket
    except ImportError:
        logger.warning("tradovate_bars: websocket-client not installed")
        return []
    from bot.tradovate_client import get_session
    sess = get_session()
    if not sess.is_configured:
        return []
    tokens = sess.get_tokens()
    if tokens is None:
        return []
    ws = websocket.create_connection(_md_ws_url(), timeout=10)
    next_req_id = [1]

    def _next_req(verb: str, body: str = "") -> str:
        rid = next_req_id[0]
        next_req_id[0] += 1
        return f"{verb}\n{rid}\n\n{body}"

    try:
        # 'o' open frame
        try:
            ws.recv()
        except Exception:
            pass
        ws.send(_next_req("authorize", tokens.access_token))
        auth_resp = ws.recv()
        if not auth_resp.startswith("a"):
            logger.warning(f"tradovate_bars auth resp: {auth_resp[:200]!r}")
        chart_desc = _interval_to_chart_desc(interval)
        body = json.dumps({
            "symbol": symbol,
            "chartDescription": {**chart_desc, "withHistogram": False},
            "timeRange": {"asMuchAsElements": int(n)},
        })
        ws.send(_next_req("md/getChart", body))
        # Collect packets until we have enough bars or timeout
        bars = []
        deadline = time.time() + _recv_timeout()
        ws.settimeout(2.0)
        while time.time() < deadline and len(bars) < n:
            try:
                raw = ws.recv()
            except Exception:
                continue
            if not raw or raw[0] != "a":
                continue
            try:
                msgs = json.loads(raw[1:])
            except Exception:
                continue
            for m in msgs if isinstance(msgs, list) else []:
                if not isinstance(m, dict):
                    continue
                ev = m.get("e")
                data = m.get("d") or {}
                if ev != "chart":
                    continue
                # Chart packets contain 'charts' list with bars array
                for ch in (data.get("charts") or []):
                    if not isinstance(ch, dict):
                        continue
                    for b in (ch.get("bars") or []):
                        if not isinstance(b, dict):
                            continue
                        ts = b.get("timestamp")
                        try:
                            import pandas as _pd
                            ts_pd = _pd.Timestamp(ts)
                        except Exception:
                            continue
                        bars.append({
                            "timestamp": ts_pd,
                            "open": float(b.get("open", 0)),
                            "high": float(b.get("high", 0)),
                            "low": float(b.get("low", 0)),
                            "close": float(b.get("close", 0)),
                            "volume": float((b.get("upVolume") or 0)
                                              + (b.get("downVolume") or 0)),
                        })
        logger.info(f"tradovate_bars {symbol} {interval}: got "
                    f"{len(bars)}/{n} bars")
        return bars
    finally:
        try:
            ws.close()
        except Exception:
            pass


def health() -> dict:
    """Cache + last-fetch stats for the diagnostic bundle."""
    with _CACHE_LOCK:
        return {
            "cache_size": len(_CACHE),
            "cache_keys": list(_CACHE.keys()),
            "cache_ttl_s": _cache_ttl(),
        }

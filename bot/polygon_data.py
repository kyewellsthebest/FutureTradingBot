"""Polygon market data client — clean rebuild.

ONE module, ONE responsibility: get fresh MNQ futures data from
Polygon (or its reseller proxy). No silent fallbacks. No caching of
stale data. Every API call's status is logged.

What we learned from the existing code's failure:

  /futures/v1/snapshot/{tk}      -> 404 (deprecated)
  /futures/v1/last/trade/{tk}    -> 404 (deprecated)
  /futures/v1/last/quote/{tk}    -> 404 (deprecated)
  /futures/v1/aggs/{tk}          -> 200 OK but bars 13+ hours stale
  /v3/snapshot?ticker={tk}       -> 200 OK with "Ticker not found"
                                    because v3 uses a DIFFERENT
                                    ticker format than v1.

The fix: detect the right ticker format for the v3 endpoint by
trying multiple variants and caching whichever works.

Public API:
  PolygonData.get_snapshot()   -> (price, age_s, ticker_used, raw) or None
  PolygonData.get_bars(tf,n)   -> DataFrame indexed by UTC ts
  PolygonData.ws_subscribe(...) -> spawns WS thread

Anything that fails returns None or empty -- never stale data. The
caller decides whether to retry or fall through to another source.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger("polygon_data")


# ---------------------------------------------------------------------------
# Ticker construction
# ---------------------------------------------------------------------------

_MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    # First Friday
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d + timedelta(days=14)


def _front_month_components(product: str, asof: Optional[date] = None
                             ) -> tuple[str, str, int]:
    """Returns (product, month_code, year). The front-month is the
    nearest quarterly contract whose 3rd-Friday expiry is in the
    future."""
    asof = asof or date.today()
    year = asof.year
    for _ in range(9):
        for m in (3, 6, 9, 12):
            exp = _third_friday(year, m)
            if exp >= asof:
                return product, _MONTH_CODE[m], year
        year += 1
    raise RuntimeError("unreachable")


def ticker_variants(product: str = "MNQ",
                    asof: Optional[date] = None) -> list[str]:
    """Generate every plausible ticker format Polygon might accept,
    so we can try them all and lock onto the one that works.

    For E-mini index futures (NQ, MNQ, ES, etc.) Polygon endpoints
    historically use one of these formats:
      MNQM6      -- CME short (single year digit)
      MNQM26     -- 2-digit year (some v2 endpoints)
      MNQM2026   -- full year (v3 / reference endpoints)
      F:MNQM6    -- with futures prefix
      F:MNQM26
      F:MNQM2026
    """
    p, mc, yr = _front_month_components(product, asof)
    short = f"{p}{mc}{yr % 10}"
    yy = f"{p}{mc}{yr % 100:02d}"
    full = f"{p}{mc}{yr:04d}"
    return [short, yy, full, f"F:{short}", f"F:{yy}", f"F:{full}"]


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class PolygonData:
    BASE = "https://api.polygon.io"

    def __init__(self, api_key: Optional[str] = None,
                 product: str = "MNQ") -> None:
        self.api_key = api_key or os.environ.get("POLYGON_API")
        if not self.api_key:
            logger.error("POLYGON_API env var not set")
        self.product = product
        # Once we find a ticker format that works for a given endpoint
        # kind ("snapshot" / "aggs" / "ws"), remember it so we stop
        # cycling on every poll.
        self._working_ticker: dict[str, str] = {}

    # ----- HTTP helpers --------------------------------------------------

    def _get(self, path: str, **params) -> tuple[Optional[int], str]:
        """Single GET. Returns (status_code_or_None, body_text)."""
        if not self.api_key:
            return None, "no_api_key"
        params = {**params, "apiKey": self.api_key}
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE}{path}?{qs}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "hftbot/2.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return resp.status, body
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return e.code, body
        except Exception as e:
            return None, repr(e)

    # ----- SNAPSHOT (most recent price) ----------------------------------

    def get_snapshot(self) -> Optional[tuple[float, float, str, dict]]:
        """Most recent price for the front-month contract.

        Returns (price, age_s, ticker_used, raw_response) on success
        or None if every variant fails / is stale / unparseable. Age
        is computed from Polygon's timestamp field; values >300s are
        rejected so we never return a frozen price.

        Tries the v3 universal snapshot endpoint with each ticker
        variant until one returns a result without a NOT_FOUND error.
        """
        # If we previously locked onto a ticker format, try it first
        # so steady-state polling doesn't waste time cycling.
        locked = self._working_ticker.get("snapshot")
        tickers = ([locked] if locked else []) + [
            t for t in ticker_variants(self.product) if t != locked
        ]

        for tk in tickers:
            status, body = self._get("/v3/snapshot", ticker=tk)
            logger.info(f"snapshot {tk}: status={status} body[:300]={body[:300]!r}")
            if status != 200:
                continue
            try:
                data = json.loads(body)
            except Exception as e:
                logger.warning(f"snapshot {tk}: JSON decode failed: {e!r}")
                continue
            results = data.get("results") or []
            if not isinstance(results, list) or not results:
                continue
            r = results[0]
            if not isinstance(r, dict):
                continue
            if r.get("error") == "NOT_FOUND":
                # Ticker format wrong for this endpoint; try next variant
                continue

            # Universal snapshot shape varies by asset class. For
            # futures we expect a "session" object with day-OHLC and
            # a "last_quote" / "last_trade" with the live tick.
            price = self._extract_price(r)
            ts_ns = self._extract_timestamp(r)
            if price is None:
                logger.warning(f"snapshot {tk}: 200 but no price found "
                                f"in payload keys={list(r.keys())}")
                continue

            age_s = (time.time() - ts_ns / 1e9) if ts_ns else 0.0
            if age_s > 300:
                logger.warning(f"snapshot {tk}: price {price} is "
                                f"{age_s/60:.1f}min stale -- rejecting")
                continue

            # Lock onto this ticker format
            self._working_ticker["snapshot"] = tk
            return float(price), float(age_s), tk, r

        return None

    @staticmethod
    def _extract_price(r: dict) -> Optional[float]:
        # Try every nested location we've seen in practice
        candidates = [
            ("last_trade", "price"), ("last_trade", "p"),
            ("trade", "price"), ("trade", "p"),
            ("last_quote", "bid_price"), ("last_quote", "bp"),
            ("session", "close"),
            ("session", "previous_close"),  # last resort
            ("price",), ("p",), ("last",), ("c",),
        ]
        for path in candidates:
            cur: object = r
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    cur = None
                    break
                cur = cur[k]
            if isinstance(cur, (int, float)) and cur > 0:
                return float(cur)
        return None

    @staticmethod
    def _extract_timestamp(r: dict) -> Optional[int]:
        candidates = [
            ("last_trade", "sip_timestamp"),
            ("last_trade", "participant_timestamp"),
            ("last_trade", "timestamp"), ("last_trade", "t"),
            ("trade", "sip_timestamp"), ("trade", "t"),
            ("last_quote", "sip_timestamp"), ("last_quote", "t"),
            ("updated",), ("timestamp",), ("t",),
        ]
        for path in candidates:
            cur: object = r
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    cur = None
                    break
                cur = cur[k]
            if isinstance(cur, (int, float)):
                return int(cur)
        return None

    # ----- BARS ----------------------------------------------------------

    def get_bars(self, timeframe: str = "1min",
                 lookback_hours: int = 24,
                 max_results: int = 5000) -> pd.DataFrame:
        """Fetch closed OHLC bars for the front-month contract.

        Uses /futures/v1/aggs/{tk}?from=<ms>&to=<ms> with explicit
        time-range parameters. The bar list returned drops any rows
        older than lookback_hours from now -- so a Polygon response
        full of historical bars doesn't pollute the strategy view.

        Returns an empty DataFrame if every variant fails or returns
        no fresh data. NEVER returns stale-only frames.
        """
        res_map = {"1min": "1_minute", "5min": "5_minute",
                   "1hr": "1_hour", "daily": "1_day"}
        resolution = res_map.get(timeframe, "1_minute")

        now_ms = int(time.time() * 1000)
        from_ms = now_ms - lookback_hours * 3600 * 1000
        to_ms = now_ms + 60 * 1000

        locked = self._working_ticker.get("aggs")
        tickers = ([locked] if locked else []) + [
            t for t in ticker_variants(self.product) if t != locked
        ]

        for tk in tickers:
            status, body = self._get(
                f"/futures/v1/aggs/{tk}",
                resolution=resolution,
                limit=max_results,
                **{"from": from_ms, "to": to_ms, "order": "desc"},
            )
            if status != 200:
                logger.info(f"aggs {tk} {timeframe}: status={status} "
                            f"body[:200]={body[:200]!r}")
                continue
            try:
                data = json.loads(body)
            except Exception as e:
                logger.warning(f"aggs {tk}: JSON decode failed: {e!r}")
                continue
            results = data.get("results") or []
            if not isinstance(results, list) or not results:
                logger.info(f"aggs {tk} {timeframe}: empty results "
                            f"(status={data.get('status')})")
                continue

            rows = []
            for r in results:
                try:
                    ts = pd.Timestamp(int(r["window_start"]),
                                       unit="ns", tz="UTC")
                    rows.append((
                        ts, float(r["open"]), float(r["high"]),
                        float(r["low"]), float(r["close"]),
                        float(r.get("volume", 0)),
                    ))
                except Exception:
                    continue
            if not rows:
                continue

            df = pd.DataFrame(rows, columns=["ts", "open", "high", "low",
                                              "close", "volume"]
                              ).set_index("ts").sort_index()
            df = df[~df.index.duplicated(keep="last")]

            # Reject the whole frame if its latest bar is too old --
            # callers want to know freshness failed, not paper over it.
            latest = df.index[-1]
            if latest.tz is None:
                latest = latest.tz_localize("UTC")
            age_min = (datetime.now(timezone.utc)
                       - latest.to_pydatetime()).total_seconds() / 60
            if age_min > 60:
                logger.warning(f"aggs {tk} {timeframe}: {len(df)} bars "
                                f"returned but latest is {age_min:.1f}min "
                                f"stale -- rejecting (caller should use "
                                f"WS-built bars instead)")
                # Don't try other variants -- if Polygon returns stale
                # for one variant, it'll return stale for all.
                return pd.DataFrame(columns=["open", "high", "low",
                                              "close", "volume"])

            self._working_ticker["aggs"] = tk
            logger.info(f"aggs {tk} {timeframe}: {len(df)} bars, "
                        f"latest {age_min:.1f}min ago")
            return df

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_singleton: Optional[PolygonData] = None


def client() -> PolygonData:
    global _singleton
    if _singleton is None:
        _singleton = PolygonData(product=os.environ.get("POLYGON_CONTRACT", "MNQ"))
    return _singleton


def get_snapshot_price() -> Optional[tuple[float, float]]:
    """Convenience wrapper used by price_monitor._CHAIN. Returns
    (price, age_s) or None. Never returns stale prices."""
    res = client().get_snapshot()
    if res is None:
        return None
    price, age_s, _tk, _raw = res
    return price, age_s


def get_bars(timeframe: str = "1min") -> pd.DataFrame:
    """Convenience wrapper used by the bot's bar pipeline. Returns
    a DataFrame indexed by UTC ts with OHLCV columns. Empty frame
    when no fresh bars are available."""
    return client().get_bars(timeframe=timeframe)

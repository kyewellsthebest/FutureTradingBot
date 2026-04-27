"""
Clock-sync helper.

Queries Google's HTTP `Date` header to derive a UTC offset and exposes
`real_utc_now()` so the bot uses corrected time even on a VPS with a wrong
system clock. Re-syncs every 60 cycles (~1 hour).
"""
from __future__ import annotations

import logging
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger("clock_sync")

_TIME_OFFSET_SECONDS: float = 0.0


def sync_clock(url: str = "https://www.google.com",
               timeout: float = 5.0) -> float:
    """Set the global offset from Google's Date header. Returns offset seconds."""
    global _TIME_OFFSET_SECONDS
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            date_hdr = resp.headers.get("Date")
        if not date_hdr:
            return _TIME_OFFSET_SECONDS
        server_dt = parsedate_to_datetime(date_hdr)
        if server_dt.tzinfo is None:
            server_dt = server_dt.replace(tzinfo=timezone.utc)
        local_dt = datetime.now(timezone.utc)
        offset = (server_dt - local_dt).total_seconds()
        _TIME_OFFSET_SECONDS = offset
        logger.info(f"clock sync: offset={offset:+.2f}s (server={server_dt}, local={local_dt})")
        return offset
    except Exception as e:
        logger.warning(f"clock sync failed: {e!r} — keeping previous offset {_TIME_OFFSET_SECONDS:+.2f}s")
        return _TIME_OFFSET_SECONDS


def real_utc_now() -> datetime:
    return datetime.now(timezone.utc).fromtimestamp(
        datetime.now(timezone.utc).timestamp() + _TIME_OFFSET_SECONDS, tz=timezone.utc
    )


def offset_seconds() -> float:
    return _TIME_OFFSET_SECONDS

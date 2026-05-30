"""Economic calendar -- pulls scheduled high-impact economic events so
the risk engine can block entries around CPI / FOMC / NFP / PCE etc.

DATA SOURCE: Forex Factory's free public XML feed
  https://nfs.faireconomy.media/ff_calendar_thisweek.xml

WHY THIS SOURCE:
  - Genuinely free (no API key, no rate limits in practice)
  - Includes scheduled US high-impact events
  - Has impact rating (High/Medium/Low)
  - Has the actual timestamps
  - Stable XML schema since at least 2018

WHY THIS MATTERS:
  CPI / FOMC / NFP releases can cause 20-50pt instant NQ moves. The bot's
  6pt stop is meaningless against that kind of news shock. Even one bad
  fill into a CPI print could cost $100+ vs the usual $26 stop. Worse,
  microstructure (spreads, fast stops) degrades for the 30 min after a
  release. Best policy: just don't trade around them.

USAGE:
    cal = EconomicCalendar()
    cal.refresh()  # call once on startup + every ~6 hours
    evt = cal.next_event_within(now, minutes=15)
    if evt:
        deny entries
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger("economic_calendar")

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
CACHE_TTL_SEC = 6 * 3600   # refresh every 6 hours
DEFAULT_TIMEOUT_S = 10

# Map FF impact strings to our internal severity
_IMPACT_MAP = {"high": "high", "medium": "medium", "low": "low",
                "holiday": "holiday", "non-economic": "low"}

# A conservative list of events we always treat as catastrophic for NQ
# regardless of FF's tagging. Match by substring (case-insensitive) on event
# title. These are the ones documented to cause 20+pt NQ moves on release.
_ALWAYS_BLACKOUT_KEYWORDS = (
    "fomc", "federal funds rate", "interest rate decision",
    "cpi", "core cpi",
    "nfp", "non-farm employment", "non farm payroll",
    "pce", "core pce",
    "ppi", "core ppi",
    "gdp", "advance gdp",
    "retail sales",
    "ism manufacturing", "ism services",
    "unemployment rate",
    "fed chair", "powell speaks", "fed press conference",
)


@dataclass(frozen=True)
class EconomicEvent:
    ts: datetime              # event timestamp in UTC
    title: str                # e.g. "Core CPI m/m"
    currency: str             # 'USD', 'EUR', etc
    impact: str               # 'high' / 'medium' / 'low' / 'holiday'
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None

    @property
    def is_blackout_worthy(self) -> bool:
        """High-impact USD event OR matches a known catastrophe keyword."""
        if self.currency != "USD":
            return False
        if self.impact == "high":
            return True
        t = self.title.lower()
        return any(kw in t for kw in _ALWAYS_BLACKOUT_KEYWORDS)

    def minutes_until(self, now: datetime) -> float:
        return (self.ts - now).total_seconds() / 60.0

    def to_dict(self) -> dict:
        return {
            "ts":       self.ts.isoformat(),
            "title":    self.title,
            "currency": self.currency,
            "impact":   self.impact,
            "forecast": self.forecast,
            "previous": self.previous,
            "actual":   self.actual,
        }


class EconomicCalendar:
    """Caches the upcoming week's events. Refreshes on demand if stale."""

    def __init__(self, cache_dir: Optional[Path] = None,
                 ttl_seconds: int = CACHE_TTL_SEC):
        self.events: List[EconomicEvent] = []
        self._last_refresh_ts: float = 0.0
        self._ttl = ttl_seconds
        self._cache_dir = cache_dir
        self._fetch_errors = 0
        self._last_error: Optional[str] = None

    # -----------------------------------------------------------------
    def refresh(self, *, force: bool = False) -> bool:
        """Fetch fresh calendar if cache is stale. Returns True on success.
        Failures are non-fatal: the gate just won't block any events until
        next successful fetch."""
        now = time.time()
        if not force and self.events and (now - self._last_refresh_ts) < self._ttl:
            return True
        try:
            req = urllib.request.Request(
                FEED_URL,
                headers={"User-Agent": "hftbot/1.0 (economic-calendar)"})
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
                xml_bytes = resp.read()
            self.events = _parse_ff_xml(xml_bytes)
            self._last_refresh_ts = now
            self._last_error = None
            logger.info(f"economic calendar refreshed: {len(self.events)} events")
            # Optional: persist to disk for cross-restart survival
            if self._cache_dir:
                try:
                    self._cache_dir.mkdir(parents=True, exist_ok=True)
                    (self._cache_dir / "economic_calendar.json").write_text(
                        json.dumps([e.to_dict() for e in self.events],
                                    indent=2, default=str)
                    )
                except Exception as e:
                    logger.debug(f"calendar cache write failed: {e!r}")
            return True
        except Exception as e:
            self._fetch_errors += 1
            self._last_error = repr(e)
            logger.warning(f"economic calendar fetch failed: {e!r}")
            # Try disk cache as a fallback
            if not self.events and self._cache_dir:
                self._load_from_disk()
            return False

    def _load_from_disk(self) -> None:
        if not self._cache_dir:
            return
        p = self._cache_dir / "economic_calendar.json"
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            self.events = []
            for d in data:
                ts = datetime.fromisoformat(d["ts"].replace("Z", "+00:00"))
                self.events.append(EconomicEvent(
                    ts=ts, title=d["title"], currency=d["currency"],
                    impact=d["impact"],
                    forecast=d.get("forecast"), previous=d.get("previous"),
                    actual=d.get("actual"),
                ))
            logger.info(f"calendar loaded from disk: {len(self.events)} events")
        except Exception as e:
            logger.warning(f"calendar disk load failed: {e!r}")

    # -----------------------------------------------------------------
    def next_event_within(self, now: datetime, minutes: int,
                           *, only_blackout: bool = True) -> Optional[EconomicEvent]:
        """Returns the next high-impact USD event within `minutes` (or None).
        If only_blackout=True, only events flagged is_blackout_worthy count.
        """
        self.refresh()   # no-op if cache fresh
        if not self.events:
            return None
        cutoff = now + timedelta(minutes=minutes)
        candidates = [e for e in self.events
                      if now <= e.ts <= cutoff
                      and (e.is_blackout_worthy if only_blackout else True)]
        if not candidates:
            return None
        return min(candidates, key=lambda e: e.ts)

    def upcoming(self, now: datetime, hours: int = 24,
                  *, only_blackout: bool = True) -> List[EconomicEvent]:
        self.refresh()
        cutoff = now + timedelta(hours=hours)
        return sorted([
            e for e in self.events
            if now <= e.ts <= cutoff
            and (e.is_blackout_worthy if only_blackout else True)
        ], key=lambda e: e.ts)

    # -----------------------------------------------------------------
    def status(self) -> dict:
        return {
            "n_events_cached":       len(self.events),
            "last_refresh_ts":       self._last_refresh_ts,
            "last_refresh_age_s":    (time.time() - self._last_refresh_ts)
                                      if self._last_refresh_ts else None,
            "ttl_seconds":           self._ttl,
            "fetch_errors":          self._fetch_errors,
            "last_error":            self._last_error,
            "next_high_impact_usd":  (
                self.next_event_within(datetime.now(timezone.utc), 48 * 60).to_dict()
                if self.next_event_within(datetime.now(timezone.utc), 48 * 60) else None
            ),
        }


def _parse_ff_xml(xml_bytes: bytes) -> List[EconomicEvent]:
    """Parses ForexFactory XML format. Schema (stable since ~2018):

        <weeklyevents>
          <event>
            <title>Core CPI m/m</title>
            <country>USD</country>
            <date>05-30-2026</date>
            <time>8:30am</time>
            <impact>High</impact>
            <forecast>0.3%</forecast>
            <previous>0.3%</previous>
          </event>
          ...
        </weeklyevents>

    FF times are US Eastern. We convert to UTC for storage. DST handled
    via pandas Timestamp (which knows America/New_York).
    """
    import pandas as pd
    root = ET.fromstring(xml_bytes)
    out: List[EconomicEvent] = []
    for ev in root.findall("event"):
        title    = (ev.findtext("title") or "").strip()
        country  = (ev.findtext("country") or "").strip().upper()
        date_str = (ev.findtext("date") or "").strip()
        time_str = (ev.findtext("time") or "").strip()
        impact   = (ev.findtext("impact") or "Low").strip().lower()
        forecast = (ev.findtext("forecast") or "").strip() or None
        previous = (ev.findtext("previous") or "").strip() or None
        if not title or not date_str:
            continue
        # Some events have time = "All Day" / "Tentative" / "" — skip those
        if not time_str or "day" in time_str.lower() or "tentative" in time_str.lower():
            continue
        try:
            # FF date is "MM-DD-YYYY" with time like "8:30am"
            naive = pd.to_datetime(f"{date_str} {time_str}",
                                    format="%m-%d-%Y %I:%M%p", errors="coerce")
            if pd.isna(naive):
                continue
            # FF times are US/Eastern (DST-aware)
            ts_et = naive.tz_localize("America/New_York", nonexistent="shift_forward",
                                       ambiguous="NaT")
            if pd.isna(ts_et):
                continue
            ts_utc = ts_et.tz_convert("UTC").to_pydatetime()
        except Exception:
            continue
        out.append(EconomicEvent(
            ts=ts_utc, title=title, currency=country,
            impact=_IMPACT_MAP.get(impact, "low"),
            forecast=forecast, previous=previous,
        ))
    return out

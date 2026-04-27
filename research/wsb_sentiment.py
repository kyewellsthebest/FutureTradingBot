"""
WallStreetBets retail-sentiment indicator.

Uses Reddit's public JSON endpoint (no auth) to scan r/wallstreetbets
hot posts, count mentions of NQ-related tickers, and classify overall
sentiment using naive keyword matching.

CONTRARIAN SIGNAL:
Extreme retail bullishness often marks tops; extreme bearishness marks
bottoms. We score as a CONTRARIAN indicator — retail mentions skyrocketing
with bullish keywords = fade signal for LONG entries. The opposite for
SHORTs.

Data source (free, public, rate-limited but fine for 60-min polling):
  https://www.reddit.com/r/wallstreetbets/hot.json?limit=100
Reddit requires a descriptive User-Agent; we comply.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from research.data_loader import DATA_DIR

CACHE_PATH = DATA_DIR / "wsb_cache.json"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour

USER_AGENT = "nq-trading-bot/1.0 (research only)"
SUBREDDIT = "wallstreetbets"

NQ_TICKERS = {
    "QQQ", "TQQQ", "QLD", "SQQQ",           # ETFs
    "AAPL", "MSFT", "NVDA", "AMZN", "META",  # heavy components
    "GOOGL", "GOOG", "TSLA", "AMD", "AVGO",
    "NFLX", "COST", "NQ",                    # direct futures
}

BULL_KEYWORDS = {
    "moon", "rocket", "🚀", "rally", "rip", "squeeze", "gamma",
    "buy the dip", "all time high", "ath", "call", "calls", "yolo",
    "diamond hands", "hodl", "bullish", "breakout",
}
BEAR_KEYWORDS = {
    "crash", "dump", "puts", "short", "bear", "bearish",
    "bubble", "recession", "correction", "collapse", "bagholder",
    "capitulation", "blood", "red day", "tank",
}

WSBBias = Literal["FADE_LONGS", "BEARISH", "NEUTRAL", "BULLISH", "FADE_SHORTS"]


@dataclass
class WSBSnapshot:
    as_of: str
    posts_scanned: int
    nq_mentions: int
    bull_score: float           # raw count
    bear_score: float
    avg_upvotes_nq: float
    contrarian_score: float     # -1 (bearish/fade longs) .. +1 (bullish/fade shorts)
    bias: WSBBias


def _fetch_hot_posts(limit: int = 100) -> list[dict]:
    url = f"https://www.reddit.com/r/{SUBREDDIT}/hot.json?limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"WSB fetch failed: {e}")
        return []
    children = data.get("data", {}).get("children", [])
    return [c.get("data", {}) for c in children]


_TICKER_RE = re.compile(r"\$?([A-Z]{2,5})\b")


def _count_mentions(text: str) -> set[str]:
    found: set[str] = set()
    for m in _TICKER_RE.findall(text or ""):
        if m in NQ_TICKERS:
            found.add(m)
    return found


def _keyword_score(text: str) -> tuple[int, int]:
    """Count bull vs bear keywords (case-insensitive)."""
    low = (text or "").lower()
    bulls = sum(1 for k in BULL_KEYWORDS if k in low)
    bears = sum(1 for k in BEAR_KEYWORDS if k in low)
    return bulls, bears


def fetch_wsb_snapshot(*, force_refresh: bool = False,
                       post_limit: int = 100) -> WSBSnapshot | None:
    if not force_refresh and CACHE_PATH.exists():
        try:
            d = json.loads(CACHE_PATH.read_text())
            ts = datetime.fromisoformat(d["as_of"])
            if (datetime.now(timezone.utc) - ts).total_seconds() < CACHE_TTL_SECONDS:
                return WSBSnapshot(**d)
        except Exception:
            pass

    posts = _fetch_hot_posts(limit=post_limit)
    if not posts:
        return None

    bull_total = 0
    bear_total = 0
    nq_mentions = 0
    nq_upvotes: list[float] = []

    for p in posts:
        title = p.get("title", "") or ""
        body = p.get("selftext", "") or ""
        combined = title + " " + body
        tickers = _count_mentions(combined)
        if tickers:
            nq_mentions += len(tickers)
            nq_upvotes.append(float(p.get("score", 0) or 0))
        bulls, bears = _keyword_score(combined)
        bull_total += bulls
        bear_total += bears

    total_keywords = bull_total + bear_total
    # Raw sentiment in [-1,+1] from bulls vs bears
    if total_keywords == 0:
        raw = 0.0
    else:
        raw = (bull_total - bear_total) / max(1, total_keywords)

    # Contrarian inversion: high bullish retail = fade → score becomes negative
    # but only scale it by mention volume (more mentions = stronger contrarian)
    mention_intensity = min(1.0, nq_mentions / 20.0)
    contrarian = -raw * mention_intensity

    bias: WSBBias
    if contrarian >= 0.5:
        bias = "FADE_SHORTS"      # retail is extreme bearish → we fade them = bullish
    elif contrarian >= 0.2:
        bias = "BULLISH"
    elif contrarian <= -0.5:
        bias = "FADE_LONGS"       # retail euphoric → we fade = bearish
    elif contrarian <= -0.2:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    avg_up = sum(nq_upvotes) / len(nq_upvotes) if nq_upvotes else 0.0
    snap = WSBSnapshot(
        as_of=datetime.now(timezone.utc).isoformat(),
        posts_scanned=len(posts),
        nq_mentions=nq_mentions,
        bull_score=bull_total,
        bear_score=bear_total,
        avg_upvotes_nq=float(avg_up),
        contrarian_score=float(contrarian),
        bias=bias,
    )
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(snap.__dict__))
    return snap


def _main() -> int:
    print("Fetching WSB hot posts...")
    snap = fetch_wsb_snapshot(force_refresh=True)
    if snap is None:
        print("WSB data unavailable.")
        return 1
    print(f"Posts scanned: {snap.posts_scanned}")
    print(f"NQ ticker mentions: {snap.nq_mentions}")
    print(f"Bull keywords: {snap.bull_score}   Bear keywords: {snap.bear_score}")
    print(f"Avg upvotes on NQ-tagged posts: {snap.avg_upvotes_nq:.0f}")
    print(f"Contrarian score: {snap.contrarian_score:+.3f}   bias={snap.bias}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

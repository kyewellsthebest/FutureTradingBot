"""Dukascopy USTECH (Nasdaq-100 CFD) tick-data downloader.

Pulls Dukascopy's free historical tick data for USATECHIDXUSD between two
dates, decodes the .bi5 binary format, and writes a single CSV ready for
the bot's existing tick-replay backtester (same format as
data/tick/NQ.03-26.Last.txt).

Why this dataset: 35 years of free tick data on the Nasdaq-100 underlying.
Price level is offset from CME's NQ/MNQ futures by the contango premium
(~50 pt) but every intraday pattern (momentum, retracements, regime,
volatility) is essentially identical. Sufficient to validate strategy
hypotheses across bull/bear/chop regimes without paying Databento.

Requirements:
  Python 3.8+ stdlib only. No pip install needed.

Usage:
  python research/dukascopy_download.py --start 2024-01-01 --end 2026-06-17
  python research/dukascopy_download.py --start 2020-01-01 --end 2026-06-17 --workers 16

Output:
  data/tick/USATECHIDXUSD_<start>_<end>.csv
  Format: YYYYMMDD HHMMSS NNN;last;bid;ask;volume
  (matches the format the bot's tick-replay scripts already parse)

Resumable: each downloaded hour is cached as a .bi5 file in
data/tick/_dukascopy_cache/, so re-running after a network blip skips
already-downloaded hours. Safe to Ctrl-C and re-run.

Cost: $0. Dukascopy publishes tick data publicly. No API key needed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import logging
import lzma
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger("dukascopy_download")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "tick" / "_dukascopy_cache"
OUT_DIR = ROOT / "data" / "tick"

# Dukascopy publishes ticks at predictable URLs. Months are 0-indexed
# (January = 00, December = 11) -- that's a quirk of the publisher, not
# a typo here.
URL_TEMPLATE = (
    "https://datafeed.dukascopy.com/datafeed/"
    "{instrument}/{year:04d}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
)

# Each tick is 5 big-endian 4-byte fields = 20 bytes.
TICK_STRUCT = struct.Struct(">IIIff")
TICK_SIZE = 20

# Price scale for the index (3 decimals). Dukascopy stores prices as ints
# multiplied by this factor. Different instruments use different factors;
# USATECHIDXUSD ticks come in at scale=1000 (3 decimal places).
PRICE_SCALE = 1000.0


def url_for(instrument: str, dh: dt.datetime) -> str:
    return URL_TEMPLATE.format(
        instrument=instrument,
        year=dh.year, month=dh.month - 1, day=dh.day, hour=dh.hour,
    )


def cache_path(instrument: str, dh: dt.datetime) -> Path:
    return (CACHE_DIR / instrument /
            f"{dh.year:04d}-{dh.month:02d}-{dh.day:02d}-{dh.hour:02d}h.bi5")


def download_one(instrument: str, dh: dt.datetime,
                  retries: int = 3) -> bytes | None:
    """Download a single hour's .bi5 file. Returns None on permanent failure
    (e.g. 404 for hours when the market was closed; that's normal)."""
    p = cache_path(instrument, dh)
    if p.exists():
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    url = url_for(instrument, dh)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "dukascopy_download/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
            p.write_bytes(body)
            return body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Market closed (weekend / holiday) -- this is normal,
                # don't waste retries.
                p.write_bytes(b"")
                return b""
            last_err = e
        except Exception as e:
            last_err = e
        time.sleep(2 ** attempt)
    logger.warning(f"give up {url}: {last_err!r}")
    return None


def decode_bi5(body: bytes, dh: dt.datetime) -> list[tuple]:
    """LZMA-decompress + parse a .bi5 hour into ticks.

    Returns list of (epoch_ms, bid, ask, ask_vol, bid_vol).
    """
    if not body:
        return []
    # Dukascopy uses raw LZMA1 (legacy format), not xz. Need an explicit
    # decompressor with LZMA_ALONE format and the right filter chain.
    try:
        try:
            raw = lzma.decompress(body, format=lzma.FORMAT_AUTO)
        except lzma.LZMAError:
            raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    except Exception as e:
        logger.warning(f"decompress {dh}: {e!r}")
        return []
    hour_start_ms = int(dh.timestamp() * 1000)
    out = []
    for i in range(0, len(raw) - TICK_SIZE + 1, TICK_SIZE):
        ms_delta, ask_raw, bid_raw, ask_vol, bid_vol = TICK_STRUCT.unpack_from(raw, i)
        ts_ms = hour_start_ms + ms_delta
        ask = ask_raw / PRICE_SCALE
        bid = bid_raw / PRICE_SCALE
        out.append((ts_ms, bid, ask, ask_vol, bid_vol))
    return out


def iter_hours(start: dt.datetime, end: dt.datetime):
    cur = start.replace(minute=0, second=0, microsecond=0,
                         tzinfo=dt.timezone.utc)
    end = end.replace(tzinfo=dt.timezone.utc) if end.tzinfo is None else end
    while cur <= end:
        yield cur
        cur += dt.timedelta(hours=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instrument", default="USATECHIDXUSD",
                     help="Dukascopy instrument id (default USATECHIDXUSD)")
    ap.add_argument("--start", required=True,
                     help="YYYY-MM-DD inclusive (UTC)")
    ap.add_argument("--end", required=True,
                     help="YYYY-MM-DD inclusive (UTC)")
    ap.add_argument("--workers", type=int, default=10,
                     help="parallel hour downloads (default 10, max ~20)")
    args = ap.parse_args()

    start = dt.datetime.fromisoformat(args.start)
    end = (dt.datetime.fromisoformat(args.end)
           + dt.timedelta(hours=23, minutes=59))
    hours = list(iter_hours(start, end))
    total = len(hours)
    logger.info(f"{args.instrument}: {total} hours from {start.date()} "
                f"to {end.date()}, {args.workers} workers")

    # Phase 1: parallel download into cache.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = [0]
    failures = [0]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download_one, args.instrument, h): h for h in hours}
        for fut in as_completed(futs):
            r = fut.result()
            done[0] += 1
            if r is None:
                failures[0] += 1
            if done[0] % 100 == 0 or done[0] == total:
                eta_s = (time.time() - t0) / done[0] * (total - done[0])
                logger.info(f"  download {done[0]}/{total}  "
                            f"({100*done[0]/total:.1f}%)  "
                            f"fails={failures[0]}  "
                            f"eta={eta_s/60:.1f}min")
    logger.info(f"download phase done in {(time.time()-t0)/60:.1f}min, "
                f"{failures[0]} permanent failures")

    # Phase 2: parse cache + write CSV in chronological order.
    out_path = (OUT_DIR /
                f"{args.instrument}_{start.date()}_{end.date()}.csv")
    n_ticks = 0
    n_hours = 0
    logger.info(f"writing {out_path} ...")
    with open(out_path, "w", newline="") as f:
        for h in hours:
            p = cache_path(args.instrument, h)
            if not p.exists():
                continue
            body = p.read_bytes()
            ticks = decode_bi5(body, h)
            if not ticks:
                continue
            n_hours += 1
            for ts_ms, bid, ask, ask_vol, bid_vol in ticks:
                t = dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc)
                # Format matches bot's tick-replay parser (e.g.
                # data/tick/NQ.03-26.Last.txt):
                #   YYYYMMDD HHMMSS NNN;last;bid;ask;volume
                # Dukascopy doesn't publish a "last" -- use mid as
                # a reasonable proxy. Volume = combined ask+bid CFD lots.
                last = (bid + ask) / 2.0
                vol = ask_vol + bid_vol
                stamp = (f"{t:%Y%m%d %H%M%S} "
                         f"{(ts_ms % 1000) * 10000:07d}")
                f.write(f"{stamp};{last:.3f};{bid:.3f};"
                        f"{ask:.3f};{vol:.0f}\n")
                n_ticks += 1
            if n_hours % 100 == 0:
                logger.info(f"  parsed {n_hours} hours, "
                            f"{n_ticks/1e6:.2f}M ticks so far")
    logger.info(f"DONE: {n_ticks:,} ticks across {n_hours} hours -> {out_path}")
    size_mb = out_path.stat().st_size / 1024 / 1024
    logger.info(f"output size: {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

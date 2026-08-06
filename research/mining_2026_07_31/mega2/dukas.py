"""Dukascopy tick downloader that cannot hang.

The previous attempt used tick-vault's own orchestrator and burned five hours
and thirty-eight minutes producing nothing. The logs say exactly why, and it
was not slowness:

  10:42:50  Rate limited (429) ... 00h_ticks.bi5   <- ten of these, at once
  10:43:49  Metadata worker timeout - assuming parent crashed
  16:21:36  The operation was canceled.

Two seconds in, Dukascopy 429'd all ten concurrent workers. A minute later the
metadata worker decided its parent had died and exited. Every download worker
then exhausted its three retries and died too -- and the orchestrator's main
loop sits on `await downloader_output_queue.get()`, a queue with no remaining
producers, checking for worker exceptions only AFTER that await returns. It
never returned. The job did not download slowly for five hours; it downloaded
for sixty seconds and then deadlocked in silence.

So this does not use that orchestrator. The wire format is trivial and
documented by the library itself, so the whole thing is forty lines:

  URL    datafeed.dukascopy.com/datafeed/{SYM}/{YYYY}/{MM-1:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
         -- months are ZERO INDEXED, January is 00
  BODY   LZMA-alone, decompressing to 20-byte big-endian records:
         u4 ms-since-hour, u4 ask, u4 bid, f4 ask_vol, f4 bid_vol
  SCALE  prices multiply by the symbol's pipet size (1e-5 majors, 1e-3 JPY/gold)

Three rules make it unhangable, each one a direct answer to a failure above:

  BOUNDED CONCURRENCY. Four, not ten. Ten got 429'd in two seconds.
  REAL BACKOFF. A 429 sleeps and retries six times, not three, and the sleep
    grows. Empty hours (weekends, holidays) are 404 or zero bytes and are not
    errors -- FX closes.
  A DEADLINE. Every request has a socket timeout and the whole month has a
    wall-clock budget. When the budget is gone the month writes what it has and
    returns. Nothing in here can wait forever on anything.

Usage: python dukas.py SYMBOL YYYY-MM OUTPUT.parquet
"""
import io
import lzma
import os
import random
import sys
import time
import urllib.error
import urllib.request
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

BASE = "https://datafeed.dukascopy.com/datafeed"
# from tick_vault.constants.PIPET_SIZE_REGISTRY -- a JPY pipet is 1e-3, not 1e-5
PIPET = {"EURUSD": 1e-5, "GBPUSD": 1e-5, "AUDUSD": 1e-5, "NZDUSD": 1e-5,
         "USDCAD": 1e-5, "USDCHF": 1e-5, "USDJPY": 1e-3,
         "XAUUSD": 1e-3, "BTCUSD": 0.1, "ETHUSD": 0.1}

WORKERS = int(os.environ.get("DUKAS_WORKERS", "4"))
TRIES = int(os.environ.get("DUKAS_TRIES", "6"))
SOCK_TIMEOUT = float(os.environ.get("DUKAS_SOCK_TIMEOUT", "30"))
BUDGET_S = float(os.environ.get("DUKAS_BUDGET_S", "2400"))   # 40 min a month

REC = np.dtype([("t", ">u4"), ("ask", ">u4"), ("bid", ">u4"),
                ("av", ">f4"), ("bv", ">f4")])

T0 = time.time()
STATS = {"ok": 0, "empty": 0, "gone": 0, "failed": 0, "rate": 0, "skipped": 0}


def hour_url(sym, t):
    return (f"{BASE}/{sym}/{t.year}/{t.month - 1:02d}/{t.day:02d}/"
            f"{t.hour:02d}h_ticks.bi5")


def fetch(sym, t):
    """One hour of ticks, or None. Never raises, never blocks indefinitely."""
    if time.time() - T0 > BUDGET_S:
        STATS["skipped"] += 1
        return None
    url = hour_url(sym, t)
    for attempt in range(TRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=SOCK_TIMEOUT) as r:
                body = r.read()
            if not body:                    # market closed this hour
                STATS["empty"] += 1
                return None
            raw = np.frombuffer(lzma.decompress(body), dtype=REC)
            STATS["ok"] += 1
            return t, raw
        except urllib.error.HTTPError as e:
            if e.code in (404, 416):        # no such hour -- weekend, holiday
                STATS["gone"] += 1
                return None
            if e.code in (429, 503, 500, 502):
                STATS["rate"] += 1
                # grow the wait, and jitter it so four workers do not all
                # come back at the same instant and 429 each other again
                time.sleep(min(60.0, 1.5 * (2 ** attempt)) * (0.5 + random.random()))
                continue
            STATS["failed"] += 1
            return None
        except (urllib.error.URLError, lzma.LZMAError, OSError, ValueError):
            time.sleep(min(30.0, 1.0 * (2 ** attempt)) * (0.5 + random.random()))
    STATS["failed"] += 1
    return None


def month(sym, year, mon, out):
    scale = PIPET.get(sym)
    if scale is None:
        print(f"no pipet scale registered for {sym}", flush=True)
        return 1
    ndays = monthrange(year, mon)[1]
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    hours = [start + timedelta(hours=h) for h in range(ndays * 24)]
    print(f"{sym} {year}-{mon:02d}: {len(hours)} hours, {WORKERS} workers, "
          f"{BUDGET_S/60:.0f} min budget", flush=True)

    got = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, r in enumerate(ex.map(lambda t: fetch(sym, t), hours)):
            if r is not None:
                got.append(r)
            if (i + 1) % 200 == 0:
                print(f"  {i+1}/{len(hours)}  ok={STATS['ok']} "
                      f"empty={STATS['empty']} 404={STATS['gone']} "
                      f"429={STATS['rate']} fail={STATS['failed']} "
                      f"skip={STATS['skipped']}  {time.time()-T0:.0f}s",
                      flush=True)

    if not got:
        print(f"{sym} {year}-{mon:02d}: NOTHING -- {STATS}", flush=True)
        return 2

    got.sort(key=lambda x: x[0])
    ts, bid, ask, bv, av = [], [], [], [], []
    for t, raw in got:
        if not len(raw):
            continue
        base = np.datetime64(t.replace(tzinfo=None), "ms")
        ts.append(base + raw["t"].astype(np.int64).astype("timedelta64[ms]"))
        ask.append(raw["ask"].astype(np.float64) * scale)
        bid.append(raw["bid"].astype(np.float64) * scale)
        av.append(np.round(raw["av"].astype(np.float64) * 1e6).astype(np.int64))
        bv.append(np.round(raw["bv"].astype(np.float64) * 1e6).astype(np.int64))
    if not ts:
        print(f"{sym} {year}-{mon:02d}: all hours decoded empty", flush=True)
        return 2

    d = pd.DataFrame({"time": np.concatenate(ts),
                      "bid": np.concatenate(bid), "ask": np.concatenate(ask),
                      "bid_volume": np.concatenate(bv),
                      "ask_volume": np.concatenate(av)})
    d = d.sort_values("time", kind="stable").reset_index(drop=True)

    # sanity, printed before anything downstream trusts the file: a crossed or
    # absurd spread means the pipet scale is wrong for this symbol
    sp = (d.ask - d.bid).values
    pip = 10.0 * scale
    print(f"{sym} {year}-{mon:02d}: {len(d):,} ticks, "
          f"{d.time.min()} .. {d.time.max()}", flush=True)
    print(f"  spread pips: median {np.median(sp)/pip:.2f} "
          f"mean {sp.mean()/pip:.2f} p99 {np.percentile(sp,99)/pip:.2f} "
          f"crossed {(sp < 0).mean()*100:.3f}%", flush=True)
    d.to_parquet(out, compression="zstd", index=False)
    print(f"  wrote {out} ({os.path.getsize(out)/1e6:.1f} MB) "
          f"[{STATS}] in {time.time()-T0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sym = sys.argv[1].upper()
    y, m = sys.argv[2].split("-")
    out = sys.argv[3] if len(sys.argv) > 3 else f"{sym}_{y}{m}.parquet"
    sys.exit(month(sym, int(y), int(m), out))

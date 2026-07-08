"""Download the last N days of MNQ futures TRADES (ticks) from Polygon.

One parquet per UTC day -> data/tick/week/{TICKER}_{YYYYMMDD}.parquet
(ts ns, price, size). Used by the no-lookahead live-bot simulation:
replaying the bot's real code over last week's real tick stream.

Env:  POLYGON_API (key), TICKER (default MNQU6), DAYS (default 9).
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

KEY = os.environ.get("POLYGON_API") or os.environ.get("POLYGON_API_KEY")
TICKER = os.environ.get("TICKER", "MNQU6").strip()
DAYS = int(os.environ.get("DAYS", "9"))
DATA = os.environ.get("DATA", "trades").strip().lower()   # trades | quotes
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tick" / "week"
OUT.mkdir(parents=True, exist_ok=True)
LIMIT = 50000
NS = 1_000_000_000


def _get(url, tries=8):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(min(90, 2 ** attempt * 3)); continue
            try: body = json.loads(e.read().decode())
            except Exception: body = {}
            return None, f"HTTP {e.code}: {body.get('message') or body.get('error')}"
        except Exception as e:
            if attempt < tries - 1: time.sleep(4); continue
            return None, f"{type(e).__name__}: {e}"
    return None, "exhausted"


def fetch_day(day_start: datetime) -> None:
    day = day_start.strftime("%Y%m%d")
    prefix = f"Q_{TICKER}" if DATA == "quotes" else TICKER
    path = OUT / f"{prefix}_{day}.parquet"
    if path.exists():
        print(f"{day}: already have {pd.read_parquet(path).shape[0]:,} rows", flush=True)
        return
    s_ns = int(day_start.timestamp()) * NS
    e_ns = int((day_start + timedelta(days=1)).timestamp()) * NS
    url = (f"https://api.polygon.io/futures/v1/{DATA}/{TICKER}"
           f"?timestamp.gte={s_ns}&timestamp.lt={e_ns}"
           f"&order=asc&limit={LIMIT}&apiKey={KEY}")
    rows, page = [], 0
    while url:
        data, err = _get(url)
        if err:
            print(f"{day}: {err}", flush=True)
            break
        for r in (data.get("results") or []):
            try:
                if DATA == "quotes":
                    rows.append((int(r["timestamp"]),
                                 float(r.get("bid_price") or 0),
                                 float(r.get("ask_price") or 0),
                                 int(r.get("bid_size") or 0),
                                 int(r.get("ask_size") or 0)))
                else:
                    rows.append((int(r["timestamp"]), float(r["price"]),
                                 int(r.get("size", 1))))
            except Exception:
                continue
        page += 1
        nxt = data.get("next_url")
        url = (nxt + f"&apiKey={KEY}") if nxt else None
        if page % 10 == 0:
            print(f"{day}: {len(rows):,} rows (page {page})...", flush=True)
    cols = (["ts", "bid", "ask", "bid_size", "ask_size"]
            if DATA == "quotes" else ["ts", "price", "size"])
    df = pd.DataFrame(rows, columns=cols)
    df.to_parquet(path, compression="zstd", index=False)
    print(f"{day}: COMPLETE {len(df):,} rows -> {path.name}", flush=True)


def main():
    if not KEY:
        print("NO POLYGON KEY. export POLYGON_API='...'")
        sys.exit(1)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                               microsecond=0)
    for d in range(DAYS, -1, -1):
        fetch_day(today - timedelta(days=d))
    total = sum(pd.read_parquet(f).shape[0] for f in OUT.glob(f"{TICKER}_*.parquet"))
    print(f"ALL DONE: {total:,} ticks across "
          f"{len(list(OUT.glob(f'{TICKER}_*.parquet')))} day files")


if __name__ == "__main__":
    main()

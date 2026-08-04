"""Download NQ futures TRADES (ticks) from Polygon.

Two modes:
  * SINGLE CONTRACT (for GitHub Actions matrix): set env TICKER=NQU3
      -> downloads just that contract's front-month window to
         data/tick/raw/<TICKER>.parquet, with mid-contract checkpointing
         (resumes if interrupted; re-run is safe).
  * ALL CONTRACTS (local/Codespace): no TICKER env
      -> loops every quarterly contract, then stitches a continuous
         front-month series to data/tick/nq_ticks_2p5y.parquet.

Needs:  export POLYGON_API="your_key"   (pip install pandas pyarrow)
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

KEY = os.environ.get("POLYGON_API") or os.environ.get("POLYGON_API_KEY")
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "tick" / "raw"; RAW.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "data" / "tick" / "nq_ticks_2p5y.parquet"

HISTORY_DAYS = 1010                      # ~2.75 years
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}
# Root symbol. Derived from TICKER when one is given, so the same script
# serves any product -- the contract-window logic is identical across roots.
PRODUCT = (os.environ.get("PRODUCT")
           or (os.environ.get("TICKER", "NQ")[:-2] if os.environ.get("TICKER")
               else "NQ")).upper()
LIMIT = 50000
NS = 1_000_000_000
CHECKPOINT_PAGES = 40                    # save partial progress this often

def _third_friday(y, m):
    d = date(y, m, 1)
    return date(y, m, 1 + ((4 - d.weekday()) % 7) + 14)

def quarterly_tickers():
    today = date.today()
    start = today - timedelta(days=HISTORY_DAYS + 120)
    end = today + timedelta(days=10)
    out = []
    for year in range(start.year, end.year + 1):
        for month, code in MONTH_CODE.items():
            exp = _third_friday(year, month)
            if start <= exp <= end:
                out.append((f"{PRODUCT}{code}{year % 10}", exp))
    out.sort(key=lambda t: t[1])
    return out

def _window_for(ticker):
    """[prev_expiry, own_expiry) front-month window for one ticker (ns)."""
    tk = quarterly_tickers()
    prev = None
    for i, (t, exp) in enumerate(tk):
        if t == ticker:
            start = prev or (exp - timedelta(days=130))
            return (int(time.mktime(start.timetuple())) * NS,
                    int(time.mktime(exp.timetuple())) * NS, start, exp)
        prev = exp
    raise SystemExit(f"unknown ticker {ticker}; known: {[t for t,_ in tk]}")

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

def fetch_contract(ticker):
    cache = RAW / f"{ticker}.parquet"
    cursor_f = RAW / f"{ticker}.cursor"          # exists => partial / resumable
    if cache.exists() and not cursor_f.exists():
        print(f"{ticker}: already complete ({pd.read_parquet(cache).shape[0]:,} trades)", flush=True)
        return
    s_ns, e_ns, s_d, e_d = _window_for(ticker)
    rows = []
    if cache.exists() and cursor_f.exists():       # resume
        rows = list(pd.read_parquet(cache).itertuples(index=False, name=None))
        url = cursor_f.read_text().strip()
        print(f"{ticker}: RESUME {len(rows):,} trades, cursor restored", flush=True)
    else:
        url = (f"https://api.polygon.io/futures/v1/trades/{ticker}"
               f"?timestamp.gte={s_ns}&timestamp.lt={e_ns}"
               f"&order=asc&limit={LIMIT}&apiKey={KEY}")
        print(f"{ticker}: START window {s_d} -> {e_d}", flush=True)
    page = 0
    while url:
        data, err = _get(url)
        if err:
            print(f"{ticker}: {err}", flush=True); break
        for r in (data.get("results") or []):
            try: rows.append((int(r["timestamp"]), float(r["price"]), int(r.get("size", 1))))
            except Exception: continue
        page += 1
        nxt = data.get("next_url")
        url = (nxt + f"&apiKey={KEY}") if nxt else None
        if page % CHECKPOINT_PAGES == 0:
            pd.DataFrame(rows, columns=["ts","price","size"]).to_parquet(cache, compression="zstd", index=False)
            cursor_f.write_text(url or "")
            print(f"{ticker}: {len(rows):,} trades (page {page}) [checkpoint]", flush=True)
    df = pd.DataFrame(rows, columns=["ts","price","size"])
    df = df[(df.ts >= s_ns) & (df.ts < e_ns)]
    df.to_parquet(cache, compression="zstd", index=False)
    if cursor_f.exists(): cursor_f.unlink()         # mark complete
    print(f"{ticker}: COMPLETE {len(df):,} trades -> {cache.name}", flush=True)

def stitch():
    parts = []
    for ticker, _ in quarterly_tickers():
        f = RAW / f"{ticker}.parquet"
        if f.exists(): parts.append(pd.read_parquet(f))
    if not parts: print("no contract files to stitch"); return
    full = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
    full = full[~full.ts.duplicated(keep="last")]
    full.to_parquet(OUT, compression="zstd", index=False)
    print(f"STITCHED {len(full):,} ticks -> {OUT} ({OUT.stat().st_size/1e6:.0f} MB)")
    print(f"range {pd.to_datetime(full.ts.min())} -> {pd.to_datetime(full.ts.max())}")

def main():
    if not KEY: print("NO POLYGON KEY. export POLYGON_API='...'"); sys.exit(1)
    tk = os.environ.get("TICKER")
    if tk:
        fetch_contract(tk.strip())
    else:
        for t, _ in quarterly_tickers():
            fetch_contract(t)
        stitch()

if __name__ == "__main__":
    main()

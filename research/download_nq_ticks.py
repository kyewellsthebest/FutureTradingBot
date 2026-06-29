"""Download ~2.5 years of NQ futures TRADES (ticks) from Polygon, stitch a
continuous front-month series, save as Parquet. Run in a GitHub Codespace
(open internet) with the Polygon key:

    export POLYGON_API="your_key"
    pip install pandas pyarrow
    nohup python -m research.download_nq_ticks > dl.log 2>&1 &
    tail -f dl.log

Output: data/tick/nq_ticks_2p5y.parquet  (columns: ts[ns], price, size)
Per-contract files are cached in data/tick/raw/ so it RESUMES if interrupted
(just re-run). Bid/ask are modelled as price +/- half a tick in the sim
(NQ front-month spread is ~1 tick in liquid hours); pull quotes separately
only if we later need exact spreads.
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

HISTORY_DAYS = 920                       # ~2.5 years
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}
PRODUCT = "NQ"
LIMIT = 50000
NS = 1_000_000_000

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

def _get(url, tries=6):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                w = min(60, 2 ** attempt * 3); time.sleep(w); continue
            try: body = json.loads(e.read().decode())
            except Exception: body = {}
            return None, f"HTTP {e.code}: {body.get('message') or body.get('error')}"
        except Exception as e:
            if attempt < tries - 1: time.sleep(3); continue
            return None, f"{type(e).__name__}: {e}"
    return None, "exhausted"

def fetch_contract(ticker, t_start_ns, t_end_ns):
    """Page all trades for ticker in [t_start_ns, t_end_ns). Resumable cache."""
    cache = RAW / f"{ticker}.parquet"
    if cache.exists():
        print(f"  {ticker}: cached", flush=True); return pd.read_parquet(cache)
    rows = []
    url = (f"https://api.polygon.io/futures/v1/trades/{ticker}"
           f"?timestamp.gte={t_start_ns}&timestamp.lt={t_end_ns}"
           f"&order=asc&limit={LIMIT}&apiKey={KEY}")
    page = 0
    while url:
        data, err = _get(url)
        if err:
            print(f"  {ticker}: {err}", flush=True)
            break
        res = data.get("results") or []
        for r in res:
            try: rows.append((int(r["timestamp"]), float(r["price"]), int(r.get("size", 1))))
            except Exception: continue
        page += 1
        if page % 20 == 0:
            print(f"  {ticker}: {len(rows):,} trades so far (page {page})", flush=True)
        nxt = data.get("next_url")
        url = (nxt + f"&apiKey={KEY}") if nxt else None
    df = pd.DataFrame(rows, columns=["ts", "price", "size"])
    df.to_parquet(cache, compression="zstd", index=False)
    print(f"  {ticker}: DONE {len(df):,} trades -> {cache.name}", flush=True)
    return df

def main():
    if not KEY:
        print("NO POLYGON KEY. export POLYGON_API='...'"); sys.exit(1)
    t0 = time.time()
    tickers = quarterly_tickers()
    print(f"contracts: {[t[0] for t in tickers]}", flush=True)
    # front-month stitch: contract active from prior expiry -> its own expiry
    parts = []
    prev_exp = None
    for ticker, exp in tickers:
        win_start = prev_exp or (exp - timedelta(days=120))
        s_ns = int(time.mktime(win_start.timetuple())) * NS
        e_ns = int(time.mktime(exp.timetuple())) * NS
        print(f"{ticker}: window {win_start} -> {exp}", flush=True)
        df = fetch_contract(ticker, s_ns, e_ns)
        if df is not None and len(df):
            df = df[(df.ts >= s_ns) & (df.ts < e_ns)]
            parts.append(df)
        prev_exp = exp
        print(f"  elapsed {time.time()-t0:.0f}s", flush=True)
    if not parts:
        print("NO DATA fetched"); sys.exit(1)
    full = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
    full = full[~full.ts.duplicated(keep="last")]
    full.to_parquet(OUT, compression="zstd", index=False)
    print(f"\nDONE {time.time()-t0:.0f}s | {len(full):,} ticks", flush=True)
    print(f"range: {pd.to_datetime(full.ts.min())} -> {pd.to_datetime(full.ts.max())}", flush=True)
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.0f} MB)", flush=True)
    print("\nNEXT: publish as a release so the research session can grab it:")
    print('  split -b 1900m', OUT, 'nq_ticks_part_   # only if >2GB')
    print('  gh release create nq-ticks-2p5y', OUT, '-t "NQ 2.5yr ticks" -n "Polygon trades, continuous front-month"')

if __name__ == "__main__":
    main()

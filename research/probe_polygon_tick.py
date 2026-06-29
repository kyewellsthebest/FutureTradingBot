"""Probe: does this Polygon plan provide NQ futures TICK (trades/quotes)?

Run in a GitHub Codespace (open internet). Needs the Polygon key:
    export POLYGON_API="your_key_here"
    python -m research.probe_polygon_tick

It tries the trades and quotes endpoints for a recent NQ contract and a
recent contract for a single day, and reports: HTTP status, any error
message, how many records came back, the FIELDS of a sample record (so we
know if bid/ask are included), and whether pagination (next_url) exists.

From the output we decide if we can bulk-download 2.5yr of NQ ticks here.
"""
from __future__ import annotations
import json, os, sys, urllib.request, urllib.error
from datetime import date

KEY = os.environ.get("POLYGON_API") or os.environ.get("POLYGON_API_KEY")

# Candidate NQ outright contracts (code: H=Mar M=Jun U=Sep Z=Dec, last digit=year).
# Try a couple recent ones so at least one is in-range for a given test day.
CONTRACTS = ["NQM6", "NQH6", "NQU5", "NQM5"]
TEST_DAY = "2026-05-15"   # a normal trading day inside our window

def _get(url):
    safe = url.split("apiKey=")[0] + "apiKey=***"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "probe/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read().decode())
        except Exception: body = {}
        return None, f"HTTP {e.code}: {body.get('message') or body.get('error') or safe}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def probe(label, url_tmpl):
    print(f"\n===== {label} =====")
    for c in CONTRACTS:
        url = url_tmpl.format(ticker=c) + f"&apiKey={KEY}"
        data, err = _get(url)
        if err:
            print(f"  {c}: {err}")
            continue
        res = (data or {}).get("results") or []
        status = (data or {}).get("status")
        nxt = bool((data or {}).get("next_url"))
        print(f"  {c}: OK status={status} results={len(res)} next_url={nxt}")
        if res:
            print(f"     sample fields: {list(res[0].keys())}")
            print(f"     sample record: {json.dumps(res[0])[:300]}")
            return True   # found a working contract+endpoint
    return False

def main():
    if not KEY:
        print("NO POLYGON KEY. Run:  export POLYGON_API='your_key'  then re-run.")
        sys.exit(1)
    print(f"key present (len {len(KEY)}). test day {TEST_DAY}")
    base = "https://api.polygon.io/futures/v1"
    # endpoint guesses — we report whichever works
    any_trades = probe("TRADES /futures/v1/trades/{ticker}",
          base + "/trades/{ticker}?timestamp=" + TEST_DAY + "&limit=5")
    any_quotes = probe("QUOTES /futures/v1/quotes/{ticker}",
          base + "/quotes/{ticker}?timestamp=" + TEST_DAY + "&limit=5")
    # fallback: aggs at 1-second (a tick proxy) — confirms the plan + ticker
    any_secs = probe("1-SECOND AGGS (proxy/confirm) /futures/v1/aggs/{ticker}",
          base + "/aggs/{ticker}?resolution=1_second&limit=5")
    print("\n===== VERDICT =====")
    print(f"  trades available: {any_trades}")
    print(f"  quotes (bid/ask) available: {any_quotes}")
    print(f"  1-second aggs available: {any_secs}")
    if any_trades:
        print("  -> we CAN bulk-download NQ ticks from Polygon. I'll write the full downloader.")
    elif any_secs:
        print("  -> no raw trades, but 1-second bars work = a strong tick-proxy. Usable.")
    else:
        print("  -> Polygon plan lacks futures tick. We'll need NinjaTrader/Databento.")

if __name__ == "__main__":
    main()

"""What do your subscriptions ACTUALLY give us? Run this instead of guessing.

RUN ON YOUR MACHINE. This container's egress policy blocks polygon.io,
partner.tradovate.com and hist.databento.com, so I cannot test any of it from
here -- and vendor documentation is frequently wrong about what a given plan
tier includes anyway. This probes each credential and reports what came back.

    pip install requests websocket-client
    export POLYGON_KEY=...
    export TRADOVATE_USER=...  TRADOVATE_PASS=...
    export TRADOVATE_CID=...   TRADOVATE_SEC=...      # from API Access page
    python check_access.py

It writes access_report.json. Send me that file and I will know exactly which
of the data types are reachable, at what latency, without either of us
speculating.

NOTHING IS PURCHASED AND NOTHING IS ORDERED. Every call is a read. The
Tradovate section talks to the DEMO host only.
"""
import json
import os
import sys
import time

REPORT = {}


def note(section, key, ok, detail=""):
    REPORT.setdefault(section, {})[key] = {"ok": bool(ok), "detail": str(detail)[:400]}
    print(f"  [{'OK ' if ok else 'no '}] {section:11s} {key:34s} {str(detail)[:90]}",
          flush=True)


# --------------------------------------------------------------- POLYGON
def polygon():
    import requests
    key = os.environ.get("POLYGON_KEY")
    if not key:
        print("POLYGON_KEY not set, skipping\n")
        return
    print("POLYGON")
    S = requests.Session()
    S.params = {"apiKey": key}

    def get(url, **kw):
        try:
            r = S.get(url, timeout=30, params={**S.params, **kw})
            return r.status_code, (r.json() if "json" in
                                   r.headers.get("content-type", "") else r.text)
        except Exception as e:                                   # noqa: BLE001
            return 0, str(e)

    # which futures products exist, and what the plan will actually serve
    sc, js = get("https://api.polygon.io/futures/vX/products", limit=5)
    note("polygon", "futures products list", sc == 200,
         f"HTTP {sc} " + (str(js)[:120] if sc != 200 else
                          f"{len(js.get('results', []))} products"))

    for what, url in [
        ("futures contracts (NQ)",
         "https://api.polygon.io/futures/vX/contracts"),
        ("futures TRADES",
         "https://api.polygon.io/futures/vX/trades/NQZ5"),
        ("futures QUOTES  <-- the key one",
         "https://api.polygon.io/futures/vX/quotes/NQZ5"),
        ("futures aggregates",
         "https://api.polygon.io/futures/vX/aggs/NQZ5"),
    ]:
        sc, js = get(url, limit=2)
        n = len(js.get("results", [])) if isinstance(js, dict) else 0
        note("polygon", what, sc == 200 and n > 0,
             f"HTTP {sc}" + (f", {n} rows, fields="
                             f"{list(js['results'][0])[:9]}" if n else
                             f" {str(js)[:110]}"))

    # options: this is what a dealer-gamma model would be built from
    sc, js = get("https://api.polygon.io/v3/snapshot/options/I:NDX", limit=2)
    has_greek = "greeks" in str(js)[:4000]
    note("polygon", "OPTIONS snapshot w/ greeks+OI", sc == 200 and has_greek,
         f"HTTP {sc}, greeks present={has_greek}")

    sc, js = get("https://api.polygon.io/v3/snapshot/indices", **{"ticker": "I:NDX"})
    note("polygon", "index level (NDX cash)", sc == 200, f"HTTP {sc}")

    # is the plan real-time or delayed? last trade timestamp answers it.
    sc, js = get("https://api.polygon.io/v2/last/trade/QQQ")
    lag = None
    try:
        lag = time.time() - js["results"]["t"] / 1e3
    except Exception:                                            # noqa: BLE001
        pass
    note("polygon", "REAL-TIME? (QQQ last trade age)", lag is not None and lag < 90,
         f"{lag:.0f}s old" if lag is not None else f"HTTP {sc}")
    print()


# ------------------------------------------------------------- TRADOVATE
def tradovate():
    import requests
    u, p = os.environ.get("TRADOVATE_USER"), os.environ.get("TRADOVATE_PASS")
    cid, sec = os.environ.get("TRADOVATE_CID"), os.environ.get("TRADOVATE_SEC")
    if not (u and p and cid and sec):
        print("TRADOVATE_* not all set, skipping\n")
        return
    print("TRADOVATE (demo host)")
    base = "https://demo.tradovateapi.com/v1"
    try:
        r = requests.post(f"{base}/auth/accessTokenRequest", timeout=30, json={
            "name": u, "password": p, "appId": "ResearchProbe", "appVersion": "1.0",
            "cid": int(cid), "sec": sec, "deviceId": "research-probe-001"})
        tok = r.json().get("accessToken")
        mdtok = r.json().get("mdAccessToken")
    except Exception as e:                                       # noqa: BLE001
        note("tradovate", "auth", False, e)
        return
    note("tradovate", "auth", bool(tok), "got token" if tok else str(r.text)[:150])
    if not tok:
        return
    H = {"Authorization": f"Bearer {tok}"}

    # the REST side: this is where the fill logs live
    for what, path in [("account list", "/account/list"),
                       ("FILLS  <-- cost analysis", "/fill/list"),
                       ("ORDERS", "/order/list"),
                       ("orderVersion (original limit px)", "/orderVersion/list"),
                       ("executionReport (exch timestamps)", "/executionReport/list"),
                       ("fillPair (round-turn P&L)", "/fillPair/list"),
                       ("cashBalance", "/cashBalance/list")]:
        try:
            rr = requests.get(base + path, headers=H, timeout=30)
            js = rr.json()
            n = len(js) if isinstance(js, list) else 0
            note("tradovate", what, rr.status_code == 200,
                 f"HTTP {rr.status_code}, {n} rows" +
                 (f", fields={list(js[0])[:10]}" if n else ""))
        except Exception as e:                                   # noqa: BLE001
            note("tradovate", what, False, e)

    # the live side: quotes and DOM over the market-data websocket
    try:
        import websocket
    except ImportError:
        note("tradovate", "websocket lib", False, "pip install websocket-client")
        return
    got = {"quote": None, "dom": None}
    try:
        ws = websocket.create_connection("wss://md-demo.tradovateapi.com/v1/websocket",
                                         timeout=25)
        ws.recv()                                    # server 'o' frame
        ws.send(f"authorize\n0\n\n{mdtok or tok}")
        deadline = time.time() + 8
        while time.time() < deadline:
            if '"i":0' in ws.recv():
                break
        ws.send('md/subscribeQuote\n1\n\n{"symbol":"NQZ5"}')
        ws.send('md/subscribeDOM\n2\n\n{"symbol":"NQZ5"}')
        deadline = time.time() + 25
        while time.time() < deadline and not (got["quote"] and got["dom"]):
            m = ws.recv()
            if '"quotes"' in m and not got["quote"]:
                got["quote"] = m[:600]
            if '"doms"' in m and not got["dom"]:
                got["dom"] = m[:900]
        ws.close()
    except Exception as e:                                       # noqa: BLE001
        note("tradovate", "market data websocket", False, e)

    note("tradovate", "LIVE QUOTES (bid/ask)", bool(got["quote"]),
         got["quote"] or "no quote frame in 25s")
    lv = 0
    if got["dom"]:
        try:
            lv = len(json.loads(got["dom"].split("\n", 1)[-1])[0]["d"]["doms"][0]["bids"])
        except Exception:                                        # noqa: BLE001
            lv = got["dom"].count('"price"') // 2
    note("tradovate", "LIVE DOM (depth)  <-- how many levels?", bool(got["dom"]),
         f"~{lv} levels per side | " + (got["dom"] or "no dom frame in 25s"))
    print()


if __name__ == "__main__":
    print("Probing what your subscriptions actually serve. Nothing is bought.\n")
    polygon()
    tradovate()
    json.dump(REPORT, open("access_report.json", "w"), indent=2)
    ok = sum(v["ok"] for s in REPORT.values() for v in s.values())
    tot = sum(len(s) for s in REPORT.values())
    print(f"{ok}/{tot} checks passed -> access_report.json")
    print("Send me that file and I will know exactly what we can build.")
    sys.exit(0)

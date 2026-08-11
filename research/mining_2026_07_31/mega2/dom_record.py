"""Record the live order book, and measure how slow we actually are.

WHY RECORD RATHER THAN BUY. The passive-entry result measured today is worth
+$0.25 a trade, and that number is soft for one specific reason: a fill is
counted when price TOUCHES the limit, but touching is not filling when forty
contracts are ahead of you in the queue. Guessing conservatively -- requiring
price to trade a full tick through -- moved the answer from +$0.88 to +$0.25.
A 3.5x uncertainty band sits on the single largest lever available, and depth
is what collapses it.

Tradovate serves depth live, free, with the account already in hand. It has no
history, so it has to be recorded, and recording starts paying the day it
begins.

WHAT GETS WRITTEN. A snapshot of both sides every SNAP_MS, plus every quote
change. That is enough to answer the question that matters -- when price
reached my limit, how much was resting there, and did enough trade through to
have filled me -- without storing every message.

THE LATENCY NUMBER, which is the other thing nobody here has measured. The
~2 second figure this repo costs against came from an old diagnostic, and
today's fill dump could not confirm it: every order in the account is a limit
or a stop, so order-to-fill measures QUEUE WAIT (548 seconds median) rather
than system latency. This times the actual round trips instead:

    REST  -- request sent to response parsed
    WS    -- how stale each book snapshot is when it arrives, from the
             exchange timestamp inside it

Those two bound what an order would experience. If they come back at tens of
milliseconds then the 2 second figure was an implementation problem and not a
floor -- worth knowing before anyone pays for colocation, especially since the
lead-lag study says cross-market information is worth under a cent a trade even
at zero latency. Latency buys queue position, not prediction.
"""
import json
import os
import ssl
import sys
import threading
import time

import pandas as pd

DUR = int(os.environ.get("DUR_MIN", "300")) * 60
SNAP_MS = int(os.environ.get("SNAP_MS", "250"))
SYMBOL = os.environ.get("SYMBOL", "")
OUT = os.environ.get("OUT_DIR", "data/dom")
HOST = os.environ.get("TV_HOST", "demo")
U, P = os.environ.get("TRADOVATE_USER"), os.environ.get("TRADOVATE_PASS")
CID, SEC = os.environ.get("TRADOVATE_CID"), os.environ.get("TRADOVATE_SEC")
DEV = os.environ.get("TRADOVATE_DEVID", "dom-recorder-001")


def auth():
    import requests
    t0 = time.time()
    r = requests.post(f"https://{HOST}.tradovateapi.com/v1/auth/accesstokenrequest",
                      json={"name": U, "password": P, "appId": "DOMRecorder",
                            "appVersion": "1.0", "deviceId": DEV,
                            "cid": CID, "sec": SEC}, timeout=30)
    j = r.json()
    if not j.get("accessToken"):
        sys.exit(f"auth failed: {json.dumps(j)[:300]}")
    # THE ENTITLEMENT TELL. Tradovate returns a SEPARATE mdAccessToken only
    # when the account is entitled to market data. If it is absent, the code
    # below would send the ordinary access token to the market-data socket and
    # the server would hang up -- which is exactly what happened: authorize
    # sent, connection closed, before any subscribe was even attempted.
    # Printing it turns "the websocket died" into a fact worth quoting at
    # support: the API is not issuing a market-data token for this account.
    md = j.get("mdAccessToken")
    print(f"  accessToken: yes | mdAccessToken: "
          f"{'YES' if md else 'NO  <-- market data not entitled'} | "
          f"keys returned: {sorted(j)}", flush=True)
    return j["accessToken"], md or j["accessToken"], (time.time() - t0) * 1000


def front_month(tok):
    """Whichever NQ contract the exchange says is front. Hard-coding a symbol
    is how the last run ended up querying an expired December contract."""
    import requests
    if SYMBOL:
        return SYMBOL
    r = requests.get(f"https://{HOST}.tradovateapi.com/v1/contract/suggest",
                     params={"t": "NQ", "l": 10},
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    # Sorting names alphabetically picked NQH7 -- March 2027 -- because "H7"
    # precedes "U6" as text. Contract codes are not chronological as strings,
    # so decode the month letter and year digit instead.
    MON = "FGHJKMNQUVXZ"
    def when(nm):
        try:
            return (int(nm[-1]), MON.index(nm[-2]))
        except Exception:                                        # noqa: BLE001
            return (99, 99)
    names = [c["name"] for c in r.json()
             if c.get("name", "").startswith("NQ") and len(c["name"]) >= 4]
    return sorted(names, key=when)[0] if names else "NQU6"


def rest_latency(tok, n=12):
    """Round trip on a trivial authenticated call: the floor for anything the
    order path could achieve."""
    import requests
    h = {"Authorization": f"Bearer {tok}"}
    out = []
    for _ in range(n):
        t0 = time.time()
        try:
            requests.get(f"https://{HOST}.tradovateapi.com/v1/account/list",
                         headers=h, timeout=20)
            out.append((time.time() - t0) * 1000)
        except Exception:                                        # noqa: BLE001
            pass
        time.sleep(0.3)
    return out


def main():
    if not all([U, P, CID, SEC]):
        sys.exit("TRADOVATE_USER/PASS/CID/SEC must all be set")
    import websocket
    os.makedirs(OUT, exist_ok=True)
    tok, mdtok, auth_ms = auth()
    sym = front_month(tok)
    lat = rest_latency(tok)
    lat.sort()
    print(f"symbol {sym} | auth {auth_ms:.0f} ms | REST round trip "
          f"median {lat[len(lat)//2]:.0f} ms, best {lat[0]:.0f} ms, "
          f"worst {lat[-1]:.0f} ms", flush=True)

    # THE SOCKET KEPT CLOSING ON AUTHORIZE AND I BLAMED THE SUBSCRIPTION.
    # It was not the subscription -- the auth response carries mdAccessToken
    # and hasMarketData. Two things in the previous version could each close a
    # Tradovate feed on their own, so both are fixed and the survivor is
    # reported instead of assumed:
    #
    #   1. the heartbeat thread started IMMEDIATELY after sending authorize and
    #      wrote "[]" onto the socket while the server was still replying.
    #      Interleaving a frame into an unfinished handshake is enough. It now
    #      starts only once authorization is acknowledged.
    #   2. the market-data host may not be md-demo for this account. A demo
    #      login can still be entitled against the live feed, so each candidate
    #      is tried in turn and the one that answers is used.
    ws = None
    for host in [f"md-{HOST}", "md", "md-live"]:
        url = f"wss://{host}.tradovateapi.com/v1/websocket"
        try:
            c = websocket.create_connection(url, timeout=25,
                                            sslopt={"cert_reqs": ssl.CERT_REQUIRED})
            first = c.recv()
            c.send(f"authorize\n0\n\n{mdtok}")
            ok, frames = False, []
            t0 = time.time()
            while time.time() - t0 < 10:
                try:
                    m = c.recv()
                except Exception as e:                           # noqa: BLE001
                    frames.append(f"CLOSED: {e}")
                    break
                if len(m) > 1:
                    frames.append(m[:160])
                if '"i":0' in m:
                    ok = '"s":200' in m or '"s": 200' in m or True
                    break
            print(f"  {url}: open={first!r} ok={ok} frames={frames[:3]}",
                  flush=True)
            if ok:
                ws = c
                break
            c.close()
        except Exception as e:                                   # noqa: BLE001
            print(f"  {url}: {type(e).__name__}: {e}", flush=True)
    if ws is None:
        sys.exit("no market data host accepted the token")

    stop = threading.Event()

    def beat():
        # started only AFTER authorization, for the reason above
        while not stop.is_set():
            try:
                ws.send("[]")
            except Exception:                                    # noqa: BLE001
                return
            stop.wait(2.0)
    threading.Thread(target=beat, daemon=True).start()
    ws.send('md/subscribeDOM\n1\n\n{"symbol":"%s"}' % sym)
    ws.send('md/subscribeQuote\n2\n\n{"symbol":"%s"}' % sym)

    rows, stale, last = [], [], 0.0
    t0 = time.time()
    while time.time() - t0 < DUR:
        try:
            m = ws.recv()
        except Exception as e:                                   # noqa: BLE001
            print("ws closed:", e, flush=True)
            break
        if '"doms"' not in m:
            continue
        try:
            d = json.loads(m[1:])[0]["d"]["doms"][0]
        except Exception:                                        # noqa: BLE001
            continue
        now = time.time()
        # how old is this book by the time we see it -- the market-data half
        # of any latency budget
        try:
            ex = pd.Timestamp(d["timestamp"]).timestamp()
            stale.append((now - ex) * 1000)
        except Exception:                                        # noqa: BLE001
            pass
        if (now - last) * 1000 < SNAP_MS:
            continue
        last = now
        b = d.get("bids") or []
        a = d.get("asks") or []
        rows.append(dict(
            ts=int(now * 1e9), exch=d.get("timestamp"),
            bid=b[0]["price"] if b else None,
            bid_sz=b[0]["size"] if b else None,
            ask=a[0]["price"] if a else None,
            ask_sz=a[0]["size"] if a else None,
            bid_depth=sum(x["size"] for x in b[:10]),
            ask_depth=sum(x["size"] for x in a[:10]),
            levels=len(b),
            book=json.dumps({"b": [(x["price"], x["size"]) for x in b[:10]],
                             "a": [(x["price"], x["size"]) for x in a[:10]]})))
        if len(rows) % 2000 == 0:
            print(f"  {len(rows):,} snapshots, {(now-t0)/60:.0f} min",
                  flush=True)
    stop.set()
    try:
        ws.close()
    except Exception:                                            # noqa: BLE001
        pass

    if not rows:
        print("no depth received -- check market data entitlement")
        return
    df = pd.DataFrame(rows)
    day = time.strftime("%Y-%m-%d")
    p = f"{OUT}/{sym}_{day}_dom.parquet"
    if os.path.exists(p):
        df = pd.concat([pd.read_parquet(p), df])
    df.to_parquet(p, compression="zstd")
    stale.sort()
    med = stale[len(stale) // 2] if stale else float("nan")
    sp = (df.ask - df.bid).dropna()
    log = [f"## {day} — `{sym}`", "",
           f"- `{len(df):,}` book snapshots at {SNAP_MS} ms",
           f"- **median spread {sp.median():.2f} pts "
           f"({sp.median()/0.25:.1f} ticks)**, "
           f"{float((sp <= 0.26).mean())*100:.0f}% of the time one tick",
           f"- median top of book **{df.bid_sz.median():.0f} bid / "
           f"{df.ask_sz.median():.0f} ask**, "
           f"ten-level depth {df.bid_depth.median():.0f} / "
           f"{df.ask_depth.median():.0f}",
           "",
           "### Latency, measured rather than assumed",
           "",
           f"- REST round trip **{lat[len(lat)//2]:.0f} ms** median "
           f"({lat[0]:.0f} best, {lat[-1]:.0f} worst)",
           f"- market data staleness **{med:.0f} ms** median on arrival",
           f"- the repo has been costing every study against **2,000 ms**",
           ""]
    rp = "research/DOM.md"
    head = ("# Live order book, recorded\n\nDepth is free with the Tradovate "
            "account but has no history, so it is recorded from here forward. "
            "It exists to settle one number: the passive-entry edge measured "
            "at +$0.25 a trade rests on guessing whether a limit order would "
            "have filled, and that guess moved the answer by 3.5x.\n")
    prev = open(rp).read() if os.path.exists(rp) else head
    if not prev.startswith("# Live order book"):
        prev = head
    os.makedirs("research", exist_ok=True)
    open(rp, "w").write(prev.rstrip() + "\n\n" + "\n".join(log) + "\n")
    print("\n".join(log))
    print("wrote", p)


if __name__ == "__main__":
    main()

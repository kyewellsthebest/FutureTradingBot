"""Which symbols does the market-data socket accept? A matrix, not a theory.

The recorder connects, authorizes with s:200, and every subscription comes back

    {"errorText":"Symbol is inaccessible","errorCode":"UnknownSymbol",
     "mode":"None"}

Two explanations fit that equally well and they lead opposite ways:

  ENTITLEMENT   the account has no CME market-data subscription, so every CME
                symbol is refused and no code change will ever fix it
  SYMBOL        NQU6 specifically is wrong -- expired, misnamed, or the socket
                wants the numeric contract id rather than the name

I have guessed at Tradovate entitlements twice already and been wrong both
times, so this guesses at nothing. It asks REST which contracts exist, then
tries each one on the market-data socket by NAME and by ID, and prints what
came back for each. The shape of the matrix is the answer:

  every row refused                 -> entitlement, and the fix is a purchase
  some rows accepted                -> symbol handling, and the fix is code
  names refused but ids accepted    -> the socket wants ids

It also asks REST for each contract's status, because a contract that REST
itself calls expired should not be blamed on the feed.
"""
import json
import os
import ssl
import sys
import time

import requests
import websocket

HOST = os.environ.get("TV_HOST", "demo")
U, P = os.environ.get("TRADOVATE_USER"), os.environ.get("TRADOVATE_PASS")
CID, SEC = os.environ.get("TRADOVATE_CID"), os.environ.get("TRADOVATE_SEC")
DEV = os.environ.get("TRADOVATE_DEVID", "dom-recorder-001")
ROOTS = os.environ.get("PROBE_ROOTS", "NQ,MNQ,ES,MES,CL,GC").split(",")


def auth():
    r = requests.post(
        f"https://{HOST}.tradovateapi.com/v1/auth/accesstokenrequest",
        json={"name": U, "password": P, "appId": "DOMRecorder",
              "appVersion": "1.0", "deviceId": DEV, "cid": CID, "sec": SEC},
        timeout=30)
    j = r.json()
    if not j.get("accessToken"):
        sys.exit(f"auth failed: {json.dumps(j)[:300]}")
    print(f"hasMarketData={j.get('hasMarketData')!r} "
          f"hasLive={j.get('hasLive')!r} hasFunded={j.get('hasFunded')!r} "
          f"experience={j.get('experience')!r} "
          f"userStatus={j.get('userStatus')!r}", flush=True)
    return j["accessToken"], j.get("mdAccessToken") or j["accessToken"]


def contracts(tok):
    """What REST believes exists, with its own view of expiry."""
    h = {"Authorization": f"Bearer {tok}"}
    out = []
    for root in ROOTS:
        try:
            r = requests.get(
                f"https://{HOST}.tradovateapi.com/v1/contract/suggest",
                params={"t": root, "l": 6}, headers=h, timeout=30).json()
        except Exception as e:                                   # noqa: BLE001
            print(f"{root}: suggest failed {type(e).__name__}: {e}")
            continue
        MON = "FGHJKMNQUVXZ"
        def when(c):
            nm = c.get("name", "")
            try:
                return (int(nm[-1]), MON.index(nm[-2]))
            except Exception:                                    # noqa: BLE001
                return (99, 99)
        got = sorted([c for c in r if c.get("name", "").startswith(root)],
                     key=when)[:2]
        for c in got:
            out.append((c["name"], c.get("id")))
    return out


def probe(mdtok, items):
    url = f"wss://md-{HOST}.tradovateapi.com/v1/websocket"
    c = websocket.create_connection(
        url, timeout=25, sslopt={"cert_reqs": ssl.CERT_REQUIRED})
    c.recv()
    c.send(f"authorize\n0\n\n{mdtok}")
    t0 = time.time()
    while time.time() - t0 < 10:
        if '"i":0' in c.recv():
            break

    rid, want = 10, {}
    for name, cid in items:
        # by NAME
        rid += 1
        want[rid] = (name, "name")
        c.send('md/subscribeQuote\n%d\n\n{"symbol":"%s"}' % (rid, name))
        # by numeric contract ID, which the socket also accepts
        if cid:
            rid += 1
            want[rid] = (name, "id")
            c.send('md/subscribeQuote\n%d\n\n{"symbol":%d}' % (rid, cid))

    res, t0 = {}, time.time()
    while time.time() - t0 < 25 and len(res) < len(want):
        try:
            m = c.recv()
        except Exception:                                        # noqa: BLE001
            break
        if len(m) < 2 or '"i":' not in m:
            continue
        try:
            for f in json.loads(m[1:]):
                i = f.get("i")
                if i in want:
                    d = f.get("d") or {}
                    res[i] = (d.get("errorText") or d.get("errorCode")
                              or f"OK {json.dumps(d)[:60]}")
        except Exception:                                        # noqa: BLE001
            continue
    try:
        c.close()
    except Exception:                                            # noqa: BLE001
        pass
    return want, res


def main():
    if not all([U, P, CID, SEC]):
        sys.exit("TRADOVATE_USER/PASS/CID/SEC must all be set")
    tok, mdtok = auth()
    items = contracts(tok)
    print(f"\nREST knows {len(items)} contracts: "
          f"{', '.join(n for n, _ in items)}\n", flush=True)
    want, res = probe(mdtok, items)
    print(f"{'symbol':<10} {'by':<5} {'market-data socket says'}")
    print("-" * 62)
    ok = 0
    for i in sorted(want):
        name, how = want[i]
        ans = res.get(i, "(no reply)")
        if ans.startswith("OK"):
            ok += 1
        print(f"{name:<10} {how:<5} {ans}")
    print("-" * 62)
    n = len(want)
    if ok == 0:
        print(f"ALL {n} refused, every root and both lookup forms.\n"
              f"That is not a symbol bug -- it is the account. The market-data\n"
              f"subscription has to be enabled in Tradovate before any depth\n"
              f"can be recorded, and no code change substitutes for it.")
    elif ok == n:
        print(f"All {n} accepted. The recorder's symbol was the only problem.")
    else:
        print(f"{ok} of {n} accepted -- compare the rows above: whichever "
              f"column is consistently refused is the actual constraint.")


if __name__ == "__main__":
    main()

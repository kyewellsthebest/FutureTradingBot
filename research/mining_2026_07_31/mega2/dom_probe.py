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
          f"userStatus={j.get('userStatus')!r} "
          f"mdAccessToken={'YES' if j.get('mdAccessToken') else 'MISSING'}",
          flush=True)
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


def entitlements(tok):
    """Ask REST what this account actually owns. The forum's canonical cause
    for 'Symbol is inaccessible' on EVERY symbol is a missing Contract
    Library add-on -- an account-level plugin, invisible from the md socket,
    enumerable here."""
    h = {"Authorization": f"Bearer {tok}"}
    for ep in ("userPlugin/list", "marketDataSubscription/list",
               "tradovateSubscription/list"):
        try:
            r = requests.get(f"https://{HOST}.tradovateapi.com/v1/{ep}",
                             headers=h, timeout=30)
            j = r.json()
        except Exception as e:                                   # noqa: BLE001
            print(f"{ep}: failed {type(e).__name__}: {e}", flush=True)
            continue
        if not isinstance(j, list):
            print(f"{ep}: {str(j)[:200]}", flush=True)
            continue
        print(f"{ep}: {len(j)} entries", flush=True)
        for x in j[:20]:
            keep = {k: x.get(k) for k in
                    ("pluginName", "planPrice", "autorenewal", "active",
                     "startDate", "expirationDate", "cancelledRenewal",
                     "planCategories", "entitlementId", "timestamp")
                    if k in x}
            print(f"  {keep}", flush=True)


def probe(mdtok, items):
    # production market data lives at md.tradovateapi.com, NOT md-live --
    # md-live accepts the connection and the authorize but owns no md/*
    # routes, which is why every request 404'd there in both spellings
    mdhost = "md" if HOST == "live" else f"md-{HOST}"
    url = f"wss://{mdhost}.tradovateapi.com/v1/websocket"
    c = websocket.create_connection(
        url, timeout=25, sslopt={"cert_reqs": ssl.CERT_REQUIRED})
    c.recv()
    c.send(f"authorize\n0\n\n{mdtok}")
    t0 = time.time()
    while time.time() - t0 < 10:
        m = c.recv()
        if '"i":0' in m:
            # the reply to authorize decides everything downstream, so show it
            print(f"authorize reply: {m[:300]}", flush=True)
            break

    # LOWERCASE endpoints: live's router 404s the camelCase spelling that
    # demo tolerates ("Not found: md/subscribeQuote", s:404, every request)
    rid, want = 10, {}
    for name, cid in items:
        # by NAME
        rid += 1
        want[rid] = (name, "quote")
        c.send('md/subscribequote\n%d\n\n{"symbol":"%s"}' % (rid, name))
        # by numeric contract ID, which the socket also accepts
        if cid:
            rid += 1
            want[rid] = (name, "id")
            c.send('md/subscribequote\n%d\n\n{"symbol":%d}' % (rid, cid))
        # depth is the prize -- ask for it on the front months
        if name in ("NQU6", "MNQU6", "ESU6", "MESU6"):
            rid += 1
            want[rid] = (name, "dom")
            c.send('md/subscribedom\n%d\n\n{"symbol":"%s"}' % (rid, name))

    res, t0, raw = {}, time.time(), []
    while time.time() - t0 < 25 and len(res) < len(want):
        try:
            m = c.recv()
        except Exception:                                        # noqa: BLE001
            break
        if len(raw) < 12 and m not in ("h", ""):
            raw.append(m[:200])
        if len(m) < 2 or '"i":' not in m:
            continue
        try:
            for f in json.loads(m[1:]):
                i = f.get("i")
                if i in want:
                    d = f.get("d")
                    # d is a dict on entitlement replies but a plain STRING
                    # on router errors -- treating it as a dict raised and
                    # got swallowed, which printed as '(no reply)'
                    if isinstance(d, dict):
                        res[i] = (d.get("errorText") or d.get("errorCode")
                                  or f"OK {json.dumps(d)[:60]}")
                    else:
                        s = f.get("s")
                        res[i] = (f"OK s={s}" if s == 200
                                  else f"s={s} {str(d)[:60]}")
        except Exception:                                        # noqa: BLE001
            continue
    if not res and raw:
        # every request unanswered -- show what the socket DID send instead
        print("no request got a reply; first raw frames received:", flush=True)
        for m in raw:
            print(f"  {m}", flush=True)
    try:
        c.close()
    except Exception:                                            # noqa: BLE001
        pass
    return want, res


def main():
    if not all([U, P, CID, SEC]):
        sys.exit("TRADOVATE_USER/PASS/CID/SEC must all be set")
    tok, mdtok = auth()
    entitlements(tok)
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

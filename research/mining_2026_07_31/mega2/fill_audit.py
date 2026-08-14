"""Broker-truth audit: what did the demo account ACTUALLY do today?

Pulls today's orders + fills + positions straight from Tradovate demo
REST (no bot files involved), maps contract IDs to names, and answers:

  1. Did the retired basket (ZB/ZN) stop trading, and when was its last
     fill?  (the 2026-08-14 cutover force-disables it at boot)
  2. Is the pulse strategy alive -- are MNQ orders being PLACED (working
     or filled), and what were the last few?

Writes research/FILL_AUDIT.md. /fill/list and /order/list are
trade-date-scoped on Tradovate, so this is exactly "today".
"""
import datetime as dt
import json
import os
import sys

import requests

HOST = os.environ.get("TV_HOST", "demo")
U, P = os.environ.get("TRADOVATE_USER"), os.environ.get("TRADOVATE_PASS")
CID, SEC = os.environ.get("TRADOVATE_CID"), os.environ.get("TRADOVATE_SEC")
BASE = f"https://{HOST}.tradovateapi.com/v1"

if not all((U, P, CID, SEC)):
    sys.exit("TRADOVATE_USER/PASS/CID/SEC must all be set")

r = requests.post(f"{BASE}/auth/accesstokenrequest", timeout=30,
                  json={"name": U, "password": P, "appId": "FillAudit",
                        "appVersion": "1.0", "deviceId": "fill-audit-001",
                        "cid": int(CID), "sec": SEC})
j = r.json()
if not j.get("accessToken"):
    sys.exit(f"auth failed: {json.dumps(j)[:300]}")
H = {"Authorization": f"Bearer {j['accessToken']}"}


def get(path, **params):
    rr = requests.get(f"{BASE}{path}", headers=H, params=params, timeout=30)
    if rr.status_code != 200:
        print(f"  {path} -> {rr.status_code} {rr.text[:120]}", flush=True)
        return []
    return rr.json()


accounts = get("/account/list")
print(f"accounts: {[(a['id'], a.get('name')) for a in accounts]}", flush=True)
orders = get("/order/list")
fills = get("/fill/list")
positions = get("/position/list")

cname = {}


def name_of(cid_):
    if cid_ not in cname:
        c = get("/contract/item", id=cid_)
        cname[cid_] = (c or {}).get("name", f"?{cid_}")
    return cname[cid_]


# order id -> contract for fills that carry orderId but no contractId
o_by_id = {o["id"]: o for o in orders}


def ts(s):
    return (s or "").replace("T", " ")[:19]


L = ["# Fill audit — broker's own records (Tradovate demo REST)", "",
     f"Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}. "
     "Trade-date-scoped: today's orders/fills only.", ""]

L.append(f"## Orders today: {len(orders)}")
L.append("")
L.append("| time (UTC) | contract | action | type | status | qty |")
L.append("|---|---|---|---|---|---|")
for o in sorted(orders, key=lambda x: x.get("timestamp", "")):
    nm = name_of(o.get("contractId")) if o.get("contractId") else "?"
    L.append(f"| {ts(o.get('timestamp'))} | {nm} | {o.get('action')} | "
             f"{o.get('orderType', '?')} | {o.get('ordStatus')} | "
             f"{o.get('orderQty', 1)} |")

L += ["", f"## Fills today: {len(fills)}", "",
      "| time (UTC) | contract | side | qty | price |", "|---|---|---|---|---|"]
sym_last = {}
for f in sorted(fills, key=lambda x: x.get("timestamp", "")):
    cid_ = f.get("contractId") or o_by_id.get(f.get("orderId"), {}).get("contractId")
    nm = name_of(cid_) if cid_ else "?"
    root = "".join(ch for ch in nm if not ch.isdigit()).rstrip()
    sym_last[root] = ts(f.get("timestamp"))
    L.append(f"| {ts(f.get('timestamp'))} | {nm} | {f.get('action')} | "
             f"{f.get('qty')} | {f.get('price')} |")

L += ["", "## Open positions", ""]
for p in positions:
    if p.get("netPos"):
        L.append(f"- {name_of(p.get('contractId'))}: net {p['netPos']}")
if not any(p.get("netPos") for p in positions):
    L.append("- flat")

L += ["", "## Verdict", ""]
old = {k: v for k, v in sym_last.items() if k[:2] in ("ZB", "ZN")}
mnq_orders = [o for o in orders
              if o.get("contractId") and
              name_of(o["contractId"]).startswith(("MNQ", "MES", "MYM"))]
L.append(f"- last basket (ZB/ZN) fill: {old or 'none today'}")
L.append(f"- pulse-symbol orders placed (MNQ/MES/MYM): {len(mnq_orders)}")
if mnq_orders:
    lo = max(mnq_orders, key=lambda x: x.get("timestamp", ""))
    L.append(f"- latest: {ts(lo.get('timestamp'))} "
             f"{name_of(lo['contractId'])} {lo.get('action')} "
             f"{lo.get('orderType')} -> {lo.get('ordStatus')}")

out = "research/FILL_AUDIT.md"
open(out, "w").write("\n".join(L) + "\n")
print("\n".join(L), flush=True)
print(f"\nwrote {out}", flush=True)

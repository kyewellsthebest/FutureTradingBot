"""Diagnostic canary: telemetry through the broker's order table.

The Railway host has no channel back to the operator except the broker
API itself (dashboard URL unknown, no git creds, no log access). So:
every CANARY_EVERY_S the bot places a 1-lot LIMIT far below market on
the front MNQ contract, with the diagnostic payload in the order's
`text` field, and cancels it ~2s later. The fill-audit workflow reads
the order table and gets:

  1. PROOF the host's order-placement path works end to end
     (auth -> contract -> placeorder -> cancel), and
  2. live counters: signals fired since boot, engine cycle, plus the
     most recent '[broker ...]' log line (the forwarding gate verdicts).

DEMO ONLY: refuses to run against a live cluster. A 10%-below-market
buy limit cannot fill in the sim, and it is cancelled immediately.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

logger = logging.getLogger("diag_canary")

CANARY_EVERY_S = int(os.environ.get("PULSE_CANARY_EVERY_S", "1200"))
FIRST_DELAY_S = 180


def _payload() -> str:
    """Compact diag string for the order text field (keep it short)."""
    parts = ["diag"]
    try:
        from bot.account_ctx import data_dir
        blob = json.loads((data_dir() / "dashboard_data.json").read_text())
        rt = blob.get("bot_runtime") or blob
        sf = rt.get("signals_fired")
        cy = rt.get("cycle")
        if sf is not None:
            parts.append(f"sf{sf}")
        if cy is not None:
            parts.append(f"cy{cy}")
    except Exception:
        parts.append("noblob")
    try:
        logp = os.environ.get("BOT_LOG_FILE", "/data/bot.log")
        with open(logp, "rb") as f:
            f.seek(max(0, os.path.getsize(logp) - 40_000))
            tail = f.read().decode(errors="replace")
        hits = re.findall(r"\[broker[^\n]*", tail)
        if hits:
            parts.append(hits[-1][:40])
        else:
            parts.append("nogate")
    except Exception:
        parts.append("nolog")
    return " ".join(parts)[:120]


def _once() -> None:
    from bot.tradovate_client import get_session, _is_demo
    if not _is_demo():
        logger.warning("[canary] non-demo cluster -- refusing to run")
        return
    sess = get_session()
    if not sess.is_configured:
        return
    acct = sess.get_account_id()
    if acct is None:
        return
    c = sess.find_contract("MNQ")
    if not c or not c.get("id"):
        return
    # price: 10% below last known price, snapped to tick
    px = None
    try:
        from bot.account_ctx import data_dir
        blob = json.loads((data_dir() / "dashboard_data.json").read_text())
        px = float(blob.get("price") or 0) or None
    except Exception:
        pass
    if not px:
        return
    limit = round(px * 0.90 / 0.25) * 0.25
    spec = getattr(sess.creds, "username", None)
    body = {
        "accountSpec": spec, "accountId": int(acct),
        "action": "Buy", "symbol": c["name"], "orderQty": 1,
        "orderType": "Limit", "price": limit, "isAutomated": True,
        "text": _payload()[:64],
    }
    body = {k: v for k, v in body.items() if v is not None}
    st, resp = sess._rest("POST", "/order/placeorder", body=body)
    oid = (resp or {}).get("orderId") if isinstance(resp, dict) else None
    logger.info(f"[canary] placed http={st} orderId={oid} "
                f"limit={limit} text={body['text']!r}")
    time.sleep(2)
    if oid:
        st2, _ = sess._rest("POST", "/order/cancelorder",
                            body={"orderId": int(oid)})
        logger.info(f"[canary] cancel http={st2}")


def _loop() -> None:
    time.sleep(FIRST_DELAY_S)
    while True:
        try:
            _once()
        except Exception as e:
            logger.warning(f"[canary] failed: {e!r}")
        time.sleep(CANARY_EVERY_S)


def start() -> None:
    if os.environ.get("PULSE_CANARY", "1") == "0":
        return
    t = threading.Thread(target=_loop, name="diag-canary", daemon=True)
    t.start()
    logger.info(f"[canary] armed (every {CANARY_EVERY_S}s)")

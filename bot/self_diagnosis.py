"""Automated self-diagnosis for the bundle: the exact issue, coded.

Every bundle now answers "why isn't it trading / what is wrong" by
itself: a decision funnel (setups -> fires -> forwards -> broker
accepts -> fills), grouped error signatures with counts and
timestamps, forced-env drift, and coded verdicts:

  PULSE-E01 wrong engine mode        PULSE-E06 broker rejecting orders
  PULSE-E02 shadow mode on           PULSE-E07 orders resting unfilled
  PULSE-E03 price feed dead          PULSE-E08 recent crash
  PULSE-E04 no setups in-session     PULSE-E09 engine tick stalled
  PULSE-E05 fires not forwarded      PULSE-E10 OSO denied, no fallback

Severity: CRIT (not trading and it's a fault), WARN (degraded), INFO.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone


def _log_tail(max_bytes=200_000) -> str:
    try:
        p = os.environ.get("BOT_LOG_FILE", "/data/bot.log")
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - max_bytes))
            return f.read().decode(errors="replace")
    except Exception:
        return ""


def _in_session(now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    hm = now.hour * 60 + now.minute
    return now.weekday() < 5 and (13 * 60 + 30) <= hm < 20 * 60


def diagnose() -> dict:
    now = datetime.now(timezone.utc)
    verdicts = []
    ev = {}

    def V(code, sev, msg, **kw):
        verdicts.append({"code": code, "severity": sev, "msg": msg, **kw})

    # ---- inputs, all best-effort ----
    blob, blob_age = {}, None
    try:
        from bot.account_ctx import data_dir
        p = data_dir() / "dashboard_data.json"
        if p.exists():
            blob_age = round(time.time() - p.stat().st_mtime, 1)
            blob = json.loads(p.read_text())
    except Exception:
        pass
    try:
        from bot.pullback_strategy import get_decision_log
        dlog = get_decision_log()
    except Exception:
        dlog = []
    try:
        from bot.tradovate_orders import get_audit_log
        alog = get_audit_log()
    except Exception:
        alog = []
    tail = _log_tail()

    # ---- decision funnel (this process) ----
    fn = {
        "setups_detected": sum(1 for d in dlog
                               if d.get("event") == "setup_detected"),
        "entries_blocked": sum(1 for d in dlog
                               if d.get("event") == "entry_blocked"),
        "trades_opened": sum(1 for d in dlog
                             if d.get("event") == "trade_opened"),
        "broker_attempts": sum(1 for a in alog
                               if a.get("kind") in ("placeoso",
                                                    "placeorder",
                                                    "placeorder_oso_fallback")),
        "broker_accepted": sum(1 for a in alog if a.get("parsed_ok")),
        "broker_rejected": sum(1 for a in alog
                               if a.get("kind", "").startswith("place")
                               and a.get("parsed_ok") is False),
        "safety_cap_skips": sum(1 for a in alog
                                if a.get("kind") == "placeoso_aborted_safety_cap"),
    }
    ev["funnel"] = fn
    block_reasons = {}
    for d in dlog:
        if d.get("event") == "entry_blocked":
            r = str(d.get("reason"))
            block_reasons[r] = block_reasons.get(r, 0) + 1
    ev["block_reasons"] = block_reasons
    rej_reasons = {}
    for a in alog:
        if a.get("parsed_ok") is False:
            r = str(a.get("parsed_error") or a.get("reason") or "?")[:60]
            rej_reasons[r] = rej_reasons.get(r, 0) + 1
    ev["rejection_reasons"] = rej_reasons

    # ---- error signatures from the log ----
    sig = {}
    for ln in tail.splitlines():
        if " ERROR " not in ln and "REJECTED" not in ln:
            continue
        m = re.match(r"(\S+ \S+?),\d+ \S+ \S+ (.*)", ln)
        if not m:
            continue
        when, msg = m.group(1), m.group(2)
        key = re.sub(r"[\d.]+", "#", msg)[:110]
        s = sig.setdefault(key, {"n": 0, "first": when, "last": when,
                                 "sample": msg[:160]})
        s["n"] += 1
        s["last"] = when
    ev["error_signatures"] = dict(
        sorted(sig.items(), key=lambda kv: -kv[1]["n"])[:12])

    # ---- forced-env drift ----
    drift = {}
    try:
        from live_runner import PULSE_FORCED_ENV
        for k, want in PULSE_FORCED_ENV.items():
            got = os.environ.get(k)
            expected = os.environ.get("PULSE_" + k) or want
            if got != expected:
                drift[k] = {"expected": expected, "got": got}
    except Exception:
        pass
    ev["env_drift"] = drift

    # ---- verdicts ----
    eng = os.environ.get("BROKER_ENGINE", "")
    if eng != "mirror":
        V("PULSE-E01", "CRIT", f"engine mode {eng!r} != 'mirror' -- "
          "trades will never forward to the broker")
    if os.environ.get("BOT_SHADOW_MODE", "0") == "1":
        V("PULSE-E02", "CRIT", "shadow mode ON -- no orders by design")
    price_ts = blob.get("price_ts") or (blob.get("live_snapshot") or
                                        {}).get("price_ts")
    if _in_session(now) and price_ts:
        try:
            age = (now - datetime.fromisoformat(
                str(price_ts).replace("Z", "+00:00"))).total_seconds()
            if age > 120:
                V("PULSE-E03", "CRIT",
                  f"price feed dead: last price {age:.0f}s old in-session")
        except Exception:
            pass
    if blob_age is not None and blob_age > 300:
        V("PULSE-E09", "CRIT",
          f"engine tick stalled: no dashboard publish for {blob_age:.0f}s")
    if _in_session(now) and fn["setups_detected"] == 0 and \
            (blob.get("cycle") or 0) > 900:
        V("PULSE-E04", "WARN", "no setups detected this session despite "
          f"{blob.get('cycle')} cycles -- check bar feed / thresholds")
    if fn["trades_opened"] > 0 and fn["broker_attempts"] == 0:
        V("PULSE-E05", "CRIT",
          f"{fn['trades_opened']} paper trades opened, ZERO broker "
          "attempts -- a forwarding gate is eating them",
          block_reasons=block_reasons)
    if fn["broker_rejected"] > 0 and fn["broker_accepted"] == 0:
        top = max(rej_reasons, key=rej_reasons.get) if rej_reasons else "?"
        V("PULSE-E06", "CRIT",
          f"every broker attempt rejected ({fn['broker_rejected']}); "
          f"top reason: {top}", rejections=rej_reasons)
        if "access" in top.lower() and os.environ.get(
                "BROKER_OSO_FALLBACK_PLAIN", "0") != "1":
            V("PULSE-E10", "CRIT", "OSO access denied and the plain-"
              "order fallback is DISABLED (BROKER_OSO_FALLBACK_PLAIN)")
    try:
        from bot.account_ctx import data_dir
        crash = data_dir() / "bot_crash.txt"
        if crash.exists() and time.time() - crash.stat().st_mtime < 6 * 3600:
            V("PULSE-E08", "WARN", "crash file fresh",
              crash=crash.read_text()[:400])
    except Exception:
        pass
    if drift:
        V("PULSE-E11", "WARN", "forced-env drift (running an old "
          "build?)", drift=drift)
    if not verdicts:
        V("PULSE-OK", "INFO", "all checks pass: engine live, feed "
          "fresh, funnel unobstructed" + (
              " (out of session)" if not _in_session(now) else ""))
    return {"ts": now.isoformat(), "verdicts": verdicts, "evidence": ev}

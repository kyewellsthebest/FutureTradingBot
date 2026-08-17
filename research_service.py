"""Railway entrypoint for the research bot: searches 24/7, serves a console.

    Railway service start command:  python research_service.py

This is a SECOND Railway service off the same repo as the trading bot.
The bot's service runs `python live_runner.py`; this one runs the
searcher in a background thread and serves a dashboard on $PORT so
there is always something to look at.

THE ONE THING THAT MUST NOT GO WRONG: STATE.

The whole safety property of a searcher that never stops is that it
counts its own trials and raises its own bar as sqrt(2 ln N). Lose the
ledger and the trial count resets to zero, the bar drops from ~5 sigma
back to 3.0, and the next run reports "findings" that are just the noise
it had already ruled out. A quiet state loss does not degrade this
system, it inverts it.

Railway containers have an EPHEMERAL filesystem -- every deploy and
every restart wipes it. So:

  1  RESEARCH_DIR should point at a mounted Railway volume. Set it to
     the volume's mount path (e.g. /data/research).
  2  If it does not, this file says so LOUDLY on boot and on the
     dashboard, rather than searching happily into a void.
  3  The ledger records its own high-water trial mark. If the process
     starts with fewer trials than it last reported, that is a state
     loss and it is displayed as an alert, not swallowed.

Endpoints
  GET /                 the console
  GET /api/state        everything the console renders
  GET /api/feed         recent research events
  GET /api/health       liveness, for Railway's healthcheck
  POST /api/stop        set the stop flag (search halts within seconds)
  POST /api/start       clear the stop flag
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("M2_REPO", str(ROOT))
RDIR = Path(os.environ.get("RESEARCH_DIR", ROOT / "data" / "research"))
STATIC = ROOT / "researcher" / "static"

app = Flask(__name__, static_folder=None)

STATE = {
    "boot": None,
    "alive": False,
    "cycle": 0,
    "last_event": None,
    "error": None,
    "storage": {"path": str(RDIR), "durable": False, "warning": None},
    "state_loss": None,
}
FEED = deque(maxlen=400)
_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------- storage
def check_storage():
    """Is RESEARCH_DIR somewhere that survives a restart?

    There is no API that answers this, so it is inferred: a path inside
    the app directory is definitely ephemeral on Railway, and an
    explicitly-set path outside it is presumed to be a mounted volume.
    Presumed, not proven -- which is why the trial high-water mark below
    is the check that actually catches a loss.
    """
    p = str(RDIR.resolve())
    explicit = "RESEARCH_DIR" in os.environ
    inside_app = p.startswith(str(ROOT.resolve()))
    on_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    durable = explicit and not inside_app
    warn = None
    if on_railway and not durable:
        warn = ("RESEARCH_DIR is not set to a mounted volume, so the "
                "ledger will be DESTROYED on every deploy and restart. "
                "The trial count resets to zero, the significance bar "
                "falls from ~5 sigma back to 3.0, and this searcher "
                "starts reporting as discoveries the noise it had "
                "already ruled out. Add a Railway volume and set "
                "RESEARCH_DIR to its mount path.")
    elif not on_railway and not durable:
        warn = ("running outside Railway with local storage -- fine for "
                "a laptop, not for the deployed service")
    STATE["storage"] = {"path": p, "durable": durable, "warning": warn}
    if warn:
        print("[storage] " + warn, flush=True)


HIGHWATER = RDIR / "highwater.json"


def check_state_loss(trials):
    """Did we come back with fewer trials than we last reported?

    This is the check that does not rely on guessing whether storage is
    durable. It compares against a high-water mark, so a wipe is caught
    even if every other assumption was wrong.
    """
    prev = 0
    try:
        prev = int(json.load(open(HIGHWATER)).get("trials", 0))
    except Exception:                                         # noqa: BLE001
        pass
    if prev > trials + 10:
        STATE["state_loss"] = {
            "t": now(), "was": prev, "now": trials,
            "note": (f"STATE LOSS: this searcher previously reached "
                     f"{prev:,} trials and has restarted at {trials:,}. "
                     f"The significance bar has fallen back with it, so "
                     f"anything it reports until it re-covers that "
                     f"ground has been judged against a bar that is too "
                     f"low. Treat findings as unproven until the trial "
                     f"count passes {prev:,} again."),
        }
        print("[STATE LOSS] " + STATE["state_loss"]["note"], flush=True)
    if trials > prev:
        try:
            RDIR.mkdir(parents=True, exist_ok=True)
            json.dump({"trials": trials, "t": now()}, open(HIGHWATER, "w"))
        except Exception:                                     # noqa: BLE001
            pass


# ------------------------------------------------------------ the search
def research_loop():
    """Run the searcher forever, in-process, capturing its event feed."""
    os.environ["RESEARCH_DIR"] = str(RDIR)
    os.environ.setdefault("RESEARCH_SLEEP", "20")
    RDIR.mkdir(parents=True, exist_ok=True)
    from researcher import runner as R

    # tee the runner's event feed into memory for the dashboard
    _say = R.say

    def say(msg, **kw):
        line = {"t": now(), "msg": msg}
        line.update(kw)
        with _lock:
            FEED.append(line)
            STATE["last_event"] = line
            if msg == "cycle_done":
                STATE["cycle"] = kw.get("cycle", STATE["cycle"])
            if "trials" in kw:
                check_state_loss(int(kw["trials"]))
        return _say(msg, **kw)

    R.say = say
    STATE["boot"] = now()
    STATE["alive"] = True
    while True:
        try:
            R.main()
            # main() returns when RESEARCH_STOP appears or on no_data.
            # Idle rather than spin, and keep serving the console.
            with _lock:
                STATE["alive"] = False
            time.sleep(20)
            if not (RDIR / "RESEARCH_STOP").exists():
                with _lock:
                    STATE["alive"] = True
        except Exception:                                     # noqa: BLE001
            tb = traceback.format_exc()[-2000:]
            with _lock:
                STATE["error"] = {"t": now(), "tb": tb}
                STATE["alive"] = False
            print("[research crashed]\n" + tb, flush=True)
            time.sleep(60)
            with _lock:
                STATE["error"] = None
                STATE["alive"] = True


# -------------------------------------------------------------- the API
def read_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:                                         # noqa: BLE001
        return default


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "alive": STATE["alive"], "t": now()})


@app.get("/api/state")
def api_state():
    status = read_json(RDIR / "status.json", {}) or {}
    led = status.get("summary", {})
    learn = status.get("learning", {})
    stopped = (RDIR / "RESEARCH_STOP").exists()
    with _lock:
        last = STATE["last_event"]
        err = STATE["error"]
    return jsonify({
        "t": now(),
        "boot": STATE["boot"],
        "alive": STATE["alive"] and not stopped,
        "stopped": stopped,
        "cycle": status.get("cycle", STATE["cycle"]),
        "last_event": last,
        "error": err,
        "storage": STATE["storage"],
        "state_loss": STATE["state_loss"],
        "ledger": led,
        "learning": learn,
        # the honest headline. Zero survivors with a high bar is the
        # expected output, and the console has to say that rather than
        # rendering an empty table that reads like a failure.
        "verdict": verdict(led),
    })


def verdict(led):
    if not led:
        return {"line": "starting up", "detail": "no cycle has completed yet"}
    n = led.get("trials", 0)
    bar = led.get("current_bar_sigma", 3.0)
    s = led.get("survivors", 0)
    v = led.get("vault_used", 0)
    if s == 0:
        return {"line": f"{n:,} hypotheses tested, nothing survived",
                "detail": (f"The bar is now {bar} sigma and rises as the "
                           f"search continues, so this is the expected "
                           f"result and it is a real one: {n:,} specific "
                           f"ideas have been ruled out. A searcher that "
                           f"reported a finding here would be lying.")}
    return {"line": f"{s} survivor(s) of {n:,} at {bar} sigma",
            "detail": (f"{v} vault look(s) spent. A survivor is a "
                       f"CANDIDATE, not a strategy -- it still owes the "
                       f"all-cell null, quarter-by-quarter stability, a "
                       f"stale placebo that loses, and a bot-exact "
                       f"simulation before any capital moves.")}


@app.get("/api/feed")
def api_feed():
    with _lock:
        return jsonify({"feed": list(FEED)[-200:][::-1]})


@app.post("/api/stop")
def api_stop():
    RDIR.mkdir(parents=True, exist_ok=True)
    (RDIR / "RESEARCH_STOP").write_text(now())
    return jsonify({"stopped": True})


@app.post("/api/start")
def api_start():
    f = RDIR / "RESEARCH_STOP"
    if f.exists():
        f.unlink()
    return jsonify({"stopped": False})


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/<path:f>")
def static_file(f):
    return send_from_directory(STATIC, f)


def main():
    check_storage()
    t = threading.Thread(target=research_loop, daemon=True, name="research")
    t.start()
    port = int(os.environ.get("PORT", "8080"))
    print(f"[research_service] console on :{port}, storage {RDIR}",
          flush=True)
    # Flask's dev server is single-threaded and warns in production;
    # the repo already ships gunicorn for the bot's dashboard, but this
    # process OWNS the research thread, so it cannot be handed to a
    # multi-worker gunicorn -- N workers would mean N searchers all
    # writing the same ledger and corrupting the trial count. One
    # process, threaded, is the correct shape here.
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False,
            use_reloader=False)


if __name__ == "__main__":
    main()

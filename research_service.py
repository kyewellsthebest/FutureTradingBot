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

from flask import Flask, jsonify, request, send_from_directory

from researcher.backup import Backup

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("M2_REPO", str(ROOT))

# WHERE STATE LIVES. Railway sets RAILWAY_VOLUME_MOUNT_PATH automatically
# whenever a volume is attached, so attaching one is sufficient -- no
# second variable to set and no second chance to get it wrong. An
# explicit RESEARCH_DIR still wins, for local runs and for anyone who
# wants the ledger somewhere specific on the volume.
VOL = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
if os.environ.get("RESEARCH_DIR"):
    RDIR = Path(os.environ["RESEARCH_DIR"])
elif VOL:
    RDIR = Path(VOL) / "research"
else:
    RDIR = ROOT / "data" / "research"
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
    "backup": {"mode": "off"},
}
FEED = deque(maxlen=400)
_lock = threading.Lock()

# Durability, belt and braces. The volume is the fast path; GitHub is the
# recovery path and works even when the volume was never attached. Either
# alone is enough to keep the trial count honest; neither is a silent
# failure, because the console reports both.
BACKUP = Backup(RDIR)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------- storage
def check_storage():
    """Is RESEARCH_DIR somewhere that survives a restart?

    Railway answers this itself: RAILWAY_VOLUME_MOUNT_PATH is set at
    runtime whenever a volume is attached, so "is the ledger on a
    volume" is a containment check against a value Railway supplies,
    not a guess about paths. Note the mount may legitimately sit INSIDE
    /app -- Railway's own docs recommend /app/data for apps writing to
    a relative ./data -- so an earlier version that treated any path
    under the app directory as ephemeral would have raised a false
    alarm on a perfectly good setup.
    """
    p = str(RDIR.resolve())
    on_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    vol = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    durable = bool(vol) and (p == str(Path(vol).resolve())
                             or p.startswith(str(Path(vol).resolve()) + os.sep))
    warn = None
    if on_railway and not vol:
        warn = ("NO VOLUME IS ATTACHED to this service, so the ledger "
                "will be DESTROYED on every deploy and restart. The "
                "trial count resets to zero, the significance bar falls "
                "from ~5 sigma back to 3.0, and this searcher starts "
                "reporting as discoveries the noise it had already "
                "ruled out. Attach a Railway volume -- the mount path "
                "is picked up automatically, no other variable needed.")
    elif on_railway and not durable:
        warn = (f"a volume is mounted at {vol} but the ledger is being "
                f"written to {p}, which is outside it. That path is "
                f"wiped on every deploy. Either unset RESEARCH_DIR so "
                f"the volume is used automatically, or point it inside "
                f"{vol}.")
    elif not on_railway and not durable:
        warn = ("running outside Railway with local storage -- fine for "
                "a laptop, not for the deployed service")
    STATE["storage"] = {"path": p, "durable": durable,
                        "volume": vol, "warning": warn}
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


def push_backup():
    """Save state to GitHub after each cycle. Never fatal."""
    if not BACKUP.enabled:
        return
    try:
        r = BACKUP.push()
        STATE["backup"] = dict(STATE.get("backup") or {},
                               mode="github", last_push=r)
    except Exception as exc:                                  # noqa: BLE001
        STATE["backup"] = dict(STATE.get("backup") or {},
                               mode="github", error=str(exc)[:200])


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
                push_backup()
            if "trials" in kw:
                check_state_loss(int(kw["trials"]))
        return _say(msg, **kw)

    R.say = say

    # RECOVERY BEFORE SEARCH. If the volume is missing or was wiped, the
    # local ledger is an empty container and GitHub holds the real
    # history. Restoring must happen before the first hypothesis is
    # scored, or the searcher spends that cycle judging against a bar
    # that has fallen back to 3.0 sigma.
    if BACKUP.enabled:
        try:
            r = BACKUP.restore_if_better()
            STATE["backup"] = {"mode": "github", "restore": r}
            print("[backup] " + json.dumps(r)[:300], flush=True)
        except Exception as exc:                              # noqa: BLE001
            STATE["backup"] = {"mode": "github",
                               "error": str(exc)[:200]}

    STATE["boot"] = now()
    # RESTART TALLY. An OOM kill is not a Python exception -- the process
    # simply stops -- so the crash handler below never sees it and the
    # console reports a healthy service that happens to keep starting
    # over. Every boot is appended here, so "12 restarts in the last
    # hour" is visible even when nothing ever raised.
    try:
        # A DEPLOY IS NOT A CRASH. Every push restarts the container, so
        # counting boots alone reports "5 restarts in the last hour"
        # during an afternoon of shipping fixes -- crying wolf on the
        # one alarm that must stay trustworthy. Railway stamps the
        # commit, so a boot whose commit differs from the last one is a
        # deploy and is recorded as such.
        sha = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:12] or "?"
        bl = RDIR / "boots.log"
        bl.open("a").write(f"{now()} {sha}\n")
        lines = [x.strip() for x in bl.read_text().splitlines() if x.strip()]
        if len(lines) > 400:
            bl.write_text("\n".join(lines[-400:]) + "\n")
        cut = time.time() - 3600
        recent = deploys = 0
        prev_sha = None
        for x in lines[-400:]:
            parts = x.split()
            try:
                ts = datetime.fromisoformat(parts[0]).timestamp()
            except Exception:                                 # noqa: BLE001
                continue
            cur = parts[1] if len(parts) > 1 else "?"
            is_deploy = (prev_sha is not None and cur != "?"
                         and cur != prev_sha)
            prev_sha = cur if cur != "?" else prev_sha
            if ts > cut:
                if is_deploy:
                    deploys += 1
                else:
                    recent += 1
        STATE["boots_total"] = len(lines)
        STATE["boots_last_hour"] = max(0, recent - 1)   # the current boot
        STATE["deploys_last_hour"] = deploys
        if recent > 3:
            print(f"[RESTART LOOP] {recent} boots in the last hour — the "
                  f"process is being killed, most likely out of memory.",
                  flush=True)
    except Exception:                                         # noqa: BLE001
        pass
    # LET THE SERVER BIND FIRST. This thread immediately reads 24 CSVs
    # and a 1.59M-row parquet, and pandas holds the GIL in chunks while
    # it does. Racing that against Flask's first bind is how a perfectly
    # healthy service fails its platform healthcheck and gets restarted
    # in a loop -- the search never gets past loading, so the logs show
    # nothing wrong.
    time.sleep(float(os.environ.get("RESEARCH_START_DELAY", "8")))
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
                # A CRASH THAT ERASES ITSELF IS A CRASH YOU CANNOT FIX.
                # The old code cleared STATE["error"] after 60s, so a
                # process restarting every couple of minutes showed
                # "ALL GOOD" almost all the time -- while the round
                # counter reset to 1 and the trial count slid backwards.
                # The tally is permanent and lives on the volume.
                STATE.setdefault("crashes", []).append(
                    {"t": now(), "tb": tb[-600:]})
                STATE["crashes"] = STATE["crashes"][-20:]
                STATE["crash_count"] = STATE.get("crash_count", 0) + 1
            try:
                (RDIR / "crashes.log").open("a").write(
                    f"\n===== {now()}\n{tb}\n")
            except Exception:                                 # noqa: BLE001
                pass
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


def memory_breakdown():
    """What the searcher itself says its memory is going on."""
    try:
        from researcher import runner as R
        return R.memory_report()
    except Exception:                                         # noqa: BLE001
        return {}


def rss_mb():
    """Resident memory, from /proc — no psutil dependency.

    Worth showing because the failure it diagnoses is invisible
    otherwise: a container killed for exceeding its memory limit leaves
    no traceback, no log line and no error state, just a service that
    keeps starting again.
    """
    try:
        with open("/proc/self/statm") as fh:
            pages = int(fh.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 1e6, 1)
    except Exception:                                         # noqa: BLE001
        return None


@app.get("/api/live")
def api_live():
    """The fast endpoint. Polled every second, so it must stay cheap --
    no file reads, no ledger scans, just the in-memory counters the
    search updates as it goes."""
    try:
        from researcher import runner as R
        lv = dict(R.LIVE)
        # THE COUNTERS THE WORKERS WRITE. The sweep runs in forked
        # children now, and a child's LIVE["tested"] dies with the child,
        # so this read used to sit at zero for the whole eight minutes a
        # cycle took. These are shared-memory counters incremented by
        # whichever process is doing the work.
        lv["tested"] = R.progress("v")
        lv["slate_measured"] = R.progress("s")
    except Exception:                                         # noqa: BLE001
        lv = {}
    # THE HEADLINE COMES FROM THE LEDGER'S OWN COUNTER, not from the
    # mirror the search loop keeps by hand. Feature scoring adds trials
    # in bulk through bump() and never touched that mirror, so the number
    # on screen sat frozen for minutes at a time while the search was
    # running normally. This reads the value every mutation path writes.
    try:
        from researcher.ledger import LIVE_TRIALS
        if LIVE_TRIALS["n"] > lv.get("trials", 0):
            lv["trials"] = LIVE_TRIALS["n"]
        lv["last_trial_age_s"] = (round(time.time() - LIVE_TRIALS["t"], 1)
                                  if LIVE_TRIALS["t"] else None)
        lv["never_scored"] = not LIVE_TRIALS["t"]
    except Exception:                                         # noqa: BLE001
        pass
    if lv.get("stage_t"):
        lv["stage_age_s"] = round(time.time() - lv["stage_t"], 1)
    lv["rss_mb"] = rss_mb()
    lv["boots_last_hour"] = STATE.get("boots_last_hour")
    import math
    n = max(lv.get("trials", 0), 1)
    lv["bar"] = round(max(3.0, math.sqrt(2.0 * math.log(n)) + 0.8), 2)
    lv["alive"] = STATE["alive"] and not (RDIR / "RESEARCH_STOP").exists()
    return jsonify(lv)


@app.get("/api/history")
def api_history():
    """The learning series, thinned for the wire.

    Sampled once a minute the file reaches a few thousand rows, and the
    console polls this often enough that shipping all of them every time
    would be the heaviest thing the service does. The charts are 300px
    wide, so more than a couple of hundred points cannot be seen
    anyway -- but the LAST point always survives the thinning, because
    that one is the number printed above the graph.
    """
    h = read_json(RDIR / "history.json", []) or []
    cap = 200
    if len(h) > cap:
        step = len(h) / float(cap)
        idx = sorted({int(i * step) for i in range(cap)} | {len(h) - 1})
        h = [h[i] for i in idx]
    return jsonify({"history": h})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "alive": STATE["alive"], "t": now()})


def tiers():
    """What data this deployment can actually see.

    Checked from the API rather than trusted from the search log,
    because the dangerous case is the tier that is absent: an absent
    tier produces no events at all, so a console driven purely by the
    event stream renders a perfectly healthy search running on a
    fraction of its data.
    """
    from researcher import data_tiers as DT
    out = []
    t1 = len(DT.tier1())
    out.append({"tier": 1,
                "name": f"breadth · 5-minute bars, {t1} markets",
                "ok": t1 > 0, "detail": f"{t1} markets on disk"})
    src = DT.tier2_sources(60)
    kind = src[0][1] if src else None
    out.append({"tier": 2, "name": "depth · NQ intraday bars, 8 quarters",
                "ok": bool(src),
                "detail": (f"{len(src)} contracts ("
                           + ("precomputed" if kind == "pre" else "raw ticks")
                           + ")") if src else
                          "MISSING — data/tick/ is gitignored (4.7 GB) and "
                          "data/research_bars/ was not committed. Run "
                          "researcher/build_deep_bars.py where the raw "
                          "ticks live and commit its output."})
    bp = os.path.join(str(ROOT), "data", "depth", "NQU6_book_1s.parquet")
    ok3 = os.path.exists(bp)
    out.append({"tier": 3, "name": "book · NQ top-of-book, 1-second",
                "ok": ok3,
                "detail": "1.59M seconds" if ok3 else "MISSING"})
    return out


_TIERS = {"v": None, "t": 0.0}


def cached_tiers():
    """tier1() reads 24 CSVs, so cache it for a few minutes."""
    if _TIERS["v"] is None or time.time() - _TIERS["t"] > 300:
        try:
            _TIERS["v"] = tiers()
        except Exception as exc:                              # noqa: BLE001
            _TIERS["v"] = [{"tier": 0, "name": "tier probe failed",
                            "ok": False, "detail": str(exc)[:200]}]
        _TIERS["t"] = time.time()
    return _TIERS["v"]


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
        "restarts": {"last_hour": STATE.get("boots_last_hour"),
                     "total": STATE.get("boots_total"),
                     "crashes": STATE.get("crash_count", 0),
                     "deploys_last_hour": STATE.get("deploys_last_hour", 0),
                     "last_tb": (STATE.get("crashes") or [{}])[-1].get("tb")},
        "rss_mb": rss_mb(),
        "memory": memory_breakdown(),
        "tiers": cached_tiers(),
        "backup": STATE["backup"],
        "adaptations": adaptations(),
        "learned": learned_facts(),
        "archive": archive_view(),
        "calibration": read_json(RDIR / "calibration.json", None),
        "survivors": survivors(),
        "near": near_misses(),
        "recent": recent_best(),
        "ledger": led,
        "learning": learn,
        # the honest headline. Zero survivors with a high bar is the
        # expected output, and the console has to say that rather than
        # rendering an empty table that reads like a failure.
        "verdict": verdict(led),
    })


def adaptations():
    """What the searcher has changed about itself, newest-used first."""
    m = read_json(RDIR / "memory.json", {}) or {}
    return sorted(m.get("adaptations", []), key=lambda a: -a.get("applied", 0))


def survivors():
    """Candidates that cleared the bar, with their vault verdict.

    A survivor with no vault entry has not been confirmed -- it cleared
    the search set only. The console has to distinguish those, because
    "found a strategy" and "found something that looked good on the data
    it was chosen from" are not the same claim.
    """
    led = read_json(RDIR / "ledger.json", {}) or {}
    touches = led.get("vault_touches", {}) or {}
    out = []
    for s in led.get("survivors", [])[-40:]:
        r = s.get("result", {}) or {}
        v = (touches.get(s.get("fp")) or {}).get("result") or {}
        out.append({
            "what": describe(s.get("hyp", {})),
            "market": (s.get("hyp") or {}).get("market", ""),
            "z": r.get("z"), "n": r.get("n"), "net": r.get("net"),
            "win_rate": r.get("win_rate"), "rr": r.get("rr"),
            "per_week": r.get("per_week"),
            "confirmed": bool(v and v.get("z", 0) > 2.0
                              and v.get("net", 0) > 0),
            "vault": v or None,
        })
    return out[::-1]


def near_misses(k=15):
    """Best-scoring hypotheses whether or not they passed.

    Shown because a Strategies tab that is empty for weeks reads as a
    broken service rather than an honest one. Each row carries the bar
    it faced, so "z 3.1 against a bar of 5.4" is legible as the failure
    it is rather than as a near-thing.
    """
    from researcher.ledger import Ledger
    try:
        led = Ledger(str(RDIR / "ledger.json"))
        out = []
        for r in led.near_misses(k):
            out.append({"what": describe(r["hyp"]),
                        "market": (r["hyp"] or {}).get("market", ""),
                        "family": r["family"], "z": r["z"],
                        "gross": r["gross"], "net": r["net"], "n": r["n"],
                        "win_rate": r.get("win_rate"), "rr": r.get("rr"),
                        "per_week": r.get("per_week"),
                        "bar": r["bar_at_test"], "passed": r["passed"],
                        "tier": (r["hyp"] or {}).get("tier"),
                        # pooled rows are a different KIND of result and
                        # must not be rendered as if they were one
                        # market's dollars per trade
                        "pooled": bool(r.get("pooled")),
                        "cu": r.get("cu"), "k": r.get("k"),
                        "mde": r.get("mde"),
                        "agree": r.get("agree"),
                        "stale": r.get("stale"), "killed": r.get("killed"),
                        "code_stale": r.get("code_stale"),
                        # WHEN, and on how many INDEPENDENT observations.
                        # Without the date a high-water board looks
                        # frozen; without eff_n a cell of two overlapping
                        # days reads the same as one of eight hundred.
                        "t": r.get("t"), "eff_n": r.get("eff_n"),
                        "kill_reasons": r.get("kill_reasons") or []})
        return out
    except Exception:                                         # noqa: BLE001
        return []


def recent_best(hours=24, k=5):
    """The best of a recent WINDOW, beside the all-time board.

    The all-time board ranks by strength and strength is a maximum, so
    it only moves when something beats the best result ever recorded. On
    a searcher that is working correctly that is rare, and the board sits
    unchanged for days while hundreds of thousands of trials happen
    behind it -- indistinguishable, from the outside, from a process
    that has stopped. This is the second view that tells them apart.
    """
    from researcher.ledger import Ledger
    try:
        led = Ledger(str(RDIR / "ledger.json"))
        d = led.recent_best(hours=hours, k=k)
        for r in d["rows"]:
            r["what"] = describe(r.get("hyp") or {})
            r.pop("hyp", None)
        return d
    except Exception:                                         # noqa: BLE001
        return {"hours": hours, "considered": 0, "rows": []}


def archive_view():
    """The map of best-per-niche, and the question the account asks.

    Kept separate from the leaderboard on purpose. The leaderboard ranks
    by significance, which systematically prefers the rare; the map
    keeps the best thing at EVERY trading frequency, including the high
    ones the account's arithmetic actually needs.
    """
    try:
        from researcher import archive as AR
        p = RDIR / "archive.json"
        if not p.exists():
            return {"filled": 0, "total": AR.TOTAL_CELLS, "top": [],
                    "frequent": None}
        a = AR.Archive(json.load(open(p)))
        cov = a.coverage()
        from researcher import hypotheses as HY
        def row(e):
            if not e:
                return None
            return {"what": describe(e.get("hyp") or {}),
                    "cell": AR.cell_name(tuple(int(x) for x in
                                               e["cell"].split(","))),
                    "cu": e.get("cu"), "z": e.get("z"), "n": e.get("n"),
                    "per_week": e.get("per_week"),
                    # WITHOUT THESE, cu IS UNREADABLE. A cell holding 240
                    # bars while firing every bar has 240x overlap, so
                    # its 391 trades carry the information of two -- and
                    # "+110 RT on 391 trades" is then the most
                    # misleading sentence this console can print.
                    "eff_n": e.get("eff_n"), "mde": e.get("mde"),
                    "overlap": e.get("overlap"),
                    "win_rate": e.get("win_rate"), "rr": e.get("rr"),
                    "market": e.get("market")}
        return {"filled": cov["filled"], "total": cov["total"],
                "pct": cov["pct"], "improvements": cov["improvements"],
                "bands": [dict(row(e) or {}, band=e.get("band"))
                          for e in a.by_frequency()],
                "frequent": row(a.best_at_frequency(400))}
    except Exception:                                         # noqa: BLE001
        return {"filled": 0, "total": 0, "top": [], "frequent": None}


def learned_facts():
    """What the searcher has worked out about the market itself.

    Distinct from adaptations, which record what it CHANGED. These are
    claims about the world with a number and a sample size attached, so
    they can be argued with.
    """
    try:
        from researcher.memory import Memory
        m = Memory(str(RDIR / "memory.json"))
        return m.learned()
    except Exception:                                         # noqa: BLE001
        return []


def describe(h):
    try:
        from researcher import hypotheses as HY
        return HY.describe(h)
    except Exception:                                         # noqa: BLE001
        return str(h)[:160]


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


@app.get("/api/learning.pdf")
def api_learning_pdf():
    from flask import Response
    from researcher.report import learning_pdf
    try:
        pdf = learning_pdf(str(RDIR))
    except Exception as exc:                                  # noqa: BLE001
        return jsonify({"error": str(exc)[:400]}), 500
    d = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="research-learning-'
                               f'{d}.pdf"'})


def _live_extra():
    """Everything the report needs that lives in this process, not on disk.

    The report reads state files, but health is about the process that is
    running right now -- its resident memory, the phase it is in, how
    many workers it forked, how many times it has restarted. None of that
    is written to disk between cycles, so it is collected here and handed
    in rather than guessed at from a file.
    """
    e = {"storage": STATE["storage"].get("path"),
         "durable": STATE["storage"].get("durable"),
         "volume": STATE["storage"].get("volume"),
         "backup": (STATE.get("backup") or {}).get("mode"),
         "alive": STATE["alive"] and not (RDIR / "RESEARCH_STOP").exists(),
         "state_loss": bool(STATE.get("state_loss")),
         "boots_last_hour": STATE.get("boots_last_hour"),
         "boots_total": STATE.get("boots_total"),
         "rss_mb": rss_mb(),
         "tiers": ", ".join(f"{t['tier']}:{'ok' if t['ok'] else 'MISSING'}"
                            for t in cached_tiers())}
    try:
        from researcher import runner as R
        e["stage"] = R.LIVE.get("stage")
        if R.LIVE.get("stage_t"):
            e["stage_age_s"] = round(time.time() - R.LIVE["stage_t"], 1)
        e["workers"] = R.WORKERS
        e["mem_limit_mb"] = R.MEM_LIMIT_MB
        e["cores"] = os.cpu_count()
        e["tested_this_session"] = R.progress("v")
        e["slate_measured_this_session"] = R.progress("s")
    except Exception:                                         # noqa: BLE001
        pass
    return e


# ONE BUILD AT A TIME, AND A SHORT CACHE.
#
# The full bundle is ~450 KB and about two seconds of CPU. That is
# nothing on an idle box and quite a lot on this one, where 47 search
# workers own every core and the parent process is also running the
# gauntlet, fitting the surrogate and saving a large ledger. The first
# version returned "Application failed to respond" on a phone: the
# request was not failing, it was starving.
#
# Two fixes, both here. The lock means a second tap -- which is exactly
# what anyone does when a download appears to hang -- waits for the
# build already running instead of starting a competing one that makes
# both slower. The cache means that wait happens at most once every few
# minutes. Keyed by the arguments, so the light and full variants do not
# evict each other.
_PDF_LOCK = threading.Lock()
_PDF_CACHE = {}
_PDF_TTL_S = float(os.environ.get("STATE_PDF_TTL_S", "240"))


def _pdf_response(pdf, age):
    from flask import Response
    d = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="research-state-'
                               f'{d}.pdf"',
        "Content-Length": str(len(pdf)),
        "Cache-Control": "no-store",
        # So a stale-looking figure can always be explained.
        "X-Report-Age-Seconds": str(int(age))})


def _build_pdf(top, src):
    """Build and cache one variant. Caller must hold _PDF_LOCK."""
    from researcher.report import state_pdf
    t0 = time.time()
    pdf = state_pdf(str(RDIR), _live_extra(), top=top, source=src)
    _PDF_CACHE[(top, src)] = (time.time(), pdf)
    print(f"[report] state.pdf top={top} source={src} "
          f"{len(pdf) / 1024:.0f}KB in {time.time() - t0:.1f}s", flush=True)
    return pdf


def _warm_pdfs():
    """Keep both variants warm, so a tap never waits on a build.

    The download is the one thing on this console that a person reaches
    for precisely when something looks wrong -- which is also when the
    box is busiest and least able to build it quickly. Building it on a
    timer instead means the request is a file read, and the two seconds
    of work happen when nobody is watching.
    """
    # The FIRST build is the expensive one -- 8.6s against 0.9s warm,
    # almost all of it reportlab importing and registering fonts. Paying
    # that once shortly after boot, rather than on whichever tap happens
    # to be first, is the whole point.
    wait = 45.0
    while True:
        try:
            time.sleep(wait)
            wait = max(60.0, _PDF_TTL_S * 0.75)
            if not STATE.get("alive"):
                continue
            for top, src in ((100, False), (100, True)):
                with _PDF_LOCK:
                    _build_pdf(top, src)
                time.sleep(2.0)          # never hog the interpreter
        except Exception as exc:                              # noqa: BLE001
            print(f"[report] warm failed: {str(exc)[:200]}", flush=True)


@app.get("/api/state.pdf")
def api_state_pdf():
    """THE download. One file, everything the backend knows about itself.

    Replaces the old diagnostics bundle, which carried the source and the
    controls but almost none of the numbers -- no throughput, no power,
    no leaderboard, no per-strategy specification. Answering "where is
    this bot actually at" from it meant opening four other tabs.
    """
    from flask import Response
    from researcher.report import state_pdf
    try:
        top = max(1, min(500, int(request.args.get("top", 100))))
    except Exception:                                         # noqa: BLE001
        top = 100
    src = request.args.get("source", "1") != "0"
    key = (top, src)
    fresh = request.args.get("fresh") == "1"
    hit = _PDF_CACHE.get(key)
    if hit and not fresh and time.time() - hit[0] < _PDF_TTL_S:
        pdf, age = hit[1], time.time() - hit[0]
    else:
        with _PDF_LOCK:
            # Re-check inside the lock: whoever we queued behind has
            # very likely just built exactly what we were about to.
            hit = _PDF_CACHE.get(key)
            if hit and not fresh and time.time() - hit[0] < _PDF_TTL_S:
                pdf, age = hit[1], time.time() - hit[0]
            else:
                try:
                    pdf = _build_pdf(top, src)
                except Exception as exc:                      # noqa: BLE001
                    # A STALE REPORT BEATS AN ERROR PAGE. If a build
                    # fails and an older one is in hand, serve that and
                    # say how old it is; the numbers being four minutes
                    # behind is a far smaller problem than the person
                    # looking at them getting nothing at all.
                    if hit:
                        pdf, age = hit[1], time.time() - hit[0]
                        print(f"[report] build failed, serving cached "
                              f"({age:.0f}s old): {str(exc)[:200]}",
                              flush=True)
                        return _pdf_response(pdf, age)
                    return jsonify({"error": str(exc)[:400],
                                    "where": traceback.format_exc()[-900:]
                                    }), 500
                age = 0.0
    return _pdf_response(pdf, age)


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
    threading.Thread(target=_warm_pdfs, daemon=True,
                     name="report-warm").start()
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

"""What the process was doing when it died, readable after it died.

WHY THIS EXISTS, and it is a specific failure this project keeps
paying for. When a container is OOM-killed it receives SIGKILL. There
is no traceback, no atexit handler, no final log line -- the process
simply stops mid-instruction. Railway then shows CRASHED, and every
piece of evidence about the cause was resident memory that is now gone.

That is not a hypothetical. This searcher has been killed repeatedly,
and diagnosing it produced THREE WRONG THEORIES in a row -- garbage
collector freezing, refcount dirtying of a fingerprint set, and pickled
worker arguments -- each argued from the code because there was no
measurement to argue from. The eventual fix came from measuring one
constant, and the two days before it were spent on plausible stories.

So: sample the two numbers that matter to a small file on the VOLUME,
which survives what the process does not.

    rss          how much memory this process holds, right now
    phase        what it was doing when that was true

THE DIRTY BIT is the part that makes this diagnostic rather than
decorative. A clean shutdown clears a flag on the way out; SIGKILL
cannot. So at boot, a file whose flag is still set is proof that the
previous process was killed rather than stopped -- and it carries the
last RSS and the last phase alongside. "Killed at 3,812 MB of a 4,096
MB limit during deep sweep NQM5" is a cause. "CRASHED" is not.

WHAT IT COSTS. One background thread, asleep 5 seconds out of every 5,
writing roughly 400 bytes. It is written with atomic replace, so a kill
during the write leaves the previous good record rather than a
half-file -- a black box that can itself be corrupted by the crash is
not a black box.

WHAT IT DELIBERATELY DOES NOT DO. It does not try to prevent the kill.
Shedding load on a memory threshold is a separate decision with its own
failure modes, and a recorder that also intervenes cannot be trusted to
report what would have happened. This only remembers.
"""
from __future__ import annotations

import json
import os
import threading
import time

NAME = "blackbox.json"
INTERVAL_S = 5.0

_S = {"phase": "starting", "path": None, "peak": 0.0, "stop": False,
      "thread": None, "started": 0.0}


def rss_mb():
    """This process's resident memory, right now."""
    try:
        with open("/proc/self/statm") as fh:
            return (int(fh.read().split()[1])
                    * os.sysconf("SC_PAGE_SIZE") / 1e6)
    except Exception:                                         # noqa: BLE001
        return None


def limit_mb():
    """The container's memory ceiling, from cgroup. None if unbounded."""
    for p in ("/sys/fs/cgroup/memory.max",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(p) as fh:
                v = fh.read().strip()
            if v == "max":
                return None
            n = int(v)
            # An unbounded cgroup reports a number near 2^63, not "max".
            return None if n > (1 << 60) else n / 1e6
        except Exception:                                     # noqa: BLE001
            continue
    return None


def phase(name, **extra):
    """Record what the process is doing. Free -- memory only."""
    _S["phase"] = str(name)[:120]
    if extra:
        _S["phase_extra"] = {k: str(v)[:60] for k, v in list(extra.items())[:6]}


def _write(clean=False):
    p = _S["path"]
    if not p:
        return
    # ONLY THE PROCESS THAT STARTED THE RECORDER MAY WRITE IT. The
    # searcher forks worker processes, and a fork inherits this
    # module's state wholesale -- path included. A child that reached
    # stop() would clear the dirty bit while the parent was still
    # alive, which is the one way this file could lie: it would report
    # a clean shutdown for a process that went on to be killed.
    if _S.get("owner") not in (None, os.getpid()):
        return
    # Belt to the join in stop(): once shutdown has begun, only the
    # clean record may be written. Two guards because a false "it was
    # killed" is more damaging than no record at all.
    if _S.get("stop") and not clean:
        return
    r = rss_mb()
    if r and r > _S["peak"]:
        _S["peak"] = r
    rec = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "pid": os.getpid(),
        "rss_mb": None if r is None else round(r, 1),
        "peak_mb": round(_S["peak"], 1),
        "limit_mb": (lambda L: None if L is None else round(L, 1))(limit_mb()),
        "phase": _S["phase"],
        "phase_extra": _S.get("phase_extra"),
        "uptime_s": round(time.time() - _S["started"], 1),
        # THE DIRTY BIT. Cleared only by an orderly shutdown, which
        # means a file still carrying `running: true` at boot is proof
        # the last process was killed rather than stopped.
        "running": not clean,
    }
    if rec["rss_mb"] is not None and rec["limit_mb"]:
        rec["headroom_mb"] = round(rec["limit_mb"] - rec["rss_mb"], 1)
        rec["used_pct"] = round(100.0 * rec["rss_mb"] / rec["limit_mb"], 1)
    try:
        # ATOMIC. A kill during the write must not destroy the record of
        # the previous sample -- a black box the crash can corrupt is
        # not a black box.
        tmp = p + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(rec, fh, separators=(",", ":"))
        os.replace(tmp, p)
    except Exception:                                         # noqa: BLE001
        pass
    return rec


def _loop():
    while not _S["stop"]:
        _write()
        for _ in range(int(INTERVAL_S * 4)):
            if _S["stop"]:
                return
            time.sleep(0.25)


def postmortem(rdir):
    """Read the previous process's last words. None if it shut down
    cleanly or never ran.

    Called BEFORE start(), which overwrites the file.
    """
    try:
        with open(os.path.join(rdir, NAME)) as fh:
            rec = json.load(fh)
    except Exception:                                         # noqa: BLE001
        return None
    if not rec.get("running"):
        return None                      # it stopped on purpose
    return rec


def explain(rec):
    """The postmortem as the sentence a person would write."""
    if not rec:
        return None
    rss, lim = rec.get("rss_mb"), rec.get("limit_mb")
    pct = rec.get("used_pct")
    who = f"during '{rec.get('phase')}'" if rec.get("phase") else ""
    base = (f"the previous process was KILLED (it never cleared its "
            f"shutdown flag) after {rec.get('uptime_s', 0) / 60:.0f} "
            f"minutes {who}")
    if rss and lim:
        near = " -- that is at the ceiling, so this was almost certainly " \
               "the OOM killer" if pct and pct >= 85 else \
               " -- well under the ceiling, so memory was probably NOT " \
               "the cause; look for a signal, a platform restart or a " \
               "deploy"
        return (f"{base}, holding {rss:,.0f} MB of a {lim:,.0f} MB limit "
                f"({pct:.0f}%), peak {rec.get('peak_mb', 0):,.0f} MB{near}")
    if rss:
        return (f"{base}, holding {rss:,.0f} MB (no cgroup limit visible, "
                f"so the ceiling is the host's)")
    return base


def start(rdir):
    """Begin recording. Returns the postmortem of the previous run."""
    os.makedirs(rdir, exist_ok=True)
    prev = postmortem(rdir)
    _S.update({"path": os.path.join(rdir, NAME), "stop": False,
               "peak": 0.0, "started": time.time(), "owner": os.getpid()})
    _write()
    t = threading.Thread(target=_loop, daemon=True, name="blackbox")
    t.start()
    _S["thread"] = t
    return prev


def stop():
    """Orderly shutdown: clear the dirty bit so the next boot knows
    this process was not killed.

    THE SAMPLER MUST BE STOPPED BEFORE THE CLEAN RECORD IS WRITTEN, and
    this is not fussiness. If the loop is inside _write() when stop()
    is called, its os.replace can land AFTER the clean one and put the
    dirty bit back -- reporting a kill for a process that shut down
    perfectly. It is timing-dependent, so it passed alone and failed
    under load, which is the worst way for a diagnostic to be wrong:
    the black box would invent crashes that never happened.
    """
    _S["stop"] = True
    t = _S.get("thread")
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=5.0)
    _write(clean=True)


def selftest(verbose=True):
    """The property under test: a KILLED process is distinguishable
    from a stopped one, using only what is left on disk."""
    import subprocess
    import sys
    import tempfile

    fails = []
    d = tempfile.mkdtemp()

    # 1. a process that is SIGKILLed leaves the dirty bit set
    prog = (f"import sys; sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))!r});"
            f"from researcher import blackbox as B;"
            f"B.start({d!r}); B.phase('deep sweep NQM5');"
            f"B._write();"
            f"import time; time.sleep(60)")
    p = subprocess.Popen([sys.executable, "-c", prog])
    for _ in range(80):
        if os.path.exists(os.path.join(d, NAME)):
            break
        time.sleep(0.05)
    p.kill()
    p.wait(timeout=10)
    rec = postmortem(d)
    ok = bool(rec) and rec.get("phase") == "deep sweep NQM5"
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a SIGKILLed process is "
              f"identified as killed, and names its phase"
              + (f"  -- {rec.get('phase')}" if rec else ""))
    if not ok:
        fails.append("kill not detected")

    # 2. a process that stops cleanly does NOT look killed.
    #    REPEATED, because the failure here was a race between the
    #    sampler thread and stop(): it passed once and failed under
    #    load. A diagnostic that invents crashes is worse than none, so
    #    this runs enough times to make the race show itself.
    bad2 = 0
    for _ in range(8):
        prog2 = (f"import sys; sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))!r});"
                 f"from researcher import blackbox as B;"
                 f"B.start({d!r}); B.phase('tidy exit'); B.stop()")
        subprocess.run([sys.executable, "-c", prog2], timeout=60, check=True)
        if postmortem(d) is not None:
            bad2 += 1
    ok2 = bad2 == 0
    if verbose:
        print(f"  {'PASS' if ok2 else 'FAIL'}  a clean shutdown is NOT "
              f"reported as a crash, 8 times out of 8"
              + (f"  -- {bad2} false crashes" if bad2 else ""))
    if not ok2:
        fails.append(f"clean shutdown looked like a kill {bad2}/8")

    # 3. a FORKED CHILD must not be able to clear the parent's dirty
    #    bit. The searcher forks workers, and a child inheriting this
    #    module's state is the one way the record could lie.
    d3 = tempfile.mkdtemp()
    start(d3)
    phase("parent working")
    pid = os.fork()
    if pid == 0:                      # child: try to falsify the record
        try:
            stop()
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    ok_fork = postmortem(d3) is not None      # parent still looks alive
    _S["stop"] = True                          # tidy this test's thread
    if verbose:
        print(f"  {'PASS' if ok_fork else 'FAIL'}  a forked worker cannot "
              f"clear the parent's shutdown flag")
    if not ok_fork:
        fails.append("child cleared the dirty bit")

    # 4. a truncated/corrupt file must not raise at boot
    with open(os.path.join(d, NAME), "w") as fh:
        fh.write('{"rss_mb": 12')
    try:
        ok3 = postmortem(d) is None
    except Exception:                                         # noqa: BLE001
        ok3 = False
    if verbose:
        print(f"  {'PASS' if ok3 else 'FAIL'}  a half-written record is "
              f"ignored rather than raised at boot")
    if not ok3:
        fails.append("corrupt record raised")
    return fails

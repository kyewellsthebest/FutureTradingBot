"""Run market sweeps in PROCESSES, because threads were doing nothing.

THE MEASUREMENT THAT FORCED THIS.

    4 markets x 200 hypotheses
      sequential      5.11s
      4 threads       5.70s     0.90x
      4 processes     1.69s     2.95x   (74% of perfect)

The thread pool was not merely inefficient, it was SLOWER than doing the
work one market at a time. Everything expensive in a hypothesis
evaluation -- building masks, gathering entries, walking the bracket --
is either Python-level or too small for numpy to bother releasing the
GIL, so the pool serialised itself and paid the scheduling on top. On a
32-core box, threads would leave 31 cores idle.

WHY IT COULD NOT SIMPLY BE SWAPPED. sweep() mutates shared state as it
goes: it records into the ledger, bumps the trial count, asks for the
current bar, notes outcomes into memory, appends adaptations, and adds
to the pooled book. None of that survives a process boundary, and
"just move the mutations out" would have meant rewriting the two
hundred lines that do the actual searching.

So instead the worker is handed PROXIES that answer reads from a
snapshot and BUFFER writes. sweep() is unchanged -- it cannot tell the
difference -- and the parent replays the buffered writes in order when
the worker returns. One process owns the ledger, exactly as before, and
the thing that must never be raced (the trial count that sets the bar)
is still only ever touched in one place.

WHAT THE SNAPSHOT COSTS. Nothing, on Linux. The pool forks, so children
share the parent's tapes, its fingerprint set and its priors
copy-on-write. Workers only read them, so no page is ever copied.

ONE DELIBERATE SEMANTIC CHANGE, and it is an improvement. Every
hypothesis in a cycle is now judged against the SAME bar -- the one
snapshotted when the cycle began -- instead of against a bar that crept
upward as its neighbours were scored. Previously the cell tested first
in a cycle faced an easier standard than the cell tested last, purely
because of arrival order. A fixed within-cycle bar is both fairer and
easier to reason about, and it is never lower than the bar the trials
justify: the count catches up at the end of the cycle.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import traceback


class LedgerProxy:
    """Reads from a snapshot; writes go into a buffer for the parent.

    Deliberately mimics only the six methods sweep() actually calls. A
    proxy that quietly accepted every attribute would let a future
    caller mutate real state inside a worker and lose it silently.
    """

    def __init__(self, seen, bar, priors, trials, families):
        self._seen = seen              # shared, read-only, copy-on-write
        self._bar = float(bar)
        self._priors = priors
        self._new = set()              # fingerprints recorded this sweep
        self.records = []              # (hyp, result, family)
        self.bumps = 0
        self.d = {"trials": int(trials), "families": families}

    # -- reads
    @staticmethod
    def fingerprint(hyp):
        from researcher.ledger import Ledger
        return Ledger.fingerprint(hyp)

    def seen(self, hyp) -> bool:
        fp = self.fingerprint(hyp)
        return fp in self._seen or fp in self._new

    def bar(self, extra=0) -> float:
        return self._bar

    def family_prior(self, family) -> float:
        return float(self._priors.get(family, 1.0))

    # -- buffered writes
    def record(self, hyp, result, family=None):
        fp = self.fingerprint(hyp)
        self._new.add(fp)
        self.records.append((hyp, result, family))
        # keep the local view of the count honest so anything that seeds
        # a generator from it still varies within the sweep
        self.d["trials"] += 1
        return fp

    def bump(self, n):
        self.bumps += int(n)
        self.d["trials"] += int(n)


class MemoryProxy:
    """Same idea for the lesson store: snapshot reads, buffered writes."""

    def __init__(self, holds, insights, lessons):
        self._holds = holds
        self._insights = insights
        self._lessons = lessons
        self.notes = []                # (family, mode, result)
        self.adapts = []               # (kind, family, kwargs)

    def hold_multiplier(self, family):
        return float(self._holds.get(family, 1.0))

    def insights(self):
        return self._insights

    def target_horizon(self, family):
        return (self._insights.get("target_horizons") or {}).get(family)

    def lesson(self, family):
        return self._lessons.get(family, ("no lesson yet", 1.0))

    def note(self, family, mode, result):
        self.notes.append((family, mode, result))

    def adapt(self, kind, family, **kw):
        self.adapts.append((kind, family, kw))


def snapshot(led, mem):
    """Everything a worker needs to read, taken once under the lock."""
    with led._lock:
        seen = set(led.d["tested"])
        trials = int(led.d["trials"])
        bar = led.bar()
        families = {k: dict(v) for k, v in led.d["families"].items()}
        priors = {k: led.family_prior(k) for k in families}
    holds, lessons = {}, {}
    for fam in set(families) | set(mem.d.get("families", {})):
        try:
            adv, mult = mem.lesson(fam)
            lessons[fam] = (adv, mult)
            holds[fam] = mem.hold_multiplier(fam)
        except Exception:                                     # noqa: BLE001
            continue
    return {"seen": seen, "bar": bar, "priors": priors, "trials": trials,
            "families": families, "holds": holds,
            "insights": mem.insights(), "lessons": lessons}


def replay(led, mem, out):
    """Apply a worker's buffered writes in the parent. Single-threaded.

    Order matters: bumps before records, so the trial count -- and
    therefore the bar the NEXT cycle faces -- reflects feature scoring
    as well as hypothesis scoring, exactly as it did when everything
    ran in one process.
    """
    if out.get("bumps"):
        led.bump(out["bumps"])
    for hyp, result, family in out.get("records", ()):
        led.record(hyp, result, family=family)
    for family, mode, result in out.get("notes", ()):
        try:
            mem.note(family, mode, result)
        except Exception:                                     # noqa: BLE001
            pass
    for kind, family, kw in out.get("adapts", ()):
        try:
            mem.adapt(kind, family, **kw)
        except Exception:                                     # noqa: BLE001
            pass


# ---------------------------------------------------------------- worker
_CTX = {}


def _init(ctx):
    """Runs once per worker. With fork, `ctx` arrives copy-on-write."""
    _CTX.update(ctx)


def _run(job):
    """One market, in a worker process. Returns everything to replay."""
    sym, tier, budget = job
    try:
        from researcher import runner as R
        from researcher import pooled as PO
        snap = _CTX["snap"]
        data = _CTX["data"]
        d = data.get(sym)
        if d is None:
            return {"sym": sym, "error": f"no tape for {sym}"}
        led = LedgerProxy(snap["seen"], snap["bar"], snap["priors"],
                          snap["trials"], snap["families"])
        mem = MemoryProxy(snap["holds"], snap["insights"], snap["lessons"])
        book = PO.PooledBook()
        # The worker gets its OWN feature libraries and its own pooled
        # book; both are merged by the parent. Sharing them would mean
        # sharing mutable state across processes, which is the thing
        # this design exists to avoid.
        libs = dict(_CTX.get("libs") or {})
        R.SLATE["hyps"] = _CTX.get("slate") or []
        R.SLATE["book"] = book
        R.SLATE["surrogate"] = _CTX.get("surrogate")
        tv, cost = R.SPEC[sym]
        pts, mrows = {}, {}
        out, err = R.sweep(sym, d, led, mem, libs, tier, tv, cost,
                           budget=budget, points=pts, mrows=mrows)
        if err:
            return {"sym": sym, "error": err}
        done, cands, kept = out
        return {
            "sym": sym, "tier": tier, "done": done,
            "records": led.records, "bumps": led.bumps,
            "notes": mem.notes, "adapts": mem.adapts,
            "book": book.rows,
            "kept": list(kept),
            "points": pts, "mrows": mrows,
            "libs": {k: {"kept": v.kept, "scores": v.scores}
                     for k, v in libs.items()},
            # Candidates carry DataFrames, which must not cross a
            # process boundary; the parent re-derives those. Everything
            # else in the tuple travels, INCLUDING the sweep's empirical
            # null and its cross-market rows -- both are controls the
            # gauntlet applies, and quietly replacing them with None
            # would have disabled two checks while looking like
            # plumbing.
            "candidates": [(c[0], c[1], c[2], c[3], c[7], c[8])
                           for c in cands],
        }
    except Exception:                                         # noqa: BLE001
        return {"sym": sym, "error": traceback.format_exc()[-1200:]}


class Pool:
    """A fork-based pool that keeps the tapes in shared pages."""

    def __init__(self, workers, ctx):
        self.workers = max(1, int(workers))
        mpctx = mp.get_context("fork" if hasattr(os, "fork") else "spawn")
        self.pool = mpctx.Pool(self.workers, initializer=_init,
                               initargs=(ctx,))

    def map(self, jobs):
        return self.pool.map(_run, list(jobs))

    def close(self):
        try:
            self.pool.close()
            self.pool.join()
        except Exception:                                     # noqa: BLE001
            try:
                self.pool.terminate()
            except Exception:                                 # noqa: BLE001
                pass


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """The proxies must behave exactly like the objects they stand in for.

    A proxy that silently diverges would corrupt the trial count, and
    the trial count is what sets the bar. There is no more dangerous
    thing in this system to get subtly wrong.
    """
    import tempfile
    from researcher.ledger import Ledger
    from researcher.memory import Memory
    fails = []

    d = tempfile.mkdtemp()
    led = Ledger(os.path.join(d, "l.json"))
    mem = Memory(os.path.join(d, "m.json"))
    for i in range(50):
        led.record({"x": i, "market": "NQ", "tier": 1},
                   {"z": i * 0.01, "net": 0.0, "edge": 0.0, "n": 100},
                   family="fam/a")
    snap = snapshot(led, mem)

    p = LedgerProxy(snap["seen"], snap["bar"], snap["priors"],
                    snap["trials"], snap["families"])
    ok = (p.seen({"x": 3, "market": "NQ", "tier": 1})
          and not p.seen({"x": 999, "market": "NQ", "tier": 1}))
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  proxy sees what the ledger "
              f"has already tested")
    if not ok:
        fails.append("seen() wrong")

    # a fingerprint recorded inside the worker must not be handed out twice
    h = {"x": 999, "market": "NQ", "tier": 1}
    p.record(h, {"z": 1.0}, "fam/a")
    ok = p.seen(h)
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a hypothesis recorded inside "
              f"the worker is not tested again by that worker")
    if not ok:
        fails.append("within-worker dedup broken")

    # replay must move the count by exactly the buffered amount
    p.bump(7)
    before = led.d["trials"]
    replay(led, mem, {"bumps": p.bumps, "records": p.records,
                      "notes": [], "adapts": []})
    moved = led.d["trials"] - before
    ok = moved == 8            # 1 record + 7 bumps
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  replay moves the trial count "
              f"by exactly what the worker spent  — {moved} (expect 8)")
    if not ok:
        fails.append(f"replay moved {moved}, expected 8")

    ok = led.seen(h)
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  the worker's record reaches "
              f"the real ledger")
    if not ok:
        fails.append("record did not survive replay")

    # the proxy must refuse to answer for things it does not model, so a
    # future caller cannot mutate real state inside a worker by accident
    ok = not hasattr(p, "confirm") and not hasattr(p, "touch_vault")
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  proxy does not pretend to "
              f"offer confirm() or the vault")
    if not ok:
        fails.append("proxy exposes state-changing methods it cannot honour")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\nparallel selftest:", "PASS" if not f else f"FAIL {f}")

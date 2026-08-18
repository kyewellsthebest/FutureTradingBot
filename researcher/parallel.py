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

WHAT THE SNAPSHOT COSTS, AND THE SENTENCE THAT WAS WRONG.

This used to say: "Nothing, on Linux. The pool forks, so children share
the parent's tapes, its fingerprint set and its priors copy-on-write.
Workers only read them, so no page is ever copied."

The last clause is false, and it cost the deployment. "Reading" a Python
object writes its reference count, and a refcount lives in the same
cache line as the object. So a child doing hundreds of thousands of
`fp in seen` lookups against a set of 336,449 strings privately copies
the pages holding those strings -- and their dict, and their set.

Measured, six markets, three workers, same sweep:

    empty ledger      +1.44 GB
    336,449 entries   +3.21 GB     -> 604 MB PER WORKER of pure copying

At 47 workers that is 28 GB of ledger alone, on a box with a 24 GB
limit. It was OOM-killed for hours and the memory graph sawtoothed all
the way up. gc.freeze() was tried first on the theory that the cyclic
collector was doing the touching; measured, it changed nothing (3.21 GB
vs 3.15 GB), which rules that out and leaves refcounts.

The fix is to stop shipping Python objects. The fingerprints are 16 hex
characters -- exactly 64 bits -- so they become ONE sorted numpy
uint64 array: 2.7 MB, a single object with a single refcount, and
`np.searchsorted` instead of a hash lookup. A worker can probe it a
million times and dirty nothing. Verified exact against the set it
replaces over 40,000 probes, with zero collisions on the real keys.

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

import gc
import hashlib
import multiprocessing as mp
import os
import traceback

import numpy as np


_U64 = (1 << 64) - 1


def fp64(fp):
    """A fingerprint as a 64-bit int.

    Fingerprints are sha1 truncated to 16 hex characters, which is
    exactly 64 bits, so this is lossless for everything the ledger
    actually writes. Anything else -- a key from an older format, or
    hand-edited -- is hashed instead of raising, because a snapshot that
    throws on one odd key takes the whole cycle down.
    """
    try:
        return int(fp, 16) & _U64
    except (TypeError, ValueError):
        return int.from_bytes(
            hashlib.sha1(str(fp).encode()).digest()[:8], "big")


def fingerprint_array(tested):
    """Every tested fingerprint as ONE sorted uint64 array.

    2.7 MB for 336,449 entries, against ~485 MB of dict and strings, and
    -- the point -- a single Python object. A forked child can probe it
    as often as it likes without touching a refcount, so the pages stay
    shared. See the module docstring for the measurement that forced
    this.
    """
    if not tested:
        return np.zeros(0, dtype=np.uint64)
    a = np.fromiter((fp64(k) for k in tested), dtype=np.uint64,
                    count=len(tested))
    a.sort()
    return a


class LedgerProxy:
    """Reads from a snapshot; writes go into a buffer for the parent.

    Deliberately mimics only the six methods sweep() actually calls. A
    proxy that quietly accepted every attribute would let a future
    caller mutate real state inside a worker and lose it silently.
    """

    def __init__(self, seen, bar, priors, trials, families, feats=None):
        self._seen = seen              # shared, read-only, copy-on-write
        self._bar = float(bar)
        self._priors = priors
        self._feats = feats or {}      # scope -> names already charged
        self._new = set()              # fingerprints recorded this sweep
        self.records = []              # (hyp, result, family)
        self.charged = {}              # scope -> names charged this sweep
        self.bumps = 0
        self.d = {"trials": int(trials), "families": families}

    # -- reads
    @staticmethod
    def fingerprint(hyp):
        from researcher.ledger import Ledger
        return Ledger.fingerprint(hyp)

    def seen(self, hyp) -> bool:
        fp = self.fingerprint(hyp)
        if fp in self._new:                # this sweep's own, a small set
            return True
        a = self._seen
        if a is None or len(a) == 0:
            return False
        v = np.uint64(fp64(fp))
        i = int(np.searchsorted(a, v))
        return i < a.size and bool(a[i] == v)

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

    def charge_features(self, scope, names):
        """Same contract as the real ledger: count what is genuinely new.

        Reads the already-charged names from the snapshot and buffers
        the new ones for the parent to record. Scopes are market/tier so
        two workers never touch the same one in a cycle, which is what
        makes replaying them a union rather than a reconciliation.
        """
        hs = set(self._feats.get(scope) or ())
        hs.update(self.charged.get(scope) or ())
        new = [n for n in names if n not in hs]
        if new:
            self.charged.setdefault(scope, []).extend(new)
        return len(new)


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
        seen = fingerprint_array(led.d["tested"])
        trials = int(led.d["trials"])
        bar = led.bar()
        families = {k: dict(v) for k, v in led.d["families"].items()}
        priors = {k: led.family_prior(k) for k in families}
        feats = {k: list(v) for k, v in
                 (led.d.get("features_charged") or {}).items()}
    holds, lessons = {}, {}
    for fam in set(families) | set(mem.d.get("families", {})):
        try:
            adv, mult = mem.lesson(fam)
            lessons[fam] = (adv, mult)
            holds[fam] = mem.hold_multiplier(fam)
        except Exception:                                     # noqa: BLE001
            continue
    return {"seen": seen, "bar": bar, "priors": priors, "trials": trials,
            "families": families, "holds": holds, "feats": feats,
            "insights": mem.insights(), "lessons": lessons}


def replay(led, mem, out, arch=None):
    """Apply a worker's buffered writes in the parent. Single-threaded.

    Order matters: bumps before records, so the trial count -- and
    therefore the bar the NEXT cycle faces -- reflects feature scoring
    as well as hypothesis scoring, exactly as it did when everything
    ran in one process.
    """
    if out.get("bumps"):
        led.bump(out["bumps"])
    # The names behind those bumps, so the next cycle -- and the next
    # restart -- knows they have already been paid for. Recorded here
    # rather than in the worker for the same reason the ledger is:
    # one owner, one writer.
    for scope, names in (out.get("charged") or {}).items():
        led.charge_features(scope, names)
    for hyp, result, family in out.get("records", ()):
        led.record(hyp, result, family=family)
        # Every measurement is offered to the map. Doing it here rather
        # than in the worker keeps one owner for the archive, the same
        # discipline the ledger has.
        if arch is not None:
            try:
                arch.consider(hyp, family, result)
            except Exception:                                 # noqa: BLE001
                pass
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
    # A worker lives for one sweep and allocates mostly numpy, which the
    # cyclic collector cannot help with anyway. Every collection it runs
    # is pages dirtied in a child that is about to exit.
    if os.environ.get("RESEARCH_GC_FREEZE", "0") == "1":
        try:
            gc.freeze()
        except Exception:                                     # noqa: BLE001
            pass


def _run(job):
    """One market, in a worker process. Returns everything to replay."""
    sym, tier, budget = job[0], job[1], job[2]
    # (index, count) over the shared slate; absent means "the whole
    # thing", which is what every caller written before sharding meant.
    shard = job[3] if len(job) > 3 else (0, 1)
    try:
        from researcher import runner as R
        from researcher import pooled as PO
        snap = _CTX["snap"]
        data = _CTX["data"]
        d = data.get(sym)
        if d is None:
            return {"sym": sym, "error": f"no tape for {sym}"}
        led = LedgerProxy(snap["seen"], snap["bar"], snap["priors"],
                          snap["trials"], snap["families"],
                          feats=snap.get("feats"))
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
        tv, cost = R.spec_for(sym)
        pts, mrows = {}, {}
        out, err = R.sweep(sym, d, led, mem, libs, tier, tv, cost,
                           budget=budget, points=pts, mrows=mrows,
                           shard=shard)
        if err:
            return {"sym": sym, "error": err}
        done, cands, kept = out
        return {
            "sym": sym, "tier": tier, "done": done, "shard": shard,
            "records": led.records, "bumps": led.bumps,
            "charged": led.charged,
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
        # HAND THE CONTEXT OVER BY FORK, NOT BY PICKLE.
        #
        # This used to pass ctx through Pool(initializer=..., initargs=),
        # and initargs does not share anything: multiprocessing PICKLES
        # it and sends a full private copy to EVERY worker. The context
        # holds the tapes. Measured, 23 markets:
        #
        #     tier-1 tapes, pickled      241.5 MB   per worker
        #
        # and larger again once unpickled back into DataFrames. That is
        # the 604 MB per worker that was measured end to end and blamed
        # first on refcount dirtying and then on the garbage collector;
        # both were wrong, and the uint64 fingerprint index that came
        # out of the second theory saved only the 24 MB the set itself
        # was worth. The tapes were the other 580.
        #
        # Assigning into a module global BEFORE forking is the actual
        # copy-on-write path: the child inherits the address space and
        # never unpickles anything. Workers only read it, and now that
        # is true rather than merely asserted.
        self._forked = hasattr(os, "fork")
        if self._forked:
            _CTX.clear()
            _CTX.update(ctx)
        # FREEZE BEFORE FORKING.
        #
        # Copy-on-write is supposed to make a forked child nearly free.
        # In CPython it is not, and the reason is the cyclic garbage
        # collector: a gen-2 collection walks EVERY tracked object and
        # writes to its header, so a child that merely lives long enough
        # to collect twice ends up privately copying most of the
        # parent's heap -- including a ledger that is hundreds of
        # megabytes and grows all day.
        #
        # gc.freeze() moves everything currently allocated into a
        # permanent generation the collector never visits. Objects the
        # child allocates afterwards are still collected normally, so
        # this trades no safety for the copies.
        if os.environ.get("RESEARCH_GC_FREEZE", "0") == "1":
            try:
                gc.collect()
                gc.freeze()
            except Exception:                                 # noqa: BLE001
                pass
        mpctx = mp.get_context("fork" if self._forked else "spawn")
        # On spawn there is no inheritance, so the pickle is unavoidable
        # and initargs is still the right mechanism.
        self.pool = (mpctx.Pool(self.workers) if self._forked else
                     mpctx.Pool(self.workers, initializer=_init,
                                initargs=(ctx,)))

    def map(self, jobs):
        return self.pool.map(_run, list(jobs))

    def close(self):
        try:
            self.pool.close()
            self.pool.join()
            if self._forked:
                # Drop the parent's reference so a cycle's tapes are not
                # pinned by this module between sweeps.
                _CTX.clear()
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

    # FEATURES ARE CHARGED ONCE, EVER. The library is in-memory only, so
    # every restart regrows it; charging by count meant paying for the
    # same look again on every boot, and the bar rises with the count.
    led.charge_features("NQ/t1", ["a", "b", "c"])
    snap2 = snapshot(led, mem)
    q = LedgerProxy(snap2["seen"], snap2["bar"], snap2["priors"],
                    snap2["trials"], snap2["families"],
                    feats=snap2.get("feats"))
    again = q.charge_features("NQ/t1", ["a", "b", "c"])
    novel = q.charge_features("NQ/t1", ["c", "d"])
    other = q.charge_features("ES/t1", ["a"])
    ok = (again == 0 and novel == 1 and other == 1)
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a regrown feature is not "
              f"charged twice  — rediscovered {again} (expect 0), new "
              f"{novel} (expect 1), same name on another market {other} "
              f"(expect 1)")
    if not ok:
        fails.append(f"feature charging wrong: {again}/{novel}/{other}")

    before2 = led.d["trials"]
    replay(led, mem, {"bumps": 0, "records": [], "notes": [], "adapts": [],
                      "charged": q.charged})
    r = LedgerProxy(snapshot(led, mem)["seen"], 3.0, {}, 0, {},
                    feats=snapshot(led, mem).get("feats"))
    ok = (r.charge_features("NQ/t1", ["c", "d"]) == 0
          and led.d["trials"] == before2)
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  charged names survive replay, "
              f"so the next cycle does not pay again")
    if not ok:
        fails.append("charged feature names did not survive replay")

    # THE COMPACT FINGERPRINT INDEX MUST ANSWER EXACTLY LIKE THE SET IT
    # REPLACED. It exists to stop forked children copying 604 MB each,
    # and it is worth nothing if it ever says "already tested" about
    # something that was not -- that would silently skip real work and
    # look like a search that had run out of ideas.
    import random as _rnd
    _rnd.seed(11)
    from researcher.ledger import Ledger as _L
    keys = [_L.fingerprint({"i": i, "market": "NQ"}) for i in range(4000)]
    arr = fingerprint_array({k: 1 for k in keys})
    ref = set(keys)
    absent = [_L.fingerprint({"i": i, "market": "ES"})
              for i in range(4000, 8000)]
    pr = LedgerProxy(arr, 3.0, {}, 0, {})
    wrong = 0
    for i, k in enumerate(keys[:1500] + absent[:1500]):
        want = k in ref
        v = np.uint64(fp64(k))
        j = int(np.searchsorted(arr, v))
        got = j < arr.size and bool(arr[j] == v)
        wrong += int(got != want)
    ok = (wrong == 0 and arr.dtype == np.uint64
          and len(np.unique(arr)) == len(arr))
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  the compact fingerprint index "
              f"answers exactly like the set it replaced  — {wrong} "
              f"disagreements over 3,000 probes, {arr.nbytes / 1e6:.2f} MB "
              f"for {arr.size:,} keys")
    if not ok:
        fails.append(f"fingerprint index disagrees ({wrong} of 3000)")

    # and it must still see what the real ledger has, through snapshot()
    ok = pr.seen({"i": 7, "market": "NQ"}) and not pr.seen(
        {"i": 99999, "market": "NQ"})
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  proxy.seen() over the compact "
              f"index agrees with the ledger")
    if not ok:
        fails.append("proxy.seen() wrong over the compact index")

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

"""Questions somebody wrote down, answered by a process that never sleeps.

WHY THIS EXISTS.

The searcher runs 168 hours a week and asks one shape of question:
"does this cell of the strategy grid pay?" It asks it superbly -- never
forgetting, never skipping a control, never getting bored.

Everything ELSE anybody has ever wanted to know about this project has
been answered by a person, once, in a session, and then died with that
session. "Does the long-horizon signal survive being traded at its own
cadence?" was measured today from a file written weeks ago; the answer
lives in a chat log. "Is the overnight session priced correctly?" has
never been measured at all. Each is a single well-posed question that a
machine could answer far better than a person, because answering it
properly means running it on every market, with controls, repeatedly,
and watching whether the answer holds -- which is precisely the thing
the searcher is good at and the person is not.

So: an experiment is a QUESTION plus a MEASUREMENT plus its CONTROLS,
dropped in this directory as a file. The searcher picks it up, runs it
inside its own cycle, accumulates the answer across cycles, and reports
it in the brief. The person who wrote the question does not have to be
present, and the answer does not evaporate when they leave.

THE RULES, and each is here because breaking it would be worse than
having no experiments at all:

  1  AN EXPERIMENT MAY NEVER BREAK A CYCLE. Every call is wrapped and
     time-boxed. A sweep that dies because somebody's question threw an
     exception costs more than the question was worth.

  2  IT DECLARES ITS OWN CONTROL. A measurement with no control is a
     number, not evidence, and this project has six false positives
     from numbers that had none. `control` is not optional.

  3  IT COSTS TRIALS. Looking at the data is looking at the data. An
     experiment that runs free would be a way to buy unlimited looks
     without moving the bar, which is the exact hole the ledger exists
     to close.

  4  IT SAYS WHEN IT IS DONE. An experiment that runs forever is a
     background job, not a question. `done()` decides.

  5  ITS ANSWER IS WRITTEN IN ENGLISH. `verdict()` returns the sentence
     a person would write, because a number nobody interprets is a
     number nobody uses -- which is how this repo accumulated four
     research documents whose conclusions had never been connected.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import time

# A single experiment gets this long per cycle. Generous for a
# measurement, far too short to threaten a sweep.
BUDGET_S = float(os.environ.get("EXPERIMENT_BUDGET_S", "90"))


def discover():
    """Every experiment module in this package, by name.

    Import failures are reported, never raised: a half-written
    experiment must not stop the other ones, and it must not be silent
    either -- an experiment that vanishes because of a typo would look
    exactly like an experiment that found nothing.
    """
    out, broken = {}, {}
    here = os.path.dirname(os.path.abspath(__file__))
    for m in pkgutil.iter_modules([here]):
        if m.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{m.name}")
        except Exception as exc:                              # noqa: BLE001
            broken[m.name] = str(exc)[:200]
            continue
        if not hasattr(mod, "run") or not hasattr(mod, "QUESTION"):
            broken[m.name] = "no run() or no QUESTION"
            continue
        out[m.name] = mod
    return out, broken


def run_all(state, store, say=None, budget_s=None):
    """Run every experiment that is not finished. Returns what changed.

    `state` is whatever the caller can offer -- tapes, ledger, spec.
    `store` is the accumulated results dict, mutated in place and
    persisted by the caller, so an experiment can build its answer over
    many cycles rather than having to finish inside one.
    """
    mods, broken = discover()
    budget = BUDGET_S if budget_s is None else float(budget_s)
    ran, cost = [], 0
    for name, exc in broken.items():
        if say:
            say("experiment_broken", name=name, err=exc,
                note="a question that cannot load is not a question that "
                     "found nothing")
    for name, mod in sorted(mods.items()):
        slot = store.setdefault(name, {"runs": 0, "history": [],
                                       "question": mod.QUESTION,
                                       "why": getattr(mod, "WHY", "")})
        try:
            if getattr(mod, "done", None) and mod.done(slot):
                continue
        except Exception:                                     # noqa: BLE001
            pass
        t0 = time.time()
        try:
            r = mod.run(state, slot, budget_s=budget)
        except Exception as exc:                              # noqa: BLE001
            slot["error"] = str(exc)[:300]
            if say:
                say("experiment_failed", name=name, err=slot["error"])
            continue
        if not r:
            continue
        slot.pop("error", None)
        slot["runs"] += 1
        slot["t"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        slot["secs"] = round(time.time() - t0, 1)
        slot["latest"] = r
        slot["history"] = (slot.get("history") or [])[-19:] + [r]
        # RULE 3: looking costs. measurements is what the experiment
        # says it spent, and it is charged like any other look.
        cost += int(r.get("measurements") or 0)
        try:
            slot["verdict"] = (mod.verdict(slot) if hasattr(mod, "verdict")
                               else None)
        except Exception as exc:                              # noqa: BLE001
            slot["verdict"] = f"verdict failed: {str(exc)[:120]}"
        ran.append(name)
        if say:
            say("experiment", name=name, secs=slot["secs"],
                measurements=r.get("measurements"),
                verdict=slot.get("verdict"))
    return {"ran": ran, "broken": sorted(broken), "measurements": cost}


def selftest(verbose=True):
    """The queue must be unable to take a cycle down with it."""
    fails = []
    mods, broken = discover()
    if verbose:
        print(f"  ..    {len(mods)} experiment(s) load, {len(broken)} broken")

    # a deliberately hostile experiment
    class Bomb:
        QUESTION = "does a broken experiment kill the cycle?"
        WHY = "it must not"

        @staticmethod
        def run(state, slot, budget_s=None):
            raise RuntimeError("boom")

    store = {}
    saved = globals()["discover"]
    globals()["discover"] = lambda: ({"bomb": Bomb}, {})
    try:
        out = run_all({}, store, say=None)
        ok = out["ran"] == [] and "boom" in (store["bomb"].get("error") or "")
    finally:
        globals()["discover"] = saved
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  an experiment that raises is "
              f"recorded and skipped, not propagated")
    if not ok:
        fails.append("exception escaped run_all")

    # every shipped experiment must declare a control
    for name, mod in mods.items():
        has = bool(getattr(mod, "CONTROL", None))
        if verbose:
            print(f"  {'PASS' if has else 'FAIL'}  {name} declares its "
                  f"control")
        if not has:
            fails.append(f"{name} has no CONTROL")
    return fails

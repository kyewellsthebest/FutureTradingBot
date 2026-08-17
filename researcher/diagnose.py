"""Differential diagnosis: not "this is suspicious" but "this is WHY".

plausible.py is a smoke alarm. It knows that a 96% win rate cannot be
real and it can list the usual suspects. What it cannot do is tell you
WHICH suspect, and that gap is where every hour of this project's
debugging time has gone.

The insight is that the suspects are DISTINGUISHABLE, because each one
responds differently to a different perturbation. Delaying the entry by
one bar destroys a timing leak completely and barely touches a real
slow-moving edge. Doubling the cost kills a cost-marginal effect and
leaves a large one standing. Sliding the signal forward in time kills
anything that genuinely depends on the signal and leaves a time-of-day
drift untouched. None of these tests is individually conclusive; the
PATTERN across them is.

So this runs the battery and reads the pattern. It is the same procedure
a person uses when a number looks wrong -- change one thing at a time
and see what moves -- written down so it happens every time instead of
whenever somebody thinks to do it.

  perturbation          a real edge      a timing leak     a drift
  --------------------  ---------------  ----------------  -----------
  enter one bar later   mostly survives  collapses         survives
  enter five bars late  decays slowly    already gone      survives
  double the cost       shrinks by cost  irrelevant        shrinks
  slide signal +30min   collapses        collapses         SURVIVES
  first half only       similar          similar           may differ
  flip the direction    mirrors          mirrors           mirrors

The final column is the one that matters most and the one nobody thinks
to run: an "edge" that survives sliding its own signal half an hour into
the future was never about the signal.

WHAT IT STILL CANNOT DO. Diagnose a cause nobody has thought of. The
tick-ordering bug was found by reasoning from an impossible number to
its only possible explanation, and there was no perturbation in any
battery that would have isolated it. This mechanises the known
differentials; it does not replace the thinking.
"""
from __future__ import annotations

import numpy as np

# Below this many trades the perturbations are noise and the diagnosis
# would be a coin flip wearing a lab coat.
MIN_N = 120


def battery(evaluate, d, h, tv, cost, bar_s, feats=None):
    """Run the discriminating perturbations. Returns raw measurements."""
    def run(**kw):
        try:
            hh = dict(h)
            shift = kw.pop("shift_signal", 0)
            if shift:
                hh["_shift"] = shift
            r = evaluate(d, hh, tv, kw.pop("cost", cost), feats, bar_s,
                         **kw)
            return r if r and r.get("n", 0) >= MIN_N else None
        except Exception:                                     # noqa: BLE001
            return None

    out = {"base": run()}
    for k in (1, 2, 3, 5):
        out[f"delay{k}"] = run(delay=k)
    out["cost2"] = run(cost=cost * 2.0)
    return out


def read(b, cost):
    """Turn the battery's numbers into a named cause.

    Every branch states the evidence that produced it, because a
    diagnosis you cannot check is just a different kind of assertion.
    """
    base = b.get("base")
    if not base:
        return None
    n0 = float(base.get("net") or 0.0)
    if abs(n0) < 1e-9:
        return None

    def keep(k):
        r = b.get(k)
        if not r:
            return None
        return float(r.get("net") or 0.0) / n0

    k1, k2, k3, k5 = keep("delay1"), keep("delay2"), keep("delay3"), keep("delay5")
    kc = keep("cost2")
    ev = {"net": round(n0, 3),
          "kept_after_delay": {k: (None if v is None else round(v, 3))
                               for k, v in
                               (("1 bar", k1), ("2 bars", k2),
                                ("3 bars", k3), ("5 bars", k5))},
          "kept_at_double_cost": None if kc is None else round(kc, 3)}

    if k1 is None:
        return {"cause": "not measurable",
                "confidence": "low",
                "what_it_means": "Too few trades survive the perturbations "
                                 "to tell these explanations apart.",
                "evidence": ev}

    # 1. THE TIMING LEAK. Collapses on the first bar of delay and does
    #    not keep decaying -- because there was never a decaying signal,
    #    only information from inside the entry bar.
    later = [v for v in (k2, k3, k5) if v is not None]
    flat_after = (not later) or (max(later) - min(later) < 0.25)
    if k1 < 0.35 and flat_after:
        return {"cause": "entry-timing leak",
                "confidence": "high",
                "what_it_means":
                    "The edge lives inside the bar it was selected on. "
                    "Entering one bar later removes "
                    f"{(1 - k1) * 100:.0f}% of it and delaying further "
                    "changes nothing more, which is the signature of "
                    "information that was never available in time rather "
                    "than of a signal that fades. It cannot be traded.",
                "evidence": ev}

    # 2. GENUINELY FAST. Decays smoothly with delay: a real but
    #    short-lived signal. Tradeable only if you can act inside the
    #    decay, which is an execution question, not a research one.
    if k1 >= 0.35 and k5 is not None and k5 < k1 * 0.6:
        return {"cause": "real but short-lived",
                "confidence": "medium",
                "what_it_means":
                    f"Keeps {k1 * 100:.0f}% after one bar and "
                    f"{k5 * 100:.0f}% after five, decaying smoothly rather "
                    "than vanishing. That is what an actual fast signal "
                    "looks like. Whether it can be traded is now a "
                    "question about execution speed, not about the data.",
                "evidence": ev}

    # 3. COST-MARGINAL. Survives delay but not the cost of trading it.
    if kc is not None and kc < 0.2 and k1 > 0.7:
        return {"cause": "real but too small to pay",
                "confidence": "high",
                "what_it_means":
                    "Survives being entered late, so the timing is "
                    "honest, but doubling the round trip removes "
                    f"{(1 - kc) * 100:.0f}% of it. The effect is real and "
                    "smaller than the cost of harvesting it. Worth "
                    "revisiting only at a lower cost per trade.",
                "evidence": ev}

    # 4. ROBUST. Nothing shifted it. This is the interesting one, and
    #    the correct response is more scrutiny, not celebration.
    if k1 > 0.7 and (k5 is None or k5 > 0.5):
        return {"cause": "survives every perturbation",
                "confidence": "medium",
                "what_it_means":
                    "Delay does not touch it and cost does not remove it. "
                    "That is either a real slow-moving effect or something "
                    "the battery is not built to catch — a drift or a "
                    "calendar artifact that does not depend on the signal "
                    "at all. The stale-signal placebo in validate.py is "
                    "the next test, and it is the one that separates "
                    "those two.",
                "evidence": ev}

    return {"cause": "partially fragile",
            "confidence": "low",
            "what_it_means":
                f"Keeps {k1 * 100:.0f}% after one bar with no clean "
                "pattern across the rest of the battery. Not obviously "
                "an artifact, not obviously real.",
            "evidence": ev}


def diagnose(evaluate, d, h, tv, cost, bar_s, feats=None):
    return read(battery(evaluate, d, h, tv, cost, bar_s, feats), cost)


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """Each known failure mode must be told apart from the others.

    Synthetic batteries with the exact response profile of each cause,
    so the reader is graded on reading, not on measurement.
    """
    fails = []

    def fake(net, k1, k2, k3, k5, kc):
        b = {"base": {"net": net, "n": 900}}
        for name, k in (("delay1", k1), ("delay2", k2), ("delay3", k3),
                        ("delay5", k5), ("cost2", kc)):
            b[name] = None if k is None else {"net": net * k, "n": 900}
        return b

    cases = [
        # a timing leak: gone at one bar, flat thereafter
        ("entry-timing leak", fake(15.0, 0.06, 0.05, 0.04, 0.05, 0.06)),
        # a fast but real signal: smooth decay
        ("real but short-lived", fake(1.2, 0.80, 0.62, 0.48, 0.30, 0.55)),
        # real, honest timing, eaten by cost
        ("real but too small to pay", fake(0.30, 0.92, 0.90, 0.88, 0.85, 0.05)),
        # unmoved by anything
        ("survives every perturbation", fake(2.0, 0.95, 0.93, 0.91, 0.90, 0.70)),
    ]
    for want, b in cases:
        got = read(b, 0.6)
        ok = got and got["cause"] == want
        if verbose:
            print(f"  {'PASS' if ok else 'FAIL'}  tells apart: {want}"
                  + ("" if ok else f"  — said {got and got['cause']!r}"))
        if not ok:
            fails.append(f"misdiagnosed {want}")

    # It must refuse rather than guess when the battery is empty.
    got = read({"base": {"net": 5.0, "n": 900}}, 0.6)
    ok = got and got["cause"] == "not measurable"
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  refuses to diagnose without "
              f"a battery")
    if not ok:
        fails.append("guessed with no evidence")

    # And it must not diagnose a zero-edge cell at all.
    ok = read({"base": {"net": 0.0, "n": 900}}, 0.6) is None
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  says nothing about a cell "
              f"with no edge to explain")
    if not ok:
        fails.append("diagnosed a null result")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\ndiagnose selftest:", "PASS" if not f else f"FAIL {f}")

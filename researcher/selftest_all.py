"""One command that checks everything: python -m researcher.selftest_all

WHY THIS EXISTS. The checks were spread across five files and nobody --
including me -- ran all of them before shipping. Twice I added an
evaluation path, forgot to wire the delay control into it, and the
searcher spent hours reporting artifacts as strategies. A control you
have to remember to run is not a control.

THE INVARIANT TEST is the important one and it is new. Everything else
here verifies that a component behaves; the invariant verifies that the
SYSTEM cannot commit the error class that has produced five of this
project's false positives:

    a hypothesis selects a bar using information known only at that
    bar's close, then enters at that same close

The test plants the purest possible version of that error -- a signal
that fires exactly when the close IS the bar's high -- and asserts the
evaluator scores it flat. Before ENTRY_LAG it scored $21.01 a trade at
96% wins. If a future path bypasses entries(), this test goes red
immediately rather than after a day of fake results on a dashboard.

Exit code 0 = everything passed.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("M2_REPO", os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RESEARCH_DIR", "/tmp/researcher_selftest")

FAIL = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAIL.append(f"{name}: {detail}")
    return ok


# ------------------------------------------------------- the invariant
def synthetic_walk(n=40000, seed=7, spread=0.25, sub=40):
    """A driftless walk with OHLC and a BID-ASK BOUNCE.

    Two details decide whether this test means anything.

    DEMEANED. The first version used raw standard normals, whose sample
    mean over 480,000 draws still leaves a visible drift -- +0.05 ATR
    over twelve bars, which is $0.94 a trade at MNQ scale. The test read
    that as a leak and failed clean code. Subtracting the sample mean
    makes "driftless" true rather than approximately true.

    BOUNCE. Every observed print lands on the bid or the ask, at random.
    Without it a synthetic close is rarely an extreme of its own bar and
    the close_high artifact barely appears -- 0.03 points here against
    -10.2 on real NQ 60-second bars. The artifact this whole test exists
    to catch is CAUSED by the bounce: selecting bars whose close is the
    maximum selects prints that happened to be at the ask, and the next
    print reverts to the mid. A synthetic without a spread cannot
    reproduce it, so a test built on one proves nothing.
    """
    rng = np.random.default_rng(seed)
    steps = rng.standard_normal(n * sub) * 2.0
    steps -= steps.mean()                       # exactly driftless
    true = 21000 + np.cumsum(steps)
    obs = true + rng.choice([-spread / 2, spread / 2], size=n * sub)
    px = obs.reshape(n, sub)
    idx = pd.date_range("2024-01-02 13:30", periods=n, freq="1min", tz="UTC")
    d = pd.DataFrame({
        "open": px[:, 0], "high": px.max(axis=1),
        "low": px.min(axis=1), "close": px[:, -1],
    }, index=idx)
    d["vol"] = rng.integers(100, 2000, n).astype(float)
    d["n"] = d["vol"]
    d["absret"] = d["close"].diff().abs()
    return d


def corrupt_closes(d, seed=3):
    """Reproduce the exact data bug that faked a $21/trade strategy.

    85.3% of rows in the raw tick files are out of chronological order,
    and tier2() aggregated close as ("px","last") -- the last row in
    FILE order. So every bar's close was a RANDOM trade from inside it
    while high and low stayed correct.

    That is what this does: replace each close with a uniform draw from
    its own bar's range. Selecting bars whose close sits high in the
    range then selects a randomly-high print, and the next bar reverts
    to the true price. -10.2 points on NQ 60s against an unconditional
    -0.03, which became "after close_high, go short" at $21.01 a trade
    and 96% wins.
    """
    rng = np.random.default_rng(seed)
    x = d.copy()
    u = rng.random(len(x))
    x["close"] = x["low"].values + u * (x["high"].values - x["low"].values)
    x["absret"] = x["close"].diff().abs()
    return x


def test_invariant():
    """The error class that has produced five false positives here.

    Structured as a POSITIVE and a NEGATIVE control together, because
    either alone is worthless. If the artifact does not appear with the
    lag disabled, the test is not exercising the bug and passing means
    nothing. Only "large without the lag, gone with it" is evidence.

    close_high fires when the close IS near the bar's maximum. With a
    bid-ask bounce that selects prints at the ask, so the next print
    reverts to the mid -- an edge made entirely of the spread, and
    untradeable because you cannot know a bar's close was its high
    until the bar has ended.
    """
    from researcher import runner as R
    # The tape is deliberately CORRUPTED in the way the real one was,
    # so the positive control has a real bug to detect. A test whose
    # positive control does not fire proves nothing at all.
    d = corrupt_closes(synthetic_walk())
    tv, cost = 2.0, 0.0        # zero cost: this is about bias, not economics
    ok_all = True
    for shape, ls in (("close_high", "short"), ("close_low", "long")):
        for exit_spec in (None, [2.0, 1.0]):
            h = {"kind": "shape", "shape": shape, "n": 3, "k": 1.5,
                 "ls": ls, "exit": exit_spec, "hold_s": 60, "cond": "none"}
            kind = "bracket" if exit_spec else "fixed-time"
            old = R.ENTRY_LAG
            try:
                R.ENTRY_LAG = 0
                leak = R.evaluate(d, h, tv, cost, None, 60.0)
            finally:
                R.ENTRY_LAG = old
            fixed = R.evaluate(d, h, tv, cost, None, 60.0)
            if not (leak and fixed):
                continue
            # positive control: the bug must be reproducible
            ok_all &= check(
                f"artifact reproduces · {shape}/{kind}",
                leak["net"] > 0.20,
                f"entering at the signal bar earns ${leak['net']:+.3f}"
                f"/trade from nothing")
            # negative control: the invariant must remove it
            removed = leak["net"] - fixed["net"]
            share = removed / max(abs(leak["net"]), 1e-9)
            # THE RIGHT QUESTION IS WHETHER THE TIMING LEAK IS GONE, not
            # whether the number reaches exactly zero. On a tape whose
            # closes are randomised, entry price carries measurement
            # error, and with an asymmetric bracket that error leaves a
            # residual of its own -- consistently ~$0.9 across seeds and
            # NOT decaying with further delay, which is the signature of
            # something that is not a timing leak. A timing leak shrinks
            # every time the entry moves further from the signal.
            # Only diagnose a residual that is actually there. Below 5%
            # of the artifact there is nothing left to explain, and
            # comparing two numbers near zero produces a verdict that is
            # pure sign noise -- which is what failed a 101%-removed
            # case a moment ago.
            negligible = share > 0.95
            more = None if negligible else R.evaluate(
                d, h, tv, cost, None, 60.0, delay=2)
            decays = (not negligible) and (
                more is None or more["net"] < fixed["net"] * 0.7)
            verdict_txt = ("nothing left to explain" if negligible else
                           "still shrinking with more delay - TIMING LEAK"
                           if decays else
                           "flat under further delay, so not a timing leak")
            ok_all &= check(
                f"invariant kills it - {shape}/{kind}",
                share > 0.90 and not decays,
                f"${leak['net']:+.3f} -> ${fixed['net']:+.3f} "
                f"({100 * share:.0f}% removed; residual {verdict_txt})")
    return ok_all


def test_tick_sorting():
    """Tier-2 bars must be built from time-ordered ticks.

    This is the bug itself, checked at source rather than through its
    symptoms: if the aggregation ever stops sorting, close becomes a
    random trade again and every tier-2 result silently rots.
    """
    from researcher import data_tiers as DT
    src = DT.tier2_sources(60)
    if not src:
        return check("tier-2 bars built from sorted ticks", True,
                     "no deep bars present to check")
    import inspect
    body = inspect.getsource(DT.tier2)
    return check("tier-2 aggregation sorts ticks by time",
                 "argsort" in body,
                 "" if "argsort" in body else
                 "close would be a random trade from inside the bar")


def test_bracket_unbiased():
    """A bracket on RANDOM entries must return ~0 on a driftless walk.

    Compared against a no-barrier hold on the same entries, not against
    zero: any residual drift in the sample affects both equally, so the
    difference isolates the barrier logic itself.
    """
    from researcher import brackets as BR
    d = synthetic_walk(seed=31)
    H, L, C, O = (d[c].values for c in ("high", "low", "close", "open"))
    unit = BR.atr(H, L, C, 60)
    rng = np.random.default_rng(5)
    ok = np.flatnonzero(np.isfinite(unit) & (unit > 0))
    ok = ok[ok + 14 < len(d)]
    sel = rng.choice(ok, min(15000, len(ok)), replace=False)
    base = float(np.mean((C[sel + 12] - C[sel]) / unit[sel]))
    worst = 0.0
    for st, tg in ((1.0, 2.0), (2.0, 1.0), (2.0, 2.0)):
        ex, _, _, _ = BR.run(sel, np.full(len(sel), 1.0), H, L, C,
                             st, tg, unit, 12, open_=O)
        got = float(np.mean((ex - C[sel]) / unit[sel]))
        worst = max(worst, abs(got - base))
    return check("bracket adds no bias of its own", worst < 0.05,
                 f"largest deviation from a plain hold {worst:.4f} ATR")


def test_planted_edge():
    """A real edge must still be found. A blind harness reports silence."""
    from researcher import runner as R
    from researcher.runner_selftest import walk
    good = all(R.selftest(walk(seed=s), 2.0, 0.60, 300.0)
               for s in (3, 11, 21))
    return check("planted edge still detected", good,
                 "" if good else "harness is blind — every silence it "
                                 "reports is worthless")


def test_brackets():
    from researcher import brackets as BR
    f = BR.selftest()
    return check("bracket engine (5 hand-checked cases)", not f,
                 "; ".join(f))


def test_context_lag():
    from researcher import context as C
    f = C.lag_selftest(verbose=False)
    return check("external data respects publication lag", not f,
                 "; ".join(f))


def test_feature_parser():
    from researcher.features import FeatureLibrary as F
    cases = ["close", "z(vol,60)", "rank(chg(vol,1),240)",
             "abs(chg(ratio(close,60),3))", "chg(n,1)*ratio(close,60)",
             "z(rank(vol,60),20)*chg(chg(close,1),3)"]
    bad = [c for c in cases if F.name(F.parse(c)) != c]
    a = check("feature name/spec roundtrip", not bad, ", ".join(bad))

    # THE LIBRARY MUST SURVIVE A RESTART UNCHANGED. Discovery is
    # compositional -- each generation seeds from what the last one
    # kept -- so a library that comes back subtly different is a search
    # that silently resumes somewhere else. Only names and scores are
    # stored; the specs are rebuilt by parse(), and what has to match is
    # not the spec tuple but the ARRAY it produces.
    lib = F(keep=20)
    for c in cases:
        lib.kept[c] = F.parse(c)
        lib.scores[c] = 4.2
    back = F.load(lib.dump())
    same = (back.scores == lib.scores
            and all(back.kept[k] == lib.kept[k] for k in lib.kept)
            and not getattr(back, "_unparseable", 0))
    b = check("feature library survives a restart identically",
              same, f"{len(back.kept)} of {len(lib.kept)} rebuilt, "
                    f"{getattr(back, '_unparseable', 0)} unreadable")
    return a and b


def test_recent_window():
    """The complaint: "it's showing the exact same strategies, no updates."

    That was a correct observation about a board that was working as
    designed. It ranks by strength, strength is a MAXIMUM over
    everything ever tested, and a maximum only moves when something
    beats it -- so a strong early result pins the board for weeks while
    the search runs flat out behind it. Frozen is what success at not
    overfitting looks like, and it is indistinguishable from dead.

    So there are two views now, and this pins both: the all-time board
    must still surface the old high-water row, and the recent window
    must NOT.
    """
    import json as _j
    from datetime import datetime, timedelta, timezone as _tz
    from researcher.ledger import Ledger
    p = os.path.join(os.environ["RESEARCH_DIR"], "recent_test.json")
    if os.path.exists(p):
        os.remove(p)
    led = Ledger(p)
    old_t = (datetime.now(_tz.utc) - timedelta(days=3)).isoformat(
        timespec="seconds")
    new_t = datetime.now(_tz.utc).isoformat(timespec="seconds")
    led.record({"x": "ancient", "market": "NQ", "tier": 1},
               {"z": 5.37, "net": 0.9, "n": 900, "eff_n": 900}, "fam/a")
    led.d["tested"][led.fingerprint(
        {"x": "ancient", "market": "NQ", "tier": 1})]["t"] = old_t
    led.record({"x": "today", "market": "ES", "tier": 1},
               {"z": 2.10, "net": 0.4, "n": 800, "eff_n": 800}, "fam/a")
    led.d["tested"][led.fingerprint(
        {"x": "today", "market": "ES", "tier": 1})]["t"] = new_t

    board = led.near_misses(5)
    rec = led.recent_best(hours=24, k=5)
    top_all = (board[0]["hyp"] or {}).get("x") if board else None
    top_rec = (rec["rows"][0]["hyp"] or {}).get("x") if rec["rows"] else None
    a = check("the all-time board still shows the old high-water result",
              top_all == "ancient", f"showed {top_all!r}")
    b = check("the recent window excludes it and shows this cycle's best",
              top_rec == "today" and rec["considered"] == 1,
              f"showed {top_rec!r} from {rec['considered']} rows in window")
    c = check("every leaderboard row carries the date it was found",
              all(r.get("t") for r in board),
              f"{sum(1 for r in board if not r.get('t'))} rows undated")
    return a and b and c


def test_thread_safety():
    import threading
    from researcher.ledger import Ledger
    p = os.path.join(os.environ["RESEARCH_DIR"], "lock_test.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p):
        os.remove(p)
    led = Ledger(p)
    ts = [threading.Thread(target=lambda: [led.bump(1) for _ in range(2000)])
          for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    got = led.d["trials"]
    return check("ledger survives parallel writes", got == 16000,
                 f"{got:,} of 16,000 — lost updates make the bar too low"
                 if got != 16000 else "16,000 of 16,000")


def test_plausibility():
    from researcher import plausible as P
    f = P.selftest(verbose=False)
    return check("plausibility layer flags every artifact this project "
                 "actually produced", not f, "; ".join(f))


def test_pooled():
    """The cross-market combiner, which is now the primary instrument.

    If this is wrong the searcher does not merely miss things, it
    reports weak-and-broad artifacts with the authority of twenty-three
    markets behind them -- a more convincing lie than anything the
    per-market path could produce.
    """
    from researcher import pooled as P
    f = P.selftest(verbose=False)
    return check("pooled cross-market test: finds broad weak effects, "
                 "refuses single loud markets, discounts correlation",
                 not f, "; ".join(f))


def test_surrogate():
    from researcher import surrogate as S
    f = S.selftest(verbose=False)
    return check("map of the search space recovers real structure and "
                 "invents none", not f, "; ".join(f))


def test_diagnosis():
    from researcher import diagnose as D
    f = D.selftest(verbose=False)
    return check("differential diagnosis tells the known failure modes "
                 "apart", not f, "; ".join(f))


def test_archive():
    """The map, which is now what stops the search chasing rare cells."""
    from researcher import archive as A
    f = A.selftest(verbose=False)
    return check("map keeps an elite per behavioural niche and breeds "
                 "from them", not f, "; ".join(f))


def test_parallel():
    """The proxies that let sweeps run in processes.

    If these drift from the objects they stand in for, the trial count
    drifts -- and the trial count is what sets the bar.
    """
    from researcher import parallel as P
    f = P.selftest(verbose=False)
    return check("worker proxies account for every trial they spend",
                 not f, "; ".join(f))


def test_calibration():
    """The harness that measures what the searcher can SEE.

    Its own self-test caught a one-bar error in the plant that made
    entering on the marker bar pay more than the honest lagged entry --
    it would have measured the engine's ability to cheat and reported it
    as power.
    """
    from researcher import calibration as C
    f = C.selftest(verbose=False)
    return check("calibration harness recovers known edges and refuses "
                 "to reward look-ahead", not f, "; ".join(f))


def test_validators():
    from researcher import validate as V
    rng = np.random.default_rng(0)
    null = V.empirical_null(rng.standard_normal(5000))
    a = check("empirical null on pure noise", 2.0 < null < 3.2,
              f"p99 {null:.2f} (expect ~2.6)")
    # THE ASYMMETRY CASE, which the pure-noise test cannot see because
    # noise is symmetric. A real tape carries a heavy tail of cells that
    # reliably LOSE the round trip -- z of -30 with total certainty --
    # and folding those into the null once made it demand that a winner
    # beat the strength of the most confident loser. Measured on NQ 60s:
    # p99 of z was 2.49 while p99 of |z| was 27.13.
    skew = np.concatenate([rng.standard_normal(4000),
                           rng.normal(-30, 2, 400)])
    one = V.empirical_null(skew)
    two = V.empirical_null(skew, two_sided=True)
    a = check("empirical null ignores the loss tail, which is arithmetic "
              "rather than chance",
              one < 4.0 and two > 20.0,
              f"one-sided {one:.2f} (must stay near noise), "
              f"two-sided {two:.2f} (the old figure)") and a
    p = np.concatenate([rng.normal(2, 1, 300), rng.normal(-0.1, 1, 300)])
    st = V.period_stability(p, None)
    b = check("period stability catches a one-off regime",
              st["share"] <= 0.6, f"share {st['share']}")
    ok, _ = V.verdict(z=5.5, net=0.4, bar=4.9, null_p99=6.2,
                      stab={"share": 0.5, "agree": 3, "blocks": 6},
                      placebo={"gross": 0.9}, gross=1.0)
    c = check("verdict rejects a failing candidate", not ok)
    return a and b and c


def test_overlap():
    """Significance must not inflate with hold length on random data."""
    from researcher import runner as R
    from researcher.runner_selftest import walk, cells
    d = walk(seed=13)
    worst = 0.0
    for hs in (300, 1800, 3600, 10800):
        rs = cells(d, "none", holds=(hs,))
        if rs:
            worst = max(worst, max(abs(r["z"]) for r in rs))
    return check("overlap correction holds on random data", worst < 4.5,
                 f"max |z| {worst:.2f}")


def main():
    print("RESEARCHER — full self-test\n")
    print("THE INVARIANT (the error class that produced five false positives)")
    test_invariant()
    test_tick_sorting()
    test_bracket_unbiased()
    print("\nCOMPONENTS")
    test_planted_edge()
    test_brackets()
    test_context_lag()
    test_feature_parser()
    test_recent_window()
    test_thread_safety()
    test_validators()
    test_plausibility()
    test_overlap()
    test_pooled()
    test_surrogate()
    test_diagnosis()
    test_archive()
    test_parallel()
    test_calibration()
    print("\n" + "=" * 66)
    if FAIL:
        print(f"{len(FAIL)} FAILED:")
        for f in FAIL:
            print("  -", f)
        return 1
    print("ALL PASSED. The searcher cannot enter at a bar it selected on,")
    print("it still finds an edge that is really there, and its state")
    print("survives being written from many threads at once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

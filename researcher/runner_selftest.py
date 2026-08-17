"""Does the evaluator use anything it could not have known at the time?

THE BUG THIS EXISTS TO CATCH, which was live in the committed runner.

The `up_day` / `dn_day` conditions were computed as the day's FULL
return -- last close minus first close of that session. A hypothesis
conditioned on that is not filtered by the morning, it is filtered by
the afternoon. At 10am you do not know how the day ends, so every
up_day cell was quietly reading the answer.

It never produced a false survivor because the search found nothing at
all, which is luck, not protection. The right test is one that fails on
the broken version and passes on the fixed one, and this is it.

  TEST 1  LOOK-AHEAD DETECTOR. Build a tape that is a pure random walk
          with NO structure whatsoever, then evaluate up_day and
          dn_day hypotheses on it. A driftless random walk has no edge
          of any kind, so any systematically positive result is the
          evaluator reading the future. On the old code these come out
          strongly positive; on the fixed code they scatter around
          zero.
  TEST 2  the same for hi_vol / lo_vol, which thresholded on the
          full-sample median.
  TEST 3  OVERLAP INFLATION. Sampling every bar while holding many
          bars means consecutive trades share most of their path, so
          the naive standard error is too small. Confirm the reported z
          on random data does not blow up with hold length.
  TEST 4  the planted-edge check still passes, i.e. the fixes did not
          make the harness blind.

Run: python -m researcher.runner_selftest
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from researcher import runner as R                            # noqa: E402

FAIL = []


def walk(days=600, per_day=78, seed=0, sigma=8.0):
    """A driftless random walk on a 5-minute session grid.

    Nothing in here is predictable. Any strategy that shows a positive
    expectancy is measuring the harness, not the market.
    """
    rng = np.random.default_rng(seed)
    n = days * per_day
    idx = []
    start = pd.Timestamp("2024-01-02 13:30", tz="UTC")
    for dd in range(days):
        base = start + pd.Timedelta(days=dd)
        idx.extend(base + pd.Timedelta(minutes=5 * i) for i in range(per_day))
    idx = pd.DatetimeIndex(idx)
    px = 15000.0 + np.cumsum(rng.standard_normal(n) * sigma)
    d = pd.DataFrame({"close": px}, index=idx)
    d["vol"] = rng.integers(500, 5000, n).astype(float)
    d["n"] = d["vol"]
    d["absret"] = d["close"].diff().abs()
    return d


def cells(d, cond, holds=(300, 900, 3600), dirs=("with",)):
    """Score minute-of-day cells.

    Only ONE direction by default, and that matters. Scoring both
    `with` and `against` gives exact mirror images -- side is +sign and
    -sign of the same series -- so their z values are exact negatives
    and any average over both is identically zero. A first version of
    this test did exactly that and reported a flawless `mean z +0.000`
    for every row, including rows that were riddled with look-ahead.
    A control that cannot fail is not a control.
    """
    out = []
    for hh in range(13, 20):
        for mm in (0, 15, 30, 45):
            for dirn in dirs:
                for hs in holds:
                    h = {"kind": "footprint", "dim": "minute_of_day",
                         "bucket": f"{hh:02d}:{mm:02d}", "metric": "vol",
                         "dir": dirn, "hold_s": hs, "cond": cond}
                    r = R.evaluate(d, h, tv=2.0, cost=0.0, bar_s=300.0)
                    if r:
                        out.append(r)
    return out


def report(name, rs, tol=0.40):
    if not rs:
        print(f"    {name:10s} no cells scored")
        return
    z = np.array([r["z"] for r in rs])
    e = np.array([r["edge"] for r in rs])
    mz, me = float(z.mean()), float(e.mean())
    frac = float((z > 0).mean())
    flag = "ok" if abs(mz) < tol else "LOOK-AHEAD"
    print(f"    {name:10s} cells {len(rs):4d}  mean z {mz:+6.3f}  "
          f"mean edge ${me:+7.4f}  z>0 {frac:5.1%}   {flag}")
    if abs(mz) >= tol:
        FAIL.append(f"{name}: mean z {mz:+.3f} on a driftless random "
                    f"walk -- the evaluator is using information it "
                    f"could not have had")
    return mz


def direct_probe(d, holds=(300, 1800, 3600)):
    """The unambiguous look-ahead test: mean FORWARD return inside each
    conditioning mask, with no trading rule on top.

    A trading rule can hide a leak. `side` is the sign of the last move,
    which is roughly a coin flip, so multiplying a biased forward return
    by it averages the bias away and the leak disappears from the P&L
    while still being there. Looking at the forward return directly
    removes that camouflage: on a driftless walk, every mask that is
    knowable at the time must average zero, and a mask built from the
    day's closing direction cannot.
    """
    idx = d.index
    c = d["close"]
    conds = R._conds(d)
    sd = float(c.diff().std())
    print(f"    (one sigma of a 5-minute move is {sd:.2f} points; "
          f"read the numbers against that)")
    for cond in ("hi_vol", "lo_vol", "up_day", "dn_day"):
        m = conds[cond]
        row = []
        worst = 0.0
        for bars in [int(h / 300) for h in holds]:
            fwd = (c.shift(-bars) - c)
            same = idx.normalize().values == \
                pd.Series(idx).shift(-bars).dt.normalize().values
            f = fwd.where(same).values
            ok = m & np.isfinite(f)
            mu = float(np.mean(f[ok]))
            se = float(np.std(f[ok], ddof=1) / np.sqrt(ok.sum()))
            row.append(f"{bars*5:>3d}m {mu:+6.3f}pt ({mu/se:+5.1f}sd)")
            worst = max(worst, abs(mu / se))
        print(f"    {cond:8s} " + "  ".join(row))
        if worst > 4.0:
            FAIL.append(f"{cond}: forward returns inside this mask are "
                        f"{worst:.1f} sd from zero on a driftless random "
                        f"walk -- the mask knows the future")


def main():
    print("Driftless random walk: 600 sessions x 78 five-minute bars.")
    print("Nothing in it is predictable. Every number below should sit "
          "at zero.\n")

    print("[0] DIRECT PROBE -- mean forward return inside each mask, "
          "no trading rule")
    direct_probe(walk(seed=101))

    print("\n[1] day-direction conditions, one direction only "
          "(the bug that was live)")
    for seed in (0, 1, 2):
        d = walk(seed=seed)
        print(f"  seed {seed}")
        report("none", cells(d, "none"))
        report("up_day", cells(d, "up_day"))
        report("dn_day", cells(d, "dn_day"))

    print("\n[2] volatility conditions")
    d = walk(seed=7)
    report("hi_vol", cells(d, "hi_vol"))
    report("lo_vol", cells(d, "lo_vol"))

    print("\n[3] overlap inflation -- does z grow with hold length?")
    print("    Sampling every bar while holding many means consecutive "
          "trades share most of\n    their path. If the standard error "
          "ignores that, long holds look more significant\n    purely "
          "because they overlap more.")
    print("    But the correction must track how far apart the trades "
          "REALLY are. These are\n    minute-of-day cells: one trade "
          "per session, 78 bars apart, so even a 36-bar\n    hold "
          "overlaps nothing and the overlap factor must stay at 1.00.")
    print("    Under a correct null, mean |z| is ~0.8 at every hold. "
          "Much below that is\n    over-correction -- safe, but it "
          "hides real findings, and a check that only\n    catches "
          "errors in the flattering direction is half a check.")
    d = walk(seed=13)
    for hs in (300, 1800, 3600, 10800):
        rs = cells(d, "none", holds=(hs,))
        z = np.array([r["z"] for r in rs])
        ov = np.array([r["overlap"] for r in rs])
        mabs = float(np.abs(z).mean())
        print(f"    hold {hs:6d}s  cells {len(rs):3d}  overlap "
              f"{ov.mean():4.2f}  mean |z| {mabs:5.3f}  max |z| "
              f"{np.abs(z).max():5.3f}")
        if np.abs(z).max() > 4.5:
            FAIL.append(f"hold {hs}s: max |z| {np.abs(z).max():.2f} on "
                        f"random data -- overlap is inflating "
                        f"significance")
        if mabs < 0.45:
            FAIL.append(f"hold {hs}s: mean |z| {mabs:.3f} is far below "
                        f"the ~0.8 a correct null gives -- the overlap "
                        f"correction is firing on trades that do not "
                        f"overlap, which hides real findings")
        if ov.mean() > 1.05:
            FAIL.append(f"hold {hs}s: overlap factor {ov.mean():.2f} on "
                        f"once-per-session cells that cannot overlap")

    print("\n[3b] and it must still fire when trades DO overlap")
    d = walk(seed=17)
    for hs in (300, 3600, 10800):
        h = {"kind": "footprint", "dim": "day_of_week", "bucket": 2,
             "metric": "vol", "dir": "with", "hold_s": hs, "cond": "none"}
        r = R.evaluate(d, h, tv=2.0, cost=0.0, bar_s=300.0)
        exp = max(int(hs / 300), 1)
        print(f"    every-bar cell, hold {hs:6d}s ({exp:2d} bars): "
              f"overlap {r['overlap']:5.2f}  n {r['n']:5d} -> eff_n "
              f"{r['eff_n']:5d}  z {r['z']:+6.3f}")
        if r["overlap"] < min(exp, 2) * 0.9:
            FAIL.append(f"hold {hs}s on an every-bar cell: overlap "
                        f"{r['overlap']:.2f} but {exp} bars are held -- "
                        f"the correction is not firing where it must")

    print("\n[4] not blind -- planted edge still found")
    d = walk(seed=21)
    ok = R.selftest(d, tv=2.0, cost=0.60, bar_s=300.0)
    print(f"    planted-edge self-test: {'PASS' if ok else 'FAIL'}")
    if not ok:
        FAIL.append("planted-edge self-test failed -- the harness is "
                    "blind and every silence it reports is worthless")

    print("\n" + "=" * 64)
    if FAIL:
        for f in FAIL:
            print("FAIL:", f)
        return 1
    print("PASS -- no look-ahead detected, significance is not inflated "
          "by overlap, and\nthe harness still finds an edge that is "
          "really there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

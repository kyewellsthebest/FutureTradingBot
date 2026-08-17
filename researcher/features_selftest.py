"""Does the feature library discriminate, or does it just find noise?

THE FAILURE MODE THIS EXISTS TO CATCH. `dispersion()` returns the largest
bucket deviation in standard errors. Two things inflate it for free:

  1  it is a MAXIMUM over five buckets, so even pure noise scores ~1.5-2.0
  2  the standard error shrinks as sqrt(n), so on 300k rows a
     meaninglessly small difference becomes many sigmas

Either one alone means "top by dispersion" could be a ranking of pure
luck, and every downstream hypothesis would then be anchored to nothing.
That is the same shape as every error found in this project: a number
that looks like signal because nothing measured what the number does
when there is no signal.

So this test measures the null directly rather than reasoning about it.

  TEST 1  null level. Score PURE NOISE features against real forward
          returns, many times. Report the distribution. Any usable
          threshold has to sit above it.
  TEST 2  detection. Plant a feature that genuinely sorts forward
          returns and confirm it beats the null by a wide margin.
  TEST 3  ordering. Give the library the planted feature mixed into a
          crowd of noise and confirm the plant ranks first.
  TEST 4  no-signal restraint. Score real features against SHUFFLED
          forward returns -- all real structure in x, none in y. The
          top score here is what the library manufactures from nothing.

Run: python -m researcher.features_selftest
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from researcher.features import FeatureLibrary, UNARY, BASE   # noqa: E402,F401

ROOT = os.environ.get("M2_REPO", os.getcwd())
FAIL = []


def load():
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "NQ*_5min.csv"))):
        d = pd.read_csv(p)
        d["ts"] = pd.to_datetime(d["ts"], utc=True)
        d = d.set_index("ts").sort_index()
        d = d[~d.index.duplicated(keep="last")]
        if len(d) < 20000:
            continue
        d["absret"] = d["close"].diff().abs()
        d["n"] = d.get("volume", pd.Series(1.0, index=d.index))
        d["vol"] = d["n"]
        return d
    return None


def fwd(d, k=1):
    y = (d["close"].shift(-k) - d["close"]).values
    same = d.index.normalize().values == \
        pd.Series(d.index).shift(-k).dt.normalize().values
    y = np.where(same, y, np.nan)
    return y


def main():
    d = load()
    if d is None:
        print("no NQ 5-min data -- cannot self-test")
        return 1
    print(f"data: {len(d):,} bars  {d.index[0].date()} -> {d.index[-1].date()}")
    y = fwd(d, 1)
    rng = np.random.default_rng(11)
    n = len(d)

    # ---------------------------------------------------------- TEST 1
    print("\n[1] NULL LEVEL -- pure-noise features vs real returns")
    null = []
    for _ in range(200):
        x = rng.standard_normal(n)
        null.append(FeatureLibrary.dispersion(x, y))
    null = np.array(null)
    q50, q95, q99 = np.percentile(null, [50, 95, 99])
    print(f"    median {q50:.2f}   p95 {q95:.2f}   p99 {q99:.2f}   "
          f"max {null.max():.2f}")
    print("    -> a dispersion score below p99 is indistinguishable "
          "from noise")
    if q50 < 0.3:
        FAIL.append("null median implausibly low -- dispersion may be "
                    "returning 0 for valid input")

    # noise with REAL autocorrelation, the harder null: features are
    # smooth, and a smooth feature has fewer independent observations
    # than its row count suggests.
    smooth = []
    for _ in range(100):
        x = pd.Series(rng.standard_normal(n)).rolling(60).mean().values
        smooth.append(FeatureLibrary.dispersion(x, y))
    smooth = np.array(smooth)
    s95, s99 = np.percentile(smooth, [95, 99])
    print(f"    autocorrelated noise (60-bar smoothed): p95 {s95:.2f}   "
          f"p99 {s99:.2f}   max {smooth.max():.2f}")
    floor = max(q99, s99)
    print(f"    USABLE FLOOR = {floor:.2f}")

    # ---------------------------------------------------------- TEST 2
    print("\n[2] DETECTION -- a feature that genuinely sorts returns")
    # x carries a weak but real relationship to y: 3% of y's own value
    # plus noise. Deliberately weak -- if the library needs a strong
    # plant to see anything it is useless on real data.
    ysafe = np.nan_to_num(y, nan=0.0)
    ysd = np.nanstd(y)
    for frac in (0.01, 0.03, 0.10):
        x = frac * ysafe / ysd + rng.standard_normal(n)
        s = FeatureLibrary.dispersion(x, y)
        mark = "detected" if s > floor else "MISSED"
        print(f"    plant strength {frac:.2f} -> dispersion {s:6.2f}   "
              f"({mark}, floor {floor:.2f})")
        if frac >= 0.03 and s <= floor:
            FAIL.append(f"missed a {frac:.0%} plant -- library is blind")

    # ---------------------------------------------------------- TEST 3
    print("\n[3] ORDERING -- plant hidden in a crowd of noise")
    x = 0.03 * ysafe / ysd + rng.standard_normal(n)
    df = d.copy()
    df["planted"] = x
    for i in range(12):
        df[f"noise{i}"] = rng.standard_normal(n)
    scores = {}
    for c in ["planted"] + [f"noise{i}" for i in range(12)]:
        scores[c] = FeatureLibrary.dispersion(df[c].values, y)
    order = sorted(scores.items(), key=lambda kv: -kv[1])
    for c, s in order[:5]:
        print(f"    {c:10s} {s:6.2f}")
    if order[0][0] != "planted":
        FAIL.append(f"plant ranked #{[c for c, _ in order].index('planted')+1}"
                    f", not #1 -- ordering is unreliable")
    else:
        print("    -> plant ranked #1")

    # ---------------------------------------------------------- TEST 4
    print("\n[4] RESTRAINT -- real features vs SHUFFLED returns")
    yperm = rng.permutation(np.nan_to_num(y, nan=0.0))
    yperm = np.where(np.isfinite(y), yperm, np.nan)
    lib = FeatureLibrary(keep=16)
    kept = lib.grow(d, yperm, np.random.default_rng(3))
    top = sorted(kept, key=lambda kv: -kv[1])[:5]
    for nm, s in top:
        print(f"    {nm:34s} {s:6.2f}")
    manufactured = top[0][1] if top else 0.0
    print(f"    -> best score from a target with NO structure: "
          f"{manufactured:.2f}")
    if manufactured > floor * 1.5:
        FAIL.append(f"library scores {manufactured:.2f} on a shuffled "
                    f"target vs floor {floor:.2f} -- selection is "
                    f"manufacturing structure")

    # ---------------------------------------------------------- TEST 5
    print("\n[5] REAL GROWTH -- three generations on the real target")
    lib = FeatureLibrary(keep=16)
    g = np.random.default_rng(5)
    for gen in range(3):
        kept = lib.grow(d, y, g)
        top = sorted(kept, key=lambda kv: -kv[1])[:6]
        print(f"    gen {gen+1}: {len(kept)} kept, top:")
        for nm, s in top:
            flag = "*" if s > floor else " "
            print(f"       {flag} {nm:36s} {s:6.2f}")
    print(f"    (* = above the {floor:.2f} noise floor; anything "
          f"unmarked is not evidence of anything)")

    # ---------------------------------------------------------- TEST 6
    print("\n[6] THE FLOOR THAT ACTUALLY APPLIES -- full growth on a "
          "target with no alignment")
    print("    Tests 1-4 calibrated the null for a SINGLE feature, but "
          "generation 3 takes a\n    maximum over hundreds of composed "
          "candidates. Comparing a search-max against a\n    "
          "single-draw floor is how a search convinces itself. So: run "
          "the WHOLE three-\n    generation growth against targets that "
          "cannot carry information, and take the\n    max it reaches.")
    print("    The null here is a circular ROLL, not a shuffle. Rolling "
          "keeps the target's own\n    autocorrelation and destroys only "
          "the alignment; shuffling destroys both, which\n    makes the "
          "control easier to beat than reality and flatters the search.")
    maxes = []
    for off in (7919, 23011, 41011, 61001, 90011):
        yr = np.roll(np.nan_to_num(y, nan=0.0), off)
        yr = np.where(np.isfinite(y), yr, np.nan)
        lb = FeatureLibrary(keep=16)
        gr = np.random.default_rng(5)
        best = 0.0
        for _ in range(3):
            k = lb.grow(d, yr, gr)
            best = max(best, max(s for _, s in k) if k else 0.0)
        maxes.append(best)
        print(f"    roll {off:>6d}: gen-3 max {best:5.2f}")
    search_floor = float(np.max(maxes))
    print(f"    -> SEARCH-MAX NULL = {search_floor:.2f}  "
          f"(mean {np.mean(maxes):.2f})")
    lb = FeatureLibrary(keep=16)
    gr = np.random.default_rng(5)
    real_best = 0.0
    for _ in range(3):
        k = lb.grow(d, y, gr)
        real_best = max(real_best, max(s for _, s in k) if k else 0.0)
    print(f"    real target gen-3 max {real_best:5.2f} vs null "
          f"{search_floor:5.2f}  ->  "
          f"{'ABOVE' if real_best > search_floor else 'INSIDE THE NULL'}")
    if real_best <= search_floor:
        print("    Read that plainly: the composed features found on the "
              "REAL target score no\n    better than the same machinery "
              "finds on a target it cannot possibly predict.\n    "
              "Composition depth is buying search, not structure. The "
              "usable threshold for\n    anything downstream is "
              f"{search_floor:.2f}, not {floor:.2f}.")
    USABLE = max(search_floor, floor)
    print(f"\n    THRESHOLD FOR DOWNSTREAM USE: {USABLE:.2f}")

    print("\n" + "=" * 64)
    if FAIL:
        for f in FAIL:
            print("FAIL:", f)
        return 1
    print("PASS -- library detects real structure (tests 1-3) and does "
          "not manufacture it from a shuffled target (test 4).")
    print(f"THRESHOLD FOR DOWNSTREAM USE: {USABLE:.2f}   "
          f"(search-max null {search_floor:.2f}, single-feature null "
          f"{floor:.2f})")
    print(f"Set FEAT_FLOOR={USABLE:.2f} in the runner. Reporting the "
          f"single-feature\nnull as the usable floor -- which an earlier "
          f"version of this line did -- would\nlet every generation-3 "
          f"composition through at the level noise already reaches.")
    if real_best <= search_floor:
        print(f"\nAND NOTE THE RESULT ITSELF: on this tape the real "
              f"target's best composed\nfeature ({real_best:.2f}) is "
              f"below what the same machinery reaches on targets it\n"
              f"cannot predict ({search_floor:.2f}, mean "
              f"{np.mean(maxes):.2f}). Compositional discovery at this\n"
              f"resolution found nothing. The library is working; there "
              f"is nothing here to find.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Is +$246/week at h=400 unusual, or is it one good roll of the dice?

WHAT THIS SETTLES. cadence.py found that at h=400 (~18 hours), trading
the signal at its own pace makes +$246/week at the measured $1.99 round
turn, while ONE shuffled control lost $164. That gap is suggestive and
it is not evidence, for a reason that has already bitten twice today:

    a single shuffle is one draw from the null, not the null.

The same run produced +$123/week at h=50 and +$196 at h=200, both with
an information coefficient indistinguishable from zero -- and at h=200
the shuffled target scored a HIGHER IC than the real one. Positive
numbers are cheap here. What is expensive, and what decides it, is
knowing the whole distribution those numbers come from.

So: refit the same pipeline on N independently permuted targets and
record where the real result falls among them. The p-value is the
share of shuffles that did at least as well.

WHY h=400 SPECIFICALLY, and why not the others. h=400 is the only
horizon where three things agreed: IC +0.0300 against a shuffled
-0.0012, net rising MONOTONICALLY as trading slowed (-$573 -> +$172 ->
+$246), and profitability at the real cost rather than an optimistic
one. The other horizons had none of that and do not deserve the
compute.

THE HONEST CEILING ON WHAT THIS CAN SHOW. There are only 915
independent 400-bar windows in this tape. That is a small sample and no
amount of permutation makes it bigger; it bounds how sure anyone can
be. A pass here means "worth the next test", never "deploy it".
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadence as C                                          # noqa: E402

H = int(os.environ.get("H", "400"))
NPERM = int(os.environ.get("NPERM", "20"))
NTREE = int(os.environ.get("NTREE", "200"))
NFOLD = int(os.environ.get("NFOLD", "4"))


def fit_predict(Xo, yt, h, seed):
    import lightgbm as lgb
    preds = np.full(len(yt), np.nan)
    for tr, te in C.purged_cv(len(yt), NFOLD, h):
        m = lgb.LGBMRegressor(
            n_estimators=NTREE, learning_rate=0.05, num_leaves=31,
            min_child_samples=500, subsample=0.7, subsample_freq=1,
            colsample_bytree=0.5, reg_lambda=10.0, verbose=-1,
            n_jobs=4, random_state=seed)
        m.fit(Xo[tr], yt[tr])
        preds[te] = m.predict(Xo[te])
    return preds


def main():
    print(__doc__, flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    X, names, cls, ts = C.load()
    n_bars = len(X)
    weeks = n_bars * C.BAR_MIN / (60 * 24 * 7)
    bars_wk = n_bars / weeks
    yh, y1 = C.targets(cls, H)
    ok = np.isfinite(yh) & np.isfinite(y1)
    Xo, yo, y1o = X[ok], yh[ok], y1[ok]
    eff_n = len(yo) / H
    print(f"h={H}, {len(yo):,} rows, ~{eff_n:.0f} INDEPENDENT windows, "
          f"se(IC) ~ {1/math.sqrt(eff_n):.4f}", flush=True)

    def evaluate(preds):
        v = np.isfinite(preds)
        r = C.execute(preds[v], y1o[v], H, C.COST_MEASURED)
        return (float(np.corrcoef(preds[v], yo[v])[0, 1]),
                r["net_per_bar"] * bars_wk)

    real_ic, real_net = evaluate(fit_predict(Xo, yo, H, 0))
    print(f"\nREAL   IC {real_ic:+.4f}   net ${real_net:+,.0f}/wk\n",
          flush=True)

    rng = np.random.default_rng(2029)
    nulls = []
    for i in range(NPERM):
        ic, net = evaluate(fit_predict(Xo, rng.permutation(yo), H, i + 1))
        nulls.append({"ic": round(ic, 4), "net": round(net, 1)})
        ge = sum(1 for x in nulls if x["net"] >= real_net)
        print(f"  perm {i+1:>3}/{NPERM}  IC {ic:+.4f}  net ${net:+9,.0f}/wk"
              f"   (>= real so far: {ge}/{len(nulls)})", flush=True)

    nets = np.array([x["net"] for x in nulls])
    ics = np.array([x["ic"] for x in nulls])
    ge = int((nets >= real_net).sum())
    p = (ge + 1) / (NPERM + 1)          # add-one: never report p = 0
    out = {"h": H, "nperm": NPERM, "eff_n": round(eff_n),
           "real_ic": round(real_ic, 4), "real_net_per_week": round(real_net, 1),
           "null_net_mean": round(float(nets.mean()), 1),
           "null_net_sd": round(float(nets.std(ddof=1)), 1),
           "null_net_max": round(float(nets.max()), 1),
           "null_ic_sd": round(float(ics.std(ddof=1)), 4),
           "n_null_ge_real": ge, "p_value": round(p, 4)}
    print("\n" + "=" * 72, flush=True)
    print(f"  real          ${real_net:+,.0f}/wk   IC {real_ic:+.4f}")
    print(f"  null mean     ${nets.mean():+,.0f}/wk   sd ${nets.std(ddof=1):,.0f}")
    print(f"  null best     ${nets.max():+,.0f}/wk")
    print(f"  IC sd across shuffles  {ics.std(ddof=1):.4f}  "
          f"(the empirical se -- compare to the formula's "
          f"{1/math.sqrt(eff_n):.4f})")
    print(f"\n  {ge} of {NPERM} shuffles matched or beat the real result")
    print(f"  p = {p:.3f}")
    verdict = ("SURVIVES this test -- worth the next one, NOT a deployable "
               "edge" if p <= 0.05 else
               "DOES NOT SURVIVE -- the result sits inside what shuffling "
               "produces")
    print(f"\n  {verdict}", flush=True)
    out["verdict"] = verdict
    p_out = os.path.join(C.ROOT, "research", f"PERM_H{H}.json")
    json.dump(out, open(p_out, "w"), indent=1)
    print(f"\nwrote {p_out}  ({time.time()-t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

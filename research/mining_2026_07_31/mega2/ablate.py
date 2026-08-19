"""Which feature type carries the h=400 result -- or is there nothing to carry?

THE DISCREPANCY THIS SETTLES. NQ at 18 hours on TICK data scored an IC
of +0.0282, three empirical standard errors from zero, and +$228/week.
The same market at 24 hours on FIVE-MINUTE data scored 0.86 se and
+$80/week. Near-identical horizon, largely the same idea, very
different answer.

Two explanations, pointing opposite ways:

  1  ORDER FLOW IS THE INGREDIENT. The tick matrix has 40 f_ features
     -- aggressor side and trade size -- which simply do not exist in
     five-minute closes. If they are doing the work, the lane is alive
     and it lives wherever tick data can be had.

  2  THE TICK RESULT WAS LUCK. p = 0.048 was the FLOOR of a
     20-permutation test, on 915 independent windows. Small samples
     produce three-sigma results by chance more often than the sigma
     count suggests.

Removing the flow features separates them. Collapse to ~0.003 and flow
is the ingredient. Holding near 0.028 and flow was never the story --
in which case the five-minute null becomes the better-powered
measurement of the two, and the honest reading is noise.

Every subset is run, not just the one that answers the question,
because "which type matters" is worth knowing either way and costs the
same fits:

    all          266 features, the original
    no_flow      drop f_        -- the decisive comparison
    flow_only    f_ alone
    price_only   p_ alone       -- 26 billion configs say this is dead
    cross_only   i_ + m_        -- other markets, no NQ flow

A SHUFFLED control runs alongside `all` so the scale of a null IC on
this exact sample is visible rather than assumed.
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
NTREE = int(os.environ.get("NTREE", "200"))
NFOLD = int(os.environ.get("NFOLD", "4"))

SETS = {
    "all":        lambda n: True,
    "no_flow":    lambda n: not n.startswith("f_"),
    "flow_only":  lambda n: n.startswith("f_"),
    "price_only": lambda n: n.startswith("p_"),
    "cross_only": lambda n: n.startswith(("i_", "m_")),
}


def main():
    print(__doc__, flush=True)
    print("=" * 74, flush=True)
    t0 = time.time()
    X, names, cls, ts = C.load()
    n_bars = len(X)
    weeks = n_bars * C.BAR_MIN / (60 * 24 * 7)
    yh, y1 = C.targets(cls, H)
    ok = np.isfinite(yh) & np.isfinite(y1)
    Xo, yo, y1o = X[ok], yh[ok], y1[ok]
    eff = len(yo) / H
    se = 1.0 / math.sqrt(eff)
    print(f"h={H}, {len(yo):,} rows, {eff:.0f} independent windows, "
          f"formula se {se:.4f}\n", flush=True)

    import lightgbm as lgb

    def run(cols, target, seed):
        Xs = Xo[:, cols]
        pr = np.full(len(target), np.nan)
        for tr, te in C.purged_cv(len(target), NFOLD, H):
            m = lgb.LGBMRegressor(
                n_estimators=NTREE, learning_rate=0.05, num_leaves=31,
                min_child_samples=500, subsample=0.7, subsample_freq=1,
                colsample_bytree=0.5, reg_lambda=10.0, verbose=-1,
                n_jobs=4, random_state=seed)
            m.fit(Xs[tr], target[tr])
            pr[te] = m.predict(Xs[te])
        v = np.isfinite(pr)
        ic = float(np.corrcoef(pr[v], target[v])[0, 1])
        r = C.execute(pr[v], y1o[v], H, C.COST_MEASURED)
        bars_wk = n_bars / weeks
        return ic, r["net_per_bar"] * bars_wk

    rows = []
    print(f"{'feature set':>12} {'n':>5} {'IC':>9} {'net $/wk':>10}")
    for name, keep in SETS.items():
        cols = [i for i, n in enumerate(names) if keep(str(n))]
        if not cols:
            continue
        ic, net = run(cols, yo, 0)
        rows.append({"set": name, "n_features": len(cols),
                     "ic": round(ic, 4), "net_per_week": round(net, 1)})
        print(f"{name:>12} {len(cols):>5} {ic:>+9.4f} {net:>10,.0f}"
              f"   ({time.time()-t0:.0f}s)", flush=True)

    rng = np.random.default_rng(31)
    ic_s, net_s = run(list(range(len(names))), rng.permutation(yo), 1)
    rows.append({"set": "SHUFFLED(all)", "n_features": len(names),
                 "ic": round(ic_s, 4), "net_per_week": round(net_s, 1)})
    print(f"{'SHUFFLED':>12} {len(names):>5} {ic_s:>+9.4f} {net_s:>10,.0f}")

    a = [r for r in rows if r["set"] == "all"][0]
    nf = [r for r in rows if r["set"] == "no_flow"][0]
    print("\n" + "=" * 74)
    print("VERDICT")
    print(f"  all      IC {a['ic']:+.4f}   ${a['net_per_week']:,.0f}/wk")
    print(f"  no_flow  IC {nf['ic']:+.4f}   ${nf['net_per_week']:,.0f}/wk")
    drop = (a["ic"] - nf["ic"]) / a["ic"] if a["ic"] else 0.0
    if nf["ic"] < 0.35 * a["ic"]:
        print(f"\n  ORDER FLOW IS THE INGREDIENT -- removing it costs "
              f"{100*drop:.0f}% of the IC.")
        print("  The lane is alive, and it lives only where tick data "
              "exists.")
    else:
        print(f"\n  FLOW IS NOT THE STORY -- removing it costs only "
              f"{100*drop:.0f}% of the IC.")
        print("  Then the tick result and the far better-powered "
              "five-minute null")
        print("  disagree with no mechanism to explain it, and noise is "
              "the honest reading.")
    p = os.path.join(C.ROOT, "research", f"ABLATE_H{H}.json")
    json.dump({"h": H, "eff_n": int(eff), "rows": rows}, open(p, "w"),
              indent=1)
    print(f"\nwrote {p}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

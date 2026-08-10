"""Search with the toll switched off. How big is the edge before costs?

The ablation ranked everything on net dollars and every row lost. That answers
"can we afford it" but it buries "is it there", and those are different
questions with different fixes. If the gross edge is large and cost eats it,
the job is execution and commissions. If the gross edge is small everywhere,
no amount of cheap execution saves it and the job is still the search.

So this ranks on GROSS and reports, for every configuration, the one number
that translates straight back:

    gross $ per round turn  ==  the cost we would have to pay for it to work

We pay $1.99. Anything whose gross-per-round-turn sits under that is not a
strategy, it is a donation. Anything above it is a strategy whose only problem
is a bill, and bills can be negotiated.

TWO THINGS THIS SWEEPS THAT THE ABLATION DID NOT:

  HORIZON, much wider -- 1 to 500 bars, half a minute to twenty hours. The
  ablation stopped at 20 bars and the trend was still improving at the edge of
  the table, which is exactly where you should not stop looking.

  SELECTIVITY. The ablation held a position every single bar. Real trading does
  not: you wait for the setups you like. So each model's predictions are
  filtered to the most confident top q%, and trades are taken
  NON-OVERLAPPING -- one position at a time, the way one account actually
  works. That turns the output into the user's own units: trades per week and
  dollars per trade.

WHY SELECTIVITY NEEDS ITS OWN CONTROL, and this is the trap. Taking the top
0.1% of anything is a selection procedure, and selection manufactures edge out
of noise as reliably as it finds it in signal -- the best 300 of 293,000 coin
flips look spectacular. So every threshold is run identically on the SHUFFLED
model, and the shuffled column is printed next to the real one at the SAME
threshold. Read the pair, never the real number alone.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import fusion_ceiling as FC  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "GROSS.md"))
HZ = [int(x) for x in os.environ.get("HZ", "1,2,5,10,20,50,100,200,500")
      .split(",")]
QS = [float(x) for x in os.environ.get("QS", "0.5,0.2,0.1,0.05,0.02,0.01,0.002")
      .split(",")]
COST_RT = 1.99
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def trades(pred, y, thr, h):
    """Non-overlapping trades, chronological, one position at a time.

    Overlapping samples would let a single good stretch of tape be counted
    fifty times and would make trades-per-week a fiction. One account can hold
    one position, so the count has to respect that or the dollars do not mean
    anything.
    """
    take = np.flatnonzero(np.isfinite(pred) & (np.abs(pred) >= thr))
    if len(take) == 0:
        return np.array([], dtype=np.int64)
    out = []
    last = -(10 ** 9)
    for i in take:
        if i >= last + h:
            out.append(i)
            last = i
    return np.array(out, dtype=np.int64)


def sweep(pred, y, h, days):
    """Every selectivity level for one model, as real trades."""
    v = np.isfinite(pred) & np.isfinite(y)
    p = np.where(v, pred, np.nan)
    a = np.abs(p[v])
    rows = []
    for q in QS:
        thr = float(np.quantile(a, 1 - q))
        idx = trades(p, y, thr, h)
        if len(idx) < 50:
            continue
        g = float(np.mean(np.sign(p[idx]) * y[idx]))
        n = len(idx)
        rows.append(dict(q=q, n=n, tpw=n / days * 5, gross=g,
                         wk=g * n / days * 5, net_wk=(g - COST_RT) * n / days * 5))
    return rows


def main():
    t0 = time.time()
    import lightgbm as lgb
    X, names, Y, T, cov = FC.assemble(False)
    nm = np.array(names)
    days = len(np.unique(T // fuse.DAY_NS))
    bpd = len(T) / max(days, 1)
    print(f"{X.shape[0]:,} bars, {days} days, {bpd:.0f} bars/day", flush=True)

    # widen the outcome set beyond what fusion_ceiling built
    c = None
    res = {}
    rng = np.random.default_rng(7)
    for lab, pres in FC.SETS:
        cols = np.flatnonzero([n.startswith(pres) for n in nm])
        for h in HZ:
            y = Y.get(h)
            if y is None:
                continue
            for ctl in ("real", "shuffled"):
                ok = np.isfinite(y)
                Xo = X[ok][:, cols]
                yo = y[ok]
                if ctl == "shuffled":
                    yo = rng.permutation(yo)
                preds = np.full(len(yo), np.nan)
                for tr, te in FC.purged_cv(len(yo), FC.NFOLD, h):
                    m = lgb.LGBMRegressor(
                        n_estimators=FC.NTREE, learning_rate=0.05,
                        num_leaves=31, min_child_samples=500, subsample=0.7,
                        subsample_freq=1, colsample_bytree=0.5,
                        reg_lambda=10.0, verbose=-1, n_jobs=4)
                    m.fit(Xo[tr], yo[tr])
                    preds[te] = m.predict(Xo[te])
                res[(lab, h, ctl)] = sweep(preds, yo, h, days)
                best = max((r["gross"] for r in res[(lab, h, ctl)]), default=0)
                print(f"  {lab:32s} h={h:<4d} {ctl:9s} best gross/trade="
                      f"${best:+.2f}  ({time.time()-t0:.0f}s)", flush=True)
                json.dump({f"{a}|{b}|{c2}": v for (a, b, c2), v in res.items()},
                          open(os.path.join(FC.FCACHE, "gross_partial.json"),
                               "w"))

    log("# The search with the toll switched off")
    log()
    log("Every row of the previous study lost money, which answers *can we "
        "afford it* and buries *is it there*. Those have different fixes: a "
        "big gross edge eaten by costs is an execution problem, a small gross "
        "edge everywhere is still a search problem. So this ranks on gross and "
        "reports the number that converts straight back —")
    log()
    log("> **gross $ per round turn = the cost we would have to pay for this "
        "to work.** We pay $1.99.")
    log()
    log(f"Horizons run from 1 to {max(HZ)} bars (~{60/bpd*24*60:.0f} seconds to "
        f"~{max(HZ)/bpd*24:.0f} hours). Positions are **non-overlapping** — one "
        f"at a time, the way one account works — and filtered to the most "
        f"confident top q% of predictions, so the output is in trades per week "
        f"and dollars per trade.")
    log()
    log("**The shuffled column is not optional here.** Taking the best 0.2% of "
        "293,000 predictions is a selection procedure, and selection invents "
        "edge from noise exactly as reliably as it finds it in signal. Every "
        "threshold is run identically on a model trained against scrambled "
        "outcomes. Read the pair; the real number alone means nothing.")
    log()

    # ---- headline: best gross per round turn anywhere in the space ----------
    flat = []
    for (lab, h, ctl), rows in res.items():
        if ctl != "real":
            continue
        for r in rows:
            sh = res.get((lab, h, "shuffled"), [])
            m = [s for s in sh if s["q"] == r["q"]]
            flat.append((r["gross"], lab, h, r, m[0] if m else None))
    flat.sort(key=lambda z: -z[0])

    log("## The best gross-per-trade anywhere in the space")
    log()
    log("| data | horizon | selectivity | trades/week | **gross $/trade** | "
        "same cut, shuffled | net $/week at $1.99 |")
    log("|---|---|---|---|---|---|---|")
    for g, lab, h, r, s in flat[:20]:
        sg = f"${s['gross']:+.2f}" if s else "—"
        log(f"| {lab} | {h} bars | top {r['q']*100:g}% | {r['tpw']:.0f} | "
            f"**${g:+.2f}** | {sg} | ${r['net_wk']:+,.0f} |")
    log()

    # ---- the horizon curve, which is the actual finding ---------------------
    log("## Gross per trade against horizon")
    log()
    log("At a fixed, undemanding selectivity — the top 10% of signals — so the "
        "trend is not confounded by how hard each row is cherry-picking.")
    log()
    log("| horizon | " + " | ".join(l for l, _ in FC.SETS) + " |")
    log("|---" * (1 + len(FC.SETS)) + "|")
    for h in HZ:
        cells = []
        for lab, _ in FC.SETS:
            rows = [r for r in res.get((lab, h, "real"), []) if r["q"] == 0.1]
            cells.append(f"${rows[0]['gross']:+.2f}" if rows else "—")
        mins = h / bpd * 24 * 60
        lab_h = f"{mins:.0f} min" if mins < 90 else f"{mins/60:.1f} h"
        log(f"| {h} bars ({lab_h}) | " + " | ".join(cells) + " |")
    log()
    log(f"Read down a column. If gross-per-trade keeps climbing with horizon "
        f"and only crosses ${COST_RT:.2f} out at the long end, then the edge is "
        f"real but slow, and high frequency is the thing making it unaffordable "
        f"rather than the thing making it work.")
    log()
    log(f"_Ran in {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

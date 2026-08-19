"""Does the long-horizon signal survive being traded at its OWN cadence?

SUCCESS CRITERION, fixed before this runs so it cannot move afterwards:

    A horizon PASSES if, holding the position for h bars instead of
    re-deciding every bar, net P&L per week is positive at the MEASURED
    cost of $1.99 a round turn, AND the same pipeline on a SHUFFLED
    target at the same cadence is not.

    Anything that only works at $0.60 is reported but does NOT pass.

WHY THIS EXISTS. `fusion_ceiling.py` measured a real-minus-shuffled IC
of about +0.048 at h=400 (~18 hours of tape) and still reported a loss.
The reason is in its own `score()`: the position is

    pos = clip(pred / std(pred), -1, 1)

recomputed EVERY BAR. A bar is ~2.7 minutes, so a model predicting an
18-hour move re-decides its position roughly 400 times inside the
window it is predicting. Turnover -- and therefore cost -- is that of a
400x faster strategy, while the edge being harvested is the slow one.
It paid the toll hundreds of times to collect one move's worth of edge.

That is not a finding about the signal. It is a finding about the
execution wrapped around it, and nobody has ever run the other way.

WHAT THIS CHANGES AND NOTHING ELSE. Same cached features, same purged
CV, same LightGBM, same predictions. The ONLY difference is when the
position is allowed to change:

    every_bar   pos updates each bar          (the original)
    hold_h      pos updates every h bars      (the signal's own cadence)
    hold_h/2    a middle setting, to show the trend is monotone rather
                than a single lucky point

Holding the predictions fixed and varying only the execution is what
makes this a controlled comparison rather than a new model.

THE CONTROLS, both of them:

  1  SHUFFLED TARGET at every cadence. Slowing turnover reduces cost
     for a random signal too, so "net improved when I traded less" is
     not evidence by itself. What has to survive is real BEATING
     shuffled at the same cadence. If shuffled also turns positive,
     the cadence change is just charging less for noise.

  2  THE COST IS THE MEASURED ONE. $1.99 a round turn, from actual
     fills. $0.60 is shown alongside only to make the gap legible; it
     is not the number anything is judged on.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import math
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", "..", ".."))
FCACHE = os.path.join(ROOT, "data", "tick", "fusecache")

HZ = [int(x) for x in os.environ.get("HZ", "50,100,200,400").split(",")]
NFOLD = int(os.environ.get("NFOLD", "4"))
NTREE = int(os.environ.get("NTREE", "200"))
USD_PT = 2.00                       # MNQ
COST_MEASURED = 1.99                # from the user's own fills
COST_OPTIMISTIC = 0.60              # what the searcher's model assumes
WARM = 250
BAR_MIN = 2.7                       # minutes per K=500 volume bar


def log(s=""):
    print(s, flush=True)


# ------------------------------------------------------------------ data
def load():
    """The cached matrices, in date order. No rebuild, no tick parsing."""
    Xs, cls, tss = [], [], []
    names = None
    for p in sorted(glob.glob(os.path.join(FCACHE, "*_K500_L250_real.npz"))):
        z = np.load(p, allow_pickle=False)
        nm = list(z["names"])
        if names is None:
            names = nm
        assert nm == names, f"{p} feature set differs"
        Xs.append(z["X"][WARM:])
        cls.append(z["c"][WARM:].astype(np.float64))
        tss.append(z["ts"][WARM:])
        log(f"  {os.path.basename(p)[:20]:22} {len(z['X'])-WARM:>7,} bars")
    order = np.argsort([t[0] for t in tss])
    Xs = [Xs[i] for i in order]
    cls = [cls[i] for i in order]
    tss = [tss[i] for i in order]
    return np.vstack(Xs), names, cls, np.concatenate(tss)


def targets(cls, h):
    """Forward h-bar move and the one-bar move, both in dollars.

    Built PER CONTRACT and then concatenated, so no target ever spans
    the seam between two quarters -- that would be a price gap of
    hundreds of points read as a signal.
    """
    yh, y1 = [], []
    for c in cls:
        a = np.full(len(c), np.nan)
        a[:-h] = (c[h:] - c[:-h]) * USD_PT
        b = np.full(len(c), np.nan)
        b[:-1] = (c[1:] - c[:-1]) * USD_PT
        yh.append(a)
        y1.append(b)
    return np.concatenate(yh), np.concatenate(y1)


def purged_cv(n, nfold, horizon):
    """Folds with an h-bar gap either side of the test block, so a
    training bar can never overlap the window of a test bar."""
    edges = np.linspace(0, n, nfold + 2).astype(int)
    for i in range(1, nfold + 1):
        a, b = edges[i], edges[i + 1]
        tr = np.concatenate([np.arange(0, max(0, a - horizon)),
                             np.arange(min(n, b + horizon), n)])
        yield tr, np.arange(a, b)


# ------------------------------------------------------- the one variable
def execute(pred, y1, hold, cost_rt, demean=True):
    """Turn a prediction series into a traded position and price it.

    `hold` is the ONLY thing that varies across the rows of the table.
    hold=1 reproduces fusion_ceiling's original accounting.

    DEMEAN, AND WHY IT IS NOT OPTIONAL. The first run of this file
    reported that slowing turnover took net from -$381 to +$178 a week
    -- and that the SHUFFLED control did the same thing, +$157. The
    mechanism: shuffling permutes the target but preserves its MEAN,
    and NQ rose across these two years. So the model learns to predict
    that positive average, sits persistently long, and collects the
    market's drift. At 44 round turns a day the cost buried it; hold
    the position and the drift surfaces and looks like skill.

    That is beta, not timing. Removing the mean of the signal leaves
    only the part that says WHEN to be long rather than THAT one should
    be long. The un-demeaned version is still computed, because a
    long-biased strategy is allowed -- it just has to beat buying and
    holding, which is what `baseline_long` below measures.
    """
    s = pred / (np.nanstd(pred) + 1e-12)
    if demean:
        s = s - np.nanmean(s)
    want = np.clip(s, -1.0, 1.0)
    if hold > 1:
        # Re-decide only every `hold` bars; carry the decision between.
        idx = np.arange(len(want))
        pos = want[(idx // hold) * hold]
    else:
        pos = want
    gross = float(np.nanmean(pos * y1))
    turn = float(np.mean(np.abs(np.diff(pos, prepend=0.0))))
    # A unit of turnover is half a round trip, so cost is turn * RT/2.
    net = gross - turn * cost_rt / 2.0
    return {"gross_per_bar": gross, "turnover_per_bar": turn,
            "net_per_bar": net, "avg_pos": float(np.nanmean(pos))}


def baseline_long(pred, y1, hold, cost_rt):
    """THE OTHER CONTROL: hold a constant long of the same average size.

    A strategy that is net long in a rising market earns money without
    knowing anything. To claim timing skill it has to beat simply
    holding that same average position and never trading. Turnover here
    is one entry across the whole sample, so cost is ~0 -- which is
    exactly why this is a hard baseline to beat and an honest one.
    """
    s = pred / (np.nanstd(pred) + 1e-12)
    avg = float(np.nanmean(np.clip(s, -1.0, 1.0)))
    return {"gross_per_bar": avg * float(np.nanmean(y1)),
            "turnover_per_bar": 0.0,
            "net_per_bar": avg * float(np.nanmean(y1)),
            "avg_pos": avg}


def main():
    log(__doc__)
    log("=" * 74)
    t0 = time.time()
    log("loading cached matrices...")
    X, names, cls, ts = load()
    n_bars = len(X)
    span_min = n_bars * BAR_MIN
    weeks = span_min / (60 * 24 * 7)
    log(f"  {n_bars:,} bars x {len(names)} features, "
        f"~{weeks:.0f} weeks of tape")
    log("")

    import lightgbm as lgb
    rng = np.random.default_rng(11)
    out = []
    preds_n = {}

    for h in HZ:
        hours = h * BAR_MIN / 60.0
        log(f"--- h = {h} bars (~{hours:.1f} hours) " + "-" * 30)
        yh, y1 = targets(cls, h)
        preds_n[h] = np.flatnonzero(
            np.isfinite(yh) & np.isfinite(y1))
        ok = np.isfinite(yh) & np.isfinite(y1)
        Xo, yo, y1o = X[ok], yh[ok], y1[ok]

        for shuffled in (False, True):
            tag = "SHUFFLED" if shuffled else "real"
            yt = rng.permutation(yo) if shuffled else yo
            preds = np.full(len(yt), np.nan)
            for tr, te in purged_cv(len(yt), NFOLD, h):
                m = lgb.LGBMRegressor(
                    n_estimators=NTREE, learning_rate=0.05, num_leaves=31,
                    min_child_samples=500, subsample=0.7, subsample_freq=1,
                    colsample_bytree=0.5, reg_lambda=10.0, verbose=-1,
                    n_jobs=4)
                m.fit(Xo[tr], yt[tr])
                preds[te] = m.predict(Xo[te])
            v = np.isfinite(preds)
            ic = float(np.corrcoef(preds[v], yt[v])[0, 1])
            log(f"  {tag:8}  IC {ic:+.4f}")

            bars_wk = n_bars / weeks
            bl = baseline_long(preds[v], y1o[v], h, COST_MEASURED)
            log(f"      {'BE-LONG':12} {0.0:>7.1f} RT/day  "
                f"gross ${bl['gross_per_bar']*bars_wk:>9,.0f}/wk  "
                f"net ${bl['net_per_bar']*bars_wk:>9,.0f}/wk   "
                f"<- do-nothing baseline (avg pos {bl['avg_pos']:+.2f})")
            out.append({"h": h, "target": tag, "policy": "baseline_long",
                        "net_per_week_at_1.99": round(
                            bl["net_per_bar"] * bars_wk, 2)})

            for label, hold in (("every_bar", 1),
                                (f"hold_{h//2}", max(1, h // 2)),
                                (f"hold_{h}", h)):
                r = execute(preds[v], y1o[v], hold, COST_MEASURED)
                per_week = r["net_per_bar"] * bars_wk
                gross_wk = r["gross_per_bar"] * bars_wk
                rt_day = r["turnover_per_bar"] / 2.0 * (60 * 24 / BAR_MIN)
                cheap = execute(preds[v], y1o[v], hold, COST_OPTIMISTIC)
                row = {"h": h, "hours": round(hours, 1), "target": tag,
                       "ic": round(ic, 4), "policy": label,
                       "round_turns_per_day": round(rt_day, 1),
                       "gross_per_week": round(gross_wk, 2),
                       "net_per_week_at_1.99": round(per_week, 2),
                       "net_per_week_at_0.60": round(
                           cheap["net_per_bar"] * bars_wk, 2)}
                out.append(row)
                log(f"      {label:12} {rt_day:>7.1f} RT/day  "
                    f"gross ${gross_wk:>9,.0f}/wk  "
                    f"net ${per_week:>9,.0f}/wk  "
                    f"(at $0.60: ${row['net_per_week_at_0.60']:>9,.0f})")
        log("")

    p = os.path.join(ROOT, "research", "CADENCE.json")
    json.dump({"cost_measured": COST_MEASURED, "weeks": round(weeks, 1),
               "bars": n_bars, "rows": out}, open(p, "w"), indent=1)
    log(f"wrote {p}   ({time.time()-t0:.0f}s)")

    # ---- the verdict, against the criterion fixed in the header
    log("")
    log("VERDICT")
    passed = []
    for h in HZ:
        real = [r for r in out if r["h"] == h and r["target"] == "real"
                and r["policy"] == f"hold_{h}"]
        shuf = [r for r in out if r["h"] == h and r["target"] == "SHUFFLED"
                and r["policy"] == f"hold_{h}"]
        if not real or not shuf:
            continue
        r, s = real[0], shuf[0]
        bl = [x for x in out if x["h"] == h and x["target"] == "real"
              and x["policy"] == "baseline_long"]
        blv = bl[0]["net_per_week_at_1.99"] if bl else 0.0
        # Three hurdles, not one: positive, better than the same
        # pipeline on noise, and better than doing nothing at all.
        # FOURTH HURDLE, and the one whose absence made this table lie.
        # The first run passed h=50 (IC +0.0030) and h=200 (IC +0.0010,
        # BELOW its own shuffled control at +0.0051) purely on P&L. A
        # position sized off a forecast worth nothing still produces a
        # P&L, and with few independent windows that P&L can be large.
        #
        # The se of an IC is 1/sqrt(effective n), and effective n is
        # NOT the row count -- h-bar overlapping targets mean only
        # n/h independent windows. At h=200 that is 1,831 rows of
        # information dressed as 366,189, and the naive se (0.0017) is
        # seven times too small. Overlap deflation is the exact error
        # this project fixed elsewhere and I reintroduced here.
        eff_n = max(1.0, len(preds_n.get(h, [1])) / h)
        se_ic = 1.0 / math.sqrt(eff_n)
        ic_ok = abs(r.get("ic", 0.0)) >= 2.0 * se_ic
        ok = (r["net_per_week_at_1.99"] > 0
              and r["net_per_week_at_1.99"] > s["net_per_week_at_1.99"]
              and r["net_per_week_at_1.99"] > blv
              and ic_ok)
        log(f"  h={h:>4} (~{r['hours']:>4.1f}h)  real "
            f"${r['net_per_week_at_1.99']:>9,.0f}/wk   shuffled "
            f"${s['net_per_week_at_1.99']:>9,.0f}/wk   "
            f"be-long ${blv:>9,.0f}/wk   "
            f"IC {r.get('ic',0):+.4f} vs 2se {2*se_ic:.4f}   "
            f"{'PASS' if ok else 'fail'}")
        if ok:
            passed.append(h)
    log("")
    log(f"  {len(passed)} of {len(HZ)} horizons pass at the measured "
        f"$1.99 round turn: {passed or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

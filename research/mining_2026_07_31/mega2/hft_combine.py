"""Do the order-flow features COMBINE? The last free shot at HFT.

Every number in this project is a single feature measured alone. At
60-second bars three of them sit at almost exactly the same strength --
range, trade intensity, and return, each around 0.15pt of edge, each at
3.1-3.5x the measured noise floor with sign-stable train/holdout. They
are different measurements of the market, so they may carry partly
independent information.

    if fully independent:  sqrt(3) x 0.15 = 0.26 pt = $0.52/trade
    cost at the user's $0.60 all-in:                  $0.60/trade
    -> 87% of breakeven, from features already measured

That is the entire hypothesis. It has never been tested because every
run so far scored one column at a time.

WHAT PAYS, stated before the run. At 60-second bars sigma is 11.47 pt,
so on one MNQ at $2/point:

    edge($) = IC x 11.47 x 2
    breakeven at $0.60/trade  ->  IC > 0.026
    $150/day at 200 trades    ->  IC > 0.059

Best single feature measured: intensity, holdout IC 0.0132. So breakeven
needs 2.0x the best single feature and the income target needs 4.5x.

DISCIPLINE, because a combination test is the easiest thing in the world
to fool yourself with:

  EXACTLY the nine features already measured. No new ones invented for
  this run -- adding features after seeing which horizon looked good is
  fishing.
  PURGED BY CONTRACT. Train on five quarters, hold out three. Different
  contracts are different periods, so there is no leakage across the
  boundary and no overlap to correct.
  RIDGE FIRST. A linear model with nine inputs cannot overfit 300k rows
  in any interesting way. LightGBM is reported alongside, and if the
  tree beats ridge by a lot on TRAIN and not on HOLDOUT, that gap is the
  overfit and it is visible rather than hidden.
  SHUFFLED CONTROL. Same pipeline, permuted target. Whatever it reports
  is what this machinery manufactures from nothing.

Output: research/HFT_COMBINE.md
"""
import gc
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
OUT = os.path.join(ROOT, "research", "HFT_COMBINE.md")
NS = 1_000_000_000
BAR = 60
BIG = 10
TV = 2.0
COST = 0.60
FEATS = ["delta", "dratio", "cumdelta", "bigratio", "szskew",
         "intensity", "tickrun", "ret", "rng"]
FWD = [1, 2, 5]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def ic(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 1000:
        return np.nan
    a = pd.Series(x[ok]).rank().values
    b = pd.Series(y[ok]).rank().values
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else np.nan


def build(path):
    d = pd.read_parquet(path, columns=["ts", "price", "size"])
    d = d.sort_values("ts", kind="stable")
    ts = d.ts.values
    px = d.price.values.astype(np.float64)
    sz = d["size"].values.astype(np.float64)
    del d
    idx = pd.to_datetime(ts)
    keep = np.asarray((idx.hour * 60 + idx.minute >= 13 * 60 + 30)
                      & (idx.hour < 20))
    if keep.sum() < 100_000:
        return None
    ts, px, sz = ts[keep], px[keep], sz[keep]
    del idx, keep
    gc.collect()
    dp = np.diff(px, prepend=px[0])
    sg = np.sign(dp)
    filled = pd.Series(np.where(sg != 0, sg, np.nan)).ffill()
    filled = filled.fillna(1.0).values
    b = ts // (BAR * NS)
    g = pd.DataFrame(dict(b=b, px=px, sz=sz, sv=filled * sz,
                          big=np.where(sz >= BIG, sz, 0.0),
                          up=(filled > 0).astype(float),
                          day=ts // (86400 * NS), ts=ts))
    a = g.groupby("b").agg(high=("px", "max"), low=("px", "min"),
                           close=("px", "last"), vol=("sz", "sum"),
                           delta=("sv", "sum"), bigv=("big", "sum"),
                           nup=("up", "sum"), ntr=("px", "size"),
                           day=("day", "first"), t0=("ts", "first"),
                           t1=("ts", "last"))
    a = a[a.vol > 0]
    hi = g.px.values == g.groupby("b").px.transform("max").values
    lo = g.px.values == g.groupby("b").px.transform("min").values
    a["hisz"] = g[hi].groupby("b").sz.sum().reindex(a.index).fillna(0)
    a["losz"] = g[lo].groupby("b").sz.sum().reindex(a.index).fillna(0)
    del g
    gc.collect()
    a["dratio"] = a.delta / a.vol
    a["bigratio"] = a.bigv / a.vol
    a["szskew"] = (a.hisz - a.losz) / np.maximum(a.hisz + a.losz, 1.0)
    a["tickrun"] = 2.0 * (a.nup / np.maximum(a.ntr, 1)) - 1.0
    dur = np.maximum((a.t1 - a.t0) / NS, 1e-3)
    a["intensity"] = a.ntr / dur
    a["intensity"] /= a["intensity"].rolling(400, min_periods=100).mean()
    a["cumdelta"] = a.delta.cumsum()
    a["cumdelta"] -= a.cumdelta.rolling(400, min_periods=100).mean()
    a["ret"] = a.close.diff()
    a["rng"] = a.high - a.low
    a["delta"] = a.delta / np.maximum(
        a.vol.rolling(400, min_periods=100).mean(), 1e-9)
    return a


def fwd_ret(a, k):
    c = a.close.values
    day = a.day.values
    n = len(c)
    y = np.full(n, np.nan)
    y[:n - k] = c[k:] - c[:n - k]
    same = np.zeros(n, dtype=bool)
    same[:n - k] = day[k:] == day[:n - k]
    y[~same] = np.nan
    return y


def main():
    files = sorted(glob.glob(os.path.join(RAW, "NQ*.parquet")))
    per = {}
    for f in files:
        cn = os.path.basename(f).replace(".parquet", "")
        try:
            a = build(f)
        except Exception as exc:                              # noqa: BLE001
            print(f"  {cn}: FAILED {exc}", flush=True)
            continue
        if a is None:
            continue
        per[cn] = a
        print(f"  {cn}: {len(a):,} bars", flush=True)
        gc.collect()
    if len(per) < 4:
        print("not enough contracts")
        return
    cs = sorted(per)
    tr_c, ho_c = cs[:5], cs[5:]

    log("# Do the order-flow features combine?")
    log()
    log("Every number in this project is a **single feature measured "
        "alone**. At 60-second bars three sit at almost the same "
        "strength -- range, trade intensity and return, each ~0.15pt of "
        "edge at 3.1-3.5x the noise floor with sign-stable "
        "train/holdout. They are different measurements, so they may "
        "carry partly independent information.")
    log()
    log("    if fully independent: sqrt(3) x 0.15 = 0.26pt = $0.52")
    log("    cost at $0.60 all-in:                          $0.60")
    log("    -> 87% of breakeven, from features already measured")
    log()
    log(f"**What pays.** At {BAR}s bars on one MNQ, `edge($) = IC x "
        f"sigma x 2`. Breakeven at ${COST:.2f} needs **IC > 0.026**; "
        f"$150/day at 200 trades needs **IC > 0.059**. Best single "
        f"feature measured is intensity at holdout IC 0.0132, so "
        f"breakeven needs 2.0x it and the income target 4.5x.")
    log()
    log(f"Train: {', '.join(tr_c)}. Holdout: {', '.join(ho_c)}. "
        f"Purged by contract -- different quarters are different "
        f"periods, so there is no leakage across the boundary. Exactly "
        f"the nine features already measured, no new ones.")
    log()

    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    try:
        import lightgbm as lgb
        HAVE_LGB = True
    except Exception:                                         # noqa: BLE001
        HAVE_LGB = False

    log("| horizon | model | train IC | **holdout IC** | edge $ | "
        "net @ $0.60 | vs best single |")
    log("|" + "---|" * 7)
    best_overall = None
    for k in FWD:
        Xtr, ytr, Xho, yho = [], [], [], []
        for c in cs:
            a = per[c]
            y = fwd_ret(a, k)
            X = a[FEATS].values.astype(np.float64)
            ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
            if c in tr_c:
                Xtr.append(X[ok])
                ytr.append(y[ok])
            else:
                Xho.append(X[ok])
                yho.append(y[ok])
        Xtr = np.vstack(Xtr)
        ytr = np.concatenate(ytr)
        Xho = np.vstack(Xho)
        yho = np.concatenate(yho)
        sig = float(np.nanstd(yho))
        sc = StandardScaler().fit(Xtr)
        Xtr_s, Xho_s = sc.transform(Xtr), sc.transform(Xho)

        # best single feature on the holdout, for comparison
        singles = {f: abs(ic(Xho[:, i], yho)) for i, f in enumerate(FEATS)}
        bsf = max(singles.values())

        runs = [("ridge", Ridge(alpha=100.0).fit(Xtr_s, ytr))]
        if HAVE_LGB:
            m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.05,
                                  num_leaves=15, min_child_samples=500,
                                  subsample=0.7, subsample_freq=1,
                                  colsample_bytree=0.7, reg_lambda=20.0,
                                  verbose=-1, n_jobs=4)
            runs.append(("lightgbm", m.fit(Xtr_s, ytr)))
        rng = np.random.default_rng(8)
        runs.append(("shuffled ctl",
                     Ridge(alpha=100.0).fit(Xtr_s, rng.permutation(ytr))))

        for nm, mdl in runs:
            ptr = mdl.predict(Xtr_s)
            pho = mdl.predict(Xho_s)
            itr, iho = ic(ptr, ytr), ic(pho, yho)
            ed = abs(iho) * sig * TV
            net = ed - COST
            log(f"| {k*BAR}s | {nm} | {itr:+.4f} | **{iho:+.4f}** | "
                f"${ed:.2f} | ${net:+.2f} | {abs(iho)/bsf:.2f}x |")
            if nm != "shuffled ctl" and (best_overall is None
                                         or abs(iho) > best_overall[0]):
                best_overall = (abs(iho), nm, k * BAR, ed, net)
        log()
        del Xtr, ytr, Xho, yho, Xtr_s, Xho_s
        gc.collect()

    log("## Verdict")
    log()
    if best_overall:
        b = best_overall
        log(f"Best combination: **{b[1]} at {b[2]}s, holdout IC "
            f"{b[0]:.4f}**, edge ${b[3]:.2f}/trade, "
            f"**${b[4]:+.2f} net of ${COST:.2f} cost**.")
        log()
        if b[4] > 0:
            log("**Positive.** That is the first configuration in this "
                "project to clear its cost. It now owes the rest of the "
                "gauntlet: an all-cell null, quarter-by-quarter "
                "stability, a stale placebo that loses, and a bot-exact "
                "simulation before any capital moves.")
        else:
            log(f"Still short by ${-b[4]:.2f}/trade. Combining helped "
                f"only to the extent the features were independent, and "
                f"the shortfall is what remains for full-depth book data "
                f"to close.")
    log()
    log("Read the shuffled row first. Whatever it reports is what this "
        "pipeline manufactures from nothing, and every real number has "
        "to be judged against it rather than against zero. And compare "
        "train IC with holdout IC on the LightGBM row: a large gap there "
        "is overfitting made visible.")
    log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()

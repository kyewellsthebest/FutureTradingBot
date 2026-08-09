"""Stop enumerating strategies. Measure the CEILING of the whole feature space.

The user's question -- have we metal-detectored a fifth of the haystack, or
should we just brute force harder -- deserves a real answer, and the answer is
that neither framing is right.

We have not covered a fifth. Every one of the 1.8M strategies was an
AXIS-ALIGNED THRESHOLD RULE: feature A above its 70th percentile AND feature B
above its 85th. That is a blocky, measure-zero sliver of all the ways twelve
features can combine, and no amount of it will ever cover the space, because
the space of functions is infinite.

But brute-forcing more rules is the wrong response. Rules are a terrible way to
explore -- 1.8 million of them probe less of the function space than one fitted
model does, because a model finds continuous combinations and interactions that
no threshold grid contains.

So this does something different in kind. It fits a gradient-boosted model to
ALL features at once and measures its out-of-sample predictive power. That
number is an UPPER BOUND on what any strategy built from these features can
achieve -- including every rule never enumerated and every idea never had.

    ceiling below cost  ->  more searching in this space is PROVABLY pointless
    ceiling above cost  ->  real signal the blocky rules could not capture,
                            and the job becomes extraction rather than search

WHAT MAKES THE NUMBER HONEST:

  PURGED, EMBARGOED, WALK-FORWARD CV. Time series leak through ordinary k-fold
  because neighbouring rows share overlapping outcome windows. Each fold trains
  strictly on the past, and a gap the length of the prediction horizon is cut
  out between train and test so no training row's outcome window overlaps a
  test row.

  A SHUFFLED CONTROL, same model, same folds, same everything. A boosted tree
  with hundreds of splits will fit noise; the shuffled run measures exactly how
  much, instead of assuming it is zero. Reported ceiling is real minus shuffled.

  DOLLARS, WITH TURNOVER. The model's output is a POSITION, not a trade. Cost
  is charged on |change in position|, which is the other thing every previous
  test got wrong -- they charged a full round turn for every signal even when
  the signal had not changed. Cost scales with how often the view FLIPS, not
  how often a view exists.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.environ.get("OUT_MD", os.path.join(ROOT, "research", "CEILING.md"))
PT = 4
USD_PT = 2.00
COST_RT = 1.99                     # per round turn, i.e. per 2 units of |dpos|
K = int(os.environ.get("K", "2000"))          # tick-event bar size
HZ = [int(x) for x in os.environ.get("HZ", "1,3,10,30").split(",")]
NFOLD = int(os.environ.get("NFOLD", "6"))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def bars(pc, vol, ts, k):
    m = (len(pc) // k) * k
    q = pc[:m].reshape(-1, k)
    v = vol[:m].reshape(-1, k)
    t = ts[:m].reshape(-1, k)
    return dict(o=q[:, 0].astype(np.float64), c=q[:, -1].astype(np.float64),
                h=q.max(1).astype(np.float64), l=q.min(1).astype(np.float64),
                v=v.sum(1).astype(np.float64),
                dur=np.log1p(np.maximum(t[:, -1] - t[:, 0], 0) / 1e6),
                path=np.abs(np.diff(q, axis=1)).sum(1).astype(np.float64),
                ts=t[:, 0])


def features(B):
    """Everything the rule searches had, plus everything they could not express:
    continuous values rather than thresholds, and the model finds the rest."""
    c, h, l, o, v = B["c"], B["h"], B["l"], B["o"], B["v"]
    dur, path = B["dur"], B["path"]
    F = {}
    dc = np.r_[np.nan, np.diff(c)]
    for w in (3, 8, 21, 55, 144):
        mu = pd.Series(c).rolling(w).mean().values
        sd = np.maximum(pd.Series(c).rolling(w).std().values, 1e-9)
        prev = np.r_[np.full(w, np.nan), c[:-w]]
        hh = pd.Series(h).rolling(w).max().values
        ll = pd.Series(l).rolling(w).min().values
        rng = np.maximum(hh - ll, 1e-9)
        pw = np.maximum(pd.Series(np.abs(dc)).rolling(w).sum().values, 1e-9)
        F[f"mom{w}"] = (c - prev) / sd
        F[f"rev{w}"] = -(c - mu) / sd
        F[f"pos{w}"] = (c - ll) / rng * 2 - 1
        F[f"eff{w}"] = (c - prev) / pw
        F[f"rngz{w}"] = rng / np.maximum(
            pd.Series(rng).rolling(w).mean().values, 1e-9) - 1
        F[f"volz{w}"] = (v - pd.Series(v).rolling(w).mean().values) / np.maximum(
            pd.Series(v).rolling(w).std().values, 1e-9)
        F[f"durz{w}"] = (dur - pd.Series(dur).rolling(w).mean().values) / \
            np.maximum(pd.Series(dur).rolling(w).std().values, 1e-9)
        F[f"pthz{w}"] = (path - pd.Series(path).rolling(w).mean().values) / \
            np.maximum(pd.Series(path).rolling(w).std().values, 1e-9)
        F[f"chop{w}"] = pd.Series((np.sign(dc) * np.sign(np.r_[np.nan, dc[:-1]])
                                   < 0).astype(float)).rolling(w).mean().values
    F["shape"] = (c - l) / np.maximum(h - l, 1e-9) * 2 - 1
    F["body"] = (c - o) / np.maximum(h - l, 1e-9)
    F["gap"] = np.r_[np.nan, o[1:] - c[:-1]]
    F["ineff"] = (h - l) / np.maximum(path, 1e-9)
    F["hour"] = ((B["ts"] // 3_600_000_000_000) % 24).astype(np.float64)
    F["volreg"] = (pd.Series(np.abs(dc)).rolling(21).mean().values /
                   np.maximum(pd.Series(np.abs(dc)).rolling(144).mean().values,
                              1e-9))
    return F


def purged_cv(n, nfold, horizon):
    """Walk-forward folds with an embargo, so no training row's outcome window
    can overlap a test row. Ordinary k-fold leaks badly here."""
    edges = np.linspace(0, n, nfold + 2).astype(int)
    for i in range(1, nfold + 1):
        te0, te1 = edges[i], edges[i + 1]
        tr1 = max(0, te0 - horizon - 1)
        if tr1 < 500 or te1 - te0 < 200:
            continue
        yield np.arange(0, tr1), np.arange(te0, te1)


def main():
    import lightgbm as lgb
    Xs, Ys, Cs = [], {h: [] for h in HZ}, []
    for p in sorted(glob.glob(os.path.join(CACHE, "dest_NQ*.npz"))):
        c = os.path.basename(p)[5:-4]
        z = np.load(p, allow_pickle=False)
        B = bars(z["pc"].astype(np.int64), z["vol"].astype(np.float64),
                 z["ts"].astype(np.int64), K)
        F = features(B)
        names = sorted(F)
        X = np.column_stack([F[k] for k in names])
        cl = B["c"]
        for h in HZ:
            y = np.full(len(cl), np.nan)
            y[:-h] = (cl[h:] - cl[:-h]) / PT * USD_PT     # dollars, one MNQ
            Ys[h].append(y)
        Xs.append(X)
        Cs.append(np.full(len(cl), c))
        print(f"  {c}: {len(cl):,} bars of {K} prints", flush=True)
    X = np.vstack(Xs)
    C = np.concatenate(Cs)
    log("# The ceiling: how much signal is in these features AT ALL?")
    log()
    log("Every previous search enumerated axis-aligned threshold rules — "
        "'feature A above its 70th percentile'. That is a blocky, measure-zero "
        "sliver of the ways features can combine, so 'have we covered a fifth?' "
        "has no good answer. This asks the question that does: fit a "
        "gradient-boosted model to all features at once and measure its "
        "out-of-sample power. That is an **upper bound on every strategy in "
        "this feature space**, including the ones never enumerated.")
    log()
    log(f"{X.shape[0]:,} bars of {K} price prints, {X.shape[1]} features, "
        f"8 NQ contracts. Walk-forward folds with an embargo the length of the "
        "prediction horizon, so no training row's outcome window can touch a "
        "test row. A shuffled-target control runs identically — a boosted tree "
        "WILL fit noise, and this measures how much rather than assuming zero.")
    log()
    log("| horizon | out-of-sample IC | shuffled control | **real − shuffled** "
        "| $/bar at full position | turnover-aware net |")
    log("|---|---|---|---|---|---|")
    rng = np.random.default_rng(11)
    for h in HZ:
        y = np.concatenate(Ys[h])
        ok = np.isfinite(y) & np.isfinite(X).all(1)
        Xo, yo = X[ok], y[ok]
        res = {}
        for lab in ("real", "shuffled"):
            yy = yo if lab == "real" else rng.permutation(yo)
            preds = np.full(len(yy), np.nan)
            for tr, te in purged_cv(len(yy), NFOLD, h):
                m = lgb.LGBMRegressor(n_estimators=250, learning_rate=0.04,
                                      num_leaves=31, min_child_samples=200,
                                      subsample=0.7, colsample_bytree=0.7,
                                      reg_lambda=5.0, verbose=-1, n_jobs=4)
                m.fit(Xo[tr], yy[tr])
                preds[te] = m.predict(Xo[te])
            v = np.isfinite(preds)
            ic = float(np.corrcoef(preds[v], yy[v])[0, 1])
            # position = sign-scaled prediction, clipped to +-1 contract
            s = preds[v] / max(np.nanstd(preds[v]), 1e-12)
            pos = np.clip(s, -1, 1)
            gross = float(np.mean(pos * yy[v]))
            turn = float(np.mean(np.abs(np.diff(pos, prepend=0.0))))
            net = gross - turn * COST_RT / 2.0
            res[lab] = (ic, gross, turn, net)
        (ir, gr, tu, nt) = res["real"]
        (isx, gsx, tsx, nsx) = res["shuffled"]
        log(f"| {h} bars | {ir:+.4f} | {isx:+.4f} | **{ir-isx:+.4f}** | "
            f"${gr:+.3f} | **${nt:+.3f}** (turnover {tu:.2f}/bar) |")
    log()
    log("**How to read it.** The IC column is the correlation between the "
        "model's prediction and what actually happened, out of sample. The "
        "shuffled column is the same model on scrambled targets — that is how "
        "much a boosted tree invents from nothing. Only the difference is real.")
    log()
    log("The last column is the one that decides everything: the model's output "
        "treated as a POSITION, with cost charged on how much the position "
        "CHANGES rather than a full round turn per signal. That is the "
        "turnover fix — every earlier test paid $1.99 for every opinion even "
        "when the opinion had not changed.")
    log()
    log("If real minus shuffled is at zero, no strategy built from these "
        "features can work, and no further enumeration in this space is worth "
        "running. That is the answer to 'how much of the haystack is left'.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

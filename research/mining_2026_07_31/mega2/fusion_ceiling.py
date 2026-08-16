"""Does adding data types raise the ceiling? Ablation, one group at a time.

This is the metal detector pointed at DATA SOURCES instead of at strategies.

Enumerating rules inside a stream that carries no information is the handful of
hay. 26 billion configurations were spent that way and the measured ceiling of
the NQ price path came back at zero. So before spending another configuration,
sweep the detector over each stream and ask the only question that matters
first: is there anything in here AT ALL?

A gradient-boosted model given every feature of a group is an upper bound on
every strategy anyone could build from that group, including the ones nobody
will ever enumerate. So:

    group raises the ceiling  ->  go and enumerate strategies in it
    group does not            ->  searching it is provably pointless, and we
                                  have that answer in hours instead of weeks

SIX SETS:

    p            price path only            reproduces the known zero
    p+f          + NQ order flow            same file, size and aggressor
    p+i          + index complex            ES / YM / RTY on NQ's clock
    p+m          + macro complex            CL / GC / HG
    p+f+i+m      all four at once           the user's actual proposal
    f+i+m        everything EXCEPT price    the cleanest possible statement of
                                            "is there information outside the
                                            one stream two billion people
                                            already watch?"

THREE CONTROLS, and the third is the one that can fail interestingly:

    shuffled target   how much a boosted tree invents from nothing
    stream shift      foreign tapes slid days along the calendar and rejoined.
                      Same tapes, wrong times. A real cross-market effect dies;
                      a join bug survives.
    chronological     contracts concatenated in DATE order and folds walked
                      forward through them. ceiling.py stacked them in
                      alphabetical order -- H5, H6, M5, M6, U4... -- so its
                      "train on the past" trained on 2026 to predict 2025. It
                      measured zero anyway so it manufactured nothing, but the
                      fold structure was wrong and is fixed here.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

ROOT = fuse.ROOT
FCACHE = os.path.join(ROOT, "data", "tick", "fusecache")
OUT = os.environ.get("OUT_MD", os.path.join(ROOT, "research", "FUSION.md"))
K = int(os.environ.get("K", "500"))            # prints per bar -> ~2.7 min
HZ = [int(x) for x in os.environ.get("HZ", "1,5,20").split(",")]
NFOLD = int(os.environ.get("NFOLD", "4"))
NTREE = int(os.environ.get("NTREE", "200"))
USD_PT = 2.00                                   # MNQ
COST_RT = 1.99                                  # measured, from the user's fills
WARM = 250                                      # bars of feature warm-up
CONTRACTS = os.environ.get("CONTRACTS", ",".join(fuse.NQ_CONTRACTS)).split(",")
SKIP_SHIFT = os.environ.get("SKIP_SHIFT", "") not in ("", "0")
L = []


def floor_of(n, h):
    """Three standard errors on the number of INDEPENDENT observations.

    An h-bar forward return measured at every bar overlaps its h-1
    neighbours, so n out-of-sample bars carry about n/h independent
    outcomes. Using 3/sqrt(n) at h=400 would quote a noise floor twenty
    times tighter than the data supports, which is exactly how a long
    horizon manufactures a finding. This is the correction B2 asks for.
    """
    return 3.0 / np.sqrt(max(n / max(h, 1), 1.0))


def log(s=""):
    print(s, flush=True)
    L.append(s)


def matrix(contract, shift):
    """Build (and cache) one contract's aligned feature matrix."""
    tag = "shift" if shift else "real"
    p = os.path.join(FCACHE, f"{contract}_K{K}_L{fuse.LAG_MS}_{tag}.npz")
    if os.path.exists(p):
        z = np.load(p, allow_pickle=False)
        return (z["X"], list(z["names"]), z["c"], z["ts"],
                json.loads(str(z["cov"])))
    B, F, cov = fuse.build(contract, K, shift=shift)
    names = sorted(F)
    X = np.column_stack([np.asarray(F[k], dtype=np.float32) for k in names])
    os.makedirs(FCACHE, exist_ok=True)
    np.savez_compressed(p, X=X, names=np.array(names), c=B["c"], ts=B["ts"],
                        cov=json.dumps(cov))
    return X, names, B["c"], B["ts"], cov


def assemble(shift):
    """Contracts concatenated in DATE order -- the quarters are sequential and
    non-overlapping, so this is two continuous years of tape."""
    Xs, cs, ts, cov = [], [], [], {}
    names = None
    for c in CONTRACTS:
        t0 = time.time()
        X, nm, cl, tt, cv = matrix(c, shift)
        if names is None:
            names = nm
        assert nm == names, f"{c} feature set differs"
        X = X[WARM:]
        cl = cl[WARM:].astype(np.float64)
        tt = tt[WARM:]
        y = {}
        for h in HZ:
            v = np.full(len(cl), np.nan)
            v[:-h] = (cl[h:] - cl[:-h]) / fuse.PT * USD_PT
            y[h] = v
        Xs.append(X)
        cs.append(y)
        ts.append(tt)
        cov[c] = cv
        print(f"  {c}: {len(cl):,} bars  ({time.time()-t0:.0f}s)", flush=True)
    X = np.vstack(Xs)
    Y = {h: np.concatenate([d[h] for d in cs]) for h in HZ}
    T = np.concatenate(ts)
    return X, names, Y, T, cov


def purged_cv(n, nfold, horizon):
    edges = np.linspace(0, n, nfold + 2).astype(int)
    for i in range(1, nfold + 1):
        te0, te1 = edges[i], edges[i + 1]
        tr1 = max(0, te0 - horizon - 1)
        if tr1 < 5000 or te1 - te0 < 1000:
            continue
        yield np.arange(0, tr1), np.arange(te0, te1)


def score(X, y, h, shuffle, rng, y1=None):
    """OVERLAP INFLATION -- fixed here, and it was wrong in the first run.

    The dollar columns used to be mean(pos[t] * y_h[t]) summed over every bar,
    where y_h is an h-bar forward return. Holding pos[t] from t to t+h for
    EVERY t means running h overlapping positions at once, so that P&L belongs
    to a book h times the intended size while the turnover -- and therefore the
    cost -- was still that of a single contract. Gross was inflated by roughly
    h, cost was not, and every net figure at h>1 was flattered.

    The fix is the standard one: predict the h-bar return, but account the P&L
    against the NEXT BAR's return and let the position persist. `y1` is that
    one-bar return in dollars. The IC columns were never affected.
    """
    import lightgbm as lgb
    ok = np.isfinite(y)
    Xo, yo = X[ok], y[ok]
    if shuffle:
        yo = rng.permutation(yo)
    preds = np.full(len(yo), np.nan)
    for tr, te in purged_cv(len(yo), NFOLD, h):
        m = lgb.LGBMRegressor(n_estimators=NTREE, learning_rate=0.05,
                              num_leaves=31, min_child_samples=500,
                              subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.5, reg_lambda=10.0,
                              verbose=-1, n_jobs=4)
        m.fit(Xo[tr], yo[tr])
        preds[te] = m.predict(Xo[te])
    v = np.isfinite(preds)
    if v.sum() < 1000 or np.nanstd(preds[v]) < 1e-12:
        return dict(ic=0.0, gross=0.0, turn=0.0, net=0.0, n=int(v.sum()))
    ic = float(np.corrcoef(preds[v], yo[v])[0, 1])
    s = preds[v] / np.nanstd(preds[v])
    pos = np.clip(s, -1, 1)
    if y1 is None:
        pnl = yo[v]                     # h == 1: the two coincide
    else:
        pnl = y1[ok][v]                 # one-bar return, position persists
    gross = float(np.nanmean(pos * pnl))
    turn = float(np.mean(np.abs(np.diff(pos, prepend=0.0))))
    return dict(ic=ic, gross=gross, turn=turn,
                net=gross - turn * COST_RT / 2.0, n=int(v.sum()))


SETS = [
    ("price path only", ("p_",)),
    ("+ NQ order flow", ("p_", "f_")),
    ("+ index complex (ES/YM/RTY)", ("p_", "i_")),
    ("+ macro complex (CL/GC/HG)", ("p_", "m_")),
    ("all four types", ("p_", "f_", "i_", "m_")),
    ("everything EXCEPT price path", ("f_", "i_", "m_")),
]


def main():
    t0 = time.time()
    print("building real matrices...", flush=True)
    X, names, Y, T, cov = assemble(False)
    nm = np.array(names)
    days = len(np.unique(T // fuse.DAY_NS))
    bpd = len(T) / max(days, 1)
    print(f"\n{X.shape[0]:,} bars x {X.shape[1]} features, "
          f"{days} days, {bpd:.0f} bars/day", flush=True)

    log("# Four data types at once — does any of them carry information?")
    log()
    log("Every search so far read one stream: the NQ price path. Its ceiling "
        "measured zero. That is a fact about **that stream**, not about the "
        "market. This loads three more and asks the question that has to come "
        "first — is there anything in here at all — before another "
        "configuration is enumerated.")
    log()
    log(f"`{X.shape[0]:,}` tick-event bars of {K} prints (~{bpd:.0f} bars/day, "
        f"{days} trading days, {len(CONTRACTS)} sequential NQ quarters — two "
        f"continuous years). `{X.shape[1]}` features. Foreign tapes are read "
        f"as of **bar close minus {fuse.LAG_MS} ms**, so nothing contemporaneous "
        f"can leak in through them.")
    log()
    log("## Stream coverage")
    log()
    log("| NQ quarter | " + " | ".join(fuse.FOREIGN) + " |")
    log("|---" * (len(fuse.FOREIGN) + 1) + "|")
    for c in CONTRACTS:
        row = " | ".join(f"{cov[c].get(s, 0.0)*100:.0f}%" for s in fuse.FOREIGN)
        log(f"| {c} | {row} |")
    log()
    log("GC and HG only have dense tape in a few quarters — thin contracts are "
        "rejected by a 5,000-prints-a-day floor rather than silently averaged "
        "in, because a name-based pick once grabbed a 22,805-print stub and "
        "invented a market that traded 161 ticks a day.")
    log()

    rng = np.random.default_rng(1234)
    res = {}
    for lab, pres in SETS:
        cols = np.flatnonzero([n.startswith(pres) for n in nm])
        for h in HZ:
            for ctl in ("real", "shuffled"):
                k = (lab, h, ctl)
                t1 = time.time()
                res[k] = score(X[:, cols], Y[h], h, ctl == "shuffled", rng,
                               y1=None if h == 1 else Y[1])
                print(f"  {lab:32s} h={h:<3d} {ctl:9s} "
                      f"IC={res[k]['ic']:+.4f} net=${res[k]['net']:+.3f} "
                      f"({time.time()-t1:.0f}s)", flush=True)
                json.dump({f"{a}|{b}|{c}": v for (a, b, c), v in res.items()},
                          open(os.path.join(FCACHE, "partial.json"), "w"))

    log("## The ceiling of each data set")
    log()
    log("IC is the out-of-sample correlation between what the model predicted "
        "and what happened. The shuffled column is the identical model on "
        "scrambled outcomes — that is what a boosted tree invents from nothing. "
        "Only the difference is real.")
    log()
    for h in HZ:
        log(f"### {h} bar" + ("s" if h > 1 else "") +
            f" ahead (~{h * 24 * 60 / bpd:.0f} min)")
        log()
        log("| data | features | IC | shuffled | **real − shuffled** | "
            "round turns/day | gross $/day | **net $/week** |")
        log("|---|---|---|---|---|---|---|---|")
        for lab, pres in SETS:
            nc = int(np.sum([n.startswith(pres) for n in nm]))
            r = res[(lab, h, "real")]
            s = res[(lab, h, "shuffled")]
            d = r["ic"] - s["ic"]
            flag = "**" if abs(d) > floor_of(r["n"], h) else ""
            log(f"| {lab} | {nc} | {r['ic']:+.4f} | {s['ic']:+.4f} | "
                f"{flag}{d:+.4f}{flag} | {r['turn']*bpd/2:.0f} | "
                f"${r['gross']*bpd:+.0f} | **${r['net']*bpd*5:+,.0f}** |")
        log()
        _n0 = res[(SETS[0][0], h, "real")]["n"]
        log(f"Noise floor at this sample size is ±{floor_of(_n0, h):.4f} "
            f"(3 standard errors on {_n0/max(h,1):,.0f} INDEPENDENT "
            f"outcomes — {_n0:,} out-of-sample bars, but an {h}-bar forward "
            f"return overlaps its {h-1} neighbours); bolded gaps clear it. "
            f"One MNQ, "
            f"${COST_RT:.2f} a round turn, cost charged on how much the "
            f"position CHANGES rather than once per opinion.")
        log()

    # -------- the control that only a fusion study can run -------------------
    best = max(
        [(res[(lab, h, "real")]["ic"] - res[(lab, h, "shuffled")]["ic"], lab, h)
         for lab, pres in SETS if any(p in ("i_", "m_") for p in pres)
         for h in HZ])
    log("## The stream-shift control")
    log()
    log("The foreign tapes are slid "
        f"{fuse.SHIFT_DAYS:g} days along the calendar and rejoined to the same "
        "NQ bars. Their volatility, their flow, their autocorrelation are all "
        "untouched — only the alignment with NQ is destroyed. A real "
        "cross-market effect has to die here. Anything that survives was never "
        "cross-market information and is a bug in the join.")
    log()
    dshift, blab, bh = best
    if SKIP_SHIFT:
        log("_Skipped in this run (`SKIP_SHIFT=1`): rebuilding the shifted "
            "matrices costs more than the whole horizon sweep, and there is "
            "nothing to kill unless a real−shuffled gap clears its noise "
            "floor first. If one does, re-run without the flag._")
        log()
        _finish(t0, bpd)
        return
    print(f"\nstream-shift control on: {blab} h={bh}", flush=True)
    Xs, names_s, Ys, Ts, _ = assemble(True)
    assert names_s == names
    log("| data | horizon | real − shuffled | **shifted − shuffled** | verdict |")
    log("|---|---|---|---|---|")
    for lab, pres in SETS:
        if not any(p in ("i_", "m_") for p in pres):
            continue
        cols = np.flatnonzero([n.startswith(pres) for n in nm])
        for h in HZ:
            sh = score(Xs[:, cols], Ys[h], h, False, rng,
                       y1=None if h == 1 else Ys[1])
            base = res[(lab, h, "shuffled")]["ic"]
            d_real = res[(lab, h, "real")]["ic"] - base
            d_sh = sh["ic"] - base
            # gate every verdict on the noise floor first. An IC gap smaller
            # than three standard errors is not an effect, so it can neither
            # be killed by the shift nor survive it, and calling it either way
            # is how a study talks itself into a finding.
            floor = floor_of(sh["n"], h)
            v = ("nothing to kill (below the ±%.4f noise floor)" % floor
                 if abs(d_real) < floor
                 else "**real cross-market effect**" if d_sh < d_real / 2
                 else "**SURVIVES THE SHIFT — leak, do not trade**")
            log(f"| {lab} | {h} | {d_real:+.4f} | {d_sh:+.4f} | {v} |")
            print(f"  shift {lab:32s} h={h:<3d} d={d_sh:+.4f}", flush=True)

    _finish(t0, bpd)


def _finish(t0, bpd):
    log()
    log("## What this decides")
    log()
    log(f"A round turn costs **${COST_RT:.2f}** and the model trades a "
        f"continuous position, so cost is charged on how much the position "
        f"CHANGES, not once per opinion. At {bpd:.0f} bars a day, "
        f"${0.10:.2f}/bar would be ${0.10*bpd*5:,.0f} a week — so the net "
        f"column is the whole answer, and any set whose real−shuffled gap sits "
        f"at zero is a stream that cannot be searched profitably no matter how "
        f"many configurations are thrown at it.")
    log()
    log("Data types 5 and 6 — order book and options — are stubbed in "
        "`fuse.py` behind `load_book()` and `load_options()`. They drop into "
        "the same clock, the same lag rail and the same ablation the moment "
        "the files exist; see TODO_FOR_USER.md for the exact format.")
    log()
    log(f"_Ran in {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

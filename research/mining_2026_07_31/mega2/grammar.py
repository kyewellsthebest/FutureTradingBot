"""Phase A of Engine V3: the tick tape as a grammar of legs.

Not bars. The tape is decomposed into alternating directional LEGS via a
reversal threshold R: price runs one way until it comes back R ticks off its
extreme. The moment that R-tick retracement prints is the CONFIRMATION -- the
first instant the leg's completion is knowable -- and everything is anchored
there. Conditioning features use only data at or before confirmation; outcomes
are measured from the confirmation price forward. Look-ahead is structurally
impossible rather than carefully avoided.

Each completed leg carries distance, price-change count, duration, velocity
and volume, each normalized by the rolling median of the previous 200 legs
(shifted -- a leg never normalizes itself). Retracement depth is this leg's
distance over the previous leg's. Binned on train-only quantiles, those
attributes become a conditional expectancy table:

    given what the last leg looked like, what is the distribution of the
    signed forward move over the next F price-changes?

Positive = continuation of the newly confirmed direction. Cells are judged
against the EVENT-POPULATION baseline (all confirmations at that scale), not
against zero; with neighbourhood stability (do the +/-1-bin cells agree out of
sample?); with a per-contract sign vote across all eight NQ contracts; and
against two cost gates, $1.42 commission-only and $4.40 with the user's $3
slippage figure, at $0.50 a tick on MNQ.

SYNTH=1 runs the whole machine on a random-walk tape first. On data with no
structure by construction it must report nothing beyond the false-positive
rate -- an engine that finds something in nothing is not allowed near the
real tape.

Usage: python grammar.py [R ...]        (reversal thresholds in ticks)
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.environ.get("RAW_DIR", os.path.join(ROOT, "data", "tick", "raw"))
OUT = os.environ.get("OUT_MD", os.path.join(ROOT, "research", "TICK_GRAMMAR.md"))
GLOB = os.environ.get("GLOB", "NQ*.parquet")
TAG = os.environ.get("TAG", "NQ")
TICK = float(os.environ.get("TICKSZ", "0.25"))     # tick size, price units
USD_TICK = float(os.environ.get("USD_TICK", "0.50"))  # $ per tick, micro contract
RS = [int(x) for x in (sys.argv[1:] or ["4", "8", "16"])]
HORIZONS = [int(x) for x in os.environ.get("HORIZONS", "50,200,1000").split(",")]
NORM_W = int(os.environ.get("NORM_W", "200"))
MIN_TR, MIN_HO = 400, 150
SYNTH = os.environ.get("SYNTH", "0") == "1"
# DELAY: measure outcomes from the DELAY-th price CHANGE after confirmation
# instead of the confirmation print itself. Trade prints bounce between bid
# and ask, and the confirmation print sits preferentially on one side, so a
# same-print entry inherits up to a spread of free-looking edge. One price
# change later the bounce has resolved. If a cell's effect is bounce, DELAY=1
# kills it; if it is behaviour, it survives smaller.
DELAY = int(os.environ.get("DELAY", "0"))
# HOLDOUT_CONTRACTS: comma-separated contract names held out ENTIRELY. The
# default split takes the last 30% within each contract, so training has seen
# a slice of every era. Holding out whole contracts -- the newest ones, an era
# the engine has never touched -- closes the last leakage channel. Bin edges,
# screens and baselines then come only from the training contracts.
HOLDOUT_CONTRACTS = set(x for x in
                        os.environ.get("HOLDOUT_CONTRACTS", "").split(",") if x)
GATES = [1.42, 4.40]               # $ per round turn: commission-only, +slippage
# SEQ2=1 appends the PREVIOUS leg's distance and velocity bins to the cell key
# -- the first state-machine depth. Cells multiply 15x; the count gates decide
# which survive, and sparsity is reported rather than hidden.
SEQ2 = os.environ.get("SEQ2", "0") == "1"

LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


def compress(price, size, ts):
    """Collapse consecutive same-price prints to price CHANGES.

    Event time starts here: horizons and leg lengths are counted in price
    changes, not prints and not seconds. Volume between changes is summed so
    nothing is lost, only deduplicated.
    """
    pt = np.round(price / TICK).astype(np.int64)
    chg = np.r_[True, pt[1:] != pt[:-1]]
    starts = np.flatnonzero(chg)
    pc = pt[starts]
    vol = np.add.reduceat(size.astype(np.float64), starts)
    tsc = ts[starts]
    return pc, vol, tsc


def decompose(pc, R):
    """Zigzag with confirmation indices. Returns (pivot_i, confirm_i, dir).

    dir is the direction of the COMPLETED leg (+1 the leg went up and ended at
    a peak). The new leg's direction is -dir. Both pivot and confirmation are
    indices into the compressed change series.
    """
    n = len(pc)
    piv, conf, dirs = [], [], []
    hi = lo = pc[0]
    hi_i = lo_i = 0
    d = 0                                     # current leg direction, 0=unknown
    for k in range(1, n):
        x = pc[k]
        if d >= 0:
            if x > hi:
                hi, hi_i = x, k
                if d == 0 and x - lo >= R:
                    d = 1
            if hi - x >= R and d >= 0:
                if d == 1:
                    piv.append(hi_i); conf.append(k); dirs.append(1)
                d = -1
                lo, lo_i = x, k
                continue
        if d <= 0:
            if x < lo:
                lo, lo_i = x, k
                if d == 0 and hi - x >= R:
                    d = -1
            if x - lo >= R and d <= 0:
                if d == -1:
                    piv.append(lo_i); conf.append(k); dirs.append(-1)
                d = 1
                hi, hi_i = x, k
    return (np.array(piv, np.int64), np.array(conf, np.int64),
            np.array(dirs, np.int8))


def leg_table(pc, vol, tsc, R):
    """One contract, one scale -> DataFrame of confirmed legs with outcomes."""
    piv, conf, dirs = decompose(pc, R)
    if len(piv) < 300:
        return None
    # completed leg i runs from the previous pivot to this one
    start = np.r_[0, piv[:-1]]
    dist = np.abs(pc[piv] - pc[start]).astype(np.float64)      # ticks
    nchg = (piv - start).astype(np.float64)
    dur = (tsc[piv] - tsc[start]).astype(np.float64) / 1e9     # seconds
    cvol = np.array([vol[a:b].sum() for a, b in zip(start, piv)])
    vel = dist / np.maximum(dur, 1e-3)
    conf_lag = (conf - piv).astype(np.float64)

    d = pd.DataFrame(dict(piv=piv, conf=conf, dir=dirs, dist=dist, nchg=nchg,
                          dur=dur, vol=cvol, vel=vel, conf_lag=conf_lag))
    # normalize by the market's own recent state (Parts 23-24). shift(1): the
    # current leg must never appear in its own normalizer.
    for c in ("dist", "dur", "vol", "vel", "nchg"):
        med = d[c].rolling(NORM_W, min_periods=50).median().shift(1)
        d[c + "_n"] = d[c] / med
    d["retr"] = d.dist / d.dist.shift(1)      # this leg vs the one it retraced

    # outcomes: signed forward move from the CONFIRMATION price, continuation
    # of the new direction positive. new direction = -dir of completed leg.
    ent = np.minimum(conf + DELAY, len(pc) - 1)
    cp = pc[ent].astype(np.float64)
    for F in HORIZONS:
        tgt = np.minimum(ent + F, len(pc) - 1)
        d[f"fwd{F}"] = (pc[tgt] - cp) * (-d.dir)               # ticks
    d["ok"] = conf + DELAY + max(HORIZONS) < len(pc)
    return d[d.ok].drop(columns="ok").reset_index(drop=True)


def qbins(x, edges):
    return np.clip(np.digitize(x, edges), 0, len(edges)).astype(np.int8)


def main():
    files = sorted(glob.glob(os.path.join(RAW, GLOB)))
    log(f"# Tick grammar: {TAG} -- {len(files)} contracts, tick {TICK}, ${USD_TICK}/tick")
    log()
    if DELAY:
        log(f"**ENTRY DELAYED {DELAY} price change(s) past confirmation** -- "
            f"the bid-ask bounce test. Bounce dies at the first change; "
            f"behaviour survives it.")
        log()
    if SYNTH:
        log("**SYNTHETIC RANDOM WALK** -- the null check. Anything that "
            "passes screening here is the engine's false-positive rate.")
        log()

    t0 = time.time()
    for R in RS:
        frames = []
        for f in files:
            c = os.path.basename(f).replace(".parquet", "")
            if SYNTH:
                rng = np.random.default_rng(hash(c) % 2**31)
                n = 4_000_000
                price = 20000 + np.cumsum(rng.choice([-TICK, 0, 0, TICK], n))
                size = rng.integers(1, 5, n).astype(np.float64)
                ts = np.arange(n, dtype=np.int64) * 250_000_000
            else:
                import pyarrow.parquet as pq
                t = pq.read_table(f, columns=["ts", "price", "size"])
                price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
                size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
                ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
                del t
                # THE BUG THAT INVENTED CELL #21. These parquets are 86-88%
                # out of time order (rows jump back up to 73 hours), and this
                # loader never sorted. Every "leg" was a fiction of row order
                # and the "reversal continuation" was the file jumping back to
                # where the market had been hours earlier. The trade-level
                # replay sorted the tape and the effect died. Sort, always,
                # and never trust a tape without checking.
                o = np.argsort(ts, kind="stable")
                price, size, ts = price[o], size[o], ts[o]
                del o
            pc, vol, tsc = compress(price, size, ts)
            del price, size, ts
            d = leg_table(pc, vol, tsc, R)
            del pc, vol, tsc
            if d is None:
                continue
            d["contract"] = c
            if HOLDOUT_CONTRACTS:
                d["train"] = c not in HOLDOUT_CONTRACTS
            else:
                # chronological split WITHIN each contract, so train and
                # holdout both span all eight regimes
                d["train"] = np.arange(len(d)) < int(len(d) * 0.7)
            frames.append(d)
            print(f"  R={R} {c}: {len(d):,} legs [{time.time()-t0:.0f}s]",
                  flush=True)
        if not frames:
            continue
        D = pd.concat(frames, ignore_index=True)
        del frames

        # bins from TRAIN only, frozen
        tr = D.train.values
        edges = {}
        for c, nb in (("dist_n", 5), ("vel_n", 3), ("retr", 5), ("vol_n", 3)):
            v = D.loc[tr, c].replace([np.inf, -np.inf], np.nan).dropna()
            edges[c] = np.quantile(v, np.linspace(0, 1, nb + 1)[1:-1])
            D[c + "_b"] = qbins(D[c].values, edges[c])
        D = D.dropna(subset=["dist_n", "vel_n", "retr", "vol_n"])
        if SEQ2:
            # the leg before the one just completed, within the same contract
            D["p_dist_b"] = D.groupby("contract")["dist_n_b"].shift(1)
            D["p_vel_b"] = D.groupby("contract")["vel_n_b"].shift(1)
            D = D.dropna(subset=["p_dist_b", "p_vel_b"])
            D[["p_dist_b", "p_vel_b"]] = D[["p_dist_b", "p_vel_b"]].astype(np.int8)

        log(f"## R = {R} ticks -- {len(D):,} legs, "
            f"{D.contract.nunique()} contracts")
        log()
        for F in HORIZONS:
            y = D[f"fwd{F}"].values
            base_tr = y[D.train].mean()
            base_ho = y[~D.train].mean()
            log(f"### horizon {F} price-changes -- population baseline "
                f"train {base_tr:+.2f}, holdout {base_ho:+.2f} ticks")
            log()
            key = ["dir", "dist_n_b", "vel_n_b", "retr_b", "vol_n_b"]
            if SEQ2:
                key += ["p_dist_b", "p_vel_b"]
            g = D.groupby(key, observed=True)
            rows = []
            for k, grp in g:
                t_ = grp[grp.train]
                h_ = grp[~grp.train]
                if len(t_) < MIN_TR or len(h_) < MIN_HO:
                    continue
                yt = t_[f"fwd{F}"].values - base_tr
                yh = h_[f"fwd{F}"].values - base_ho
                set_ = yt.std() / np.sqrt(len(yt))
                tstat = yt.mean() / max(set_, 1e-9)
                if abs(tstat) < 3.0:
                    continue
                seh = yh.std() / np.sqrt(len(yh))
                # per-contract vote, holdout only
                votes = h_.groupby("contract")[f"fwd{F}"].mean() - base_ho
                agree = int((np.sign(votes) == np.sign(yt.mean())).sum())
                rows.append(dict(key=k, ntr=len(t_), nho=len(h_),
                                 tr=yt.mean(), t=tstat, ho=yh.mean(),
                                 hose=seh, agree=agree, nvote=len(votes)))
            if not rows:
                log("No cell reached |t|>=3 on train with enough data. "
                    "Nothing to screen.")
                log()
                continue
            RW = pd.DataFrame(rows)
            # neighbourhood stability: same holdout sign among cells whose
            # key differs by one step in exactly one binned dimension
            keymap = {r.key: np.sign(r.ho) for r in RW.itertuples()}
            def stab(k):
                same = tot = 0
                for dim in range(1, 5):
                    for step in (-1, 1):
                        kk = list(k); kk[dim] += step
                        s = keymap.get(tuple(kk))
                        if s is not None:
                            tot += 1
                            same += int(s == np.sign(keymap[k]))
                return same / tot if tot else np.nan
            RW["nbhd"] = [stab(k) for k in RW.key]
            RW["held"] = np.sign(RW.tr) == np.sign(RW.ho)
            RW["usd"] = RW.ho.abs() * USD_TICK
            RW = RW.sort_values("t", key=np.abs, ascending=False)

            held = RW.held.mean() * 100
            log(f"{len(RW)} cells passed the train screen (|t|>=3). "
                f"**{held:.0f}% held their sign out of sample** "
                f"(coin: 50%). Shuffled control below.")
            log()
            log("| cell (dir,dist,vel,retr,vol) | n tr/ho | train | t | "
                "HOLDOUT +/- se | vote | nbhd | $ gross | gates |")
            log("|---|---|---|---|---|---|---|---|---|")
            for r in RW.head(15).itertuples():
                gate = " ".join("PASS" if r.usd >= g_ else "fail"
                                for g_ in GATES)
                log(f"| {r.key} | {r.ntr:,}/{r.nho:,} | {r.tr:+.2f} | "
                    f"{r.t:+.1f} | {r.ho:+.2f} +/- {r.hose:.2f} | "
                    f"{r.agree}/{r.nvote} | "
                    f"{'' if np.isnan(r.nbhd) else format(r.nbhd,'.0%')} | "
                    f"${r.usd:.2f} | {gate} |")
            log()
            # shuffled-outcome control: same screen on permuted outcomes
            rng = np.random.default_rng(5)
            D["_shuf"] = rng.permutation(D[f"fwd{F}"].values)
            sh = 0
            for k, grp in D.groupby(key, observed=True):
                t_ = grp[grp.train]
                if len(t_) < MIN_TR or len(grp[~grp.train]) < MIN_HO:
                    continue
                yt = t_["_shuf"].values - D.loc[D.train, "_shuf"].mean()
                if abs(yt.mean() / max(yt.std() / np.sqrt(len(yt)), 1e-9)) >= 3:
                    sh += 1
            log(f"Shuffled control: **{sh} cells** pass the same screen on "
                f"permuted outcomes (the false-positive floor).")
            log()
        del D

    log("---")
    log(f"Gates: ${GATES[0]:.2f} commission-only and ${GATES[1]:.2f} with the "
        f"$3 slippage figure, against the FULL gross cell mean at "
        f"$0.50/tick. 'vote' is contracts agreeing with the train sign, out "
        f"of sample. Cells are judged against the event-population baseline "
        f"at their horizon, never against zero.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    suffix = "_SYNTH" if SYNTH else ""
    open(OUT.replace(".md", suffix + ".md"), "w").write("\n".join(LINES) + "\n")
    print("\nwrote", OUT.replace(".md", suffix + ".md"))


if __name__ == "__main__":
    main()

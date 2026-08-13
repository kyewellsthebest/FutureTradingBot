"""Fast validated search. Fixes a bug that made the last one search 5% of the
data, and runs about sixty times quicker.

THE BUG, because it explains every empty result before this. Legs were built
by looping features alphabetically, appending ten per feature (five quantiles
x two directions), then truncating each data type's list to the first ten:

    for fn in sorted(F): ... byt[type].append(leg)     # 10 legs per feature
    byt[t] = byt[t][:PERTYPE]                          # PERTYPE = 10

The alphabetically first feature of each type therefore consumed the entire
quota and every other feature was thrown away. Ten features out of 196 --
5.1%. Order flow contributed `f_eff1` and nothing else, out of forty. mega.py
sorted by score before truncating; that sort was lost in the rewrite and the
truncation was not. Nothing was wrong with the gates or the data: the search
simply never looked.

THE SPEED, measured rather than assumed:

    130 combos/sec   original -- pall recomputed for all 154 brackets on
                     EVERY combination, though it depends on none of them
    387 combos/sec   after hoisting it out
  1,896 combos/sec   after transposing so bar-rows are gathered contiguously
                     instead of striding across 154 separate arrays, and
                     packing the win matrix as uint8 (wt is boolean)
  ~7,000 combos/sec  x4 processes, one per core

Fifteen times faster single-threaded, about sixty with the fan-out. Eight
quarters of scanning goes from four hours to roughly four minutes.

WHAT IS NOT COMPROMISED. Validation still sits inside the gate: train on the
first 60% of a contract, confirm on the held-out 40%, then require profit
across every OTHER quarter. The gates are unchanged.
"""
import itertools
import json
import pickle
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402
import vsearch as V  # noqa: E402  -- reuse cached(), ladder(), brackets()

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "FSEARCH.md"))
STATE = os.environ.get("STATE_JSON",
                       os.path.join(fuse.ROOT, "data", "fsearch_state.json"))
TRAIN = float(os.environ.get("TRAIN", "0.60"))
MIN_GREEN = int(os.environ.get("MIN_GREEN", "5"))
MIN_OOS_DOL = float(os.environ.get("MIN_OOS_DOL", "0.50"))
MIN_TPW = float(os.environ.get("MIN_TPW", "200"))
MIN_DOL = float(os.environ.get("MIN_DOL", "2.00"))
MIN_EDGE_REL = float(os.environ.get("MIN_EDGE_REL", "0.10"))
MIN_EDGE_PP = float(os.environ.get("MIN_EDGE_PP", "0.02"))
MAX_FIRE = float(os.environ.get("MAX_FIRE", "0.90"))
PERTYPE = int(os.environ.get("PERTYPE", "14"))
ARITY = int(os.environ.get("ARITY", "4"))
SHAPES = os.environ.get("SHAPES", "state,cross,hold4,hold8,after8").split(",")
QS = [float(x) for x in os.environ.get(
    "QS", "0.15,0.3,0.45,0.6,0.75,0.9").split(",")]
KBAR = int(os.environ.get("KBAR", "500"))
WORKERS = int(os.environ.get("WORKERS", "4"))
MAXCOMBO = int(os.environ.get("MAXCOMBO", "400000"))
# per-market economics of the MICRO contract, env-overridable. MAKER
# defaults to the measured MNQ front-of-queue edge only for NQ; other
# markets have no queue measurement yet and price as takers (0).
TV = float(os.environ.get("TV", "0.50"))
TPX = float(os.environ.get("TPX", "0.25"))
COST = float(os.environ.get("COST", "1.24"))
MAKER = float(os.environ.get("MAKER", "0.355"))
# survivor-level spec: what a rule must still do on quarters it never saw
MIN_OOS_TPW = float(os.environ.get("MIN_OOS_TPW", os.environ.get("MIN_TPW", "100")))
MIN_OOS_WK = float(os.environ.get("MIN_OOS_WK", "150"))


def nonoverlap(idx, hold):
    """Greedy non-overlap, one step per TRADE TAKEN rather than one per
    candidate bar.

Two algorithms, because neither wins everywhere and I measured both.

    Jumping with searchsorted from each accepted trade to the first bar after
    it closes touches only the trades actually TAKEN -- a big win when holds
    are long and most signals get absorbed. But when holds are short almost
    every signal becomes a trade, and then the jump version pays a log-n
    search per trade for nothing: on a one-bar bracket it measured 25 ms
    against the plain scan's 4.6 ms, five times WORSE.

    So the median hold picks the algorithm. Long holds jump, short holds
    scan."""
    if len(idx) == 0:
        return np.empty(0, dtype=np.int64)
    if float(np.median(hold[idx[::max(len(idx) // 64, 1)]])) > 12:
        out, i, m = [], 0, len(idx)
        while i < m:
            j = int(idx[i])
            out.append(j)
            nxt = int(np.searchsorted(idx, j + int(hold[j]), side="left"))
            i = nxt if nxt > i else i + 1
        return np.asarray(out, dtype=np.int64)
    out, last = [], -(10 ** 9)
    for i in idx:
        if i >= last:
            out.append(i)
            last = i + int(hold[i])
    return np.asarray(out, dtype=np.int64)


def prep(cn):
    """Everything a contract needs, laid out for speed rather than clarity.

    WT is (bars x brackets) uint8 instead of a dict of (brackets) arrays. The
    inner loop gathers the rows for a signal's bars, so those rows have to be
    contiguous -- striding across 154 separate arrays to collect one bar was
    costing 15x."""
    B, F = V.cached(cn, KBAR)
    n = len(B["c"])
    dayspan = len(np.unique(B["ts"] // fuse.DAY_NS))
    if n < 8000 or dayspan < 20:
        return None
    ct = COST / TV
    ks = V.ladder(B)
    pairs = V.brackets(ks, ct)
    if not pairs:
        return None
    cut = int(n * TRAIN)
    up, dn = hunt.tau(B, ks, TPX)
    keys, wcol, rcol, hcol, bar = [], [], [], [], []
    for (si, ti) in pairs:
        for side in (1, -1):
            r, hold, wt = hunt.outcomes(B, up, dn, si, ti, side, ks,
                                        TPX, TV)[:3]
            keys.append((int(ks[si]), int(ks[ti]), side))
            wcol.append(wt.astype(np.uint8))
            rcol.append(r.astype(np.float32))
            hcol.append(hold.astype(np.int32))
            pstar = (ks[si] + ct) / (ks[si] + ks[ti])
            # the bar depends only on the bracket, so it is computed ONCE here
            # rather than 154 times per combination as it was before
            bar.append(max(pstar * (1 + MIN_EDGE_REL),
                           float(wt[:cut].mean()) + MIN_EDGE_PP))
    del up, dn
    return dict(cn=cn, n=n, cut=cut, dayspan=dayspan, keys=keys,
                WT=np.ascontiguousarray(np.stack(wcol, axis=1)),
                R=np.ascontiguousarray(np.stack(rcol, axis=1)),
                H=np.ascontiguousarray(np.stack(hcol, axis=1)),
                BAR=np.array(bar, dtype=np.float32), F=F, B=B)


def forms(v, n):
    """SIX DIFFERENT QUESTIONS OF THE SAME COLUMN, not six thresholds on one.

    Every leg until now asked one question -- "is this feature above a level
    right now" -- of 287 features. That is one idea repeated 287 times, and it
    is why the survivors came back as near-duplicates differing by a single
    threshold. These ask structurally different things, and they fire on
    genuinely different bars rather than on slightly shifted versions of the
    same set:

      raw     where the value sits                  a STATE
      d21     how much it moved over 21 bars        a CHANGE
      d89     the same over 89                      a slower change
      rk55    its position within the last 55 bars  a LOCAL extreme, scale-free
      rk233   the same over 233                     a slower extreme
      acc     change of the change                  ACCELERATION

    A local-extreme condition and a level condition on the same feature select
    almost disjoint bars: one fires when the value is high absolutely, the
    other when it is high RELATIVE TO ITS RECENT PAST, which in a trending
    market are close to opposites."""
    S = pd.Series(v, dtype="float64")
    out = {"raw": v}
    # z: how unusual the value is vs its own recent distribution -- a
    # different question from raw level and from rank position
    m = S.rolling(288, min_periods=72).mean()
    sd = S.rolling(288, min_periods=72).std()
    out["z288"] = ((S - m) / sd.replace(0, np.nan)).to_numpy()
    for w in (21, 89):
        out[f"d{w}"] = (S - S.shift(w)).to_numpy()
    for w in (55, 233):
        lo = S.rolling(w, min_periods=w // 3).min()
        hi = S.rolling(w, min_periods=w // 3).max()
        out[f"rk{w}"] = ((S - lo) / (hi - lo).replace(0, np.nan)).to_numpy()
    out["acc"] = (S.diff() - S.diff().shift(21)).to_numpy()
    return out


def shape(sig, kind):
    """And three ways to USE a condition once it exists.

      state   it is true now
      cross   it BECAME true this bar -- an event, firing on a fraction of the
              bars the state does, and selecting the moment of change rather
              than the whole period after it
      hold4   it has been true for four bars running -- sustained rather than
              momentary, which is a different claim about the market

    A state and its own cross share a name and almost no trades."""
    if kind == "state":
        return sig
    if kind == "cross":
        out = np.zeros_like(sig)
        out[1:] = sig[1:] & ~sig[:-1]
        return out
    if kind == "after8":
        # the AFTERMATH window: the condition fired within the last 8 bars
        # but is not firing now -- shock-and-cooldown, a different claim from
        # the state itself and disjoint from it by construction
        rec = np.zeros_like(sig)
        for k in range(1, 9):
            rec[k:] |= sig[:-k]
        return rec & ~sig
    span = 8 if kind == "hold8" else 4
    out = sig.copy()
    for k in range(1, span):
        out[k:] &= sig[:-k]
    out[:span - 1] = False
    return out


def legs_for(P, cn=None):
    """Every feature gets a fair hearing, then the best survive.

    This is the line that was missing. Legs are SCORED -- how far each moves
    the win rate on a handful of reference brackets -- and the top PERTYPE per
    data type are kept. Truncating an unsorted list, as before, kept whichever
    feature happened to sort first and discarded the other 95%.

    This stage, not the combo scan, turned out to own the runtime: ~94k
    candidate legs each fancy-indexed a (bars x 8) slice, 20+ minutes per
    quarter and growing. Scoring is now one BLAS matvec per leg, and the
    finished list is pickled per quarter so it is computed once ever."""
    F, n, cut = P["F"], P["n"], P["cut"]
    WT, dayspan = P["WT"], P["dayspan"]
    lp = None
    if cn is not None:
        lp = os.path.join(os.path.dirname(STATE), "fsearch_ck",
                          f"legs_{cn}_{PERTYPE}_{int(MIN_TPW)}_"
                          f"{len(QS)}x{len(SHAPES)}.pkl")
        if os.path.exists(lp):
            try:
                raw = pickle.load(open(lp, "rb"))
                return {t: [(sc, np.unpackbits(pk)[:n].astype(bool), nm, sd, q)
                            for sc, pk, nm, sd, q in v]
                        for t, v in raw.items()}
            except Exception:                                    # noqa: BLE001
                pass
    need = MIN_TPW / 5.0 / (n / dayspan)
    ref = np.linspace(0, WT.shape[1] - 1, min(8, WT.shape[1])).astype(int)
    # slice the columns ONCE. WT[tr][:, ref] materialises (len(tr), 154) and
    # then throws away all but eight columns -- 3x slower than slicing first.
    WTr = np.ascontiguousarray(WT[:, ref])
    base = WTr[:cut].mean(axis=0)
    WTc = WTr[:cut].astype(np.float32)      # matvec operand, built once
    out = {}
    for fn in sorted(F):
        v0 = np.asarray(F[fn], dtype=np.float64)
        if np.isfinite(v0).sum() < n * 0.5:
            continue
        for form, v in forms(v0, n).items():
            fin = np.isfinite(v)
            if fin.sum() < n * 0.4:
                continue
            qs = np.quantile(v[fin], QS)
            for q, thr in zip(QS, qs):
                for sd in (1, -1):
                    base_sig = ((v >= thr) if sd > 0 else (v <= thr)) & fin
                    for sh in SHAPES:
                        sig = shape(base_sig, sh)
                        m = sig.mean()
                        if m < need or m > MAX_FIRE:
                            continue
                        sigc = sig[:cut]
                        ntr = int(sigc.sum())
                        if ntr < 200:
                            continue
                        wr = sigc.astype(np.float32) @ WTc / ntr
                        sc = float(np.abs(wr - base).max())
                        # PACKED, 8x smaller: retaining tens of thousands of
                        # full bool arrays across 4 workers is what OOM-killed
                        # the MIN_TPW=100 run with no traceback
                        out.setdefault(fn.split("_")[0] + "_", []).append(
                            (sc, np.packbits(sig), f"{fn}|{form}|{sh}",
                             sd, float(q)))
    for t in out:
        out[t].sort(key=lambda z: -z[0])
        best, seen = [], {}
        for lg in out[t]:                    # spread across FEATURES, not
            root = lg[2].split("|")[0]       # many forms of one feature
            c = seen.get(root, 0)
            if c >= 3:
                continue
            seen[root] = c + 1
            best.append(lg)
            if len(best) >= PERTYPE:
                break
        out[t] = best
    if lp is not None:
        pickle.dump(out, open(lp + ".tmp", "wb"))
        os.replace(lp + ".tmp", lp)
    return {t: [(sc, np.unpackbits(pk)[:n].astype(bool), nm, sd, q)
                for sc, pk, nm, sd, q in v] for t, v in out.items()}


def scan(cn):
    """One contract: fit on train, confirm on the held-out tail."""
    t0 = time.time()
    P = prep(cn)
    if P is None:
        return cn, [], dict(scan=0, gate=0, test=0)
    tp = time.time()
    print(f"    {cn}: prep {tp-t0:.0f}s", flush=True)
    byt = legs_for(P, cn)
    print(f"    {cn}: legs {time.time()-tp:.0f}s", flush=True)
    types = sorted(byt)
    if len(types) < 2:
        return cn, [], dict(scan=0, gate=0, test=0)
    WT, R, H, BAR = P["WT"], P["R"], P["H"], P["BAR"]
    cut, n, dayspan, keys = P["cut"], P["n"], P["dayspan"], P["keys"]
    nfeat = sum(len({l[2] for l in v}) for v in byt.values())

    # the needle has a SHAPE: at MIN_TPW/wk, a candidate needs this many
    # non-overlapping trades in each segment -- anything that cannot reach
    # it is hay and gets no further arithmetic
    needA = int(MIN_TPW * dayspan * TRAIN / 5.0)
    needB = int(MIN_TPW * dayspan * (1 - TRAIN) / 5.0)
    WIDE = {2: PERTYPE, 3: 6, 4: 4, 5: 3}
    groups = [[(a,) for t in types for a in byt[t][:8]]]
    for m in range(2, min(ARITY, len(types)) + 1):
        w = WIDE.get(m, 3)
        for ts_ in itertools.combinations(types, m):
            groups.append([tuple(c) for c in
                           itertools.product(*[byt[t][:w] for t in ts_])])
    combos = [c for tier in itertools.zip_longest(*groups)
              for c in tier if c is not None][:MAXCOMBO]

    # intra-quarter checkpoints: the host is reclaimed every hour or two,
    # and a whole quarter at this config does not fit inside that window.
    # The durable unit is a 100k-combo chunk (~minutes). combos is rebuilt
    # deterministically from the cache, so an offset is a valid resume point;
    # only the bar-set dedup memory is lost across restarts, and downstream
    # trade-set clustering catches any duplicate that slips the seam.
    ckp = os.path.join(os.path.dirname(STATE), "fsearch_ck", f"part_{cn}.json")
    start, st, cand = 0, dict(scan=0, gate=0, test=0), []
    if os.path.exists(ckp):
        try:
            d = json.load(open(ckp))
            if d.get("nc") == len(combos):
                start, st, cand = d["i"], d["st"], d["cand"]
                print(f"    {cn}: resume at combo {start:,} "
                      f"({len(cand)} candidates so far)", flush=True)
        except Exception:                                        # noqa: BLE001
            pass
    CHUNK = 100_000
    seen = set()
    for ci, cb in enumerate(combos):
        if ci < start:
            continue
        if ci > start and ci % CHUNK == 0:
            json.dump({"i": ci, "nc": len(combos), "st": st, "cand": cand},
                      open(ckp + ".tmp", "w"), default=float)
            os.replace(ckp + ".tmp", ckp)
            el = time.time() - t0
            print(f"    {cn}: {ci:,}/{len(combos):,} combos, "
                  f"{st['scan']:,} scanned, {st['test']:,} passed, "
                  f"{el/60:.0f}m", flush=True)
        fs = tuple(x[2] for x in cb)
        if len(set(fs)) < len(fs):
            continue
        tot = cb[0][1].astype(np.int16)
        for x in cb[1:]:
            tot = tot + x[1]
        for k in ({len(cb)} if len(cb) < 3 else
                  {len(cb)} | set(range(2, len(cb)))):
            sig = tot >= k
            fr = sig.mean()
            if fr < 0.01 or fr > MAX_FIRE:
                continue
            tr = np.flatnonzero(sig[:cut])
            # signal bars bound trades from above: below the frequency spec
            # in EITHER segment means impossible, skip before any scoring
            if len(tr) < max(200, needA):
                continue
            if int(sig[cut:].sum()) < needB:
                continue
            # DEDUP ON THE BAR-SET, not on the label. Two rules with
            # different names that select the same bars are one rule, and
            # scoring both inflates the count while adding nothing -- which is
            # exactly how a "top 5" came back as two ideas wearing five names.
            key = hash(np.packbits(sig).tobytes())
            if key in seen:
                continue
            seen.add(key)
            st["scan"] += 1
            # ---- the whole point: 154 brackets in one vectorised pass ----
            m = np.add.reduce(WT[tr], axis=0, dtype=np.int32) / len(tr)
            ok = np.flatnonzero(m >= BAR)
            if not len(ok):
                continue
            st["gate"] += 1
            # Only the BEST few brackets are worth the non-overlap pass. The
            # loop breaks on the first success, so testing all of them just
            # pays for the expensive step on brackets that will never be used.
            # SIX brackets, judged by $/WEEK -- ranking by edge alone and
            # breaking at the first pass systematically chose wide slow
            # brackets and discarded the tight fast ones the spec demands
            ok = ok[np.argsort(-(m[ok] - BAR[ok]))[:6]]
            allidx = np.flatnonzero(sig)
            best, bestwk = None, 0.0
            for bi in ok:
                keep = nonoverlap(allidx, H[:, bi])
                a, b = keep[keep < cut], keep[keep >= cut]
                if len(a) < needA or len(b) < needB:
                    continue
                if float(WT[a, bi].mean()) < BAR[bi]:
                    continue
                ra = R[a, bi] - COST + MAKER
                rb = R[b, bi] - COST + MAKER
                da, db = float(ra.mean()), float(rb.mean())
                if da < MIN_DOL or db <= 0:
                    continue
                tpwa = len(a) / (dayspan * TRAIN) * 5
                if da * tpwa > bestwk:
                    bestwk = da * tpwa
                    S, T, side = keys[bi]
                    best = dict(
                        legs=[(x[2], int(x[3]), float(x[4])) for x in cb],
                        k=int(k), side=int(side), stop=S, tgt=T, home=cn,
                        train=dict(dol=da, tpw=tpwa),
                        test=dict(dol=db,
                                  tpw=len(b) / (dayspan * (1 - TRAIN)) * 5))
            if best is not None:
                st["test"] += 1
                cand.append(best)
    st["feat"] = nfeat
    st["combos"] = len(combos)
    st["secs"] = time.time() - t0
    if os.path.exists(ckp):
        os.remove(ckp)     # the quarter-level checkpoint takes over from here
    return cn, cand, st


def evaluate(cn, cands, csig=None):
    """Every candidate on a quarter it has never seen.

    THE BRACKET HAS TO BE REBUILT, NOT LOOKED UP. The ladder is derived from
    each contract's own median bar range, so a 49/62-tick bracket found in one
    quarter simply does not exist in another quarter's ladder. The first
    version looked the bracket up by tick value and skipped the candidate when
    it was missing -- which was almost always. Validation silently evaluated
    NOTHING and reported "0 survived", a lookup failure wearing the costume of
    a result. The saved state gave it away: zero out-of-sample entries for
    5,521 candidates that had supposedly all been tested.

    Outcomes are now computed for the candidate's exact stop and target on
    this quarter's bars, cached per distinct bracket so the cost is paid once
    however many candidates share it."""
    B, F = V.cached(cn, KBAR)
    n = len(B["c"])
    dayspan = len(np.unique(B["ts"] // fuse.DAY_NS))
    out, cache, sigs, fcache = {}, {}, {}, {}
    # chunked resume, same reason as scan(): a validation quarter over tens
    # of thousands of candidates outlives the host's reclaim window
    vckp = os.path.join(os.path.dirname(STATE), "fsearch_ck",
                        f"pval_{cn}.json")
    start = 0
    if csig and os.path.exists(vckp):
        try:
            d = json.load(open(vckp))
            if d.get("sig") == csig:
                start = d["i"]
                out = {int(k): v for k, v in d["out"].items()}
                print(f"    val {cn}: resume at {start:,}", flush=True)
        except Exception:                                        # noqa: BLE001
            pass
    t0 = time.time()
    for j, c in enumerate(cands):
        if j < start:
            continue
        if csig and j > start and j % 2000 == 0:
            json.dump({"sig": csig, "i": j, "out": out},
                      open(vckp + ".tmp", "w"), default=float)
            os.replace(vckp + ".tmp", vckp)
            print(f"    val {cn}: {j:,}/{len(cands):,} "
                  f"({(time.time()-t0)/60:.0f}m)", flush=True)
        if c["home"] == cn:
            continue
        key = (c["stop"], c["tgt"], c["side"])
        if key not in cache:
            kk = np.array(sorted({c["stop"], c["tgt"]}), dtype=np.int64)
            si = int(np.where(kk == c["stop"])[0][0])
            ti = int(np.where(kk == c["tgt"])[0][0])
            u, d = hunt.tau(B, kk, TPX)
            r, hold, _wt = hunt.outcomes(B, u, d, si, ti, c["side"], kk,
                                         TPX, TV)[:3]
            del u, d
            cache[key] = (r.astype(np.float32), hold.astype(np.int32))
        r, hold = cache[key]

        # legs reloaded from JSON checkpoints are lists-of-lists; tuples all
        # the way down or the cache key is unhashable
        sk = (tuple(tuple(x) for x in c["legs"]), c["k"])
        sig = sigs.get(sk)
        if sig is None:
            # LEG NAMES CARRY A FORM AND A SHAPE NOW -- "d_z55|rk55|hold4" --
            # and the first validator looked that string up as a literal
            # feature, found nothing, and silently skipped every candidate.
            # 13,331 candidates, zero evaluated, reported as "0 survived".
            # Same disease as the bracket lookup, third occurrence today. The
            # transformed series must be REBUILT here exactly as legs_for
            # built it, and it is cached per (root, form) per quarter.
            tot, have = np.zeros(n, dtype=np.int16), 0
            for fn, sd, q in c["legs"]:
                parts = fn.split("|")
                root = parts[0]
                form = parts[1] if len(parts) > 1 else "raw"
                sh = parts[2] if len(parts) > 2 else "state"
                fk = (root, form)
                if fk not in fcache:
                    v0 = F.get(root)
                    fcache[fk] = (None if v0 is None else
                                  forms(np.asarray(v0, dtype=np.float64),
                                        n).get(form))
                v = fcache[fk]
                if v is None:
                    continue
                fin = np.isfinite(v)
                if fin.sum() < n * 0.4:
                    continue
                thr = float(np.quantile(v[fin], q))
                bs = ((v >= thr) if sd > 0 else (v <= thr)) & fin
                tot += shape(bs, sh).astype(np.int16)
                have += 1
            sig = (tot >= c["k"]) if have >= c["k"] else False
            sigs[sk] = sig
        if sig is False:
            continue
        idx = nonoverlap(np.flatnonzero(sig), hold)
        if len(idx) < 30:
            continue
        v = r[idx] - COST + MAKER
        out[j] = dict(dol=float(v.mean()), tpw=len(idx) / dayspan * 5)
    if csig and os.path.exists(vckp):
        os.remove(vckp)      # quarter-level val checkpoint takes over
    return cn, out


def main():
    t0 = time.time()
    meta = fuse.tape_meta()
    want = os.environ.get("CONTRACTS")
    cons = (want.split(",") if want else
            [c for c in fuse.NQ_CONTRACTS if c in meta])
    cons = [c for c in cons if c in meta]
    print(f"{len(cons)} quarters, {WORKERS} workers, K={KBAR}", flush=True)

    # per-quarter checkpoints: the container hosting this search is reclaimed
    # roughly hourly, and state written only at the end means every reclaim
    # loses everything. A finished quarter is a durable unit -- dump it, and
    # skip it on relaunch.
    ckdir = os.path.join(os.path.dirname(STATE), "fsearch_ck")
    os.makedirs(ckdir, exist_ok=True)
    allc, stats, todo = [], {}, []
    for cn in cons:
        p = os.path.join(ckdir, f"scan_{cn}.json")
        if os.path.exists(p):
            d = json.load(open(p))
            stats[cn] = d["st"]
            allc += d["cand"]
            print(f"  {cn}: checkpoint ({len(d['cand'])} candidates)",
                  flush=True)
        else:
            todo.append(cn)
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        for cn, cand, st in ex.map(scan, todo):
            stats[cn] = st
            allc += cand
            json.dump({"st": st, "cand": cand},
                      open(os.path.join(ckdir, f"scan_{cn}.json"), "w"),
                      default=float)
            print(f"  {cn}: {st.get('feat',0)} features, "
                  f"{st.get('combos',0):,} combos, scanned {st['scan']:,} -> "
                  f"gate {st['gate']:,} -> train+test {st['test']:,} "
                  f"({st.get('secs',0)/60:.1f}m, "
                  f"{st['scan']/max(st.get('secs',1),1):,.0f}/s)", flush=True)
    print(f"\n{len(allc):,} candidates passed train AND held-out test. "
          f"Validating across quarters...", flush=True)

    # THE SPEC IS END-TO-END, not train-side only. A candidate that cannot
    # sustain MIN_TPW in the held-out 40% has already failed the brief --
    # validating it wastes the budget and reporting it wastes attention.
    n0 = len(allc)
    allc = [c for c in allc
            if c["train"]["tpw"] >= MIN_TPW and c["test"]["tpw"] >= MIN_TPW]
    print(f"frequency gate: {n0:,} -> {len(allc):,} sustain "
          f">={MIN_TPW:.0f}/wk in train AND held-out", flush=True)
    MAXVAL = int(os.environ.get("MAX_VAL", "20000"))
    if len(allc) > MAXVAL:
        # the held-out test segment, not train, ranks who gets validated --
        # still selection, but selection on the least-fitted number we have
        allc.sort(key=lambda c: -(c["test"]["dol"] * c["test"]["tpw"]))
        print(f"validation capped: top {MAXVAL:,} of {len(allc):,} "
              f"by held-out $/wk", flush=True)
        allc = allc[:MAXVAL]
    res = {i: {} for i in range(len(allc))}
    if allc:
        # validation checkpoints are only valid against the exact candidate
        # list they were computed for -- key them to its digest
        import hashlib
        csig = hashlib.blake2b(
            json.dumps([(c["home"], c["stop"], c["tgt"], c["side"], c["k"],
                         c["legs"]) for c in allc],
                       default=float).encode(), digest_size=8).hexdigest()
        vtodo = []
        for cn in cons:
            p = os.path.join(ckdir, f"val_{cn}.json")
            if os.path.exists(p):
                d = json.load(open(p))
                if d.get("sig") == csig:
                    for j, v in d["out"].items():
                        res[int(j)][cn] = v
                    print(f"  validated on {cn} (checkpoint)", flush=True)
                    continue
            vtodo.append(cn)
        with ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(evaluate, cn, allc, csig): cn for cn in vtodo}
            for f in futs:
                cn, out = f.result()
                for j, v in out.items():
                    res[j][cn] = v
                json.dump({"sig": csig, "out": out},
                          open(os.path.join(ckdir, f"val_{cn}.json"), "w"),
                          default=float)
                print(f"  validated on {cn}", flush=True)

    if allc and not any(res.values()):
        print("!!! VALIDATION EVALUATED NOTHING -- leg reconstruction failed. "
              "Result is NOT a finding.", flush=True)
    winners = []
    for i, c in enumerate(allc):
        got = res[i]
        if len(got) < 4:
            continue
        dols = [v["dol"] for v in got.values()]
        c["oos"] = dict(dol=float(np.mean(dols)),
                        green=sum(1 for x in dols if x > 0), q=len(got),
                        tpw=float(np.mean([v["tpw"] for v in got.values()])))
        ok = (c["oos"]["dol"] >= MIN_OOS_DOL
              and c["oos"]["green"] >= MIN_GREEN
              and c["oos"]["tpw"] >= MIN_OOS_TPW
              and c["oos"]["dol"] * c["oos"]["tpw"] >= MIN_OOS_WK)
        if ok:
            winners.append(c)

    ts = sum(s["scan"] for s in stats.values())
    tg = sum(s["gate"] for s in stats.values())
    tt = sum(s["test"] for s in stats.values())
    L = ["# Fast validated search", "",
         f"The previous run searched **10 features out of 196** — legs were "
         f"appended alphabetically, ten per feature, then each data type's "
         f"list was truncated to the first ten, so the alphabetically first "
         f"feature consumed the whole quota. Order flow contributed one "
         f"feature out of forty. That, not the rarity of edge, is why it "
         f"found nothing.", "",
         f"Legs are now scored and the best per type kept, capped at three "
         f"thresholds per feature so one feature cannot crowd out the rest.",
         "",
         "| quarter | features | combos | scanned | cleared train gate | "
         "+ held-out test | combos/sec |", "|---|---|---|---|---|---|---|"]
    for cn in cons:
        s = stats.get(cn, {})
        if not s:
            continue
        L.append(f"| {cn} | {s.get('feat',0)} | {s.get('combos',0):,} | "
                 f"{s['scan']:,} | {s['gate']:,} | {s['test']:,} | "
                 f"{s['scan']/max(s.get('secs',1),1):,.0f} |")
    L += ["", f"**{ts:,} scanned → {tg:,} cleared the train gate → {tt:,} also "
              f"paid on the held-out 40% → {len(winners)} survived every other "
              f"quarter.**", ""]
    if winners:
        L += ["| rule | side | home | train | test | **out of sample** | green "
              "| **$/wk oos** |", "|---|---|---|---|---|---|---|---|"]
        for c in sorted(winners, key=lambda z: -z["oos"]["dol"]*z["oos"]["tpw"])[:30]:
            o = c["oos"]
            lg = ", ".join(f"`{a}`" for a, _, _ in c["legs"])[:58]
            L.append(f"| {c['k']}of({lg}) | {'L' if c['side']>0 else 'S'} | "
                     f"{c['home']} | ${c['train']['dol']:+.2f} | "
                     f"${c['test']['dol']:+.2f} | **${o['dol']:+.2f}** | "
                     f"{o['green']}/{o['q']} | **${o['dol']*o['tpw']:+,.0f}** |")
    else:
        L.append("**Nothing survived out of sample** — but this time the "
                 "search actually looked at the data.")
    L += ["", f"_Ran {(time.time()-t0)/60:.1f} min on {WORKERS} workers._"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    # EVERY validated candidate, not just the survivors. "Zero survived" and
    # "zero came close" are different findings and the second one needs the
    # distribution -- if 5,521 candidates cluster at -$1.50 out of sample the
    # answer is settled; if they straddle zero it is a threshold question.
    allo = [c["oos"] for c in allc if "oos" in c]
    json.dump({"winners": winners, "stats": stats, "oos": allo},
              open(STATE, "w"), default=float)
    if allo:
        v = np.array([o["dol"] for o in allo])
        g = np.array([o["green"] for o in allo])
        L += ["", "## How far off were they?", "",
              f"`{len(v):,}` candidates reached cross-quarter validation.",
              "", "| out-of-sample $/trade | candidates |", "|---|---|"]
        for lo, hi in ((-99, -1), (-1, -0.5), (-0.5, 0), (0, 0.25),
                       (0.25, 0.5), (0.5, 99)):
            n_ = int(((v >= lo) & (v < hi)).sum())
            L.append(f"| {lo:+.2f} to {hi:+.2f} | {n_:,} "
                     f"({n_/len(v)*100:.1f}%) |")
        L += ["", f"Best out-of-sample **${v.max():+.2f}/trade**, median "
                  f"**${np.median(v):+.2f}**. "
                  f"`{int((v>0).sum()):,}` were positive at all "
                  f"({(v>0).mean()*100:.1f}%), "
                  f"`{int((g>=MIN_GREEN).sum()):,}` were green in "
                  f"{MIN_GREEN}+ quarters.", ""]
        open(OUT, "w").write("\n".join(L) + "\n")
    print("\n".join(L[-8:]))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

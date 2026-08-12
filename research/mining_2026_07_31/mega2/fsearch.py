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
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

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
QS = [float(x) for x in os.environ.get(
    "QS", "0.15,0.3,0.45,0.6,0.75,0.9").split(",")]
KBAR = int(os.environ.get("KBAR", "500"))
WORKERS = int(os.environ.get("WORKERS", "4"))
MAXCOMBO = int(os.environ.get("MAXCOMBO", "400000"))
TV, TPX, COST, MAKER = 0.50, 0.25, 1.24, 0.355


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


def legs_for(P):
    """Every feature gets a fair hearing, then the best survive.

    This is the line that was missing. Legs are SCORED -- how far each moves
    the win rate on a handful of reference brackets -- and the top PERTYPE per
    data type are kept. Truncating an unsorted list, as before, kept whichever
    feature happened to sort first and discarded the other 95%."""
    F, n, cut = P["F"], P["n"], P["cut"]
    WT, dayspan = P["WT"], P["dayspan"]
    need = MIN_TPW / 5.0 / (n / dayspan)
    ref = np.linspace(0, WT.shape[1] - 1, min(8, WT.shape[1])).astype(int)
    # slice the columns ONCE. WT[tr][:, ref] materialises (len(tr), 154) and
    # then throws away all but eight columns -- 3x slower than slicing first.
    WTr = np.ascontiguousarray(WT[:, ref])
    base = WTr[:cut].mean(axis=0)
    out = {}
    for fn in sorted(F):
        v = np.asarray(F[fn], dtype=np.float32)
        fin = np.isfinite(v)
        if fin.sum() < n * 0.5:
            continue
        qs = np.quantile(v[fin], QS)
        for q, thr in zip(QS, qs):
            for sd in (1, -1):
                sig = ((v >= thr) if sd > 0 else (v <= thr)) & fin
                m = sig.mean()
                if m < need or m > MAX_FIRE:
                    continue
                tr = np.flatnonzero(sig[:cut])
                if len(tr) < 200:
                    continue
                sc = float(np.abs(WTr[tr].mean(axis=0) - base).max())
                out.setdefault(fn.split("_")[0] + "_", []).append(
                    (sc, sig, fn, sd, float(q)))
    for t in out:
        out[t].sort(key=lambda z: -z[0])
        best, seen = [], {}
        for lg in out[t]:                    # spread across FEATURES, not
            c = seen.get(lg[2], 0)           # three thresholds of one feature
            if c >= 3:
                continue
            seen[lg[2]] = c + 1
            best.append(lg)
            if len(best) >= PERTYPE:
                break
        out[t] = best
    return out


def scan(cn):
    """One contract: fit on train, confirm on the held-out tail."""
    t0 = time.time()
    P = prep(cn)
    if P is None:
        return cn, [], dict(scan=0, gate=0, test=0)
    byt = legs_for(P)
    types = sorted(byt)
    if len(types) < 2:
        return cn, [], dict(scan=0, gate=0, test=0)
    WT, R, H, BAR = P["WT"], P["R"], P["H"], P["BAR"]
    cut, n, dayspan, keys = P["cut"], P["n"], P["dayspan"], P["keys"]
    nfeat = sum(len({l[2] for l in v}) for v in byt.values())

    WIDE = {2: PERTYPE, 3: 6, 4: 4, 5: 3}
    groups = [[(a,) for t in types for a in byt[t][:8]]]
    for m in range(2, min(ARITY, len(types)) + 1):
        w = WIDE.get(m, 3)
        for ts_ in itertools.combinations(types, m):
            groups.append([tuple(c) for c in
                           itertools.product(*[byt[t][:w] for t in ts_])])
    combos = [c for tier in itertools.zip_longest(*groups)
              for c in tier if c is not None][:MAXCOMBO]

    st = dict(scan=0, gate=0, test=0)
    cand, seen = [], set()
    for cb in combos:
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
            if len(tr) < 200:
                continue
            key = (fs, k)
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
            ok = ok[np.argsort(-(m[ok] - BAR[ok]))[:3]]
            allidx = np.flatnonzero(sig)
            for bi in ok:
                keep = nonoverlap(allidx, H[:, bi])
                a, b = keep[keep < cut], keep[keep >= cut]
                if len(a) < 100 or len(b) < 60:
                    continue
                if float(WT[a, bi].mean()) < BAR[bi]:
                    continue
                ra = R[a, bi] - COST + MAKER
                rb = R[b, bi] - COST + MAKER
                da, db = float(ra.mean()), float(rb.mean())
                if da < MIN_DOL or db <= 0:
                    continue
                st["test"] += 1
                S, T, side = keys[bi]
                cand.append(dict(
                    legs=[(x[2], int(x[3]), float(x[4])) for x in cb],
                    k=int(k), side=int(side), stop=S, tgt=T, home=cn,
                    train=dict(dol=da, tpw=len(a) / (dayspan * TRAIN) * 5),
                    test=dict(dol=db,
                              tpw=len(b) / (dayspan * (1 - TRAIN)) * 5)))
                break
    st["feat"] = nfeat
    st["combos"] = len(combos)
    st["secs"] = time.time() - t0
    return cn, cand, st


def evaluate(cn, cands):
    """Every candidate on a quarter it has never seen."""
    P = prep(cn)
    if P is None:
        return cn, {}
    F, n, dayspan = P["F"], P["n"], P["dayspan"]
    keys, R, H = P["keys"], P["R"], P["H"]
    kmap = {k: i for i, k in enumerate(keys)}
    out = {}
    for j, c in enumerate(cands):
        if c["home"] == cn:
            continue
        bi = kmap.get((c["stop"], c["tgt"], c["side"]))
        if bi is None:
            continue
        tot, have = np.zeros(n, dtype=np.int16), 0
        for fn, sd, q in c["legs"]:
            v = F.get(fn)
            if v is None:
                continue
            v = np.asarray(v, dtype=np.float32)
            fin = np.isfinite(v)
            if fin.sum() < n * 0.5:
                continue
            thr = float(np.quantile(v[fin], q))
            tot += (((v >= thr) if sd > 0 else (v <= thr)) & fin).astype(np.int16)
            have += 1
        if have < c["k"]:
            continue
        idx = hunt.nonoverlap(np.flatnonzero(tot >= c["k"]), H[:, bi])
        if len(idx) < 30:
            continue
        v = R[idx, bi] - COST + MAKER
        out[j] = dict(dol=float(v.mean()), tpw=len(idx) / dayspan * 5)
    return cn, out


def main():
    t0 = time.time()
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    print(f"{len(cons)} quarters, {WORKERS} workers, K={KBAR}", flush=True)

    allc, stats = [], {}
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        for cn, cand, st in ex.map(scan, cons):
            stats[cn] = st
            allc += cand
            print(f"  {cn}: {st.get('feat',0)} features, "
                  f"{st.get('combos',0):,} combos, scanned {st['scan']:,} -> "
                  f"gate {st['gate']:,} -> train+test {st['test']:,} "
                  f"({st.get('secs',0)/60:.1f}m, "
                  f"{st['scan']/max(st.get('secs',1),1):,.0f}/s)", flush=True)
    print(f"\n{len(allc):,} candidates passed train AND held-out test. "
          f"Validating across quarters...", flush=True)

    res = {i: {} for i in range(len(allc))}
    if allc:
        with ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(evaluate, cn, allc) for cn in cons]
            for f in futs:
                cn, out = f.result()
                for j, v in out.items():
                    res[j][cn] = v
                print(f"  validated on {cn}", flush=True)

    winners = []
    for i, c in enumerate(allc):
        got = res[i]
        if len(got) < 4:
            continue
        dols = [v["dol"] for v in got.values()]
        c["oos"] = dict(dol=float(np.mean(dols)),
                        green=sum(1 for x in dols if x > 0), q=len(got),
                        tpw=float(np.mean([v["tpw"] for v in got.values()])))
        if c["oos"]["dol"] >= MIN_OOS_DOL and c["oos"]["green"] >= MIN_GREEN:
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

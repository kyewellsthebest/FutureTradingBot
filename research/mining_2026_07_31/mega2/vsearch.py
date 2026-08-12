"""Search with the validation inside the gate, not bolted on afterwards.

WHY EVERY PREVIOUS SEARCH FAILED, and it was not the gates. 365 million
configurations, ten distinct winners, all ten profitable in the quarter they
were found in and negative in every other -- eight of ten green in exactly one
quarter out of eight, which is what picking the best quarter at random
produces. Every one of them had cleared a frequency gate, a drawdown gate, a
random-entry gate and a win rate ten percent above break-even. The gates were
fine. The problem is that a configuration was fitted and scored on the SAME
data, so the gates were measuring how well it had memorised.

Selecting the maximum of N noisy estimates guarantees the winner's in-sample
number is inflated -- the more you search, the more inflated. That is not a
bug to be tuned away, it is arithmetic, and no threshold on an in-sample
statistic can survive it.

SO VALIDATION MOVES INSIDE THE GATE. A configuration is not a hit until it has
made money on data that had no say in choosing it:

  1. TRAIN, the first 60% of each contract by time. Gates applied here exactly
     as before -- frequency, geometry, drawdown, random entry, ten percent over
     break-even. Nothing loosened.

  2. TEST, the remaining 40% of the same contract. Must also pay. This is
     cheap, it needs no extra data, and it kills the worst overfits instantly.

  3. OUT OF SAMPLE, every OTHER quarter. This is the one that killed all ten
     winners, so it is now a requirement rather than a post-mortem. A survivor
     must be positive on average across quarters it never saw AND green in at
     least MIN_GREEN of them.

Only then is it a hit, and only then does the bar ratchet. The search can
still fool itself -- selecting the best of many validated candidates re-creates
the same problem one level up -- so the count of candidates validated is
reported and the selection ceiling is computed against it.

WHAT THIS COSTS. Each quarter is touched twice per epoch instead of once, so
the features are cached to disk as float32 (58 MB per contract-clock, under
half a gigabyte for all eight). The first epoch pays the build; the rest are
nearly free, which is what makes a validated search affordable at all.
"""
import hashlib
import itertools
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402
import mega  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "VSEARCH.md"))
STATE = os.environ.get("STATE_JSON",
                       os.path.join(fuse.ROOT, "data", "vsearch_state.json"))
FCACHE = os.path.join(fuse.ROOT, "data", "fcache")

TRAIN = float(os.environ.get("TRAIN", "0.60"))
MIN_GREEN = int(os.environ.get("MIN_GREEN", "5"))     # of the other quarters
MIN_OOS_DOL = float(os.environ.get("MIN_OOS_DOL", "0.50"))
MAX_CAND = int(os.environ.get("MAX_CAND", "400"))

MIN_TPW = float(os.environ.get("MIN_TPW", "400"))
MIN_DOL = float(os.environ.get("MIN_DOL", "2.00"))
MIN_RR = float(os.environ.get("MIN_RR", "1.1"))
MAX_RR = float(os.environ.get("MAX_RR", "3.0"))
MIN_WIN = float(os.environ.get("MIN_WIN", "0.28"))
MAX_WIN = float(os.environ.get("MAX_WIN", "0.80"))
MAX_DD_PCT = float(os.environ.get("MAX_DD_PCT", "0.10"))
MIN_EDGE_REL = float(os.environ.get("MIN_EDGE_REL", "0.10"))
MIN_EDGE_PP = float(os.environ.get("MIN_EDGE_PP", "0.02"))
MAX_EDGE = float(os.environ.get("MAX_EDGE", "0.06"))
MAX_FIRE = float(os.environ.get("MAX_FIRE", "0.90"))
PROBE = float(os.environ.get("PROBE", "0.04"))
ACCOUNT = float(os.environ.get("ACCOUNT", "4100"))
HOURS = float(os.environ.get("HOURS", "6"))
KBAR = [int(x) for x in os.environ.get("KBAR", "500").split(",")]
QS = [float(x) for x in os.environ.get("QS", "0.2,0.35,0.5,0.65,0.8").split(",")]
PERTYPE = int(os.environ.get("PERTYPE", "10"))
ARITY = int(os.environ.get("ARITY", "5"))

TV, TPX, COST = 0.50, 0.25, 1.24
# resting a limit is worth this much over crossing, MEASURED, not the flat two
# ticks the earlier searches credited -- which was most of their reported edge
MAKER = 0.355
L = []
STAT = dict(scan=0, gate1=0, test=0, cand=0, oos=0, hit=0, epochs=0)


def log(s=""):
    print(s, flush=True)
    L.append(s)


def cached(cn, K):
    """Features on disk as float32. Each quarter is visited twice per epoch --
    once to search, once to validate candidates found elsewhere -- and
    fuse.build re-reads the raw tape every call, so without this a validated
    search costs double what an unvalidated one does."""
    os.makedirs(FCACHE, exist_ok=True)
    p = os.path.join(FCACHE, f"{cn}_K{K}.npz")
    if os.path.exists(p):
        z = np.load(p, allow_pickle=False)
        B = {k: z["B_" + k] for k in ("o", "h", "l", "c", "ts")}
        B["ts"] = B["ts"].astype(np.int64)
        F = {k[2:]: z[k] for k in z.files if k.startswith("F_")}
        return B, F
    B, F = mega.features(cn, K)
    np.savez(p, **{"B_" + k: v for k, v in B.items()},
             **{"F_" + k: np.asarray(v, dtype=np.float32) for k, v in F.items()})
    return B, F


def ladder(B):
    unit = max(float(np.median(B["h"] - B["l"])) / TPX, 1.0)
    rung, x = [], 0.25 * unit
    while x <= 3.0 * unit:
        rung.append(x)
        x *= 1.12
    ks = np.unique(np.rint(np.array(rung))).astype(int)
    return ks[ks >= 1]


def brackets(ks, ct):
    out = []
    for i, S in enumerate(ks):
        for j, T in enumerate(ks):
            if ct / (S + T) > MAX_EDGE or not (MIN_RR <= T / S <= MAX_RR):
                continue
            need = (S + ct) / (S + T)
            if not (MIN_WIN <= need <= MAX_WIN):
                continue
            run = math.log(MIN_TPW * 52) / math.log(1 / max(1 - need, 1e-9))
            if run * S * TV <= MAX_DD_PCT * ACCOUNT:
                out.append((i, j))
    return out


def mask(F, legs, k, n):
    tot, have = np.zeros(n, dtype=np.int16), 0
    for fn, sd, q in legs:
        v = F.get(fn)
        if v is None:
            continue
        v = np.asarray(v, dtype=np.float64)[:n]
        fin = np.isfinite(v)
        if fin.sum() < n * 0.5:
            continue
        thr = float(np.quantile(v[fin], q))
        tot += (((v >= thr) if sd > 0 else (v <= thr)) & fin).astype(np.int16)
        have += 1
    return (tot >= k) if have >= k else None


def pnl_of(r, idx, days_frac, dayspan):
    if len(idx) < 30:
        return None
    v = r[idx] - COST + MAKER
    return dict(n=len(idx), dol=float(v.mean()),
                tpw=len(idx) / max(dayspan * days_frac, 1) * 5)


def search_one(cn, K, cand, deadline):
    """Fit on the first 60% of this contract, confirm on the last 40%."""
    B, F = cached(cn, K)
    n = len(B["c"])
    dayspan = len(np.unique(B["ts"] // fuse.DAY_NS))
    if n < 8000 or dayspan < 20:
        return
    cut = int(n * TRAIN)
    bpd = n / dayspan
    need = MIN_TPW / 5.0 / bpd
    ct = COST / TV
    ks = ladder(B)
    pairs = brackets(ks, ct)
    if not pairs:
        return
    up, dn = hunt.tau(B, ks, TPX)
    OC = {}
    for (si, ti) in pairs:
        for side in (1, -1):
            OC[(si, ti, side)] = hunt.outcomes(B, up, dn, si, ti, side, ks,
                                               TPX, TV)[:3]
    del up, dn

    # ---- legs, bucketed by data type so combinations cross types ----
    byt = {}
    for fn in sorted(F):
        v = np.asarray(F[fn], dtype=np.float64)
        fin = np.isfinite(v)
        if fin.sum() < n * 0.5:
            continue
        for q in QS:
            thr = float(np.quantile(v[fin], q))
            for sd in (1, -1):
                sig = ((v >= thr) if sd > 0 else (v <= thr)) & fin
                m = sig.mean()
                if m < need or m > MAX_FIRE:
                    continue
                byt.setdefault(fn.split("_")[0] + "_", []).append(
                    (sig, fn, sd, q))
    for t in byt:
        byt[t] = byt[t][:PERTYPE]
    types = sorted(byt)
    if len(types) < 2:
        return

    WIDE = {2: PERTYPE, 3: 5, 4: 4, 5: 3}
    groups = []
    for m in range(1, min(ARITY, len(types)) + 1):
        if m == 1:
            groups.append([(a,) for t in types for a in byt[t][:6]])
            continue
        w = WIDE.get(m, 3)
        for ts_ in itertools.combinations(types, m):
            groups.append([tuple(c) for c in
                           itertools.product(*[byt[t][:w] for t in ts_])])
    combos = [c for tier in itertools.zip_longest(*groups)
              for c in tier if c is not None]

    print(f"  {cn} K{K}: {len(ks)} rungs, {len(pairs)} brackets, "
          f"{len(types)} types, {len(combos):,} combos "
          f"(train {cut:,}/{n:,} bars)", flush=True)
    seen = set()
    t_start = time.time()
    for cb in combos:
        if time.time() > deadline or len(cand) >= MAX_CAND:
            return
        fs = tuple(x[1] for x in cb)
        if len(set(fs)) < len(fs):
            continue
        modes = ([(len(cb), "AND")] if len(cb) < 3 else
                 [(len(cb), "AND")] + [(k, str(k)) for k in range(2, len(cb))])
        for k, mname in modes:
            tot = np.zeros(n, dtype=np.int16)
            for x in cb:
                tot += x[0].astype(np.int16)
            sig = tot >= k
            fr = sig.mean()
            if fr < need or fr > MAX_FIRE:
                continue
            h = hashlib.blake2b(np.packbits(sig).tobytes(),
                                digest_size=12).digest()
            if h in seen:
                continue
            seen.add(h)
            idx_all = np.flatnonzero(sig)
            tr_all = idx_all[idx_all < cut]
            if len(tr_all) < 200:
                continue
            STAT["scan"] += 1

            for side in (1, -1):
                best = None
                for (si, ti) in pairs:
                    r, hold, wt = OC[(si, ti, side)]
                    pstar = (ks[si] + ct) / (ks[si] + ks[ti])
                    pall = float(wt[:cut].mean())
                    bar = max(pstar * (1 + MIN_EDGE_REL), pall + MIN_EDGE_PP)
                    # THE EXACT GATE BEFORE THE EXPENSIVE PART, not after.
                    # nonoverlap is O(n) and was being called for every
                    # (combination, bracket, side) that merely came within
                    # PROBE of the bar -- so the costly step ran on thousands
                    # of configurations that the very next line rejected. That
                    # is why this scanned 92,842 configurations in 22 minutes
                    # while the unvalidated search managed 365 million in six
                    # hours: 68x slower, for no extra information.
                    #
                    # The overlapping win rate is a tight upper bound on the
                    # non-overlapping one, so failing it here means failing it
                    # there. Screen exactly, then pay for nonoverlap only on
                    # what survives.
                    if float(wt[tr_all].mean()) < bar:
                        continue
                    keep = hunt.nonoverlap(idx_all, hold)
                    tr = keep[keep < cut]
                    te = keep[keep >= cut]
                    if len(tr) < 100 or len(te) < 60:
                        continue
                    if float(wt[tr].mean()) < bar:
                        continue
                    STAT["gate1"] += 1
                    a = pnl_of(r, tr, TRAIN, dayspan)
                    b = pnl_of(r, te, 1 - TRAIN, dayspan)
                    if not a or not b:
                        continue
                    # THE FREQUENCY MINIMUM IS A HIT CRITERION, NOT A
                    # CANDIDATE FILTER. 400 trades a week has never once been
                    # reached -- 0 of 11,742 scored configurations in the
                    # six-hour run, against a maximum of 252 -- so applying it
                    # here would guarantee an empty run for reasons that have
                    # nothing to do with validation. It is enforced at the end,
                    # where a hit must meet every minimum; anything that
                    # validates but falls short on frequency is still recorded,
                    # because "it generalises but only trades 250 times a week"
                    # is information and an empty file is not.
                    if a["dol"] < MIN_DOL:
                        continue
                    # ---- the held-out half of this very contract ----
                    if b["dol"] <= 0:
                        continue
                    STAT["test"] += 1
                    sc = min(a["dol"], b["dol"])
                    if best is None or sc > best[0]:
                        best = (sc, si, ti, a, b)
                if best is None:
                    continue
                sc, si, ti, a, b = best
                STAT["cand"] += 1
                cand.append(dict(
                    legs=[(x[1], int(x[2]), float(x[3])) for x in cb],
                    k=int(k), mode=mname, side=int(side), K=int(K),
                    stop=int(ks[si]), tgt=int(ks[ti]), home=cn,
                    train=a, test=b))
                print(f"  cand {len(cand):3d} {cn} {mname}of"
                      f"{[x[1] for x in cb]} {'L' if side > 0 else 'S'} "
                      f"train ${a['dol']:+.2f}@{a['tpw']:.0f}/wk  "
                      f"test ${b['dol']:+.2f}@{b['tpw']:.0f}/wk", flush=True)
    # WHERE THINGS DIE, after every contract rather than only at the end.
    # Without this the log is silent for hours and "found nothing" is
    # indistinguishable from "nothing came close" -- the counters are the
    # only thing that says which stage is the wall.
    print(f"  {cn} K{K}: done in {(time.time()-t_start)/60:.0f}m | "
          f"scanned {STAT['scan']:,} -> train gates {STAT['gate1']:,} -> "
          f"also paid on held-out {STAT['test']:,} -> candidates "
          f"{STAT['cand']:,}", flush=True)
    del B, F, OC


def validate(cand, cons, deadline):
    """Every candidate on every quarter it has never seen."""
    if not cand:
        return []
    need_k = sorted({c["K"] for c in cand})
    res = {i: {} for i in range(len(cand))}
    for K in need_k:
        for cn in cons:
            if time.time() > deadline:
                break
            try:
                B, F = cached(cn, K)
            except Exception as e:                               # noqa: BLE001
                print(f"  val {cn} K{K}: {type(e).__name__}: {e}", flush=True)
                continue
            n = len(B["c"])
            dayspan = len(np.unique(B["ts"] // fuse.DAY_NS))
            ks_cache = {}
            for i, c in enumerate(cand):
                if c["K"] != K or c["home"] == cn:
                    continue
                sig = mask(F, c["legs"], c["k"], n)
                if sig is None or sig.sum() < 50:
                    continue
                key = (c["stop"], c["tgt"], c["side"])
                if key not in ks_cache:
                    kk = np.array(sorted({c["stop"], c["tgt"]}), dtype=int)
                    si = int(np.where(kk == c["stop"])[0][0])
                    ti = int(np.where(kk == c["tgt"])[0][0])
                    u, d = hunt.tau(B, kk, TPX)
                    ks_cache[key] = hunt.outcomes(B, u, d, si, ti, c["side"],
                                                  kk, TPX, TV)[:3]
                    del u, d
                r, hold, wt = ks_cache[key]
                idx = hunt.nonoverlap(np.flatnonzero(sig), hold)
                o = pnl_of(r, idx, 1.0, dayspan)
                if o:
                    res[i][cn] = o
            del B, F, ks_cache
            print(f"  validated on {cn} K{K}", flush=True)
    out = []
    for i, c in enumerate(cand):
        got = res[i]
        if len(got) < 4:
            continue
        STAT["oos"] += 1
        dols = [v["dol"] for v in got.values()]
        green = sum(1 for x in dols if x > 0)
        c["oos"] = dict(dol=float(np.mean(dols)), green=green, q=len(got),
                        tpw=float(np.mean([v["tpw"] for v in got.values()])),
                        worst=float(np.min(dols)))
        out.append(c)
    return out


def main():
    t0 = time.time()
    end = float(os.environ.get("END_TS") or 0) or (t0 + HOURS * 3600)
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    winners, ep = [], 0
    global MIN_DOL, MIN_TPW
    print(f"train {TRAIN:.0%}/{1-TRAIN:.0%} split, then every other quarter. "
          f"hit = train gates AND test>0 AND out-of-sample >= "
          f"${MIN_OOS_DOL:.2f} in >= {MIN_GREEN} quarters", flush=True)

    while time.time() < end - 60:
        ep += 1
        STAT["epochs"] = ep
        rng = np.random.default_rng(500 + ep)
        global QS
        if ep > 1:
            QS = sorted(float(np.clip(q + rng.uniform(-0.06, 0.06), 0.05, 0.95))
                        for q in [0.2, 0.35, 0.5, 0.65, 0.8])
        print(f"\n=== epoch {ep} | {(end-time.time())/3600:.2f}h left | "
              f"bar ${MIN_DOL:.2f}/tr {MIN_TPW:.0f}/wk | "
              f"q={[round(q,2) for q in QS]}", flush=True)
        cand = []
        for K in KBAR:
            for cn in cons:
                if time.time() > end - 60 or len(cand) >= MAX_CAND:
                    break
                try:
                    search_one(cn, K, cand, end - 60)
                except Exception as e:                           # noqa: BLE001
                    print(f"{cn} K{K}: {type(e).__name__}: {e}", flush=True)
        print(f"  {len(cand)} candidates passed train+test, validating...",
              flush=True)
        vals = validate(cand, cons, end - 30)
        passed = [c for c in vals
                  if c["oos"]["dol"] >= MIN_OOS_DOL
                  and c["oos"]["green"] >= MIN_GREEN]
        good = [c for c in passed if c["oos"]["tpw"] >= MIN_TPW]
        short = [c for c in passed if c["oos"]["tpw"] < MIN_TPW]
        for c in short:
            o = c["oos"]
            print(f"  validated but {o['tpw']:.0f}/wk < {MIN_TPW:.0f}: "
                  f"${o['dol']:+.2f}/tr oos, {o['green']}/{o['q']} green",
                  flush=True)
        winners += short
        for c in good:
            STAT["hit"] += 1
            o = c["oos"]
            print(f"*** VALIDATED HIT  ${o['dol']:+.2f}/tr out of sample, "
                  f"{o['green']}/{o['q']} quarters green, {o['tpw']:.0f}/wk\n"
                  f"    {c['mode']}of{[l[0] for l in c['legs']]} "
                  f"{'L' if c['side'] > 0 else 'S'} {c['stop']}/{c['tgt']}",
                  flush=True)
        if good:
            top = max(good, key=lambda c: c["oos"]["dol"] * c["oos"]["tpw"])
            nd = max(MIN_DOL, round(top["oos"]["dol"] * 1.10, 3))
            nt = max(MIN_TPW, round(top["oos"]["tpw"] * 1.05))
            if nd > MIN_DOL or nt > MIN_TPW:
                print(f"    ratchet ${MIN_DOL:.2f}->${nd:.2f}, "
                      f"{MIN_TPW:.0f}->{nt:.0f}/wk", flush=True)
                MIN_DOL, MIN_TPW = nd, nt
        json.dump({"winners": winners, "stat": STAT,
                   "min_dol": MIN_DOL, "min_tpw": MIN_TPW},
                  open(STATE, "w"), default=float)

    # ------------------------------------------------------------ report
    log("# Searching with the validation inside the gate")
    log()
    log(f"Every previous search fitted and scored a configuration on the same "
        f"data. 365 million of them, ten distinct winners, and all ten were "
        f"profitable in the quarter they were found in and negative in every "
        f"other — eight of ten green in exactly one quarter of eight, which is "
        f"what picking the best quarter at random produces. The gates were "
        f"never the problem. Selecting the maximum of N noisy estimates "
        f"guarantees the winner's in-sample number is inflated, and no "
        f"threshold on an in-sample statistic survives that.")
    log()
    log(f"So a configuration here is not a hit until it has paid on data that "
        f"had no say in choosing it: gates on the first **{TRAIN:.0%}** of a "
        f"contract, then the held-out **{1-TRAIN:.0%}** must also pay, then "
        f"**every other quarter** must average **≥ ${MIN_OOS_DOL:.2f}** a "
        f"trade and be green in at least **{MIN_GREEN}** of them.")
    log()
    log("| stage | survived |")
    log("|---|---|")
    log(f"| scanned | {STAT['scan']:,} |")
    log(f"| cleared the train gates | {STAT['gate1']:,} |")
    log(f"| **also paid on the held-out 40%** | {STAT['test']:,} |")
    log(f"| became candidates | {STAT['cand']:,} |")
    log(f"| validated across quarters | {STAT['oos']:,} |")
    log(f"| **VALIDATED HITS** | **{STAT['hit']:,}** |")
    log()
    if not winners:
        log(f"**No configuration survived.** `{STAT['cand']:,}` cleared the "
            f"gates on their training half *and* paid on the held-out half of "
            f"the same contract, and not one of them stayed profitable across "
            f"the quarters it had never seen. That is the same verdict as "
            f"before, reached without needing a separate validation pass to "
            f"discover it — which is the point of building it into the gate.")
    else:
        nfull = sum(1 for c in winners if c["oos"]["tpw"] >= MIN_TPW)
        log(f"`{len(winners)}` survived train, test AND every other quarter — "
            f"**{nfull}** of them also meet the {MIN_TPW:.0f} trades/week "
            f"minimum. The rest generalise but trade too rarely, which is "
            f"reported rather than hidden: 400 a week has never been reached "
            f"by anything, in any run.")
        log()
        log(f"Ranked by out-of-sample "
            f"dollars per week, which is the only number here that was not "
            f"used to select them.")
        log()
        log("| rule | side | home | train $/tr | test $/tr | **out-of-sample "
            "$/tr** | green | **$/wk out of sample** |")
        log("|---|---|---|---|---|---|---|---|")
        for c in sorted(winners,
                        key=lambda z: -z["oos"]["dol"] * z["oos"]["tpw"])[:25]:
            o = c["oos"]
            legs = ", ".join(f"`{a}`" for a, _, _ in c["legs"])[:60]
            log(f"| {c['mode']}of({legs}) | "
                f"{'L' if c['side'] > 0 else 'S'} | {c['home']} | "
                f"${c['train']['dol']:+.2f} | ${c['test']['dol']:+.2f} | "
                f"**${o['dol']:+.2f}** | {o['green']}/{o['q']} | "
                f"**${o['dol']*o['tpw']:+,.0f}** |")
        log()
        log(f"Selecting the best of `{STAT['oos']:,}` validated candidates "
            f"re-creates the selection problem one level up, so the ceiling "
            f"applies here too: **{math.sqrt(2*math.log(max(STAT['oos'],2))):.2f}σ** "
            f"worth of it. Out-of-sample profit is necessary, not sufficient.")
    log()
    log(f"_Ran {(time.time()-t0)/3600:.2f} h, {ep} epochs._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

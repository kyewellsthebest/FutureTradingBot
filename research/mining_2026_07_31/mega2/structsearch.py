"""100,000 structural strategies. Variable triggers, variable stops, variable targets.

Everything before this used FIXED distances, and that was the right criticism.
A real method aims at structure: the stop sits where the last swing low is, the
target sits at whatever level is overhead, and both distances differ on every
single trade. So does the risk:reward -- it is an output of the geometry, never
an input.

WHAT MAKES A SEARCH THIS SIZE POSSIBLE. Resolving a target-vs-stop race on the
tick path is the expensive part, and doing it 100,000 times is impossible if
each strategy re-walks the tape. But the race only depends on the entry index
and two DISTANCES, so it can be precomputed once:

    tau_up[i, k]  = price changes after entry i until price is k ticks higher
    tau_dn[i, k]  = price changes after entry i until price is k ticks lower

Build those two tables once and every strategy in the space becomes two array
lookups and a comparison. A hundred thousand strategies then costs about what
one used to.

WHAT MAKES IT HONEST. Two baselines, and a strategy has to beat both.

  1  ITS OWN GEOMETRY. A trade risking S to make T wins S/(S+T) of the time on
     a driftless walk, no matter how S and T were chosen. With variable
     distances this is the only meaningful null -- a 70% win rate means nothing
     if the geometry alone hands you 72%.

  2  A SHUFFLED TAPE. The identical search re-run on a tape built from a random
     permutation of the real tick-by-tick increments. Same volatility, same tick
     distribution, same everything -- only the ORDER is destroyed, so no
     structure can survive. This second control exists because the levels study
     found that my own measurement carried a -0.79pp censoring bias: trades that
     resolve slowly get dropped, and slow wins to a far target are dropped more
     often than fast losses to a near stop. Running the whole machine on
     shuffled data measures that bias instead of assuming it away.

The reported edge is `real - shuffled`, in percentage points of win rate above
each trade's own geometry. Everything else is bookkeeping.

THE QUESTIONS BUILT INTO THE SPACE, which are the user's questions:
  what triggers it            -- 13 structural features x 8 strengths x 2 sides
  where does it aim           -- prior levels 1st/2nd/3rd, measured moves, R-multiples
  where is it wrong           -- swing extreme, older extremes, volatility multiples
  does the R:R vary           -- yes, every trade, and it is reported not chosen
  does filtering help         -- the R:R and hit-rate breakdown answers it directly
"""
import glob
import itertools
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.environ.get("OUT_MD", os.path.join(ROOT, "research", "STRUCTSEARCH.md"))
JL = os.path.join(ROOT, "research", "structsearch_survivors.jsonl")
PT = 4                                   # ticks per NQ point
USD_TICK = 0.50
COST = 1.99
# W and KMAX are bound together by physics: a walk needs about k^2 price
# changes to travel k ticks, so a horizon of 32,000 resolves roughly 180 ticks.
# Barriers beyond that mostly never resolve, and a validation run showed the
# distortion tracks the unresolved fraction exactly -- 0% unresolved gave
# +0.71pp (noise), 76% unresolved gave +8.08pp (garbage). Hence MAXUNRES.
W = int(os.environ.get("W", "32000"))
KMAX = int(os.environ.get("KMAX", "200"))     # 50 points
MAXUNRES = float(os.environ.get("MAXUNRES", "0.25"))
CHUNK = int(os.environ.get("CHUNK", "250"))
RS = [int(x) for x in os.environ.get("RS", "8,12,20").split(",")]
MINTR = int(os.environ.get("MINTR", "400"))
SEED = 20260808
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


# ----------------------------------------------------------------- tables --

def tau_tables(pc, ent):
    """First-passage times to every distance, for every entry. The whole trick.

    cummax after an entry is non-decreasing, so the first time price is k ticks
    up is a searchsorted into it -- one call answers all 640 distances at once.
    """
    n = len(pc)
    ent = ent[(ent > 0) & (ent < n - W - 2)]
    up = np.full((len(ent), KMAX + 1), W, np.int32)
    dn = np.full((len(ent), KMAX + 1), W, np.int32)
    ks = np.arange(KMAX + 1)
    for c0 in range(0, len(ent), CHUNK):
        ii = ent[c0:c0 + CHUNK]
        fwd = np.lib.stride_tricks.sliding_window_view(pc, W + 1)[ii][:, 1:]
        cmax = np.maximum.accumulate(fwd, axis=1)
        cmin = np.minimum.accumulate(fwd, axis=1)
        p0 = pc[ii]
        for r in range(len(ii)):
            up[c0 + r] = np.searchsorted(cmax[r], p0[r] + ks, side="left")
            dn[c0 + r] = np.searchsorted(-cmin[r], -p0[r] + ks, side="left")
        del fwd, cmax, cmin
    return ent, up, dn


def pivot_frame(pc, R):
    """Confirmed swings with causal features, plus the levels overhead."""
    piv, conf, dirs = grammar.decompose(pc, R * PT)
    if len(piv) < 500:
        return None
    st = np.r_[0, piv[:-1]]
    S = np.abs(pc[piv] - pc[st]).astype(np.float64) / PT
    nch = np.maximum((piv - st).astype(np.float64), 1)
    side = -dirs.astype(np.int64)                       # new leg direction
    ep = pc[conf].astype(np.float64)

    def med(a, w=100):
        import pandas as pd
        return pd.Series(a).rolling(w, min_periods=min(30, w)).median().shift(1).values

    prev = np.r_[np.nan, S[:-1]]
    F = {
        "size": S / np.maximum(med(S), 1e-9),
        "speed": (S / nch) / np.maximum(med(S / nch), 1e-9),
        "retrace": S / np.maximum(prev, 1e-9),
        "prev_size": prev / np.maximum(med(S), 1e-9),
        "conf_len": (conf - piv) / np.maximum(med((conf - piv).astype(float)), 1e-9),
        "regime": med(S, 20) / np.maximum(med(S, 200), 1e-9),
        "accel": S / np.maximum(prev, 1e-9) - np.r_[np.nan, np.nan, S[:-2]] /
                 np.maximum(prev, 1e-9),
        # LOOK-AHEAD BUG, fixed. This was np.convolve(..., "same"), and "same"
        # is CENTRED -- it reaches one step forward, so run[i] carried part of
        # S[i+1], the size of the very swing the trade is about to take. The
        # filter was selecting trades whose upcoming swing was large, which is
        # reading the answer. It produced +14.83pp above geometry ON A SHUFFLED
        # RANDOM WALK, where no edge can exist, and six "profitable" strategies
        # worth $13/trade. Now a strictly backward window: run[i] counts how
        # many of the LAST three completed swings grew.
        "run": np.r_[np.nan, np.nan, np.nan,
                     np.convolve((np.diff(S) > 0).astype(float),
                                 np.ones(3), "valid")[:len(S) - 3]],
        "pos_in_range": np.zeros(len(S)),
        "size_z": (S - med(S)) / np.maximum(med(np.abs(S - med(S))), 1e-9),
        "len_ratio": nch / np.maximum(med(nch), 1e-9),
        "prev_speed": np.r_[np.nan, (S / nch)[:-1]] /
                      np.maximum(med(S / nch), 1e-9),
        "two_ago": np.r_[np.nan, np.nan, S[:-2]] / np.maximum(med(S), 1e-9),
    }
    # levels overhead in the trade direction: 1st, 2nd, 3rd prior same-sign pivot
    lv = np.full((len(piv), 3), np.nan)
    for i in range(len(piv)):
        s = side[i]
        found = []
        for j in range(i - 1, max(-1, i - 150), -1):
            if -int(dirs[j]) != -s:          # a prior extreme facing the trade
                continue
            v = float(pc[piv[j]])
            if (s > 0 and v > ep[i]) or (s < 0 and v < ep[i]):
                found.append(v)
                if len(found) == 3:
                    break
        for q in range(len(found)):
            lv[i, q] = found[q]
    return dict(conf=conf, piv=piv, side=side, ep=ep, S=S, F=F, lv=lv,
                medS=med(S))


# --------------------------------------------------------------- strategy --

FEATS = ["size", "speed", "retrace", "prev_size", "conf_len", "regime",
         "accel", "size_z", "len_ratio", "prev_speed", "two_ago", "run"]
QS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.78, 0.85, 0.9, 0.95]
STOPS = [("swing", 0), ("swing2", 0), ("m0.4", 0.4), ("m0.7", 0.7),
         ("m1.0", 1.0), ("m1.5", 1.5), ("m2.0", 2.0), ("m3.0", 3.0)]
TARGETS = [("lvl1", 0), ("lvl2", 0), ("lvl3", 0), ("mm0.6", 0.6),
           ("mm1.0", 1.0), ("mm1.6", 1.6), ("r0.75", -0.75), ("r1.0", -1.0),
           ("r2.0", -2.0), ("r3.0", -3.0)]
SIDES = [("long", 1), ("short", -1), ("both", 0)]


def barriers(P, stop_rule, tgt_rule):
    """Stop and target distances in TICKS, per trade. Both vary by structure."""
    ep, S, medS, lv, side = P["ep"], P["S"], P["medS"], P["lv"], P["side"]
    piv = P["piv"]
    name, k = stop_rule
    if name == "swing":
        sd = np.abs(ep - P["pcpiv"])
    elif name == "swing2":
        prev_piv = np.r_[P["pcpiv"][0], P["pcpiv"][:-1]]
        sd = np.abs(ep - prev_piv)
    else:
        sd = k * medS * PT
    tname, tk = tgt_rule
    if tname.startswith("lvl"):
        td = np.abs(lv[:, int(tname[3]) - 1] - ep)
    elif tname.startswith("mm"):
        td = tk * np.r_[np.nan, S[:-1]] * PT          # measured move
    else:
        td = (-tk) * sd                                # R multiple
    return sd, td


def evaluate(P, ent_idx, up, dn, feat, q, stop_rule, tgt_rule, sside):
    sd, td = barriers(P, stop_rule, tgt_rule)
    v = P["F"][feat]
    ok = np.isfinite(v) & np.isfinite(sd) & np.isfinite(td) & (sd >= 2) & (td >= 2)
    ok &= (sd <= KMAX) & (td <= KMAX)
    if sside != 0:
        ok &= P["side"] == sside
    if ok.sum() < MINTR:
        return None
    thr = P["thr"].get((feat, q))
    if thr is None:                       # computed once per feature, not per strategy
        fin = v[np.isfinite(v)]
        thr = float(np.quantile(fin, q)) if (q > 0 and len(fin)) else -np.inf
        P["thr"][(feat, q)] = thr
    ok &= v >= thr
    if ok.sum() < MINTR:
        return None
    pos = P["row"][ok]
    good = pos >= 0
    if good.sum() < MINTR:
        return None
    pos = pos[good]
    s = np.rint(sd[ok][good]).astype(np.int64).clip(1, KMAX)
    t = np.rint(td[ok][good]).astype(np.int64).clip(1, KMAX)
    sgn = P["side"][ok][good]
    tt = np.where(sgn > 0, up[pos, t], dn[pos, t])
    ts = np.where(sgn > 0, dn[pos, s], up[pos, s])
    res = tt != ts
    unres = float(1.0 - res.mean())
    if res.sum() < MINTR or unres > MAXUNRES:
        return None
    win = (tt < ts)[res]
    sv, tv = s[res].astype(float), t[res].astype(float)
    geo = sv / (sv + tv)
    pnl = np.where(win, tv, -sv) * USD_TICK
    return dict(n=int(res.sum()), unres=unres, hit=float(win.mean()),
                geo=float(geo.mean()), edge=float(win.mean() - geo.mean()),
                gross=float(pnl.mean()), rr=float(np.median(tv / sv)))


def build(tapes, label):
    out = {}
    for c, pc in tapes.items():
        for R in RS:
            P = pivot_frame(pc, R)
            if P is None:
                continue
            P["pcpiv"] = pc[P["piv"]].astype(np.float64)
            ent, up, dn = tau_tables(pc, P["conf"])
            row = np.full(len(P["conf"]), -1, np.int64)
            pos = np.searchsorted(ent, P["conf"])
            hit = (pos < len(ent)) & (ent[np.minimum(pos, len(ent) - 1)]
                                      == P["conf"])
            row[hit] = pos[hit]
            P["row"] = row
            P["thr"] = {}
            out[(c, R)] = (P, up, dn)
            print(f"  [{label}] {c} R={R}: {len(P['conf']):,} swings, "
                  f"{len(ent):,} with tables", flush=True)
    return out


def main():
    real = {}
    for p in sorted(glob.glob(os.path.join(CACHE, "NQ*_R4.npz"))):
        c = os.path.basename(p).split("_")[0]
        if c in ("NQU4", "NQZ4", "NQH5", "NQM5", "NQU5"):
            continue                       # held-out contracts only
        real[c] = np.load(p, allow_pickle=False)["pc"].astype(np.int64)
    rng = np.random.default_rng(SEED)
    shuf = {}
    for c, pc in real.items():
        d = np.diff(pc)
        rng.shuffle(d)
        shuf[c] = np.r_[pc[0], pc[0] + np.cumsum(d)].astype(np.int64)

    t0 = time.time()
    RE = build(real, "real")
    SH = build(shuf, "shuffled")
    log("# 100,000 structural strategies, judged against geometry and a shuffled tape")
    log()
    log("Triggers, stops and targets are all STRUCTURAL — the distances differ "
        "on every trade and the risk:reward is an output, never an input. "
        "Resolving target-versus-stop is precomputed as first-passage tables, "
        "so every strategy costs two lookups instead of a walk down the tape.")
    log()
    log("Two baselines, and a strategy must beat both. **Its own geometry**: a "
        "trade risking S to make T wins S/(S+T) on a driftless walk however S "
        "and T were chosen, so a 70% win rate is nothing if geometry hands you "
        "72%. And **a shuffled tape** — the same search on a random permutation "
        "of the real tick increments, identical volatility, order destroyed. "
        "That second control exists because the levels study caught a −0.79pp "
        "censoring bias in this very measurement.")
    log()
    log(f"Tables built in {time.time() - t0:.0f}s.")
    log()

    combos = list(itertools.product(FEATS, QS, STOPS, TARGETS, SIDES))
    log(f"Strategy space: {len(FEATS)} triggers x {len(QS)} strengths x "
        f"{len(STOPS)} stop rules x {len(TARGETS)} target rules x "
        f"{len(SIDES)} sides x {len(RS)} scales = "
        f"**{len(combos) * len(RS) * len(real):,} evaluations**, "
        f"{len(combos) * len(RS):,} distinct strategies.")
    log()

    rows = []
    t0 = time.time()
    for si, (feat, q, sr, tr, (sn, sv)) in enumerate(combos):
        for R in RS:
            agg = {}
            for src, store in (("real", RE), ("shuf", SH)):
                N = H = G = 0
                gr = 0.0
                for c in real:
                    k = (c, R)
                    if k not in store:
                        continue
                    P, up, dn = store[k]
                    r = evaluate(P, None, up, dn, feat, q, sr, tr, sv)
                    if r is None:
                        continue
                    N += r["n"]; H += r["hit"] * r["n"]; G += r["geo"] * r["n"]
                    gr += r["gross"] * r["n"]
                if N >= MINTR * 2:
                    agg[src] = (N, H / N, G / N, gr / N)
            if "real" in agg and "shuf" in agg:
                n, h, g, gross = agg["real"]
                _, sh, sg, _ = agg["shuf"]
                rows.append((h - g - (sh - sg), n, h, g, sh - sg, gross,
                             f"{feat}>=q{q:g} R={R} stop={sr[0]} tgt={tr[0]} {sn}"))
        if si % 400 == 0 and si:
            print(f"  {si}/{len(combos)} combos, {len(rows):,} scored, "
                  f"{time.time() - t0:.0f}s", flush=True)

    log(f"**{len(rows):,} strategies scored** (met the {MINTR}-trade gate on "
        f"both the real and the shuffled tape) in {(time.time() - t0)/60:.1f} "
        f"minutes.")
    log()
    e = np.array([r[0] for r in rows])
    log("### The whole population")
    log()
    log(f"Mean edge over geometry-and-shuffle: **{e.mean()*100:+.3f} pp**. "
        f"{int((e > 0).sum()):,}/{len(e):,} positive "
        f"({(e > 0).mean()*100:.1f}%, a coin gives 50%). "
        f"Spread {e.min()*100:+.2f} to {e.max()*100:+.2f} pp.")
    log()
    log("### The 40 strongest, after both controls")
    log()
    log("| edge vs geometry+shuffle | trades | hit | geometry | shuffle bias | "
        "$/trade gross | net | strategy |")
    log("|---|---|---|---|---|---|---|---|")
    for d, n, h, g, sb, gross, tag in sorted(rows, reverse=True)[:40]:
        log(f"| **{d*100:+.2f} pp** | {n:,} | {h*100:.2f}% | {g*100:.2f}% | "
            f"{sb*100:+.2f} pp | ${gross:+.3f} | ${gross-COST:+.2f} | `{tag}` |")
    log()
    prof = [r for r in rows if r[5] - COST > 0]
    log(f"### Strategies profitable after the ${COST:.2f} toll: "
        f"**{len(prof):,}** of {len(rows):,}")
    log()
    if prof:
        log("| net $/trade | trades | edge vs controls | hit | strategy |")
        log("|---|---|---|---|---|")
        for d, n, h, g, sb, gross, tag in sorted(prof, key=lambda x: -(x[5]))[:40]:
            log(f"| **${gross-COST:+.2f}** | {n:,} | {d*100:+.2f} pp | "
                f"{h*100:.2f}% | `{tag}` |")
    log()
    with open(JL, "w") as f:
        for d, n, h, g, sb, gross, tag in sorted(rows, reverse=True)[:2000]:
            f.write(json.dumps(dict(edge=d, n=n, hit=h, geo=g, shuf=sb,
                                    gross=gross, tag=tag)) + "\n")
    log("---")
    log("Held-out contracts only. First touch on the real tick sequence. "
        "Trades where neither barrier resolves inside the horizon are dropped "
        "on BOTH tapes, which is why the shuffled control is subtracted rather "
        "than assumed to be zero.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

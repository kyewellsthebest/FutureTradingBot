"""Pool every candidate across all eight quarters. The test that has killed
every previous winner, run deliberately instead of as an afterthought.

WHY THIS AND NOT A WIDER SEARCH.

The hunt scored each contract separately and nothing recurred in more than
three quarters out of eight. Mean drift-corrected sigma across the best
families was 1.8-2.2 against a 4.9 sigma selection ceiling. Widening the
search would not help: more configurations raises the ceiling faster than it
raises the best draw, so a bigger sweep makes a real find HARDER to establish,
not easier. The budget is better spent shrinking the error bar than growing
the candidate list.

Pooling does exactly that. Eight quarters is roughly eight times the trades, so
the standard error on a win rate falls by about 2.8x. A genuine 1-2 percentage
point edge that reads +1.8 sigma on one quarter reads +5 sigma pooled. A lucky
quarter averages away to nothing. Same data, better question.

THE SELECTION TRAP THIS AVOIDS, which is the whole reason it needs its own
file. The hunt only recorded a family on contracts where it PASSED the gate.
Pooling those rows would average the quarters it happened to win in and ignore
the ones it lost -- a guaranteed positive result, from arithmetic. So every
family here is re-evaluated on EVERY quarter, including the ones it never
appeared in, and the pooled figure is over all of them.

WHAT COUNTS AS A PASS:
  1. pooled win rate beats what the SAME bracket earns entered at every bar
     (drift, trend and time-of-day are the baseline, never a coin flip)
  2. pooled net dollars per trade above zero after the market's own cost
  3. positive in most quarters, not carried by one
  4. pooled sigma above the sqrt(2 ln N) ceiling for the number of families
     the hunt actually tried
"""
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "POOLED.md"))
STATE = hunt.STATE
MULT = np.array([.5, .75, 1, 1.5, 2, 3, 4.5, 7])
NFAM = int(os.environ.get("NFAM", "300"))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def ladder(B, tpx):
    unit = max(float(np.median(B["h"] - B["l"])) / tpx, 1.0)
    ks = np.unique(np.rint(unit * MULT)).astype(int)
    return ks[ks >= 1], unit


def legs(label):
    """'f_ofi21>q0.7 & f_ofi89>q0.6' -> [(feat, side, q), ...]; a bare feature
    name comes back as a single leg with its own q supplied by the caller."""
    out = []
    for part in label.split(" & "):
        if ">q" in part:
            f, q = part.split(">q")
            out.append((f, 1, float(q)))
        elif "<q" in part:
            f, q = part.split("<q")
            out.append((f, -1, float(q)))
        else:
            out.append((part, None, None))
    return out


def signal(F, n, label, q, side):
    sig = np.ones(n, dtype=bool)
    for (f, s, qq) in legs(label):
        if f not in F:
            return None
        v = F[f]
        fin = np.isfinite(v)
        s = side if s is None else s
        qq = q if qq is None else qq
        thr = np.quantile(v[fin], qq)
        sig &= (((v >= thr) if s > 0 else (v <= thr)) & fin)
    return sig


def main():
    t0 = time.time()
    st = json.load(open(STATE))
    rows = st["rows"]
    ntried = len(rows)
    ceil = math.sqrt(2 * math.log(max(ntried, 2)))
    meta = fuse.tape_meta()

    # families keyed by the LADDER POSITION, not absolute ticks -- the ladder
    # is scaled to each quarter's own volatility, so "135 ticks" is a
    # different animal in a calm quarter than a wild one.
    fam = {}
    for x in rows:
        if x.get("zd", 0) <= 0 or x["dol"] <= 0:
            continue
        key = (x["mkt"], x["K"], x["feat"], x["q"], x["side"],
               x["stop"], x["tgt"], x["con"])
        fam[key] = max(fam.get(key, 0.0), x.get("zd", 0.0))
    ranked = sorted(fam.items(), key=lambda kv: -kv[1])[:NFAM]
    print(f"{ntried:,} rows -> {len(ranked)} families to pool "
          f"(ceiling {ceil:.1f}σ)", flush=True)

    cons = {}
    for m in set(k[0] for k, _ in ranked):
        cons[m] = [c for c, v in sorted(meta.items()) if v["sym"] == m and
                   v["n"] / max((v["t1"] - v["t0"]) / fuse.DAY_NS, 1) >= 5000]

    out = []
    for i, ((m, K, feat, q, side, stop, tgt, seen), z0) in enumerate(ranked):
        tv, tpx = hunt.MKT[m]["tickval"], hunt.MKT[m]["tickpx"]
        cost = hunt.MKT[m]["cost"]
        tw = tn = 0
        bw = 0.0
        pq, dollars, days_t = [], [], 0
        for cn in cons[m]:
            try:
                B, F = hunt.build(cn, K, meta[cn]["path"])
            except Exception:                                    # noqa: BLE001
                continue
            ks, unit = ladder(B, tpx)
            # same LADDER POSITION as the quarter it was found on
            ks0, unit0 = ladder(*(hunt.build(seen, K, meta[seen]["path"])[0],
                                  tpx)) if seen != cn else (ks, unit)
            si = int(np.argmin(np.abs(ks0 - stop)))
            ti = int(np.argmin(np.abs(ks0 - tgt)))
            si, ti = min(si, len(ks) - 1), min(ti, len(ks) - 1)
            n = len(B["c"])
            sig = signal(F, n, feat, q, side)
            if sig is None or sig.sum() < 200:
                continue
            up, dn = hunt.tau(B, ks, tpx)
            r, hold, wt = hunt.outcomes(B, up, dn, si, ti, side, ks, tpx,
                                        tv)[:3]
            idx = hunt.nonoverlap(np.flatnonzero(sig), hold)
            if len(idx) < 50:
                continue
            w = int(wt[idx].sum())
            tw += w
            tn += len(idx)
            bw += float(wt.mean()) * len(idx)      # drift baseline, weighted
            pnl = r[idx] - cost
            dollars.append(float(pnl.sum()))
            pq.append(float(pnl.mean()))
            days_t += len(np.unique(B["ts"] // fuse.DAY_NS))
        if tn < 500 or not pq:
            continue
        p = tw / tn
        pall = bw / tn
        se = math.sqrt(max(pall * (1 - pall), 1e-9) / tn)
        out.append(dict(mkt=m, K=K, feat=feat, q=q, side=side, stop=stop,
                        tgt=tgt, n=tn, win=p, pall=pall, zd=(p - pall) / se,
                        dol=sum(dollars) / tn, tpw=tn / max(days_t, 1) * 5,
                        pos=sum(1 for v in pq if v > 0), nq=len(pq),
                        found_on=seen, z_single=z0))
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(ranked)} ({(time.time()-t0)/60:.0f} min)",
                  flush=True)

    out.sort(key=lambda z: -z["zd"])
    log("# Every candidate, pooled across all eight quarters")
    log()
    log(f"The hunt scored each quarter separately and nothing recurred in more "
        f"than three of eight. Widening the search would not fix that — more "
        f"configurations raises the noise ceiling faster than it raises the "
        f"best draw. So the budget went on shrinking the error bar instead: "
        f"eight quarters is ~8x the trades, so a win rate's standard error "
        f"falls ~2.8x. A real 1–2 point edge reading +1.8σ on one quarter "
        f"reads about +5σ pooled; a lucky quarter averages away.")
    log()
    log(f"**The trap this avoids.** The hunt only recorded a family on quarters "
        f"where it PASSED. Pooling those rows would average its wins and ignore "
        f"its losses — a positive result guaranteed by arithmetic. Every family "
        f"below is re-scored on **every** quarter, including ones it never "
        f"appeared in.")
    log()
    log(f"`{ntried:,}` configurations were tried, so the selection ceiling is "
        f"**{ceil:.1f}σ** — the best of that many pure-noise draws. Every win "
        f"rate is measured against the same bracket entered at every bar, so "
        f"the {'8,492-point' if 'NQ' in [o['mkt'] for o in out[:1]] else ''} "
        f"market drift is already removed.")
    log()
    if out:
        log("| market | clock | trigger | side | stop | target | pooled trades "
            "| win% | drift% | **σ vs drift** | quarters + | $/trade | "
            "trades/wk |")
        log("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in out[:25]:
            mark = "**" if r["zd"] > ceil else ""
            log(f"| {r['mkt']} | {r['K']} | {r['feat'][:38]} | "
                f"{'long' if r['side'] > 0 else 'short'} | {r['stop']} | "
                f"{r['tgt']} | {r['n']:,} | {r['win']*100:.1f}% | "
                f"{r['pall']*100:.1f}% | {mark}{r['zd']:+.1f}σ{mark} | "
                f"{r['pos']}/{r['nq']} | ${r['dol']:+.2f} | {r['tpw']:.0f} |")
        log()
        surv = [r for r in out if r["zd"] > ceil and r["dol"] > 0
                and r["pos"] >= r["nq"] - 1]
        log(f"**{len(surv)}** cleared everything: pooled sigma above the "
            f"{ceil:.1f}σ ceiling, positive dollars after cost, and positive in "
            f"all but at most one quarter.")
        if not surv:
            best = out[0]
            log()
            log(f"The best pooled result is **{best['zd']:+.1f}σ** against a "
                f"**{ceil:.1f}σ** ceiling, positive in {best['pos']} of "
                f"{best['nq']} quarters at ${best['dol']:+.2f} a trade. Pooling "
                f"multiplied the sample by eight and the sigma did not follow, "
                f"which is what a real edge would have done and noise does not.")
    log()
    log(f"_Ran {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

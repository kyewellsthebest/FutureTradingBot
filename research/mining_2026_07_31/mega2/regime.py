"""Does anything work once the day is split by dealer gamma?

THE HYPOTHESIS, and it is a specific claim about why everything has failed.

Every study in this repo measured an AVERAGE over two years. If a rule makes
money when dealers are long gamma -- when they sell rallies and buy dips, and
the range is suppressed -- and loses when they are short and the range is
amplified, then its average is near zero. Near zero is exactly what every
single study has reported. The average was never evidence of no edge; it was
evidence of not conditioning.

That is a real, falsifiable explanation, and it is the first one that has been
available, because dealer gamma is the first dataset here that classifies the
day rather than describing the price.

WHY THIS IS ALSO THE EASIEST WAY TO FOOL YOURSELF, and what stops it.

Splitting results into subgroups and reporting the good half is textbook data
dredging. Four things make this different from that:

  THE SPLIT IS PRE-SPECIFIED. Gamma sign, computed from option prices that
  know nothing about any strategy. It is not fitted, not tuned, and there is
  no threshold to choose -- zero is zero.

  THE DRIFT BASELINE IS COMPUTED WITHIN EACH REGIME. Short-gamma days are
  disproportionately down days. Comparing a long strategy's short-gamma
  performance to an all-days baseline would manufacture a result out of that
  alone.

  THE LABELS GET SHUFFLED. The day-to-regime map is permuted and the whole
  split recomputed several times. That gives the size of the regime gap that
  random labelling produces, which is the only honest floor for the real one.

  THE CEILING RISES. Testing two subgroups instead of one doubles the draws,
  so sqrt(2 ln N) is computed against the doubled count. Splitting is not free.

A REAL RESULT LOOKS LIKE: the same sign, in the same regime, across many
unrelated families, beyond the shuffled floor. One family flipping is noise
with an explanation attached.
"""
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

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "REGIME.md"))
GEX = os.path.join(fuse.ROOT, "data", "gex", "gex_history.parquet")
NFAM = int(os.environ.get("NFAM", "120"))
NSHUF = int(os.environ.get("NSHUF", "5"))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def regime_map(fam="NDX"):
    g = pd.read_parquet(GEX)
    g = g[g.fam == fam].copy()
    g["date"] = pd.to_datetime(g.day).dt.strftime("%Y-%m-%d")
    return dict(zip(g.date, np.where(g.gex_vol > 0, 1, -1)))


def families(rows, n):
    fam = {}
    for x in rows:
        k = (x["mkt"], x["K"], x["feat"], x["q"], x["side"], x["stop"],
             x["tgt"], x["con"])
        fam[k] = max(fam.get(k, -9.9), x.get("zd", -9.9))
    return sorted(fam.items(), key=lambda kv: -kv[1])[:n]


def evaluate(key, rmap):
    """Every quarter, trades bucketed by the gamma regime of their own day."""
    (m, K, feat, q, side, stop, tgt, seen) = key
    meta = fuse.tape_meta()
    tv, tpx = hunt.MKT[m]["tickval"], hunt.MKT[m]["tickpx"]
    cost = hunt.MKT[m]["cost"]
    cons = [c for c, v in sorted(meta.items()) if v["sym"] == m and
            v["n"] / max((v["t1"] - v["t0"]) / fuse.DAY_NS, 1) >= 5000]
    acc = {1: dict(w=0, n=0, b=0.0, pnl=0.0), -1: dict(w=0, n=0, b=0.0, pnl=0.0)}
    for cn in cons:
        try:
            B, F = hunt.build(cn, K, meta[cn]["path"])
        except Exception:                                        # noqa: BLE001
            continue
        unit = max(float(np.median(B["h"] - B["l"])) / tpx, 1.0)
        ks = np.unique(np.rint(unit * hunt.MULT if hasattr(hunt, "MULT")
                               else unit * np.array([.5, .75, 1, 1.5, 2, 3,
                                                     4.5, 7]))).astype(int)
        ks = ks[ks >= 1]
        if len(ks) < 3:
            continue
        si = int(np.argmin(np.abs(ks - stop)))
        ti = int(np.argmin(np.abs(ks - tgt)))
        n = len(B["c"])
        import pool as P
        sig = P.signal(F, n, feat, q, side)
        if sig is None or sig.sum() < 200:
            continue
        up, dn = hunt.tau(B, ks, tpx)
        r, hold, wt = hunt.outcomes(B, up, dn, si, ti, side, ks, tpx, tv)[:3]
        idx = hunt.nonoverlap(np.flatnonzero(sig), hold)
        if len(idx) < 30:
            continue
        days = pd.to_datetime(B["ts"][idx]).strftime("%Y-%m-%d")
        # THE BASELINE MUST BE PER REGIME, and the first version of this file
        # used one per-quarter baseline for both -- precisely the artifact its
        # own docstring warned about. Short-gamma sessions are
        # disproportionately DOWN sessions, so a short strategy beats an
        # all-days baseline on them for no reason but direction. The smoke run
        # duly showed every short family "working" in short gamma and every
        # long family in long gamma: beta wearing a regime costume.
        #
        # The baseline is now what the SAME bracket earns entered at every bar
        # OF THAT REGIME. What survives is conditioning, not drift.
        allday = pd.to_datetime(B["ts"]).strftime("%Y-%m-%d")
        lab = np.array([rmap.get(x, 0) for x in allday])
        base = {}
        for g in (1, -1):
            sel = lab == g
            base[g] = float(wt[sel].mean()) if sel.sum() > 200 else None
        for j, d in zip(idx, days):
            g = rmap.get(d)
            if g is None or base.get(g) is None:
                continue
            a = acc[g]
            a["w"] += int(wt[j]); a["n"] += 1
            a["b"] += base[g]; a["pnl"] += float(r[j]) - cost
        del up, dn
    out = {}
    for g in (1, -1):
        a = acc[g]
        if a["n"] < 100:
            continue
        p = a["w"] / a["n"]
        pall = a["b"] / a["n"]
        se = math.sqrt(max(pall * (1 - pall), 1e-9) / a["n"])
        out[g] = dict(n=a["n"], win=p, pall=pall, zd=(p - pall) / se,
                      dol=a["pnl"] / a["n"])
    return out


def main():
    t0 = time.time()
    rmap = regime_map()
    nlong = sum(1 for v in rmap.values() if v > 0)
    st = json.load(open(hunt.STATE))
    fams = families(st["rows"], NFAM)
    ntried = len(st["rows"]) * 2          # two subgroups per family now
    ceil = math.sqrt(2 * math.log(max(ntried, 2)))
    print(f"{len(rmap)} days ({nlong} long / {len(rmap)-nlong} short gamma), "
          f"{len(fams)} families, ceiling {ceil:.1f}σ", flush=True)

    res = []
    for i, (key, _z) in enumerate(fams):
        o = evaluate(key, rmap)
        if 1 in o and -1 in o:
            res.append((key, o))
            d = o[1]["zd"] - o[-1]["zd"]
            print(f"  {i+1}/{len(fams)} {key[2][:26]:26s} "
                  f"long {o[1]['zd']:+5.1f}σ ${o[1]['dol']:+5.2f} | "
                  f"short {o[-1]['zd']:+5.1f}σ ${o[-1]['dol']:+5.2f} | "
                  f"gap {d:+5.1f} ({(time.time()-t0)/60:.0f}m)", flush=True)

    # ---- the control: does a random day-labelling produce the same gap? ----
    rng = np.random.default_rng(0)
    days = list(rmap)
    floors = []
    for s in range(NSHUF):
        vals = rng.permutation(list(rmap.values()))
        shuf = dict(zip(days, vals))
        gaps = []
        for key, _z in fams[:max(6, len(fams) // 10)]:
            o = evaluate(key, shuf)
            if 1 in o and -1 in o:
                gaps.append(o[1]["zd"] - o[-1]["zd"])
        if gaps:
            floors.append(float(np.max(np.abs(gaps))))
        print(f"  shuffle {s+1}/{NSHUF}: max |gap| {floors[-1] if floors else 0:.2f}",
              flush=True)
    floor = float(np.mean(floors)) if floors else 0.0

    log("# Split by dealer gamma: does anything work in one regime?")
    log()
    log(f"Every study here measured an **average over two years**. A rule that "
        f"makes money when dealers are long gamma and loses when they are short "
        f"averages to near zero — which is exactly what every study reported. "
        f"The average was never evidence of no edge; it was evidence of not "
        f"conditioning. This is the first dataset that classifies the *day* "
        f"rather than describing the price, so it is the first time the "
        f"question can be asked.")
    log()
    log(f"`{len(rmap)}` sessions, **{nlong} long-gamma / {len(rmap)-nlong} "
        f"short**, from option prices alone. Gamma sign is pre-specified — not "
        f"fitted, no threshold to tune, zero is zero. The drift baseline is "
        f"computed **within each regime**, because short-gamma days skew down "
        f"and comparing against an all-days baseline would manufacture a result "
        f"from that alone.")
    log()
    log(f"Two subgroups instead of one doubles the draws, so the selection "
        f"ceiling is **{ceil:.1f}σ**. Splitting is not free.")
    log()
    log(f"**Shuffled-label floor: {floor:.2f}σ.** The day-to-regime map was "
        f"permuted {NSHUF} times and the whole split recomputed; that is the "
        f"regime gap random labelling produces. A real gap has to clear it.")
    log()
    res.sort(key=lambda kv: -abs(kv[1][1]["zd"] - kv[1][-1]["zd"]))
    log("| trigger | side | LONG gamma σ | $/trade | SHORT gamma σ | $/trade | "
        "**gap** |")
    log("|---|---|---|---|---|---|---|")
    for key, o in res[:25]:
        gap = o[1]["zd"] - o[-1]["zd"]
        mark = "**" if abs(gap) > max(floor, 1.0) else ""
        log(f"| {key[2][:34]} | {'L' if key[4] > 0 else 'S'} | "
            f"{o[1]['zd']:+.1f}σ | ${o[1]['dol']:+.2f} | "
            f"{o[-1]['zd']:+.1f}σ | ${o[-1]['dol']:+.2f} | {mark}{gap:+.1f}{mark} |")
    log()
    if res:
        gaps = np.array([o[1]["zd"] - o[-1]["zd"] for _, o in res])
        log(f"Across all {len(res)} families the median gap is "
            f"**{np.median(gaps):+.2f}σ** and {int((gaps > 0).sum())} of "
            f"{len(gaps)} lean the same way. A real regime effect shows up as "
            f"the same sign across unrelated families, beyond the shuffled "
            f"floor — one family flipping is noise with a story attached.")
    log()
    log(f"_Ran {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

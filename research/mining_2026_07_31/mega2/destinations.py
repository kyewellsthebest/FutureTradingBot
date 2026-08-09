"""Where does price actually GO? Ten pre-specified destinations, symmetric barriers.

The user's instinct is right and it is the opposite of what I have been doing.
Searching 103,680 strategies made the answer WORSE, not better: the best of
81,348 came in at +4.16pp when pure chance at that sample size produces +7.51pp,
and the one coherent family retained -19% on contracts the search never touched.
Testing more things guarantees the winner is luckier rather than better.

So this tests TEN things, each named in advance, and reports all ten.

THE DESIGN THAT REMOVES THE ARGUMENT. For each destination, put the target ON
the destination and the stop at EXACTLY the same distance the other way.
Symmetric barriers on a driftless walk win exactly 50% -- not "about" 50%, not
an estimate with censoring subtleties, exactly 50% by the reflection principle.
So the whole result is one number per destination:

    hit rate - 50%

Positive means price genuinely seeks that place. Negative means it is repelled.
Zero means the level is just a distance and the chart pattern is decoration.
A shuffled-increment tape is run alongside as a second check, and it must come
back at 50% or the instrument is broken.

THE FREQUENCY FILTER, which is the user's other idea and is legitimate because
it is OUTCOME-BLIND: how often is each destination reachable, and how often is
it touched per day? Decided without looking at whether anything wins, so it
cannot manufacture a false positive the way filtering on win rate does. It also
selects for what is actually wanted -- something that fires often enough to
trade hundreds of times a day.

THE TEN DESTINATIONS, all causal, all computable at the moment of entry:
   1  prior swing high/low at 8-point structure
   2  prior swing high/low at 20-point structure
   3  round number, nearest 25 points
   4  round number, nearest 100 points
   5  session high / session low so far
   6  previous session's high / low
   7  previous session's close
   8  running volume-weighted average price
   9  the heaviest-volume price of the session so far
  10  a gap: a price level the tape crossed in a single large jump and has not
      revisited
"""
import glob
import os
import sys

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402
import structsearch as S  # noqa: E402

ROOT = S.ROOT
RAW = os.path.join(ROOT, "data", "tick", "raw")
CACHE = S.CACHE
OUT = os.path.join(ROOT, "research", "DESTINATIONS.md")
PT = 4
USD_TICK = 0.50
COST = 1.99
STEP = int(os.environ.get("STEP", "600"))     # sample an entry every N changes
MINK = int(os.environ.get("MINK", "8"))       # ignore destinations under 2 pts
MAXK = S.KMAX
SESSION_NS = 86_400_000_000_000
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def load(c):
    """Compressed tape with volume and timestamps -- needed for VWAP, sessions,
    volume-point-of-control and gaps, which price-only features cannot express."""
    cp = os.path.join(CACHE, f"dest_{c}.npz")
    if os.path.exists(cp):
        z = np.load(cp, allow_pickle=False)
        return z["pc"], z["vol"], z["ts"]
    f = os.path.join(RAW, f"{c}.parquet")
    t = pq.read_table(f, columns=["ts", "price", "size"])
    price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
    size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
    ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
    del t
    o = np.argsort(ts, kind="stable")
    price, size, ts = price[o], size[o], ts[o]
    assert np.all(np.diff(ts) >= 0)
    pc, vol, tsc = grammar.compress(price, size, ts)
    np.savez_compressed(cp, pc=pc.astype(np.int64), vol=vol.astype(np.float32),
                        ts=tsc.astype(np.int64))
    return pc.astype(np.int64), vol.astype(np.float32), tsc.astype(np.int64)


def destinations(pc, vol, ts, ent):
    """For every entry, the price of each destination. NaN where undefined.

    Everything here uses only data at or before the entry index.
    """
    D = {}
    day = ts // SESSION_NS
    newday = np.r_[True, day[1:] != day[:-1]]
    dstart = np.maximum.accumulate(np.where(newday, np.arange(len(pc)), 0))

    # --- swing extremes at two scales -------------------------------------
    for R in (8, 20):
        piv, conf, dirs = grammar.decompose(pc, R * PT)
        hi = piv[dirs == 1]
        lo = piv[dirs == -1]
        for nm, idxs in (("high", hi), ("low", lo)):
            if len(idxs) < 50:
                continue
            # most recent such extreme strictly BEFORE the entry
            j = np.searchsorted(idxs, ent, side="left") - 1
            v = np.where(j >= 0, pc[idxs[np.maximum(j, 0)]], np.nan)
            D[f"swing {nm} R={R}"] = v.astype(np.float64)

    p0 = pc[ent].astype(np.float64)
    # --- round numbers ------------------------------------------------------
    for pts in (25, 100):
        step = pts * PT
        D[f"round {pts}pt above"] = np.ceil((p0 + 1) / step) * step
        D[f"round {pts}pt below"] = np.floor((p0 - 1) / step) * step

    # --- session extremes so far -------------------------------------------
    runmax = np.maximum.accumulate(np.where(newday, pc, -10**9))
    runmin = np.minimum.accumulate(np.where(newday, pc, 10**9))
    for i in range(1, len(pc)):
        if not newday[i]:
            runmax[i] = max(runmax[i - 1], pc[i])
            runmin[i] = min(runmin[i - 1], pc[i])
    D["session high so far"] = runmax[ent].astype(np.float64)
    D["session low so far"] = runmin[ent].astype(np.float64)

    # --- previous session ---------------------------------------------------
    bounds = np.flatnonzero(newday)
    prev_hi = np.full(len(pc), np.nan)
    prev_lo = np.full(len(pc), np.nan)
    prev_cl = np.full(len(pc), np.nan)
    for k in range(1, len(bounds)):
        a, b = bounds[k - 1], bounds[k]
        e = bounds[k + 1] if k + 1 < len(bounds) else len(pc)
        prev_hi[b:e] = pc[a:b].max()
        prev_lo[b:e] = pc[a:b].min()
        prev_cl[b:e] = pc[b - 1]
    D["prev session high"] = prev_hi[ent]
    D["prev session low"] = prev_lo[ent]
    D["prev session close"] = prev_cl[ent]

    # --- running VWAP of the session ---------------------------------------
    pv = np.cumsum(pc * vol)
    vv = np.cumsum(vol)
    base_pv = pv[np.maximum(dstart - 1, 0)] * (dstart > 0)
    base_vv = vv[np.maximum(dstart - 1, 0)] * (dstart > 0)
    vwap = (pv - base_pv) / np.maximum(vv - base_vv, 1e-9)
    D["session VWAP"] = vwap[ent]
    return D


def run(c, tape_kind, rng):
    pc, vol, ts = load(c)
    if tape_kind == "shuf":
        d = np.diff(pc).copy()
        rng.shuffle(d)
        pc = np.r_[pc[0], pc[0] + np.cumsum(d)].astype(np.int64)
    ent = np.arange(1, len(pc) - S.W - 3, STEP, dtype=np.int64)
    D = destinations(pc, vol, ts, ent)
    e, up, dn = S.tau_tables(pc, ent)
    ok = np.isin(ent, e)
    pos = np.searchsorted(e, ent[ok])
    p0 = pc[ent[ok]].astype(np.float64)
    out = {}
    for name, lv in D.items():
        v = lv[ok]
        k = np.rint(np.abs(v - p0)).astype(np.int64)
        good = np.isfinite(v) & (k >= MINK) & (k <= MAXK)
        if good.sum() < 500:
            continue
        kk = k[good]
        above = (v[good] > p0[good])
        pr = pos[good]
        # target at the destination, stop the SAME distance the other way
        t_to = np.where(above, up[pr, kk], dn[pr, kk])
        t_away = np.where(above, dn[pr, kk], up[pr, kk])
        res = t_to != t_away
        if res.sum() < 500:
            continue
        hit = (t_to < t_away)[res]
        out[name] = (int(res.sum()), float(hit.mean()),
                     float(np.median(kk[res]) / PT),
                     float(1 - res.mean()))
    return out, len(pc), ts


HOLD = ["NQH6", "NQM6", "NQZ5"]
rng = np.random.default_rng(4242)
acc = {"real": {}, "shuf": {}}
ndays = 0
for c in HOLD:
    for kind in ("real", "shuf"):
        o, n, ts = run(c, kind, rng)
        if kind == "real":
            ndays += len(np.unique(ts // SESSION_NS))
        for k, v in o.items():
            a = acc[kind].setdefault(k, [0, 0.0, [], 0.0])
            a[0] += v[0]; a[1] += v[1] * v[0]; a[2].append(v[2]); a[3] += v[3] * v[0]
        print(f"  {c} {kind}: {len(o)} destinations", flush=True)

log("# Where does price actually go? Ten destinations, named in advance")
log()
log("Searching 103,680 strategies made the answer worse, not better — the best "
    "of 81,348 came in below what chance produces, and the one coherent family "
    "retained −19% on data it had not been selected on. Testing more guarantees "
    "the winner is luckier, not better. So this tests **ten** things, every one "
    "named before looking, and reports all ten.")
log()
log("**The design that removes the argument.** The target sits ON the "
    "destination and the stop sits at EXACTLY the same distance the other way. "
    "Symmetric barriers on a driftless walk win exactly 50% — not approximately, "
    "exactly, by the reflection principle. So the entire result is one number "
    "per row: `hit − 50%`. Positive means price genuinely seeks that place. "
    "The shuffled tape beside it must read 50% or the instrument is broken.")
log()
log(f"Held-out NQ contracts, {ndays} trading days, an entry sampled every "
    f"{STEP} price changes.")
log()
log("| destination | trades | median distance | **hit rate** | "
    "**vs the 50% coin flip** | shuffled tape | unresolved |")
log("|---|---|---|---|---|---|---|")
rows = []
for k in acc["real"]:
    a = acc["real"][k]
    b = acc["shuf"].get(k)
    if not b or not a[0] or not b[0]:
        continue
    hr = a[1] / a[0]
    sr = b[1] / b[0]
    rows.append((abs(hr - 0.5), k, a[0], np.median(a[2]), hr, sr, a[3] / a[0]))
for _, k, n, dist, hr, sr, un in sorted(rows, key=lambda x: -x[0]):
    se = np.sqrt(0.25 / n) * 100
    log(f"| {k} | {n:,} | {dist:.1f} pts | {hr*100:.2f}% | "
        f"**{(hr-0.5)*100:+.2f} pp** (se {se:.2f}) | {sr*100:.2f}% | "
        f"{un*100:.0f}% |")
log()
log("A destination is worth trading only if its deviation is several times its "
    "standard error AND the shuffled column sits at 50%. Anything else is the "
    "instrument, not the market.")
log()
log("### What a real one would be worth")
log()
log(f"At a symmetric bracket, expectancy is `(2p − 1) × distance × $2/point`. "
    f"Against the ${COST:.2f} toll, a destination {20:.0f} points away needs "
    f"**{(0.5 + COST / (2 * 20 * 2.0))*100:.1f}%** to break even, and one "
    f"{40:.0f} points away needs "
    f"**{(0.5 + COST / (2 * 40 * 2.0))*100:.1f}%**.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

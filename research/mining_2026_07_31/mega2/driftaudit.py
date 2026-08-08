"""Is the surviving NQ leg-grammar cell a behaviour, or is it NQ going up?

The #1 open question. The sorted rerun left one cell standing: (-1,4,2,4,0) --
a large, fast, deeply-retraced, LOW-volume DOWN leg, traded LONG, holdout
+1.64/+2.12/+3.81 ticks at F=50/200/1000. Its short mirror (1,4,2,4,0) is
weak and flips negative at the long horizon.

That asymmetry is either information or it is drift. NQ rose across the whole
sample. A cell that is direction-signed inherits that rise: every long-side
cell gets a free positive and every short-side cell gets a free negative, and
the GLOBAL population baseline grammar.py subtracts cannot remove it, because
the global mean averages longs and shorts together and so cancels to roughly
zero while leaving the per-direction bias fully intact. This is the exact
mechanism that produced YM's 13/13 and RTY's 21/21 in the cross-market sweep.

So the test is simple and decisive. Re-score the cell against baselines that
absorb progressively more of the drift:

  A  global      -- what grammar.py did (all legs, both directions pooled)
  B  dir-matched -- all legs of the SAME direction. Removes market drift
                    exactly, because drift enters every same-direction leg
                    identically.
  C  dir x contract -- also removes per-contract regime, so a single trending
                    contract cannot carry the result.
  D  dir x contract x volume-tercile -- the strictest: the cell must beat
                    other legs that are also LOW volume, isolating the one
                    attribute the story rests on.

If the edge is real it shrinks somewhat from A to D and stays positive. If it
is drift it collapses at B, because B is the drift subtraction itself.

Reported per contract too: drift is a whole-contract property, so a real
behaviour should hold in contracts that FELL as well as ones that rose.

Runs single-threaded on purpose -- megatick owns the other cores.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("DELAY", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyarrow.parquet as pq  # noqa: E402

import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
OUT = os.path.join(ROOT, "research", "DRIFT_AUDIT.md")
R = int(os.environ.get("R", "4"))
USD_TICK = 0.50
TRAIN = set(os.environ.get("TRAIN_CONTRACTS",
                           "NQU4,NQZ4,NQH5,NQM5,NQU5").split(","))
CELLS = {"(-1,4,2,4,0) LONG after thin down-spike": (-1, 4, 2, 4, 0),
         "(1,4,2,4,0) SHORT after thin up-spike": (1, 4, 2, 4, 0)}
HZ = [50, 200, 1000]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


legs, drift = {}, {}
for f in sorted(glob.glob(os.path.join(RAW, "NQ*.parquet"))):
    c = os.path.basename(f).replace(".parquet", "")
    t = pq.read_table(f, columns=["ts", "price", "size"])
    price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
    size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
    ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
    del t
    o = np.argsort(ts, kind="stable")
    price, size, ts = price[o], size[o], ts[o]
    assert np.all(np.diff(ts) >= 0)
    pc, vol, tsc = grammar.compress(price, size, ts)
    # the contract's own drift, in ticks per price-change: this is the number
    # that leaks into every direction-signed cell.
    drift[c] = (pc[-1] - pc[0]) / len(pc)
    del price, size, ts
    d = grammar.leg_table(pc, vol, tsc, R)
    del pc, vol, tsc
    if d is None:
        continue
    d["contract"] = c
    legs[c] = d[["contract", "dir", "dist_n", "vel_n", "retr", "vol_n"]
                + [f"fwd{h}" for h in HZ]].copy()
    log(f"  {c}: {len(legs[c]):,} legs, drift {drift[c]*1e3:+.4f} "
        f"ticks per 1000 price-changes")
    del d

A = pd.concat(legs.values(), ignore_index=True)
del legs

pool = A[A.contract.isin(TRAIN)]
edges = {}
for col, nb in (("dist_n", 5), ("vel_n", 3), ("retr", 5), ("vol_n", 3)):
    v = pool[col].replace([np.inf, -np.inf], np.nan).dropna()
    edges[col] = np.quantile(v, np.linspace(0, 1, nb + 1)[1:-1])
del pool

for col in ("dist_n", "vel_n", "retr", "vol_n"):
    A[col + "_b"] = grammar.qbins(A[col].values, edges[col])
A["fin"] = np.isfinite(A[["dist_n", "vel_n", "retr", "vol_n"]].values).all(1)
A = A[A.fin]
A["oos"] = ~A.contract.isin(TRAIN)

log()
log("# Drift audit: is the NQ cell a behaviour, or is it NQ going up?")
log()
log("Every number is the cell's mean forward move MINUS a baseline, in ticks. "
    "The baselines absorb progressively more drift. A real behaviour survives "
    "column D; drift dies at column B, because B is the drift subtraction.")
log()
log(f"Contract drift (ticks per 1000 price-changes): " +
    ", ".join(f"{k} {v*1e3:+.3f}" for k, v in sorted(drift.items())))
log()
up = [k for k, v in drift.items() if v > 0]
log(f"{len(up)} of {len(drift)} contracts drifted UP. That is the bias a "
    f"direction-signed cell can rent without predicting anything.")
log()

for name, (dr, db, vb, rb, ob) in CELLS.items():
    sel = ((A.dir == dr) & (A.dist_n_b == db) & (A.vel_n_b == vb)
           & (A.retr_b == rb) & (A.vol_n_b == ob))
    same_dir = A.dir == dr
    log(f"## {name}")
    log()
    log(f"{int(sel.sum()):,} legs total, {int((sel & A.oos).sum()):,} in the "
        f"held-out contracts.")
    log()
    log("| horizon | split | A global | B dir-matched | C dir x contract | "
        "D dir x contract x volume | D in $ |")
    log("|---|---|---|---|---|---|---|")
    for h in HZ:
        col = f"fwd{h}"
        for split, mask in (("train", ~A.oos), ("HOLDOUT", A.oos)):
            s = sel & mask
            if not s.any():
                continue
            cell = A.loc[s, col].mean()
            bA = A.loc[mask, col].mean()
            bB = A.loc[same_dir & mask, col].mean()
            gc_ = A.loc[same_dir & mask].groupby("contract")[col].mean()
            wc = A.loc[s].groupby("contract")[col].size()
            wc = wc.reindex(gc_.index).fillna(0)
            bC = float((gc_ * wc).sum() / max(wc.sum(), 1))
            gd = A.loc[same_dir & mask].groupby(["contract", "vol_n_b"])[col].mean()
            wd = A.loc[s].groupby(["contract", "vol_n_b"]).size()
            wd = wd.reindex(gd.index).fillna(0)
            bD = float((gd * wd).sum() / max(wd.sum(), 1))
            log(f"| {h} | {split} | {cell - bA:+.3f} | {cell - bB:+.3f} | "
                f"{cell - bC:+.3f} | **{cell - bD:+.3f}** | "
                f"**${(cell - bD) * USD_TICK:+.2f}** |")
    log()
    # per contract under the strictest baseline, at the horizon that mattered
    h = 1000
    col = f"fwd{h}"
    log(f"Per contract at horizon {h}, baseline D, against that contract's "
        f"own drift:")
    log()
    log("| contract | legs | edge (ticks) | contract drift/1000 | held? |")
    log("|---|---|---|---|---|")
    agree = 0
    tot = 0
    for c in sorted(drift):
        s = sel & (A.contract == c)
        if s.sum() < 100:
            continue
        gd = A.loc[same_dir & (A.contract == c)].groupby("vol_n_b")[col].mean()
        wd = A.loc[s].groupby("vol_n_b").size().reindex(gd.index).fillna(0)
        b = float((gd * wd).sum() / max(wd.sum(), 1))
        e = A.loc[s, col].mean() - b
        tot += 1
        agree += int(e > 0)
        log(f"| {c} | {int(s.sum()):,} | {e:+.3f} | {drift[c]*1e3:+.3f} | "
            f"{'yes' if e > 0 else 'NO'} |")
    log()
    log(f"**{agree}/{tot} contracts positive** under the strictest baseline "
        f"(coin: {tot/2:.1f}).")
    log()

log("---")
log("Reading it: column A is what the original study reported. If B is much "
    "smaller than A, the original number was mostly the market rising. If D "
    "is still positive and most contracts agree, there is a behaviour left, "
    "and its size in dollars is the last column -- to be compared against "
    "$1.75 all-in per round turn, not against zero.")
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

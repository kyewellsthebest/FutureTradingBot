"""The one real behaviour is 13-25% short of costs. Close the gap or prove it can't be.

The drift audit confirmed a genuine NQ behaviour: after a large, fast,
deeply-retraced, LOW-volume DOWN spike, price continues up. 8/8 contracts,
survives a direction x contract x volume baseline, strongest in contracts
that FELL. Worth $0.80 / $0.97 / $1.52 gross at F=50/200/1000 against
$1.75-2.00 all-in. It loses by a quarter, not by an order of magnitude.

Searching harder is the wrong move -- ledger #19 measured selection-by-train-
score to be actively harmful, and this behaviour is already found. The right
move is to ask whether the TRADE around it is badly built, which is a
different question with only a handful of degrees of freedom:

  1  EXTREMENESS. The cell is four coarse bins. Inside it, is the edge flat,
     or does it concentrate in the most extreme instances? If it concentrates,
     a tighter definition trades less often for more per trade -- which is
     exactly what a cost problem needs.
  2  EXIT. F=50/200/1000 were arbitrary. Sweep the horizon properly and see
     where dollars per trade peaks, and whether the peak is a plateau (real)
     or a spike (fitted).
  3  ENTRY DELAY. Entry sits one price change past confirmation to kill the
     bid-ask bounce. Is 1 the right number, or is the behaviour still
     arriving at 2, 5, 20 -- which would mean the entry is early and paying
     for it?
  4  EXTRA CONDITIONS. Three attributes the original cell ignored --
     confirmation lag, leg length in price changes, leg duration -- are free
     to test and might separate the good instances from the bad.
  5  FREQUENCY. Whatever wins, how many trades per week does it fire, and
     what does that make per week on one micro contract? A $3 edge that
     fires twice a month is not a business.

Everything is chosen on the five TRAIN contracts and reported on the three
held-out ones. The train column is there to be ignored; the holdout column is
the answer. Costs are the measured $1.75 and the conservative $2.00.

Caches the decomposed tape so later studies do not repay the load.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.path.join(ROOT, "research", "SHARPEN.md")
R = int(os.environ.get("R", "4"))
USD = 0.50
COSTS = (1.75, 2.00)
TRAIN = set("NQU4,NQZ4,NQH5,NQM5,NQU5".split(","))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def get(c, f):
    """Compressed tape + leg attributes, cached. Sorted and asserted."""
    p = os.path.join(CACHE, f"{c}_R{R}.npz")
    if os.path.exists(p):
        z = np.load(p, allow_pickle=False)
        return z["pc"], {k: z[k] for k in z.files if k != "pc"}
    t = pq.read_table(f, columns=["ts", "price", "size"])
    price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
    size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
    ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
    del t
    o = np.argsort(ts, kind="stable")
    price, size, ts = price[o], size[o], ts[o]
    assert np.all(np.diff(ts) >= 0)
    pc, vol, tsc = grammar.compress(price, size, ts)
    del price, size, ts
    d = grammar.leg_table(pc, vol, tsc, R)
    cols = ["conf", "dir", "dist_n", "vel_n", "retr", "vol_n", "nchg_n",
            "dur_n", "conf_lag"]
    D = {k: d[k].values.astype(np.float64) for k in cols if k in d}
    D["tsconf"] = tsc[d.conf.values.astype(np.int64)].astype(np.float64)
    os.makedirs(CACHE, exist_ok=True)
    np.savez_compressed(p, pc=pc, **D)
    return pc, D


tapes, legs = {}, {}
for f in sorted(glob.glob(os.path.join(RAW, "NQ*.parquet"))):
    c = os.path.basename(f)[:-8]
    pc, D = get(c, f)
    tapes[c] = pc
    legs[c] = pd.DataFrame(D)
    legs[c]["contract"] = c
    print(f"  {c}: {len(pc):,} price changes, {len(legs[c]):,} legs",
          flush=True)

A = pd.concat(legs.values(), ignore_index=True)
A["oos"] = ~A.contract.isin(TRAIN)
tr_pool = A[~A.oos]
edges = {}
for col, nb in (("dist_n", 5), ("vel_n", 3), ("retr", 5), ("vol_n", 3)):
    v = tr_pool[col].replace([np.inf, -np.inf], np.nan).dropna()
    edges[col] = np.quantile(v, np.linspace(0, 1, nb + 1)[1:-1])
for col in ("dist_n", "vel_n", "retr", "vol_n"):
    A[col + "_b"] = grammar.qbins(A[col].values, edges[col])
A = A[np.isfinite(A[["dist_n", "vel_n", "retr", "vol_n"]].values).all(1)]

BASE = ((A.dir == -1) & (A.dist_n_b == 4) & (A.vel_n_b == 2)
        & (A.retr_b == 4) & (A.vol_n_b == 0))


def outcomes(sub, delay, F):
    """Net move in ticks for each selected leg, at a given entry delay and
    horizon, signed so positive means the behaviour happened."""
    out = np.full(len(sub), np.nan)
    for c, g in sub.groupby("contract", sort=False):
        pc = tapes[c]
        ent = np.minimum(g.conf.values.astype(np.int64) + delay, len(pc) - 1)
        tgt = np.minimum(ent + F, len(pc) - 1)
        ok = ent + F < len(pc)
        v = (pc[tgt] - pc[ent]) * (-g["dir"].values)
        out[sub.index.get_indexer(g.index)] = np.where(ok, v, np.nan)
    return out


def dedrift(sub, vals, F, delay):
    """Same direction x contract x volume-tercile baseline the audit used."""
    adj = np.array(vals, float)
    for (c, vb), g in sub.groupby(["contract", "vol_n_b"], sort=False):
        pool = A[(A.contract == c) & (A.vol_n_b == vb)
                 & (A.dir == sub["dir"].iloc[0])]
        if len(pool) < 200:
            continue
        b = np.nanmean(outcomes(pool, delay, F))
        if np.isfinite(b):
            adj[sub.index.get_indexer(g.index)] -= b
    return adj


def cell_stat(mask, delay, F):
    sub = A[mask].copy()
    if len(sub) < 200:
        return None
    sub = sub.reset_index(drop=True)
    raw = outcomes(sub, delay, F)
    adj = dedrift(sub, raw, F, delay)
    r = {}
    for name, m in (("train", ~sub.oos.values), ("hold", sub.oos.values)):
        v = adj[m & np.isfinite(adj)]
        r[name] = (float(np.mean(v)) * USD if len(v) else np.nan, int(len(v)))
    return r


log("# Sharpening the one real behaviour")
log()
log(f"{int(BASE.sum()):,} instances of the confirmed cell across 8 NQ "
    f"contracts. Every number below is **net dollars per trade on one micro "
    f"contract, after the direction x contract x volume baseline** — the same "
    f"correction that proved the behaviour is not drift. Choices are made on "
    f"the five training contracts; the HOLDOUT column is the answer.")
log()

# ---- 1. exit horizon -------------------------------------------------------
log("## 1. Where does the money actually peak? (exit horizon)")
log()
log("| hold (price changes) | train $ | HOLDOUT $ | HOLDOUT net @ $1.75 | "
    "@ $2.00 |")
log("|---|---|---|---|---|")
best_f, best_v = None, -9e9
for F in (25, 50, 100, 200, 400, 700, 1000, 1500, 2500, 4000):
    r = cell_stat(BASE, 1, F)
    if not r:
        continue
    h = r["hold"][0]
    log(f"| {F} | ${r['train'][0]:+.2f} | **${h:+.2f}** | "
        f"${h - 1.75:+.2f} | ${h - 2.00:+.2f} |")
    if r["train"][0] > best_v:
        best_v, best_f = r["train"][0], F
log()
log(f"Chosen on train: **F = {best_f}**. A single spiking horizon would be a "
    f"fitted number; a plateau is a real one — read the shape of the column, "
    f"not its maximum.")
log()

# ---- 2. entry delay --------------------------------------------------------
log("## 2. Is the entry too early? (delay past confirmation)")
log()
log("| delay | train $ | HOLDOUT $ | reading |")
log("|---|---|---|---|")
for dl in (0, 1, 2, 5, 10, 25, 50):
    r = cell_stat(BASE, dl, best_f)
    if not r:
        continue
    note = ("bounce-contaminated" if dl == 0 else
            "the audited entry" if dl == 1 else "")
    log(f"| {dl} | ${r['train'][0]:+.2f} | **${r['hold'][0]:+.2f}** | {note} |")
log()
log("If the number barely falls from delay 1 to delay 25, the behaviour is "
    "slow and there is no rush — which also means a limit order can be used "
    "instead of crossing the spread, and that is worth more than any of these "
    "cents.")
log()

# ---- 3. extremeness --------------------------------------------------------
log("## 3. Does the edge concentrate in the extreme instances?")
log()
for col, label in (("dist_n", "how big the down-leg was"),
                   ("vel_n", "how fast it was"),
                   ("retr", "how deeply it retraced the prior leg"),
                   ("vol_n", "how thin the volume was (LOW is the cell)")):
    sub = A[BASE]
    q = sub[col].replace([np.inf, -np.inf], np.nan)
    cuts = np.nanquantile(q[~sub.oos], [0.25, 0.5, 0.75])
    log(f"**{col}** — {label}")
    log()
    log("| quartile within the cell | n | train $ | HOLDOUT $ |")
    log("|---|---|---|---|")
    for i, (lo, hi) in enumerate(zip([-np.inf] + list(cuts),
                                     list(cuts) + [np.inf])):
        m = BASE & (A[col] > lo) & (A[col] <= hi)
        r = cell_stat(m, 1, best_f)
        if not r:
            continue
        log(f"| Q{i+1} | {r['train'][1] + r['hold'][1]:,} | "
            f"${r['train'][0]:+.2f} | **${r['hold'][0]:+.2f}** |")
    log()

# ---- 4. extra conditions ---------------------------------------------------
log("## 4. Three attributes the original cell never looked at")
log()
log("| extra condition | n | train $ | HOLDOUT $ | HOLDOUT net @ $1.75 |")
log("|---|---|---|---|---|")
extras = []
for col in ("nchg_n", "dur_n", "conf_lag"):
    if col not in A:
        continue
    sub = A[BASE]
    med = np.nanmedian(sub.loc[~sub.oos, col].replace([np.inf, -np.inf],
                                                      np.nan))
    for op, lab in ((">", "above median"), ("<=", "at or below median")):
        m = BASE & ((A[col] > med) if op == ">" else (A[col] <= med))
        r = cell_stat(m, 1, best_f)
        if not r:
            continue
        extras.append((r["hold"][0], f"{col} {lab}"))
        log(f"| {col} {lab} (={med:.2f}) | {r['train'][1] + r['hold'][1]:,} | "
            f"${r['train'][0]:+.2f} | **${r['hold'][0]:+.2f}** | "
            f"${r['hold'][0] - 1.75:+.2f} |")
log()

# ---- 5. what it would earn -------------------------------------------------
log("## 5. So what does it pay per week?")
log()
sub = A[BASE].copy()
ts = pd.to_datetime(sub.tsconf.values.astype("int64"))
weeks = pd.Series(ts).dt.to_period("W").nunique()
r = cell_stat(BASE, 1, best_f)
n_ho = r["hold"][1]
ho_weeks = pd.Series(pd.to_datetime(
    sub[sub.oos].tsconf.values.astype("int64"))).dt.to_period("W").nunique()
per_wk = n_ho / max(ho_weeks, 1)
log("| | value |")
log("|---|---|")
log(f"| signals, held-out contracts | {n_ho:,} over {ho_weeks} weeks |")
log(f"| signals per week | {per_wk:.1f} |")
for cost in COSTS:
    net = r["hold"][0] - cost
    log(f"| **$/week at ${cost:.2f} cost, 1 micro** | **${net * per_wk:+,.0f}** |")
edge_net = r["hold"][0] - 1.75
need = ("impossible at this edge — it is negative after costs" if edge_net <= 0
        else f"{1000 / (edge_net * per_wk):.0f} micro contracts")
log(f"| contracts needed for $1,000/wk | {need} |")
log()
log("Signals here overlap; a real account trades one position at a time, so "
    "the true frequency is lower and megaverify's replay is the number to "
    "trust. This table is the ceiling, not the forecast.")
log()
log("---")
log("Nothing above re-searched anything. The behaviour was already found and "
    "already validated; these are the trade-construction choices around it, "
    "made on training contracts and reported out of sample.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

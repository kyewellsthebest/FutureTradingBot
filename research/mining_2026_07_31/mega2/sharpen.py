"""The one real behaviour is 13-25% short of costs. Close the gap or prove it can't be.

The drift audit confirmed a genuine NQ behaviour: after a large, fast,
deeply-retraced, LOW-volume DOWN spike, price continues up. 8/8 contracts,
survives a direction x contract x volume baseline, strongest in the contracts
that FELL. Worth $0.80 / $0.97 / $1.52 gross at F=50/200/1000 against
$1.75-2.00 all-in. It loses by a quarter, not by an order of magnitude.

Searching harder is the wrong move -- ledger #19 measured selection-by-train-
score to be actively harmful, and this behaviour is already found. The right
question is whether the TRADE around it is badly built, which has only a
handful of degrees of freedom:

  1  EXIT. F=50/200/1000 were arbitrary. Sweep the horizon and see where
     dollars per trade peaks, and whether the peak is a plateau (real) or a
     spike (fitted).
  2  ENTRY DELAY. Entry sits one price change past confirmation to kill the
     bid-ask bounce. If the edge is still there at delay 25, the behaviour is
     slow, a limit order can replace crossing the spread, and that single
     fact is worth more than every parameter in this file.
  3  EXTREMENESS. The cell is four coarse bins. Inside it, is the edge flat or
     concentrated in the extreme instances? Concentration is exactly what a
     cost problem needs: fewer trades, more dollars each.
  4  EXTRA CONDITIONS. Three attributes the original cell ignored --
     confirmation lag, leg length in price changes, leg duration.
  5  FREQUENCY. Whatever wins, what does it pay per week on one micro?

Everything is chosen on the five TRAIN contracts and reported on the three
held-out ones. Baselines are the same direction x contract x volume-tercile
correction the drift audit used, so nothing here can be rented from a trend.

Array hot paths and int32 tapes on purpose: the DataFrame version needed
11 GB and recomputed the same baselines 936 times.
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
ATTRS = ["dist_n", "vel_n", "retr", "vol_n", "nchg_n", "dur_n", "conf_lag"]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def build(c, f):
    p = os.path.join(CACHE, f"{c}_R{R}.npz")
    if not os.path.exists(p):
        t = pq.read_table(f, columns=["ts", "price", "size"])
        price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
        size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
        ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
        del t
        o = np.argsort(ts, kind="stable")
        price, size, ts = price[o], size[o], ts[o]
        assert np.all(np.diff(ts) >= 0), f"{c} not monotone"
        pc, vol, tsc = grammar.compress(price, size, ts)
        del price, size, ts
        d = grammar.leg_table(pc, vol, tsc, R)
        D = {k: d[k].values.astype(np.float64) for k in ATTRS if k in d}
        D["conf"] = d.conf.values.astype(np.int64)
        D["dir"] = d["dir"].values.astype(np.int64)
        D["tsconf"] = tsc[d.conf.values.astype(np.int64)]
        os.makedirs(CACHE, exist_ok=True)
        np.savez_compressed(p, pc=pc, **D)
        del d, D, pc, vol, tsc
    z = np.load(p, allow_pickle=False)
    tape = z["pc"].astype(np.int32)                 # price in ticks fits int32
    cols = {k: z[k].astype(np.float32) for k in ATTRS if k in z.files}
    cols["conf"] = z["conf"].astype(np.int64)
    cols["dir"] = z["dir"].astype(np.int8)
    cols["tsconf"] = z["tsconf"].astype(np.int64)
    return tape, cols


names, tapes, parts = [], [], []
for f in sorted(glob.glob(os.path.join(RAW, "NQ*.parquet"))):
    c = os.path.basename(f)[:-8]
    tape, cols = build(c, f)
    names.append(c)
    tapes.append(tape)
    parts.append(cols)
    print(f"  {c}: {len(tape):,} price changes, {len(cols['conf']):,} legs",
          flush=True)

CID = np.concatenate([np.full(len(p["conf"]), i, np.int8)
                      for i, p in enumerate(parts)])
COL = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
del parts
NL = len(CID)
TAPELEN = np.array([len(t) for t in tapes], np.int64)
OOS = ~np.array([n in TRAIN for n in names], bool)[CID.astype(int)]

# bins from the training contracts only, exactly as the audit built them
BINS = {}
for col, nb in (("dist_n", 5), ("vel_n", 3), ("retr", 5), ("vol_n", 3)):
    v = COL[col][~OOS]
    v = v[np.isfinite(v)]
    e = np.quantile(v, np.linspace(0, 1, nb + 1)[1:-1])
    BINS[col] = grammar.qbins(COL[col], e)

FIN = np.isfinite(np.column_stack([COL[c] for c in
                                   ("dist_n", "vel_n", "retr", "vol_n")])).all(1)
BASE = (FIN & (COL["dir"] == -1) & (BINS["dist_n"] == 4) & (BINS["vel_n"] == 2)
        & (BINS["retr"] == 4) & (BINS["vol_n"] == 0))

_oc = {}


def outcomes(delay, F):
    """Signed forward move for EVERY leg at this entry delay and horizon."""
    key = (delay, F)
    if key in _oc:
        return _oc[key]
    out = np.full(NL, np.nan, np.float32)
    for i, tape in enumerate(tapes):
        s = CID == i
        conf = COL["conf"][s]
        n = len(tape)
        ent = np.minimum(conf + delay, n - 1)
        tgt = np.minimum(ent + F, n - 1)
        v = (tape[tgt].astype(np.float64)
             - tape[ent].astype(np.float64)) * (-COL["dir"][s])
        out[s] = np.where(conf + delay + F < n, v, np.nan)
    if len(_oc) > 3:
        _oc.pop(next(iter(_oc)))
    _oc[key] = out
    return out


_bl = {}


def adjusted(delay, F, dirv=-1):
    """Outcomes minus the direction x contract x volume-tercile baseline."""
    key = (delay, F, dirv)
    if key in _bl:
        return _bl[key]
    raw = outcomes(delay, F)
    adj = raw.copy()
    pool = (COL["dir"] == dirv) & np.isfinite(raw)
    grp = CID.astype(np.int32) * 8 + BINS["vol_n"].astype(np.int32)
    ng = grp.max() + 1
    cnt = np.bincount(grp[pool], minlength=ng)
    tot = np.bincount(grp[pool], weights=raw[pool].astype(np.float64),
                      minlength=ng)
    mean = np.where(cnt >= 200, tot / np.maximum(cnt, 1), 0.0)
    adj = raw - mean[grp].astype(np.float32)
    if len(_bl) > 3:
        _bl.pop(next(iter(_bl)))
    _bl[key] = adj
    return adj


def stat(mask, delay, F):
    adj = adjusted(delay, F)
    ok = mask & np.isfinite(adj)
    if ok.sum() < 200:
        return None
    a, b = ok & ~OOS, ok & OOS
    return (float(adj[a].mean()) * USD if a.sum() else np.nan, int(a.sum()),
            float(adj[b].mean()) * USD if b.sum() else np.nan, int(b.sum()))


log("# Sharpening the one real behaviour")
log()
log(f"{int(BASE.sum()):,} instances of the confirmed cell across "
    f"{len(names)} NQ contracts, {int((BASE & OOS).sum()):,} of them in the "
    f"three held-out ones. Every number is **net dollars per trade on one "
    f"micro contract after the direction x contract x volume baseline** — the "
    f"same correction that proved the behaviour is not drift. Choices are "
    f"made on the training contracts; the HOLDOUT column is the answer.")
log()

log("## 1. Where does the money actually peak? (exit horizon)")
log()
log("| hold (price changes) | train $ | HOLDOUT $ | net @ $1.75 | net @ $2.00 |")
log("|---|---|---|---|---|")
best_f, best_v = 200, -9e9
for F in (25, 50, 100, 200, 400, 700, 1000, 1500, 2500, 4000):
    r = stat(BASE, 1, F)
    if not r:
        continue
    log(f"| {F} | ${r[0]:+.2f} | **${r[2]:+.2f}** | ${r[2]-1.75:+.2f} | "
        f"${r[2]-2.00:+.2f} |")
    if r[0] > best_v:
        best_v, best_f = r[0], F
log()
log(f"Chosen on training data alone: **F = {best_f}**. Read the shape of the "
    f"column rather than its maximum — a lone spike is a fitted number, a "
    f"plateau is a real one.")
log()

log("## 2. Is the entry too early? (delay past confirmation)")
log()
log("| delay | train $ | HOLDOUT $ | n (holdout) | note |")
log("|---|---|---|---|---|")
d1 = None
for dl in (0, 1, 2, 5, 10, 25, 50, 100):
    r = stat(BASE, dl, best_f)
    if not r:
        continue
    if dl == 1:
        d1 = r[2]
    note = ("bid-ask bounce still in it" if dl == 0 else
            "the audited entry" if dl == 1 else
            f"{(r[2]/d1*100 - 100):+.0f}% vs delay 1" if d1 else "")
    log(f"| {dl} | ${r[0]:+.2f} | **${r[2]:+.2f}** | {r[3]:,} | {note} |")
log()
log("This is the most valuable row in the file. If the edge is still there "
    "25 or 50 price changes after confirmation, the behaviour is slow enough "
    "to enter with a resting limit order instead of crossing the spread — and "
    "not crossing is worth about a tick, which is $0.50, which is larger than "
    "the entire shortfall.")
log()

log("## 3. Does the edge concentrate in the extreme instances?")
log()
for col, label in (("dist_n", "how big the down-leg was"),
                   ("vel_n", "how fast it was"),
                   ("retr", "how deeply it retraced the prior leg"),
                   ("vol_n", "how thin the volume was — LOW is the cell")):
    v = COL[col]
    tv = v[BASE & ~OOS]
    tv = tv[np.isfinite(tv)]
    if len(tv) < 400:
        continue
    cuts = np.quantile(tv, [0.25, 0.5, 0.75])
    log(f"**{col}** — {label}")
    log()
    log("| quartile within the cell | n | train $ | HOLDOUT $ | net @ $1.75 |")
    log("|---|---|---|---|---|")
    for i, (lo, hi) in enumerate(zip([-np.inf] + list(cuts),
                                     list(cuts) + [np.inf])):
        r = stat(BASE & (v > lo) & (v <= hi), 1, best_f)
        if not r:
            continue
        log(f"| Q{i+1} | {r[1]+r[3]:,} | ${r[0]:+.2f} | **${r[2]:+.2f}** | "
            f"${r[2]-1.75:+.2f} |")
    log()

log("## 4. Three attributes the original cell never looked at")
log()
log("| extra condition | n | train $ | HOLDOUT $ | net @ $1.75 |")
log("|---|---|---|---|---|")
for col in ("nchg_n", "dur_n", "conf_lag"):
    if col not in COL:
        continue
    v = COL[col]
    tv = v[BASE & ~OOS]
    tv = tv[np.isfinite(tv)]
    if len(tv) < 400:
        continue
    med = float(np.median(tv))
    for op, lab in ((">", "above median"), ("<=", "at or below median")):
        m = BASE & ((v > med) if op == ">" else (v <= med))
        r = stat(m, 1, best_f)
        if not r:
            continue
        log(f"| {col} {lab} ({med:.2f}) | {r[1]+r[3]:,} | ${r[0]:+.2f} | "
            f"**${r[2]:+.2f}** | ${r[2]-1.75:+.2f} |")
log()

log("## 5. So what would it pay per week?")
log()
r = stat(BASE, 1, best_f)
tsh = pd.to_datetime(COL["tsconf"][BASE & OOS])
wks = pd.Series(tsh).dt.to_period("W").nunique()
per_wk = r[3] / max(wks, 1)
log("| | value |")
log("|---|---|")
log(f"| signals, held-out contracts | {r[3]:,} over {wks} weeks |")
log(f"| signals per week | {per_wk:.1f} |")
log(f"| holdout $/trade | **${r[2]:+.2f}** |")
for cost in COSTS:
    log(f"| **$/week at ${cost:.2f} cost, 1 micro** | "
        f"**${(r[2]-cost)*per_wk:+,.0f}** |")
net = r[2] - 1.75
log(f"| contracts needed for $1,000/wk | "
    f"{'impossible at this edge — negative after costs' if net <= 0 else f'{1000/(net*per_wk):.0f} micros'} |")
log()
log("Signals overlap; a real account holds one position at a time, so true "
    "frequency is lower. This is the ceiling, not the forecast.")
log()
log("---")
log("Nothing above re-searched anything. The behaviour was already found and "
    "already validated against drift; these are the trade-construction "
    "choices around it, made on training contracts and reported out of "
    "sample.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)

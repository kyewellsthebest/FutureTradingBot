"""Round 65: QUOTE FEATURE FACTORY + PREDICTIVE DECAY MAP.
Mission: quotes as the PRIMARY signal (completely different strategy
class). Before simulating anything, measure what the book actually
knows and for how long:

Phase A - IC map: on a 250ms grid over every ticks+quotes overlap
day, compute book features (spread, depth, microprice tilt, size
imbalance at 1s/10s/60s, quote rate, depth-vacuum ratio) and their
rank correlation with forward MID returns at 1s/5s/30s/2m/15m.
Directional features -> signed return; stress features -> both
|return| (does stress predict movement?) and continuation (stress x
current move direction).

Phase B - latency decay: for the standout event types (liquidity
vacuum, extreme tilt, extreme imb60), event-level forward returns
measured from t+latency for latency 0/30/65/100/200/500ms - the
exact "how fast do we need to be" curve the user asked for.
"""
import glob, json, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq
from scipy.stats import spearmanr

QDIR = "/tmp/claude-0/quotes"
TICK = 0.25
GRID_NS = 250_000_000
SESS_LO, SESS_HI = 14.0, 20.9
HORIZONS = [("1s", 1), ("5s", 5), ("30s", 30), ("2m", 120), ("15m", 900)]
LATS = [0, 30, 65, 100, 200, 500]      # ms
EVT_H = [("2s", 2), ("10s", 10), ("60s", 60), ("5m", 300)]


def load_day(f):
    t = pq.read_table(f)
    qts = t.column("ts").to_numpy()
    bid = t.column("bid").to_numpy()
    ask = t.column("ask").to_numpy()
    bs = t.column("bid_size").to_numpy().astype(np.float64)
    asz = t.column("ask_size").to_numpy().astype(np.float64)
    del t
    o = np.argsort(qts, kind="stable")
    qts, bid, ask = qts[o], bid[o], ask[o]
    bs, asz = bs[o], asz[o]
    ok = (ask > bid) & (bid > 0)
    return qts[ok], bid[ok], ask[ok], bs[ok], asz[ok]


def day_features(qts, bid, ask, bs, asz):
    """250ms grid over the RTH session; all features causal."""
    day0 = (qts[0] // 86_400_000_000_000) * 86_400_000_000_000
    t0 = day0 + int(SESS_LO * 3600e9)
    t1 = day0 + int(SESS_HI * 3600e9)
    grid = np.arange(t0, t1, GRID_NS)
    j = np.searchsorted(qts, grid, "right") - 1
    v = j >= 0
    grid, j = grid[v], j[v]
    mid = (bid[j] + ask[j]) / 2
    spread = ask[j] - bid[j]
    depth = bs[j] + asz[j]
    micro = (bid[j] * asz[j] + ask[j] * bs[j]) / np.maximum(depth, 1.0)
    tilt = (micro - mid) / np.maximum(spread, TICK)
    cb, ca = np.concatenate(([0.0], np.cumsum(bs))), \
        np.concatenate(([0.0], np.cumsum(asz)))
    F = dict(spread=spread, depth=depth, tilt=tilt)
    for tag, w in (("imb1", 1), ("imb10", 10), ("imb60", 60)):
        k = np.searchsorted(qts, grid - int(w * 1e9), "right") - 1
        k = np.maximum(k, 0)
        b_ = cb[j + 1] - cb[k]; a_ = ca[j + 1] - ca[k]
        F[tag] = b_ / np.maximum(b_ + a_, 1.0) - 0.5
        if tag == "imb10":
            nq = (j - k).astype(np.float64)
            F["qrate10"] = nq / 10.0
            F["dep10"] = (b_ + a_) / np.maximum(nq, 1.0)
    F["vac"] = depth / np.maximum(F["dep10"], 1.0)      # <1 = thin now
    F["sstress"] = spread / np.maximum(
        pd.Series(spread).rolling(40, min_periods=1).median().to_numpy(),
        TICK)
    k1 = np.maximum(np.searchsorted(qts, grid - int(1e9), "right") - 1, 0)
    F["mom1s"] = mid - (bid[k1] + ask[k1]) / 2
    return grid, j, mid, F


def ic_one(f, r):
    m = np.isfinite(f) & np.isfinite(r)
    if m.sum() < 500:
        return np.nan
    return spearmanr(f[m], r[m]).statistic


def main():
    t0 = time.time()
    files = sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet"))
    ics = {}          # (feat, hz, kind) -> list of daily IC
    evt = {}          # (evtname, lat, hz) -> [sum_ret, sum_hit, n]
    ndays = 0
    for f in files:
        d = f.split("_")[-1][:8]
        wd = pd.Timestamp(d).dayofweek
        if wd >= 5:
            continue
        qts, bid, ask, bs, asz = load_day(f)
        if len(qts) < 1_000_000:
            print(f"  {d}: thin ({len(qts)}) skip", flush=True)
            continue
        grid, j, mid, F = day_features(qts, bid, ask, bs, asz)
        ndays += 1
        # ---- Phase A: IC map (grid-based, latency 0)
        for hz, hs in HORIZONS:
            jf = np.searchsorted(qts, grid + int(hs * 1e9), "right") - 1
            ok = jf < len(qts) - 1
            fwd = np.where(ok, (bid[jf] + ask[jf]) / 2 - mid, np.nan)
            for feat in ("tilt", "imb1", "imb10", "imb60"):
                ics.setdefault((feat, hz, "dir"), []).append(
                    ic_one(F[feat], fwd))
            for feat in ("spread", "vac", "sstress", "qrate10", "depth"):
                ics.setdefault((feat, hz, "mag"), []).append(
                    ic_one(F[feat], np.abs(fwd)))
                cont = fwd * np.sign(F["mom1s"])
                ics.setdefault((feat, hz, "cont"), []).append(
                    ic_one(F[feat], cont))
        # ---- Phase B: events with latency grid
        med_dep = np.nanmedian(F["dep10"])
        events = {
            "VACUUM": (F["vac"] < 0.4) & (F["sstress"] >= 2.0)
                      & (np.abs(F["mom1s"]) > 0),
            "TILT+": np.abs(F["tilt"]) > 0.35,
            "IMB60x": np.abs(F["imb60"]) > 0.10,
            "THIN10": F["dep10"] < 0.5 * med_dep,
        }
        dirs = {
            "VACUUM": np.sign(F["mom1s"]),           # continuation
            "TILT+": np.sign(F["tilt"]),             # toward microprice
            "IMB60x": np.sign(F["imb60"]),           # toward heavy side
            "THIN10": np.sign(F["mom1s"]),
        }
        for nm, mask in events.items():
            idx = np.flatnonzero(mask & (dirs[nm] != 0))
            if not len(idx):
                continue
            keep = [int(idx[0])]
            for i in idx[1:]:
                if grid[i] - grid[keep[-1]] > 30_000_000_000:
                    keep.append(int(i))
            keep = np.array(keep)
            s = dirs[nm][keep]
            for lat in LATS:
                ja = np.searchsorted(qts, grid[keep] + lat * 1_000_000,
                                     "right") - 1
                m0 = (bid[ja] + ask[ja]) / 2
                for hz, hs in EVT_H:
                    jb = np.searchsorted(
                        qts, grid[keep] + lat * 1_000_000 + int(hs * 1e9),
                        "right") - 1
                    ok = jb < len(qts) - 1
                    r = ((bid[jb] + ask[jb]) / 2 - m0) * s
                    key = (nm, lat, hz)
                    a = evt.setdefault(key, [0.0, 0, 0])
                    a[0] += float(r[ok].sum())
                    a[1] += int((r[ok] > 0).sum())
                    a[2] += int(ok.sum())
        print(f"  {d}: {len(grid):,} grid pts done "
              f"({time.time()-t0:.0f}s)", flush=True)
        del qts, bid, ask, bs, asz, F
    # ---------------- report
    print(f"\n==== PHASE A: IC MAP ({ndays} days, mean daily Spearman; "
          f"|IC|>~0.02 with |t|>3 is interesting) ====", flush=True)
    print(f"{'feature':<10} {'kind':<5}" +
          "".join(f" {hz:>8}" for hz, _ in HORIZONS))
    feats = sorted({(f_, k_) for f_, _, k_ in ics})
    for f_, k_ in feats:
        row = f"{f_:<10} {k_:<5}"
        for hz, _ in HORIZONS:
            v = np.array(ics.get((f_, hz, k_), [np.nan]), float)
            v = v[np.isfinite(v)]
            if len(v):
                mu, se = v.mean(), v.std() / max(np.sqrt(len(v)), 1)
                t_ = mu / se if se > 0 else 0
                row += f" {mu:+.3f}" + (f"*" if abs(t_) > 3 else " ")
                row += f"{'':>1}"
            else:
                row += f" {'--':>8}"
        print(row, flush=True)
    print(f"\n==== PHASE B: EVENT LATENCY DECAY (fwd mid move in pts, "
          f"in event direction) ====", flush=True)
    for nm in ("VACUUM", "TILT+", "IMB60x", "THIN10"):
        n_ = evt.get((nm, 0, "2s"), [0, 0, 0])[2]
        print(f"\n{nm}  (n~{n_} events, de-clustered 30s)")
        print(f"  {'lat':>6}" + "".join(f" {hz:>16}" for hz, _ in EVT_H))
        for lat in LATS:
            row = f"  {lat:>4}ms"
            for hz, _ in EVT_H:
                a = evt.get((nm, lat, hz))
                if a and a[2]:
                    row += f" {a[0]/a[2]:+7.3f}p {a[1]/a[2]*100:3.0f}%   "
                else:
                    row += f" {'--':>16}"
            print(row, flush=True)
    with open("research/round65_results.json", "w") as fo:
        json.dump({"ics": {f"{a}|{b}|{c}": v for (a, b, c), v in
                           ics.items()},
                   "evt": {f"{a}|{b}|{c}": v for (a, b, c), v in
                           evt.items()}, "ndays": ndays}, fo, indent=1)
    print(f"\nDONE {ndays} days ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

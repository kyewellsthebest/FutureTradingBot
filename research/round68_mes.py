"""Round 68: MES QUOTE HUNT + CROSS-BOOK (the untried avenue).
31 days of real MES top-of-book (Jun 17 - Jul 17), MES ticks to
Jul 7. Three questions:
  A. MES solo decay map - does the deeper, slower ES book know its
     own future in a way MNQ's doesn't? (MES friction 12% of ATR -
     marginal but not hopeless like MYM/MBT.)
  B. CROSS-BOOK: does MES book pressure (tilt/imb/stress) predict
     MNQ forward returns? Price lead-lag died in rounds 33/36, but
     book-level lead has never been tested. MES book features on the
     shared 250ms grid vs MNQ forward mid returns.
  C. If any cross signal clears cost, sim it with MNQ tick fills.
"""
import glob, json, sys, time
import numpy as np, pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, "research")
from round65_qfactory import load_day, day_features, ic_one, HORIZONS

QDIR = "/tmp/claude-0/quotes"
MES_TICK = 0.25
LATS_MS = (0, 65, 200, 500)


def main():
    t0 = time.time()
    mnq = {f.split("_")[-1][:8]: f
           for f in sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet"))}
    ics_solo, ics_x, evt = {}, {}, {}
    ndays = nx = 0
    for f in sorted(glob.glob(f"{QDIR}/Q_MESU6_*.parquet")):
        d = f.split("_")[-1][:8]
        if pd.Timestamp(d).dayofweek >= 5:
            continue
        qts, bid, ask, bs, asz = load_day(f)
        if len(qts) < 200_000:
            print(f"  {d}: thin MES quotes, skip", flush=True)
            continue
        grid, j, mid, F = day_features(qts, bid, ask, bs, asz)
        ndays += 1
        # ---- A: solo IC map
        for hz, hs in HORIZONS:
            jf = np.searchsorted(qts, grid + int(hs * 1e9), "right") - 1
            ok = jf < len(qts) - 1
            fwd = np.where(ok, (bid[jf] + ask[jf]) / 2 - mid, np.nan)
            for feat in ("tilt", "imb1", "imb10", "imb60"):
                ics_solo.setdefault((feat, hz), []).append(
                    ic_one(F[feat], fwd))
        # ---- B: cross-book -> MNQ forward returns
        fm = mnq.get(d)
        if fm is not None:
            nts, nbid, nask, _, _ = load_day(fm)
            if len(nts) > 1_000_000:
                nx += 1
                jn = np.searchsorted(nts, grid, "right") - 1
                v = jn >= 0
                nmid0 = (nbid[jn] + nask[jn]) / 2
                for hz, hs in HORIZONS:
                    jf = np.searchsorted(nts, grid + int(hs * 1e9),
                                         "right") - 1
                    ok = v & (jf < len(nts) - 1)
                    fwd = np.where(ok, (nbid[jf] + nask[jf]) / 2 - nmid0,
                                   np.nan)
                    for feat in ("tilt", "imb1", "imb10", "imb60"):
                        ics_x.setdefault((feat, hz), []).append(
                            ic_one(F[feat], fwd))
                # event-level: extreme MES book tilt -> MNQ move,
                # with latency grid (the harvestability test)
                for nm, mask, sgn in (
                    ("XTILT", np.abs(F["tilt"]) > 0.35,
                     np.sign(F["tilt"])),
                    ("XIMB10", np.abs(F["imb10"]) > 0.06,
                     np.sign(F["imb10"])),
                ):
                    idx = np.flatnonzero(mask & (sgn != 0) & v)
                    if not len(idx):
                        continue
                    keep = [int(idx[0])]
                    for i in idx[1:]:
                        if grid[i] - grid[keep[-1]] > 30_000_000_000:
                            keep.append(int(i))
                    keep = np.array(keep)
                    s = sgn[keep]
                    for lat in LATS_MS:
                        ja = np.searchsorted(
                            nts, grid[keep] + lat * 1_000_000,
                            "right") - 1
                        m0 = (nbid[ja] + nask[ja]) / 2
                        for hz, hs in (("2s", 2), ("10s", 10),
                                       ("60s", 60), ("5m", 300)):
                            jb = np.searchsorted(
                                nts, grid[keep] + lat * 1_000_000
                                + int(hs * 1e9), "right") - 1
                            ok2 = jb < len(nts) - 1
                            r = ((nbid[jb] + nask[jb]) / 2 - m0) * s
                            a = evt.setdefault((nm, lat, hz),
                                               [0.0, 0, 0])
                            a[0] += float(r[ok2].sum())
                            a[1] += int((r[ok2] > 0).sum())
                            a[2] += int(ok2.sum())
            del nts, nbid, nask
        del qts, bid, ask, bs, asz, F
        print(f"  {d}: done ({time.time()-t0:.0f}s)", flush=True)
    print(f"\n==== A: MES SOLO IC (dir features, {ndays} days) ====")
    print(f"{'feature':<8}" + "".join(f" {hz:>8}" for hz, _ in HORIZONS))
    for feat in ("tilt", "imb1", "imb10", "imb60"):
        row = f"{feat:<8}"
        for hz, _ in HORIZONS:
            v = np.array(ics_solo.get((feat, hz), [np.nan]), float)
            v = v[np.isfinite(v)]
            if len(v):
                mu = v.mean(); se = v.std() / max(np.sqrt(len(v)), 1)
                row += f" {mu:+.3f}" + ("*" if se > 0 and
                                        abs(mu / se) > 3 else " ")
            else:
                row += f" {'--':>8}"
        print(row, flush=True)
    print(f"\n==== B: CROSS-BOOK IC - MES book vs MNQ forward "
          f"({nx} days) ====")
    print(f"{'feature':<8}" + "".join(f" {hz:>8}" for hz, _ in HORIZONS))
    for feat in ("tilt", "imb1", "imb10", "imb60"):
        row = f"{feat:<8}"
        for hz, _ in HORIZONS:
            v = np.array(ics_x.get((feat, hz), [np.nan]), float)
            v = v[np.isfinite(v)]
            if len(v):
                mu = v.mean(); se = v.std() / max(np.sqrt(len(v)), 1)
                row += f" {mu:+.3f}" + ("*" if se > 0 and
                                        abs(mu / se) > 3 else " ")
            else:
                row += f" {'--':>8}"
        print(row, flush=True)
    print(f"\n==== CROSS EVENTS: MES book extreme -> MNQ mid move ====")
    for nm in ("XTILT", "XIMB10"):
        n_ = evt.get((nm, 0, "2s"), [0, 0, 0])[2]
        print(f"\n{nm} (n~{n_})")
        print(f"  {'lat':>6}" + "".join(f" {h:>16}"
                                        for h in ("2s", "10s", "60s",
                                                  "5m")))
        for lat in LATS_MS:
            row = f"  {lat:>4}ms"
            for hz in ("2s", "10s", "60s", "5m"):
                a = evt.get((nm, lat, hz))
                row += (f" {a[0]/a[2]:+7.3f}p {a[1]/a[2]*100:3.0f}%   "
                        if a and a[2] else f" {'--':>16}")
            print(row, flush=True)
    with open("research/round68_results.json", "w") as fo:
        json.dump({"solo": {f"{a}|{b}": v for (a, b), v in
                            ics_solo.items()},
                   "cross": {f"{a}|{b}": v for (a, b), v in
                             ics_x.items()},
                   "evt": {f"{a}|{b}|{c}": v for (a, b, c), v in
                           evt.items()},
                   "ndays": ndays, "nx": nx}, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

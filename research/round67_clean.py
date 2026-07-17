"""Round 67: THE CLEAN-WINDOW RE-TEST. User fetched 10 more MNQ quote
days (Jul 8-17) -> the post-roll ticks+quotes overlap roughly doubles
to ~14 days, all in the current liquid-book regime (no roll
distortion). Re-run every quote finding that mattered:
  1. Decay map (round 65) on clean days only - do the latency-proof
     event edges reappear once the roll week can't inflate them?
  2. IMB60-FADE post-roll grid (was negative on 7 days; now ~14).
  3. THIN-MOMO grid (was outlier-driven; recheck).
"""
import glob, json, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research")
from round65_qfactory import load_day, day_features, QDIR, LATS, EVT_H
from round66_qstrats import tick_day, sim_day, ENTRY_LO, ENTRY_HI
import round54_clock as K

CLEAN_LO = "20260627"


def main():
    t0 = time.time()
    K.build_tape()
    ts_all, px_all = K.D["ts"], K.D["px"]
    days = []
    evt = {}
    for f in sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet")):
        d = f.split("_")[-1][:8]
        if d < CLEAN_LO or pd.Timestamp(d).dayofweek >= 5:
            continue
        day_ns = int(pd.Timestamp(d).value)
        tsd, pxd = tick_day(ts_all, px_all, day_ns)
        if len(tsd) < 100_000:
            print(f"  {d}: no ticks, skipped", flush=True)
            continue
        qts, bid, ask, bs, asz = load_day(f)
        if len(qts) < 1_000_000:
            print(f"  {d}: thin quotes, skipped", flush=True)
            continue
        grid, j, mid, F = day_features(qts, bid, ask, bs, asz)
        days.append((d, day_ns, grid,
                     {k: F[k] for k in ("imb60", "dep10", "mom1s")}))
        # ---- event latency tables on clean days
        med_dep = np.nanmedian(F["dep10"])
        events = {
            "VACUUM": (F["vac"] < 0.4) & (F["sstress"] >= 2.0)
                      & (np.abs(F["mom1s"]) > 0),
            "IMB60x": np.abs(F["imb60"]) > 0.04,
            "THIN10": F["dep10"] < 0.5 * med_dep,
        }
        dirs = {
            "VACUUM": np.sign(F["mom1s"]),
            "IMB60x": np.sign(F["imb60"]),
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
            for lat in (0, 65, 200, 500):
                ja = np.searchsorted(qts, grid[keep] + lat * 1_000_000,
                                     "right") - 1
                m0 = (bid[ja] + ask[ja]) / 2
                for hz, hs in EVT_H:
                    jb = np.searchsorted(
                        qts, grid[keep] + lat * 1_000_000 + int(hs * 1e9),
                        "right") - 1
                    ok = jb < len(qts) - 1
                    r = ((bid[jb] + ask[jb]) / 2 - m0) * s
                    a = evt.setdefault((nm, lat, hz), [0.0, 0, 0])
                    a[0] += float(r[ok].sum())
                    a[1] += int((r[ok] > 0).sum())
                    a[2] += int(ok.sum())
        del qts, bid, ask, bs, asz, F
        print(f"  {d}: done ({time.time()-t0:.0f}s)", flush=True)
    nwk = len(days) / 5.0
    print(f"\nclean overlap days: {len(days)}", flush=True)
    print("\n==== EVENT LATENCY TABLES (clean regime only) ====")
    for nm in ("VACUUM", "IMB60x", "THIN10"):
        n_ = evt.get((nm, 0, "2s"), [0, 0, 0])[2]
        print(f"\n{nm}  (n~{n_})")
        print(f"  {'lat':>6}" + "".join(f" {hz:>16}" for hz, _ in EVT_H))
        for lat in (0, 65, 200, 500):
            row = f"  {lat:>4}ms"
            for hz, _ in EVT_H:
                a = evt.get((nm, lat, hz))
                row += (f" {a[0]/a[2]:+7.3f}p {a[1]/a[2]*100:3.0f}%   "
                        if a and a[2] else f" {'--':>16}")
            print(row, flush=True)
    # ---- strategy grids on clean days
    print(f"\n==== SIM GRIDS (clean days, passive entries, "
          f"$1.50/RT) ====")
    print(f"{'config':<24} {'n':>4} {'/wk':>5} {'WR':>4} {'avg$':>7} "
          f"{'tot$':>7} {'$/wk':>6} {'clip3':>7} {'posD':>5}")
    results = {}
    GRID = [("S1", th, hold) for th in (0.02, 0.03, 0.04, 0.06)
            for hold in (2, 5, 15)] + \
           [("S2", th, hold) for th in (0.40, 0.50, 0.60)
            for hold in (2, 5, 15)]
    for kind, th, hold in GRID:
        trades = []
        for d, day_ns, grid, F in days:
            hrs = (grid % 86_400_000_000_000) / 3600e9
            ok = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI)
            if kind == "S1":
                m = ok & (np.abs(F["imb60"]) >= th)
                s = -np.sign(F["imb60"])
            else:
                base = pd.Series(F["dep10"]).rolling(
                    7200, min_periods=1200).median().to_numpy()
                m = ok & (F["dep10"] < th * base) & (F["mom1s"] != 0)
                s = np.sign(F["mom1s"])
            idx = np.flatnonzero(m & (s != 0))
            if len(idx):
                trades += sim_day(*tick_day(ts_all, px_all, day_ns),
                                  grid, idx, s, hold * 60_000_000_000,
                                  65_000_000, True, day_ns)
        if len(trades) < 10:
            print(f"{kind} th{th} h{hold:<14} n={len(trades)} (thin)")
            continue
        p = np.array([t[1] for t in trades])
        et = np.array([t[0] for t in trades])
        dy = pd.Series(p, index=pd.to_datetime(et, utc=True)) \
            .resample("D").sum()
        dy = dy[dy != 0]
        clip = p.sum() - np.sort(p)[-3:].sum()
        nm = f"{kind} th{th} h{hold}"
        print(f"{nm:<24} {len(p):>4} {len(p)/nwk:>5.1f} "
              f"{(p>0).mean()*100:>3.0f}% {p.mean():>+7.2f} "
              f"{p.sum():>+7.0f} {p.sum()/nwk:>+6.0f} {clip:>+7.0f} "
              f"{(dy>0).mean()*100:>4.0f}%", flush=True)
        results[nm] = dict(n=len(p), usd_wk=round(p.sum()/nwk),
                           clip3=round(clip),
                           daily={str(k.date()): round(v)
                                  for k, v in dy.items()})
    with open("research/round67_results.json", "w") as fo:
        json.dump({"evt": {f"{a}|{b}|{c}": v for (a, b, c), v
                           in evt.items()},
                   "sims": results, "ndays": len(days)}, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

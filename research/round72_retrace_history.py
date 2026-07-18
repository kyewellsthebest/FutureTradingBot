"""Round 72: THE RETRACE FAMILY FACES HISTORY. Round 71's only
retail-positive clean-slate family (the user's original retrace
idea rebuilt on ticks: trend leg -> passive limit at r% retrace ->
target/stop bracket) ran +$82 to +$176/wk at 113-181 tr/wk during
a fortnight where BP bled. It is tick-only -> unlike every quote
product it CAN face the 2.5-year judgment. This is that judgment:
the winning subfamily + neighbors, simmed over 2023-2025 history
and 2026 YTD, faithful fills, $1.50/RT, per-year verdicts.
"""
import gc, json, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "research")

LAT = 65_000_000
PT, TICK = 2.0, 0.25
FEES = 1.50
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO, HI = 14.0, 20.73


def bracket(tsd, pxd, fi, entry, s, tgt, stop, t_max, n):
    xe = min(np.searchsorted(tsd, t_max, "left"), n - 1)
    if xe <= fi:
        return None, fi
    tl, sl = entry + tgt * s, entry - stop * s
    seg = pxd[fi + 1:xe]
    if not len(seg):
        return pxd[xe] - TICK * s, xe
    ht = np.flatnonzero(seg * s > (tl + TICK * s) * s - 1e-9)
    hs = np.flatnonzero(seg * s <= sl * s + 1e-9)
    it = ht[0] if len(ht) else 10**9
    is_ = hs[0] if len(hs) else 10**9
    if it < is_:
        return tl, fi + 1 + int(it)
    if is_ < it:
        k = fi + 1 + int(is_)
        rw = min(pxd[k], sl) if s > 0 else max(pxd[k], sl)
        return rw - TICK * s, k
    return pxd[xe] - TICK * s, xe


def prep(ts, px):
    m = ts // 60_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    en = np.concatenate((st[1:], [len(m)]))
    c = px[en - 1]
    h = np.maximum.reduceat(px, st)
    l = np.minimum.reduceat(px, st)
    bts = (m[st] + 1) * 60_000_000_000
    hrs = (m[st] % 1440) / 60.0
    days = (m[st] * 60_000_000_000) // 86_400_000_000_000 \
        * 86_400_000_000_000
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    return dict(c=c, bts=bts, hrs=hrs, atr=atr, days=days)


def sim_retrace(ts, px, C, g):
    n = len(ts)
    c, atr, hrs = C["c"], C["atr"], C["hrs"]
    bts, days = C["bts"], C["days"]
    Lb = g["L"]
    leg = c - np.roll(c, Lb); leg[:Lb] = 0
    ninf = np.nan_to_num(atr, nan=np.inf)
    ok = (hrs >= LO) & (hrs < HI)
    sig = np.where(ok & (np.abs(leg) >= g["m"] * ninf),
                   np.sign(leg), 0)
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(sig):
        t_sig = int(bts[i]); s = int(sig[i])
        if t_sig < busy:
            continue
        Lv = c[i] - g["r"] * leg[i]
        j0 = np.searchsorted(ts, t_sig + LAT, "left")
        j1 = np.searchsorted(ts, t_sig + 300_000_000_000, "left")
        if j0 >= n:
            break
        seg = px[j0:j1]
        th = np.flatnonzero(seg * s < (Lv - TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = j0 + int(th[0])
        t_max = min(ts[fi] + g["tmax"] * 60_000_000_000,
                    days[i] + EOD_NS)
        fill, k = bracket(ts, px, fi, Lv, s, g["tgt"], g["stop"],
                          t_max, n)
        if fill is None:
            continue
        out_p.append((fill - Lv) * s * PT - FEES)
        out_t.append(int(ts[k]))
        busy = ts[k]
    return (np.array(out_p),
            pd.to_datetime(np.array(out_t, dtype="int64"), utc=True))


def year_rows(p, idx):
    s = pd.Series(p, index=idx)
    s = s[s.index.dayofweek < 5]
    rows = []
    for yr in sorted(set(s.index.year)):
        sy = s[s.index.year == yr]
        if len(sy) < 30:
            rows.append((yr, len(sy), 0, 0, 0, 0, 0, 0))
            continue
        wk = sy.resample("W").sum(); wk = wk[wk != 0]
        dy = sy.resample("D").sum(); dy = dy[dy != 0]
        wins = sy[sy > 0]
        ratio = (wins.mean() / abs(sy[sy < 0].mean())) \
            if (sy < 0).any() and len(wins) else 0
        rows.append((yr, len(sy), round(len(sy) / max(len(wk), 1), 1),
                     round((sy > 0).mean() * 100, 1), round(ratio, 2),
                     round(sy.sum() / max(len(wk), 1)),
                     round((wk > 0).mean() * 100),
                     round(dy.min())))
    return rows


def main():
    t0 = time.time()
    GRID = []
    for m in (1.5, 2.0, 2.5):
        for Lb in (5, 15):
            for r in (0.3, 0.5):
                for tgt, stop in ((15, 8), (12, 6), (20, 10)):
                    GRID.append(dict(m=m, L=Lb, r=r, tgt=tgt,
                                     stop=stop, tmax=20))
    # ---------- 2026 tape
    import round54_clock as K
    K.build_tape()
    ts26, px26 = K.D["ts"], K.D["px"]
    for sec in (60, 30, 15):
        K.D.pop(sec, None)
    C26 = prep(ts26, px26)
    print(f"2026 tape ready ({time.time()-t0:.0f}s)", flush=True)
    res26 = {}
    for g in GRID:
        p, idx = sim_retrace(ts26, px26, C26, g)
        nm = f"m{g['m']} L{g['L']} r{g['r']} t{g['tgt']} s{g['stop']}"
        res26[nm] = year_rows(p, idx)
    del ts26, px26, C26, K.D["ts"], K.D["px"]
    K.D.clear(); gc.collect()
    print(f"2026 sims done ({time.time()-t0:.0f}s)", flush=True)
    # ---------- 2023-2025 history, memory-frugal: bucket by year
    pf = pq.ParquetFile("data/tick/nq_ticks_2p5y.parquet")
    buckets = {}
    for batch in pf.iter_batches(batch_size=8_000_000,
                                 columns=["ts", "price"]):
        bt = batch.column("ts").to_numpy()
        bp = batch.column("price").to_numpy().astype(np.float32)
        yrs = bt // 31_536_000_000_000_000  # coarse year bucketing
        for y in np.unique(yrs):
            m_ = yrs == y
            buckets.setdefault(int(y), []).append(
                (bt[m_], bp[m_]))
    print(f"history batched ({time.time()-t0:.0f}s)", flush=True)
    trades_by_cfg = {}
    for y in sorted(buckets):
        tsY = np.concatenate([a for a, _ in buckets[y]])
        pxY = np.concatenate([b for _, b in buckets[y]]) \
            .astype(np.float64)
        buckets[y] = None; gc.collect()
        o = np.argsort(tsY, kind="stable")
        tsY, pxY = tsY[o], pxY[o]
        del o
        okm = np.isfinite(pxY)
        wd = (tsY // 86_400_000_000_000 + 4) % 7
        keep = okm & (wd < 5)
        tsY, pxY = tsY[keep], pxY[keep]
        del okm, wd, keep; gc.collect()
        if len(tsY) < 1_000_000:
            continue
        CY = prep(tsY, pxY)
        yr_lab = pd.to_datetime(tsY[0]).year
        print(f"  chunk {yr_lab}: {len(tsY):,} ticks "
              f"({time.time()-t0:.0f}s)", flush=True)
        for g in GRID:
            nm = (f"m{g['m']} L{g['L']} r{g['r']} t{g['tgt']} "
                  f"s{g['stop']}")
            p, idx = sim_retrace(tsY, pxY, CY, g)
            a = trades_by_cfg.setdefault(nm, ([], []))
            a[0].append(p); a[1].append(idx)
        del tsY, pxY, CY; gc.collect()
    print(f"\n{'config':<26} {'yr':>5} {'n':>6} {'tr/wk':>6} "
          f"{'WR%':>5} {'ratio':>5} {'$/wk':>6} {'posW%':>5} "
          f"{'wd':>7}", flush=True)
    allrows = {}
    for g in GRID:
        nm = f"m{g['m']} L{g['L']} r{g['r']} t{g['tgt']} s{g['stop']}"
        ps, idxs = trades_by_cfg.get(nm, ([], []))
        p = np.concatenate(ps) if ps else np.array([])
        idx = idxs[0].append(idxs[1:]) if len(idxs) > 1 else \
            (idxs[0] if idxs else pd.DatetimeIndex([], tz="UTC"))
        rows = year_rows(p, idx) + res26.get(nm, [])
        allrows[nm] = rows
        for (yr, n_, tw, wr, ra, uw, pw, wdm) in rows:
            print(f"{nm:<26} {yr:>5} {n_:>6} {tw:>6} {wr:>5} "
                  f"{ra:>5} {uw:>+6} {pw:>5} {wdm:>+7}", flush=True)
        # verdict line: all years positive?
        pos = [uw for (yr, n_, tw, wr, ra, uw, pw, wdm) in rows
               if n_ >= 30]
        tag = "ALL-GREEN" if pos and all(u > 0 for u in pos) else \
            ("MOSTLY" if pos and sum(u > 0 for u in pos)
             >= len(pos) - 1 else "no")
        print(f"{'':<26} verdict: {tag}", flush=True)
    with open("research/round72_results.json", "w") as fo:
        json.dump({k: [[int(x) if isinstance(x, (np.integer,))
                        else float(x) if isinstance(x, (np.floating,))
                        else x for x in row] for row in v]
                   for k, v in allrows.items()}, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

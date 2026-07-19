"""Round 74: THE DUAL-ENGINE SEARCH - first strategies built on all
new data. Gamma state (lag-1, causal, synthetic-OI map from round
73b) switches the engine per day over 417 tick-overlap days:
  FADE engine  = deployed BP-Final mechanics (fade 1.2xATR)
  MOMO engine  = same mechanics, direction WITH the move (the
                 inverse trade for the inverse regime)
Variants: fade-always (baseline) | fade sticky-only | momo always
(control) | momo slippery-only | DUAL (fade sticky + momo slippery)
| DUAL-inverted (sanity). Faithful fills, $1.50/RT, per-year rows.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "research")
from round63_transfer import build

LAT = 65_000_000
PT, TICK, FEES = 2.0, 0.25, 1.50
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO, HI = 14.0, 20.73


def sim_dir(ts, px, C, momentum):
    n = len(ts)
    c, atr, hrs = C["c"], C["atr"], C["hrs"]
    bts, days, sdt = C["bts"], C["days"], C["sdt"]
    ninf = np.nan_to_num(atr, nan=np.inf)
    mom = np.concatenate(([0.0] * 10, c[10:] - c[:-10]))
    ent = (hrs >= LO) & (hrs < HI) & (sdt <= 8.0)
    raw = np.where(mom < -1.2 * ninf, 1,
                   np.where(mom > 1.2 * ninf, -1, 0))
    if momentum:
        raw = -raw
    sig = np.where(ent, raw, 0)
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        Lv = c[i] - 1.0 * s
        a0 = np.searchsorted(ts, bts[i] + LAT, "left")
        a1 = np.searchsorted(ts, bts[i] + 180_000_000_000, "left")
        if a0 >= n:
            break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (Lv - TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_x = min(ts[fi] + 15 * 60_000_000_000, days[i] + EOD_NS)
        xe = min(np.searchsorted(ts, t_x, "left"),
                 C["day_last_i"][i])
        if xe <= fi:
            continue
        fill = None; k = xe
        stop = Lv - 60.0 * s
        seg2 = px[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * s <= stop * s + 1e-9)
            if len(sh):
                k = fi + 1 + int(sh[0])
                rw = min(px[k], stop) if s > 0 else max(px[k], stop)
                fill = rw - TICK * s
        if fill is None:
            fill = px[xe] - TICK * s
            k = xe
        out_p.append((fill - Lv) * s * PT - FEES)
        out_t.append(int(ts[k]))
        busy = ts[k]
    return pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))


def daily_of(sr):
    d = sr.resample("D").sum()
    d = d[d != 0]
    d.index = d.index.astype(str).str[:10]
    return d


def main():
    t0 = time.time()
    M = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
    M.index = pd.Index(pd.to_datetime(M.index).astype(str).str[:10])
    sticky = (M["ngp2"].shift(1) > 0)
    fade_d, momo_d = {}, {}
    # history chunks from mid-2024 + 2026 tape
    pf = pq.ParquetFile("data/tick/nq_ticks_2p5y.parquet")
    buckets = {}
    for batch in pf.iter_batches(batch_size=8_000_000,
                                 columns=["ts", "price"]):
        bt = batch.column("ts").to_numpy()
        bp_ = batch.column("price").to_numpy().astype(np.float32)
        keep = bt >= 1_721_000_000_000_000_000
        bt, bp_ = bt[keep], bp_[keep]
        if not len(bt):
            continue
        yrs = bt // 31_536_000_000_000_000
        for y in np.unique(yrs):
            m_ = yrs == y
            buckets.setdefault(int(y), []).append((bt[m_], bp_[m_]))

    def run_tape(ts, px):
        C = build(ts, px)
        for tgt, momentum in ((fade_d, False), (momo_d, True)):
            for d, v in daily_of(sim_dir(ts, px, C, momentum)).items():
                tgt[d] = tgt.get(d, 0) + float(v)

    for y in sorted(buckets):
        ts = np.concatenate([a for a, _ in buckets[y]])
        px = np.concatenate([b for _, b in buckets[y]]) \
            .astype(np.float64)
        buckets[y] = None; gc.collect()
        o = np.argsort(ts, kind="stable"); ts, px = ts[o], px[o]
        wd = (ts // 86_400_000_000_000 + 4) % 7
        keep = np.isfinite(px) & (wd < 5)
        ts, px = ts[keep], px[keep]
        if len(ts) < 500_000:
            continue
        run_tape(ts, px)
        del ts, px; gc.collect()
        print(f"  chunk {y} done ({time.time()-t0:.0f}s)", flush=True)
    import round54_clock as K
    K.build_tape()
    run_tape(K.D["ts"], K.D["px"])
    print(f"sims done ({time.time()-t0:.0f}s)", flush=True)
    F = pd.Series(fade_d).sort_index()
    Mo = pd.Series(momo_d).sort_index()
    idx = F.index.union(Mo.index)
    stick = sticky.reindex(idx)
    ok = stick.notna()
    variants = {
        "FADE always (baseline)": F.reindex(idx).fillna(0),
        "FADE sticky-only": F.reindex(idx).fillna(0)
        .where(stick.fillna(True), 0.0),
        "MOMO always (control)": Mo.reindex(idx).fillna(0),
        "MOMO slippery-only": Mo.reindex(idx).fillna(0)
        .where(~stick.fillna(False), 0.0),
        "DUAL fade-sticky+momo-slip": F.reindex(idx).fillna(0)
        .where(stick.fillna(True), 0.0)
        + Mo.reindex(idx).fillna(0).where(~stick.fillna(False), 0.0),
        "DUAL-INVERTED (sanity)": F.reindex(idx).fillna(0)
        .where(~stick.fillna(False), 0.0)
        + Mo.reindex(idx).fillna(0).where(stick.fillna(True), 0.0),
    }
    print(f"\ngamma-known days: {int(ok.sum())} of {len(idx)}")
    print(f"{'variant':<30} {'yr':>5} {'$/wk':>7} {'posW%':>6} "
          f"{'avgD':>7} {'wd':>7}", flush=True)
    res = {}
    for nm, s in variants.items():
        s = s[ok]
        s.index = pd.to_datetime(s.index, utc=True)
        rows = []
        for yr in sorted(set(s.index.year)):
            sy = s[s.index.year == yr]
            sy = sy[sy != 0]
            if len(sy) < 15:
                continue
            wk = sy.resample("W").sum(); wk = wk[wk != 0]
            rows.append((yr, round(float(sy.sum() / len(wk))),
                         round(float((wk > 0).mean() * 100)),
                         round(float(sy.mean()), 1),
                         round(float(sy.min()))))
        tot = s[s != 0]
        wk = tot.resample("W").sum(); wk = wk[wk != 0]
        for (yr, uw, pw, ad, wdm) in rows:
            print(f"{nm:<30} {yr:>5} {uw:>+7} {pw:>6} {ad:>+7} "
                  f"{wdm:>+7}", flush=True)
        print(f"{nm:<30} {'ALL':>5} "
              f"{round(float(tot.sum()/max(len(wk),1))):>+7} "
              f"{round(float((wk>0).mean()*100)):>6} "
              f"{round(float(tot.mean()),1):>+7} "
              f"{round(float(tot.min())):>+7}", flush=True)
        res[nm] = rows
    import json
    with open("research/round74_results.json", "w") as fo:
        json.dump(res, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

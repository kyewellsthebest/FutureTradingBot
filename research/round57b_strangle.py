"""Round 57b: strangle-quoter gauntlet. Extend the x/tgt grid, then
2.5y history judgment + fee/latency stress on finalists."""
import sys, time, json
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round54_clock as K
import round57_hf as H
import round46_bulletproof_ga as R
from round48_drawdown import maxdd

def build_hist_30s():
    import pyarrow.parquet as pq
    tb = pq.read_table("data/tick/nq_ticks_2p5y.parquet",
                       columns=["ts", "price"])
    ts = tb["ts"].to_numpy(); px = tb["price"].to_numpy()
    del tb
    cut = np.searchsorted(ts, pd.Timestamp("2026-01-01", tz="UTC").value)
    ts, px = ts[:cut], np.asarray(px[:cut], np.float64)
    keep = np.asarray(pd.to_datetime(ts, utc=True).dayofweek) < 5
    ts, px = ts[keep], px[keep]
    cb = K.clock_bars(ts, px, 30)
    idx = pd.to_datetime(cb["bts"] - 30_000_000_000, utc=True)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0 \
        + np.asarray(idx.second) / 3600.0
    c, h, l = cb["c"], cb["h"], cb["l"]
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr_ = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr_).rolling(40).mean().to_numpy()
    day = idx.normalize()
    ro = pd.Series(np.where(hrs >= 14.0, c, np.nan), index=idx) \
        .groupby(day).transform("first")
    ro = pd.to_numeric(ro, errors="coerce").to_numpy()
    atr_eq = atr * np.sqrt(2.0)
    pos_a = np.where(np.nan_to_num(atr_eq) > 0, atr_eq, np.inf)
    C = dict(c=c, bts=cb["bts"], nb=len(c), hrs=hrs, days=day.asi8,
             atr=atr, sdt=np.nan_to_num((c - ro) / pos_a))
    C["tick_at"] = np.searchsorted(ts, C["bts"], "left")
    C["day_eod_i"] = np.searchsorted(ts, C["days"] + H.EOD_NS, "left")
    C["day_last_i"] = np.searchsorted(ts, C["days"] + H.CLOSE_NS, "left") - 1
    return ts, px, C

def sim_str(g, ts, px, C):
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    tick_at = C["tick_at"]
    ok = (hrs >= H.ENTRY_LO) & (hrs < H.ENTRY_HI) & (np.abs(sdt) <= H.GUARD)
    X = g["x"]
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(ok):
        if bts[i] < busy: continue
        a0 = tick_at[i]
        a1 = tick_at[i + 1] if i + 1 < nb else n
        if a0 >= n or a1 <= a0: continue
        seg = px[a0:a1]
        B, S = c[i] - X, c[i] + X
        hb = np.flatnonzero(seg < B - R.TICK + 1e-9)
        hs = np.flatnonzero(seg > S + R.TICK - 1e-9)
        ib = hb[0] if len(hb) else 1 << 60
        is_ = hs[0] if len(hs) else 1 << 60
        if ib == is_: continue
        if ib < is_: s, entry, fi = 1, B, a0 + int(ib)
        else: s, entry, fi = -1, S, a0 + int(is_)
        tgt_lvl = entry + g["tgt"] * s
        xe = min(np.searchsorted(ts, days[i] + H.EOD_NS, "left"),
                 C["day_last_i"][i])
        if xe <= fi: continue
        fill = None; k_exit = xe
        seg2 = px[fi + 1:xe]
        if len(seg2):
            ht = np.flatnonzero(seg2 * s > (tgt_lvl + R.TICK * s) * s - 1e-9)
            if len(ht):
                k_exit = fi + 1 + int(ht[0]); fill = tgt_lvl
        if fill is None:
            f2, k2, _ = H._walk(ts, px, fi, xe, entry, s, g.get("dis", 40.0))
            if f2 is not None and k2 < k_exit: fill, k_exit = f2, k2
        if fill is None:
            fill = px[xe] - R.TICK * s; k_exit = xe
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit]); busy = ts[k_exit]
    s_ = pd.Series(out_p, index=pd.to_datetime(np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]

def main():
    t0 = time.time()
    K.build_tape(); H.prep_indptr()
    ts26, px26 = K.D["ts"], K.D["px"]; C26 = K.D[30]
    print("=== extended grid (2026, 28wk) ===", flush=True)
    print(f"{'cfg':<20} {'$/wk':>5} {'tr/wk':>6} {'wr':>4} {'pos':>4} {'wd':>6} {'MDD':>6} {'host':>5} {'minF':>5}")
    best = []
    for x in (6.0, 8.0, 10.0, 12.0, 15.0, 20.0):
        for r in (1.0, 1.25, 1.5, 2.0):
            g = {"x": x, "tgt": r * x}
            m = H.metrics(sim_str(g, ts26, px26, C26))
            if m:
                print(f"x{x:<4} tgt{r*x:<6.1f} {m['usd_wk']:>7} {m['tr_wk']:>6} {m['wr']:>3}% {m['pos']:>4} {m['wd']:>6} {m['mdd']:>6} {m['host']:>5} {m['minf']:>5}", flush=True)
                best.append((m["usd_wk"], g, m))
    best.sort(key=lambda z: -z[0])
    fin = [g for _, g, _ in best[:3]]
    print(f"\nfinalists: {fin} ({time.time()-t0:.0f}s)", flush=True)
    print("\n=== fee stress $2.50/RT (2026) ===", flush=True)
    R.FEES = 2.50
    for g in fin:
        m = H.metrics(sim_str(g, ts26, px26, C26))
        if m: print(f"x{g['x']} tgt{g['tgt']}: $/wk {m['usd_wk']} pos {m['pos']}% wd {m['wd']}", flush=True)
    R.FEES = 1.50
    print("\n=== latency 200ms (2026) ===", flush=True)
    R.LAT_NS = 200_000_000
    for g in fin:
        m = H.metrics(sim_str(g, ts26, px26, C26))
        if m: print(f"x{g['x']} tgt{g['tgt']}: $/wk {m['usd_wk']} pos {m['pos']}%", flush=True)
    R.LAT_NS = 65_000_000
    print(f"\nbuilding 2.5y 30s history clock... ({time.time()-t0:.0f}s)", flush=True)
    tsH, pxH, CH = build_hist_30s()
    print(f"history 30s bars: {CH['nb']:,} ({time.time()-t0:.0f}s)", flush=True)
    print("\n=== HISTORY JUDGMENT 2023-2025 (1 lot) ===", flush=True)
    for g in fin:
        sH = sim_str(g, tsH, pxH, CH)
        print(f"-- x{g['x']} tgt{g['tgt']} --", flush=True)
        for yr in (2023, 2024, 2025):
            sy = sH[sH.index.year == yr]
            if len(sy) < 50: print(f"  {yr}: n={len(sy)}"); continue
            w = R.wk_of(sy); d = sy.resample("D").sum(); d = d[d != 0]
            print(f"  {yr}: $/wk {sy.sum()/max(len(w),1):6.0f} | tr/wk {len(sy)/max(len(w),1):5.1f} | pos {(w>0).mean()*100:3.0f}% | wd {d.min():6.0f} | MDD {maxdd(d):7.0f}", flush=True)
    print(f"\nDONE ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()

"""Round 57c: strangle history judgment (memory-frugal, standalone) +
adversarial fill model (entry latency, 2-tick trade-through option)."""
import sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
from round48_drawdown import maxdd

PT, FEES, TICK = 2.0, 1.50, 0.25
LAT = 65_000_000
ENTRY_LO, ENTRY_HI, GUARD = 14.0, 20.73, 8.0
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000
STOP_SLIP = 0.25

def wk_of(s):
    wk = s.resample("W").sum()
    return wk[wk != 0]

def build_30s(ts, px):
    m = ts // 30_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    en = np.concatenate((st[1:], [len(m)]))
    c = px[en - 1]
    h = np.maximum.reduceat(px, st)
    l = np.minimum.reduceat(px, st)
    bts = (m[st] + 1) * 30_000_000_000
    days = (bts - 1) // 86_400_000_000_000 * 86_400_000_000_000
    secs = (bts - 1) % 86_400_000_000_000 / 1e9
    hrs = secs / 3600.0
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr_ = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr_).rolling(40).mean().to_numpy()
    # day RTH open (first close >= 14:00) via numpy
    dayid = days // 86_400_000_000_000
    is_rth = hrs >= 14.0
    open_px = np.full(len(c), np.nan)
    seen = {}
    ro = np.empty(len(c)); ro[:] = np.nan
    cur_day, cur_open = -1, np.nan
    for i in range(len(c)):
        d = dayid[i]
        if d != cur_day:
            cur_day, cur_open = d, np.nan
        if np.isnan(cur_open) and is_rth[i]:
            cur_open = c[i]
        ro[i] = cur_open
    atr_eq = atr * np.sqrt(2.0)
    pos_a = np.where(np.nan_to_num(atr_eq) > 0, atr_eq, np.inf)
    sdt = np.nan_to_num((c - ro) / pos_a)
    C = dict(c=c, bts=bts, nb=len(c), hrs=hrs, days=days, sdt=sdt)
    C["tick_at"] = np.searchsorted(ts, bts, "left")
    C["day_last_i"] = np.searchsorted(ts, days + CLOSE_NS, "left") - 1
    return C

def sim_str(g, ts, px, C, through=1, entry_lat=True):
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    tick_at = C["tick_at"]
    ok = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    X, TGT = g["x"], g["tgt"]
    dis = g.get("dis", 40.0)
    thr_o = TICK * through
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(ok):
        if bts[i] < busy: continue
        a0 = tick_at[i]
        if entry_lat:
            a0 = np.searchsorted(ts, bts[i] + LAT, "left")
        a1 = tick_at[i + 1] if i + 1 < nb else n
        if a0 >= n or a1 <= a0: continue
        seg = px[a0:a1]
        B, S = c[i] - X, c[i] + X
        hb = np.flatnonzero(seg < B - thr_o + 1e-9)
        hs = np.flatnonzero(seg > S + thr_o - 1e-9)
        ib = hb[0] if len(hb) else 1 << 60
        is_ = hs[0] if len(hs) else 1 << 60
        if ib == is_: continue
        if ib < is_: s, entry, fi = 1, B, a0 + int(ib)
        else: s, entry, fi = -1, S, a0 + int(is_)
        tgt_lvl = entry + TGT * s
        xe = min(np.searchsorted(ts, days[i] + EOD_NS, "left"),
                 C["day_last_i"][i])
        if xe <= fi: continue
        fill = None; k_exit = xe
        seg2 = px[fi + 1:xe]
        stop_lvl = entry - dis * s
        it = 1 << 60; ist = 1 << 60
        if len(seg2):
            ht = np.flatnonzero(seg2 * s > (tgt_lvl + thr_o * s) * s - 1e-9)
            hst = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
            it = ht[0] if len(ht) else it
            ist = hst[0] if len(hst) else ist
        if it < ist:
            k_exit = fi + 1 + int(it); fill = tgt_lvl
        elif ist < it:
            k_exit = fi + 1 + int(ist)
            raw = min(px[k_exit], stop_lvl) if s > 0 else max(px[k_exit], stop_lvl)
            fill = raw - STOP_SLIP * s
        if fill is None:
            fill = px[xe] - TICK * s; k_exit = xe
        out_p.append((fill - entry) * s * PT - FEES)
        out_t.append(ts[k_exit]); busy = ts[k_exit]
    s_ = pd.Series(out_p, index=pd.to_datetime(np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]

def yearly(nm, s):
    print(f"-- {nm} --", flush=True)
    for yr in (2023, 2024, 2025):
        sy = s[s.index.year == yr]
        if len(sy) < 50:
            print(f"  {yr}: n={len(sy)}"); continue
        w = wk_of(sy); d = sy.resample("D").sum(); d = d[d != 0]
        print(f"  {yr}: $/wk {sy.sum()/max(len(w),1):6.0f} | tr/wk {len(sy)/max(len(w),1):5.1f} | "
              f"pos {(w>0).mean()*100:3.0f}% | wr {(sy>0).mean()*100:3.0f}% | wd {d.min():6.0f} | MDD {maxdd(d):7.0f}", flush=True)

def main():
    t0 = time.time()
    import pyarrow.parquet as pq
    tb = pq.read_table("data/tick/nq_ticks_2p5y.parquet", columns=["ts", "price"])
    ts = tb["ts"].to_numpy(); px = np.asarray(tb["price"].to_numpy(), np.float64)
    del tb
    cut = np.searchsorted(ts, pd.Timestamp("2026-01-01", tz="UTC").value)
    ts, px = ts[:cut].copy(), px[:cut].copy()
    wd = (ts // 86_400_000_000_000 + 4) % 7
    keep = wd < 5
    ts, px = ts[keep], px[keep]
    print(f"hist ticks: {len(ts):,} ({time.time()-t0:.0f}s)", flush=True)
    C = build_30s(ts, px)
    print(f"hist 30s bars: {C['nb']:,} ({time.time()-t0:.0f}s)", flush=True)
    for g in ({"x": 10.0, "tgt": 20.0}, {"x": 12.0, "tgt": 24.0},
              {"x": 6.0, "tgt": 9.0}):
        yearly(f"x{g['x']} tgt{g['tgt']} (1-tick through)",
               sim_str(g, ts, px, C, through=1))
    print("\n=== adversarial: 2-tick trade-through required ===", flush=True)
    yearly("x10 tgt20 (2-tick)", sim_str({"x": 10.0, "tgt": 20.0}, ts, px, C, through=2))
    print(f"\nDONE ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()

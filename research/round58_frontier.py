"""Round 58: THE FREQUENCY FRONTIER. User mandate: the most trades/wk
with the smallest wins/losses that still makes ~$500/wk. Floor: beat
200 tr/wk. Round 57 proved 400-500 is behind the fee wall; this round
sweeps the unexplored 180-350 tr/wk corner:
  - fade on 1m and 30s clocks with LOW thresholds (a 0.6-1.1),
    short holds (3-12 min), tight disaster stops (30-60pt),
    passive and market entries, flat 1 MNQ, trend-day guard 8.
Selection: tr/wk >= 180, $/wk >= 400, pos weeks >= 75%,
hostile week > -400, min fold >= 100. Survivors -> 2.5y history
pools + fee stress $2.50.
Phase A sweeps 2026 (28 wk); phase B frees memory and judges the
survivors on history with the matching clock.
"""
import gc, json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round54_clock as K
import round46_bulletproof_ga as R
from round48_drawdown import maxdd

ENTRY_LO, ENTRY_HI, GUARD = 14.0, 20.73, 8.0
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000
F26 = [("2026-01-01", "2026-03-01"), ("2026-03-01", "2026-05-01"),
       ("2026-05-01", "2026-06-01"), ("2026-06-01", "2026-07-07")]


def prep_clock(C, ts):
    C["day_last_i"] = np.searchsorted(ts, C["days"] + CLOSE_NS, "left") - 1


def sim_fade(g, ts, px, C, sec):
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    atr_eq = C["atr"] * np.sqrt(60.0 / sec)
    ninf = np.nan_to_num(atr_eq, nan=np.inf)
    kb = max(1, int(g["km"] * 60 / sec))
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    thr = g["a"] * ninf
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    out_t, out_p = [], []
    busy = 0
    hold_ns = R.HN(g["hold"])
    passive = g["passive"]
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        if passive:
            L = c[i] - g["off"] * s
            a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + int(g["cxl"] * 1e9), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
            if not len(th):
                continue
            fi = a0 + int(th[0])
            entry = L
        else:
            fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + R.TICK * s
        t_tgt = min(ts[fi] + hold_ns + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill = None; k_exit = xe
        stop_lvl = entry - g["dis"] * s
        seg2 = px[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
            if len(sh):
                k_exit = fi + 1 + int(sh[0])
                rw = min(px[k_exit], stop_lvl) if s > 0 \
                    else max(px[k_exit], stop_lvl)
                fill = rw - R.STOP_SLIP * s
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit])
        busy = ts[k_exit]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]


def metrics(s):
    if len(s) < 800:
        return None
    wk = R.wk_of(s)
    if len(wk) < 24:
        return None
    dy = s.resample("D").sum(); dy = dy[dy != 0]
    folds = []
    for lo, hi in F26:
        f = s[(s.index >= pd.Timestamp(lo, tz="UTC"))
              & (s.index < pd.Timestamp(hi, tz="UTC"))]
        w = R.wk_of(f)
        folds.append(round(float(f.sum() / max(len(w), 1))) if len(f) else 0)
    ho = float(s[s.index >= pd.Timestamp("2026-07-07", tz="UTC")].sum())
    wins = s[s > 0]
    return dict(usd_wk=round(float(s.sum() / len(wk))),
                tr_wk=round(len(s) / len(wk), 1),
                wr=round(float((s > 0).mean() * 100)),
                aw=round(float(wins.mean()), 1) if len(wins) else 0,
                al=round(float(s[s < 0].mean()), 1),
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), mdd=round(float(maxdd(dy))),
                host=round(ho), minf=min(folds))


def show(nm, m):
    print(f"{nm:<36} {m['usd_wk']:>5} {m['tr_wk']:>6} {m['wr']:>3}% "
          f"{m['aw']:>6} {m['al']:>7} {m['pos']:>4} {m['wd']:>6} "
          f"{m['mdd']:>6} {m['host']:>5} {m['minf']:>5}", flush=True)


def hist_clock(sec):
    import pyarrow.parquet as pq
    tb = pq.read_table("data/tick/nq_ticks_2p5y.parquet",
                       columns=["ts", "price"])
    ts = tb["ts"].to_numpy(); px = np.asarray(tb["price"].to_numpy(),
                                              np.float64)
    del tb
    cut = np.searchsorted(ts, pd.Timestamp("2026-01-01", tz="UTC").value)
    ts, px = ts[:cut].copy(), px[:cut].copy()
    wd = (ts // 86_400_000_000_000 + 4) % 7
    keep = wd < 5
    ts, px = ts[keep], px[keep]
    cb = K.clock_bars(ts, px, sec)
    bts = cb["bts"]
    days = (bts - 1) // 86_400_000_000_000 * 86_400_000_000_000
    hrs = ((bts - 1) % 86_400_000_000_000) / 3.6e12
    c, h, l = cb["c"], cb["h"], cb["l"]
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr_ = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr_).rolling(max(1, int(20 * 60 / sec))).mean().to_numpy()
    dayid = days // 86_400_000_000_000
    ro = np.empty(len(c)); ro[:] = np.nan
    cur_day, cur_open = -1, np.nan
    rth = hrs >= 14.0
    for i in range(len(c)):
        if dayid[i] != cur_day:
            cur_day, cur_open = dayid[i], np.nan
        if np.isnan(cur_open) and rth[i]:
            cur_open = c[i]
        ro[i] = cur_open
    atr_eq = atr * np.sqrt(60.0 / sec)
    pos_a = np.where(np.nan_to_num(atr_eq) > 0, atr_eq, np.inf)
    C = dict(c=c, bts=bts, nb=len(c), hrs=hrs, days=days, atr=atr,
             sdt=np.nan_to_num((c - ro) / pos_a))
    prep_clock(C, ts)
    return ts, px, C


def main():
    t0 = time.time()
    K.build_tape()
    for sec in (60, 30):
        prep_clock(K.D[sec], K.D["ts"])
    ts26, px26 = K.D["ts"], K.D["px"]
    print(f"{'variant':<36} {'$/wk':>5} {'tr/wk':>6} {'wr':>4} "
          f"{'avgW':>6} {'avgL':>7} {'posW':>4} {'wd':>6} {'MDD':>6} "
          f"{'host':>5} {'minF':>5}", flush=True)
    survivors = {}
    n_run = 0
    for sec in (60, 30):
        C = K.D[sec]
        for km in (5, 8, 10):
            for a in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1):
                for hold in (3, 5, 8, 12):
                    for passive, off, cxl in ((True, 0.5, 60),
                                              (True, 1.0, 120),
                                              (False, 0, 0)):
                        for dis in (40.0, 60.0):
                            g = {"km": km, "a": a, "hold": hold,
                                 "passive": passive, "off": off,
                                 "cxl": cxl, "dis": dis}
                            n_run += 1
                            m = metrics(sim_fade(g, ts26, px26, C, sec))
                            if m is None:
                                continue
                            if (m["tr_wk"] >= 180 and m["usd_wk"] >= 400
                                    and m["pos"] >= 75
                                    and m["host"] > -400
                                    and m["minf"] >= 100):
                                nm = (f"c{sec} m{km} a{a} h{hold} "
                                      f"{'p' + str(off) if passive else 'mkt'} "
                                      f"d{int(dis)}")
                                survivors[nm] = {"g": g, "sec": sec, "m": m}
                                show(nm, m)
            print(f"  [c{sec} km{km}] {n_run} run "
                  f"({time.time()-t0:.0f}s)", flush=True)
    with open("research/round58_survivors.json", "w") as f:
        json.dump({k: {"g": v["g"], "sec": v["sec"], "m": v["m"]}
                   for k, v in survivors.items()}, f, indent=1)
    print(f"\nsurvivors: {len(survivors)} of {n_run}", flush=True)
    if not survivors:
        print("NO SURVIVORS in the 180+ band. DONE "
              f"({time.time()-t0:.0f}s)")
        return
    # rank: max frequency first among qualifiers, then $/wk
    ranked = sorted(survivors.items(),
                    key=lambda kv: (-kv[1]["m"]["tr_wk"],
                                    -kv[1]["m"]["usd_wk"]))
    finalists = ranked[:6]
    print("\n=== fee stress $2.50/RT (2026) ===", flush=True)
    R.FEES = 2.50
    keep = []
    for nm, v in finalists:
        m = metrics(sim_fade(v["g"], ts26, px26, K.D[v["sec"]], v["sec"]))
        ok = m is not None and m["usd_wk"] >= 200
        print(f"  {nm}: $/wk {m['usd_wk'] if m else '-'} "
              f"{'PASS' if ok else 'FAIL'}", flush=True)
        if ok:
            keep.append((nm, v))
    R.FEES = 1.50
    if not keep:
        print("all finalists fail fee stress. DONE")
        return
    # phase B: history judgment (free 2026 ticks first)
    print(f"\nfreeing 2026 tape, building history clocks "
          f"({time.time()-t0:.0f}s)", flush=True)
    del ts26, px26
    K.D.clear()
    gc.collect()
    by_sec = {}
    for nm, v in keep:
        by_sec.setdefault(v["sec"], []).append((nm, v))
    for sec, items in by_sec.items():
        tsH, pxH, CH = hist_clock(sec)
        print(f"history {sec}s clock: {CH['nb']:,} bars "
              f"({time.time()-t0:.0f}s)", flush=True)
        for nm, v in items:
            sH = sim_fade(v["g"], tsH, pxH, CH, sec)
            print(f"-- {nm} --", flush=True)
            for yr in (2023, 2024, 2025):
                sy = sH[sH.index.year == yr]
                if len(sy) < 50:
                    print(f"  {yr}: n={len(sy)}"); continue
                w = R.wk_of(sy)
                d = sy.resample("D").sum(); d = d[d != 0]
                print(f"  {yr}: $/wk {sy.sum()/max(len(w),1):6.0f} | "
                      f"tr/wk {len(sy)/max(len(w),1):5.1f} | "
                      f"pos {(w>0).mean()*100:3.0f}% | wd {d.min():6.0f} | "
                      f"MDD {maxdd(d):7.0f}", flush=True)
        del tsH, pxH, CH
        gc.collect()
    print(f"\nDONE {n_run} configs ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

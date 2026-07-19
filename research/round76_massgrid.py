"""Round 76: THE MASS GRID - 10,260 gamma-level configs over 2y.
PIN-FADE: D{20,30,45,60,80,100,130,170} x tgt{pin,half,10,20,30} x
stop{0.5,0.75,1,1.5,2}xD x timer{15,30,60}m x gate{all,sticky,slip}
= 5,400.  FLIP-BREAK: dir{both,short,long} x tgt{20..120} x
stop{10..40} x confirm{0,2,5}m x gate x hold{30,60,120}m = 4,860.
Event-based: per day precompute pin-distance episodes + flip
crossings once; per config fast busy-chained bracket sims.
Reports: top-30 by $/wk (clip3>0 required), dream flags, bucket
stats. $1.50/RT, passive pin entries, market flip entries.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "research")
PT, TICK, FEES = 2.0, 0.25, 1.50
LAT = 65_000_000
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO_H, HI_H = 14.0, 20.44
D_SET = [20.0, 30.0, 45.0, 60.0, 80.0, 100.0, 130.0, 170.0]

CFG = []
for D in D_SET:
    for tm in ("pin", "half", "f10", "f20", "f30"):
        for sm in (0.5, 0.75, 1.0, 1.5, 2.0):
            for tmr in (15, 30, 60):
                for gt in ("all", "st", "sl"):
                    CFG.append(("P", D, tm, sm, tmr, gt))
N_PIN = len(CFG)
for dr in ("b", "s", "l"):
    for tg in (20.0, 30.0, 40.0, 60.0, 80.0, 120.0):
        for st_ in (10.0, 15.0, 20.0, 30.0, 40.0):
            for cf in (0, 120, 300):
                for gt in ("all", "st", "sl"):
                    for hd in (30, 60, 120):
                        CFG.append(("F", dr, tg, st_, cf, gt, hd))
NC = len(CFG)
print(f"configs: {NC}", flush=True)
SUM = np.zeros(NC); NTR = np.zeros(NC, np.int64)
WIN = np.zeros(NC, np.int64)
TOP3 = np.zeros((NC, 3))
WEEK = {}


def upd(ci, pnl, wk):
    SUM[ci] += pnl; NTR[ci] += 1
    if pnl > 0:
        WIN[ci] += 1
        m = TOP3[ci].argmin()
        if pnl > TOP3[ci][m]:
            TOP3[ci][m] = pnl
    WEEK.setdefault(wk, np.zeros(NC, np.float32))[ci] += pnl


def bracket(tsd, pxd, fi, entry, s, tgt_px, stop_px, t_max, n):
    xe = min(np.searchsorted(tsd, t_max, "left"), n - 1)
    if xe <= fi:
        return None, fi
    seg = pxd[fi + 1:xe]
    if not len(seg):
        return pxd[xe] - TICK * s, xe
    ht = np.flatnonzero(seg * s > (tgt_px + TICK * s) * s - 1e-9)
    hs = np.flatnonzero(seg * s <= stop_px * s + 1e-9)
    it = ht[0] if len(ht) else 10**9
    is_ = hs[0] if len(hs) else 10**9
    if it < is_:
        return tgt_px, fi + 1 + int(it)
    if is_ < it:
        k = fi + 1 + int(is_)
        rw = min(pxd[k], stop_px) if s > 0 else max(pxd[k], stop_px)
        return rw - TICK * s, k
    return pxd[xe] - TICK * s, xe


def process(ts, px, lvl):
    d = ts // 86_400_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(d)) + 1))
    en = np.concatenate((st[1:], [len(ts)]))
    for di in range(len(st)):
        day0 = int(d[st[di]]) * 86_400_000_000_000
        dstr = str(pd.Timestamp(day0).date())
        v = lvl.get(dstr)
        if v is None:
            continue
        S, flip, pin, sticky = v
        if not np.isfinite(S) or S <= 0:
            continue
        a, b = st[di], en[di]
        tsd, pxd = ts[a:b], px[a:b]
        n = len(tsd)
        if n < 50_000:
            continue
        i0 = np.searchsorted(tsd, day0 + int(LO_H * 3600e9))
        i1 = np.searchsorted(tsd, day0 + int(HI_H * 3600e9))
        if i1 - i0 < 10_000:
            continue
        ratio = pxd[min(i0, n - 1)] / S
        wk = (day0 // 86_400_000_000_000 + 3) // 7
        pinN = pin * ratio if np.isfinite(pin) else np.nan
        flipN = flip * ratio if np.isfinite(flip) else np.nan
        # ---- pin episodes per D
        ep = {}
        if np.isfinite(pinN):
            dist = pxd[i0:i1] - pinN
            for D in D_SET:
                out = np.abs(dist) >= D
                starts = np.flatnonzero(out & ~np.roll(out, 1))
                starts = starts[starts > 0][:40]
                ep[D] = i0 + starts
        # ---- flip crossings
        fx = np.array([], dtype=np.int64)
        if np.isfinite(flipN):
            abv = pxd[i0:i1] > flipN
            fx = i0 + np.flatnonzero(abv != np.roll(abv, 1))[1:][:40]
        for ci, cfg in enumerate(CFG):
            if cfg[0] == "P":
                _, D, tm, sm, tmr, gt = cfg
                if (gt == "st" and not sticky) or \
                        (gt == "sl" and sticky):
                    continue
                evs = ep.get(D)
                if evs is None or not len(evs):
                    continue
                busy = 0
                for j in evs:
                    if tsd[j] < busy:
                        continue
                    s_ = -int(np.sign(pxd[j] - pinN))
                    if s_ == 0:
                        continue
                    Lv = pxd[j] - 1.0 * s_
                    j1_ = np.searchsorted(
                        tsd, tsd[j] + 180_000_000_000)
                    seg = pxd[j + 1:j1_]
                    th = np.flatnonzero(
                        seg * s_ < (Lv - TICK * s_) * s_ + 1e-9)
                    if not len(th):
                        continue
                    fi = j + 1 + int(th[0])
                    if tm == "pin":
                        tp = pinN
                    elif tm == "half":
                        tp = Lv + (pinN - Lv) * 0.5
                    else:
                        tp = Lv + float(tm[1:]) * s_
                    fill, k = bracket(
                        tsd, pxd, fi, Lv, s_, tp, Lv - sm * D * s_,
                        min(tsd[fi] + tmr * 60_000_000_000,
                            day0 + EOD_NS), n)
                    if fill is None:
                        continue
                    upd(ci, (fill - Lv) * s_ * PT - FEES, wk)
                    busy = tsd[k]
            else:
                _, dr, tg, st_, cf, gt, hd = cfg
                if (gt == "st" and not sticky) or \
                        (gt == "sl" and sticky):
                    continue
                if not len(fx):
                    continue
                busy = 0
                for j in fx:
                    if tsd[j] < busy:
                        continue
                    s_ = 1 if pxd[j] > flipN else -1
                    if (dr == "s" and s_ > 0) or \
                            (dr == "l" and s_ < 0):
                        continue
                    t_e = tsd[j] + cf * 1_000_000_000
                    fi = np.searchsorted(tsd, t_e + LAT)
                    if fi >= n:
                        break
                    if cf and (pxd[fi] > flipN) != (s_ > 0):
                        continue
                    entry = pxd[fi] + TICK * s_
                    fill, k = bracket(
                        tsd, pxd, fi, entry, s_, entry + tg * s_,
                        entry - st_ * s_,
                        min(tsd[fi] + hd * 60_000_000_000,
                            day0 + EOD_NS), n)
                    if fill is None:
                        continue
                    upd(ci, (fill - entry) * s_ * PT - FEES, wk)
                    busy = tsd[k]


def main():
    t0 = time.time()
    M1 = pd.read_csv("research/gexmap_daily.csv", index_col=0)
    M2 = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
    M2.index = pd.Index(pd.to_datetime(M2.index).astype(str).str[:10])
    M = M1.join(M2["ngp2"], how="inner")
    M["sticky"] = M["ngp2"].shift(1) > 0
    lvl = {dd: (r["S"], r["flip"], r["pin"], bool(r["sticky"]))
           for dd, r in M.iterrows()}
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
    for y in sorted(buckets):
        ts = np.concatenate([a for a, _ in buckets[y]])
        px = np.concatenate([b for _, b in buckets[y]]) \
            .astype(np.float64)
        buckets[y] = None; gc.collect()
        o = np.argsort(ts, kind="stable"); ts, px = ts[o], px[o]
        wd = (ts // 86_400_000_000_000 + 4) % 7
        keep = np.isfinite(px) & (wd < 5)
        ts, px = ts[keep], px[keep]
        if len(ts) > 500_000:
            process(ts, px, lvl)
        del ts, px; gc.collect()
        print(f"chunk {y} done ({time.time()-t0:.0f}s)", flush=True)
    import round54_clock as K
    K.build_tape()
    process(K.D["ts"], K.D["px"], lvl)
    print(f"sims done ({time.time()-t0:.0f}s)", flush=True)
    Wm = np.stack(list(WEEK.values()))          # weeks x cfg
    nwk_tot = Wm.shape[0]
    act = Wm != 0
    nwk = np.maximum(act.sum(0), 1)
    usd_wk = SUM / nwk
    posw = (Wm > 0).sum(0) / nwk * 100
    clip3 = SUM - TOP3.sum(1)
    wr = np.where(NTR > 0, WIN / np.maximum(NTR, 1) * 100, 0)
    ok = (NTR >= 100) & (clip3 > 0) & (usd_wk > 0)
    print(f"\nconfigs with n>=100, $/wk>0 AND clip3>0: {int(ok.sum())}"
          f" of {NC}", flush=True)
    order = np.argsort(-usd_wk)
    shown = 0
    print(f"{'config':<44} {'n':>5} {'WR%':>5} {'$/wk':>7} "
          f"{'clip3':>8} {'posW%':>6}")
    for ci in order:
        if not ok[ci]:
            continue
        print(f"{str(CFG[ci]):<44} {NTR[ci]:>5} {wr[ci]:>5.1f} "
              f"{usd_wk[ci]:>+7.0f} {clip3[ci]:>+8.0f} "
              f"{posw[ci]:>6.0f}", flush=True)
        shown += 1
        if shown >= 30:
            break
    dream = (NTR / nwk >= 150) & (wr >= 45) & (wr <= 55) & ok
    print(f"\ndream flags: {int(dream.sum())}")
    np.savez("research/round76_results.npz", SUM=SUM, NTR=NTR,
             WIN=WIN, clip3=clip3, usd_wk=usd_wk, posw=posw)
    print(f"\nDONE {NC} configs ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

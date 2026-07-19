"""Round 75: GAMMA LEVEL STRATEGIES (wave 2 of the triple-data
search). The 2y gamma map's daily flip + pin strikes, mapped from
QQQ to NQ points via each day's inferred ratio, used as ENTRY
triggers over 417 tick days:
  A PIN-FADE: price drifts D pts from the pin level -> passive
    entry back toward pin, target = pin, stop D, timer 30m.
  B FLIP-BREAK: price crosses below flip -> momentum short,
    bracket; cross above -> long. (negative-gamma acceleration)
Arms: all days vs sticky/slippery-consistent days. $1.50/RT.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "research")

PT, TICK, FEES = 2.0, 0.25, 1.50
LAT = 65_000_000
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO_H, HI_H = 14.0, 20.44


def day_slices(ts):
    d = ts // 86_400_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(d)) + 1))
    en = np.concatenate((st[1:], [len(ts)]))
    return d[st] * 86_400_000_000_000, st, en


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


def main():
    t0 = time.time()
    M1 = pd.read_csv("research/gexmap_daily.csv", index_col=0)
    M2 = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
    M2.index = pd.Index(pd.to_datetime(M2.index).astype(str).str[:10])
    M = M1.join(M2["ngp2"], how="inner")
    M["sticky"] = M["ngp2"].shift(1) > 0
    lvl = {d: (r["S"], r["flip"], r["pin"], bool(r["sticky"]))
           for d, r in M.iterrows()}
    trades = {}          # cfg -> list of (exit_ts, pnl, day)

    def process(ts, px):
        days, st, en = day_slices(ts)
        for di in range(len(st)):
            dstr = str(pd.Timestamp(days[di]).date())
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
            i0 = np.searchsorted(
                tsd, days[di] + int(LO_H * 3600e9))
            if i0 >= n:
                continue
            ratio = pxd[min(i0, n - 1)] / S
            pinN = pin * ratio if np.isfinite(pin) else np.nan
            flipN = flip * ratio if np.isfinite(flip) else np.nan
            i1 = np.searchsorted(tsd, days[di] + int(HI_H * 3600e9))
            # ---- A PIN-FADE
            if np.isfinite(pinN):
                for D in (30.0, 60.0, 100.0):
                    for gate in ("all", "sticky"):
                        if gate == "sticky" and not sticky:
                            continue
                        busy = 0
                        j = i0
                        while j < i1:
                            dist = pxd[j] - pinN
                            if abs(dist) >= D and tsd[j] >= busy:
                                s_ = -int(np.sign(dist))
                                Lv = pxd[j] - 1.0 * s_
                                j1_ = np.searchsorted(
                                    tsd, tsd[j] + 180_000_000_000)
                                seg = pxd[j + 1:j1_]
                                th = np.flatnonzero(
                                    seg * s_ < (Lv - TICK * s_)
                                    * s_ + 1e-9)
                                if len(th):
                                    fi = j + 1 + int(th[0])
                                    t_max = min(
                                        tsd[fi] + 1800_000_000_000,
                                        days[di] + EOD_NS)
                                    fill, k = bracket(
                                        tsd, pxd, fi, Lv, s_, pinN,
                                        Lv - D * s_, t_max, n)
                                    if fill is not None:
                                        pnl = (fill - Lv) * s_ * PT \
                                            - FEES
                                        trades.setdefault(
                                            f"A pin D{D:.0f} {gate}",
                                            []).append(
                                            (int(tsd[k]), pnl))
                                        busy = tsd[k]
                                        j = k
                            j += 200
            # ---- B FLIP-BREAK
            if np.isfinite(flipN):
                for tgt, stp in ((40.0, 20.0), (80.0, 30.0)):
                    for gate in ("all", "slip"):
                        if gate == "slip" and sticky:
                            continue
                        busy = 0
                        prev_above = pxd[i0] > flipN
                        j = i0 + 1
                        while j < i1:
                            above = pxd[j] > flipN
                            if above != prev_above and \
                                    tsd[j] >= busy:
                                s_ = 1 if above else -1
                                fi = np.searchsorted(
                                    tsd, tsd[j] + LAT)
                                if fi >= n:
                                    break
                                entry = pxd[fi] + TICK * s_
                                t_max = min(
                                    tsd[fi] + 3600_000_000_000,
                                    days[di] + EOD_NS)
                                fill, k = bracket(
                                    tsd, pxd, fi, entry, s_,
                                    entry + tgt * s_,
                                    entry - stp * s_, t_max, n)
                                if fill is not None:
                                    pnl = (fill - entry) * s_ * PT \
                                        - FEES
                                    trades.setdefault(
                                        f"B flip t{tgt:.0f}"
                                        f"s{stp:.0f} {gate}",
                                        []).append(
                                        (int(tsd[k]), pnl))
                                    busy = tsd[k]
                                    j = k
                            prev_above = above
                            j += 50
    # tape: history chunks + 2026
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
            process(ts, px)
        del ts, px; gc.collect()
        print(f"  chunk {y} done ({time.time()-t0:.0f}s)", flush=True)
    import round54_clock as K
    K.build_tape()
    process(K.D["ts"], K.D["px"])
    print(f"\n{'config':<24} {'n':>5} {'/wk':>6} {'WR%':>5} "
          f"{'avg$':>7} {'$/wk':>7} {'clip3':>8} {'posW%':>6}",
          flush=True)
    for nm in sorted(trades):
        tl = trades[nm]
        p = np.array([x[1] for x in tl])
        et = np.array([x[0] for x in tl])
        if len(p) < 20:
            print(f"{nm:<24} n={len(p)} thin"); continue
        sr = pd.Series(p, index=pd.to_datetime(et, utc=True)) \
            .sort_index()
        wk = sr.resample("W").sum(); wk = wk[wk != 0]
        clip = p.sum() - np.sort(p)[-3:].sum()
        print(f"{nm:<24} {len(p):>5} {len(p)/max(len(wk),1):>6.1f} "
              f"{(p>0).mean()*100:>5.1f} {p.mean():>+7.2f} "
              f"{p.sum()/max(len(wk),1):>+7.0f} {clip:>+8.0f} "
              f"{(wk>0).mean()*100:>6.0f}", flush=True)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

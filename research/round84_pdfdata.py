"""Round 82: LEVELRIDE-LADDER honest portfolio audit. Rungs =
prior-reference +offsets (QQQ pts 0,+-0.5,+-1,+-1.5,+-2,+-3 ~ NQ
0..+-120). Config per rung: tgt 260 / stop 80 / hold 240m / both
dirs / no confirm (the robust plateau center). ONE account:
concurrency caps M in {1,3,5,7,14}; skipped entries when full.
Outputs: $/wk, tr/wk, WR, avgW/avgL, best/worst day, MDD, per-year,
long-only/short-only splits. $1.50/RT worst-case.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq
sys.path.insert(0, "research")
PT, TICK, FEES = 2.0, 0.25, 1.50
LAT = 65_000_000
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO_H, HI_H = 14.0, 20.44
TGT, STP, HOLD = 260.0, 80.0, 240
OFFS = (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 3.0, -3.0)

M2 = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
M2.index = pd.Index(pd.to_datetime(M2.index).astype(str).str[:10])
S1 = M2["S"].shift(1)
TRADES = []          # (t_in, t_out, side, pnl, rung)


def bracket(tsd, pxd, fi, entry, s, t_max, n):
    xe = min(np.searchsorted(tsd, t_max, "left"), n - 1)
    if xe <= fi:
        return None, fi
    tl, sl = entry + TGT * s, entry - STP * s
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


def process(ts, px):
    d = ts // 86_400_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(d)) + 1))
    en = np.concatenate((st[1:], [len(ts)]))
    for di in range(len(st)):
        day0 = int(d[st[di]]) * 86_400_000_000_000
        dstr = str(pd.Timestamp(day0).date())
        s1 = S1.get(dstr)
        if s1 is None or not np.isfinite(s1):
            continue
        a, b = st[di], en[di]
        tsd, pxd = ts[a:b], px[a:b]
        n = len(tsd)
        i0 = np.searchsorted(tsd, day0 + int(LO_H * 3600e9))
        i1 = np.searchsorted(tsd, day0 + int(HI_H * 3600e9))
        if i1 - i0 < 10_000:
            continue
        ratio = pxd[min(i0, n - 1)] / s1
        for ri, off in enumerate(OFFS):
            lev = (s1 + off) * ratio
            abv = pxd[i0:i1] > lev
            fx = i0 + np.flatnonzero(abv != np.roll(abv, 1))[1:][:40]
            busy = 0
            for j in fx:
                if tsd[j] < busy:
                    continue
                s_ = 1 if pxd[j] > lev else -1
                fi = np.searchsorted(tsd, tsd[j] + LAT)
                if fi >= n:
                    break
                entry = pxd[fi] + TICK * s_
                t_max = min(tsd[fi] + HOLD * 60_000_000_000,
                            day0 + EOD_NS)
                fill, k = bracket(tsd, pxd, fi, entry, s_, t_max, n)
                if fill is None:
                    continue
                TRADES.append((int(tsd[fi]), int(tsd[k]), s_,
                               (fill - entry) * s_ * PT - FEES, ri))
                busy = tsd[k]


t0 = time.time()
pf = pq.ParquetFile("data/tick/nq_ticks_2p5y.parquet")
YB = {}
for batch in pf.iter_batches(batch_size=8_000_000,
                             columns=["ts", "price"]):
    bt = batch.column("ts").to_numpy()
    bp_ = batch.column("price").to_numpy().astype(np.float32)
    keep = (bt >= 1_721_000_000_000_000_000) & (bt < 1_767_225_600_000_000_000)
    bt, bp_ = bt[keep], bp_[keep]
    if not len(bt):
        continue
    for y in np.unique(bt // 31_536_000_000_000_000):
        m_ = (bt // 31_536_000_000_000_000) == y
        YB.setdefault(int(y), []).append((bt[m_], bp_[m_]))
for y in sorted(YB):
    ts = np.concatenate([a for a, _ in YB[y]])
    px = np.concatenate([b for _, b in YB[y]]).astype(np.float64)
    YB[y] = None; gc.collect()
    o = np.argsort(ts, kind="stable"); ts, px = ts[o], px[o]
    wd = (ts // 86_400_000_000_000 + 4) % 7
    keep = np.isfinite(px) & (wd < 5)
    ts, px = ts[keep], px[keep]
    if len(ts) > 500_000:
        process(ts, px)
    del ts, px; gc.collect()
    print(f"chunk {y} ({time.time()-t0:.0f}s)", flush=True)
import round54_clock as K
K.build_tape()
process(K.D["ts"], K.D["px"])
print(f"raw rung-trades: {len(TRADES)} ({time.time()-t0:.0f}s)",
      flush=True)
TR = sorted(TRADES)
for M in (1, 3, 5, 7, 14):
    open_x = []
    keep = []
    for (ti, to, s_, pnl, ri) in TR:
        open_x = [x for x in open_x if x > ti]
        if len(open_x) >= M:
            continue
        keep.append((ti, to, s_, pnl))
        open_x.append(to)
    p = np.array([k[3] for k in keep])
    et = np.array([k[1] for k in keep])
    sd = np.array([k[2] for k in keep])
    sr = pd.Series(p, index=pd.to_datetime(et, utc=True)).sort_index()
    dy = sr.resample("D").sum(); dy = dy[dy != 0]
    wk = sr.resample("W").sum(); wk = wk[wk != 0]
    eq = dy.cumsum()
    mdd = float((eq - eq.cummax()).min())
    wins = p[p > 0]
    print(f"\n== CAP {M} rungs ==  n={len(p)} "
          f"({len(p)/len(wk):.1f}/wk)")
    print(f"  $/wk {sr.sum()/len(wk):+.0f} | WR {(p>0).mean()*100:.1f}%"
          f" | avgW {wins.mean():+.0f} | avgL {p[p<0].mean():+.0f}")
    print(f"  best day {dy.max():+.0f} | worst day {dy.min():+.0f} | "
          f"MDD {mdd:+.0f} | posW {(wk>0).mean()*100:.0f}%")
    for yr in sorted(set(sr.index.year)):
        sy = sr[sr.index.year == yr]
        w2 = sy.resample("W").sum(); w2 = w2[w2 != 0]
        print(f"    {yr}: {sy.sum()/max(len(w2),1):+.0f}/wk "
              f"posW {(w2>0).mean()*100:.0f}%")
    for lab, msk in (("LONG", sd > 0), ("SHORT", sd < 0)):
        sp = p[msk]
        print(f"    {lab}: n={len(sp)} avg {sp.mean():+.1f} "
              f"tot {sp.sum():+.0f}")
print(f"\nDONE ({time.time()-t0:.0f}s)")

# ---- dump daily P&L per cap for the PDF report
import json as _j
out = {}
for M in (1, 3, 5, 7):
    open_x = []; keep2 = []
    for (ti, to, s_, pnl, ri) in TR:
        open_x = [x for x in open_x if x > ti]
        if len(open_x) >= M: continue
        keep2.append((to, pnl)); open_x.append(to)
    sr = pd.Series([k[1] for k in keep2],
                   index=pd.to_datetime([k[0] for k in keep2], utc=True)).sort_index()
    dy = sr.resample("D").sum(); dy = dy[dy != 0]
    out[str(M)] = {str(k.date()): round(float(v), 2) for k, v in dy.items()}
with open("research/ladder_daily_clean.json", "w") as f:
    _j.dump(out, f)
print("csv-dumped")

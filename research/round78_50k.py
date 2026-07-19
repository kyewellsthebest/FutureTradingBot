"""Round 78: 43,200 configs - level-break mechanics x THREE daily
level sources (all lag-1, tradable): GAMMA-FLIP vs PIN-strike vs
PRIOR-CLOSE reference. Decides whether the gamma level is special
or any level works. tgt(10) x stop(8) x hold(5) x confirm(4) x
dir(3) x gate(3) = 14,400 per source.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq
sys.path.insert(0, "research")
import round76_massgrid as G

t0 = time.time()
M1 = pd.read_csv("research/gexmap_daily.csv", index_col=0)
M2 = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
M2.index = pd.Index(pd.to_datetime(M2.index).astype(str).str[:10])
M = M1.join(M2["ngp2"], how="inner")
M["sticky"] = M["ngp2"].shift(1) > 0
SRC = {
    "FLIP": M["flip"].shift(1),
    "PIN": M["pin"].shift(1),
    "PREV": M["S"].shift(1),
}
S1 = M["S"].shift(1)

CFGS = []
for tg in (30., 50., 70., 90., 110., 140., 170., 200., 250., 300.):
    for st_ in (10., 15., 20., 30., 40., 50., 65., 80.):
        for hd in (15, 30, 60, 120, 240):
            for cf in (0, 60, 180, 300):
                for dr in ("b", "s", "l"):
                    for gt in ("all", "st", "sl"):
                        CFGS.append(("F", dr, tg, st_, cf, gt, hd))
NCC = len(CFGS)
print(f"{NCC} configs x {len(SRC)} sources = {NCC*len(SRC)}",
      flush=True)

pf = pq.ParquetFile("data/tick/nq_ticks_2p5y.parquet")
YB = {}
for batch in pf.iter_batches(batch_size=8_000_000,
                             columns=["ts", "price"]):
    bt = batch.column("ts").to_numpy()
    bp_ = batch.column("price").to_numpy().astype(np.float32)
    keep = bt >= 1_721_000_000_000_000_000
    bt, bp_ = bt[keep], bp_[keep]
    if not len(bt):
        continue
    for y in np.unique(bt // 31_536_000_000_000_000):
        m_ = (bt // 31_536_000_000_000_000) == y
        YB.setdefault(int(y), []).append((bt[m_], bp_[m_]))
years = {}
for y in sorted(YB):
    ts = np.concatenate([a for a, _ in YB[y]])
    px = np.concatenate([b for _, b in YB[y]]).astype(np.float64)
    YB[y] = None; gc.collect()
    o = np.argsort(ts, kind="stable"); ts, px = ts[o], px[o]
    wd = (ts // 86_400_000_000_000 + 4) % 7
    keep = np.isfinite(px) & (wd < 5)
    years[y] = (ts[keep], px[keep])
    del ts, px; gc.collect()
import round54_clock as K
K.build_tape()
years["26w"] = (K.D["ts"], K.D["px"])
print(f"tapes ready ({time.time()-t0:.0f}s)", flush=True)

for src, lv in SRC.items():
    lvl = {}
    for d in M.index:
        s1 = S1.get(d); f1 = lv.get(d)
        if np.isfinite(s1) and np.isfinite(f1):
            lvl[d] = (s1, f1, np.nan, bool(M.loc[d, "sticky"]))
    G.CFG.clear(); G.CFG.extend(CFGS)
    G.NC = NCC
    G.SUM = np.zeros(NCC); G.NTR = np.zeros(NCC, np.int64)
    G.WIN = np.zeros(NCC, np.int64); G.TOP3 = np.zeros((NCC, 3))
    G.WEEK = {}
    for y, (ts, px) in years.items():
        if len(ts) > 500_000:
            G.process(ts, px, lvl)
    Wm = np.stack(list(G.WEEK.values()))
    nwk = np.maximum((Wm != 0).sum(0), 1)
    usd_wk = G.SUM / nwk
    posw = (Wm > 0).sum(0) / nwk * 100
    clip3 = G.SUM - G.TOP3.sum(1)
    wr = np.where(G.NTR > 0, G.WIN / np.maximum(G.NTR, 1) * 100, 0)
    ok = (G.NTR >= 100) & (clip3 > 0) & (usd_wk > 0) & (posw >= 55)
    print(f"\n==== {src}: survivors {int(ok.sum())} of {NCC} ====",
          flush=True)
    order = np.argsort(-usd_wk)
    shown = 0
    for ci in order:
        if not ok[ci]:
            continue
        print(f"  {str(G.CFG[ci]):<42} n={G.NTR[ci]:>4} "
              f"WR {wr[ci]:>4.1f}% {usd_wk[ci]:>+7.0f}/wk "
              f"clip3 {clip3[ci]:>+8.0f} posW {posw[ci]:>3.0f}%",
              flush=True)
        shown += 1
        if shown >= 15:
            break
    np.savez(f"research/round78_{src}.npz", usd_wk=usd_wk,
             posw=posw, clip3=clip3, wr=wr, NTR=G.NTR)
    print(f"({time.time()-t0:.0f}s)", flush=True)
print(f"\nDONE ({time.time()-t0:.0f}s)")

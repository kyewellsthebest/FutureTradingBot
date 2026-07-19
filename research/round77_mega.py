"""Round 77: 22,824-config mega grid on LAG-1 (tradable) gamma
levels. FLIPBREAK deep: tgt{40,60,80,100,120,150,180,220} x
stop{10,15,20,30,40,60} x hold{30,60,120,240}m x confirm{0,60,180,
300}s x dir{b,s,l} x gate{all,st,sl} = 13,824. PIN retest with
independent brackets: D{20..170}(8) x tgt{10,20,30,50,80} x
stop{10,20,30,40,60} x tmr{15,30,60} x gate{3} = 9,000.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq
sys.path.insert(0, "research")
import round76_massgrid as G

t0 = time.time()
G.CFG.clear()
for tg in (40.0, 60.0, 80.0, 100.0, 120.0, 150.0, 180.0, 220.0):
    for st_ in (10.0, 15.0, 20.0, 30.0, 40.0, 60.0):
        for hd in (30, 60, 120, 240):
            for cf in (0, 60, 180, 300):
                for dr in ("b", "s", "l"):
                    for gt in ("all", "st", "sl"):
                        G.CFG.append(("F", dr, tg, st_, cf, gt, hd))
for D in G.D_SET:
    for tm in ("f10", "f20", "f30", "f50", "f80"):
        for sm_fx in (10.0, 20.0, 30.0, 40.0, 60.0):
            for tmr in (15, 30, 60):
                for gt in ("all", "st", "sl"):
                    # encode fixed stop via sm = sm_fx / D
                    G.CFG.append(("P", D, tm, sm_fx / D, tmr, gt))
NC = len(G.CFG)
G.NC = NC
G.SUM = np.zeros(NC); G.NTR = np.zeros(NC, np.int64)
G.WIN = np.zeros(NC, np.int64); G.TOP3 = np.zeros((NC, 3))
G.WEEK = {}
print(f"configs: {NC}", flush=True)
M1 = pd.read_csv("research/gexmap_daily.csv", index_col=0)
M2 = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
M2.index = pd.Index(pd.to_datetime(M2.index).astype(str).str[:10])
M = M1.join(M2["ngp2"], how="inner")
M["sticky"] = M["ngp2"].shift(1) > 0
lvl = {d: (r["S"], r["flip"], r["pin"], bool(r["sticky"]))
       for d, r in M.assign(S=M["S"].shift(1),
                            flip=M["flip"].shift(1),
                            pin=M["pin"].shift(1)).iterrows()
       if np.isfinite(r["S"])}
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
    for y in np.unique(bt // 31_536_000_000_000_000):
        m_ = (bt // 31_536_000_000_000_000) == y
        buckets.setdefault(int(y), []).append((bt[m_], bp_[m_]))
for y in sorted(buckets):
    ts = np.concatenate([a for a, _ in buckets[y]])
    px = np.concatenate([b for _, b in buckets[y]]).astype(np.float64)
    buckets[y] = None; gc.collect()
    o = np.argsort(ts, kind="stable"); ts, px = ts[o], px[o]
    wd = (ts // 86_400_000_000_000 + 4) % 7
    keep = np.isfinite(px) & (wd < 5)
    ts, px = ts[keep], px[keep]
    if len(ts) > 500_000:
        G.process(ts, px, lvl)
    del ts, px; gc.collect()
    print(f"chunk {y} done ({time.time()-t0:.0f}s)", flush=True)
import round54_clock as K
K.build_tape()
G.process(K.D["ts"], K.D["px"], lvl)
print(f"sims done ({time.time()-t0:.0f}s)", flush=True)
Wm = np.stack(list(G.WEEK.values()))
nwk = np.maximum((Wm != 0).sum(0), 1)
usd_wk = G.SUM / nwk
posw = (Wm > 0).sum(0) / nwk * 100
clip3 = G.SUM - G.TOP3.sum(1)
wr = np.where(G.NTR > 0, G.WIN / np.maximum(G.NTR, 1) * 100, 0)
ok = (G.NTR >= 100) & (clip3 > 0) & (usd_wk > 0) & (posw >= 55)
print(f"\nsurvivors (n>=100, $/wk>0, clip3>0, posW>=55%): "
      f"{int(ok.sum())} of {NC}", flush=True)
order = np.argsort(-usd_wk)
shown = 0
print(f"{'config':<44} {'n':>5} {'WR%':>5} {'$/wk':>7} "
      f"{'clip3':>8} {'posW%':>6}")
for ci in order:
    if not ok[ci]:
        continue
    print(f"{str(G.CFG[ci]):<44} {G.NTR[ci]:>5} {wr[ci]:>5.1f} "
          f"{usd_wk[ci]:>+7.0f} {clip3[ci]:>+8.0f} "
          f"{posw[ci]:>6.0f}", flush=True)
    shown += 1
    if shown >= 40:
        break
np.savez("research/round77_results.npz", SUM=G.SUM, NTR=G.NTR,
         usd_wk=usd_wk, posw=posw, clip3=clip3, wr=wr)
print(f"\nDONE {NC} configs ({time.time()-t0:.0f}s)")

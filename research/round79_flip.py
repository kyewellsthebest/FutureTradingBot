"""Round 79: SWING-HARVEST (user spec: catch every up/down move).
Always-in-market pivot-flip: long until price retraces R pts off
the running high -> flip short, vice versa. Captures every swing
> R by construction; fees charged on every flip. Grid: R x session
x gamma-gate x min-hold. 2y, worst-case $1.50/RT per flip.
"""
import gc, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq
sys.path.insert(0, "research")
PT, FEES = 2.0, 1.50
LO_H, HI_H = 14.0, 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000

M2 = pd.read_csv("research/gexmap2_daily.csv", index_col=0)
M2.index = pd.Index(pd.to_datetime(M2.index).astype(str).str[:10])
STICKY = (M2["ngp2"].shift(1) > 0).to_dict()

RES = {}


def process(ts, px):
    d = ts // 86_400_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(d)) + 1))
    en = np.concatenate((st[1:], [len(ts)]))
    for di in range(len(st)):
        day0 = int(d[st[di]]) * 86_400_000_000_000
        dstr = str(pd.Timestamp(day0).date())
        a, b = st[di], en[di]
        i0 = np.searchsorted(ts[a:b], day0 + int(LO_H * 3600e9)) + a
        i1 = np.searchsorted(ts[a:b], day0 + EOD_NS) + a
        if i1 - i0 < 10_000:
            continue
        sk = STICKY.get(dstr)
        p = px[i0:i1:25]                 # 25-tick stride ~ sub-sec
        t_ = ts[i0:i1:25]
        wk = (day0 // 86_400_000_000_000 + 3) // 7
        for R in (15.0, 25.0, 40.0, 60.0, 80.0):
            for gate in ("all", "st", "sl"):
                if gate == "st" and sk is not True:
                    continue
                if gate == "sl" and sk is not False:
                    continue
                key = (R, gate)
                pos = 0; entry = 0.0; ext = p[0]
                pnl = 0.0; ntr = 0
                for j in range(1, len(p)):
                    x = p[j]
                    if pos == 0:
                        if x > ext + R:
                            pos = 1; entry = x
                        elif x < ext - R:
                            pos = -1; entry = x
                        ext = min(ext, x) if pos >= 0 else ext
                        continue
                    if pos == 1:
                        ext = max(ext, x)
                        if x <= ext - R:
                            pnl += (x - entry) * PT - FEES
                            ntr += 1
                            pos = -1; entry = x; ext = x
                    else:
                        ext = min(ext, x)
                        if x >= ext + R:
                            pnl += (x - entry) * -PT - FEES
                            ntr += 1
                            pos = 1; entry = x; ext = x
                if pos != 0:
                    pnl += (p[-1] - entry) * pos * PT - FEES
                    ntr += 1
                r = RES.setdefault(key, {})
                r.setdefault(wk, [0.0, 0])
                r[wk][0] += pnl; r[wk][1] += ntr


t0 = time.time()
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
print(f"\n{'R':>4} {'gate':>5} {'tr/wk':>7} {'$/wk@1.50':>10} "
      f"{'$/wk@0.78':>10} {'$/wk@0.22':>10} {'posW%':>6}", flush=True)
for (R, gate), wkd in sorted(RES.items()):
    W = np.array([[v[0], v[1]] for v in wkd.values()])
    nwk = len(W)
    trwk = W[:, 1].sum() / nwk
    for tag, fee in (("", 0.0), ("b", 0.72), ("f", 1.28)):
        pass
    u150 = W[:, 0].sum() / nwk
    u078 = (W[:, 0].sum() + 0.72 * W[:, 1].sum()) / nwk
    u022 = (W[:, 0].sum() + 1.28 * W[:, 1].sum()) / nwk
    posw = ((W[:, 0]) > 0).mean() * 100
    print(f"{R:>4.0f} {gate:>5} {trwk:>7.1f} {u150:>+10.0f} "
          f"{u078:>+10.0f} {u022:>+10.0f} {posw:>6.0f}", flush=True)
print(f"\nDONE ({time.time()-t0:.0f}s)")

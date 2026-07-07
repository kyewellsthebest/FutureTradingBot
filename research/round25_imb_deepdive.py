"""Round 25b: deep-dive the order-flow imbalance follow (E_IMBF).
Signal: rolling W-minute sum of signed tick volume exceeds M x its
30-min average magnitude -> follow for HOLD minutes. RTH.
1) neighborhood grid (sel Apr-May / blind Jun-Jul6)
2) week-by-week 2026 YTD for the select-chosen config
3) execution stress pads
Tick-walked fills, $1.50 commission."""
import glob, os, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
SEL_LO = pd.Timestamp("2026-04-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")
CACHE = "data/tick/ytd2026sz.npz"


def load_ticks():
    if os.path.exists(CACHE):
        z = np.load(CACHE)
        return z["ts"], z["px"], z["sz"]
    start = pd.Timestamp("2026-01-01", tz="UTC").value
    parts = []
    for f in ("data/tick/raw/NQH6.parquet", "data/tick/raw/NQM6.parquet"):
        pf = pq.ParquetFile(f)
        for i in range(pf.num_row_groups):
            t = pf.read_row_group(i, columns=["ts", "price", "size"]).to_pandas()
            t = t[t["ts"] >= start]
            if len(t):
                parts.append(t)
    for f in sorted(glob.glob("/tmp/claude-0/weekticks/MNQU6_2026*.parquet")):
        t = pd.read_parquet(f)
        if len(t):
            parts.append(t[["ts", "price", "size"]])
    a = pd.concat(parts, ignore_index=True).sort_values("ts", kind="mergesort")
    ts = a["ts"].to_numpy(np.int64)
    px = a["price"].to_numpy(np.float64)
    sz = a["size"].to_numpy(np.float64)
    np.savez_compressed(CACHE, ts=ts, px=px, sz=sz)
    return ts, px, sz


def main():
    t0 = time.time()
    ts, px, sz = load_ticks()
    print(f"YTD ticks w/ size: {len(ts):,} ({time.time()-t0:.0f}s)", flush=True)
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px, "iv": d * sz})
    agg = g.groupby("m").agg(open=("px", "first"), close=("px", "last"),
                             high=("px", "max"), low=("px", "min"),
                             iv=("iv", "sum"))
    agg.index = pd.to_datetime(agg.index, utc=True)
    c = agg["close"].to_numpy()
    idx = agg.index
    bts = idx.asi8 + 60_000_000_000
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    iv = agg["iv"].to_numpy()
    rth = (hrs >= 13.5) & (hrs < 20.9)
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    n = len(ts)

    def run(times, sides, hold_min, pad=TICK, lat=LAT_NS):
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for t, s in zip(times, sides):
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + lat, side="left")
            if ei >= n:
                break
            e = px[ei] + pad * s
            xj = np.searchsorted(ts, t + hn + lat, side="left")
            if xj >= n:
                break
            out.append((ts[xj], (px[xj] - pad * s - e) * s * PT - FEES))
            busy = ts[xj]
        return out

    def wkst(out, lo, hi):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        if not len(s):
            return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0)
        w = s.resample("W").sum(); w = w[w != 0]
        weeks = max(len(w), 1)
        return dict(usd_wk=round(s.sum() / weeks, 0),
                    tr_wk=round(len(s) / weeks, 1), per=round(s.mean(), 2),
                    worst=round(w.min(), 0), pos=round((w > 0).mean() * 100))

    # ---- 1) neighborhood ---------------------------------------------------
    print("\n=== neighborhood (sel Apr-May | blind Jun-Jul6, $/wk [tr/wk]) ===")
    rows = []
    for W in (5, 10, 20):
        ima = pd.Series(iv).rolling(W).sum().to_numpy()
        ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
        for M in (2.0, 3.0, 4.0, 6.0):
            thr = M * np.nan_to_num(ias, nan=np.inf)
            for stag, smask in (("rth", rth), ("skip30", skip30)):
                sig = np.where((ima > thr) & smask, 1,
                               np.where((ima < -thr) & smask, -1, 0))
                live = np.flatnonzero(sig != 0)
                if len(live) < 100:
                    continue
                for hold in (15, 30, 45, 60):
                    out = run(bts[live], sig[live], hold)
                    a = wkst(out, SEL_LO, SPLIT); b = wkst(out, SPLIT, END)
                    rows.append({"W": W, "M": M, "sess": stag, "hold": hold,
                                 "sel_wk": a["usd_wk"], "sel_tr": a["tr_wk"],
                                 "bl_wk": b["usd_wk"], "bl_tr": b["tr_wk"],
                                 "bl_per": b["per"], "bl_worst": b["worst"],
                                 "bl_pos": b["pos"]})
        print(f"  W={W} done ({time.time()-t0:.0f}s)", flush=True)
    grid = pd.DataFrame(rows)
    grid.to_csv("research/round25_imb_grid.csv", index=False)
    top = grid.sort_values("sel_wk", ascending=False)
    print(top.head(15).to_string(index=False))
    both = grid[(grid.sel_wk > 0) & (grid.bl_wk > 0)]
    print(f"\nboth-positive neighbors: {len(both)}/{len(grid)}")

    # ---- 2) YTD weekly for select-chosen best ------------------------------
    bestrow = top.iloc[0]
    W, M, stag, hold = int(bestrow["W"]), float(bestrow["M"]), bestrow["sess"], int(bestrow["hold"])
    print(f"\n=== select-chosen: W{W} M{M} {stag} t{hold} — weekly 2026 YTD ===")
    ima = pd.Series(iv).rolling(W).sum().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    thr = M * np.nan_to_num(ias, nan=np.inf)
    smask = rth if stag == "rth" else skip30
    sig = np.where((ima > thr) & smask, 1, np.where((ima < -thr) & smask, -1, 0))
    live = np.flatnonzero(sig != 0)
    out = run(bts[live], sig[live], hold)
    s = pd.Series([p for _, p in out],
                  index=pd.to_datetime([t for t, _ in out], utc=True))
    w = s.resample("W").sum(); cnt = s.resample("W").count()
    for i in range(len(w)):
        if cnt.iloc[i] == 0:
            continue
        print(f"  {w.index[i].date()}  ${w.iloc[i]:8.0f}  ({cnt.iloc[i]:3d} tr)")
    q = s[s.index >= pd.Timestamp("2026-03-01", tz="UTC")]
    wq = q.resample("W").sum(); wq = wq[wq != 0]
    print(f"  YTD ${s.sum():.0f} | since Mar 1: ${q.sum()/max(len(wq),1):.0f}/wk, "
          f"{(wq>0).mean()*100:.0f}% pos, worst ${wq.min():.0f}, "
          f"{len(q)/max(len(wq),1):.1f} tr/wk")

    # ---- 3) stress ---------------------------------------------------------
    print("\n=== stress (blind Jun-Jul6) ===")
    for pad, lat, tag in ((0.25, 65_000_000, "1-tick 65ms"),
                          (0.50, 65_000_000, "2-tick 65ms"),
                          (0.50, 200_000_000, "2-tick 200ms"),
                          (0.75, 500_000_000, "3-tick 500ms")):
        out2 = run(bts[live], sig[live], hold, pad=pad, lat=lat)
        b = wkst(out2, SPLIT, END)
        print(f"  {tag}: ${b['usd_wk']:.0f}/wk, ${b['per']:.2f}/trade, "
              f"worst wk ${b['worst']:.0f}, {b['tr_wk']} tr/wk")


if __name__ == "__main__":
    main()

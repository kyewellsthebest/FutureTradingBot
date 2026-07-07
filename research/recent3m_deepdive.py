"""Round 24b: deep-dive the recent-regime champion — RTH overextension
fade (MOMR: fade a k-bar move > a*ATR, time exit).
1) Parameter neighborhood (plateau or lucky spike?)
2) Week-by-week P&L for ALL of 2026 (NQH6 Jan-Mar + NQM6 Mar-Jun + week
   files) — how long has this regime paid, is it strengthening?
3) Execution stress: double adverse ticks, 200 ms latency.
All fills tick-walked; $1.50 commission."""
import glob, os, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

PT = 2.0
FEES = 1.50
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
CACHE = "data/tick/ytd2026.npz"


def load_ticks():
    if os.path.exists(CACHE):
        z = np.load(CACHE)
        return z["ts"], z["px"]
    start = pd.Timestamp("2026-01-01", tz="UTC").value
    parts = []
    for f in ("data/tick/raw/NQH6.parquet", "data/tick/raw/NQM6.parquet"):
        pf = pq.ParquetFile(f)
        for i in range(pf.num_row_groups):
            t = pf.read_row_group(i, columns=["ts", "price"]).to_pandas()
            t = t[t["ts"] >= start]
            if len(t):
                parts.append(t)
    for f in sorted(glob.glob("/tmp/claude-0/weekticks/MNQU6_2026*.parquet")):
        t = pd.read_parquet(f)
        if len(t):
            parts.append(t[["ts", "price"]])
    a = pd.concat(parts, ignore_index=True).sort_values("ts", kind="mergesort")
    ts = a["ts"].to_numpy(np.int64)
    px = a["price"].to_numpy(np.float64)
    np.savez_compressed(CACHE, ts=ts, px=px)
    return ts, px


def run(ts, px, sig_times, sig_sides, hold_min, tick_pad=0.25, lat_ns=65_000_000):
    out = []
    busy_until = 0
    hold_ns = int(hold_min * 60_000_000_000)
    n = len(ts)
    for t, s in zip(sig_times, sig_sides):
        if t < busy_until:
            continue
        ei = np.searchsorted(ts, t + lat_ns, side="left")
        if ei >= n:
            break
        entry = px[ei] + tick_pad * s
        xj = np.searchsorted(ts, t + hold_ns + lat_ns, side="left")
        if xj >= n:
            break
        fill = px[xj] - tick_pad * s
        out.append((ts[xj], (fill - entry) * s * PT - FEES))
        busy_until = ts[xj]
    return out


def series(out):
    return pd.Series([p for _, p in out],
                     index=pd.to_datetime([t for t, _ in out], utc=True))


def main():
    t0 = time.time()
    ts, px = load_ticks()
    print(f"2026 YTD ticks: {len(ts):,} ({time.time()-t0:.0f}s)", flush=True)
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px})
    bars = g.groupby("m")["px"].agg(open="first", high="max", low="min", close="last")
    bars.index = pd.to_datetime(bars.index, utc=True)
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    idx = bars.index
    bts = idx.asi8 + 60_000_000_000
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    rth = (hrs >= 13.5) & (hrs < 20.9)
    ret1 = c - np.roll(c, 1); ret1[0] = 0
    tr = np.maximum(h - l, np.abs(ret1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    sel_lo = pd.Timestamp("2026-04-01", tz="UTC")

    # ---- 1) neighborhood grid, select Apr-May / blind Jun-Jul6 ------------
    print("\n=== neighborhood (sel=Apr-May, blind=Jun-Jul6, $/wk) ===")
    rows = []
    for k in (10, 15, 20, 30):
        mom = c - np.roll(c, k); mom[:k] = 0
        for a in (1.2, 1.5, 2.0, 3.0):
            thr = a * np.nan_to_num(atr, nan=np.inf)
            sig = np.where((mom < -thr) & rth, 1,
                           np.where((mom > thr) & rth, -1, 0))
            live = np.flatnonzero(sig != 0)
            for hold in (10, 15, 20, 30):
                out = run(ts, px, bts[live], sig[live], hold)
                s = series(out)
                ssel = s[(s.index >= sel_lo) & (s.index < SPLIT)]
                sbl = s[s.index >= SPLIT]
                wsel = ssel.resample("W").sum(); wsel = wsel[wsel != 0]
                wbl = sbl.resample("W").sum(); wbl = wbl[wbl != 0]
                rows.append({
                    "k": k, "a": a, "hold": hold,
                    "sel_wk": round(ssel.sum() / max(len(wsel), 1), 0),
                    "bl_wk": round(sbl.sum() / max(len(wbl), 1), 0),
                    "bl_tr_wk": round(len(sbl) / max(len(wbl), 1), 1),
                    "bl_per": round(sbl.mean(), 2) if len(sbl) else 0,
                })
    grid = pd.DataFrame(rows)
    print(grid.pivot_table(index=["k", "a"], columns="hold", values="bl_wk")
          .round(0).to_string())
    both = grid[(grid.sel_wk > 0) & (grid.bl_wk > 0)]
    print(f"\nboth-positive neighbors: {len(both)}/{len(grid)}")

    # ---- 2) champion weekly P&L, all 2026 ---------------------------------
    k, a, hold = 15, 1.5, 15
    mom = c - np.roll(c, k); mom[:k] = 0
    thr = a * np.nan_to_num(atr, nan=np.inf)
    sig = np.where((mom < -thr) & rth, 1, np.where((mom > thr) & rth, -1, 0))
    live = np.flatnonzero(sig != 0)
    out = run(ts, px, bts[live], sig[live], hold)
    s = series(out)
    w = s.resample("W").sum()
    cnt = s.resample("W").count()
    print("\n=== champion k15 a1.5 t15 rth — weekly P&L 2026 YTD ===")
    for i in range(len(w)):
        if cnt.iloc[i] == 0:
            continue
        print(f"  {w.index[i].date()}  ${w.iloc[i]:8.0f}   ({cnt.iloc[i]} trades)")
    print(f"TOTAL: ${s.sum():.0f} over {len(s)} trades "
          f"({(s > 0).mean()*100:.0f}% win, avg ${s.mean():.2f}/trade)")

    # ---- 3) execution stress ----------------------------------------------
    print("\n=== execution stress (blind window only) ===")
    for pad, lat, tag in ((0.25, 65_000_000, "base 1-tick pad, 65ms"),
                          (0.50, 65_000_000, "2-tick pad, 65ms"),
                          (0.50, 200_000_000, "2-tick pad, 200ms"),
                          (0.75, 500_000_000, "3-tick pad, 500ms")):
        out = run(ts, px, bts[live], sig[live], hold, tick_pad=pad, lat_ns=lat)
        s = series(out)
        sbl = s[s.index >= SPLIT]
        wbl = sbl.resample("W").sum(); wbl = wbl[wbl != 0]
        print(f"  {tag}: blind ${sbl.sum()/max(len(wbl),1):.0f}/wk, "
              f"${sbl.mean():.2f}/trade, worst wk ${wbl.min():.0f}")


if __name__ == "__main__":
    main()

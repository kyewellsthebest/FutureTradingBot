"""Round 25c: the current-regime portfolio question.
Five tick-fill-verified components, each week-by-week 2026 YTD at 1 MNQ:
  1. FADE  — MOMR k10 a1.2 skip30 t15 (round 24 champion)
  2. IMBF  — signed-volume follow W10 M3 rth t30 (round 25 discovery)
  3. BWEXP — 3m band-width expansion t40 rth (vault leg)
  4. CONSECC — 15m 4-bar run follow t60 (vault leg)
  5. NRB   — 5m narrowest-range-8 breakout t120 (vault leg)
Weekly correlation + combined equity, since-Mar and blind stats.
Tick-walked fills, $1.50 commission."""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
MAR = pd.Timestamp("2026-03-01", tz="UTC")


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    print(f"ticks: {n:,}", flush=True)

    def run(times, sides, hold_min):
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for t, s in zip(times, sides):
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, side="left")
            if ei >= n:
                break
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + hn + LAT_NS, side="left")
            if xj >= n:
                break
            out.append((ts[xj], (px[xj] - TICK * s - e) * s * PT - FEES))
            busy = ts[xj]
        return out

    def bars_tf(res_ns, with_iv=False):
        m = (ts // res_ns) * res_ns
        cols = {"m": m, "px": px}
        if with_iv:
            d = np.sign(np.diff(px, prepend=px[0]))
            cols["iv"] = d * sz
        g = pd.DataFrame(cols)
        spec = dict(open=("px", "first"), high=("px", "max"),
                    low=("px", "min"), close=("px", "last"))
        if with_iv:
            spec["iv"] = ("iv", "sum")
        a = g.groupby("m").agg(**spec)
        a.index = pd.to_datetime(a.index, utc=True)
        return a

    series = {}

    # ---- 1. FADE (1m) ------------------------------------------------------
    b = bars_tf(60_000_000_000, with_iv=True)
    c = b["close"].to_numpy(); h = b["high"].to_numpy(); l = b["low"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    mom = c - np.roll(c, 10); mom[:10] = 0
    thr = 1.2 * np.nan_to_num(atr, nan=np.inf)
    sig = np.where((mom < -thr) & skip30, 1,
                   np.where((mom > thr) & skip30, -1, 0))
    live = np.flatnonzero(sig != 0)
    series["FADE"] = run(bts[live], sig[live], 15)
    # ---- 2. IMBF (1m, needs iv) -------------------------------------------
    iv = b["iv"].to_numpy()
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    rth = (hrs >= 13.5) & (hrs < 20.9)
    thr = 3.0 * np.nan_to_num(ias, nan=np.inf)
    sig = np.where((ima > thr) & rth, 1, np.where((ima < -thr) & rth, -1, 0))
    live = np.flatnonzero(sig != 0)
    series["IMBF"] = run(bts[live], sig[live], 30)
    # ---- 3. BWEXP (3m) -----------------------------------------------------
    b3 = bars_tf(3 * 60_000_000_000)
    c3 = b3["close"].to_numpy(); o3 = b3["open"].to_numpy()
    i3 = b3.index; t3 = i3.asi8 + 3 * 60_000_000_000
    h3 = np.asarray(i3.hour) + np.asarray(i3.minute) / 60.0
    sd = pd.Series(c3).rolling(20).std().to_numpy()
    bw = 4 * sd
    exp_ = bw > 1.5 * np.roll(bw, 10); exp_[:30] = False
    rth3 = (h3 >= 13.5) & (h3 < 20.9)
    sig = np.where(exp_ & (c3 > o3) & rth3, 1,
                   np.where(exp_ & (c3 < o3) & rth3, -1, 0))
    live = np.flatnonzero(sig != 0)
    series["BWEXP"] = run(t3[live], sig[live], 120)
    # ---- 4. CONSECC (15m) --------------------------------------------------
    b15 = bars_tf(15 * 60_000_000_000)
    c15 = b15["close"].to_numpy(); o15 = b15["open"].to_numpy()
    i15 = b15.index; t15 = i15.asi8 + 15 * 60_000_000_000
    h15 = np.asarray(i15.hour) + np.asarray(i15.minute) / 60.0
    upb = c15 > o15
    r4 = np.array([j >= 3 and all(upb[j - 3:j + 1]) for j in range(len(c15))])
    d4 = np.array([j >= 3 and not any(upb[j - 3:j + 1]) for j in range(len(c15))])
    rth15 = (h15 >= 13.5) & (h15 < 20.9)
    sig = np.where(r4 & rth15, 1, np.where(d4 & rth15, -1, 0))
    live = np.flatnonzero(sig != 0)
    series["CONSECC"] = run(t15[live], sig[live], 60)
    # ---- 5. NRB (5m) -------------------------------------------------------
    b5 = bars_tf(5 * 60_000_000_000)
    c5 = b5["close"].to_numpy(); h5 = b5["high"].to_numpy(); l5 = b5["low"].to_numpy()
    i5 = b5.index; t5 = i5.asi8 + 5 * 60_000_000_000
    h5r = np.asarray(i5.hour) + np.asarray(i5.minute) / 60.0
    rth5 = (h5r >= 13.5) & (h5r < 20.9)
    rng5 = h5 - l5
    nrmin = pd.Series(rng5).rolling(8).min().shift(1).to_numpy()
    isnr = np.roll(rng5, 1) <= nrmin
    sig = np.where(rth5 & isnr & (c5 > np.roll(h5, 1)), 1,
                   np.where(rth5 & isnr & (c5 < np.roll(l5, 1)), -1, 0))
    live = np.flatnonzero(sig != 0)
    series["NRB"] = run(t5[live], sig[live], 120 * 5)

    # ---- weekly matrix -----------------------------------------------------
    wk = {}
    for k, out in series.items():
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        wk[k] = s.resample("W").sum()
        print(f"{k}: {len(s)} trades YTD ({time.time()-t0:.0f}s)", flush=True)
    W = pd.DataFrame(wk).fillna(0.0)
    W["TOTAL"] = W.sum(axis=1)
    print("\n=== weekly P&L matrix 2026 YTD (1 MNQ each, $ per week) ===")
    print(W.round(0).to_string())
    print("\n=== weekly correlations (since Mar 1) ===")
    Wm = W[W.index >= MAR]
    print(Wm.drop(columns="TOTAL").corr().round(2).to_string())
    print("\n=== summary since Mar 1 ===")
    tr_wk = {k: round(len([1 for t, _ in series[k]
                           if pd.Timestamp(t, tz='UTC') >= MAR]) /
                      max(len(Wm), 1), 1) for k in series}
    for k in list(series) + ["TOTAL"]:
        col = Wm[k]
        print(f"  {k:8s} ${col.mean():7.0f}/wk  worst ${col.min():7.0f}  "
              f"pos {(col > 0).mean()*100:3.0f}%  "
              f"{tr_wk.get(k, sum(tr_wk.values())):5.1f} tr/wk")
    print("\n=== blind only (Jun 1 - Jul 6) ===")
    Wb = W[W.index >= SPLIT]
    for k in list(series) + ["TOTAL"]:
        col = Wb[k]
        print(f"  {k:8s} ${col.mean():7.0f}/wk  worst ${col.min():7.0f}  "
              f"pos {(col > 0).mean()*100:3.0f}%")


if __name__ == "__main__":
    main()

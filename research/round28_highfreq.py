"""Round 28: HIGH-FREQUENCY hunt — 100-500 trades/week mandate.
Levers on validated edges (sel Apr-May, blind Jun 1 - Jul 6, tick fills):
  A. FLOW-HF: lower entry bar (2x), shorter holds (10-20m), ladder sizing
  B. FADESZ: the 110-tr/wk overextension fade + magnitude sizing (the
     trick that tripled FLOWSZ, never applied to FADE)
  C. RUNSZ: tick-run follow, lower run bar, sized by run length
  D. DIVSZ: flow/price divergence, shorter holds, sized
  E. PYRAMID: flow burst with up to 3 concurrent positions (one strategy,
     position management)
$1.50/RT per contract. Trades/wk reported; 500 hard cap flagged.
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
SEL_LO = pd.Timestamp("2026-04-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")
MAR = pd.Timestamp("2026-03-01", tz="UTC")


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    print(f"ticks: {n:,}", flush=True)
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px, "iv": d * sz})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           iv=("iv", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    o = b["open"].to_numpy(); h = b["high"].to_numpy()
    l = b["low"].to_numpy(); c = b["close"].to_numpy()
    iv = b["iv"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000; nb = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    rth = (hrs >= 13.5) & (hrs < 20.9)
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()

    def run(sig, qty, hold, pad=TICK, lat=LAT_NS):
        out = []
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0:
                i += 1; continue
            ei = np.searchsorted(ts, bts[i] + lat, side="left")
            if ei >= n:
                break
            e = px[ei] + pad * s
            j = min(i + hold, nb - 1)
            xi = np.searchsorted(ts, bts[j] + lat, side="left")
            if xi >= n:
                break
            q = 1 if qty is None else qty[i]
            out.append((ts[xi], ((px[xi] - pad * s - e) * s * PT - FEES) * q))
            i = j + 1
        return out

    def run_pyr(sig, qty, hold, cap):
        """Up to `cap` concurrent positions, each its own timer exit."""
        out = []
        open_pos = []          # list of exit-bar indices
        i = 0
        while i < nb - 2:
            open_pos = [x for x in open_pos if x > i]
            s = sig[i]
            if s != 0 and len(open_pos) < cap:
                ei = np.searchsorted(ts, bts[i] + LAT_NS, side="left")
                if ei >= n:
                    break
                e = px[ei] + TICK * s
                j = min(i + hold, nb - 1)
                xi = np.searchsorted(ts, bts[j] + LAT_NS, side="left")
                if xi >= n:
                    break
                q = 1 if qty is None else qty[i]
                out.append((ts[xi], ((px[xi] - TICK * s - e) * s * PT - FEES) * q))
                open_pos.append(j)
            i += 1
        return out

    def st(out, lo, hi):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        w = s.resample("W").sum(); w = w[w != 0]
        if not len(s) or not len(w):
            return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0)
        wkn = max(len(w), 1)
        return dict(usd_wk=round(s.sum() / wkn, 0), tr_wk=round(len(s) / wkn, 1),
                    per=round(s.mean(), 2), worst=round(w.min(), 0),
                    pos=round((w > 0).mean() * 100))

    rows = []

    def add(name, out):
        a = st(out, SEL_LO, SPLIT); bl = st(out, SPLIT, END)
        mr = st(out, MAR, END)
        rows.append({"name": name, "sel_usd_wk": a["usd_wk"],
                     "sel_tr_wk": a["tr_wk"], "bl_usd_wk": bl["usd_wk"],
                     "bl_tr_wk": bl["tr_wk"], "bl_per": bl["per"],
                     "bl_worst": bl["worst"], "bl_pos": bl["pos"],
                     "mar_usd_wk": mr["usd_wk"], "mar_worst": mr["worst"],
                     "mar_pos": mr["pos"],
                     "over_cap": max(a["tr_wk"], bl["tr_wk"]) > 500})

    # ---- A. FLOW-HF ---------------------------------------------------------
    for W in (5, 10):
        ima = pd.Series(iv).rolling(W).sum().to_numpy()
        mag = np.abs(np.nan_to_num(ima)) / np.where(np.nan_to_num(ias) > 0, ias, np.inf)
        for M in (2.0, 3.0):
            sig = np.where((ima > M * np.nan_to_num(ias, nan=np.inf)) & rth, 1,
                           np.where((ima < -M * np.nan_to_num(ias, nan=np.inf)) & rth,
                                    -1, 0))
            qty = np.where(mag >= 8, 3, np.where(mag >= 5, 2, 1)).astype(int)
            for hold in (10, 15, 20):
                add(f"A_FLOWHF_W{W}_M{M}_t{hold}", run(sig, qty, hold))
        print(f"[A W{W}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. FADESZ ----------------------------------------------------------
    mom10 = c - np.roll(c, 10); mom10[:10] = 0
    fmag = np.abs(mom10) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    for a_ in (1.2, 1.5):
        sig = np.where((mom10 < -a_ * np.nan_to_num(atr, nan=np.inf)) & skip30, 1,
                       np.where((mom10 > a_ * np.nan_to_num(atr, nan=np.inf)) & skip30,
                                -1, 0))
        for lad, l1, l2 in (("2/3x", 2.0, 3.0), ("2.5/4x", 2.5, 4.0)):
            qty = np.where(fmag >= l2, 3, np.where(fmag >= l1, 2, 1)).astype(int)
            for hold in (10, 15):
                add(f"B_FADESZ_a{a_}_{lad}_t{hold}", run(sig, qty, hold))
        print(f"[B a{a_}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. RUNSZ (tick runs, sized by run length) -------------------------
    nz = d != 0
    chg = np.flatnonzero(np.diff(np.where(nz, d, 0)) != 0) + 1
    last = np.zeros(n, dtype=np.int64)
    last[chg] = chg
    last = np.maximum.accumulate(last)
    runlen = np.arange(n) - last + 1
    hrs_t = ((ts // 3_600_000_000_000) % 24).astype(int)
    rth_t = (hrs_t >= 14) & (hrs_t < 21)

    def run_ticksig(fire, sides, qtys, hold_min):
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        ft = ts[fire]; fs = sides[fire]; fq = qtys[fire] if qtys is not None else None
        for k in range(len(ft)):
            t = ft[k]
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, side="left")
            if ei >= n:
                break
            s = int(fs[k]); q = 1 if fq is None else int(fq[k])
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + hn + LAT_NS, side="left")
            if xj >= n:
                break
            out.append((ts[xj], ((px[xj] - TICK * s - e) * s * PT - FEES) * q))
            busy = ts[xj]
        return out

    for R in (10, 15):
        fire = (runlen == R) & nz & rth_t
        ql = np.ones(n, dtype=int)      # size at fire is 1 (run == R exactly)
        for hold in (5, 10, 15):
            add(f"C_RUNF_R{R}_t{hold}", run_ticksig(fire, d, None, hold))
        # sized: also fire again at 1.5R and 2R with bigger size
        fire2 = ((runlen == R) | (runlen == int(1.5 * R)) | (runlen == 2 * R)) \
            & nz & rth_t
        qs = np.where(runlen >= 2 * R, 3,
                      np.where(runlen >= int(1.5 * R), 2, 1)).astype(int)
        for hold in (5, 15):
            add(f"C_RUNSZ_R{R}_t{hold}", run_ticksig(fire2, d, qs, hold))
        print(f"[C R{R}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. DIVSZ -----------------------------------------------------------
    ima10 = pd.Series(iv).rolling(10).sum().to_numpy()
    mag10 = np.abs(np.nan_to_num(ima10)) / np.where(np.nan_to_num(ias) > 0, ias, np.inf)
    mom15 = c - np.roll(c, 15); mom15[:15] = 0
    flat = np.abs(mom15) < 0.5 * np.nan_to_num(atr, nan=np.inf)
    sig = np.where(flat & (ima10 > 3 * np.nan_to_num(ias, nan=np.inf)) & rth, 1,
                   np.where(flat & (ima10 < -3 * np.nan_to_num(ias, nan=np.inf)) & rth,
                            -1, 0))
    qty = np.where(mag10 >= 8, 3, np.where(mag10 >= 5, 2, 1)).astype(int)
    for hold in (15, 30, 60):
        add(f"D_DIVSZ_t{hold}", run(sig, qty, hold))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. PYRAMID flow ----------------------------------------------------
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    mag = np.abs(np.nan_to_num(ima)) / np.where(np.nan_to_num(ias) > 0, ias, np.inf)
    sig = np.where((ima > 3 * np.nan_to_num(ias, nan=np.inf)) & rth, 1,
                   np.where((ima < -3 * np.nan_to_num(ias, nan=np.inf)) & rth, -1, 0))
    qty = np.where(mag >= 8, 3, np.where(mag >= 5, 2, 1)).astype(int)
    for cap in (2, 3):
        for hold in (15, 30):
            add(f"E_PYR_cap{cap}_t{hold}", run_pyr(sig, qty, hold, cap))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round28_highfreq.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "mar_usd_wk", "mar_worst", "mar_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (blind + since-Mar shown):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0) & ~out.over_cap]
    hf = ok[ok.bl_tr_wk >= 100]
    print(f"\nboth-positive: {len(ok)} | of those >=100 tr/wk: {len(hf)}")
    print(hf.sort_values("mar_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()

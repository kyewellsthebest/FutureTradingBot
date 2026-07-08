"""Round 30: BREAKTHROUGH hunt. Flat 1 MNQ, 100-500 tr/wk target,
recent-window protocol, tick-walked fills, $1.50/RT.
  A. P-FLOW: passive pullback entry INTO the flow burst (rest 2-4 pts
     behind, ride the burst 30m) — PFADE's execution alpha on momentum
  B. REQUOTE: PFADE with one re-quote 1pt deeper if missed (fill rate up)
  C. CLIMAX: 3-bar range+flow acceleration exhaustion -> fade the climax
  D. SPEED-FADE: fade only FAST impulses (>=70% of the move in last 3 min)
  E. WAVE2: second push to new extreme on weaker flow (divergence) -> fade
  F. NEWSFADE: spike reversion in the 14:30/16:00 UTC news windows
  G. TRENDPULL: 10m counter-move against 60m trend -> join trend (and anti)
  H. SWEEP: local 45m swing point taken by >=2pt then rejected -> fade
  I. STRUCT-X: PFADE with structural exit limit at the impulse origin
  J. IBS30: close at extreme of 30m window + tick reversal -> fade
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
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    mom10 = c - np.roll(c, 10); mom10[:10] = 0
    mom3 = c - np.roll(c, 3); mom3[:3] = 0
    mom60 = c - np.roll(c, 60); mom60[:60] = 0
    thr12 = 1.2 * np.nan_to_num(atr, nan=np.inf)
    HN = lambda mins: int(mins * 60_000_000_000)

    def run_mkt(sig, hold):
        out = []
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0:
                i += 1; continue
            ei = np.searchsorted(ts, bts[i] + LAT_NS, side="left")
            if ei >= n:
                break
            e = px[ei] + TICK * s
            j = min(i + hold, nb - 1)
            xi = np.searchsorted(ts, bts[j] + LAT_NS, side="left")
            if xi >= n:
                break
            out.append((ts[xi], (px[xi] - TICK * s - e) * s * PT - FEES))
            i = j + 1
        return out

    def run_limit(sig, off, cxl, hold, requote=0.0, struct_tgt=None,
                  tgt_hold=None):
        out = []
        busy = 0
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, side="left")
            a1 = np.searchsorted(ts, bts[i] + HN(cxl), side="left")
            if a0 >= n:
                break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            fi = None
            if len(th):
                fi = a0 + th[0]
            elif requote > 0:
                L = L - requote * s
                a2 = np.searchsorted(ts, ts[min(a1, n - 1)] + HN(cxl), side="left")
                seg2 = px[a1:a2]
                th2 = np.flatnonzero(seg2 * s < (L - TICK * s) * s + 1e-9)
                if len(th2):
                    fi = a1 + th2[0]
            if fi is None:
                i += 1; continue
            hold_eff = hold if tgt_hold is None else tgt_hold
            t_exit = ts[fi] + HN(hold_eff)
            xe = np.searchsorted(ts, t_exit + LAT_NS, side="left")
            if xe >= n:
                break
            fill_exit = None
            if struct_tgt is not None:
                T = struct_tgt[i]
                if (T - L) * s > 0.5:      # target must be beyond entry
                    seg3 = px[fi + 1:xe]
                    th3 = np.flatnonzero(seg3 * s > (T + TICK * s) * s - 1e-9)
                    if len(th3):
                        fill_exit = T
                        xe = fi + 1 + th3[0]
            if fill_exit is None:
                fill_exit = px[xe] - TICK * s
            out.append((ts[xe], (fill_exit - L) * s * PT - FEES))
            busy = ts[xe]
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
                     "bl_worst": bl["worst"], "mar_usd_wk": mr["usd_wk"],
                     "mar_worst": mr["worst"], "mar_pos": mr["pos"]})

    # ---- A. P-FLOW passive pullback into the burst -------------------------
    burst = np.where((ima > 3 * np.nan_to_num(ias, nan=np.inf)) & rth, 1,
                     np.where((ima < -3 * np.nan_to_num(ias, nan=np.inf)) & rth,
                              -1, 0))
    for off in (2.0, 4.0):
        for hold in (15, 30):
            add(f"A_PFLOW_off{off}_t{hold}",
                run_limit(-(-burst), off, 5, hold))   # rest off pts BELOW for longs
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. REQUOTE PFADE ---------------------------------------------------
    sigf = np.where((mom10 < -thr12) & skip30, 1,
                    np.where((mom10 > thr12) & skip30, -1, 0))
    add("B_REQUOTE_1+1_t15", run_limit(sigf, 1.0, 3, 15, requote=1.0))
    add("B_REQUOTE_2+2_t15", run_limit(sigf, 2.0, 3, 15, requote=2.0))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. CLIMAX exhaustion ----------------------------------------------
    racc = (tr > np.roll(tr, 1)) & (np.roll(tr, 1) > np.roll(tr, 2))
    iacc = (np.abs(iv) > np.abs(np.roll(iv, 1))) & \
           (np.abs(np.roll(iv, 1)) > np.abs(np.roll(iv, 2)))
    bigf = tr > 2 * np.nan_to_num(atr, nan=np.inf)
    sg = np.where(racc & iacc & bigf & (r1 < 0) & rth, 1,
                  np.where(racc & iacc & bigf & (r1 > 0) & rth, -1, 0))
    for hold in (10, 15, 30):
        add(f"C_CLIMAX_t{hold}", run_mkt(sg, hold))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. SPEED-FADE ------------------------------------------------------
    fast = np.abs(mom3) > 0.7 * np.abs(mom10)
    sg = np.where((mom10 < -thr12) & fast & skip30, 1,
                  np.where((mom10 > thr12) & fast & skip30, -1, 0))
    for hold in (15, 30):
        add(f"D_SPEED_t{hold}", run_mkt(sg, hold))
    slow = ~fast
    sg = np.where((mom10 < -thr12) & slow & skip30, 1,
                  np.where((mom10 > thr12) & slow & skip30, -1, 0))
    add("D_SLOW_t15", run_mkt(sg, 15))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. WAVE2 divergence fade ------------------------------------------
    lo30 = pd.Series(l).rolling(30).min().shift(3).to_numpy()
    hi30 = pd.Series(h).rolling(30).max().shift(3).to_numpy()
    weak = np.abs(np.nan_to_num(ima)) < np.nan_to_num(ias)
    sg = np.where((l < lo30) & weak & (mom10 < 0) & skip30, 1,
                  np.where((h > hi30) & weak & (mom10 > 0) & skip30, -1, 0))
    for hold in (15, 30):
        add(f"E_WAVE2_t{hold}", run_mkt(sg, hold))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- F. NEWSFADE --------------------------------------------------------
    news = ((hrs >= 14.42) & (hrs < 14.92)) | ((hrs >= 15.92) & (hrs < 16.42))
    for a_ in (1.0, 1.5):
        thr = a_ * np.nan_to_num(atr, nan=np.inf)
        sg = np.where((mom10 < -thr) & news, 1,
                      np.where((mom10 > thr) & news, -1, 0))
        for hold in (15, 30):
            add(f"F_NEWS_a{a_}_t{hold}", run_mkt(sg, hold))
    print(f"[F] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- G. TRENDPULL -------------------------------------------------------
    trend_up = mom60 > 2 * np.nan_to_num(atr, nan=np.inf)
    trend_dn = mom60 < -2 * np.nan_to_num(atr, nan=np.inf)
    pull = np.abs(mom10) > 0.8 * np.nan_to_num(atr, nan=np.inf)
    sg = np.where(trend_up & (mom10 < 0) & pull & skip30, 1,
                  np.where(trend_dn & (mom10 > 0) & pull & skip30, -1, 0))
    for hold in (15, 30, 60):
        add(f"G_TRENDPULL_t{hold}", run_mkt(sg, hold))
    sg2 = np.where(trend_up & (mom10 > thr12) & skip30, -1,
                   np.where(trend_dn & (mom10 < -thr12) & skip30, 1, 0))
    add("G_ANTITREND_t15", run_mkt(sg2, 15))
    print(f"[G] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- H. SWEEP of local swing --------------------------------------------
    lo45 = pd.Series(l).rolling(45).min().shift(2).to_numpy()
    hi45 = pd.Series(h).rolling(45).max().shift(2).to_numpy()
    sg = np.where((l < lo45 - 2) & (c > lo45) & skip30, 1,
                  np.where((h > hi45 + 2) & (c < hi45) & skip30, -1, 0))
    for hold in (15, 30, 60):
        add(f"H_SWEEP_t{hold}", run_mkt(sg, hold))
    print(f"[H] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- I. STRUCT-X: PFADE + structural target -----------------------------
    origin = np.roll(c, 10)
    add("I_STRUCTX_t15", run_limit(sigf, 1.0, 3, 15, struct_tgt=origin))
    add("I_STRUCTX_t30", run_limit(sigf, 1.0, 3, 30, struct_tgt=origin,
                                   tgt_hold=30))
    print(f"[I] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- J. IBS30 -----------------------------------------------------------
    lo30w = pd.Series(l).rolling(30).min().to_numpy()
    hi30w = pd.Series(h).rolling(30).max().to_numpy()
    rngw = hi30w - lo30w
    ibs = np.where(rngw > 0, (c - lo30w) / np.where(rngw > 0, rngw, 1), 0.5)
    tickup = r1 > 0; tickdn = r1 < 0
    sg = np.where((ibs < 0.05) & tickup & skip30 & (rngw > 15), 1,
                  np.where((ibs > 0.95) & tickdn & skip30 & (rngw > 15), -1, 0))
    for hold in (15, 30):
        add(f"J_IBS30_t{hold}", run_mkt(sg, hold))
    print(f"[J] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round30_breakthrough.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "mar_usd_wk", "mar_worst", "mar_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (benchmark: PFADE $727/wk since Mar @107tr):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("mar_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()

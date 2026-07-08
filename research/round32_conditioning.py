"""Round 32: conditioning + horizon avenues (flat 1 MNQ, recent-window
protocol, tick-walked fills, $1.50/RT).
  A. Multi-horizon passive fade: k10 OR k20 OR k30 overextension as one
     family signal (fires on any horizon) — frequency toward 150-200
  B. Larger-horizon passive fades alone (k20/k30, t30/t60)
  C. Flow persistence: N consecutive same-sign flow minutes -> follow
     while it persists / fade the break
  D. Quiet-burst: flow burst that erupts from a sub-median-volume 30m
     stretch (signal-from-silence filter on flat flow-follow)
  E. Big-print participation: flow burst carried by >=20-lot prints vs
     retail-sized prints (institutional filter, flat flow-follow)
  F. Session-boundary flow: Europe close (15:30-16:30 UTC) and US equity
     close (19:30-20:00 UTC) flow -> drift trades
  G. Day-state conditioning: PFADE only on days whose first two RTH hours
     were choppy vs trendy (state fitted on select window)
  H. PFADE hour map: which RTH hours carry the fade edge (fit select,
     verdict blind, trade only paying hours)
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
    big = np.where(sz >= 20, d * sz, 0.0)
    g = pd.DataFrame({"m": m, "px": px, "sz": sz, "iv": d * sz, "bg": big})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), iv=("iv", "sum"), bg=("bg", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    o = b["open"].to_numpy(); h = b["high"].to_numpy()
    l = b["low"].to_numpy(); c = b["close"].to_numpy()
    vol = b["vol"].to_numpy(); iv = b["iv"].to_numpy(); bg = b["bg"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000; nb = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize(); days = dk.asi8
    rth = (hrs >= 13.5) & (hrs < 20.9)
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    vma = pd.Series(vol).rolling(30).mean().to_numpy()
    HN = lambda mins: int(mins * 60_000_000_000)
    moms = {}
    for k in (10, 20, 30):
        mk = c - np.roll(c, k); mk[:k] = 0
        moms[k] = mk
    thr12 = 1.2 * np.nan_to_num(atr, nan=np.inf)

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

    def run_pfade_sig(sig, off, hold):
        out = []
        busy = 0
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, side="left")
            a1 = np.searchsorted(ts, bts[i] + HN(3), side="left")
            if a0 >= n:
                break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th):
                i += 1; continue
            fi = a0 + th[0]
            xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, side="left")
            if xe >= n:
                break
            out.append((ts[xe], (px[xe] - TICK * s - L) * s * PT - FEES))
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

    # ---- A. multi-horizon union fade ---------------------------------------
    def fade_sig(k, a_):
        thr = a_ * np.nan_to_num(atr, nan=np.inf) * np.sqrt(k / 10.0)
        return np.where((moms[k] < -thr) & skip30, 1,
                        np.where((moms[k] > thr) & skip30, -1, 0))
    s10, s20, s30 = fade_sig(10, 1.2), fade_sig(20, 1.2), fade_sig(30, 1.2)
    union = np.where(s10 != 0, s10, np.where(s20 != 0, s20, s30))
    for hold in (15, 20):
        add(f"A_UNION_k102030_t{hold}", run_pfade_sig(union, 1.0, hold))
    union2 = np.where(s10 != 0, s10, s20)
    add("A_UNION_k1020_t15", run_pfade_sig(union2, 1.0, 15))
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. larger-horizon passive fades -----------------------------------
    for k in (20, 30):
        sg = fade_sig(k, 1.2)
        for hold in (30, 60):
            add(f"B_PFADE_k{k}_t{hold}", run_pfade_sig(sg, 1.0, hold))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. flow persistence -----------------------------------------------
    sgn = np.sign(np.nan_to_num(iv))
    streak = np.zeros(nb)
    for i in range(1, nb):
        streak[i] = streak[i - 1] + 1 if sgn[i] == sgn[i - 1] and sgn[i] != 0 else 1
    for N in (5, 8):
        pers = (streak == N) & rth
        sg = np.where(pers & (sgn > 0), 1, np.where(pers & (sgn < 0), -1, 0))
        for hold in (15, 30):
            add(f"C_PERSF_N{N}_t{hold}", run_mkt(sg, hold))
        brk = (np.roll(streak, 1) >= N) & (sgn != np.roll(sgn, 1)) & rth
        sg = np.where(brk & (sgn > 0), 1, np.where(brk & (sgn < 0), -1, 0))
        add(f"C_PERSBRK_N{N}_t15", run_mkt(sg, 15))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. quiet-burst flow-follow ----------------------------------------
    quiet30 = pd.Series(vol).rolling(30).mean().shift(1).to_numpy() < \
        0.7 * np.nan_to_num(vma, nan=np.inf)
    burst = np.where((ima > 3 * np.nan_to_num(ias, nan=np.inf)) & rth, 1,
                     np.where((ima < -3 * np.nan_to_num(ias, nan=np.inf)) & rth,
                              -1, 0))
    sg = np.where(quiet30, burst, 0)
    for hold in (15, 30, 60):
        add(f"D_QUIETB_t{hold}", run_mkt(sg, hold))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. big-print participation ----------------------------------------
    bga = pd.Series(bg).rolling(10).sum().to_numpy()
    inst = np.abs(np.nan_to_num(bga)) > 0.4 * np.abs(np.nan_to_num(ima))
    sg = np.where(inst, burst, 0)
    for hold in (15, 30):
        add(f"E_INSTB_t{hold}", run_mkt(sg, hold))
    sg = np.where(~inst, burst, 0)
    add("E_RETAILB_t30", run_mkt(sg, 30))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- F. session-boundary flow ------------------------------------------
    ima5 = pd.Series(iv).rolling(5).sum().to_numpy()
    for wlo, whi, tag in ((15.5, 16.5, "EUCLOSE"), ((19.5), 20.0, "USCLOSE")):
        wmask = (hrs >= wlo) & (hrs < whi)
        thrF = 2 * np.nan_to_num(ias, nan=np.inf)
        sg = np.where(wmask & (ima5 > thrF), 1,
                      np.where(wmask & (ima5 < -thrF), -1, 0))
        for hold in (30, 60):
            add(f"F_{tag}_t{hold}", run_mkt(sg, hold))
    print(f"[F] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- G. day-state conditioned PFADE ------------------------------------
    two_h = (hrs >= 13.5) & (hrs < 15.5)
    dft = pd.DataFrame({"d": dk, "r": np.where(two_h, r1, np.nan),
                        "c": np.where(two_h, c, np.nan)})
    net = dft.groupby("d")["c"].transform("last") - \
        dft.groupby("d")["c"].transform("first")
    path = dft.groupby("d")["r"].transform(lambda x: np.nansum(np.abs(x)))
    eff = np.abs(net.to_numpy()) / np.where(path.to_numpy() > 0,
                                            path.to_numpy(), np.inf)
    after = hrs >= 15.5
    sgf = np.where((moms[10] < -thr12) & after & skip30, 1,
                   np.where((moms[10] > thr12) & after & skip30, -1, 0))
    choppy = eff < 0.15
    trendy = eff > 0.3
    add("G_CHOPPYDAY_t15", run_pfade_sig(np.where(choppy, sgf, 0), 1.0, 15))
    add("G_TRENDYDAY_t15", run_pfade_sig(np.where(trendy, sgf, 0), 1.0, 15))
    print(f"[G] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- H. PFADE hour map --------------------------------------------------
    sig_full = np.where((moms[10] < -thr12) & skip30, 1,
                        np.where((moms[10] > thr12) & skip30, -1, 0))
    out_sel = run_pfade_sig(np.where(np.asarray(idx < SPLIT) &
                                     np.asarray(idx >= SEL_LO), sig_full, 0),
                            1.0, 15)
    es = pd.Series([p for _, p in out_sel],
                   index=pd.to_datetime([t for t, _ in out_sel], utc=True))
    hour_pnl = es.groupby(es.index.hour).sum()
    good_hours = hour_pnl[hour_pnl > 0].index.to_numpy()
    print(f"  select hour P&L: {hour_pnl.round(0).to_dict()}", flush=True)
    hh = np.asarray(idx.hour)
    sg = np.where(np.isin(hh, good_hours), sig_full, 0)
    add("H_HOURMAP_t15", run_pfade_sig(sg, 1.0, 15))
    print(f"[H] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round32_conditioning.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "mar_usd_wk", "mar_worst", "mar_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (incumbent PFADE $727/wk @107tr since Mar):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("mar_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()

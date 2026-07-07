"""Round 27: ten untouched avenues, recent-window protocol (sel Apr-May,
blind Jun 1 - Jul 6), tick-walked fills, $1.50/RT.
  A. Flow acceleration + flow/price divergence
  B. Flow-at-extremes: burst while at fresh day high/low vs mid-range
  C. Liquidity vacuum: big move on thin tape
  D. Tick-run patterns (raw tape): N consecutive same-direction ticks
  E. Inter-tick price jumps (>= 1pt single print gaps)
  F. Hours-long compression breakout
  G. Cross-scale momentum alignment (5m+15m+60m)
  H. Opening auction (first 5m of RTH) day-bias trades
  I. Overnight-inventory-conditioned opening drive
  J. Killzone concentration of the plain 3x flow signal (windows fitted
     on select only)
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


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    print(f"ticks: {n:,}", flush=True)
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px, "sz": sz, "iv": d * sz})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), iv=("iv", "sum"), nt=("px", "size"))
    b.index = pd.to_datetime(b.index, utc=True)
    o = b["open"].to_numpy(); h = b["high"].to_numpy()
    l = b["low"].to_numpy(); c = b["close"].to_numpy()
    vol = b["vol"].to_numpy(); iv = b["iv"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize(); nb = len(c)
    rth = (hrs >= 13.5) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    vma = pd.Series(vol).rolling(30).mean().to_numpy()
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()

    def exec_times(times, sides, hold_min, qty=None):
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for i_, (t, s) in enumerate(zip(times, sides)):
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, side="left")
            if ei >= n:
                break
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + hn + LAT_NS, side="left")
            if xj >= n:
                break
            q = 1 if qty is None else qty[i_]
            out.append((ts[xj], ((px[xj] - TICK * s - e) * s * PT - FEES) * q))
            busy = ts[xj]
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
        rows.append({"name": name, "sel_usd_wk": a["usd_wk"],
                     "sel_tr_wk": a["tr_wk"], "bl_usd_wk": bl["usd_wk"],
                     "bl_tr_wk": bl["tr_wk"], "bl_per": bl["per"],
                     "bl_worst": bl["worst"], "bl_pos": bl["pos"]})

    def add_bar(name, sig, hold, qty=None):
        live = np.flatnonzero(sig != 0)
        q = None if qty is None else qty[live]
        add(name, exec_times(bts[live], sig[live], hold, qty=q))

    # ---- A. flow acceleration & divergence --------------------------------
    ima5 = pd.Series(iv).rolling(5).sum().to_numpy()
    accel = ima5 - (np.roll(ima, 5) / 2)
    thrA = 3 * np.nan_to_num(ias, nan=np.inf)
    sg = np.where((accel > thrA) & rth, 1, np.where((accel < -thrA) & rth, -1, 0))
    for hold in (15, 30):
        add_bar(f"A_ACCEL_t{hold}", sg, hold)
    mom15 = c - np.roll(c, 15); mom15[:15] = 0
    flat = np.abs(mom15) < 0.5 * np.nan_to_num(atr, nan=np.inf)
    sg = np.where(flat & (ima > thrA) & rth, 1,
                  np.where(flat & (ima < -thrA) & rth, -1, 0))
    for hold in (15, 30, 60):
        add_bar(f"A_DIVERGE_t{hold}", sg, hold)
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. flow at extremes vs mid ---------------------------------------
    dhi = pd.Series(h, index=idx).groupby(dk).cummax().to_numpy()
    dlo = pd.Series(l, index=idx).groupby(dk).cummin().to_numpy()
    at_hi = c >= dhi - 2; at_lo = c <= dlo + 2
    burst_l = (ima > thrA) & rth; burst_s = (ima < -thrA) & rth
    sg = np.where(burst_l & at_hi, 1, np.where(burst_s & at_lo, -1, 0))
    for hold in (15, 30, 60):
        add_bar(f"B_FLOWEXT_t{hold}", sg, hold)
    mid = ~at_hi & ~at_lo
    sg = np.where(burst_l & mid, 1, np.where(burst_s & mid, -1, 0))
    for hold in (15, 30):
        add_bar(f"B_FLOWMID_t{hold}", sg, hold)
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. liquidity vacuum ----------------------------------------------
    bigmove = np.abs(r1) > 1.5 * np.nan_to_num(atr, nan=np.inf)
    thin = vol < 0.5 * np.nan_to_num(vma, nan=0)
    up1 = r1 > 0
    sgF = np.where(bigmove & thin & up1 & rth, 1,
                   np.where(bigmove & thin & ~up1 & rth, -1, 0))
    for hold in (5, 15, 30):
        add_bar(f"C_VACF_t{hold}", sgF, hold)
    for hold in (15, 30):
        add_bar(f"C_VACR_t{hold}", -sgF, hold)
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. tick runs (raw tape) ------------------------------------------
    nz = d != 0
    chg = np.flatnonzero(np.diff(np.where(nz, d, 0)) != 0) + 1
    last = np.zeros(n, dtype=np.int64)
    last[chg] = chg
    last = np.maximum.accumulate(last)
    runlen = np.arange(n) - last + 1
    hrs_t = ((ts // 3_600_000_000_000) % 24).astype(int)
    rth_t = (hrs_t >= 14) & (hrs_t < 21)
    for R in (15, 25, 40):
        fire = (runlen == R) & nz & rth_t
        times = ts[fire]; sides = d[fire].astype(int)
        for hold in (2, 5, 15):
            add(f"D_RUNF_R{R}_t{hold}", exec_times(times, sides, hold))
        for hold in (5, 15):
            add(f"D_RUNR_R{R}_t{hold}", exec_times(times, -sides, hold))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. inter-tick price jumps ----------------------------------------
    dpx = np.diff(px, prepend=px[0])
    for J in (1.0, 2.0):
        fire = (np.abs(dpx) >= J) & rth_t
        times = ts[fire]; sides = np.sign(dpx[fire]).astype(int)
        for hold in (2, 5, 15):
            add(f"E_JUMPF_j{J}_t{hold}", exec_times(times, sides, hold))
        for hold in (5, 15):
            add(f"E_JUMPR_j{J}_t{hold}", exec_times(times, -sides, hold))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- F. hours-long compression breakout -------------------------------
    for CW in (120, 240):
        rhi = pd.Series(h).rolling(CW).max().shift(1).to_numpy()
        rlo = pd.Series(l).rolling(CW).min().shift(1).to_numpy()
        width = rhi - rlo
        wmed = pd.Series(width).rolling(1000).median().to_numpy()
        tight = width < 0.6 * np.nan_to_num(wmed, nan=np.inf)
        sg = np.where(tight & (c > rhi) & rth, 1,
                      np.where(tight & (c < rlo) & rth, -1, 0))
        for hold in (30, 60, 120):
            add_bar(f"F_COMPBO_w{CW}_t{hold}", sg, hold)
    print(f"[F] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- G. cross-scale alignment -----------------------------------------
    m5 = c - np.roll(c, 5); m5[:5] = 0
    m15v = c - np.roll(c, 15); m15v[:15] = 0
    m60 = c - np.roll(c, 60); m60[:60] = 0
    alignL = (m5 > 0) & (m15v > 0.75 * np.nan_to_num(atr)) & (m60 > 2 * np.nan_to_num(atr))
    alignS = (m5 < 0) & (m15v < -0.75 * np.nan_to_num(atr)) & (m60 < -2 * np.nan_to_num(atr))
    sg = np.where(alignL & rth, 1, np.where(alignS & rth, -1, 0))
    for hold in (15, 30, 60):
        add_bar(f"G_ALIGNF_t{hold}", sg, hold)
    for hold in (15, 30):
        add_bar(f"G_ALIGNR_t{hold}", -sg, hold)
    print(f"[G] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- H. opening auction day bias --------------------------------------
    open5 = (hrs >= 13.5) & (hrs < 13.583)
    df5 = pd.DataFrame({"d": dk, "iv": np.where(open5, iv, 0),
                        "r": np.where(open5, r1, 0)})
    oiv = df5.groupby("d")["iv"].transform("sum").to_numpy()
    orr = df5.groupby("d")["r"].transform("sum").to_numpy()
    fire_t = (hrs >= 13.583) & (hrs < 13.6)
    ivs = pd.Series(np.abs(iv)).rolling(300).mean().to_numpy() * 5
    sg = np.where(fire_t & (oiv > np.nan_to_num(ivs, nan=np.inf)), 1,
                  np.where(fire_t & (oiv < -np.nan_to_num(ivs, nan=np.inf)), -1, 0))
    for hold in (60, 120, 240):
        add_bar(f"H_AUCTF_t{hold}", sg, hold)
    sg2 = np.where(fire_t & (orr > 5), 1, np.where(fire_t & (orr < -5), -1, 0))
    for hold in (60, 240):
        add_bar(f"H_DRIVEF_t{hold}", sg2, hold)
    print(f"[H] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- I. overnight inventory + opening drive ---------------------------
    on_mask = (hrs >= 22.0) | (hrs < 13.5)
    dfo = pd.DataFrame({"d": dk, "hi": np.where(on_mask, h, np.nan),
                        "lo": np.where(on_mask, l, np.nan)})
    onhi = dfo.groupby("d")["hi"].transform("max").to_numpy()
    onlo = dfo.groupby("d")["lo"].transform("min").to_numpy()
    pos_in = np.where(onhi > onlo, (c - onlo) / (onhi - onlo), 0.5)
    sg = np.where(fire_t & (pos_in > 1.0), 1,
                  np.where(fire_t & (pos_in < 0.0), -1, 0))   # opened beyond ON range
    for hold in (60, 120, 240):
        add_bar(f"I_ONBREAK_t{hold}", sg, hold)
    print(f"[I] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- J. killzones for plain 3x flow (fitted on select) ----------------
    base = np.where((ima > thrA) & rth, 1, np.where((ima < -thrA) & rth, -1, 0))
    selb = np.asarray(idx < SPLIT) & np.asarray(idx >= SEL_LO)
    halfhr = (np.asarray(idx.hour) * 2 + (np.asarray(idx.minute) >= 30)).astype(int)
    perf = {}
    live = np.flatnonzero((base != 0) & selb)
    outs = exec_times(bts[live], base[live], 30)
    ent = pd.to_datetime([t for t, _ in outs], utc=True)
    slot = (pd.Series(ent).dt.hour * 2 +
            (pd.Series(ent).dt.minute >= 30)).to_numpy()
    pnl = np.array([p for _, p in outs])
    for s_ in np.unique(slot):
        perf[s_] = pnl[slot == s_].sum()
    good = sorted(perf, key=lambda k: -perf[k])[:6]
    sg = np.where(np.isin(halfhr, good), base, 0)
    for hold in (30, 45):
        add_bar(f"J_KILLZ6_t{hold}", sg, hold)
    print(f"[J] done; good slots {sorted(good)} ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round27_avenues.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "bl_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nTOP 30 by SELECT (blind = verdict):")
    print(out[cols].head(30).to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(20).to_string(index=False))


if __name__ == "__main__":
    main()

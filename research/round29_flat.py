"""Round 29: FLAT 1-MNQ hunt. No sizing allowed — per-trade edge must come
from execution and signal quality. Recent-window protocol, tick fills.
  A. PASSIVE-ENTRY fade: rest a limit 1-4 pts beyond the signal, filled
     only on trade-through (first passive execution test of the program)
  B. Passive entry + passive target exit (limit out at +4/+8, timer fallback)
  C. Flow-confirmed fade: only fade when tick flow has already flipped
     against the move (quality filter at lower threshold for frequency)
  D. Echo fade: persistent second push (overextension still extended
     5 min later) -> fade the exhaustion
  E. Wick-rejection fade: big bar that closes deep against its own move
  F. Adaptive per-hour threshold (75th pct of |mom10| fitted on select)
All flat 1 contract, $1.50/RT. Benchmarks: flat FADE $610/wk,
flat IMBF ~$650/wk since Mar.
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
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    mom10 = c - np.roll(c, 10); mom10[:10] = 0

    HOLD_NS = lambda mins: int(mins * 60_000_000_000)

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

    def run_limit(sig, off_pts, cancel_min, hold_min, tgt_pts=0.0):
        """Rest limit at close -/+ off. Fill on trade-through (a tick strictly
        beyond the limit). Exit: passive target (trade-through) if tgt>0,
        else/fallback market at hold after fill."""
        out = []
        placed = attempts = 0
        busy = 0
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            attempts += 1
            L = c[i] - off_pts * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, side="left")
            a1 = np.searchsorted(ts, bts[i] + HOLD_NS(cancel_min), side="left")
            if a0 >= n:
                break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th):
                i += 1; continue          # never filled; next signal
            placed += 1
            fi = a0 + th[0]
            fill_entry = L
            t_fill = ts[fi]
            t_exit = t_fill + HOLD_NS(hold_min)
            x_end = np.searchsorted(ts, t_exit + LAT_NS, side="left")
            if x_end >= n:
                break
            fill_exit = None
            if tgt_pts > 0:
                T = fill_entry + tgt_pts * s
                seg2 = px[fi + 1:x_end]
                th2 = np.flatnonzero(seg2 * s > (T + TICK * s) * s - 1e-9)
                if len(th2):
                    fill_exit = T
                    x_end = fi + 1 + th2[0]
            if fill_exit is None:
                fill_exit = px[x_end] - TICK * s
            out.append((ts[x_end], (fill_exit - fill_entry) * s * PT - FEES))
            busy = ts[x_end]
            i += 1
        return out, (placed / max(attempts, 1))

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

    def add(name, out, fillrate=None):
        a = st(out, SEL_LO, SPLIT); bl = st(out, SPLIT, END)
        mr = st(out, MAR, END)
        rows.append({"name": name, "sel_usd_wk": a["usd_wk"],
                     "sel_tr_wk": a["tr_wk"], "bl_usd_wk": bl["usd_wk"],
                     "bl_tr_wk": bl["tr_wk"], "bl_per": bl["per"],
                     "bl_worst": bl["worst"],
                     "mar_usd_wk": mr["usd_wk"], "mar_worst": mr["worst"],
                     "mar_pos": mr["pos"],
                     "fill%": round(fillrate * 100) if fillrate is not None else ""})

    thr12 = 1.2 * np.nan_to_num(atr, nan=np.inf)
    sigf = np.where((mom10 < -thr12) & skip30, 1,
                    np.where((mom10 > thr12) & skip30, -1, 0))

    # ---- A. passive-entry fade ---------------------------------------------
    for off in (1.0, 2.0, 4.0):
        for cxl in (3, 5):
            out, fr = run_limit(sigf, off, cxl, 15)
            add(f"A_PFADE_off{off}_cxl{cxl}_t15", out, fr)
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. passive entry + passive target ---------------------------------
    for off in (1.0, 2.0):
        for tgt in (4.0, 8.0):
            out, fr = run_limit(sigf, off, 5, 15, tgt_pts=tgt)
            add(f"B_PFADETX_off{off}_tgt{tgt}", out, fr)
            out, fr = run_limit(sigf, off, 5, 30, tgt_pts=tgt)
            add(f"B_PFADETX_off{off}_tgt{tgt}_t30", out, fr)
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. flow-confirmed fade --------------------------------------------
    for a_ in (1.0, 1.2):
        thr = a_ * np.nan_to_num(atr, nan=np.inf)
        conf_l = (mom10 < -thr) & (np.nan_to_num(ima) > 0)     # price down, flow up
        conf_s = (mom10 > thr) & (np.nan_to_num(ima) < 0)
        sg = np.where(conf_l & skip30, 1, np.where(conf_s & skip30, -1, 0))
        for hold in (15, 30):
            add(f"C_CONF_a{a_}_t{hold}", run_mkt(sg, hold))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. echo fade -------------------------------------------------------
    mom_prev = np.roll(mom10, 5)
    echo_l = (mom10 < -thr12) & (mom_prev < -thr12)
    echo_s = (mom10 > thr12) & (mom_prev > thr12)
    sg = np.where(echo_l & skip30, 1, np.where(echo_s & skip30, -1, 0))
    for hold in (15, 30):
        add(f"D_ECHO_t{hold}", run_mkt(sg, hold))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. wick-rejection fade --------------------------------------------
    rng = h - l
    bigbar = rng > 1.5 * np.nan_to_num(atr, nan=np.inf)
    posin = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1), 0.5)
    rej_l = bigbar & (r1 < 0) & (posin > 0.6)     # down bar closing high
    rej_s = bigbar & (r1 > 0) & (posin < 0.4)
    sg = np.where(rej_l & skip30, 1, np.where(rej_s & skip30, -1, 0))
    for hold in (5, 15, 30):
        add(f"E_WICK_t{hold}", run_mkt(sg, hold))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- F. adaptive per-hour threshold ------------------------------------
    selb = np.asarray(idx < SPLIT) & np.asarray(idx >= SEL_LO)
    hh = np.asarray(idx.hour)
    q75 = {}
    for hour in range(24):
        v = np.abs(mom10[selb & (hh == hour) & skip30])
        q75[hour] = np.percentile(v, 90) if len(v) > 200 else np.inf
    thr_h = np.array([q75.get(x, np.inf) for x in hh])
    sg = np.where((mom10 < -thr_h) & skip30, 1,
                  np.where((mom10 > thr_h) & skip30, -1, 0))
    for hold in (15, 30):
        add(f"F_ADAPT90_t{hold}", run_mkt(sg, hold))
    print(f"[F] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round29_flat.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "mar_usd_wk", "mar_worst", "mar_pos", "fill%"]
    print(f"\n{len(out)} flat-1-MNQ configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (benchmarks: flat FADE $610/wk, flat IMBF $650/wk since Mar):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("mar_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()

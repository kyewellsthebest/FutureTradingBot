"""Round 40: BULLETPROOF hunt. New objective per user after the Jul 15
whipsaw day (-$1,388 live): FADESZ-class return at 1-3 MNQ, optimized
for WORST DAY, not average week. Five untested avenues:
  A. MOMTRAIL: momentum with tick-walked TRAILING exits + magnitude
     sizing (the anti-regime harvester; trail exits never ran in the
     tick-executor era)
  B. FLIP: stop-and-reverse — when a fade loses badly, the market just
     said 'trend day': enter WITH the move it lost to
  C. TSCALE: fade with CONTINUOUS trendiness-scaled sizing (path
     efficiency of the day so far shrinks the ladder; not a binary gate)
  D. FVOL: fade sized down when flow-volatility (news microstructure)
     is in its top decile
  E. LTHROTTLE: graduated loss-throttle — after each same-day fade loss,
     next-trade size drops one rung (resets on a win)
Metrics per config: $/wk sel+blind, worst DAY, worst week, %pos weeks.
Benchmark: FADESZ+P sinceMar $1,330/wk, worst day (sim) ~-$700, worst
week -$400. Tick-walked fills, $1.50/RT, flat ladders 1/2/3.
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
HN = lambda m: int(m * 60_000_000_000)


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px, "iv": d * sz})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           iv=("iv", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    iv = b["iv"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000; nb = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize(); days = dk.asi8
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    rth = (hrs >= 13.5) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    mom10 = c - np.roll(c, 10); mom10[:10] = 0
    thr = 1.2 * np.nan_to_num(atr, nan=np.inf)
    fmag = np.abs(mom10) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    qty_lad = np.where(fmag >= 3.0, 3, np.where(fmag >= 2.0, 2, 1)).astype(int)
    sigF = np.where((mom10 < -thr) & skip30, 1,
                    np.where((mom10 > thr) & skip30, -1, 0))
    # continuous day-trendiness: |net move today| / path length today
    df_ = pd.DataFrame({"d": dk, "r": np.abs(r1), "c": c}, index=idx)
    cum_path = df_.groupby("d")["r"].cumsum().to_numpy()
    day_open = df_.groupby("d")["c"].transform("first").to_numpy()
    eff = np.abs(c - day_open) / np.where(cum_path > 0, cum_path, np.inf)
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    fvol = pd.Series(np.abs(iv)).rolling(120).std().to_numpy()
    fvol_hi = fvol > np.nanquantile(fvol[rth], 0.9)

    def stats(out, tag):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= MAR) & (s.index < END)]
        if not len(s):
            return None
        wk = s.resample("W").sum(); wk = wk[wk != 0]
        dy = s.resample("D").sum(); dy = dy[dy != 0]
        sb = s[s.index >= SPLIT]
        return {"name": tag,
                "mar_usd_wk": round(s.sum() / max(len(wk), 1), 0),
                "bl_usd_wk": round(sb.sum() / max(len(sb.resample('W').sum()[lambda x: x != 0] if len(sb) else []), 1), 0) if len(sb) else 0,
                "worst_day": round(dy.min(), 0),
                "p5_day": round(np.percentile(dy, 5), 0),
                "worst_wk": round(wk.min(), 0),
                "pos_wk": round((wk > 0).mean() * 100),
                "tr_wk": round(len(s) / max(len(wk), 1), 1)}

    def run_pfade(sig, qty_arr, hold):
        out = []
        busy = 0
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            L = c[i] - 1.0 * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + HN(3), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                i += 1; continue
            fi = a0 + th_[0]
            xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, "left")
            if xe >= n: break
            q = qty_arr[i] if qty_arr is not None else 1
            out.append((ts[xe], ((px[xe] - TICK * s - L) * s * PT - FEES) * q))
            busy = ts[xe]
            i += 1
        return out

    rows = []

    # ---- benchmark ---------------------------------------------------------
    st = stats(run_pfade(sigF, qty_lad, 15), "BENCH_FADESZ+P")
    rows.append(st)
    print("bench:", st, f"({time.time()-t0:.0f}s)", flush=True)

    # ---- A. MOMTRAIL: momentum + tick trailing exit + sizing --------------
    mom30 = c - np.roll(c, 30); mom30[:30] = 0
    for k, karr in (("10", mom10), ("30", mom30)):
        for a_ in (1.5, 2.5):
            thrM = a_ * np.nan_to_num(atr, nan=np.inf) * (1 if k == "10" else 1.8)
            sigM = np.where((karr > thrM) & rth, 1,
                            np.where((karr < -thrM) & rth, -1, 0))
            mmag = np.abs(karr) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
            qM = np.where(mmag >= 3 * a_, 3, np.where(mmag >= 2 * a_, 2, 1)).astype(int)
            for trail_pt in (8.0, 15.0):
                out = []
                busy = 0
                i = 0
                while i < nb - 2:
                    s = sigM[i]
                    if s == 0 or bts[i] < busy:
                        i += 1; continue
                    ei = np.searchsorted(ts, bts[i] + LAT_NS, "left")
                    if ei >= n: break
                    e = px[ei] + TICK * s
                    xmax = np.searchsorted(ts, bts[i] + HN(120), "left")
                    if xmax >= n: break
                    seg = px[ei:xmax]
                    if s > 0:
                        peak = np.maximum.accumulate(seg)
                        hit = np.flatnonzero(seg <= peak - trail_pt)
                    else:
                        trough = np.minimum.accumulate(seg)
                        hit = np.flatnonzero(seg >= trough + trail_pt)
                    xj = ei + (hit[0] if len(hit) else len(seg) - 1)
                    q = qM[i]
                    out.append((ts[xj], ((px[xj] - TICK * s - e) * s * PT - FEES) * q))
                    busy = ts[xj]
                    i += 1
                st = stats(out, f"A_MOMTRAIL_k{k}_a{a_}_tr{trail_pt}")
                if st: rows.append(st)
        print(f"[A k{k}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. FLIP: stop-and-reverse after a losing fade ---------------------
    for loss_pt in (6.0, 10.0):
        for fhold in (15, 30):
            out = []
            busy = 0
            i = 0
            while i < nb - 2:
                s = sigF[i]
                if s == 0 or bts[i] < busy:
                    i += 1; continue
                L = c[i] - 1.0 * s
                a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
                a1 = np.searchsorted(ts, bts[i] + HN(3), "left")
                if a0 >= n: break
                seg = px[a0:a1]
                th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
                if not len(th_):
                    i += 1; continue
                fi = a0 + th_[0]
                xe = np.searchsorted(ts, ts[fi] + HN(15) + LAT_NS, "left")
                if xe >= n: break
                q = qty_lad[i]
                pnl_pts = (px[xe] - TICK * s - L) * s
                out.append((ts[xe], (pnl_pts * PT - FEES) * q))
                busy = ts[xe]
                if pnl_pts <= -loss_pt:          # fade lost hard -> trend day info
                    s2 = -s                       # go WITH the move
                    e2 = px[xe] + TICK * s2
                    xf = np.searchsorted(ts, ts[xe] + HN(fhold) + LAT_NS, "left")
                    if xf >= n: break
                    out.append((ts[xf], ((px[xf] - TICK * s2 - e2) * s2 * PT - FEES) * q))
                    busy = ts[xf]
                i += 1
            st = stats(out, f"B_FLIP_l{loss_pt}_fh{fhold}")
            if st: rows.append(st)
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. TSCALE: continuous trendiness-scaled fade ladder ---------------
    for lo, hi in ((0.10, 0.30), (0.15, 0.40)):
        scale = np.clip((hi - eff) / (hi - lo), 0.0, 1.0)   # 1 in chop, 0 in trend
        qts = np.maximum(0, np.round(qty_lad * scale)).astype(int)
        sigC = np.where(qts > 0, sigF, 0)
        st = stats(run_pfade(sigC, qts, 15), f"C_TSCALE_{lo}-{hi}")
        if st: rows.append(st)
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. FVOL: shrink ladder when flow-vol is top-decile ----------------
    qfv = np.where(fvol_hi, 1, qty_lad).astype(int)
    st = stats(run_pfade(sigF, qfv, 15), "D_FVOL_cap1_top10")
    if st: rows.append(st)
    qfv0 = np.where(fvol_hi, 0, qty_lad).astype(int)
    st = stats(run_pfade(np.where(qfv0 > 0, sigF, 0), qfv0, 15), "D_FVOL_skip_top10")
    if st: rows.append(st)
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. LTHROTTLE: graduated same-day loss throttle --------------------
    for step in (1, 2):
        out = []
        busy = 0
        i = 0
        cur_day = -1
        throttle = 0
        while i < nb - 2:
            s = sigF[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            if days[i] != cur_day:
                cur_day = days[i]; throttle = 0
            q = max(1, qty_lad[i] - throttle)
            L = c[i] - 1.0 * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + HN(3), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                i += 1; continue
            fi = a0 + th_[0]
            xe = np.searchsorted(ts, ts[fi] + HN(15) + LAT_NS, "left")
            if xe >= n: break
            pnl = ((px[xe] - TICK * s - L) * s * PT - FEES) * q
            out.append((ts[xe], pnl))
            busy = ts[xe]
            throttle = min(2, throttle + step) if pnl < 0 else 0
            i += 1
        st = stats(out, f"E_LTHROTTLE_step{step}")
        if st: rows.append(st)
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame([r for r in rows if r])
    out.to_csv("research/round40_bulletproof.csv", index=False)
    cols = ["name", "mar_usd_wk", "worst_day", "p5_day", "worst_wk",
            "pos_wk", "tr_wk"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL (benchmark first; judge worst_day/worst_wk vs $/wk):")
    print(out[cols].to_string(index=False))


if __name__ == "__main__":
    main()

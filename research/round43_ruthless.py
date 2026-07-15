"""Round 43: RUTHLESS micro-frontier grind on the champion. Four fronts
never swept:
  B. Signal micro-grid: mom window 8-12 x threshold 1.1-1.3 x hold
     12/15/18 (the champion's k10/1.2/15 was never fine-tuned)
  A. Execution physics: cancel-window grid, offset grid, signal RE-ARM
     (retry the limit while the overextension persists — recovers the
     ~15% missed fills), PASSIVE timer exit (earn the exit spread too)
  C. Disaster guard fine grid x FVOL cap (60/70/80/100pt)
  D. Scheduled-news clock blackouts: no entries 14:00-14:10 UTC (10am ET
     data drops) and/or 17:55-18:15 UTC (2pm ET Fed slot)
Protocol: B uses SELECT Apr-May / BLIND Jun-Jul6 at flat 1 MNQ.
A/C/D run on the 1/2/3 ladder, since-Mar stats + worst day.
Tick-walked fills, $1.50/RT.
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
STOP_SLIP = 0.25
MAR = pd.Timestamp("2026-03-01", tz="UTC")
SEL_LO = pd.Timestamp("2026-04-01", tz="UTC")
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")
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
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    rth = (hrs >= 13.5) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr20 = pd.Series(tr).rolling(20).mean().to_numpy()
    fvol = pd.Series(np.abs(iv)).rolling(120).std().to_numpy()
    fvol_hi = fvol > np.nanquantile(fvol[rth], 0.9)

    def stats(out, lo, hi):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        if len(s) < 30:
            return dict(usd_wk=0, tr_wk=0, pos=0, wd=0, ww=0)
        wk = s.resample("W").sum(); wk = wk[wk != 0]
        dy = s.resample("D").sum(); dy = dy[dy != 0]
        return dict(usd_wk=round(s.sum() / max(len(wk), 1), 0),
                    tr_wk=round(len(s) / max(len(wk), 1), 1),
                    pos=round((wk > 0).mean() * 100),
                    wd=round(dy.min(), 0), ww=round(wk.min(), 0))

    def engine(k=10, a=1.2, hold=15, offset=1.0, cancel_s=180, rearm=0,
               pexit=False, disaster=None, fvol_cap=False, ladder=False,
               mask=None):
        mom = c - np.roll(c, k); mom[:k] = 0
        thr = a * np.nan_to_num(atr20, nan=np.inf)
        fmag = np.abs(mom) / np.where(np.nan_to_num(atr20) > 0, atr20, np.inf)
        qарr = None
        sig = np.where((mom < -thr) & skip30, 1,
                       np.where((mom > thr) & skip30, -1, 0))
        if mask is not None:
            sig = np.where(mask, 0, sig)
        out = []
        busy = 0
        i = 0
        tries = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; tries = 0; continue
            L = c[i] - offset * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + int(cancel_s * 1e9), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                if rearm and tries < rearm:
                    tries += 1
                i += 1
                continue
            tries = 0
            fi = a0 + th_[0]
            xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, "left")
            if xe >= n: break
            fill = None; k_exit = xe
            if disaster:
                stop_lvl = L - disaster * s
                seg2 = px[fi + 1:xe]
                if len(seg2):
                    sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
                    if len(sh):
                        k_exit = fi + 1 + int(sh[0])
                        raw = min(px[k_exit], stop_lvl) if s > 0 else max(px[k_exit], stop_lvl)
                        fill = raw - STOP_SLIP * s
            if fill is None:
                if pexit:
                    # rest a limit at last price at exit time; trade-through
                    # or market fallback 2 min later
                    Lx = px[xe]
                    x2 = np.searchsorted(ts, ts[xe] + HN(2), "left")
                    if x2 >= n: break
                    seg3 = px[xe:x2]
                    tho = np.flatnonzero(seg3 * s > (Lx + TICK * s) * s - 1e-9)
                    if len(tho):
                        fill = Lx; k_exit = xe + int(tho[0])
                    else:
                        fill = px[x2] - TICK * s; k_exit = x2
                else:
                    fill = px[xe] - TICK * s
                    k_exit = xe
            if ladder:
                q = 3 if fmag[i] >= 3.0 * a / 1.2 else (2 if fmag[i] >= 2.0 * a / 1.2 else 1)
                if fvol_cap and fvol_hi[i]:
                    q = 1
            else:
                q = 1
            out.append((ts[k_exit], ((fill - L) * s * PT - FEES) * q))
            busy = ts[k_exit]
            i += 1
        return out

    # ---- B. signal micro-grid (flat 1, sel/blind) --------------------------
    print("=== B. signal micro-grid (SEL Apr-May | BLIND Jun-Jul6, flat 1) ===",
          flush=True)
    rows = []
    for k in (8, 9, 10, 11, 12):
        for a in (1.1, 1.2, 1.3):
            for hold in (12, 15, 18):
                out = engine(k=k, a=a, hold=hold)
                s_ = stats(out, SEL_LO, SPLIT); b_ = stats(out, SPLIT, END)
                rows.append({"cfg": f"k{k}_a{a}_h{hold}", **{f"sel_{x}": s_[x] for x in ("usd_wk", "tr_wk")},
                             **{f"bl_{x}": b_[x] for x in ("usd_wk", "tr_wk", "pos", "wd")}})
        print(f"  k{k} done ({time.time()-t0:.0f}s)", flush=True)
    B = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    print(B.head(12).to_string(index=False))
    B.to_csv("research/round43_siggrid.csv", index=False)

    # ---- A. execution physics (ladder, since-Mar) --------------------------
    print("\n=== A. execution physics (ladder 1/2/3, since-Mar) ===", flush=True)
    base = stats(engine(ladder=True), MAR, END)
    print(f"  incumbent            : {base}")
    for cs_ in (60, 120, 300):
        st = stats(engine(cancel_s=cs_, ladder=True), MAR, END)
        print(f"  cancel {cs_:>3}s          : {st}", flush=True)
    for off in (0.75, 1.5):
        st = stats(engine(offset=off, ladder=True), MAR, END)
        print(f"  offset {off}          : {st}", flush=True)
    st = stats(engine(rearm=2, ladder=True), MAR, END)
    print(f"  re-arm 2 bars        : {st}", flush=True)
    st = stats(engine(pexit=True, ladder=True), MAR, END)
    print(f"  passive timer exit   : {st}", flush=True)
    st = stats(engine(rearm=2, pexit=True, ladder=True), MAR, END)
    print(f"  re-arm + passive exit: {st}", flush=True)

    # ---- C. disaster x fvol fine grid (ladder, since-Mar) ------------------
    print("\n=== C. disaster x fvol (ladder, since-Mar) ===", flush=True)
    for dis in (60, 70, 80, 100):
        for fc in (False, True):
            st = stats(engine(disaster=dis, fvol_cap=fc, ladder=True), MAR, END)
            print(f"  dis{dis}{'_fvcap' if fc else '      '}       : {st}",
                  flush=True)

    # ---- D. news clock blackouts (ladder, since-Mar) -----------------------
    print("\n=== D. scheduled-news clock blackouts (ladder, since-Mar) ===",
          flush=True)
    m1 = (hrs >= 14.0) & (hrs < 14.17)
    m2 = (hrs >= 17.92) & (hrs < 18.25)
    for nm, mk in (("skip 14:00-14:10", m1), ("skip 17:55-18:15", m2),
                   ("skip both", m1 | m2)):
        st = stats(engine(ladder=True, mask=mk), MAR, END)
        print(f"  {nm:<18}: {st}", flush=True)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

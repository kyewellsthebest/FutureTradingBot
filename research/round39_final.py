"""Round 39: FINAL COMPLETENESS SWEEP. Everything asserted-but-never-run,
every untested combination of proven parts, and the integrity proof of
the harness itself. After this, the search space reachable with the
available data is closed.
  A. FADESZ+P: passive entries AND magnitude sizing merged (estimated in
     round 29, never actually simulated)
  B. PFADE-15s: same 10-min signal sampled every 15 seconds (faster entry)
  C. Side split: PFADE long-only vs short-only (asymmetry check)
  D. The same fade ON MES: does the edge exist in the S&P itself?
  E. LOOKAHEAD CANARY: signals shifted +1/-1 minute. Causal harness =>
     peek(-1m) should be hugely better, delay(+1m) somewhat worse.
  F. Fee sensitivity: PFADE/FADESZ at $1.52 / $1.96 / $2.50 per RT
  G. PAIRZ execution stress (never padded)
All tick-walked. Windows: since-Mar for champions, Apr+/blind where noted.
"""
import glob, time
import numpy as np, pandas as pd

PT = 2.0
TICK = 0.25
LAT_NS = 65_000_000
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
MAR = pd.Timestamp("2026-03-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")


def stats(out, lo, hi, tag):
    s = pd.Series([p for _, p in out],
                  index=pd.to_datetime([t for t, _ in out], utc=True))
    s = s[(s.index >= lo) & (s.index < hi)]
    w = s.resample("W").sum(); w = w[w != 0]
    if not len(s) or not len(w):
        return f"{tag}: (none)"
    wk = max(len(w), 1)
    return (f"{tag}: ${s.sum()/wk:7.0f}/wk {len(s)/wk:5.1f}tr/wk "
            f"avg ${s.mean():6.2f} worst ${w.min():7.0f} "
            f"pos {(w>0).mean()*100:3.0f}%")


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    m = (ts // 60_000_000_000) * 60_000_000_000
    d = np.sign(np.diff(px, prepend=px[0]))
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
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    mom = c - np.roll(c, 10); mom[:10] = 0
    thr = 1.2 * np.nan_to_num(atr, nan=np.inf)
    fmag = np.abs(mom) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    sig = np.where((mom < -thr) & skip30, 1,
                   np.where((mom > thr) & skip30, -1, 0))
    qty_lad = np.where(fmag >= 3.0, 3, np.where(fmag >= 2.0, 2, 1)).astype(int)
    HN = lambda mins: int(mins * 60_000_000_000)

    def run_pfade(sigv, hold, fees, qty=None, shift_min=0, off=1.0,
                  times=None, closes=None):
        """Passive fade executor; optional signal-time shift for the canary."""
        tt = bts if times is None else times
        cc = c if closes is None else closes
        out = []
        busy = 0
        nn = len(sigv)
        for i in range(nn - 2):
            s = sigv[i]
            t_sig = tt[i] + shift_min * 60_000_000_000
            if s == 0 or t_sig < busy:
                continue
            L = cc[i] - off * s
            a0 = np.searchsorted(ts, t_sig + LAT_NS, side="left")
            a1 = np.searchsorted(ts, t_sig + HN(3), side="left")
            if a0 >= n:
                break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th):
                continue
            fi = a0 + th[0]
            xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, side="left")
            if xe >= n:
                break
            q = 1 if qty is None else qty[i]
            out.append((ts[xe], ((px[xe] - TICK * s - L) * s * PT - fees) * q))
            busy = ts[xe]
        return out

    def run_mkt(sigv, hold, fees, qty=None):
        out = []
        i = 0
        while i < nb - 2:
            s = sigv[i]
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
            q = 1 if qty is None else qty[i]
            out.append((ts[xi], ((px[xi] - TICK * s - e) * s * PT - fees) * q))
            i = j + 1
        return out

    print("=== A. FADESZ+P: passive entry + magnitude ladder (NEVER RUN) ===")
    o1 = run_pfade(sig, 15, 1.50, qty=qty_lad)
    print(" ", stats(o1, MAR, END, "sinceMar"))
    print(" ", stats(o1, SPLIT, END, "blind   "))
    print(" ", stats(o1, MAR, SPLIT, "Mar-May "))
    print(f"  ({time.time()-t0:.0f}s)", flush=True)

    print("\n=== B. PFADE sampled at 15s (faster reaction) ===")
    m15 = (ts // 15_000_000_000) * 15_000_000_000
    b15 = pd.DataFrame({"m": m15, "px": px}).groupby("m")["px"].last()
    b15.index = pd.to_datetime(b15.index, utc=True)
    c15 = b15.to_numpy(); i15 = b15.index
    t15 = i15.asi8 + 15_000_000_000
    h15 = np.asarray(i15.hour) + np.asarray(i15.minute) / 60.0
    sk15 = (h15 >= 14.0) & (h15 < 20.9)
    mom15g = c15 - np.roll(c15, 40); mom15g[:40] = 0     # 10 min in 15s bars
    atr15 = pd.Series(np.abs(c15 - np.roll(c15, 4))).rolling(80).mean().to_numpy()
    thr15 = 1.2 * 2.2 * np.nan_to_num(atr15, nan=np.inf)  # scale ~1m ATR
    s15 = np.where((mom15g < -thr15) & sk15, 1,
                   np.where((mom15g > thr15) & sk15, -1, 0))
    o2 = run_pfade(s15, 15, 1.50, times=t15, closes=c15)
    print(" ", stats(o2, MAR, END, "sinceMar"))
    print(f"  ({time.time()-t0:.0f}s)", flush=True)

    print("\n=== C. PFADE side split ===")
    for nm, sv in (("long-only ", np.where(sig > 0, sig, 0)),
                   ("short-only", np.where(sig < 0, sig, 0))):
        oo = run_pfade(sv, 15, 1.50)
        print(" ", stats(oo, MAR, END, nm))
    print(f"  ({time.time()-t0:.0f}s)", flush=True)

    print("\n=== D. same fade on MES (does the edge exist in ES?) ===")
    mes = pd.concat([pd.read_parquet(f)[["ts", "price"]]
                     for f in sorted(glob.glob(
                         "/tmp/claude-0/westicks/MESU6_2026*.parquet"))
                     if pd.read_parquet(f).shape[0] > 0], ignore_index=True) \
        .sort_values("ts")
    ets, epx = mes["ts"].to_numpy(), mes["price"].to_numpy()
    em = (ets // 60_000_000_000) * 60_000_000_000
    eb = pd.DataFrame({"m": em, "px": epx}).groupby("m")["px"].agg(
        open="first", high="max", low="min", close="last")
    eb.index = pd.to_datetime(eb.index, utc=True)
    eo, eh, el, ec = (eb[k].to_numpy() for k in ("open", "high", "low", "close"))
    ei_ = eb.index; ebts = ei_.asi8 + 60_000_000_000
    ehr = np.asarray(ei_.hour) + np.asarray(ei_.minute) / 60.0
    esk = (ehr >= 14.0) & (ehr < 20.9)
    er1 = ec - np.roll(ec, 1); er1[0] = 0
    etr = np.maximum(eh - el, np.abs(er1))
    eatr = pd.Series(etr).rolling(20).mean().to_numpy()
    emom = ec - np.roll(ec, 10); emom[:10] = 0
    ethr = 1.2 * np.nan_to_num(eatr, nan=np.inf)
    esig = np.where((emom < -ethr) & esk, 1,
                    np.where((emom > ethr) & esk, -1, 0))
    # MES executor: $1.25/pt, tick 0.25, $1.50 fee (approx micro rate)
    outE = []
    busy = 0
    ne = len(ets)
    for i in range(len(esig) - 2):
        s = esig[i]
        if s == 0 or ebts[i] < busy:
            continue
        L = ec[i] - 1.0 * s
        a0 = np.searchsorted(ets, ebts[i] + LAT_NS, side="left")
        a1 = np.searchsorted(ets, ebts[i] + HN(3), side="left")
        if a0 >= ne:
            break
        seg = epx[a0:a1]
        th = np.flatnonzero(seg * s < (L - 0.25 * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + th[0]
        xe = np.searchsorted(ets, ets[fi] + HN(15) + LAT_NS, side="left")
        if xe >= ne:
            break
        outE.append((ets[xe], (epx[xe] - 0.25 * s - L) * s * 1.25 - 1.50))
        busy = ets[xe]
    print(" ", stats(outE, pd.Timestamp("2026-04-01", tz="UTC"), END,
                     "MES PFADE Apr+"))
    print(f"  ({time.time()-t0:.0f}s)", flush=True)

    print("\n=== E. LOOKAHEAD CANARY (harness causality proof) ===")
    for sh, nm in ((0, "baseline "), (-1, "peek -1m "), (1, "delay +1m")):
        oo = run_pfade(sig, 15, 1.50, shift_min=sh)
        print(" ", stats(oo, MAR, END, nm))
    print(f"  ({time.time()-t0:.0f}s)", flush=True)

    print("\n=== F. fee sensitivity ===")
    for fee in (1.52, 1.96, 2.50):
        oo = run_pfade(sig, 15, fee)
        print(" ", stats(oo, MAR, END, f"PFADE  fee${fee}"))
        oo = run_pfade(sig, 15, fee, qty=qty_lad)
        print(" ", stats(oo, MAR, END, f"FADESZ+P fee${fee}"))
    print(f"  ({time.time()-t0:.0f}s)", flush=True)

    print("\n=== G. PAIRZ stress (60m z3 t30) ===")
    mesb = pd.DataFrame({"m": em, "px": epx}).groupby("m")["px"].last()
    mesb.index = pd.to_datetime(mesb.index, utc=True)
    bb = b.join(mesb.rename("es"), how="left")
    esf = bb["es"].ffill().to_numpy()
    lsp = np.log(c) - np.log(esf)
    mu = pd.Series(lsp).rolling(60).mean().to_numpy()
    sd = pd.Series(lsp).rolling(60).std().to_numpy()
    zz = (lsp - mu) / np.where(np.nan_to_num(sd) > 0, sd, np.inf)
    rthm = (hrs >= 13.5) & (hrs < 20.9)
    zs = np.where((zz < -3) & rthm, 1, np.where((zz > 3) & rthm, -1, 0))
    for pad, lat, nm in ((0.25, 65_000_000, "1t 65ms  "),
                         (0.50, 200_000_000, "2t 200ms"),
                         (0.75, 500_000_000, "3t 500ms")):
        out = []
        i = 0
        busy = 0
        while i < nb - 32:
            s = zs[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            ei2 = np.searchsorted(ts, bts[i] + lat, side="left")
            if ei2 >= n:
                break
            e = px[ei2] + pad * s
            xi = np.searchsorted(ts, bts[i] + HN(30) + lat, side="left")
            if xi >= n:
                break
            out.append((ts[xi], (px[xi] - pad * s - e) * s * PT - 1.50))
            busy = ts[xi]
            i += 1
        print(" ", stats(out, pd.Timestamp("2026-04-01", tz="UTC"), END, nm))
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

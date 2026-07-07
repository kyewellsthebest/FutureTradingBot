"""Round 26: ONE-STRATEGY hunt, higher return. Recent-window protocol
(select Apr-May 2026, blind Jun 1 - Jul 6), tick-walked fills, $1.50/RT
commission per contract. No combined strategies — each row is a single
self-contained rule set. New avenues:
  A. IMBF event-exit: ride the flow until it flips (not a fixed timer)
  B. IMBF dynamic size: 1-3 MNQ by burst magnitude (one strategy, sized)
  C. Block-print follow: signed sum of >=20-lot prints
  D. Absorption reversal: heavy one-sided volume, no price progress -> fade
  E. Stop-run reversal: day high/low taken out then rejected -> reverse
  F. VWAP bands: 2-sigma fade and band-break follow
  G. Speed-of-tape: tick-rate burst follow
  H. Ignition bars: huge range + huge volume 1m bar -> follow
  I. FADE event-exit: exit when the overextension has mean-reverted
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
    big = np.where(sz >= 20, d * sz, 0.0)
    g = pd.DataFrame({"m": m, "px": px, "sz": sz, "iv": d * sz, "bg": big,
                      "pv": px * sz})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), iv=("iv", "sum"),
                           bg=("bg", "sum"), nt=("px", "size"),
                           pv=("pv", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    o = b["open"].to_numpy(); h = b["high"].to_numpy()
    l = b["low"].to_numpy(); c = b["close"].to_numpy()
    vol = b["vol"].to_numpy(); iv = b["iv"].to_numpy()
    bg = b["bg"].to_numpy(); nt = b["nt"].to_numpy(); pv = b["pv"].to_numpy()
    idx = b.index
    bts = idx.asi8 + 60_000_000_000
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize()
    nb = len(c)
    rth = (hrs >= 13.5) & (hrs < 20.9)
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    bga = pd.Series(bg).rolling(10).sum().to_numpy()
    bgs = pd.Series(np.abs(bg)).rolling(30).mean().to_numpy()
    vma = pd.Series(vol).rolling(30).mean().to_numpy()
    ntma = pd.Series(nt).rolling(30).mean().to_numpy()
    mom10 = c - np.roll(c, 10); mom10[:10] = 0

    def tick_at(t_ns):
        i = np.searchsorted(ts, t_ns + LAT_NS, side="left")
        return i if i < n else None

    def run_ev(sig, qty, exit_long, exit_short, min_hold, max_hold):
        """Event exit on 1m grid: exit at first bar close where the exit
        condition for the held side is true (after min_hold), else timer."""
        out = []
        i = 0
        while i < nb - 2:
            s = sig[i]
            if s == 0:
                i += 1; continue
            q = qty[i] if qty is not None else 1
            ei = tick_at(bts[i])
            if ei is None:
                break
            entry = px[ei] + TICK * s
            jend = min(i + max_hold, nb - 1)
            j = i + min_hold
            cond = exit_long if s > 0 else exit_short
            while j < jend and not cond[j]:
                j += 1
            xi = tick_at(bts[j])
            if xi is None:
                break
            fill = px[xi] - TICK * s
            out.append((ts[xi], ((fill - entry) * s * PT - FEES) * q))
            i = j + 1
        return out

    def run_t(sig, hold, qty=None):
        z_ = np.zeros(nb, bool)
        return run_ev(sig, qty, z_, z_, hold, hold)

    def st(out, lo, hi):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        if not len(s):
            return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0)
        w = s.resample("W").sum(); w = w[w != 0]
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

    # ---- A. IMBF event-exit ------------------------------------------------
    thr3 = 3.0 * np.nan_to_num(ias, nan=np.inf)
    base = np.where((ima > thr3) & rth, 1, np.where((ima < -thr3) & rth, -1, 0))
    flipL = np.nan_to_num(ima) < 0
    flipS = np.nan_to_num(ima) > 0
    decayL = np.nan_to_num(ima) < np.nan_to_num(ias)
    decayS = np.nan_to_num(ima) > -np.nan_to_num(ias)
    for nm, xl, xs in (("flip", flipL, flipS), ("decay", decayL, decayS)):
        for mh, xh in ((5, 60), (5, 120), (10, 240)):
            add(f"A_IMBFev_{nm}_min{mh}_max{xh}",
                run_ev(base, None, xl, xs, mh, xh))
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. IMBF dynamic size ---------------------------------------------
    mag = np.abs(np.nan_to_num(ima)) / np.where(np.nan_to_num(ias) > 0, ias, np.inf)
    qty = np.where(mag >= 10, 3, np.where(mag >= 6, 2, 1)).astype(int)
    for hold in (30, 45):
        add(f"B_IMBFsz_t{hold}", run_t(base, hold, qty=qty))
    zb = np.zeros(nb, bool)
    add("B_IMBFsz_flip_max120", run_ev(base, qty, flipL, flipS, 5, 120))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. block-print follow --------------------------------------------
    for M in (2.0, 4.0):
        thr = M * np.nan_to_num(bgs, nan=np.inf)
        sg = np.where((bga > thr) & rth, 1, np.where((bga < -thr) & rth, -1, 0))
        for hold in (15, 30, 60):
            add(f"C_BLOCK_m{M}_t{hold}", run_t(sg, hold))
        add(f"C_BLOCK_m{M}_flip", run_ev(sg, None,
                                         np.nan_to_num(bga) < 0,
                                         np.nan_to_num(bga) > 0, 5, 120))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. absorption reversal -------------------------------------------
    rng = h - l
    rmed = pd.Series(rng).rolling(60).median().to_numpy()
    heavy = np.abs(np.nan_to_num(ima)) > 3 * np.nan_to_num(ias, nan=np.inf)
    quiet = rng < 0.8 * np.nan_to_num(rmed, nan=0)
    sg = np.where(heavy & quiet & (ima > 0) & rth, -1,
                  np.where(heavy & quiet & (ima < 0) & rth, 1, 0))
    for hold in (15, 30, 60):
        add(f"D_ABSORB_t{hold}", run_t(sg, hold))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. stop-run reversal ---------------------------------------------
    dhi = pd.Series(h, index=idx).groupby(dk).cummax().shift(1).to_numpy()
    dlo = pd.Series(l, index=idx).groupby(dk).cummin().shift(1).to_numpy()
    tookhi = (h > np.nan_to_num(dhi, nan=np.inf) + 2) & (c < dhi)
    tooklo = (l < np.nan_to_num(dlo, nan=-np.inf) - 2) & (c > dlo)
    sg = np.where(tooklo & skip30, 1, np.where(tookhi & skip30, -1, 0))
    for hold in (30, 60, 120):
        add(f"E_STOPRUN_t{hold}", run_t(sg, hold))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- F. VWAP bands ------------------------------------------------------
    dfv = pd.DataFrame({"d": dk, "pv": pv, "v": vol}, index=idx)
    cpv = dfv.groupby("d")["pv"].cumsum().to_numpy()
    cv = dfv.groupby("d")["v"].cumsum().to_numpy()
    vwap = np.where(cv > 0, cpv / cv, np.nan)
    dev = c - vwap
    dsd = pd.Series(dev).rolling(60).std().to_numpy()
    zz = dev / np.where(np.nan_to_num(dsd) > 0, dsd, np.inf)
    sgF = np.where((zz < -2) & rth, 1, np.where((zz > 2) & rth, -1, 0))
    sgB = np.where((zz > 2) & rth, 1, np.where((zz < -2) & rth, -1, 0))
    for nm, sg in (("F_VWAPfade", sgF), ("F_VWAPbreak", sgB)):
        for hold in (15, 30, 60):
            add(f"{nm}_t{hold}", run_t(sg, hold))
    print(f"[F] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- G. speed-of-tape ---------------------------------------------------
    fast = nt > 4 * np.nan_to_num(ntma, nan=np.inf)
    up1 = c > np.roll(c, 1)
    sg = np.where(fast & up1 & rth, 1, np.where(fast & ~up1 & rth, -1, 0))
    for hold in (5, 15, 30):
        add(f"G_SPEED_t{hold}", run_t(sg, hold))
    sg2 = -sg
    for hold in (15, 30):
        add(f"G_SPEEDR_t{hold}", run_t(sg2, hold))
    print(f"[G] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- H. ignition bars ---------------------------------------------------
    ign = (tr > 3 * np.nan_to_num(atr, nan=np.inf)) & \
          (vol > 3 * np.nan_to_num(vma, nan=np.inf))
    sg = np.where(ign & (c > o) & rth, 1, np.where(ign & (c < o) & rth, -1, 0))
    for hold in (15, 30, 60):
        add(f"H_IGNITE_t{hold}", run_t(sg, hold))
    add("H_IGNITE_flip", run_ev(sg, None, np.nan_to_num(ima) < 0,
                                np.nan_to_num(ima) > 0, 5, 120))
    print(f"[H] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- I. FADE event-exit -------------------------------------------------
    thrf = 1.2 * np.nan_to_num(atr, nan=np.inf)
    sgf = np.where((mom10 < -thrf) & skip30, 1,
                   np.where((mom10 > thrf) & skip30, -1, 0))
    revL = np.nan_to_num(mom10) > 0        # long fade done when mom back >0
    revS = np.nan_to_num(mom10) < 0
    for mh, xh in ((3, 30), (5, 45), (5, 90)):
        add(f"I_FADEev_min{mh}_max{xh}", run_ev(sgf, None, revL, revS, mh, xh))
    print(f"[I] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round26_single.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "bl_pos"]
    print(f"\n{len(out)} single-strategy configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT $/wk (blind is the verdict):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(20).to_string(index=False))


if __name__ == "__main__":
    main()

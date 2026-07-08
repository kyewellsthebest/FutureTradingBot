"""Round 38: ORDER BOOK battery — first bid/ask data of the project.
Quotes: Q_MNQU6 Jun 8 - Jul 8 (31 days, ~31M updates/day) aggregated to
a 1-second book state. Signals from the BOOK; entries walked through NQ
trade ticks as always, flat 1 MNQ, $1.50/RT.
Windows (thin, flagged): SELECT Jun 8-18, BLIND Jun 28 - Jul 6 (NQ trade
gap Jun 19-27 and trade data ends Jul 6).
  A. Book imbalance follow/fade (bid vs ask size, 30s/120s means)
  B. Spread-stress states (spread > 1 tick)
  C. Quote-pull: one side's size collapsing -> price runs from that side
  D. PFADE gated by book agreement at signal time
  E. Microprice divergence: size-weighted mid vs trade price
"""
import glob, os, time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SEL_LO = pd.Timestamp("2026-06-08", tz="UTC")
SEL_HI = pd.Timestamp("2026-06-19", tz="UTC")
BL_LO = pd.Timestamp("2026-06-28", tz="UTC")
BL_HI = pd.Timestamp("2026-07-07", tz="UTC")
CACHE = "data/tick/quotes_1s.npz"


def build_book():
    if os.path.exists(CACHE):
        z = np.load(CACHE)
        return z["sec"], z["bid"], z["ask"], z["bs"], z["asz"]
    secs, bids, asks, bss, ass_ = [], [], [], [], []
    for f in sorted(glob.glob("/tmp/claude-0/quotes/Q_MNQU6_2026*.parquet")):
        t = pd.read_parquet(f)
        if not len(t):
            continue
        t = t.sort_values("ts", kind="mergesort")
        s = (t["ts"].to_numpy() // 1_000_000_000).astype(np.int64)
        g = pd.DataFrame({"s": s, "b": t["bid"].to_numpy(),
                          "a": t["ask"].to_numpy(),
                          "bs": t["bid_size"].to_numpy(float),
                          "as_": t["ask_size"].to_numpy(float)})
        a = g.groupby("s").agg(b=("b", "last"), a=("a", "last"),
                               bs=("bs", "mean"), as_=("as_", "mean"))
        secs.append(a.index.to_numpy()); bids.append(a["b"].to_numpy())
        asks.append(a["a"].to_numpy()); bss.append(a["bs"].to_numpy())
        ass_.append(a["as_"].to_numpy())
        print(f"{os.path.basename(f)}: {len(t):,} -> {len(a):,}s", flush=True)
    sec = np.concatenate(secs); order = np.argsort(sec, kind="mergesort")
    sec = sec[order]
    bid = np.concatenate(bids)[order]; ask = np.concatenate(asks)[order]
    bs = np.concatenate(bss)[order]; asz = np.concatenate(ass_)[order]
    np.savez_compressed(CACHE, sec=sec, bid=bid, ask=ask, bs=bs, asz=asz)
    return sec, bid, ask, bs, asz


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px = z["ts"], z["px"]
    n = len(ts)
    sec, bid, ask, bs, asz = build_book()
    ng = len(sec)
    print(f"book seconds: {ng:,} | NQ ticks: {n:,} ({time.time()-t0:.0f}s)",
          flush=True)
    gts = sec * 1_000_000_000 + 1_000_000_000        # state known at sec close
    tsec = pd.to_datetime(sec, unit="s", utc=True)
    hrs = np.asarray(tsec.hour) + np.asarray(tsec.minute) / 60.0
    rth = (hrs >= 13.6) & (hrs < 20.65)
    mid = (bid + ask) / 2
    spread = ask - bid
    imb = (bs - asz) / np.where(bs + asz > 0, bs + asz, np.inf)

    def roll(x, k, fn="mean"):
        return getattr(pd.Series(x).rolling(k), fn)().to_numpy()

    imb30 = roll(imb, 30); imb120 = roll(imb, 120)
    bs30 = roll(bs, 30); as30 = roll(asz, 30)
    mom600 = mid - np.roll(mid, 600); mom600[:600] = 0
    atrsec = roll(np.abs(mid - np.roll(mid, 60)), 1200)
    micro = np.where(bs + asz > 0, (bid * asz + ask * bs) / (bs + asz), mid)

    def run(sig_idx, sides, hold_min):
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for i_, s in zip(sig_idx, sides):
            t = gts[i_]
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

    def st(out, lo, hi):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        if not len(s):
            return dict(usd_wk=0.0, tr_wk=0.0, per=0.0)
        days = max((s.index.max() - s.index.min()).days, 1)
        wk = max(days / 7.0, 0.5)
        return dict(usd_wk=round(s.sum() / wk, 0), tr_wk=round(len(s) / wk, 1),
                    per=round(s.mean(), 2))

    rows = []

    def add(name, out):
        a = st(out, SEL_LO, SEL_HI); b = st(out, BL_LO, BL_HI)
        rows.append({"name": name, "sel_usd_wk": a["usd_wk"],
                     "sel_tr_wk": a["tr_wk"], "sel_per": a["per"],
                     "bl_usd_wk": b["usd_wk"], "bl_tr_wk": b["tr_wk"],
                     "bl_per": b["per"]})

    def fire_once(cond):
        """Transition-triggered indices."""
        c = np.asarray(cond, bool)
        return np.flatnonzero(c & ~np.roll(c, 1))

    # ---- A. book imbalance -------------------------------------------------
    for W, arr in (("30s", imb30), ("120s", imb120)):
        for TH in (0.3, 0.5):
            li = fire_once((arr > TH) & rth)
            si = fire_once((arr < -TH) & rth)
            allidx = np.sort(np.concatenate([li, si]))
            sides = np.where(np.isin(allidx, li), 1, -1)
            for hold in (5, 15, 30):
                add(f"A_IMB{W}_th{TH}_F_t{hold}", run(allidx, sides, hold))
                add(f"A_IMB{W}_th{TH}_R_t{hold}", run(allidx, -sides, hold))
        print(f"[A {W}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. spread stress ---------------------------------------------------
    wide = spread > 0.3
    up1 = mid > np.roll(mid, 5)
    li = fire_once(wide & up1 & rth); si = fire_once(wide & ~up1 & rth)
    allidx = np.sort(np.concatenate([li, si]))
    sides = np.where(np.isin(allidx, li), 1, -1)
    for hold in (5, 15):
        add(f"B_WIDEF_t{hold}", run(allidx, sides, hold))
        add(f"B_WIDER_t{hold}", run(allidx, -sides, hold))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. quote pull -------------------------------------------------------
    bidpull = (bs30 < 0.3 * np.roll(bs30, 60)) & (np.roll(bs30, 60) > 0)
    askpull = (as30 < 0.3 * np.roll(as30, 60)) & (np.roll(as30, 60) > 0)
    li = fire_once(askpull & ~bidpull & rth)     # ask vanishing -> up
    si = fire_once(bidpull & ~askpull & rth)
    allidx = np.sort(np.concatenate([li, si]))
    sides = np.where(np.isin(allidx, li), 1, -1)
    for hold in (5, 15, 30):
        add(f"C_PULL_t{hold}", run(allidx, sides, hold))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. PFADE gated by book ----------------------------------------------
    fade_l = (mom600 < -6 * np.nan_to_num(atrsec, nan=np.inf)) & rth
    fade_s = (mom600 > 6 * np.nan_to_num(atrsec, nan=np.inf)) & rth
    for nm, gl, gs in (("agree", imb30 > 0.1, imb30 < -0.1),
                       ("naked", np.ones(ng, bool), np.ones(ng, bool)),
                       ("oppose", imb30 < -0.1, imb30 > 0.1)):
        li = fire_once(fade_l & gl); si = fire_once(fade_s & gs)
        allidx = np.sort(np.concatenate([li, si]))
        sides = np.where(np.isin(allidx, li), 1, -1)
        add(f"D_FADE_{nm}_t15", run(allidx, sides, 15))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. microprice divergence ---------------------------------------------
    mdiv = micro - mid
    li = fire_once((roll(mdiv, 10) > 0.08) & rth)
    si = fire_once((roll(mdiv, 10) < -0.08) & rth)
    allidx = np.sort(np.concatenate([li, si]))
    sides = np.where(np.isin(allidx, li), 1, -1)
    for hold in (5, 15):
        add(f"E_MICRO_t{hold}", run(allidx, sides, hold))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round38_book.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "sel_per",
            "bl_usd_wk", "bl_tr_wk", "bl_per"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (sel=Jun8-18, blind=Jun28-Jul6 — THIN, flagged):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()

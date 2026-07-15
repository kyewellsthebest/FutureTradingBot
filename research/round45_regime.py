"""Round 45: REGIME-MATCHED POOLING. Power upgrade #2.

Question: does the champion family's edge exist in 2.5 years of history
(Jun 2023 - Dec 2025), and specifically in the historical weeks whose
microstructure most resembles the current (Mar-Jul 2026) regime?

Method:
  1. Build 1m bars from nq_ticks_2p5y.parquet (price only, 280M ticks)
     and from ytd2026sz.npz (2026 reference regime).
  2. Weekly microstructure fingerprint on RTH bars (14:00-20:54 UTC):
       f1 rel ATR20 (median atr/price * 1e4)
       f2 10m-move frequency (share of RTH bars with |mom10| > 1.2*ATR20)
       f3 reversion coefficient: corr(mom10, fwd 15m return) on RTH bars
       f4 daily range / price (median, * 1e4)
       f5 tick intensity (ticks per RTH minute, log)
  3. Current-regime centroid = mean fingerprint of Mar-Jul6 2026 weeks;
     z-score all features on the historical distribution; rank historical
     weeks by Euclidean distance to the centroid.
  4. Run price-based strategies (champion MOMR 10/1.2 passive+ladder;
     candidates from round 44 if price-only) over the full history with
     tick-walked fills, then report $/wk, pos%, worst day/week separately
     for the nearest-30 matched weeks, the middle pool and the farthest-30,
     plus per-calendar-year rows.

NOTE: history has no trade sizes, so flow features (iv/fvol) do not exist
pre-2026; only price-based genomes can be judged here. Ladder qty uses
fmag (price-based) as deployed. fvol_cap gates cannot be replicated -> run
without them and say so.
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
HN = lambda m: int(m * 60_000_000_000)


def load_history():
    t0 = time.time()
    import pyarrow.parquet as pq
    tb = pq.read_table("data/tick/nq_ticks_2p5y.parquet",
                       columns=["ts", "price"])
    ts = tb["ts"].to_numpy()
    px = tb["price"].to_numpy()
    del tb
    print(f"history ticks: {len(ts):,} ({time.time()-t0:.0f}s)", flush=True)
    return ts, px


def load_2026():
    z = np.load("data/tick/ytd2026sz.npz")
    return z["ts"], z["px"]


def bars_of(ts, px):
    """Memory-frugal minute bars via reduceat (ticks are time-sorted)."""
    m = ts // 60_000_000_000
    starts = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    ends = np.concatenate((starts[1:], [len(m)]))
    b = pd.DataFrame({
        "open": px[starts],
        "high": np.maximum.reduceat(px, starts),
        "low": np.minimum.reduceat(px, starts),
        "close": px[ends - 1],
        "nt": ends - starts,
    }, index=pd.to_datetime(m[starts] * 60_000_000_000, utc=True))
    return b


def fingerprints(b):
    """Weekly microstructure fingerprint DataFrame."""
    idx = b.index
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    rth = (hrs >= 14.0) & (hrs < 20.9)
    c = b["close"].to_numpy()
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(b["high"].to_numpy() - b["low"].to_numpy(), np.abs(r1))
    atr = pd.Series(tr, index=idx).rolling(20).mean()
    mom10 = pd.Series(c - np.roll(c, 10), index=idx); mom10.iloc[:10] = 0
    fwd15 = pd.Series(np.roll(c, -15) - c, index=idx); fwd15.iloc[-15:] = 0
    df = pd.DataFrame({"close": c, "atr": atr, "mom10": mom10,
                       "fwd15": fwd15, "nt": b["nt"].to_numpy(),
                       "hi": b["high"].to_numpy(), "lo": b["low"].to_numpy()},
                      index=idx)
    df = df[rth]
    wk = df.groupby(pd.Grouper(freq="W"))
    rows = {}
    for w, g in wk:
        if len(g) < 1000:
            continue
        relatr = (g["atr"] / g["close"]).median() * 1e4
        movefreq = (np.abs(g["mom10"]) > 1.2 * g["atr"]).mean()
        ok = g["atr"].notna() & (np.abs(g["mom10"]) > 0)
        rev = g.loc[ok, "mom10"].corr(g.loc[ok, "fwd15"])
        dg = g.groupby(g.index.normalize())
        dayrange = ((dg["hi"].max() - dg["lo"].min())
                    / dg["close"].last()).median() * 1e4
        tickint = np.log10(max(g["nt"].mean(), 1))
        rows[w] = (relatr, movefreq, rev, dayrange, tickint)
    fp = pd.DataFrame(rows, index=["relatr", "movefreq", "rev",
                                   "dayrange", "tickint"]).T
    return fp


def engine(ts, px, b, k=10, a=1.2, hold=15, passive=True, off=1.0,
           cxl=180, l1=2.0, l2=3.0, ent_lo=14.0, ent_hi=20.9):
    """Champion-form engine, price-only, tick-walked fills."""
    n = len(ts)
    idx = b.index
    c = b["close"].to_numpy()
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    rth = (hrs >= ent_lo) & (hrs < ent_hi)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(b["high"].to_numpy() - b["low"].to_numpy(), np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    mom = c - np.roll(c, k); mom[:k] = 0
    thr = a * np.nan_to_num(atr, nan=np.inf)
    fmag = np.abs(mom) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    sig = np.where((mom < -thr) & rth, 1,
                   np.where((mom > thr) & rth, -1, 0))
    bts = idx.asi8 + 60_000_000_000
    nb = len(c)
    out_t = []; out_p = []
    busy = 0; i = 0
    while i < nb - 2:
        s = sig[i]
        if s == 0 or bts[i] < busy:
            i += 1; continue
        q = 1
        if l1 is not None:
            q = 3 if fmag[i] >= l2 * a / 1.2 else \
                (2 if fmag[i] >= l1 * a / 1.2 else 1)
        if passive:
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + int(cxl * 1e9), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                i += 1; continue
            fi = a0 + th_[0]
            entry = L
        else:
            fi = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + TICK * s
        xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, "left")
        if xe >= n: break
        fill = px[xe] - TICK * s
        out_t.append(ts[xe])
        out_p.append(((fill - entry) * s * PT - FEES) * q)
        busy = ts[xe]
        i += 1
    return pd.Series(out_p, index=pd.to_datetime(np.array(out_t), utc=True))


def pool_stats(s, weeks):
    s2 = s[s.index.to_period("W").astype(str).isin(weeks)]
    if not len(s2):
        return dict(n=0)
    wk = s2.resample("W").sum(); wk = wk[wk != 0]
    dy = s2.resample("D").sum(); dy = dy[dy != 0]
    return dict(usd_wk=round(s2.sum() / max(len(wk), 1)),
                pos=round((wk > 0).mean() * 100),
                wd=round(dy.min()), ww=round(wk.min()),
                tr_wk=round(len(s2) / max(len(wk), 1), 1),
                nwk=len(wk))


def main():
    t0 = time.time()
    hts, hpx = load_history()
    hb = bars_of(hts, hpx)
    print(f"history bars: {len(hb):,} {hb.index[0]} .. {hb.index[-1]} "
          f"({time.time()-t0:.0f}s)", flush=True)
    cts, cpx = load_2026()
    cb = bars_of(cts, cpx)

    fp_h = fingerprints(hb)
    fp_c = fingerprints(cb)
    cur = fp_c[fp_c.index >= pd.Timestamp("2026-03-01", tz="UTC")]
    print(f"\nfingerprint weeks: hist {len(fp_h)}, current {len(cur)}",
          flush=True)
    mu, sd = fp_h.mean(), fp_h.std()
    zh = (fp_h - mu) / sd
    zc = (cur - mu) / sd
    cent = zc.mean()
    print("current-regime centroid (z):",
          {k: round(v, 2) for k, v in cent.items()})
    dist = np.sqrt(((zh - cent) ** 2).sum(axis=1)).sort_values()
    wk_str = lambda ix: set(pd.PeriodIndex(ix, freq="W").astype(str))
    near = wk_str(dist.index[:30])
    far = wk_str(dist.index[-30:])
    mid = wk_str(dist.index[30:-30])
    print(f"\nnearest weeks: {sorted(pd.PeriodIndex(dist.index[:10], freq='W').astype(str))}")

    variants = (
        ("CHAMPION FADESZ+P", dict()),
        ("W1 (hour 14-18, ladder 1.5/3, off 0.5, cxl 60)",
         dict(ent_hi=18.0, l1=1.5, off=0.5, cxl=60)),
    )
    for vnm, kw in variants:
        print(f"\n=== {vnm} (price-only form, no fvol machinery) ===",
              flush=True)
        s = engine(hts, hpx, hb, **kw)
        print(f"history trades: {len(s)} ({time.time()-t0:.0f}s)", flush=True)
        for nm, pool in (("NEAR-30 (regime-matched)", near),
                         ("MIDDLE", mid), ("FAR-30 (anti-regime)", far)):
            print(f"  {nm:<26}: {pool_stats(s, pool)}", flush=True)
        for yr in (2023, 2024, 2025):
            sy = s[s.index.year == yr]
            if not len(sy):
                continue
            wk = sy.resample("W").sum(); wk = wk[wk != 0]
            dy = sy.resample("D").sum(); dy = dy[dy != 0]
            print(f"  year {yr}: $/wk {sy.sum()/max(len(wk),1):.0f} "
                  f"pos {(wk>0).mean()*100:.0f}% wd {dy.min():.0f} "
                  f"ww {wk.min():.0f} tr/wk {len(sy)/max(len(wk),1):.1f}",
                  flush=True)
        s26 = engine(cts, cpx, cb, **kw)
        wk = s26.resample("W").sum(); wk = wk[wk != 0]
        dy = s26.resample("D").sum(); dy = dy[dy != 0]
        print(f"  2026 ref: $/wk {s26.sum()/max(len(wk),1):.0f} "
              f"pos {(wk>0).mean()*100:.0f}% wd {dy.min():.0f} "
              f"ww {wk.min():.0f} tr/wk {len(s26)/max(len(wk),1):.1f}",
              flush=True)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

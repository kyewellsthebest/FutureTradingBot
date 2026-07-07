"""Round 24: RECENT-REGIME HUNT with the ultra-realistic tick executor.
User directive: test on the LAST 3 MONTHS only — the regime that exists
now — not 2.5-year averages. Every fill is walked through real ticks:
65 ms latency, one adverse tick on market fills, stops filled on
trade-through with slip, $1.50 commission (user grant; slippage comes
from the tick walk itself, not an assumption).

Data: NQM6 ticks Apr 1 - Jun 18 + MNQU6 ticks Jun 28 - Jul 6 (roll gap
Jun 19-27 is missing at the vendor, noted in weekly outputs).
SELECT = Apr 1 - May 31 (fit/choose), BLIND = Jun 1 - Jul 6 (verdict).
"""
import glob, os, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
STOP_SLIP = 0.25
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
START = pd.Timestamp("2026-04-01", tz="UTC")
CACHE = "data/tick/recent3m.npz"


def load_ticks():
    if os.path.exists(CACHE):
        z = np.load(CACHE)
        return z["ts"], z["px"], z["sz"]
    parts = []
    pf = pq.ParquetFile("data/tick/raw/NQM6.parquet")
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["ts", "price", "size"]).to_pandas()
        t = t[t["ts"] >= START.value]
        if len(t):
            parts.append(t)
    for f in sorted(glob.glob("/tmp/claude-0/weekticks/MNQU6_2026*.parquet")):
        t = pd.read_parquet(f)
        if len(t):
            parts.append(t[["ts", "price", "size"]])
    a = pd.concat(parts, ignore_index=True).sort_values("ts", kind="mergesort")
    ts = a["ts"].to_numpy(np.int64)
    px = a["price"].to_numpy(np.float64)
    sz = a["size"].to_numpy(np.float64)
    np.savez_compressed(CACHE, ts=ts, px=px, sz=sz)
    return ts, px, sz


def build_bars(ts, px, sz):
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px, "sz": sz})
    a = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), nt=("px", "size"))
    a.index = pd.to_datetime(a.index, utc=True)
    return a


class TickExec:
    """Walk real ticks for every fill. Non-overlapping positions."""

    def __init__(self, ts, px):
        self.ts = ts; self.px = px; self.n = len(ts)

    def market_fill(self, t_ns):
        i = np.searchsorted(self.ts, t_ns + LAT_NS, side="left")
        if i >= self.n:
            return None, None
        return i, self.px[i]

    def run(self, sig_times, sig_sides, hold_min, stop_pt=0.0):
        """sig at bar-close time -> market entry, exit after hold (market)
        or on stop trade-through. Returns (exit_time, pnl$) list."""
        out = []
        busy_until = 0
        hold_ns = int(hold_min * 60_000_000_000)
        for t, s in zip(sig_times, sig_sides):
            if t < busy_until:
                continue
            ei, epx = self.market_fill(t)
            if ei is None:
                break
            entry = epx + TICK * s                     # adverse tick on entry
            t_exit = t + hold_ns
            xj = np.searchsorted(self.ts, t_exit + LAT_NS, side="left")
            if xj >= self.n:
                break
            fill_px = None
            if stop_pt > 0:
                stop = entry - stop_pt * s
                seg = self.px[ei:xj]
                hit = np.flatnonzero(seg * s <= stop * s)
                if len(hit):
                    k = ei + hit[0]
                    # trade-through fill: worse of stop and the printing tick
                    raw = min(self.px[k], stop) if s > 0 else max(self.px[k], stop)
                    fill_px = raw - STOP_SLIP * s
                    xj = k
            if fill_px is None:
                fill_px = self.px[xj] - TICK * s        # adverse tick on exit
            pnl = (fill_px - entry) * s * PT - FEES
            out.append((self.ts[xj], pnl))
            busy_until = self.ts[xj]
        return out


def weekly(out, lo=None, hi=None):
    if not out:
        return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0, n=0)
    s = pd.Series([p for _, p in out],
                  index=pd.to_datetime([t for t, _ in out], utc=True))
    if lo is not None:
        s = s[(s.index >= lo)] if hi is None else s[(s.index >= lo) & (s.index < hi)]
    elif hi is not None:
        s = s[s.index < hi]
    if not len(s):
        return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0, n=0)
    w = s.resample("W").sum(); w = w[w != 0]
    weeks = max(len(w), 1)
    return dict(usd_wk=round(s.sum() / weeks, 0), tr_wk=round(len(s) / weeks, 1),
                per=round(s.mean(), 2), worst=round(w.min(), 0),
                pos=round((w > 0).mean() * 100), n=len(s))


def main():
    t0 = time.time()
    ts, px, sz = load_ticks()
    print(f"ticks: {len(ts):,} ({time.time()-t0:.0f}s)", flush=True)
    bars = build_bars(ts, px, sz)
    print(f"1m bars: {len(bars):,}", flush=True)
    ex = TickExec(ts, px)

    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    vol = bars["vol"].to_numpy(); nt = bars["nt"].to_numpy()
    idx = bars.index
    bts = idx.asi8 + 60_000_000_000       # bar CLOSE time (floor + 1min)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize()
    cs = pd.Series(c, index=idx)
    sel_bar = np.asarray(idx < SPLIT)
    rth = (hrs >= 13.5) & (hrs < 20.9)

    ret1 = c - np.roll(c, 1); ret1[0] = 0
    tr = np.maximum(h - l, np.abs(ret1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ema20 = cs.ewm(span=20, adjust=False).mean().to_numpy()
    sma60 = cs.rolling(60).mean().to_numpy()
    sd20 = cs.rolling(20).std().to_numpy()
    vma = pd.Series(vol).rolling(30).mean().to_numpy()
    ntma = pd.Series(nt).rolling(30).mean().to_numpy()
    hi20 = pd.Series(h).rolling(20).max().shift(1).to_numpy()
    lo20 = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    hi60 = pd.Series(h).rolling(60).max().shift(1).to_numpy()
    lo60 = pd.Series(l).rolling(60).min().shift(1).to_numpy()
    momk = {k: c - np.roll(c, k) for k in (3, 5, 15, 30)}
    for k in momk:
        momk[k][:k] = 0
    up = c > o; dn = c < o
    run3 = np.array([all(up[j - 2:j + 1]) for j in range(len(c))]) if len(c) else None
    run3d = np.array([all(dn[j - 2:j + 1]) for j in range(len(c))])
    z60 = (c - sma60) / np.where(sd20 > 0, sd20, np.inf)

    # prev-day high/low
    d_high = pd.Series(h, index=idx).resample("1D").max().dropna()
    d_low = pd.Series(l, index=idx).resample("1D").min().dropna()
    pdh = d_high.shift(1).reindex(dk).to_numpy()
    pdl = d_low.shift(1).reindex(dk).to_numpy()

    F = {}
    for k in (3, 5, 15, 30):
        for thr_atr in (1.5, 3.0):
            thr = thr_atr * np.nan_to_num(atr, nan=np.inf)
            F[f"MOMF_k{k}_a{thr_atr}"] = (momk[k] > thr, momk[k] < -thr)
            F[f"MOMR_k{k}_a{thr_atr}"] = (momk[k] < -thr, momk[k] > thr)
    F["BBF"] = (c > ema20 + 2 * sd20, c < ema20 - 2 * sd20)
    F["BBR"] = (c < ema20 - 2 * sd20, c > ema20 + 2 * sd20)
    F["DON20F"] = (c > hi20, c < lo20)
    F["DON20R"] = (c < lo20, c > hi20)
    F["DON60F"] = (c > hi60, c < lo60)
    F["RUNF"] = (run3, run3d)
    F["RUNR"] = (run3d, run3)
    F["Z60R"] = (z60 < -3, z60 > 3)
    F["Z60F"] = (z60 > 3, z60 < -3)
    F["VSPKF"] = ((vol > 3 * np.nan_to_num(vma, nan=np.inf)) & up,
                  (vol > 3 * np.nan_to_num(vma, nan=np.inf)) & dn)
    F["VSPKR"] = ((vol > 3 * np.nan_to_num(vma, nan=np.inf)) & dn,
                  (vol > 3 * np.nan_to_num(vma, nan=np.inf)) & up)
    F["NTBF"] = ((nt > 3 * np.nan_to_num(ntma, nan=np.inf)) & up,
                 (nt > 3 * np.nan_to_num(ntma, nan=np.inf)) & dn)
    F["PDHF"] = ((np.roll(c, 1) <= np.nan_to_num(pdh, nan=np.inf)) & (c > pdh),
                 (np.roll(c, 1) >= np.nan_to_num(pdl, nan=-np.inf)) & (c < pdl))
    F["PDHR"] = ((h >= pdh) & (c < pdh), (l <= pdl) & (c > pdl))
    # opening-range breakout (first 15/30 min of RTH)
    for orm in (15, 30):
        orh = np.full(len(c), np.nan); orl = np.full(len(c), np.nan)
        fh = (hrs >= 13.5) & (hrs < 13.5 + orm / 60.0)
        dfh = pd.DataFrame({"d": dk, "h": np.where(fh, h, np.nan),
                            "l": np.where(fh, l, np.nan)})
        gh = dfh.groupby("d")["h"].transform("max").to_numpy()
        gl = dfh.groupby("d")["l"].transform("min").to_numpy()
        after = hrs >= 13.5 + orm / 60.0
        F[f"ORB{orm}"] = (after & (c > gh) & (np.roll(c, 1) <= np.roll(gh, 1)),
                          after & (c < gl) & (np.roll(c, 1) >= np.roll(gl, 1)))
    # RSI2 fast
    d1 = cs.diff()
    rup = d1.clip(lower=0).rolling(2).mean()
    rdn = (-d1.clip(upper=0)).rolling(2).mean()
    rsi2 = (100 - 100 / (1 + rup / rdn.replace(0, np.nan))).to_numpy()
    F["RSI2R"] = (rsi2 < 5, rsi2 > 95)
    F["RSI2F"] = (rsi2 > 95, rsi2 < 5)

    rows = []
    n_cfg = 0
    for fname, (rl, rs_) in F.items():
        rl = np.nan_to_num(np.asarray(rl, dtype=float)).astype(bool)
        rs_ = np.nan_to_num(np.asarray(rs_, dtype=float)).astype(bool)
        for sess, smask in (("rth", rth), ("all", np.ones(len(c), bool))):
            sig = np.where(rl & smask, 1, np.where(rs_ & smask, -1, 0))
            live = np.flatnonzero(sig != 0)
            if len(live) < 40:
                continue
            for hold in (5, 15, 30, 60):
                for stop in (0.0, 15.0):
                    out = ex.run(bts[live], sig[live], hold, stop)
                    wsel = weekly(out, hi=SPLIT)
                    wbl = weekly(out, lo=SPLIT)
                    if wsel["n"] + wbl["n"] < 30:
                        continue
                    rows.append({"name": f"{fname}_{sess}_t{hold}_s{int(stop)}",
                                 "sel_usd_wk": wsel["usd_wk"], "sel_tr_wk": wsel["tr_wk"],
                                 "sel_per": wsel["per"], "sel_pos": wsel["pos"],
                                 "bl_usd_wk": wbl["usd_wk"], "bl_tr_wk": wbl["tr_wk"],
                                 "bl_per": wbl["per"], "bl_worst": wbl["worst"],
                                 "bl_pos": wbl["pos"]})
                    n_cfg += 1
        print(f"[{fname}] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/recent3m_results.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "bl_pos"]
    print(f"\n{n_cfg} configs ({time.time()-t0:.0f}s)")
    print("\nTOP 25 by SELECT (Apr-May) $/wk — BLIND (Jun-Jul6) is the verdict:")
    print(out[cols].head(25).to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    ok = ok.sort_values("bl_usd_wk", ascending=False)
    print(f"\npositive BOTH windows: {len(ok)}")
    print(ok[cols].head(25).to_string(index=False) if len(ok) else "(none)")
    hf = ok[ok.bl_tr_wk >= 50]
    print(f"\nhigh-frequency (>=50 tr/wk) both-positive: {len(hf)}")
    print(hf[cols].head(15).to_string(index=False) if len(hf) else "(none)")


if __name__ == "__main__":
    main()

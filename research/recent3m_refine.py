"""Round 24c: refine the RTH overextension fade (MOMR k10-15).
Entry family fixed by round 24b's plateau (k in 10/15, a in 1.2-2.0, RTH).
This pass engineers exits (time vs target/stop, tick-walked trade-through
fills) and context filters (session half, volatility regime, first-30min
skip) — chosen on SELECT (Apr-May), judged on BLIND (Jun-Jul 6).
$1.50 commission; fills walked through real ticks."""
import os, time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
STOP_SLIP = 0.25
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
SEL_LO = pd.Timestamp("2026-04-01", tz="UTC")
CACHE = "data/tick/ytd2026.npz"


def run_bracket(ts, px, sig_times, sig_sides, hold_min, tgt_pt, stop_pt):
    """Market entry; exit at target (trade-through), stop (trade-through,
    slipped) or time, whichever the tape hits first."""
    out = []
    busy_until = 0
    hold_ns = int(hold_min * 60_000_000_000)
    n = len(ts)
    for t, s in zip(sig_times, sig_sides):
        if t < busy_until:
            continue
        ei = np.searchsorted(ts, t + LAT_NS, side="left")
        if ei >= n:
            break
        entry = px[ei] + TICK * s
        xj = np.searchsorted(ts, t + hold_ns + LAT_NS, side="left")
        if xj >= n:
            break
        fill = None; k_exit = xj
        seg = px[ei + 1:xj]
        if len(seg):
            if tgt_pt > 0:
                tgt = entry + tgt_pt * s
                # trade-through: a tick strictly beyond target
                th = np.flatnonzero(seg * s > (tgt + TICK * s) * s - 1e-9)
            else:
                th = np.array([], dtype=int)
            if stop_pt > 0:
                stp = entry - stop_pt * s
                sh = np.flatnonzero(seg * s <= stp * s + 1e-9)
            else:
                sh = np.array([], dtype=int)
            it = th[0] if len(th) else np.inf
            is_ = sh[0] if len(sh) else np.inf
            if is_ <= it and is_ != np.inf:
                k_exit = ei + 1 + int(is_)
                raw = min(px[k_exit], entry - stop_pt * s) if s > 0 \
                    else max(px[k_exit], entry - stop_pt * s)
                fill = raw - STOP_SLIP * s
            elif it != np.inf:
                k_exit = ei + 1 + int(it)
                fill = entry + tgt_pt * s
        if fill is None:
            fill = px[xj] - TICK * s
            k_exit = xj
        out.append((ts[k_exit], (fill - entry) * s * PT - FEES))
        busy_until = ts[k_exit]
    return out


def wk_stats(out, lo, hi):
    s = pd.Series([p for _, p in out],
                  index=pd.to_datetime([t for t, _ in out], utc=True))
    s = s[(s.index >= lo) & (s.index < hi)]
    if not len(s):
        return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0)
    w = s.resample("W").sum(); w = w[w != 0]
    weeks = max(len(w), 1)
    return dict(usd_wk=round(s.sum() / weeks, 0), tr_wk=round(len(s) / weeks, 1),
                per=round(s.mean(), 2), worst=round(w.min(), 0),
                pos=round((w > 0).mean() * 100))


def main():
    t0 = time.time()
    z = np.load(CACHE)
    ts, px = z["ts"], z["px"]
    print(f"ticks: {len(ts):,}", flush=True)
    m = (ts // 60_000_000_000) * 60_000_000_000
    bars = pd.DataFrame({"m": m, "px": px}).groupby("m")["px"].agg(
        open="first", high="max", low="min", close="last")
    bars.index = pd.to_datetime(bars.index, utc=True)
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    idx = bars.index
    bts = idx.asi8 + 60_000_000_000
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    ret1 = c - np.roll(c, 1); ret1[0] = 0
    tr = np.maximum(h - l, np.abs(ret1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    atr_day = pd.Series(tr, index=idx).rolling(390).mean().to_numpy()
    atr_med = np.nanmedian(atr_day)
    END = pd.Timestamp("2026-07-07", tz="UTC")

    filters = {
        "none": (hrs >= 13.5) & (hrs < 20.9),
        "skip30": (hrs >= 14.0) & (hrs < 20.9),
        "am": (hrs >= 13.5) & (hrs < 17.0),
        "pm": (hrs >= 17.0) & (hrs < 20.9),
        "hivol": (hrs >= 13.5) & (hrs < 20.9) & (atr_day > atr_med),
        "lovol": (hrs >= 13.5) & (hrs < 20.9) & (atr_day <= atr_med),
    }
    exits = [("t15", 15, 0, 0), ("t10", 10, 0, 0), ("t20", 20, 0, 0),
             ("t15_tgt5", 15, 5, 0), ("t15_tgt8", 15, 8, 0),
             ("t15_tgt5_s10", 15, 5, 10), ("t15_tgt8_s15", 15, 8, 15),
             ("t30_tgt10_s15", 30, 10, 15), ("t15_s10", 15, 0, 10)]
    rows = []
    for k in (10, 15):
        mom = c - np.roll(c, k); mom[:k] = 0
        for a in (1.2, 1.5, 2.0):
            thr = a * np.nan_to_num(atr, nan=np.inf)
            for fname, fmask in filters.items():
                sig = np.where((mom < -thr) & fmask, 1,
                               np.where((mom > thr) & fmask, -1, 0))
                live = np.flatnonzero(sig != 0)
                if len(live) < 100:
                    continue
                for ename, hold, tgt, stp in exits:
                    out = run_bracket(ts, px, bts[live], sig[live], hold, tgt, stp)
                    wsel = wk_stats(out, SEL_LO, SPLIT)
                    wbl = wk_stats(out, SPLIT, END)
                    rows.append({"name": f"k{k}_a{a}_{fname}_{ename}",
                                 "sel_usd_wk": wsel["usd_wk"], "sel_tr_wk": wsel["tr_wk"],
                                 "bl_usd_wk": wbl["usd_wk"], "bl_tr_wk": wbl["tr_wk"],
                                 "bl_per": wbl["per"], "bl_worst": wbl["worst"],
                                 "bl_pos": wbl["pos"]})
            print(f"[k{k} a{a}] done ({time.time()-t0:.0f}s)", flush=True)
    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/recent3m_refine.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "bl_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nTOP 25 by SELECT — blind is the verdict:")
    print(out[cols].head(25).to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}/{len(out)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(20).to_string(index=False))


if __name__ == "__main__":
    main()

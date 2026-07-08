"""Round 31: PFADE full optimization. The passive-entry fade holds the
flat-1-MNQ crown ($727/wk @107tr since Mar); this sweeps its complete
parameter space with passive fills (never done — t15 was inherited from
the market-entry version) plus risk overlays as single-strategy features:
  - threshold a in 0.8/1.0/1.2 (lower = more trades, passive protects econ)
  - offset 1/2 pts, cancel 3m
  - hold 10/15/20/30
  - sessions: skip30 / full rth / globex / eu (passive changes overnight econ)
  - overlays on the select-best: daily stop -300/-500, 3-loss streak halt
Select Apr-May, blind Jun 1 - Jul 6, since-Mar consistency. $1.50/RT.
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
    ts, px = z["ts"], z["px"]
    n = len(ts)
    print(f"ticks: {n:,}", flush=True)
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px})
    b = g.groupby("m")["px"].agg(open="first", high="max", low="min",
                                 close="last")
    b.index = pd.to_datetime(b.index, utc=True)
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    idx = b.index; bts = idx.asi8 + 60_000_000_000; nb = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    mom = c - np.roll(c, 10); mom[:10] = 0
    days = idx.normalize().asi8
    HN = lambda mins: int(mins * 60_000_000_000)

    SESS = {
        "skip30": (hrs >= 14.0) & (hrs < 20.9),
        "rth": (hrs >= 13.5) & (hrs < 20.9),
        "globex": (hrs >= 22.0) | (hrs < 7.0),
        "eu": (hrs >= 7.0) & (hrs < 13.5),
    }

    def run_pfade(a_, off, hold, smask, day_stop=0.0, streak_halt=0):
        thr = a_ * np.nan_to_num(atr, nan=np.inf)
        sig = np.where((mom < -thr) & smask, 1,
                       np.where((mom > thr) & smask, -1, 0))
        out = []
        busy = 0
        i = 0
        day_pnl = {}
        day_streak = {}
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            dk = days[i]
            if day_stop > 0 and day_pnl.get(dk, 0.0) <= -day_stop:
                i += 1; continue
            if streak_halt > 0 and day_streak.get(dk, 0) >= streak_halt:
                i += 1; continue
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, side="left")
            a1 = np.searchsorted(ts, bts[i] + HN(3), side="left")
            if a0 >= n:
                break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th):
                i += 1; continue
            fi = a0 + th[0]
            xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, side="left")
            if xe >= n:
                break
            pnl = (px[xe] - TICK * s - L) * s * PT - FEES
            out.append((ts[xe], pnl))
            day_pnl[dk] = day_pnl.get(dk, 0.0) + pnl
            day_streak[dk] = day_streak.get(dk, 0) + 1 if pnl < 0 else 0
            busy = ts[xe]
            i += 1
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
        mr = st(out, MAR, END)
        rows.append({"name": name, "sel_usd_wk": a["usd_wk"],
                     "sel_tr_wk": a["tr_wk"], "bl_usd_wk": bl["usd_wk"],
                     "bl_tr_wk": bl["tr_wk"], "bl_per": bl["per"],
                     "bl_worst": bl["worst"], "mar_usd_wk": mr["usd_wk"],
                     "mar_worst": mr["worst"], "mar_pos": mr["pos"]})

    # ---- main grid (skip30 + rth only for the full sweep) ------------------
    for sess in ("skip30", "rth"):
        for a_ in (0.8, 1.0, 1.2):
            for off in (1.0, 2.0):
                for hold in (10, 15, 20, 30):
                    add(f"{sess}_a{a_}_off{off}_t{hold}",
                        run_pfade(a_, off, hold, SESS[sess]))
            print(f"[{sess} a{a_}] done ({time.time()-t0:.0f}s)", flush=True)
    # ---- other sessions, champion params only ------------------------------
    for sess in ("globex", "eu"):
        for a_ in (1.0, 1.2):
            add(f"{sess}_a{a_}_off1.0_t15",
                run_pfade(a_, 1.0, 15, SESS[sess]))
        print(f"[{sess}] done ({time.time()-t0:.0f}s)", flush=True)
    # ---- overlays on the incumbent (a1.2 off1 t15 skip30) ------------------
    for ds in (300.0, 500.0):
        add(f"skip30_a1.2_off1.0_t15_dstop{int(ds)}",
            run_pfade(1.2, 1.0, 15, SESS["skip30"], day_stop=ds))
    add("skip30_a1.2_off1.0_t15_streak3",
        run_pfade(1.2, 1.0, 15, SESS["skip30"], streak_halt=3))
    print(f"[overlays] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round31_pfade_opt.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "mar_usd_wk", "mar_worst", "mar_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nTOP 30 by SELECT (incumbent: skip30_a1.2_off1.0_t15 = $727/wk sinceMar):")
    print(out[cols].head(30).to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("mar_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()
